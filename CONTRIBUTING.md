# Contributing / 参与贡献

English and Chinese issues / pull requests are welcome.

- Report Maya version, OS, UI language, relevant tool settings, reproduction steps and the complete traceback. Prefer a minimal synthetic scene without private assets.
- Keep runtime and installer code compatible with Python 2.7 / 3; test behavior changes in isolated Maya processes.
- Update both READMEs when behavior changes. Rebuild the generated MEL with `python package_release.py`.
- Contributions use the project's [MIT License](LICENSE). Include only code and assets you may contribute.

欢迎中文或英文问题和 Pull Request。

- 附 Maya 版本、系统、界面语言、相关设置、复现步骤和完整报错；优先使用无私人资产的最小测试场景。
- 运行代码和安装入口保持 Python 2.7 / 3 兼容，在独立 Maya 进程验证行为修改。
- 同步维护中英文说明，并运行 `python package_release.py` 重建 MEL。
- 贡献按 [MIT 许可证](LICENSE)发布，仅提交有权提供的代码与资产。

[Development / 开发说明](docs/DEVELOPMENT.md)
