import os
import threading
import time
import json
import re
import shutil
import requests
import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np
from pynput import keyboard
import subprocess
import queue

from llm_client import llm_process
from correction_engine import (
    load_corrections,
    save_corrections,
    apply_corrections,
    suggest_corrections,
    validate_correction,
    new_correction,
    extract_context,
)

# Load .env file manually (before Flask does it, since module-level code runs first)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip().strip("'\"")
                if not os.environ.get(_k):  # Don't override existing env vars
                    os.environ[_k] = _v


CHANNELS = 1
RATE = 16000
AUDIO_FILE = "/tmp/voice_typing.wav"
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".voice_typing_history.json")


STT_LANGUAGES = {
    "auto": "Auto (detect)",
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "it": "Italian",
    "ar": "Arabic",
    "ru": "Russian",
    "nl": "Dutch",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ur": "Urdu",
    "fa": "Persian",
    "he": "Hebrew",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "uk": "Ukrainian",
    "el": "Greek",
    "cs": "Czech",
    "ro": "Romanian",
    "sv": "Swedish",
    "fi": "Finnish",
    "da": "Danish",
    "no": "Norwegian",
    "hu": "Hungarian",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "et": "Estonian",
    "sr": "Serbian",
    "ka": "Georgian",
    "hy": "Armenian",
    "az": "Azerbaijani",
    "af": "Afrikaans",
    "sw": "Swahili",
}


def load_config():
    defaults = {
        "STT_ENDPOINT": os.getenv(
            "VOICE_TYPING_STT_ENDPOINT", "http://127.0.0.1:8969/v1/audio/transcriptions"
        ),
        "STT_MODEL": os.getenv(
            "VOICE_TYPING_STT_MODEL", "Systran/faster-whisper-medium.en"
        ),
        "STT_LANGUAGE": os.getenv("VOICE_TYPING_STT_LANGUAGE", "auto"),
        "STT_API_KEY": os.getenv("VOICE_TYPING_STT_API_KEY", os.getenv("STT_API_KEY", "")),
        "DEVICE_INDEX": os.getenv("VOICE_TYPING_DEVICE_INDEX", None),
        "STREAMING_MODE": os.getenv("VOICE_TYPING_STREAMING", "0") == "1",
        "SILENCE_THRESHOLD": float(
            os.getenv("VOICE_TYPING_SILENCE_THRESHOLD", "0.015")
        ),
        "SILENCE_DURATION": float(os.getenv("VOICE_TYPING_SILENCE_DURATION", "0.8")),
        "BEEP_ENABLED": os.getenv("VOICE_TYPING_BEEP", "1") == "1",
        "HOTKEY_STR": os.getenv("VOICE_TYPING_HOTKEY", "<cmd>+<shift>+s"),
        "PULSE_SOURCE_NAME": os.getenv("VOICE_TYPING_PULSE_SOURCE", None),
        "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", ""),
        "OPENAI_CHAT_MODEL_ID": os.getenv("OPENAI_CHAT_MODEL_ID", ""),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "LLM_ACTION": "off",
        "LLM_INSTRUCTION": "",
        "PUSH_TO_HOLD": False,
        "CLIPBOARD_MODE": True,
        "WAKE_WORD": "chanakya",
        "COMMAND_URL": "",
        "INITIAL_PROMPT": "",
        "BEEP_VOLUME": 0.5,
        "BACKSPACE_AFTER_HOTKEY": True,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
            defaults.update(loaded)
        except Exception as e:
            print(f"Error loading config: {e}")
    # Normalize STT_LANGUAGE: empty or missing -> auto
    if not defaults.get("STT_LANGUAGE"):
        defaults["STT_LANGUAGE"] = "auto"
    return defaults


def save_config(config_dict):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_dict, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")


def _get_pulse_device_index():
    """Dynamically resolve the PulseAudio ALSA device (pulse/default) instead of hardcoding 9."""
    try:
        import sounddevice as _sd
        devices = _sd.query_devices()
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and "pulse" in d["name"].lower():
                return i
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0 and "default" in d["name"].lower():
                return i
        if _sd.default.device and _sd.default.device[0] is not None and _sd.default.device[0] >= 0:
            return int(_sd.default.device[0])
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                return i
    except Exception:
        pass
    return 0


# Initialize globals from config
CONFIG = load_config()
STT_ENDPOINT = CONFIG["STT_ENDPOINT"]
STT_MODEL = CONFIG["STT_MODEL"]
STT_LANGUAGE = CONFIG["STT_LANGUAGE"]
STT_API_KEY = CONFIG["STT_API_KEY"]
DEVICE_INDEX = CONFIG["DEVICE_INDEX"]
STREAMING_MODE = CONFIG["STREAMING_MODE"]
SILENCE_THRESHOLD = CONFIG["SILENCE_THRESHOLD"]
SILENCE_DURATION = CONFIG["SILENCE_DURATION"]
BEEP_ENABLED = CONFIG["BEEP_ENABLED"]
HOTKEY_STR = CONFIG["HOTKEY_STR"]
PULSE_SOURCE_NAME = CONFIG["PULSE_SOURCE_NAME"]
OPENAI_BASE_URL = CONFIG["OPENAI_BASE_URL"]
OPENAI_CHAT_MODEL_ID = CONFIG["OPENAI_CHAT_MODEL_ID"]
OPENAI_API_KEY = CONFIG["OPENAI_API_KEY"]
PUSH_TO_HOLD = CONFIG["PUSH_TO_HOLD"]
CLIPBOARD_MODE = CONFIG["CLIPBOARD_MODE"]
LLM_ACTION = CONFIG["LLM_ACTION"]
LLM_INSTRUCTION = CONFIG["LLM_INSTRUCTION"]
WAKE_WORD = CONFIG["WAKE_WORD"]
COMMAND_URL = CONFIG["COMMAND_URL"]
INITIAL_PROMPT = CONFIG["INITIAL_PROMPT"]
BEEP_VOLUME = CONFIG.get("BEEP_VOLUME", 0.5)
BACKSPACE_AFTER_HOTKEY = CONFIG.get("BACKSPACE_AFTER_HOTKEY", True)
MAX_PROMPT_CHARS = 800

# Auto-migrate stale hardcoded DEVICE_INDEX 9 (and other invalid indices) to real pulse/default device
try:
    if DEVICE_INDEX is not None:
        _test_idx = int(DEVICE_INDEX)
        import sounddevice as _sd_check
        _sd_check.query_devices(_test_idx, "input")
