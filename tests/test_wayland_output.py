"""Wayland output backend: ydotool preferred, X11 chain kept as fallback.

On Wayland sessions (e.g. Ubuntu 26.04 GNOME) xdotool/pynput inject into
XWayland where nobody listens, so typing/paste silently does nothing.
ydotool injects at evdev level and works on both — but only when the
`ydotoold` daemon is up. These tests pin `_prefer_ydotool` so they are
deterministic regardless of the machine running them.
"""
import sys
import types
from types import SimpleNamespace


def _ok_run(calls):
    def fake(*a, **k):
        calls.append(a[0])
        return SimpleNamespace(returncode=0, stderr=b"")

    return fake


def _make_app(vd):
    app = vd.VoiceDictationApp()
    app.transcription_history.clear()
    return app


def test_prefer_ydotool_only_on_wayland_with_binary(vd, monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(vd.shutil, "which",
                        lambda name: "/usr/bin/ydotool" if name == "ydotool" else None)
    assert vd._prefer_ydotool() is True

    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert vd._prefer_ydotool() is False

    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(vd.shutil, "which", lambda name: None)
    assert vd._prefer_ydotool() is False

    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setattr(vd.shutil, "which", lambda name: "/usr/bin/ydotool")
    assert vd._prefer_ydotool() is False


def test_ydotool_type_used_first_on_wayland(vd, monkeypatch):
    from pynput.keyboard import Controller

    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: True)
    calls = []
    monkeypatch.setattr(vd.subprocess, "run", _ok_run(calls))

    _make_app(vd).type_text("hello wayland")

    assert calls[0][:2] == ["ydotool", "type"]
    assert calls[0][1:6] == ["type", "-d", "2", "-H", "2"]
    assert calls[0][-2:] == ["--", "hello wayland"]
    assert all(c[0] != "xdotool" for c in calls)
    assert "hello wayland" not in Controller.typed_text


def test_ydotool_failure_falls_through_to_xdotool_and_pynput(vd, monkeypatch):
    from pynput.keyboard import Controller

    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: True)

    def fake_run(cmd, **kw):
        if cmd[0] == "ydotool":
            return SimpleNamespace(returncode=1, stderr=b"no daemon")
        if "xclip" in cmd:
            raise RuntimeError("no xclip")
        if cmd[:2] == ["xdotool", "key"]:
            raise RuntimeError("no X11")
        return SimpleNamespace(returncode=1, stderr=b"")

    monkeypatch.setattr(vd.subprocess, "run", fake_run)

    _make_app(vd).type_text("fallback me")
    assert Controller.typed_text[-1] == "fallback me"


def test_paste_uses_ydotool_ctrl_v_on_wayland(vd, monkeypatch):
    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: True)
    fake_clip = types.ModuleType("pyperclip")
    copied = []
    fake_clip.copy = copied.append
    monkeypatch.setitem(sys.modules, "pyperclip", fake_clip)
    calls = []
    monkeypatch.setattr(vd.subprocess, "run", _ok_run(calls))

    assert _make_app(vd)._paste_via_clipboard("paste me") is True
    assert copied == ["paste me"]
    assert calls == [["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]]


def test_backspace_uses_ydotool_on_wayland(vd, monkeypatch):
    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: True)
    calls = []
    monkeypatch.setattr(vd.subprocess, "run", _ok_run(calls))

    _make_app(vd)._backspace(2)
    assert calls == [["ydotool", "key", "14:1", "14:0", "14:1", "14:0"]]


def test_backspace_falls_back_when_ydotool_down(vd, monkeypatch):
    monkeypatch.setattr(vd, "_prefer_ydotool", lambda: True)

    def fake_run(cmd, **kw):
        if cmd[0] == "ydotool":
            raise RuntimeError("daemon down")
        return SimpleNamespace(returncode=0, stderr=b"")

    calls = []
    orig_fake = fake_run

    def recording_run(*a, **k):
        calls.append(a[0])
        return orig_fake(a[0], **k)

    monkeypatch.setattr(vd.subprocess, "run", recording_run)

    _make_app(vd)._backspace(1)
    assert calls[0][0] == "ydotool"
    assert calls[1][:2] == ["xdotool", "key"]
