import queue
from types import SimpleNamespace

import numpy as np


class ImmediateThread:
    def __init__(self, target=None, daemon=None, **kwargs):
        self.target = target

    def start(self):
        if self.target:
            self.target()


def test_load_and_save_config_error_paths(vd, monkeypatch, capsys):
    monkeypatch.setattr(vd.os.path, "exists", lambda _: True)
    monkeypatch.setattr(
        "builtins.open",
        lambda *a, **k: (_ for _ in ()).throw(OSError("bad open")),
    )

    cfg = vd.load_config()
    assert "STT_ENDPOINT" in cfg
    assert "Error loading config" in capsys.readouterr().out

    monkeypatch.setattr(
        "builtins.open",
        lambda *a, **k: (_ for _ in ()).throw(OSError("bad save")),
    )
    vd.save_config({"x": 1})
    assert "Error saving config" in capsys.readouterr().out


def test_audio_recorder_init_falls_back_when_query_fails(vd, monkeypatch):
    monkeypatch.setattr(
        vd.sd,
        "query_devices",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no device")),
    )
    rec = vd.AudioRecorder()
    assert rec.rate == 44100


def test_get_input_devices_success_and_exception(vd, monkeypatch):
    fake_devices = [
        {"name": "Dummy (hw:0,0)", "max_input_channels": 2, "hostapi": 0},
    ]
    monkeypatch.setattr(vd.sd, "query_devices", lambda: fake_devices)

    fake_pactl_src = (
        '\tName: alsa_input.test_device_1\n'
        '\tDescription: Test Mic 1\n'
        '\tProperties:\n'
        '\t\talsa.card = "0"\n'
    )
    monkeypatch.setattr(
        vd.subprocess, "run",
        lambda cmd, **kw: SimpleNamespace(stdout=fake_pactl_src, returncode=0),
    )

    rec = vd.AudioRecorder()
    devices = rec.get_input_devices()
    assert len(devices) >= 1
    assert "(audio)" in devices[0]["name"]
    assert devices[0]["index"] >= 0

    monkeypatch.setattr(
        vd.sd,
        "query_devices",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert rec.get_input_devices() == []


def test_audio_start_drains_queue_and_callback_streaming(vd, monkeypatch):
    vd.STREAMING_MODE = True
    rec = vd.AudioRecorder()
    rec.stream_queue.put(np.zeros((2, 1)))
    rec.stream_queue.put(np.zeros((2, 1)))

    rec.start(device_index="not-an-int")
    assert rec.stream is not None
    assert rec.stream_queue.empty()

    rec.stream.callback(np.ones((4, 1)), 4, None, "warn")
    assert len(rec.frames) == 1
    assert not rec.stream_queue.empty()


def test_audio_start_raises_when_stream_creation_fails(vd, monkeypatch):
    rec = vd.AudioRecorder()
    monkeypatch.setattr(
        vd.sd,
        "InputStream",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("stream fail")),
    )

    try:
        rec.start(device_index=0)
        assert False, "expected RuntimeError"
    except RuntimeError:
        assert True


def test_audio_stop_handles_stream_close_error_and_no_frames(vd):
    rec = vd.AudioRecorder()

    class BadStream:
        def stop(self):
            raise RuntimeError("stop fail")

        def close(self):
            raise RuntimeError("close fail")

    rec.stream = BadStream()
    rec.frames = []
    assert rec.stop() is None


def test_notify_and_beep_error_paths(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    called = {"notify": None}
    monkeypatch.setattr(
        vd.subprocess, "run", lambda cmd: called.__setitem__("notify", cmd)
    )

    app.notify("Title", "Body")
    assert called["notify"][0] == "notify-send"

    vd.BEEP_ENABLED = True
    monkeypatch.setattr(
        vd.sd, "play", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("audio fail"))
    )
    app.play_beep()


def test_type_text_handles_subprocess_and_controller_exceptions(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    # Legacy X11 chain (Wayland/ydotool order is covered in test_wayland_output.py)
    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: False)
    monkeypatch.setattr(
        vd.subprocess,
        "run",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("xdotool missing")),
    )

    import pynput.keyboard as keyboard_mod

    class BadController:
        def type(self, text):
            raise RuntimeError("type fail")

    monkeypatch.setattr(keyboard_mod, "Controller", BadController)
    app.type_text("hello")
    assert app.last_transcription == "hello"


