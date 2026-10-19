"""IDA Auto Theme - follow the Windows light/dark setting automatically.

Target: IDA Pro 9.x (developed and verified against IDA 9.5).

IDA's theming is CSS based: $IDADIR/themes/<name>/theme.css, written in a
small preprocessor dialect (@importtheme / @def / @palette / @ifdef /
@lighten / @darken).  The engine below mirrors IDA's own, so a theme produced
here is semantically identical to what IDA applies at startup.

The plugin polls HKCU\\...\\Themes\\Personalize\\AppsUseLightTheme and swaps
QApplication's style sheet + palette in place, so the switch happens without
restarting IDA.
"""
import os
import re
import json
import traceback

import idaapi
import ida_kernwin

PLUGIN_NAME = "IDAAutoTheme"
PLUGIN_VERSION = "1.0"

PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"

DEFAULT_CONFIG = {
    "enabled": True,
    "light_theme": "default",
    "dark_theme": "dark",
    "poll_ms": 1000,
}

# --------------------------------------------------------------------------
# theme.css preprocessor
# --------------------------------------------------------------------------

PLATFORM_DEFS = {"__WIN__"} if os.name == "nt" else {"__MAC__"}

_RE_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RE_IMPORT = re.compile(r'@importtheme\s+"([^"]+)"\s*;?\s*$')
_RE_DEF = re.compile(r"@def\s+([A-Za-z0-9_\-]+)\s+(.*?);?\s*$")
_RE_PALETTE = re.compile(
    r"@palette\s+((?:(?:Disabled|Inactive|Active)\s+)?[A-Za-z0-9_]+)\s+([^;]+?)\s*;?\s*$")
_RE_IFDEF = re.compile(r"@ifdef\s+([A-Za-z0-9_]+)\s*;?\s*$")
_RE_IFNDEF = re.compile(r"@ifndef\s+([A-Za-z0-9_]+)\s*;?\s*$")
_RE_ENDIF = re.compile(r"@endif\s*;?\s*$")
_RE_VAR = re.compile(r"\$\{([A-Za-z0-9_\-]+)\}")
_RE_COLORFN = re.compile(r"@(lighten|darken)\(\s*([^,()]+?)\s*,\s*(\d+)\s*\)")


class ThemeError(Exception):
    pass


class Theme(object):
    def __init__(self, name, qss, palette, defs):
        self.name = name
        self.qss = qss
        self.palette = palette  # [(role_path, value)]
        self.defs = defs


def _qt_shade(op, color, percent):
    """Mirror QColor::lighter()/darker(): they work in HSV space."""
    from PySide6 import QtGui

    c = QtGui.QColor(color)
    if not c.isValid():
        return color
    fn = c.lighter if op == "lighten" else c.darker
    return fn(int(percent)).name()


def _resolve_colors(text):
    def repl(m):
        try:
            return _qt_shade(m.group(1), m.group(2).strip(), m.group(3))
        except Exception:
            return m.group(0)

    for _ in range(6):
        new = _RE_COLORFN.sub(repl, text)
        if new == text:
            break
        text = new
    return text


def _expand_vars(text, defs):
    for _ in range(10):
        new = _RE_VAR.sub(lambda m: defs.get(m.group(1), m.group(0)), text)
        if new == text:
            break
        text = new
    return text


def _find_theme_file(theme_dirs, theme_name):
    # IDA searches $IDADIR first and $IDAUSR second; later hits win.
    for d in reversed(theme_dirs):
        path = os.path.join(d, theme_name, "theme.css")
        if os.path.isfile(path):
            return path
    return None


