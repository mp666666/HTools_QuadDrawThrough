# Development / 开发说明

## Build / 打包

Use Python 3.8+ from the repository root; Maya is not required.
在仓库根目录使用 Python 3.8+，不需要启动 Maya。

```console
python package_release.py
```

Refreshes the root universal MEL and writes the MEL, source ZIP and `SHA256SUMS.txt` into `dist/`. Use `--output DIRECTORY` for another destination. Packaging uses an explicit file allowlist and fixed ZIP metadata; test output and local settings are excluded.

会更新根目录通用 MEL，并将 MEL、源码 ZIP 和校验文件写入 `dist/`。可用 `--output` 更改输出位置。打包使用文件白名单和固定 ZIP 元数据，不带入测试输出和本机配置。

## Tests / 测试

```console
python tests/test_install.py
mayapy tests/test_maya.py
```

The first command needs only Python. The second uses the Maya version's **mayapy**, starts standalone and creates synthetic scenes. Python 2.7 additionally needs the test-only dependencies below; users of the plugin do not need them.

第一项只需要 Python；第二项使用对应 Maya 的 mayapy，在独立进程创建测试场景。Python 2.7 额外需要以下测试依赖，插件使用者无需安装。

```console
mayapy -m pip install --target tests/_output/vendor -r tests/requirements-python2.txt
```

If old mayapy lacks pip, prepare these packages with a compatible Python 2.7 environment. Output defaults to `tests/_output/`; `HTOOLS_TEST_OUTPUT` can override it, with dependencies in its `vendor` subdirectory.

旧 mayapy 没有 pip 时，用兼容的 Python 2.7 环境准备依赖。输出默认为 `tests/_output/`，可用 `HTOOLS_TEST_OUTPUT` 更改；依赖放在相应的 `vendor` 子目录。

## GUI checks / GUI 检查

**Do not import these suites into a working scene.** The launcher uses a separate Maya process and isolated profile; suites create scenes, install the plugin, then exit.

**不要导入正在工作的场景。** 启动器使用独立 Maya 进程和隔离配置；测试会创建场景、安装插件，结束后退出。

```console
python tests/launch_maya_tests.py --maya "PATH_TO_MAYA_EXECUTABLE" --suite installer
python tests/launch_maya_tests.py --maya "PATH_TO_MAYA_EXECUTABLE" --suite cold-start
python tests/launch_maya_tests.py --maya "PATH_TO_MAYA_EXECUTABLE" --suite gui
```

Replace the placeholder with the actual Maya executable. Run installer before cold-start with the same executable, `--output` and `--language`. Optional: `--language en_US`, `--output DIRECTORY`, `--timeout 240`. Reports record actual UI language. `HTOOLS_TEST_PACKAGE` optionally selects a generated source ZIP for the GUI suite instead of the checkout.

占位符换成 Maya 可执行文件路径。先运行 installer，再以相同程序、输出目录和语言运行 cold-start。可指定 `--language en_US`、`--output DIRECTORY`、`--timeout 240`。报告记录实际界面语言；设置 `HTOOLS_TEST_PACKAGE` 可让 GUI 检查生成的源码 ZIP。

Runtime and installer code must support Python 2.7 / 3. Builder and launcher use Python 3.8+. Edit Python source and rebuild the MEL; do not hand-edit the encoded payload.

运行代码和安装入口兼容 Python 2.7 / 3，打包和启动器使用 Python 3.8+。修改 Python 源码后重新生成 MEL，不直接编辑内置编码内容。
