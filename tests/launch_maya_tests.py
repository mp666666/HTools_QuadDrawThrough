# SPDX-License-Identifier: MIT
# Copyright (c) 2026 HTools contributors
"""Launch destructive test suites only in a separate, isolated Maya process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SUITES = {
    "installer": ("standalone_install", "standalone_drop_*_result.json"),
    "gui": ("gui_smoke", "gui_result_*_v10.json"),
    "cold-start": ("cold_start", "cold_start_*_v10.json"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maya", required=True, type=Path, help="Full path to Maya's GUI executable")
    parser.add_argument("--suite", required=True, choices=sorted(SUITES))
    parser.add_argument("--output", type=Path, default=ROOT / "tests" / "_output")
    parser.add_argument("--language", default="en_US", choices=("en_US", "zh_CN", "ja_JP"))
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    maya = args.maya.resolve()
    if not maya.is_file():
        parser.error("Maya executable not found: " + str(maya))
    output = args.output.resolve()
    tag = hashlib.sha256(str(maya).encode("utf-8")).hexdigest()[:12] + "_" + args.language
    profile = output / "profiles" / tag
    runs = output / "runs" / tag
    profile.mkdir(parents=True, exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    # Maya may import Maya.env from the normal user profile if it is absent.
    # These directories belong only to this test launcher, including cold starts.
    for year in range(2018, 2028):
        for locale in ("", "zh_CN", "ja_JP"):
            settings = profile / str(year) / locale
            settings.mkdir(parents=True, exist_ok=True)
            (settings / "Maya.env").write_text("", encoding="ascii")
    run_dir = Path(tempfile.mkdtemp(prefix=args.suite + "_", dir=str(runs)))
    module, report_glob = SUITES[args.suite]
    startup = run_dir / "startup.mel"
    startup.write_text(
        'python("import os, sys; sys.path.insert(0, os.path.join(os.environ[\'HTOOLS_TEST_ROOT\'], \'tests\')); '
        'import ' + module + '; ' + module + '.schedule()");\n', encoding="ascii")
    env = dict(os.environ)
    # Also allow this Python 3 launcher to run from another Maya's mayapy.
    for key in ("MAYA_LOCATION", "PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH",
                "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        env.pop(key, None)
    env.update(MAYA_APP_DIR=str(profile), MAYA_SKIP_USERSETUP_PY="1",
               MAYA_UI_LANGUAGE=args.language, HTOOLS_TEST_ROOT=str(ROOT),
               HTOOLS_TEST_OUTPUT=str(run_dir), PYTHONDONTWRITEBYTECODE="1")
    options = {}
    if os.name == "nt":
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 0
        options["startupinfo"] = info
    command = [str(maya), "-noAutoloadPlugins", "-script", startup.as_posix(),
               "-log", (run_dir / "maya.log").as_posix()]
    print("Starting " + args.suite + " in an isolated profile", flush=True)
    print("Test output: " + str(run_dir), flush=True)
    with (run_dir / "stdout.log").open("wb") as stdout, (run_dir / "stderr.log").open("wb") as stderr:
        process = subprocess.Popen(command, env=env, stdout=stdout, stderr=stderr, **options)
        try:
            code = process.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            print("Test process timed out; see logs above.", file=sys.stderr)
            return 1
    reports = list(run_dir.glob(report_glob))
    if len(reports) != 1:
        print("Missing or ambiguous test report; Maya exit code: " + str(code), file=sys.stderr)
        return 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    print("Report: " + str(reports[0]))
    print("Actual UI language: " + str(report.get("ui_language", "unknown")))
    print("Passed: " + str(report.get("ok", False)))
    if not report.get("ok"):
        print(report.get("error", "See the report for failure details"), file=sys.stderr)
    return 0 if report.get("ok") and code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