except Exception:
    try:
        _pulse_idx = _get_pulse_device_index() if '_get_pulse_device_index' in globals() else None
        # _get_pulse_device_index may not be defined yet on first load; handle via direct query
        if _pulse_idx is None:
            import sounddevice as _sd2
            _pulse_idx = _sd2.default.device[0]
        old = DEVICE_INDEX
        DEVICE_INDEX = _pulse_idx
        CONFIG["DEVICE_INDEX"] = _pulse_idx
        print(f"[MIGRATE] DEVICE_INDEX {old} invalid -> {DEVICE_INDEX} (pulse/default)", flush=True)
        try:
            # Update only DEVICE_INDEX in the existing config file, preserving all
            # other keys and never persisting secrets (STT_API_KEY / OPENAI_* live in .env).
            _migrated_cfg = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as _f:
                    try:
                        _loaded_cfg = json.load(_f)
                        if isinstance(_loaded_cfg, dict):
                            _migrated_cfg = _loaded_cfg
                    except Exception:
                        _migrated_cfg = {}
            _migrated_cfg["DEVICE_INDEX"] = DEVICE_INDEX
            with open(CONFIG_FILE, "w") as _f:
                json.dump(_migrated_cfg, _f, indent=4)
        except Exception as _e:
            print(f"[MIGRATE] save failed: {_e}", flush=True)
    except Exception as _e:
        print(f"[MIGRATE] failed: {_e}", flush=True)

def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("\"'")
                if key not in os.environ:
                    os.environ[key] = val

_load_dotenv()

_config_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Text-output backend selection (X11 vs Wayland)
#
# xdotool and pynput inject via the X server (XTEST/XRecord). On Wayland
# sessions (e.g. Ubuntu 26.04 GNOME) those events are accepted by XWayland
# but delivered to nobody, so typing/paste silently does nothing. ydotool
# injects at the evdev/uinput level instead and works on both, but needs
# the `ydotoold` daemon running (packaged as a user systemd unit).
# ---------------------------------------------------------------------------
# evdev key codes (linux/input-event-codes.h) — stable across layouts.
_YD_KEY_BACKSPACE = 14
_YD_KEY_LEFTCTRL = 29
_YD_KEY_V = 47
# ydotool type defaults (20ms hold + 20ms delay ≈ 25 chars/s) feel like a
# typewriter; evdev events are queued reliably, so small gaps are plenty.
_YD_TYPE_KEY_DELAY_MS = 2
_YD_TYPE_KEY_HOLD_MS = 2


def _session_type():
    return os.environ.get("XDG_SESSION_TYPE", "").lower()


def _has_ydotool():
    return shutil.which("ydotool") is not None


def _prefer_ydotool():
    """True when X11 injectors are known-blind: a Wayland session with
    ydotool installed. Everywhere else (X11 like Ubuntu 24.04, or missing
    ydotool) the legacy xdotool-first order is kept."""
    on_wayland = _session_type() == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))
    return on_wayland and _has_ydotool()


def _copy_to_system_clipboard(text):
    """Copy text to the system clipboard. Returns True on success.

    Tries pyperclip, then wl-copy (Wayland, from wl-clipboard), then xclip
    (X11). Returncodes are checked so a silent copy failure never masquerades
    as success to the paste path.
    """
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception as e:
        print(f"[CLIP] pyperclip failed: {e}", flush=True)
    if shutil.which("wl-copy") is not None:
        try:
            result = subprocess.run(
                ["wl-copy"], input=text, text=True, timeout=3,
                capture_output=True,
            )
            if result.returncode == 0:
                return True
            print(f"[CLIP] wl-copy failed (code {result.returncode})", flush=True)
        except Exception as e:
            print(f"[CLIP] wl-copy error: {e}", flush=True)
    try:
        result = subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text, text=True, timeout=3,
            capture_output=True,
        )
        if result.returncode == 0:
            return True
        print(f"[CLIP] xclip failed (code {result.returncode})", flush=True)
    except Exception as e:
        print(f"[CLIP] xclip error: {e}", flush=True)
    return False


