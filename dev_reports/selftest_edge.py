# -*- coding: utf-8 -*-
"""边界测试：不存在版本 / 空 Java / Java 路径无效 / 空参数 / 空命令 / 无效 workdir。

验收要求：以上场景全部得到可读中文提示，绝不抛系统级 WinError。
"""
import os
import sys
import io
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from launcher.logsetup import setup_logging
LOG_PATH = setup_logging(ROOT)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), name, "|", detail, flush=True)


def expect_error(name, fn, *keywords):
    try:
        fn()
        check(name, False, "未抛出异常")
        return None
    except Exception as e:
        msg = str(e)
        ok = any(k in msg for k in keywords) and "WinError" not in msg
        check(name, ok, msg[:110])
        return msg


def main():
    from launcher.errors import LauncherError
    from launcher.launch import (
        build_launch_command, launch_game, resolve_java_for_launch,
    )
    import launcher.java_utils as ju

    GAME_DIR = r"F:\.minecraft"

    # ---- 1. 不存在的版本 id ----
    expect_error(
        "E1 不存在版本 id -> 可读提示",
        lambda: build_launch_command(GAME_DIR, "不存在版本xyz", "java"),
        "找不到版本",
    )

    # ---- 2. 空 Java 路径（自动选择路径）在真实环境下成功解析 ----
    jp = resolve_java_for_launch(GAME_DIR, "fps1.20.1", "")
    check("E2 空 Java -> 自动解析成功且非空", bool(jp) and os.path.isfile(jp), jp)

    # ---- 3. 空 Java + 系统无任何 Java（monkeypatch） ----
    orig = ju.find_javas
    ju.find_javas = lambda extra_paths=None: []
    expect_error(
        "E3 系统无 Java -> 可读提示（无 WinError）",
        lambda: resolve_java_for_launch(GAME_DIR, "fps1.20.1", ""),
        "未找到可用的 Java", "Java",
    )
    ju.find_javas = orig

    # ---- 4. 手动 Java 路径指向不存在的文件 ----
    expect_error(
        "E4 Java 路径无效 -> 可读提示",
        lambda: resolve_java_for_launch(GAME_DIR, "fps1.20.1", r"C:\nonexistent\javaw.exe"),
        "Java 路径无效",
    )

    # ---- 5. command[0] 为空串（昨日 WinError 87 场景，现已拦截） ----
    bad_cmd = {"command": ["", "-Xmx4G"], "workdir": GAME_DIR}
    expect_error(
        "E5 空 Java 串进命令 -> 可读拦截（原 WinError 87 场景）",
        lambda: launch_game(bad_cmd),
        "未获取到 Java 路径",
    )

    # ---- 6. 命令中含空参数 ----
    bad_cmd2 = {"command": ["C:\\Windows\\System32\\cmd.exe", "-Xmx4G", "", "-cp"],
                "workdir": GAME_DIR}
    expect_error(
        "E6 命令含空参数 -> 可读拦截",
        lambda: launch_game(bad_cmd2),
        "参数为空", "空参数",
    )

    # ---- 7. workdir 不存在 ----
    good_head = ["C:\\Windows\\System32\\cmd.exe"]
    bad_cmd3 = {"command": good_head + ["a"], "workdir": r"Z:\不存在目录\abc"}
    expect_error(
        "E7 工作目录不存在 -> 可读提示",
        lambda: launch_game(bad_cmd3),
        "工作目录不存在",
    )

    # ---- 8. LaunchWorker 端到端：不存在版本 -> fail 信号为可读中文 ----
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    from launcher.ui.workers import LaunchWorker
    result = {"fail": None}
    w = LaunchWorker(
        game_dir=GAME_DIR, folder="不存在版本xyz", java_path="",
        memory_gb=4, username="kokop", uuid="x", user_type="legacy",
        jvm_extra="", width=854, height=480, isolate_dir=False,
    )
    w.fail.connect(lambda m: result.__setitem__("fail", m))
    w.start()
    import time
    t0 = time.time()
    while time.time() - t0 < 60 and result["fail"] is None:
        app.processEvents()
        time.sleep(0.2)
    msg = result["fail"] or ""
    check("E8 Worker 端到端可读报错", bool(msg) and "找不到版本" in msg and "WinError" not in msg,
          msg[:110])

    # ---- 汇总 ----
    evidence = {"pass": PASS, "fail": FAIL}
    with open(os.path.join(ROOT, "dev_reports", "evidence_edge_cases.json"), "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print()
    print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main()
