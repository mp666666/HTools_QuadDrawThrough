# HTools_QuadDrawThrough

[English](README.md) | [简体中文](README.zh-CN.md)

**1.0 · Maya 2018–2027 compatibility target · MIT**

An optional helper for Maya's native **Quad Draw**. Pick and drag existing low-poly vertices hidden by thick or layered Live meshes, with optional local-surface relax. Keep the usual **Make Live → select low-poly → Quad Draw** workflow without removing inner layers or manually projecting each stroke.

## Install

1. Download [HTools_QuadDrawThrough_v1.0_Install.mel](HTools_QuadDrawThrough_v1.0_Install.mel) with GitHub's **Download raw file** button, or extract it from the source ZIP.
2. Drag the `.mel` into a Maya viewport. A success dialog and **QD OFF / QD ON** shelf button should appear.
3. **Single-click** to toggle; **double-click** for settings. Closing settings keeps the helper active.

**Dragging does nothing?** In Script Editor, select **MEL**, use **File → Load Script**, then **Ctrl+A → Ctrl+Enter** to execute. Use the downloaded MEL, not the ZIP or a saved GitHub webpage.

The MEL contains all runtime code and the license. It works without adjacent files, fixed drive letters, administrator access or installation-time downloads. It installs into the current Maya profile's `userScriptDir/HTools_QuadDrawThrough`; the success dialog shows the path. Install separately for each Maya version / language profile you use.

Reinstall to upgrade. The old installation is retained in a sibling `.HTools_QuadDrawThrough-backup-*` folder. The helper is disabled during reload; enable it again afterwards.

## Use

Make the high-poly polygon mesh **Live**, select the low-poly mesh, activate **Quad Draw**, then switch **QD ON**. The helper follows the current meshes automatically.

| Action | Result |
| --- | --- |
| Left-drag near an existing low-poly vertex | Prefer moving it, even behind the high-poly mesh |
| Shift + left-drag over existing geometry | Auxiliary relax, if enabled |
| Click away from vertices / Shift over a valid gap | Native point / face creation |
| Release with a yellow weld cursor | Weld candidate vertices using native Auto-weld settings |
| B / hold B and drag | Native soft-selection controls |
| Esc / Undo / Redo | Cancel or undo / redo the whole assisted stroke |

The **辅助松弛** checkbox independently enables auxiliary relax. Turn it off to use native Shift relax while keeping assisted dragging. Native Shift + middle-drag, other modifiers and marking menus remain handled by Maya.

- **Symmetry:** reads native World / Object X, Y, Z settings. Initialize native **Topology** symmetry on the current low-poly center edge first; reinitialize if topology changes invalidate its pairs.
- **Soft selection:** reads native mode, radius and falloff. It replaces the panel's relax radius. Assisted auto-weld is disabled while soft selection is enabled.
- **Relax:** reads native Auto-Lock / Interior / Border / All modes, but uses a custom solver. Its feel is not identical to native Relax.
- **Hotkeys:** find `HTools_QuadDrawThroughToggle` and `HTools_QuadDrawThroughSettings` under **HTools**. No keys are assigned automatically.

The plugin UI is currently Chinese: **点拾取范围** = pick radius; **松弛半径** = relax radius; **松弛强度** = strength; **松弛贴合** = surface mode; **贴合偏移** = offset in centimeters; **额外锁住边界点** = additionally lock boundary vertices.

## Compatibility and limits

| Environment | Status |
| --- | --- |
| Windows, Maya 2018 / Python 2.7 / Qt 5 | Tested in Chinese and English Maya |
| Windows, Maya 2027 / Python 3 / Qt 6 | Tested in Chinese and English Maya |
| Other Maya versions in the target range | Compatibility code included; not individually tested |
| Japanese UI, macOS, Linux | Not validated |

The universal installer adapts to Python 2 / 3 and Qt 5 / 6. Runtime code does not depend on translated Maya menu labels; the plugin itself has no UI language switch.

Default **局部曲面** relax follows the nearby connected surface. It does not automatically find the intended outer layer; correct misplaced vertices before relaxing. Dragging and **视角最前层** mode use the first Live-surface hit from the current view and can cross layers. Coincident surfaces, self-intersections and large faces spanning grooves can remain ambiguous.

Use editable polygon meshes with outward low-poly normals. GPU Cache, NURBS, instances, referenced or deformed low-poly meshes are outside the supported scope. Queries use polygon data rather than smooth-preview surfaces. Initial high-poly indexing or changes can cause a brief pause; unchanged queries are cached. Settings last for the current session.

## Troubleshooting and removal

Installation errors appear in Script Editor and `HTools_QuadDrawThrough_install.log` in the system temporary directory. If relax affects nothing, check the auxiliary switch, native relax mode and boundary locking.

To uninstall: switch **QD OFF**, remove the shelf button, close Maya, then remove the installed folder and unwanted backups. Remove hotkeys you assigned. Do not force-unload the undo plugin while its strokes remain in the undo queue.

## Source and license

- `qd_through/`: readable runtime source.
- `install.py` + `HTools_QuadDrawThrough_Install_v10.py`: source installation entry points; keep the full source folder together.
- `package_release.py`: rebuild the universal MEL and source ZIP with Python 3.8+.
- [Validation](docs/VALIDATION.md) · [Development](docs/DEVELOPMENT.md) · [Contributing](CONTRIBUTING.md) · [Publishing](docs/PUBLISHING.md) · [Changelog](CHANGELOG.md).

Copyright (c) 2026 HTools contributors. [MIT License](LICENSE). Maya and its bundled dependencies are not redistributed. This project is not affiliated with Autodesk.