class AudioRecorder:
    def __init__(self):
        self.frames = []
        self.recording = False
        self.rate = RATE
        self.device_index = None
        self.pulse_source_name = PULSE_SOURCE_NAME
        self.stream_queue = queue.Queue()
        self.stream = None

        try:
            if DEVICE_INDEX is not None:
                try:
                    self.device_index = int(DEVICE_INDEX)
                except (ValueError, TypeError):
                    self.device_index = DEVICE_INDEX
            else:
                self.device_index = sd.default.device[0]

            # Validate device — handle stale hardcoded 9 or other invalid indices
            try:
                device_info = sd.query_devices(self.device_index, "input")
            except Exception:
                # If DEVICE_INDEX was a PulseAudio placeholder or invalid, resolve to real pulse/default device
                if PULSE_SOURCE_NAME:
                    self.device_index = _get_pulse_device_index()
                    self.pulse_source_name = PULSE_SOURCE_NAME
                else:
                    self.device_index = _get_pulse_device_index()
                device_info = sd.query_devices(self.device_index, "input")
            self.rate = int(device_info["default_samplerate"])

            try:
                sd.check_input_settings(
                    device=self.device_index, channels=CHANNELS, samplerate=RATE
                )
                self.rate = RATE
            except Exception:
                pass

            print(f"Using sample rate: {self.rate} on device {self.device_index}")
        except Exception as e:
            print(f"Error selecting device/rate: {e}")
            self.rate = 44100
            # Ensure we have a usable fallback device
            try:
                self.device_index = _get_pulse_device_index()
            except Exception:
                pass

    def get_input_devices(self):
        devices = []
        try:
            sd_devices = sd.query_devices()
            alsa_card_to_sd = {}
            for i, d in enumerate(sd_devices):
                if d["max_input_channels"] > 0:
                    m = re.search(r"\(hw:(\d+),", str(d["name"]))
                    if m:
                        alsa_card_to_sd[int(m.group(1))] = i

            pactl_out = subprocess.run(
                ["pactl", "list", "sources"], capture_output=True, text=True, timeout=3
            ).stdout

            sources = []
            cur = {}
            in_props = False
            for line in pactl_out.split("\n"):
                stripped = line.strip()
                if stripped.startswith("Name:") and not in_props:
                    if cur:
                        sources.append(cur)
                    cur = {"name": stripped.split(":", 1)[1].strip(), "alsa_card": None}
                elif stripped.startswith("Description:") and not in_props:
                    cur["desc"] = stripped.split(":", 1)[1].strip()
                elif stripped == "Properties:":
                    in_props = True
                elif in_props and stripped.startswith("alsa.card ="):
                    cur["alsa_card"] = stripped.split("=", 1)[1].strip().strip('"')
                elif in_props and stripped == "":
                    in_props = False
                elif stripped == "" and cur:
                    sources.append(cur)
                    cur = {}
                    in_props = False
            if cur:
                sources.append(cur)

            seen = set()
            for s in sources:
                src_name = s.get("name", "")
                desc = s.get("desc", "")
                alsa_card = s.get("alsa_card")

                if ".monitor" in src_name or (desc and desc.startswith("Monitor of")):
                    continue
                if desc in seen:
                    continue
                if desc:
                    seen.add(desc)

                sd_idx = None
                if alsa_card and alsa_card.isdigit():
                    sd_idx = alsa_card_to_sd.get(int(alsa_card))

                label = desc or src_name
                # Attach PulseAudio source name so frontend can send it back;
                # route through real PulseAudio device (pulse/default) for shared mic access.
                pulse_idx = _get_pulse_device_index()
                devices.append({
                    "index": sd_idx if sd_idx is not None else pulse_idx,
                    "name": f"(audio) {label}",
                    "pulse_source": src_name,
                })

            devices.sort(key=lambda d: d["index"] if d.get("pulse_source") else d["index"])
        except Exception as e:
            print(f"PulseAudio device listing failed, falling back: {e}")
            try:
                device_list = sd.query_devices()
                for i, d in enumerate(device_list):
                    if d["max_input_channels"] > 0:
                        api_name = sd.query_hostapis(d["hostapi"])["name"]
                        name = f"{d['name']} ({api_name})"
                        devices.append({"index": i, "name": name})
            except Exception as e2:
                print(f"Error listing devices: {e2}")
        return devices

    def start(self, device_index=None, pulse_source=None):
        self.frames = []
        self.recording = True

        try:
            raw_target = device_index if device_index is not None else self.device_index
            target_device = int(raw_target)
        except (ValueError, TypeError):
            target_device = raw_target

        pulse_src = pulse_source or self.pulse_source_name
        old_pulse = os.environ.get("PULSE_SOURCE")
        if pulse_src:
            os.environ["PULSE_SOURCE"] = pulse_src
            # Route through real PulseAudio device (pulse/default) so
            # PulseAudio can multiplex the source across multiple apps (calls, Zoom, etc.).
            target_device = _get_pulse_device_index()

        while not self.stream_queue.empty():
            try:
                self.stream_queue.get_nowait()
            except queue.Empty:
                break

        def callback(indata, frames, time_val, status):
            if status:
                print(f"Status check: {status}", flush=True)
            cp = indata.copy()
            self.frames.append(cp)
            if STREAMING_MODE:
                self.stream_queue.put(cp)

        def _cycle_pulse_source():
            if pulse_src:
                src = pulse_src
            elif self.pulse_source_name:
                src = self.pulse_source_name
            else:
                src = "@DEFAULT_SOURCE@"
            try:
                subprocess.run(
                    ["pactl", "suspend-source", src, "true"],
                    capture_output=True, timeout=3,
                )
                time.sleep(0.2)
                subprocess.run(
                    ["pactl", "suspend-source", src, "false"],
                    capture_output=True, timeout=3,
                )
                time.sleep(0.3)
                print(f"[REC] Cycled PulseAudio source {src}", flush=True)
            except Exception as cycle_err:
                print(f"[REC] PulseAudio source cycle failed: {cycle_err}", flush=True)

        try:
            for attempt in range(2):
                if pulse_src:
                    os.environ["PULSE_SOURCE"] = pulse_src
                try:
                    # Re-check rate if device changed
                    device_info = sd.query_devices(target_device, "input")
                    default_rate = int(device_info["default_samplerate"])
                    rate_to_use = default_rate
                    try:
                        sd.check_input_settings(device=target_device, channels=CHANNELS, samplerate=RATE)
                        rate_to_use = RATE
                    except Exception:
                        pass

                    # Sync self.rate with actual stream rate so stop() writes the WAV
                    # header at the correct sample rate (was a source of garbled audio).
                    self.rate = rate_to_use

                    self.stream = sd.InputStream(
                        samplerate=rate_to_use,
                        device=target_device,
                        channels=CHANNELS,
                        callback=callback,
                    )
                    self.stream.start()
                    print(
                        f"[REC] Audio stream started on device {target_device} at {rate_to_use}Hz.",
                        flush=True,
                    )
                    break
                except Exception as e:
                    err_str = str(e)
                    # PulseAudio can leave a source in a suspended state after a stream
                    # crashes (e.g. a call ended abruptly). Cycling suspend-source forces
                    # PulseAudio to re-probe the ALSA device and clears the error.
                    if attempt == 0 and ("-9985" in err_str or "PaErrorCode" in err_str or "Device unavailable" in err_str or "Input/output error" in err_str):
                        print(f"[REC] Device unavailable (attempt {attempt+1}), cycling PulseAudio source...", flush=True)
                        _cycle_pulse_source()
                        continue
                    raise e
        finally:
            if pulse_src:
                if old_pulse is not None:
                    os.environ["PULSE_SOURCE"] = old_pulse
                else:
                    os.environ.pop("PULSE_SOURCE", None)

    def stop(self):
        self.recording = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
                self.stream = None
                print("[PROC] Stream closed successfully.", flush=True)
            except Exception as e:
                print(f"Stream close error: {e}", flush=True)

        if not self.frames:
            return None

        audio_data = np.concatenate(self.frames, axis=0)
        wav.write(AUDIO_FILE, self.rate, audio_data)
        return AUDIO_FILE


