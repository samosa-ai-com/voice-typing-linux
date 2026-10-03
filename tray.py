#!/usr/bin/python3
"""
System tray for Voice Typing using GNOME AppIndicator (D-Bus StatusNotifierItem).
Run as subprocess from app.py, communicates via HTTP.
"""

import subprocess
import sys
import threading
import time
import json
import urllib.request
import urllib.error

UI_URL = "http://127.0.0.1:3221"

RECENT_MAX = 5
RECENT_LABEL_LEN = 45

try:
    import gi
    gi.require_version("AyatanaAppIndicator3", "0.1")
    gi.require_version("Gtk", "3.0")
    from gi.repository import AyatanaAppIndicator3, Gtk, GLib
except ImportError as e:
    print(f"[TRAY] Missing dependency: {e}", flush=True)
    sys.exit(1)


def api_get(path):
    try:
        r = urllib.request.urlopen(f"{UI_URL}{path}", timeout=2)
        return json.loads(r.read().decode())
    except Exception:
        return None


def api_post_json(path, data):
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{UI_URL}{path}", data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def update_icon(indicator):
    status = api_get("/status")
    if not status:
        indicator.set_label("Offline", "")
        indicator.set_icon("dialog-information")
        return

    rec = status.get("is_recording", False)
    running = status.get("is_running", False)

    if rec:
        icon_name = "media-record"
        label = "Recording..."
    elif running:
        icon_name = "microphone-sensitivity-high"
        label = "Active"
    else:
        icon_name = "microphone-sensitivity-muted"
        label = "Stopped"

    indicator.set_label(label, "")
    indicator.set_icon(icon_name)
    indicator.set_attention_icon("media-record")


def _send_settings(patch):
    api_post_json("/settings", patch)


def format_recent_label(entry, max_len=RECENT_LABEL_LEN):
    """Single-line menu label for a history entry. Callers must disable
    mnemonics (set_use_underline(False)) since text may contain '_'."""
    if not isinstance(entry, dict):
        entry = {}
    text = " ".join(str(entry.get("text", "") or "").split())
    if len(text) > max_len:
        text = text[:max_len - 1] + "\u2026"
    stamp = entry.get("time", "") or ""
    return f"{stamp}  {text}" if stamp else text


def _sync_recent(refs):
    history = api_get("/history")
    if not isinstance(history, list):
        return

    recent = [e for e in history[-RECENT_MAX:][::-1] if isinstance(e, dict)]
    sig = tuple((e.get("time", "") or "", e.get("text", "") or "") for e in recent)
    if sig == refs.get("recent_sig"):
        return

    sub = refs["recent_sub"]
    for child in sub.get_children():
        sub.remove(child)
    if not recent:
        empty = Gtk.MenuItem(label="(no transcriptions yet)")
        empty.set_sensitive(False)
        sub.append(empty)
    for entry in recent:
        text = entry.get("text", "") or ""
        item = Gtk.MenuItem(label=format_recent_label(entry))
        item.set_use_underline(False)
        item.connect("activate", lambda _, t=text: api_post_json(
            "/copy_to_clipboard", {"text": t}))
        sub.append(item)
    sub.show_all()
    refs["recent_sig"] = sig


def _sync_menu(refs):
    config = api_get("/llm_config")
    if not config:
        return

    pth = config.get("push_to_hold", False)
    refs["mode_push"].set_active(pth)
    refs["mode_toggle"].set_active(not pth)

    clip = config.get("clipboard_mode", True)
    refs["output_type"].set_active(clip)
    refs["output_clip"].set_active(not clip)

    llm_action = config.get("llm_action", "off")
    for action, item_key in [("off", "llm_off"), ("grammar", "llm_grammar"),
                             ("translate", "llm_translate"), ("custom", "llm_custom")]:
        item = refs[item_key]
        base = refs["llm_base"][action]
        item.set_label(f"\u2713 {base}" if action == llm_action else f"  {base}")

    llm_inst = config.get("llm_instruction", "")
    for lang, item in refs["lang_items"].items():
        base = refs["lang_base"][lang]
        is_active = (llm_action == "translate" and lang == llm_inst)
        item.set_label(f"\u2713 {base}" if is_active else f"  {base}")