def parse_theme(theme_dirs, theme_name, _stack=None):
    if _stack is None:
        _stack = []
    if theme_name in _stack:
        raise ThemeError("circular @importtheme: %s" % theme_name)

    path = _find_theme_file(theme_dirs, theme_name)
    if not path:
        raise ThemeError("theme '%s' not found in %s" % (theme_name, theme_dirs))

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = _RE_COMMENT.sub("", f.read())

    defs, palette, out, cond = {}, [], [], []

    def active():
        return all(cond)

    for line in raw.splitlines():
        s = line.strip()
        if not s:
            if active():
                out.append("")
            continue

        m = _RE_IMPORT.match(s)
        if m:
            if active():
                sub = parse_theme(theme_dirs, m.group(1), _stack + [theme_name])
                out.append(sub.qss)
                palette.extend(sub.palette)
                for k, v in sub.defs.items():
                    defs.setdefault(k, v)
            continue

        m = _RE_DEF.match(s)
        if m:
            if active():
                defs[m.group(1)] = _resolve_colors(
                    _expand_vars(m.group(2).rstrip(";").strip(), defs))
            continue

        m = _RE_PALETTE.match(s)
        if m:
            if active():
                val = _resolve_colors(
                    _expand_vars(m.group(2).rstrip(";").strip(), defs))
                palette.append((m.group(1).strip(), val))
            continue

        m = _RE_IFDEF.match(s)
        if m:
            cond.append(m.group(1) in PLATFORM_DEFS)
            continue
        m = _RE_IFNDEF.match(s)
        if m:
            cond.append(m.group(1) not in PLATFORM_DEFS)
            continue
        if _RE_ENDIF.match(s):
            if cond:
                cond.pop()
            continue

        if active():
            out.append(_resolve_colors(_expand_vars(line, defs)))

    qss = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return Theme(theme_name, qss, palette, defs)


# --------------------------------------------------------------------------
# paths / config
# --------------------------------------------------------------------------

def ida_user_dir():
    v = os.environ.get("IDAUSR")
    if v and os.path.isdir(v):
        return v
    appdata = os.environ.get("APPDATA")
    if appdata:
        cand = os.path.join(appdata, "Hex-Rays", "IDA Pro")
        if os.path.isdir(cand):
            return cand
    return os.path.expanduser("~")


def theme_search_dirs():
    dirs = []
    try:
        d = idaapi.idadir("themes")
        if d and os.path.isdir(d):
            dirs.append(d)
    except Exception:
        pass
    usr = os.path.join(ida_user_dir(), "themes")
    if os.path.isdir(usr):
        dirs.append(usr)
    return dirs


def config_path():
    return os.path.join(ida_user_dir(), "idatheme.json")


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        p = config_path()
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as f:
                cfg.update(json.load(f) or {})
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        p = config_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        traceback.print_exc()


# --------------------------------------------------------------------------
# system theme detection
# --------------------------------------------------------------------------

