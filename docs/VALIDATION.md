# Validation / 验证记录

**1.0.0 · Windows · 2026-11-19**

| Environment / 环境 | Core / 核心 | Installer / 安装 | GUI |
| --- | --- | --- | --- |
| Maya 2018 · Python 2.7.11 · Qt 5.6.1 | 67 passed | 7 passed | 33 passed |
| Maya 2027 · Python 3.13.9 · Qt 6.8.3 | 67 passed | 7 passed | 33 passed |

Chinese and English Maya GUI runs passed on both versions. Japanese UI, intermediate Maya versions and macOS / Linux are not validated. Requested language alone does not establish the actual UI language.

Coverage includes layered picking, back-face filtering, symmetry, soft selection, welding, local relax, undo / redo, native viewport interactions, shelf clicks, Unicode installation paths, upgrades, restart loading, source / MEL consistency and installed license preservation.

GUI checks run in separate Maya processes with isolated profiles and synthetic scenes. Qt events target real Maya widgets; this is not a complete manual Windows Explorer drag-and-drop test. Multi-Cut checks verify the target mesh, not a full face-cut gesture. Million-face performance, every GPU / DPI layout and arbitrary third-party interactions are outside the test scope.

See [test sources](../tests/) and [running instructions](DEVELOPMENT.md). Local reports, profiles, recordings and model files are not distributed.

两端均通过中文和英文 Maya GUI 测试；日文界面、中间 Maya 版本、macOS / Linux 未验证。指定启动语言不等于实际切换成功。

覆盖叠层拾取、背面过滤、对称、软选择、焊接、局部松弛、撤销重做、视口和工具架交互、中文路径安装、升级、重启、MEL 与源码一致性及安装后的许可证保留。

GUI 使用独立进程、隔离配置和合成场景，通过 Qt 事件测试真实控件，不代表已手动验证所有 Windows 拖入环境。Multi-Cut 只验证编辑对象衔接；百万面性能、全部显卡 / DPI 布局和第三方工具组合不在验证范围内。公开包不包含本机日志、配置、录屏或模型。
