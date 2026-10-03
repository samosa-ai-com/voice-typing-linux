from types import SimpleNamespace

import numpy as np


def test_update_config_updates_globals_and_persists(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    saved = {}

    monkeypatch.setattr(vd, "save_config", lambda payload: saved.update(payload))
    monkeypatch.setattr(app, "notify", lambda title, msg: None)

    app.update_config(
        stt_endpoint="http://new-endpoint",
        stt_model="new-model",
        streaming=False,
        hotkey="<ctrl>+<shift>+v",
        device_index="3",
        silence_threshold="0.09",
        beep_enabled=False,
    )

    assert vd.STT_ENDPOINT == "http://new-endpoint"
    assert vd.STT_MODEL == "new-model"
    assert vd.STREAMING_MODE is False
    assert vd.HOTKEY_STR == "<ctrl>+<shift>+v"
    assert vd.DEVICE_INDEX == 3
    assert vd.SILENCE_THRESHOLD == 0.09
    assert vd.BEEP_ENABLED is False
    assert saved["STT_ENDPOINT"] == "http://new-endpoint"
    assert saved["STT_MODEL"] == "new-model"


def test_update_config_hotkey_change_restarts_when_running(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    app.is_running = True
    calls = {"stop": 0, "start": 0}

    monkeypatch.setattr(vd, "save_config", lambda payload: None)
    monkeypatch.setattr(app, "notify", lambda title, msg: None)
    monkeypatch.setattr(
        app, "stop_service", lambda: calls.__setitem__("stop", calls["stop"] + 1)
    )
    monkeypatch.setattr(
        app, "start_service", lambda: calls.__setitem__("start", calls["start"] + 1)
    )

    app.update_config(hotkey="<ctrl>+j")

    assert calls == {"stop": 1, "start": 1}


def test_transcribe_success_sends_model_payload(vd, tmp_path, monkeypatch):
    app = vd.VoiceDictationApp()
    app.wake_word = "chanakya"
    app.initial_prompt = ""
    app.stt_language = "auto"
    app.stt_api_key = ""
    vd.STT_ENDPOINT = "http://localhost:1234/v1/audio/transcriptions"
    vd.STT_MODEL = "generic-model"
    vd.STT_LANGUAGE = "auto"
    vd.STT_API_KEY = ""

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fake-wav")
    captured = {}

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": " hello world "}

    def fake_post(url, files, data, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        captured["filename"] = files["file"][0]
        return Resp()

    monkeypatch.setattr(vd.requests, "post", fake_post)
    text = app.transcribe(str(audio))

    assert text == "hello world"
    assert captured["url"].startswith("http://localhost:1234")
    assert captured["data"] == {"model": "generic-model", "prompt": "chanakya"}
    assert captured["timeout"] == 300
    assert captured["filename"] == "clip.wav"


def test_transcribe_failure_returns_none(vd, tmp_path, monkeypatch):
    app = vd.VoiceDictationApp()
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fake")
    monkeypatch.setattr(
        vd.requests, "post", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    assert app.transcribe(str(audio)) is None


def test_transcribe_initial_prompt_included(vd, tmp_path, monkeypatch):
    app = vd.VoiceDictationApp()
    app.wake_word = "chanakya"
    app.initial_prompt = "Transcribe these terms: Kubernetes, gRPC"
    app.stt_language = "auto"
    app.stt_api_key = ""
    vd.STT_ENDPOINT = "http://localhost:1234/v1/audio/transcriptions"
    vd.STT_MODEL = "generic-model"
    vd.STT_LANGUAGE = "auto"
    vd.STT_API_KEY = ""

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fake-wav")
    captured = {}

    class Resp:
        def raise_for_status(self):
            return None
        def json(self):
            return {"text": "hello world"}

    def fake_post(url, files, data, timeout):
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(vd.requests, "post", fake_post)
    app.transcribe(str(audio))

    assert captured["data"]["prompt"] == "chanakya, Transcribe these terms: Kubernetes, gRPC"


def test_transcribe_initial_prompt_truncation(vd, tmp_path, monkeypatch):
    app = vd.VoiceDictationApp()
    app.wake_word = "chanakya"
    app.initial_prompt = "word, " * 500
    app.stt_language = "auto"
    app.stt_api_key = ""
    vd.STT_ENDPOINT = "http://localhost:1234/v1/audio/transcriptions"
    vd.STT_MODEL = "generic-model"
    vd.STT_LANGUAGE = "auto"
    vd.STT_API_KEY = ""

    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"fake-wav")
    captured = {}

    class Resp:
        def raise_for_status(self):
            return None
        def json(self):
            return {"text": "hello world"}

    def fake_post(url, files, data, timeout):
        captured["data"] = data
        return Resp()

    monkeypatch.setattr(vd.requests, "post", fake_post)
    app.transcribe(str(audio))

    assert len(captured["data"]["prompt"]) <= vd.MAX_PROMPT_CHARS
    assert captured["data"]["prompt"].startswith("...")


def test_type_text_falls_back_to_controller_when_xdotool_fails(vd, monkeypatch):
    app = vd.VoiceDictationApp()
    # Legacy X11 chain (Wayland/ydotool order is covered in test_wayland_output.py)
    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: False)

    # Make paste fail (xclip), xdotool type fail (non-zero), then pynput fallback
    call_log = []
    def fake_run(cmd, **kw):
        call_log.append(cmd[:3])
        if "xclip" in cmd:
            raise RuntimeError("xclip not available")
        if cmd[:2] == ["xdotool", "key"]:
            raise RuntimeError("paste fail")
        return SimpleNamespace(returncode=1, stderr=b"")
    monkeypatch.setattr(vd.subprocess, "run", fake_run)

    app.type_text("typed")

    from pynput.keyboard import Controller

    assert Controller.typed_text[-1] == "typed"
    assert any("xdotool" in c and "type" in c for c in call_log)


def test_audio_recorder_stop_writes_wav_and_returns_path(vd, monkeypatch):
    rec = vd.AudioRecorder()
    rec.frames = [np.ones((5, 1), dtype=np.float32), np.zeros((5, 1), dtype=np.float32)]
    captured = {}

    monkeypatch.setattr(
        vd.wav,
        "write",
        lambda path, rate, data: captured.update(
            {"path": path, "rate": rate, "shape": data.shape}
        ),
    )

    path = rec.stop()

    assert path == vd.AUDIO_FILE
    assert captured["path"] == vd.AUDIO_FILE
    assert captured["shape"] == (10, 1)