def system_is_light():
    """True if Windows' *app* theme is light, False for dark, None if unknown."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PERSONALIZE_KEY) as k:
            val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return bool(val)
    except Exception:
        pass
    try:
        from PySide6 import QtGui
        hints = QtGui.QGuiApplication.styleHints()
        return hints.colorScheme() == QtGui.Qt.ColorScheme.Light
    except Exception:
        return None


# --------------------------------------------------------------------------
# applying a theme
# --------------------------------------------------------------------------

_PALETTE_ROLES = {
    "Window", "WindowText", "Base", "Text", "Button", "ButtonText",
    "BrightText", "Highlight", "HighlightedText", "ToolTipBase", "ToolTipText",
    "PlaceholderText", "Link", "LinkVisited", "Light", "Midlight", "Mid",
    "Dark", "Shadow", "AlternateBase",
}


def build_palette(entries, base_palette):
    from PySide6 import QtGui

    pal = QtGui.QPalette(base_palette)
    for role_path, value in entries:
        parts = role_path.split()
        group = QtGui.QPalette.Active
        if len(parts) == 2 and parts[0] in ("Disabled", "Inactive", "Active"):
            group = getattr(QtGui.QPalette, parts[0])
            role_name = parts[1]
        else:
            role_name = parts[-1]
        if role_name not in _PALETTE_ROLES:
            continue
        role_enum = getattr(QtGui.QPalette.ColorRole, role_name, None)
        color = QtGui.QColor(value)
        if role_enum is None or not color.isValid():
            continue
        pal.setColor(group, role_enum, color)
    return pal


def repolish_all():
    from PySide6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()
        except Exception:
            pass


class ThemeApplier(object):
    def __init__(self):
        self.orig_palette = None
        self.current = None
        self.last_error = ""

    def apply(self, theme_name):
        from PySide6 import QtWidgets

        app = QtWidgets.QApplication.instance()
        if app is None:
            return False, "no QApplication"
        if self.orig_palette is None:
            self.orig_palette = app.palette()

        try:
            theme = parse_theme(theme_search_dirs(), theme_name)
        except Exception as e:
            self.last_error = "%s: %s" % (type(e).__name__, e)
            return False, self.last_error

        app.setStyleSheet(theme.qss)
        app.setPalette(
            build_palette(theme.palette, self.orig_palette)
            if theme.palette else self.orig_palette
        )
        # IDA's custom widgets read qproperty-* via the style sheet; a full
        # repolish is what makes them pick up the new values.
        repolish_all()

        self.current = theme_name
        self.last_error = ""
        return True, "applied '%s' (%d bytes QSS, %d palette entries)" % (
            theme_name, len(theme.qss), len(theme.palette))


APPLIER = ThemeApplier()


# --------------------------------------------------------------------------
# watcher
# --------------------------------------------------------------------------

class _Watcher(object):
    def __init__(self):
        self.timer = None
        self.last_light = None
        self.started = False
        self.polls = 0

    def start(self):
        if self.started:
            return
        try:
            from PySide6 import QtCore
        except Exception:
            return
        self.started = True
        self.timer = QtCore.QTimer()
        self.timer.setInterval(int(load_config().get("poll_ms") or 1000))
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.tick()

    def stop(self):
        if self.timer is not None:
            try:
                self.timer.stop()
            except Exception:
                pass
        self.timer = None
        self.started = False

    def tick(self):
        self.polls += 1
        cfg = load_config()
        if not cfg.get("enabled", True):
            return
        light = system_is_light()
        if light is None:
            return
        if self.last_light is None:
            self.last_light = light
            if APPLIER.current is None:
                self._switch(light, cfg)
            return
        if light != self.last_light:
            self.last_light = light
            self._switch(light, cfg)

    def _switch(self, light, cfg):
        name = cfg.get("light_theme" if light else "dark_theme")
        ok, msg = APPLIER.apply(name)
        if ok:
            ida_kernwin.msg("[%s] system=%s -> %s\n" % (
                PLUGIN_NAME, "light" if light else "dark", msg))
        else:
            ida_kernwin.msg("[%s] FAILED: %s\n" % (PLUGIN_NAME, msg))


WATCHER = _Watcher()


def force_refresh():
    light = system_is_light()
    if light is None:
        return "cannot read the system theme"
    WATCHER.last_light = light
    cfg = load_config()
    return APPLIER.apply(cfg.get("light_theme" if light else "dark_theme"))[1]


# --------------------------------------------------------------------------
# plugin entry
# --------------------------------------------------------------------------

class AutoThemePlugin(idaapi.plugin_t):
    flags = idaapi.PLUGIN_FIX | idaapi.PLUGIN_KEEP | idaapi.PLUGIN_HIDE
    comment = "Follow the OS light/dark theme"
    help = "Automatically switch IDA's theme when Windows switches light/dark."
    wanted_name = "Auto Theme (follow system)"
    wanted_hotkey = "Ctrl-Shift-F9"

    def init(self):
        # Called for every database; widgets may have been recreated, so
        # re-check the current state instead of assuming it is still right.
        try:
            if WATCHER.started:
                WATCHER.tick()
            else:
                WATCHER.start()
        except Exception:
            traceback.print_exc()
        return idaapi.PLUGIN_KEEP

    def run(self, arg):
        ida_kernwin.msg("[%s] %s\n" % (PLUGIN_NAME, force_refresh()))
        return True

    def term(self):
        WATCHER.stop()


def PLUGIN_ENTRY():
    return AutoThemePlugin()


def _main_window():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None
    for w in app.topLevelWidgets():
        if isinstance(w, QtWidgets.QMainWindow) and w.isWindow():
            return w
    return None


def autostart():
    """Apply the right theme once IDA's main window exists, then poll."""
    try:
        light = system_is_light()
        if light is not None and load_config().get("enabled", True):
            cfg = load_config()
            APPLIER.apply(cfg.get("light_theme" if light else "dark_theme"))
            WATCHER.last_light = light
    except Exception:
        traceback.print_exc()
    try:
        WATCHER.start()
    except Exception:
        traceback.print_exc()


def _deferred_autostart(attempt=0):
    """Styling before the main window exists can wedge IDA's start-up."""
    try:
        from PySide6 import QtCore
    except Exception:
        return
    if _main_window() is None and attempt < 40:
        QtCore.QTimer.singleShot(250, lambda: _deferred_autostart(attempt + 1))
        return
    autostart()


# IDA imports plugins while its GUI is still being built, so wait for the
# main window before touching the style sheet.
try:
    from PySide6 import QtCore as _QtCore
    _QtCore.QTimer.singleShot(400, _deferred_autostart)
except Exception:
    autostart()
