# AGENTS.md — Voice Typing (Linux)

## Quick Start
```bash
cp .env.example .env
conda activate voiceTyping
python app.py          # served at http://127.0.0.1:3221
```

## Key Commands
- **Run**: `python app.py` (Flask + hotkey daemon + system tray subprocess)
- **Tests**: `PYTHONPATH=. pytest -q` (47 tests, all mocking hardware/network)
- **Lint**: `ruff check .`
- **Single test**: `PYTHONPATH=. pytest tests/test_voice_edge_cases.py::test_name -q`

## Architecture
- `app.py` (~1356 lines) — Flask server with embedded HTML template + all JS/CSS
- `voice_dictation.py` (~1161 lines) — `AudioRecorder` + `VoiceDictationApp` classes
- `llm_client.py` — OpenAI-compatible LLM post-processor (grammar/translate/custom)
- `tray.py` — System tray via `/usr/bin/python3` + `gi.repository.AyatanaAppIndicator3`
- `config.json` — Runtime settings (auto-created, gitignored)
- `.env` — Deployment secrets (API keys, STT endpoint, port) loaded before Flask starts
- `tests/` — Pytest, mocks sounddevice/scipy/pynput via `conftest.py`

## Critical Details

### Dependencies — two environments needed
- **App runtime** (conda `voiceTyping`): `flask flask-cors requests sounddevice scipy numpy pynput pyperclip Pillow`
- **System tray** (system `/usr/bin/python3`): requires `python3-gi`, `gir1.2-ayatanaappindicator3-0.1` via apt — conda's pygobject lacks GI introspection data

### Hotkey
- Uses `pynput.keyboard.GlobalHotKeys` for press detection, separate `keyboard.Listener` for push-to-hold release detection
- Format: `<cmd>+<shift>+s` (pynput syntax, not standard key names)
- On logout/login the X11 connection dies — use `POST /restart_hotkey` or the ⌨️ Reset button in the web UI
- `pkill -f` hangs; use `timeout 3 kill <PID>` instead

### Audio
- Records at 16000 Hz if device supports it, otherwise uses device's `default_samplerate`
- PulseAudio-only devices route through ALSA index 9 + `PULSE_SOURCE` env var
- Temp files: `/tmp/voice_typing.wav`, `/tmp/vds_*.wav`

### Config priority
1. `.env` loaded into `os.environ` at module level
2. `config.json` overlays runtime overrides
3. LLM credentials (`OPENAI_*`) come from `.env` only — excluded from `config.json`

### Typing
- X11 (e.g. Ubuntu 24.04): `xdotool type --clearmodifiers` → clipboard+paste → `pynput.keyboard.Controller().type()` → printed warning
- Wayland (e.g. Ubuntu 26.04 GNOME): `ydotool type` first (needs `ydotoold` user service + `input` group), then Ctrl+V paste via `ydotool key 29:1 47:1 47:0 29:0`, then the X11 chain as fallback. Backend chosen by `_prefer_ydotool()` (`XDG_SESSION_TYPE=wayland` + `ydotool` binary present)
- Backspace injection: same backend order (`ydotool key 14:1 14:0`, then xdotool, then pynput); `_on_hotkey`'s backspace-after-hotkey routes through `_backspace(1)`
- Clipboard fallback: `pyperclip` → `xclip -selection clipboard` (copy only; the paste keystroke follows the backend order above)

### Sample rate gotcha
- PulseAudio's "default" ALSA device (index 9) may not support 16000 Hz
- `check_input_settings` can lie about support — always use `default_samplerate` as first choice
- All three recording paths (`AudioRecorder.start`, `start_mic_test`, `test_stt_endpoint`) must respect this

### System tray
- `pystray` uses X11 System Tray protocol (incompatible with GNOME AppIndicator)
- Must use `gi.repository.AyatanaAppIndicator3` via system Python with explicit `DISPLAY` + `DBUS_SESSION_BUS_ADDRESS`
- GNOME requires `gnome-shell-extension-ubuntu-appindicators` enabled
- Full tray menu: mode (Toggle/Push-to-Hold), output (Type/Clipboard), LLM submenu (Off/Grammar/Translate/Custom), Reconnect Hotkey, Open Web UI, Quit
- Polls `/llm_config` every 2s to sync menu checkmarks via `GLib.idle_add`

### Push-to-hold safety net
- Release detection via pynput Listener is unreliable (XRecord interference with GlobalHotKeys)
- `_push_to_hold_start()` creates a `threading.Timer(5.0)` as fallback — auto-stops if release not detected
- Timer cancelled in `_push_to_hold_stop()` if release fires normally

### Voice commands (wake word)
- Wake word (default `"chanakya"`) detected as first word only in `_detect_wake_word()` — case-insensitive, punctuation-robust
- Wake word alone (no following text) does nothing; mid-sentence wake words left untouched
- Stripped command text POSTed as raw body to `COMMAND_URL` via `send_command()`
- Commands skip typing and are recorded in history with `↪` prefix and amber dot
- Streaming mode bypasses `process_and_output()` entirely — wake word only works in batch mode

### Initial Prompt (STT biasing)
- `INITIAL_PROMPT` entered as chips in the web UI, joined as comma-separated text
- Sent as `"prompt"` parameter to the STT API together with wake word
- Truncated to 800 chars from the front (preserving the end) with `"..."` prefix
- Config is runtime-only (stored in `config.json`, not `.env`)
- Natural sentence framing reduces false positives over bare word lists

### History
- `type_text()` does NOT append to `transcription_history` (prevents duplicates from `process_and_output`)
- Streaming history added in `_process_stream_chunk()`; batch history in `process_and_output()`

## Test quirks
- `conftest.py` mocks sounddevice, scipy, pynput at module level via `sys.modules` injection (autouse)
- `clear_voice_typing_env` fixture (autouse) deletes all `VOICE_TYPING_*` env vars
- `ImmediateThread` (defined per test file) replaces `threading.Thread` — runs target synchronously in `.start()`, must accept `**kwargs`
- Tests patch `vd.subprocess`, `vd.sd`, etc. (module-level references, not globals)
- `vd` fixture uses `importlib.reload` — runs `load_config()` BEFORE `CONFIG_FILE` is patched, so the real `config.json` leaks into the globals. Set `app.wake_word = "chanakya"` explicitly in tests that expect a specific wake word, and clear `app.transcription_history` if it relies on empty history.

## Key files (agent should read first)
| File | Purpose |
|------|---------|
| `app.py` | All routes + embedded HTML template + JS/CSS |
| `voice_dictation.py` | Core logic, state machine, audio pipeline, wake word, initial prompt |
| `conftest.py` | Mock setup — essential for understanding test behavior |
| `tray.py` | System tray (separate process via system Python) |
| `.env.example` | All configurable env vars documented |