def test_toggle_recording_streaming_starts_worker_thread(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    vd.STREAMING_MODE = True
    vd.DEVICE_INDEX = 0

    starts = {"threads": 0}

    class CountThread:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            starts["threads"] += 1

    monkeypatch.setattr(vd.threading, "Thread", CountThread)
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    monkeypatch.setattr(app, "play_beep", lambda *a, **k: None)
    monkeypatch.setattr(app.recorder, "start", lambda device_index=None, **kw: None)

    app.toggle_recording()
    assert app.is_recording is True
    assert starts["threads"] == 1


def test_toggle_recording_stop_handles_exception(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    app.is_recording = True
    vd.STREAMING_MODE = False

    monkeypatch.setattr(vd.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    monkeypatch.setattr(app, "play_beep", lambda *a, **k: None)
    monkeypatch.setattr(
        app.recorder, "stop", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    app.toggle_recording()
    assert app.is_recording is False


def test_streaming_worker_processes_chunk_and_flushes_tail(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    app.is_recording = True
    app.recorder.rate = 16000

    processed = []
    monkeypatch.setattr(
        app, "_process_stream_chunk", lambda audio: processed.append(audio.shape[0])
    )

    chunks = [
        np.ones((16000, 1), dtype=np.float32) * 0.5,  # speaking
        np.zeros((16000, 1), dtype=np.float32),  # silence > duration => emits
        np.ones((8000, 1), dtype=np.float32) * 0.5,  # leftover flush on stop
    ]

    def fake_get(timeout=0.1):
        if chunks:
            return chunks.pop(0)
        app.is_recording = False
        raise queue.Empty

    monkeypatch.setattr(app.recorder.stream_queue, "get", fake_get)
    vd.SILENCE_THRESHOLD = 0.015
    vd.SILENCE_DURATION = 0.8

    app._streaming_worker()

    assert len(processed) >= 2


def test_process_stream_chunk_cleanup_exception_is_swallowed(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    monkeypatch.setattr(vd.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(vd.wav, "write", lambda path, rate, data: None)
    monkeypatch.setattr(app, "transcribe", lambda path: "ok")
    monkeypatch.setattr(app, "type_text", lambda text: None)
    monkeypatch.setattr(
        vd.os, "remove", lambda path: (_ for _ in ()).throw(RuntimeError("rm fail"))
    )

    app._process_stream_chunk(np.ones((9000, 1), dtype=np.float32))


def test_service_idempotent_branches(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    monkeypatch.setattr(vd.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    monkeypatch.setattr(app.recorder, "stop", lambda: None)

    app.start_service()
    app.start_service()  # early return branch when already running

    app.is_running = False
    app.stop_service()  # early return branch when already stopped


def test_backspace_uses_xdotool_first(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    # Legacy X11 chain (Wayland/ydotool order is covered in test_wayland_output.py)
    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: False)
    calls = []
    monkeypatch.setattr(
        vd.subprocess, "run",
        lambda *a, **k: calls.append(a[0]),
    )
    app._backspace(3)
    assert len(calls) == 1
    assert calls[0][:2] == ["xdotool", "key"]
    assert calls[0][2:] == ["BackSpace"] * 3


def test_backspace_fallback_to_pynput(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    # Legacy X11 chain (Wayland/ydotool order is covered in test_wayland_output.py)
    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: False)
    monkeypatch.setattr(
        vd.subprocess, "run",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no xdotool")),
    )
    backspaces = {"count": 0}

    import pynput.keyboard as kb_mod

    class FakeKey:
        backspace = "backspace"

    class FallbackController:
        def press(self, key):
            pass

        def release(self, key):
            backspaces["count"] += 1

    monkeypatch.setattr(kb_mod, "Key", FakeKey)
    monkeypatch.setattr(kb_mod, "Controller", FallbackController)

    app._backspace(5)
    assert backspaces["count"] == 5


def test_type_text_does_not_append_history(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    app.transcription_history.clear()
    # Legacy X11 chain (Wayland/ydotool order is covered in test_wayland_output.py)
    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: False)
    monkeypatch.setattr(vd.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))

    app.type_text("hello")
    assert len(app.transcription_history) == 0
    assert app.last_transcription == "hello"


def test_detect_wake_word(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    app.wake_word = "chanakya"

    detected, rest = app._detect_wake_word("Chanakya, turn on the lights")
    assert detected
    assert rest == "turn on the lights"

    detected, rest = app._detect_wake_word("chanakya turn on the lights")
    assert detected
    assert rest == "turn on the lights"

    detected, rest = app._detect_wake_word("CHANAKYA! do something")
    assert detected
    assert rest == "do something"

    detected, rest = app._detect_wake_word("turn on the lights")
    assert not detected

    detected, rest = app._detect_wake_word("Chanakya")
    assert detected
    assert rest == ""

    detected, rest = app._detect_wake_word("turn on chanakya lights")
    assert not detected


def test_process_and_output_wake_word_dispatches_command(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    app.wake_word = "chanakya"
    app.command_url = "https://ntfy.example.org/test"
    app.llm_action = "off"
    vd.STREAMING_MODE = False

    sent = {"text": None}
    monkeypatch.setattr(app, "send_command", lambda t: sent.__setitem__("text", t))
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    monkeypatch.setattr(app, "transcription_history", [])
    monkeypatch.setattr(app, "_save_history", lambda: None)

    app.process_and_output("Chanakya, turn on the lights")
    assert sent["text"] == "turn on the lights", f"got {sent['text']!r}"

    sent["text"] = None
    app.process_and_output("Chanakya")
    assert sent["text"] is None, "wake word alone should not send command"

    sent["text"] = None
    app.process_and_output("just regular dictation")
    assert sent["text"] is None, "regular text should not send command"


def test_process_and_output_wake_word_llm_processed(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    app.wake_word = "chanakya"
    app.command_url = "https://ntfy.example.org/test"
    app.llm_action = "grammar"
    vd.STREAMING_MODE = False

    sent = {"text": None}
    monkeypatch.setattr(vd, "llm_process", lambda text, action, inst, **kw: text.capitalize())
    monkeypatch.setattr(app, "send_command", lambda t: sent.__setitem__("text", t))
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    monkeypatch.setattr(app, "transcription_history", [])
    monkeypatch.setattr(app, "_save_history", lambda: None)

    app.process_and_output("Chanakya, turn on the lights")
    assert sent["text"] == "Turn on the lights", f"got {sent['text']!r}"


def test_push_to_hold_start_creates_timer(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    monkeypatch.setattr(app, "play_beep", lambda *a, **k: None)
    monkeypatch.setattr(app.recorder, "start", lambda *a, **kw: None)

    app._push_to_hold_start()
    assert app._pth_timer is not None
    assert app._pth_timer.is_alive() is True
    assert app._pth_timer.interval == 5.0


def test_push_to_hold_stop_cancels_timer(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    app.is_recording = True
    monkeypatch.setattr(app, "play_beep", lambda *a, **k: None)
    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    monkeypatch.setattr(app.recorder, "stop", lambda: None)

    app._pth_timer = vd.threading.Timer(10.0, lambda: None)
    app._pth_timer.daemon = True
    app._pth_timer.start()

    app._push_to_hold_stop()
    assert app._pth_timer is None


def test_stop_service_cancels_pth_timer(vd, monkeypatch):
    import threading as real_threading

    app = vd.VoiceDictationApp()
    app.is_running = True
    cancelled = {"timer": False}
    timer = real_threading.Timer(10.0, lambda: None)
    original_cancel = timer.cancel
    timer.cancel = lambda: (
        cancelled.__setitem__("timer", True) or original_cancel()
    )
    app._pth_timer = timer

    monkeypatch.setattr(app, "notify", lambda *a, **k: None)
    monkeypatch.setattr(app.recorder, "stop", lambda: None)
    monkeypatch.setattr(vd.threading, "Thread", ImmediateThread)

    app.start_service()
    app.stop_service()
    assert cancelled["timer"]
