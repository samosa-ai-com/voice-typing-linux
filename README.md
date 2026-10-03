# Voice Typing UI (Linux)

A lightweight Ubuntu/Linux voice typing application with a local web UI and global hotkey support. It records microphone audio, sends it to an OpenAI-compatible speech-to-text endpoint, and types the transcribed text into the currently focused window.

## Quick Start

```bash
# 1. Copy the example environment file
cp .env.example .env

# 2. Activate your Conda environment
conda activate voiceTyping

# 3. Run the application
python app.py
```

Then open `http://127.0.0.1:3221` in your browser to access the web UI.

## Features

- **Global Hotkey** — Press `Cmd+Shift+S` to start/stop recording from anywhere
- **Dual Modes** — Choose between streaming (real-time) or batch transcription
- **Auto-Typing** — Automatically types transcribed text into the active window
- **Web UI** — Control settings, view status, manage microphone selection, and test hardware
- **Voice Commands** — Configurable wake word (default: "chanakya") dispatches spoken commands to an external URL via HTTP POST
- **Mic Test** — Real-time 12-bar VU meter with dBFS readout to verify your microphone
- **STT Test** — Record a 2-second sample and send it to the endpoint to verify transcription works
- **Transcription History** — Scrollable log of all transcriptions with timestamps and source modes
- **Native Notifications** — Desktop notifications for recording status
- **Audio Feedback** — Optional beep sounds when starting/stopping (configurable)

## Prerequisites

- Ubuntu/Linux with a desktop environment
- Conda (Miniconda or Anaconda)
- A running STT server (e.g., faster-whisper on port 8969)
- Microphone access

## Configuration

Configure via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_TYPING_STT_ENDPOINT` | `http://127.0.0.1:8969/v1/audio/transcriptions` | Speech-to-text API endpoint |
| `VOICE_TYPING_STT_MODEL` | `Systran/faster-whisper-medium.en` | Model name |
| `VOICE_TYPING_DEVICE_INDEX` | (auto) | Microphone device index |
| `VOICE_TYPING_STREAMING` | `1` | Set `0` for batch mode |
| `VOICE_TYPING_SILENCE_THRESHOLD` | `0.015` | Audio level threshold for silence |
| `VOICE_TYPING_SILENCE_DURATION` | `0.8` | Seconds of silence to stop recording |
| `VOICE_TYPING_BEEP` | `1` | Set `0` to disable beep sounds |
| `VOICE_TYPING_HOTKEY` | `<cmd>+<shift>+s` | Global hotkey to toggle recording |
| `VOICE_TYPING_PULSE_SOURCE` | (none) | PulseAudio source name for PA-only devices |
| `VOICE_TYPING_UI_HOST` | `127.0.0.1` | Web UI bind address |
| `VOICE_TYPING_UI_PORT` | `3221` | Web UI port |

**Note:** The endpoint must be OpenAI-compatible for audio transcription and accept a `model` form field.

Runtime preferences (LLM action, wake word, command URL, push-to-hold mode, clipboard mode, device index) are saved to `config.json` — a per-user file excluded from version control. These can be changed at any time from the web UI and persist across restarts.

## Voice Commands

When the first word of transcribed speech matches the configured **wake word** (default: `"chanakya"`), the app strips the wake word and sends the remainder as a command to a configurable URL. This is useful for integrating with home automation, custom scripts, or any HTTP endpoint.

**How it works:**

1. Say `"Chanakya, turn on the lights"` into the microphone
2. Transcription detects the wake word `"Chanakya"` at the start
3. The wake word is stripped — the rest `"turn on the lights"` is extracted
4. If LLM post-processing is enabled, the command text is processed (e.g. grammar-fixed)
5. The final text is POSTed as raw body to the **Command URL** (e.g. `https://ntfy.example.org/Chanakya`)
6. Nothing is typed into the active window — it's a pure command dispatch

**Wake word rules:**
- Detection is case-insensitive and punctuation-robust: `"Chanakya,"`, `"chanakya!"`, `"CHANAKYA:"` all match
- Wake word alone with no following text (just `"Chanakya"`) does nothing
- Wake word appearing mid-sentence is left untouched — only the leading word triggers dispatch
- Wake word and Command URL are configurable at runtime from the web UI Settings panel

