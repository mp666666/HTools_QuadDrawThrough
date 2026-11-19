# HTools_QuadDrawThrough

[English](README.md) | [简体中文](README.zh-CN.md)

**1.0 · 适配目标 Maya 2018–2027 · MIT 许可证**

Maya 原生 **Quad Draw（四边形绘制）** 的可开关辅助工具。高模有厚度或叠层、遮住低模点时，仍可优先拾取和拖动，并可沿附近曲面松弛。保持 **Make Live → 选择低模 → Quad Draw** 的流程，无需删除内层或逐笔手动投射。

## 安装

1. 下载 [HTools_QuadDrawThrough_v1.0_Install.mel](HTools_QuadDrawThrough_v1.0_Install.mel)，在 GitHub 文件页点击 **Download raw file（下载原始文件）**，也可从源码 ZIP 中解压。
2. 将 `.mel` 拖入 Maya 视口，出现成功提示和 **QD OFF / QD ON** 工具架按钮。
3. **单击开关，双击设置**。关闭设置窗口不会停用辅助。

**拖入没反应：**在脚本编辑器切到 **MEL**，用 **文件 → 加载脚本** 打开，再按 **Ctrl+A → Ctrl+Enter** 执行。使用实际下载的 MEL，不要拖 ZIP 或保存的 GitHub 网页。

MEL 自带运行代码和许可证，可单独复制到其他电脑，不依赖旁边的文件、固定盘符、管理员权限或安装时下载。安装到当前 Maya 配置的 `userScriptDir/HTools_QuadDrawThrough`，实际路径见成功提示。不同 Maya 版本或语言配置分别安装。

升级时重新执行安装器即可；旧安装保留在同级 `.HTools_QuadDrawThrough-backup-*` 文件夹。重载会关闭辅助，完成后重新开启。

## 使用

高模多边形网格设为 **Make Live**，选择低模并开启 **Quad Draw**，再切换到 **QD ON**。辅助会自动跟随当前高模、低模。

| 操作 | 行为 |
| --- | --- |
| 已有低模点附近左键拖动 | 优先移动该点，包括被高模遮住的点 |
| Shift + 左键拖动已有低模 | 辅助松弛，需开启独立开关 |
| 空白处点击 / 在可建面的空隙按 Shift | 原生建点 / 建面 |
| 黄色焊接指针出现后松开 | 按原生 Auto-weld 设置焊接候选顶点 |
| B / 按住 B 拖动 | 原生软选择控制 |
| Esc / 撤销 / 重做 | 取消或撤销 / 重做整笔辅助操作 |

**辅助松弛**可独立关闭：关闭后 Shift 使用原生松弛，辅助拖点仍可用。Shift + 中键、其他修饰键和标记菜单继续由 Maya 处理。

- **对称：**读取原生 World / Object X、Y、Z 设置。Topology 对称需先在当前低模中线边按原生方式初始化；拓扑修改导致配对失效时重新初始化。
- **软选择：**读取原生模式、半径和衰减，取代面板的松弛半径。开启软选择时关闭辅助自动焊接。
- **松弛：**读取原生 Auto-Lock / 内部 / 边界 / 全部设置，使用自定义求解器，手感不完全等同原生 Relax。
- **快捷键：**在热键编辑器 **HTools** 分类搜索 `HTools_QuadDrawThroughToggle`、`HTools_QuadDrawThroughSettings`。安装只注册命令，不分配按键。

面板可调点拾取范围、松弛半径、强度、贴合模式和偏移；范围为屏幕像素，偏移为厘米。“额外锁住边界点”可能排除所有可松弛顶点。小圆指针不表示笔刷范围。

## 兼容范围与限制

| 环境 | 状态 |
| --- | --- |
| Windows、Maya 2018 / Python 2.7 / Qt 5 | 已验证中文和英文 Maya |
| Windows、Maya 2027 / Python 3 / Qt 6 | 已验证中文和英文 Maya |
| 目标范围内的其他 Maya 版本 | 已提供兼容处理，未逐版本实测 |
| 日文界面、macOS、Linux | 尚未验证 |

通用安装器适配 Python 2 / 3、Qt 5 / 6，不依赖 Maya 的中文菜单文字。**插件自身界面目前为中文，没有语言切换。**

默认“局部曲面”松弛沿附近连通曲面调整，不自动寻找所需外层；已贴错层时先拖点纠正。拖点和“视角最前层”模式使用当前视角的首个 Live 命中面，可能跨层。重合面、自相交和横跨深槽的大面仍可能有歧义。

使用可编辑多边形网格，低模法线朝外。GPU Cache、NURBS、实例、引用或带变形器的低模不在支持范围内。查询依据实际多边形数据，而非平滑预览。首次高模索引或几何变化后可能短暂停顿，未变化的查询会缓存。设置保留到当前会话结束。

## 排错与卸载

安装错误见脚本编辑器及系统临时目录中的 `HTools_QuadDrawThrough_install.log`。松弛没有效果时，检查独立开关、原生松弛模式和锁边界设置。

卸载：切到 **QD OFF**，移除工具架按钮，退出 Maya，再删除安装目录及不需要的备份，自行移除绑定的快捷键。撤销队列仍含辅助笔画时不要强制卸载撤销插件。

## 源码与许可证

- `qd_through/`：可阅读的运行源码。
- `install.py`、`HTools_QuadDrawThrough_Install_v10.py`：源码安装入口，使用时保持完整目录结构。
- `package_release.py`：用 Python 3.8+ 重建通用 MEL 和源码 ZIP。
- [验证记录](docs/VALIDATION.md) · [开发说明](docs/DEVELOPMENT.md) · [参与贡献](CONTRIBUTING.md) · [上传 GitHub](docs/PUBLISHING.md) · [版本记录](CHANGELOG.md)。

Copyright (c) 2026 HTools contributors。采用 [MIT 许可证](LICENSE)。不分发 Maya 及其附带依赖，本项目不隶属于 Autodesk。
