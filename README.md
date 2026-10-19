# IDA Auto Theme

[English](README.en.md) | **简体中文**

让 IDA Pro 9.x 跟随 Windows 的亮/暗模式自动切换主题，**不用重启 IDA**。

针对 IDA 9.5 开发和验证（Win32 / x64 / IDA Professional 9.5b1）。

## 安装

整个项目只有一个插件文件：`src/IDAAutoTheme.py`，拷到 IDA 的用户插件目录即可。

```powershell
Copy-Item .\src\IDAAutoTheme.py "$env:APPDATA\Hex-Rays\IDA Pro\plugins\IDAAutoTheme.py"
```

装完重启 IDA。之后系统切到暗色，IDA 会在一秒内跟着变暗；切回亮色同理。

手动立即刷新：`Edit > Plugins > Auto Theme (follow system)`，或 `Ctrl-Shift-F9`。

卸载就是删掉那个文件：

```powershell
Remove-Item "$env:APPDATA\Hex-Rays\IDA Pro\plugins\IDAAutoTheme.py"
```

## 配置

`%APPDATA%\Hex-Rays\IDA Pro\idatheme.json`（不存在就用默认值，也可以自己建）：

```json
{
  "enabled": true,
  "light_theme": "default",
  "dark_theme": "dark",
  "poll_ms": 1000
}
```

| 字段 | 说明 |
|---|---|
| `enabled` | 关掉轮询但插件仍加载 |
| `light_theme` / `dark_theme` | 用哪个主题目录名。IDA 9.5 自带 `default`、`dark`、`darcula`；放在 `%APPDATA%\Hex-Rays\IDA Pro\themes\<名字>\theme.css` 的自定义主题也能直接用 |
| `poll_ms` | 轮询间隔，默认 1000ms |

改完不需要重启插件，下一轮轮询就读到新值（间隔与主题名即时生效）。

## IDA 的主题是怎么工作的（实测结论）

IDA 9.x 的主题是 CSS，不是注册表里那套老彩蛋：

- `$IDADIR/themes/<name>/theme.css`，用户目录 `%IDAUSR%/themes/<name>/theme.css` 优先级更高
- 一份 `theme.css` 用的是 IDA 自己的方言，Qt 并不认识：
  - `@importtheme "_base";` —— 引入公共骨架
  - `@def name value;` + `${name}` —— 文本宏
  - `@palette Window #363636;` —— 直接驱动 QPalette（dark 主题靠这个改整体配色）
  - `@ifndef __MAC__ ... @endif` —— 平台条件编译
  - `@lighten(#8AD1A9, 125)` / `@darken(...)` —— 颜色变换，等价于 `QColor::lighter/darker`
- 启动时 IDA 把方言展开成一份完整 QSS（约 57KB）塞给 `QApplication::setStyleSheet`，palette 另走 `setPalette`

所以「运行时切主题」= 自己重新展开一次 CSS，然后 `setStyleSheet` + `setPalette` + 全量 repolish。
本插件实现的就是这个展开器，输出与 IDA 原生结果**语义等价**（675 条声明逐一比对，双向差集为空）。

## 已知限制

- **启动瞬间会闪一下亮色**。插件要等主窗口建好才能安全地改样式表（太早改会把 IDA 卡死），实测延迟约 0.4–1 秒。
- **只覆盖 QSS 能覆盖的部分**。极少数由 C++ 侧直接写死颜色的元素（个别自绘控件、部分图形视图节点）可能不随主题变。实测反汇编视图、函数列表、输出窗口、导航带、缩略图都正常。
- **系统主题读取的是 `AppsUseLightTheme`**（应用模式），不是 `SystemUsesLightTheme`（任务栏那套）。这是 Windows 上应用跟随的正确键值。读不到时回退到 Qt 的 `colorScheme()`。
- 轮询是 1 秒一次读注册表，开销可以忽略；没有用 `WM_SETTINGCHANGE`，因为该消息的 lParam 判断在不同 Windows 版本上不稳定。
- 只测过 Windows + IDA 9.5。Linux/macOS 的路径和平台宏已在代码里处理，但未实测。

## 发布到官方插件市场（plugins.hex-rays.com）

**不需要提交表单**。Hex-Rays 已经把流程改成自助收录：一个索引器每天扫一遍 GitHub，找出带 `ida-plugin.json` 的仓库，读取其 Release，自动收录上架。

满足三个条件即可：

1. 仓库里有格式正确的 `ida-plugin.json` —— 就是 `src/ida-plugin.json`（`entryPoint` 必须与它同目录，所以这个文件放在 `src/` 而不是仓库根）
2. 打 tag 并发一个 GitHub Release
3. 等索引器跑（每天一次）

纯 Python 插件可以直接拿 GitHub 自动附带的源码归档当插件包，不需要另外打 zip。

校验元数据（可选，但能省掉一次失败的收录）：

```bash
pip install ida-hcli
hcli plugin lint ./src
```

几天后还没出现在 <https://plugins.hex-rays.com> 的话，按这个顺序查：元数据格式 → <https://github.com/HexRaysSA/plugin-repository/blob/v1/plugin-repository.json> 里有没有你 → 仓库能否被 GitHub code search 搜到（`path:**/ida-plugin.json`）→ 都不行就把仓库加进 `known-repositories.txt`，或直接开 issue。

## 文件

```
src/IDAAutoTheme.py   插件本体（单文件，含 CSS 展开器）
src/ida-plugin.json   Plugin Manager 元数据（发布到官方市场用）
_probe/check2.py      语义一致性验证：自研展开器 vs IDA 原生 QSS
_probe/check4.py      校验插件是否出现在 Edit > Plugins 菜单
README.md             中文文档
README.en.md          英文文档
```

## 自定义主题示例

在 `%APPDATA%\Hex-Rays\IDA Pro\themes\myblue\theme.css`：

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

然后把 `idatheme.json` 里的 `"dark_theme": "myblue"` 即可。