**Example flow with LLM off:**
```
You say:       "Chanakya, turn on the lights"
Transcribed:   "Chanakya, turn on the lights"
POSTed to URL: "turn on the lights"
History:       "↪ turn on the lights"  (amber dot)
```

**Example flow with LLM on (grammar):**
```
You say:       "Chanakya, turn on the lights"
Transcribed:   "Chanakya, turn on the lights"
LLM-processed: "Turn on the lights."
POSTed to URL: "Turn on the lights."
```

## Receiving Commands

Other applications can receive voice commands by exposing an HTTP endpoint at the configured **Command URL**.

### Protocol

| Field | Value |
|-------|-------|
| Method | `POST` |
| URL | Any URL set in **Command URL** field in the web UI |
| Body | Raw text — command only (wake word stripped) |
| Content-Type | `text/plain` |
| Headers | None added by the app |

### Example receivers

**Flask:**
```python
@app.route("/commands", methods=["POST"])
def handle_command():
    command = request.get_data(as_text=True)
    print(f"Received: {command}")
    return "OK", 200
```

**FastAPI:**
```python
from fastapi import FastAPI, Request
app = FastAPI()
@app.post("/commands")
async def handle(req: Request):
    command = (await req.body()).decode()
    print(f"Received: {command}")
```

**Express (Node.js):**
```javascript
const express = require("express");
const app = express();
// The app sends text/plain, so use express.text() (not express.json())
app.use(express.text({ type: "text/plain" }));

app.post("/commands", (req, res) => {
  console.log("Received:", req.body);
  res.send("OK");
});
```

**Bash (netcat):**
```bash
while true; do
  command=$(nc -l -p 8080 -q 1 | tail -1)
  echo "Received: $command"
done
```

### Testing

```bash
curl -X POST https://your-host/commands \
  -H "Content-Type: text/plain" \
  -d "turn on the lights"
```

### Notes

- Commands are dispatched asynchronously — the app does not wait for a response
- HTTP timeout is 5 seconds; errors are logged silently (non-blocking)
- If LLM post-processing is enabled, the command is grammar-fixed or translated before dispatch
- Works only in batch mode (streaming mode bypasses command dispatch)
- Common use cases: ntfy push notifications, Home Assistant webhooks, custom automation scripts, smart home voice control

## Running on Startup (Ubuntu)

### Option 1: Startup Applications (easiest)

1. Make the launcher executable:
   ```bash
   chmod +x run_app.sh
   ```

2. Open **Startup Applications** in Ubuntu and add a new entry:
   - **Name:** `Voice Typing UI`
   - **Command:** `/absolute/path/to/voice_typing/run_app.sh`
   - **Comment:** Starts the Voice Typing web UI and hotkey service

The `run_app.sh` script auto-detects conda and your active environment.

### Option 2: systemd user service (more robust)

Create `~/.config/systemd/user/voice-typing.service`:

```ini
[Unit]
Description=Voice Typing UI Service
After=network.target sound.target

[Service]
Type=simple
ExecStart=%h/path/to/voice_typing/run_app.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

Then enable and start it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now voice-typing.service
systemctl --user status voice-typing.service
```

This will start the app on boot, restart if it crashes, and you can check logs with `journalctl --user -u voice-typing.service`.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Endpoint unreachable | Verify your STT service is running and the URL is correct |
| Hotkey not working | On X11 choose a different hotkey if your desktop uses the same shortcut; on Wayland (Ubuntu 26.04+) pynput/XRecord can't see keys, so bind the combo in Settings → Keyboard → Custom Shortcuts to `curl -s -X POST http://127.0.0.1:3221/toggle_recording` |
| Wayland typing issues | Install `ydotool` (`sudo apt install ydotool`) and `wl-clipboard` (`sudo apt install wl-clipboard`) for typing/paste, and enable the daemon (`systemctl --user enable --now ydotool.service`) — the app prefers ydotool automatically on Wayland sessions, keeping xdotool/pynput as fallback on X11. ydotool also needs your user in the `input` group (`sudo usermod -aG input $USER`, then log out/in); without it typing fails with a permissions error |
| Microphone not detected | Check input device selection in the web UI |
| USB/PulseAudio device not in list | It will appear with a `pulse_source` field and route through the "default" ALSA device |