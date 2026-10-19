# IDA Auto Theme

**English** | [简体中文](README.md)

Makes IDA Pro 9.x follow the Windows light/dark setting automatically — **no IDA restart required**.

Developed and verified against IDA 9.5 (Win32 / x64, IDA Professional 9.5b1).

## Install

The whole project is a single plugin file: `src/IDAAutoTheme.py`. Copy it into IDA's user plugin directory.

```powershell
Copy-Item .\src\IDAAutoTheme.py "$env:APPDATA\Hex-Rays\IDA Pro\plugins\IDAAutoTheme.py"
```

Restart IDA. From then on, switching Windows to dark mode turns IDA dark within a second; switching back does the same.

Force a refresh any time: `Edit > Plugins > Auto Theme (follow system)`, or `Ctrl-Shift-F9`.

To uninstall, just delete the file:

```powershell
Remove-Item "$env:APPDATA\Hex-Rays\IDA Pro\plugins\IDAAutoTheme.py"
```

## Configuration

`%APPDATA%\Hex-Rays\IDA Pro\idatheme.json` (optional — defaults apply if absent):

```json
{
  "enabled": true,
  "light_theme": "default",
  "dark_theme": "dark",
  "poll_ms": 1000
}
```

| Key | Meaning |
|---|---|
| `enabled` | Turn polling off while leaving the plugin loaded |
| `light_theme` / `dark_theme` | Theme directory name to use. IDA 9.5 ships `default`, `dark` and `darcula`; custom themes placed in `%APPDATA%\Hex-Rays\IDA Pro\themes\<name>\theme.css` work too |
| `poll_ms` | Poll interval, default 1000 ms |

Edits take effect on the next poll — no plugin reload needed (both the interval and the theme names are re-read every tick).

## How IDA's theming actually works (measured, not guessed)

IDA 9.x themes are CSS files, not the old registry colour entries:

- `$IDADIR/themes/<name>/theme.css`; `%IDAUSR%/themes/<name>/theme.css` takes precedence
- A `theme.css` is written in IDA's own dialect, which Qt knows nothing about:
  - `@importtheme "_base";` — pull in the shared skeleton
  - `@def name value;` + `${name}` — textual macros
  - `@palette Window #363636;` — drives `QPalette` directly (this is how the dark theme recolours everything)
  - `@ifndef __MAC__ ... @endif` — platform-conditional blocks
  - `@lighten(#8AD1A9, 125)` / `@darken(...)` — colour transforms, exactly `QColor::lighter/darker`
- At start-up IDA expands the dialect into one complete QSS (~57 KB) and hands it to `QApplication::setStyleSheet`; the palette goes through `setPalette` separately

So "switch theme at runtime" means: expand the CSS yourself, then `setStyleSheet` + `setPalette` + a full repolish.
That expander is what this plugin implements, and its output is **semantically identical** to IDA's own (all 675 declarations compared, both set differences empty).

## Known limitations

- **Brief flash of the light theme at start-up.** The plugin must wait for the main window to exist before touching the style sheet — styling earlier wedges IDA's start-up. Measured delay is roughly 0.4–1 s.
- **Only what QSS can reach.** A few elements with colours hard-coded on the C++ side (some custom-painted widgets, some graph view nodes) may not follow. Disassembly view, functions list, output window, navigation band and overview thumbnail were all verified to switch correctly.
- **The system setting read is `AppsUseLightTheme`** (app mode), not `SystemUsesLightTheme` (taskbar). The former is the correct value for application theming. Falls back to Qt's `colorScheme()` when unreadable.
- Polling reads the registry once a second; the cost is negligible. `WM_SETTINGCHANGE` is deliberately not used because its lParam handling is not reliable across Windows versions.
- Only Windows + IDA 9.5 has been tested. Linux/macOS paths and platform macros are handled in code but unverified.

## Publishing to the official plugin repository (plugins.hex-rays.com)

**There is no submission form.** Hex-Rays moved to a self-service flow: an indexer scans GitHub daily, finds repositories containing `ida-plugin.json`, reads their releases, and lists them automatically.

Three things are required:

1. A well-formed `ida-plugin.json` in the repo — that is `src/ida-plugin.json` here (`entryPoint` must live next to it, which is why the file sits in `src/` rather than the repo root)
2. A tag plus a GitHub Release
3. Time — the indexer runs once a day

Pure-Python plugins can use the source archive GitHub attaches to the release; no separate ZIP is needed.

Validate the metadata (optional, but it saves a failed indexing round):

```bash
pip install ida-hcli
hcli plugin lint ./src
```

If it has not shown up at <https://plugins.hex-rays.com> after a few days, check in this order: metadata validity → whether your repo appears in <https://github.com/HexRaysSA/plugin-repository/blob/v1/plugin-repository.json> → whether GitHub code search finds it (`path:**/ida-plugin.json`) → otherwise add the repo to `known-repositories.txt`, or open an issue.

## Layout

```
src/IDAAutoTheme.py   the plugin (single file, includes the CSS expander)
src/ida-plugin.json   Plugin Manager metadata (needed to publish)
_probe/check2.py      verifies the expander against IDA's native QSS
_probe/check4.py      verifies the plugin shows up under Edit > Plugins
README.md             Chinese documentation
README.en.md          this file
```

## Custom theme example

Create `%APPDATA%\Hex-Rays\IDA Pro\themes\myblue\theme.css`:

```css
@importtheme "_base";

@def my_bg #102030;
@def my_fg #ddeeff;

@palette Window     ${my_bg};
@palette WindowText ${my_fg};
@palette Base       @darken(${my_bg}, 90);
@palette Text       ${my_fg};

CustomIDAMemo
{
    qproperty-line-fg-default: ${my_fg};
}
```

Then set `"dark_theme": "myblue"` in `idatheme.json`.
