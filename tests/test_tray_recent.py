"""Tray 'Recent Transcriptions' submenu. GTK is stubbed — these tests cover
the label formatting and the submenu rebuild/click wiring, not rendering.
"""
import sys
import types


def _import_tray(monkeypatch):
    gi_mod = types.ModuleType("gi")
    gi_mod.require_version = lambda *a, **k: None
    repo = types.ModuleType("gi.repository")

    class FakeItem:
        def __init__(self, label=""):
            self.label = label
            self.sensitive = True
            self.underline = True
            self.callback = None

        def set_sensitive(self, value):
            self.sensitive = value

        def set_use_underline(self, value):
            self.underline = value

        def connect(self, _signal, callback):
            self.callback = callback

    class FakeMenu:
        def __init__(self):
            self.children = []

        def append(self, widget):
            self.children.append(widget)

        def remove(self, widget):
            self.children.remove(widget)

        def get_children(self):
            return list(self.children)

        def show_all(self):
            pass

    repo.AyatanaAppIndicator3 = types.SimpleNamespace()
    repo.Gtk = types.SimpleNamespace(Menu=FakeMenu, MenuItem=FakeItem)
    repo.GLib = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, "gi", gi_mod)
    monkeypatch.setitem(sys.modules, "gi.repository", repo)

    sys.modules.pop("tray", None)
    import tray as tray_module

    return tray_module


def _history(n):
    return [
        {"text": f"sentence number {i}", "time": f"10:00:0{i}", "source": "batch"}
        for i in range(n)
    ]


def test_format_recent_label_truncates_and_collapses(monkeypatch):
    tray = _import_tray(monkeypatch)

    assert tray.format_recent_label(
        {"text": "hello world", "time": "10:00:01"}) == "10:00:01  hello world"
    assert tray.format_recent_label({"text": "a\nb  c"}) == "a b c"
    long_label = tray.format_recent_label({"text": "x" * 100})
    assert len(long_label) == tray.RECENT_LABEL_LEN
    assert long_label.endswith("\u2026")
    # underscores must survive (widget disables mnemonics itself)
    assert tray.format_recent_label({"text": "a_b"}) == "a_b"


def test_sync_recent_shows_last_five_newest_first(monkeypatch):
    tray = _import_tray(monkeypatch)
    monkeypatch.setattr(tray, "api_get", lambda path: _history(7))

    refs = {"recent_sub": tray.Gtk.Menu(), "recent_sig": None}
    tray._sync_recent(refs)

    children = refs["recent_sub"].get_children()
    assert len(children) == 5
    assert children[0].label == "10:00:06  sentence number 6"
    assert children[-1].label == "10:00:02  sentence number 2"
    assert all(c.underline is False for c in children)


def test_sync_recent_skips_rebuild_when_unchanged(monkeypatch):
    tray = _import_tray(monkeypatch)
    monkeypatch.setattr(tray, "api_get", lambda path: _history(3))

    refs = {"recent_sub": tray.Gtk.Menu(), "recent_sig": None}
    tray._sync_recent(refs)
    first = refs["recent_sub"].get_children()
    tray._sync_recent(refs)
    assert refs["recent_sub"].get_children() == first


def test_sync_recent_click_copies_full_text(monkeypatch):
    tray = _import_tray(monkeypatch)
    monkeypatch.setattr(tray, "api_get", lambda path: _history(2))
    posted = []
    monkeypatch.setattr(tray, "api_post_json",
                        lambda path, data: posted.append((path, data)))

    refs = {"recent_sub": tray.Gtk.Menu(), "recent_sig": None}
    tray._sync_recent(refs)

    children = refs["recent_sub"].get_children()
    children[0].callback(children[0])  # newest entry (GTK passes the widget)
    assert posted == [("/copy_to_clipboard", {"text": "sentence number 1"})]


def test_sync_recent_empty_history(monkeypatch):
    tray = _import_tray(monkeypatch)
    monkeypatch.setattr(tray, "api_get", lambda path: [])

    refs = {"recent_sub": tray.Gtk.Menu(), "recent_sig": None}
    tray._sync_recent(refs)

    children = refs["recent_sub"].get_children()
    assert len(children) == 1
    assert children[0].sensitive is False


def test_sync_recent_ignores_bad_payload(monkeypatch):
    tray = _import_tray(monkeypatch)
    monkeypatch.setattr(tray, "api_get", lambda path: None)

    refs = {"recent_sub": tray.Gtk.Menu(), "recent_sig": None}
    tray._sync_recent(refs)

    assert refs["recent_sub"].get_children() == []
    assert refs["recent_sig"] is None
