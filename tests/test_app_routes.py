import importlib


def test_status_route_returns_state(monkeypatch):
    import app as app_module

    module = importlib.reload(app_module)
    client = module.app.test_client()

    module.dict_app.is_running = True
    module.dict_app.is_recording = False
    module.dict_app.last_transcription = "hello"
    module.dict_app.status = "Idle"

    res = client.get("/status")
    data = res.get_json()

    assert res.status_code == 200
    assert data["is_running"] is True
    assert data["last_text"] == "hello"


def test_settings_route_calls_update_config(monkeypatch):
    import app as app_module

    module = importlib.reload(app_module)
    client = module.app.test_client()

    captured = {}

    def fake_update_config(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(module.dict_app, "update_config", fake_update_config)

    payload = {
        "stt_endpoint": "http://localhost:9000/v1/audio/transcriptions",
        "stt_model": "my-model",
        "streaming": True,
        "hotkey": "<ctrl>+<alt>+v",
        "device_index": "2",
        "silence_threshold": "0.05",
        "beep_enabled": False,
    }

    res = client.post("/settings", json=payload)
    assert res.status_code == 200
    assert captured["stt_endpoint"].startswith("http://localhost:9000")
    assert captured["stt_model"] == "my-model"
    assert captured["streaming"] is True


def test_index_route_renders_voice_typing_labels(monkeypatch):
    import app as app_module
    import voice_dictation

    module = importlib.reload(app_module)
    client = module.app.test_client()

    monkeypatch.setattr(
        voice_dictation, "STT_ENDPOINT", "http://localhost:8969/v1/audio/transcriptions"
    )
    monkeypatch.setattr(voice_dictation, "STT_MODEL", "demo-model")

    res = client.get("/")
    body = res.get_data(as_text=True)

    assert res.status_code == 200
    assert "Voice Typing." in body
    assert "STT Endpoint" in body
    assert "STT Model" in body


def test_toggle_service_route_switches_state(monkeypatch):
    import app as app_module

    module = importlib.reload(app_module)
    client = module.app.test_client()

    calls = {"start": 0, "stop": 0}
    module.dict_app.is_running = False
    monkeypatch.setattr(
        module.dict_app,
        "start_service",
        lambda: calls.__setitem__("start", calls["start"] + 1),
    )
    monkeypatch.setattr(
        module.dict_app,
        "stop_service",
        lambda: calls.__setitem__("stop", calls["stop"] + 1),
    )

    client.post("/toggle_service")
    assert calls["start"] == 1

    module.dict_app.is_running = True
    client.post("/toggle_service")
    assert calls["stop"] == 1


def test_toggle_recording_starts_service_when_needed(monkeypatch):
    import app as app_module

    module = importlib.reload(app_module)
    client = module.app.test_client()

    calls = {"start": 0, "toggle": 0}
    module.dict_app.is_running = False
    monkeypatch.setattr(
        module.dict_app,
        "start_service",
        lambda: calls.__setitem__("start", calls["start"] + 1),
    )
    monkeypatch.setattr(
        module.dict_app,
        "toggle_recording",
        lambda: calls.__setitem__("toggle", calls["toggle"] + 1),
    )

    res = client.post("/toggle_recording")
    assert res.status_code == 200
    assert calls == {"start": 1, "toggle": 1}


def test_devices_route_returns_list(monkeypatch):
    import app as app_module

    module = importlib.reload(app_module)
    client = module.app.test_client()

    monkeypatch.setattr(
        module.dict_app.recorder,
        "get_input_devices",
        lambda: [{"index": 1, "name": "Mic"}],
    )
    res = client.get("/devices")

    assert res.status_code == 200
    assert res.get_json() == [{"index": 1, "name": "Mic"}]


def test_copy_to_clipboard_route_copies_text(monkeypatch):
    import app as app_module

    module = importlib.reload(app_module)
    client = module.app.test_client()

    copied = []
    monkeypatch.setattr(module.dict_app, "copy_to_clipboard", copied.append)

    res = client.post("/copy_to_clipboard", json={"text": "hello tray"})
    assert res.status_code == 200
    assert res.get_json() == {"success": True}
    assert copied == ["hello tray"]


def test_copy_to_clipboard_route_rejects_missing_text(monkeypatch):
    import app as app_module

    module = importlib.reload(app_module)
    client = module.app.test_client()

    copied = []
    monkeypatch.setattr(module.dict_app, "copy_to_clipboard", copied.append)

    res = client.post("/copy_to_clipboard", json={"text": ""})
    assert res.status_code == 400
    assert copied == []

    res = client.post("/copy_to_clipboard", json={})
    assert res.status_code == 400
    assert copied == []


def test_history_route_returns_transcription_list(monkeypatch):
    import app as app_module

    module = importlib.reload(app_module)
    client = module.app.test_client()

    module.dict_app.transcription_history.clear()
    module.dict_app.transcription_history.extend([
        {"text": "first", "time": "10:00:00", "source": "batch"},
        {"text": "second", "time": "10:01:00", "source": "batch"},
    ])

    res = client.get("/history")
    assert res.status_code == 200
    assert res.get_json() == [
        {"text": "first", "time": "10:00:00", "source": "batch"},
        {"text": "second", "time": "10:01:00", "source": "batch"},
    ]