def build_menu(indicator):
    menu = Gtk.Menu()

    item_status = Gtk.MenuItem(label="Voice Typing")
    item_status.set_sensitive(False)
    menu.append(item_status)
    menu.append(Gtk.SeparatorMenuItem())

    # === Mode ===
    mode_toggle = Gtk.RadioMenuItem(label="Toggle Mode")
    mode_push = Gtk.RadioMenuItem(group=mode_toggle, label="Push-to-Hold")
    mode_toggle.connect("activate", lambda _: _send_settings({"push_to_hold": False}))
    mode_push.connect("activate", lambda _: _send_settings({"push_to_hold": True}))
    menu.append(mode_toggle)
    menu.append(mode_push)
    menu.append(Gtk.SeparatorMenuItem())

    # === Output ===
    output_type = Gtk.RadioMenuItem(label="Type into document")
    output_clip = Gtk.RadioMenuItem(group=output_type, label="Copy to Clipboard")
    output_type.connect("activate", lambda _: _send_settings({"clipboard_mode": True}))
    output_clip.connect("activate", lambda _: _send_settings({"clipboard_mode": False}))
    menu.append(output_type)
    menu.append(output_clip)
    menu.append(Gtk.SeparatorMenuItem())

    # === Recent transcriptions submenu ===
    recent_parent = Gtk.MenuItem(label="Recent Transcriptions")
    recent_sub = Gtk.Menu()
    recent_parent.set_submenu(recent_sub)
    menu.append(recent_parent)
    menu.append(Gtk.SeparatorMenuItem())

    # === LLM submenu ===
    llm_parent = Gtk.MenuItem(label="LLM Post-Process")
    llm_sub = Gtk.Menu()

    llm_base = {"off": "Off", "grammar": "Grammar Fix", "translate": "Translate", "custom": "Custom"}
    llm_off = Gtk.MenuItem(label=f"  {llm_base['off']}")
    llm_grammar = Gtk.MenuItem(label=f"  {llm_base['grammar']}")

    llm_translate = Gtk.MenuItem(label=f"  {llm_base['translate']}")
    lang_sub = Gtk.Menu()
    langs = ["Hindi", "English", "French", "Spanish", "German", "Japanese", "Chinese", "Arabic"]
    lang_items = {}
    lang_base = {}
    for lang in langs:
        lang_base[lang] = lang
        li = Gtk.MenuItem(label=f"  {lang}")
        li.connect("activate", lambda _, lang_code=lang: _send_settings({
            "llm_action": "translate", "llm_instruction": lang_code
        }))
        lang_sub.append(li)
        lang_items[lang] = li
    llm_translate.set_submenu(lang_sub)

    llm_custom = Gtk.MenuItem(label=f"  {llm_base['custom']}")

    llm_off.connect("activate", lambda _: _send_settings({"llm_action": "off"}))
    llm_grammar.connect("activate", lambda _: _send_settings({"llm_action": "grammar"}))
    llm_custom.connect("activate", lambda _: _send_settings({"llm_action": "custom"}))

    for item in (llm_off, llm_grammar, llm_translate, llm_custom):
        llm_sub.append(item)
    llm_parent.set_submenu(llm_sub)
    menu.append(llm_parent)
    menu.append(Gtk.SeparatorMenuItem())

    # === Reconnect Hotkey ===
    item_reconnect = Gtk.MenuItem(label="Reconnect Hotkey")
    item_reconnect.connect("activate", lambda _: api_post_json("/restart_hotkey", {}))
    menu.append(item_reconnect)

    # === Open Web UI ===
    item_web = Gtk.MenuItem(label="Open Web UI")
    item_web.connect("activate", lambda _: subprocess.Popen(["xdg-open", UI_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    menu.append(item_web)

    # === Quit ===
    item_quit = Gtk.MenuItem(label="Quit")
    item_quit.connect("activate", lambda _: Gtk.main_quit())
    menu.append(item_quit)

    menu.show_all()
    indicator.set_menu(menu)

    refs = {
        "mode_toggle": mode_toggle,
        "mode_push": mode_push,
        "output_type": output_type,
        "output_clip": output_clip,
        "recent_sub": recent_sub,
        "recent_sig": None,
        "llm_off": llm_off,
        "llm_grammar": llm_grammar,
        "llm_translate": llm_translate,
        "llm_custom": llm_custom,
        "llm_base": llm_base,
        "lang_items": lang_items,
        "lang_base": lang_base,
    }
    return refs


def main():
    indicator = AyatanaAppIndicator3.Indicator.new(
        "voice-typing",
        "",
        AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
    )
    indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

    for _ in range(10):
        if api_get("/status") is not None:
            break
        time.sleep(1)

    update_icon(indicator)
    refs = build_menu(indicator)

    def poll():
        while True:
            time.sleep(2)
            GLib.idle_add(update_icon, indicator)
            GLib.idle_add(_sync_menu, refs)
            GLib.idle_add(_sync_recent, refs)

    threading.Thread(target=poll, daemon=True).start()
    Gtk.main()


if __name__ == "__main__":
    main()