class VoiceDictationApp:
    def __init__(self):
        self.recorder = AudioRecorder()
        self._lock = threading.Lock()
        self.is_recording = False
        self.is_running = False
        self.last_transcription = ""
        self.status = "Idle"
        self.hotkey_listener = None
        self._release_listener = None
        self._streaming_worker_active = False
        self._transcribe_semaphore = threading.BoundedSemaphore(3)
        self._mic_test_active = False
        self._mic_test_level = 0.0
        self._mic_test_stream = None
        self._mic_test_seq = 0
        self.transcription_history = []
        self._load_history()
        self.corrections = load_corrections()
        self.llm_action = LLM_ACTION
        self.llm_instruction = LLM_INSTRUCTION
        self.push_to_hold = PUSH_TO_HOLD
        self.wake_word = WAKE_WORD
        self.command_url = COMMAND_URL
        self.initial_prompt = INITIAL_PROMPT
        self.clipboard_mode = CLIPBOARD_MODE
        self.stt_language = STT_LANGUAGE
        self.stt_api_key = STT_API_KEY
        self.openai_base_url = OPENAI_BASE_URL
        self.openai_chat_model_id = OPENAI_CHAT_MODEL_ID
        self.openai_api_key = OPENAI_API_KEY
        self._hotkey_pressed = False
        self._pth_timer = None
        self._typing_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._last_hotkey_time = 0.0
        self._correction_log = []
        self.beep_volume = BEEP_VOLUME
        self.backspace_after_hotkey = BACKSPACE_AFTER_HOTKEY

    def _load_history(self):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.transcription_history = data[-50:]
        except Exception as e:
            print(f"Error loading history: {e}", flush=True)
            self.transcription_history = []

    def _save_history(self):
        try:
            data = self.transcription_history[-50:]
            with open(HISTORY_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}", flush=True)

    def _save_corrections(self):
        save_corrections(self.corrections)

    def get_corrections(self):
        return self.corrections

    def add_correction(self, pattern, replacement, source="manual", context_left="", context_right=""):
        errors = validate_correction(pattern, replacement)
        if errors:
            return {"success": False, "errors": errors}
        corr = new_correction(pattern, replacement, source, context_left, context_right)
        self.corrections.append(corr)
        if len(self.corrections) > 200:
            self.corrections = self.corrections[-200:]
        self._save_corrections()
        return {"success": True, "correction": corr}

    def remove_correction(self, corr_id):
        before = len(self.corrections)
        self.corrections = [c for c in self.corrections if c.get("id") != corr_id]
        if len(self.corrections) < before:
            self._save_corrections()
            return {"success": True}
        return {"success": False, "error": "Correction not found"}

    def update_correction(self, corr_id, updates):
        for c in self.corrections:
            if c.get("id") == corr_id:
                allowed = {"pattern", "replacement", "enabled", "case_sensitive", "context_left", "context_right"}
                for k, v in updates.items():
                    if k in allowed:
                        c[k] = v
                self._save_corrections()
                return {"success": True, "correction": c}
        return {"success": False, "error": "Correction not found"}

    def correct_history_entry(self, index, new_text):
        with self._history_lock:
            if index < 0 or index >= len(self.transcription_history):
                return {"success": False, "error": "History entry not found"}
            entry = self.transcription_history[index]
            old_text = entry["text"]
            if old_text == new_text:
                return {"success": True, "changed": False, "suggestions": []}
            entry["text"] = new_text
        self._save_history()
        suggestions = suggest_corrections(old_text, new_text)
        for s in suggestions:
            left, right = extract_context(old_text, s["pattern"])
            s["context_left"] = left
            s["context_right"] = right
        return {"success": True, "changed": True, "suggestions": suggestions}

    def _log_correction_applied(self, pattern, replacement, corr_id=""):
        entry = {
            "corr_id": corr_id,
            "pattern": pattern,
            "replacement": replacement,
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.time(),
        }
        self._correction_log.append(entry)
        if len(self._correction_log) > 50:
            self._correction_log.pop(0)
        self.status = f"Corrected: {pattern} \u2192 {replacement}"

    def get_correction_log(self):
        return list(self._correction_log)

    def flag_incorrect(self, corr_id, action="disable", context_left="", context_right=""):
        for c in self.corrections:
            if c.get("id") == corr_id:
                if action == "disable":
                    c["enabled"] = False
                    self._log_correction_applied("FLAGGED: " + c["pattern"], "disabled", c.get("id", ""))
                    self._save_corrections()
                    return {"success": True, "action": "disabled"}
                elif action == "add_exception":
                    exc = {"left": context_left, "right": context_right}
                    if "exceptions" not in c:
                        c["exceptions"] = []
                    c["exceptions"].append(exc)
                    self._save_corrections()
                    return {"success": True, "action": "exception_added"}
                return {"success": False, "error": "Unknown action"}
        return {"success": False, "error": "Correction not found"}

    def notify(self, title, message):
        print(f"[{title}] {message}", flush=True)
        self.status = f"{title}: {message}"
        try:
            subprocess.run(["notify-send", "-a", "Voice Typing", title, message])
        except Exception:
            pass

    def play_beep(self, frequency=800, duration=0.1):
        if not BEEP_ENABLED:
            return
        try:
            sample_rate = 44100
            t = np.linspace(0, duration, int(sample_rate * duration), False)
            tone = np.sin(frequency * t * 2 * np.pi)
            vol = max(0.0, min(1.0, getattr(self, "beep_volume", BEEP_VOLUME)))
            sd.play(tone * vol, samplerate=sample_rate)
        except Exception as e:
            print(f"Beep error: {e}")

    def transcribe(self, file_path):
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f, "audio/wav")}
                data = {"model": STT_MODEL}
                # STT language: "auto" or empty = auto-detect (omit field)
                lang = getattr(self, "stt_language", None) or STT_LANGUAGE
                if lang and lang != "auto":
                    data["language"] = lang
                parts = []
                if self.wake_word:
                    parts.append(self.wake_word)
                if self.initial_prompt:
                    parts.append(self.initial_prompt.strip())
                corr_words = []
                seen = set()
                for c in self.corrections:
                    if c.get("enabled", True):
                        r = c.get("replacement", "").strip().lower()
                        if r and r not in seen and len(r) >= 3:
                            seen.add(r)
                            corr_words.append(r)
                if corr_words:
                    parts.append(", ".join(corr_words[:20]))
                if parts:
                    prompt = ", ".join(parts)
                    if len(prompt) > MAX_PROMPT_CHARS:
                        prompt = "..." + prompt[-(MAX_PROMPT_CHARS - 3):]
                        print(f"[PROMPT] Truncated to {MAX_PROMPT_CHARS} chars", flush=True)
                    data["prompt"] = prompt
                # STT API key — OpenAI-compatible Bearer token (only sent when configured)
                _api_key = (getattr(self, "stt_api_key", None) or STT_API_KEY or "").strip()
                if _api_key:
                    response = requests.post(
                        STT_ENDPOINT, files=files, data=data,
                        headers={"Authorization": f"Bearer {_api_key}"}, timeout=300
                    )
                else:
                    response = requests.post(
                        STT_ENDPOINT, files=files, data=data, timeout=300
                    )
                response.raise_for_status()
                return response.json().get("text", "").strip()
        except Exception as e:
            print(f"Transcription error: {e}")
            return None

    def _process_voice_commands(self, text):
        commands = {
            "delete last word": "__DELETE_LAST_WORD__",
            "delete last sentence": "__DELETE_LAST_SENTENCE__",
        }
        lower = text.lower().strip()
        if lower in commands:
            return commands[lower]
        return text

    def copy_to_clipboard(self, text):
        if _copy_to_system_clipboard(text):
            print(f"[CLIP] Copied to clipboard: '{text}'", flush=True)
        else:
            print("[CLIP] All clipboard copy methods failed", flush=True)

    def _backspace(self, count):
        if _prefer_ydotool():
            if self._ydotool_key([(_YD_KEY_BACKSPACE, 1), (_YD_KEY_BACKSPACE, 0)] * count):
                return
            print("[TYPE] ydotool backspace failed, falling back", flush=True)
        try:
            result = subprocess.run(
                ["xdotool", "key"] + ["BackSpace"] * count,
                capture_output=True, timeout=2,
            )
            if result.returncode == 0:
                return
            print(f"[TYPE] xdotool backspace failed (code {result.returncode}), falling back", flush=True)
        except Exception as e:
            print(f"[TYPE] xdotool backspace error: {e}, falling back", flush=True)
        try:
            from pynput.keyboard import Controller, Key
            c = Controller()
            for _ in range(count):
                c.press(Key.backspace)
                c.release(Key.backspace)
        except Exception as e:
            print(f"[TYPE] Backspace failed: {e}", flush=True)

    def send_command(self, text):
        if not self.command_url or not text:
            return
        try:
            resp = requests.post(self.command_url, data=text.encode(), timeout=5)
            print(f"[CMD] Sent '{text[:60]}' to {self.command_url} (status {resp.status_code})", flush=True)
        except Exception as e:
            print(f"[CMD] Failed to send command: {e}", flush=True)

    def _detect_wake_word(self, text):
        if not self.wake_word or not text:
            return False, None
        first_space = text.find(" ")
        if first_space == -1:
            first_word = text
            rest = ""
        else:
            first_word = text[:first_space]
            rest = text[first_space + 1:]
        cleaned = first_word.strip().rstrip(",.!?:;\"'\u201c\u201d")
        if cleaned.lower() == self.wake_word.lower():
            return True, rest
        return False, None

    def process_and_output(self, text):
        if not text:
            return

        print(f"[RAW] Transcribed: '{text}'", flush=True)

        corrected, applied_list = apply_corrections(text, self.corrections)
        if applied_list:
            for a in applied_list:
                self._log_correction_applied(a["pattern"], a["replacement"], a.get("corr_id", ""))
                print(f"[CORR] '{a['pattern']}' -> '{a['replacement']}' ({a['count']}x)", flush=True)
            text = corrected

        cmd = self._process_voice_commands(text)
        if cmd == "__DELETE_LAST_WORD__":
            self._backspace(4)
            return
        if cmd == "__DELETE_LAST_SENTENCE__":
            self._backspace(20)
            return

        wake_detected, wake_rest = self._detect_wake_word(text)
        print(f"[WAKE] Detected={wake_detected}, first_word='{text.split(' ')[0] if text else ''}', rest='{wake_rest}'", flush=True)
        if wake_detected:
            command_text = wake_rest.strip()
            if not command_text:
                return
            if not STREAMING_MODE and self.llm_action != "off":
                command_text = llm_process(command_text, self.llm_action, self.llm_instruction, corrections=self.corrections)
            self.send_command(command_text)
            display_text = f"↪ {command_text}"
            self.last_transcription = display_text
            with self._history_lock:
                self.transcription_history.append({
                    "text": display_text,
                    "time": time.strftime("%H:%M:%S"),
                    "source": "command",
                })
                if len(self.transcription_history) > 50:
                    self.transcription_history.pop(0)
            self._save_history()
            print(f"[CMD] Command processed: '{command_text}'", flush=True)
            return

        if not STREAMING_MODE and self.llm_action != "off":
            processed = llm_process(text, self.llm_action, self.llm_instruction, corrections=self.corrections)
        else:
            processed = text

        self.last_transcription = processed
        with self._history_lock:
            self.transcription_history.append({
                "text": processed,
                "time": time.strftime("%H:%M:%S"),
                "source": "llm" if (not STREAMING_MODE and self.llm_action != "off") else ("streaming" if STREAMING_MODE else "batch"),
            })
            if len(self.transcription_history) > 50:
                self.transcription_history.pop(0)
        self._save_history()

        print(f"Output: '{processed}'", flush=True)
        if self.clipboard_mode:
            self.type_text(processed)
        else:
            self.copy_to_clipboard(processed)

    def _ydotool_type(self, text):
        """Type text via ydotool (evdev-level; used on the Wayland path).
        Returns True on success. ASCII-only: ydotool maps characters through
        a US-layout table, so callers must route non-ASCII to the paste path."""
        try:
            result = subprocess.run(
                ["ydotool", "type",
                 "-d", str(_YD_TYPE_KEY_DELAY_MS),
                 "-H", str(_YD_TYPE_KEY_HOLD_MS),
                 "--", text],
                capture_output=True, timeout=15,
            )
            if result.returncode == 0:
                print(f"[TYPE] Typed via ydotool: '{text[:50]}'", flush=True)
                return True
            print(f"[TYPE] ydotool failed (code {result.returncode}): {result.stderr.decode(errors='replace')[:100]}", flush=True)
        except Exception as e:
            print(f"[TYPE] ydotool error: {e}", flush=True)
        return False

    def _ydotool_key(self, sequence):
        """Emit raw key down/up pairs via ydotool.

        sequence: list of (evdev_keycode, value) tuples, e.g. [(29, 1), (47, 1)]
        for Ctrl down + V down. Returns True when the daemon accepted them."""
        args = ["ydotool", "key"] + [f"{code}:{value}" for code, value in sequence]
        try:
            result = subprocess.run(args, capture_output=True, timeout=10)
            if result.returncode != 0:
                print(f"[TYPE] ydotool key failed (code {result.returncode})", flush=True)
            return result.returncode == 0
        except Exception as e:
            print(f"[TYPE] ydotool key error: {e}", flush=True)
            return False

    def type_text(self, text):
        if not text:
            return
        with self._typing_lock:
            print(f"Injecting: '{text}'", flush=True)
            self.last_transcription = text
            prefer_ydotool = _prefer_ydotool()
            if prefer_ydotool and text.isascii() and self._ydotool_type(text):
                return
            # NOTE (non-ASCII on Wayland): ydotool type maps through a US-layout
            # table and xdotool is blind on Wayland, so skip both typing legs
            # and go straight to clipboard paste instead of emitting mojibake
            # (or swallowing the text behind a vacuous xdotool success).
            if not (prefer_ydotool and not text.isascii()):
                try:
                    result = subprocess.run(
                        ["xdotool", "type", "--clearmodifiers", text], capture_output=True, timeout=30
                    )
                    if result.returncode == 0:
                        print(f"[TYPE] Typed via xdotool: '{text[:50]}'", flush=True)
                        return
                    print(f"[TYPE] xdotool failed (code {result.returncode}): {result.stderr.decode(errors='replace')[:100]}", flush=True)
                except Exception as e:
                    print(f"[TYPE] xdotool error: {e}", flush=True)
            if self._paste_via_clipboard(text):
                return
            try:
                from pynput.keyboard import Controller
                Controller().type(text)
                print(f"[TYPE] Typed via pynput: '{text[:50]}'", flush=True)
            except Exception as e:
                print(f"[TYPE] pynput also failed: {e}", flush=True)
                print("Warning: all backends failed to type text", flush=True)

    def _paste_via_clipboard(self, text):
        if not _copy_to_system_clipboard(text):
            return False
        if _prefer_ydotool():
            if self._ydotool_key([(_YD_KEY_LEFTCTRL, 1), (_YD_KEY_V, 1),
                                  (_YD_KEY_V, 0), (_YD_KEY_LEFTCTRL, 0)]):
                print(f"[TYPE] Pasted via clipboard (ydotool ctrl+v): '{text[:50]}'", flush=True)
                return True
            print("[TYPE] ydotool ctrl+v failed, falling back", flush=True)
        try:
            result = subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                capture_output=True, timeout=3,
            )
            if result.returncode == 0:
                print(f"[TYPE] Pasted via clipboard: '{text[:50]}'", flush=True)
                return True
            print(f"[TYPE] ctrl+v paste failed (code {result.returncode}), falling back", flush=True)
            return False
        except Exception as e:
            print(f"[TYPE] ctrl+v paste failed, falling back: {e}", flush=True)
            return False

    def update_config(
        self,
        stt_endpoint=None,
        stt_model=None,
        stt_language=None,
        stt_api_key=None,
        streaming=None,
        hotkey=None,
        device_index=None,
        silence_threshold=None,
        beep_enabled=None,
        pulse_source=None,
        push_to_hold=None,
        clipboard_mode=None,
        llm_action=None,
        llm_instruction=None,
        openai_base_url=None,
        openai_chat_model_id=None,
        openai_api_key=None,
        wake_word=None,
        command_url=None,
        initial_prompt=None,
        beep_volume=None,
        backspace_after_hotkey=None,
    ):
        global STT_ENDPOINT, STT_MODEL, STT_LANGUAGE, STT_API_KEY, STREAMING_MODE, HOTKEY_STR
        global DEVICE_INDEX, SILENCE_THRESHOLD, BEEP_ENABLED, PULSE_SOURCE_NAME
        global PUSH_TO_HOLD, CLIPBOARD_MODE, LLM_ACTION, LLM_INSTRUCTION
        global OPENAI_BASE_URL, OPENAI_CHAT_MODEL_ID, OPENAI_API_KEY
        global WAKE_WORD, COMMAND_URL, INITIAL_PROMPT, BEEP_VOLUME
        global BACKSPACE_AFTER_HOTKEY

        need_hotkey_restart = False

        with _config_lock:
            if stt_endpoint is not None:
                STT_ENDPOINT = stt_endpoint
            if stt_model is not None:
                STT_MODEL = stt_model
            if stt_language is not None:
                STT_LANGUAGE = stt_language.strip() or "auto"
                self.stt_language = STT_LANGUAGE
            if stt_api_key is not None:
                STT_API_KEY = stt_api_key.strip()
                self.stt_api_key = STT_API_KEY
            if streaming is not None:
                STREAMING_MODE = bool(streaming)
            if beep_enabled is not None:
                BEEP_ENABLED = bool(beep_enabled)
            if beep_volume is not None:
                BEEP_VOLUME = max(0.0, min(1.0, float(beep_volume)))
                self.beep_volume = BEEP_VOLUME
            if silence_threshold is not None and str(silence_threshold).strip():
                SILENCE_THRESHOLD = float(silence_threshold)
            if device_index is not None and str(device_index).strip():
                try:
                    di = int(device_index)
                    if di < 0:
                        print(f"Ignoring invalid device index: {di}", flush=True)
                    else:
                        DEVICE_INDEX = di
                        self.recorder.device_index = DEVICE_INDEX
                except Exception:
                    pass

            if hotkey is not None and hotkey != HOTKEY_STR:
                HOTKEY_STR = hotkey
                need_hotkey_restart = True

            if pulse_source is not None:
                PULSE_SOURCE_NAME = pulse_source.strip() or None
                self.recorder.pulse_source_name = PULSE_SOURCE_NAME

            if push_to_hold is not None:
                PUSH_TO_HOLD = bool(push_to_hold)
                self.push_to_hold = PUSH_TO_HOLD

            if clipboard_mode is not None:
                CLIPBOARD_MODE = bool(clipboard_mode)
                self.clipboard_mode = CLIPBOARD_MODE

            if backspace_after_hotkey is not None:
                BACKSPACE_AFTER_HOTKEY = bool(backspace_after_hotkey)
                self.backspace_after_hotkey = BACKSPACE_AFTER_HOTKEY

            if llm_action is not None:
                LLM_ACTION = llm_action
                self.llm_action = LLM_ACTION

            if llm_instruction is not None:
                LLM_INSTRUCTION = llm_instruction
                self.llm_instruction = LLM_INSTRUCTION

            if openai_base_url is not None:
                OPENAI_BASE_URL = openai_base_url.strip()
                self.openai_base_url = OPENAI_BASE_URL
            if openai_chat_model_id is not None:
                OPENAI_CHAT_MODEL_ID = openai_chat_model_id.strip()
                self.openai_chat_model_id = OPENAI_CHAT_MODEL_ID
            if openai_api_key is not None:
                OPENAI_API_KEY = openai_api_key.strip()
                self.openai_api_key = OPENAI_API_KEY

            if wake_word is not None:
                WAKE_WORD = wake_word.strip()
                self.wake_word = WAKE_WORD

            if command_url is not None:
                COMMAND_URL = command_url.strip()
                self.command_url = COMMAND_URL

            if initial_prompt is not None:
                INITIAL_PROMPT = initial_prompt.strip()
                self.initial_prompt = INITIAL_PROMPT

        if need_hotkey_restart and self.is_running:
            if self.is_recording:
                print("Hotkey changed while recording — stopping first", flush=True)
                self.toggle_recording()
            self.stop_service()
            self.start_service()

        # Save to file
        save_config(
            {
                "STT_ENDPOINT": STT_ENDPOINT,
                "STT_MODEL": STT_MODEL,
                "STT_LANGUAGE": STT_LANGUAGE,
                "STT_API_KEY": STT_API_KEY,
                "STREAMING_MODE": STREAMING_MODE,
                "BEEP_ENABLED": BEEP_ENABLED,
                "SILENCE_THRESHOLD": SILENCE_THRESHOLD,
                "DEVICE_INDEX": DEVICE_INDEX,
                "HOTKEY_STR": HOTKEY_STR,
                "SILENCE_DURATION": SILENCE_DURATION,
                "PULSE_SOURCE_NAME": PULSE_SOURCE_NAME,
                "PUSH_TO_HOLD": PUSH_TO_HOLD,
                "CLIPBOARD_MODE": CLIPBOARD_MODE,
                "LLM_ACTION": LLM_ACTION,
                "LLM_INSTRUCTION": LLM_INSTRUCTION,
                "OPENAI_BASE_URL": OPENAI_BASE_URL,
                "OPENAI_CHAT_MODEL_ID": OPENAI_CHAT_MODEL_ID,
                "OPENAI_API_KEY": OPENAI_API_KEY,
                "WAKE_WORD": WAKE_WORD,
                "COMMAND_URL": COMMAND_URL,
                "INITIAL_PROMPT": INITIAL_PROMPT,
                "BEEP_VOLUME": BEEP_VOLUME,
                "BACKSPACE_AFTER_HOTKEY": BACKSPACE_AFTER_HOTKEY,
            }
        )

        self.notify("Config Updated", "Settings saved persistently")

    def toggle_recording(self):
        with self._lock:
            if not self.is_recording:
                # is_recording must be True before start() so the stop path is
                # reachable via the hotkey. On start() failure we reset it below
                # to prevent the state machine from being stuck in "recording".
                self.is_recording = True
                self.play_beep(800, 0.1)
                self.notify("Recording", "Speak now...")
                try:
                    self.recorder.start(device_index=DEVICE_INDEX, pulse_source=PULSE_SOURCE_NAME)
                except Exception as e:
                    self.is_recording = False
                    self.notify("Microphone Error", str(e)[:80])
                    print(f"[ERROR] Failed to start recording: {e}", flush=True)
                    return
                if STREAMING_MODE:
                    threading.Thread(target=self._streaming_worker, daemon=True).start()
            else:
                self.is_recording = False
                self.play_beep(400, 0.1)
                self.notify("Processing", "Finalizing...")

                def process_stop():
                    try:
                        rec = self.recorder
                        audio_path = rec.stop()
                        if not STREAMING_MODE and audio_path:
                            text = self.transcribe(audio_path)
                            self.process_and_output(text)
                        self.status = "Idle"
                    except Exception as e:
                        print(f"Stop error: {e}")

                threading.Thread(target=process_stop, daemon=True).start()

    def _push_to_hold_start(self):
        with self._lock:
            if self.is_recording:
                return
            # Same pattern as toggle_recording: set is_recording first so the
            # release key listener can call _push_to_hold_stop; reset on failure.
            self.is_recording = True
        self.play_beep(800, 0.1)
        self.notify("Recording", "Speak now...")
        try:
            self.recorder.start(device_index=DEVICE_INDEX, pulse_source=PULSE_SOURCE_NAME)
        except Exception as e:
            with self._lock:
                self.is_recording = False
            self.notify("Microphone Error", str(e)[:80])
            print(f"[ERROR] Failed to start recording: {e}", flush=True)
            return
        if STREAMING_MODE:
            threading.Thread(target=self._streaming_worker, daemon=True).start()

        # Safety timeout: auto-stop after 30min if key release not detected
        def timeout():
            print("[PTH] Safety timeout — stopping", flush=True)
            self._push_to_hold_stop()

        self._pth_timer = threading.Timer(5.0, timeout)
        self._pth_timer.daemon = True
        self._pth_timer.start()

    def _push_to_hold_stop(self):
        if self._pth_timer:
            self._pth_timer.cancel()
            self._pth_timer = None
        with self._lock:
            if not self.is_recording:
                return
            self.is_recording = False
        self.play_beep(400, 0.1)
        self.notify("Processing", "Finalizing...")

        def process_stop():
            try:
                rec = self.recorder
                audio_path = rec.stop()
                if not STREAMING_MODE and audio_path:
                    text = self.transcribe(audio_path)
                    self.process_and_output(text)
                self.status = "Idle"
            except Exception as e:
                print(f"Stop error: {e}")

        threading.Thread(target=process_stop, daemon=True).start()

    def _streaming_worker(self):
        with self._lock:
            if self._streaming_worker_active:
                return
            self._streaming_worker_active = True

        try:
            utterance_buffer = []
            silence_duration = 0.0
            is_speaking = False

            while self.is_recording:
                try:
                    chunk = self.recorder.stream_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                rms = np.sqrt(np.mean(chunk**2))
                if rms > SILENCE_THRESHOLD:
                    is_speaking = True
                    silence_duration = 0.0
                elif is_speaking:
                    silence_duration += len(chunk) / float(self.recorder.rate)

                if is_speaking:
                    utterance_buffer.append(chunk)
                    if silence_duration > SILENCE_DURATION:
                        audio_data = np.concatenate(utterance_buffer, axis=0)
                        utterance_buffer = []
                        is_speaking = False
                        silence_duration = 0.0
                        if len(audio_data) / float(self.recorder.rate) > 0.4:
                            self._process_stream_chunk(audio_data)

            if utterance_buffer:
                audio_data = np.concatenate(utterance_buffer, axis=0)
                if len(audio_data) / float(self.recorder.rate) > 0.4:
                    self._process_stream_chunk(audio_data)
        finally:
            with self._lock:
                self._streaming_worker_active = False

    def _process_stream_chunk(self, audio_data):
        temp_file = f"/tmp/vds_{int(time.time() * 1000)}.wav"
        wav.write(temp_file, self.recorder.rate, audio_data)

        def run_trans():
            text = self.transcribe(temp_file)
            if text:
                corrected, applied_list = apply_corrections(text, self.corrections)
                if applied_list:
                    for a in applied_list:
                        self._log_correction_applied(a["pattern"], a["replacement"], a.get("corr_id", ""))
                        print(f"[STREAM][CORR] '{a['pattern']}' -> '{a['replacement']}'", flush=True)
                    text = corrected
                print(f"[STREAM] '{text}'", flush=True)
                with self._history_lock:
                    self.transcription_history.append({
                        "text": text,
                        "time": time.strftime("%H:%M:%S"),
                        "source": "streaming",
                    })
                    if len(self.transcription_history) > 50:
                        self.transcription_history.pop(0)
                self._save_history()
                self.type_text(text + " ")
            try:
                os.remove(temp_file)
            except Exception:
                pass

        if not self._transcribe_semaphore.acquire(blocking=False):
            print("Warning: too many pending transcriptions, dropping chunk", flush=True)
            return

        def run_with_release():
            try:
                run_trans()
            finally:
                self._transcribe_semaphore.release()

        threading.Thread(target=run_with_release, daemon=True).start()

    def start_service(self):
        with self._lock:
            if self.is_running:
                return
            self.is_running = True

        self._start_hotkey_listener()
        self.notify("Service", "Daemon Started")

    def _start_hotkey_listener(self):
        parts = [p.strip("<>") for p in HOTKEY_STR.split("+")]
        main_key = None
        for p in parts:
            if p not in ("ctrl", "cmd", "alt", "shift"):
                main_key = p
                break

        print(f"[HOTKEY] Starting listener for {HOTKEY_STR} (push_to_hold={self.push_to_hold})", flush=True)

        def listen():
            try:
                with keyboard.GlobalHotKeys({HOTKEY_STR: self._on_hotkey}) as h:
                    self.hotkey_listener = h
                    print(f"[HOTKEY] Registered: {HOTKEY_STR}", flush=True)
                    h.join()
            except Exception as e:
                print(f"[HOTKEY] Failed to register ({HOTKEY_STR}): {e}", flush=True)

        if main_key and self.push_to_hold:
            main_key_lower = main_key.lower()
            def release_listen():
                def on_release(key):
                    if (self.push_to_hold and self.is_recording
                            and hasattr(key, "char")
                            and key.char is not None
                            and key.char.lower() == main_key_lower):
                        self._push_to_hold_stop()
                try:
                    with keyboard.Listener(on_release=on_release) as lst:
                        self._release_listener = lst
                        lst.join()
                except Exception:
                    pass
            threading.Thread(target=release_listen, daemon=True).start()

        threading.Thread(target=listen, daemon=True).start()

    def _on_hotkey(self):
        now = time.time()
        if now - self._last_hotkey_time < 0.3:
            return
        self._last_hotkey_time = now
        if self.push_to_hold:
            if not self.is_recording:
                self._push_to_hold_start()
        else:
            self.toggle_recording()
        if self.backspace_after_hotkey:
            try:
                self._backspace(1)
            except Exception:
                pass

    def stop_service(self):
        with self._lock:
            if not self.is_running:
                return
            if self._pth_timer:
                self._pth_timer.cancel()
                self._pth_timer = None
            if self.hotkey_listener:
                self.hotkey_listener.stop()
            if self._release_listener:
                self._release_listener.stop()
            self.is_running = False
            self.is_recording = False
            self.recorder.stop()
        self.notify("Service", "Daemon Stopped")

    def restart_hotkey(self):
        if self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except Exception:
                pass
            self.hotkey_listener = None
        if self._release_listener:
            try:
                self._release_listener.stop()
            except Exception:
                pass
            self._release_listener = None
        self._start_hotkey_listener()
        print("[HOTKEY] Restarted", flush=True)

    def reinit_audio(self):
        """Re-create AudioRecorder from scratch — fresh device query, clears stale PulseAudio state."""
        if self.is_recording:
            self._push_to_hold_stop() if self.push_to_hold else self.toggle_recording()
        old_device = self.recorder.device_index
        self.recorder = AudioRecorder()
        new_device = self.recorder.device_index
        print(f"[AUDIO] Reinitialized recorder (device {old_device} -> {new_device})", flush=True)
        self.notify("Audio", f"Reinitialized (device {new_device})")

    def start_mic_test(self):
        if self._mic_test_stream is not None:
            self.stop_mic_test()

        target_device = DEVICE_INDEX if DEVICE_INDEX is not None else self.recorder.device_index
        try:
            target_device = int(target_device)
        except (ValueError, TypeError):
            pass

        pulse_src = PULSE_SOURCE_NAME or self.recorder.pulse_source_name
        old_pulse = os.environ.get("PULSE_SOURCE")
        if pulse_src:
            os.environ["PULSE_SOURCE"] = pulse_src
            # Use real PulseAudio device for shared access, same as recorder.start()
            target_device = _get_pulse_device_index()

        try:
            device_info = sd.query_devices(target_device, "input")
            default_rate = int(device_info["default_samplerate"])
            rate_to_use = default_rate
            try:
                sd.check_input_settings(device=target_device, channels=CHANNELS, samplerate=RATE)
                rate_to_use = RATE
            except Exception:
                pass

            self._mic_test_level = 0.0
            self._mic_test_active = True
            self._mic_test_seq += 1
            seq = self._mic_test_seq

            def callback(indata, frames, time_val, status):
                if status:
                    print(f"Mic test status: {status}", flush=True)
                rms = np.sqrt(np.mean(indata**2))
                self._mic_test_level = min(1.0, rms * 20)

            self._mic_test_stream = sd.InputStream(
                samplerate=rate_to_use,
                device=target_device,
                channels=CHANNELS,
                callback=callback,
            )
            self._mic_test_stream.start()
        finally:
            if pulse_src:
                if old_pulse is not None:
                    os.environ["PULSE_SOURCE"] = old_pulse
                else:
                    os.environ.pop("PULSE_SOURCE", None)

        def auto_stop():
            time.sleep(5)
            if self._mic_test_seq == seq:
                self.stop_mic_test()

        threading.Thread(target=auto_stop, daemon=True).start()

    def stop_mic_test(self):
        if not self._mic_test_active:
            return
        self._mic_test_active = False
        if self._mic_test_stream:
            try:
                self._mic_test_stream.stop()
                self._mic_test_stream.close()
            except Exception:
                pass
            self._mic_test_stream = None

    def get_mic_test_level(self):
        return float(self._mic_test_level)

    def test_stt_endpoint(self):
        pulse_src = None
        old_pulse = None
        test_file = "/tmp/vds_stt_test.wav"
        try:
            duration = 2.0

            target_device = DEVICE_INDEX if DEVICE_INDEX is not None else self.recorder.device_index
            try:
                target_device = int(target_device)
            except (ValueError, TypeError):
                pass

            pulse_src = PULSE_SOURCE_NAME or self.recorder.pulse_source_name
            old_pulse = os.environ.get("PULSE_SOURCE")
            if pulse_src:
                os.environ["PULSE_SOURCE"] = pulse_src
                # Use real PulseAudio device for shared access, same as recorder.start()
                target_device = _get_pulse_device_index()

            device_info = sd.query_devices(target_device, "input")
            default_rate = int(device_info["default_samplerate"])
            rate_to_use = default_rate
            # Only try 16000 if the device explicitly supports it
            try:
                sd.check_input_settings(device=target_device, channels=CHANNELS, samplerate=RATE)
                rate_to_use = RATE
            except Exception:
                pass

            recording = sd.rec(
                int(rate_to_use * duration), samplerate=rate_to_use,
                device=target_device, channels=1,
            )
            sd.wait()

            if pulse_src and old_pulse is not None:
                os.environ["PULSE_SOURCE"] = old_pulse
            elif pulse_src:
                os.environ.pop("PULSE_SOURCE", None)

            wav.write(test_file, rate_to_use, recording)

            start = time.time()
            with open(test_file, "rb") as f:
                files = {"file": ("stt_test.wav", f, "audio/wav")}
                data = {"model": STT_MODEL}
                lang = getattr(self, "stt_language", None) or STT_LANGUAGE
                if lang and lang != "auto":
                    data["language"] = lang
                parts = []
                if self.wake_word:
                    parts.append(self.wake_word)
                if self.initial_prompt:
                    parts.append(self.initial_prompt.strip())
                corr_words = []
                seen = set()
                for c in self.corrections:
                    if c.get("enabled", True):
                        r = c.get("replacement", "").strip().lower()
                        if r and r not in seen and len(r) >= 3:
                            seen.add(r)
                            corr_words.append(r)
                if corr_words:
                    parts.append(", ".join(corr_words[:20]))
                if parts:
                    prompt = ", ".join(parts)
                    if len(prompt) > MAX_PROMPT_CHARS:
                        prompt = "..." + prompt[-(MAX_PROMPT_CHARS - 3):]
                        print(f"[PROMPT] Truncated to {MAX_PROMPT_CHARS} chars", flush=True)
                    data["prompt"] = prompt
                _api_key2 = (getattr(self, "stt_api_key", None) or STT_API_KEY or "").strip()
                if _api_key2:
                    resp = requests.post(STT_ENDPOINT, files=files, data=data, headers={"Authorization": f"Bearer {_api_key2}"}, timeout=30)
                else:
                    resp = requests.post(STT_ENDPOINT, files=files, data=data, timeout=30)
                elapsed = time.time() - start
                resp.raise_for_status()
                result_text = resp.json().get("text", "").strip()

            return {
                "success": True,
                "text": result_text or "(empty — no speech detected)",
                "model": STT_MODEL,
                "endpoint": STT_ENDPOINT,
                "elapsed": round(elapsed, 2),
            }
        except Exception as e:
            if pulse_src and old_pulse is not None:
                os.environ["PULSE_SOURCE"] = old_pulse
            elif pulse_src:
                os.environ.pop("PULSE_SOURCE", None)
            return {
                "success": False,
                "error": str(e),
                "endpoint": STT_ENDPOINT,
                "model": STT_MODEL,
            }
        finally:
            try:
                if os.path.exists(test_file):
                    os.remove(test_file)
            except Exception:
                pass


if __name__ == "__main__":
    app_instance = VoiceDictationApp()
    app_instance.start_service()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        app_instance.stop_service()
