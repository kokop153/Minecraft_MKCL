# -*- coding: utf-8 -*-
"""异常场景验证：错误 Java 路径 / 损坏版本 JSON / 网络下载失败。

目标：每种异常都有中文可读错误（LauncherError/信号）且写入日志文件。
"""
import os
import sys
import json
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from launcher.logsetup import setup_logging
LOG_PATH = setup_logging(ROOT)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), name, detail, flush=True)


def main():
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)   # 全程统一 QApplication，避免 D 场景 GUI 崩溃

    from launcher.ui.workers import LaunchWorker
    from launcher.launch import build_launch_command
    from launcher.errors import LauncherError
    from launcher import meta

    result = {"fail": None, "exited": None, "stage": []}

    # ---- 场景 A：错误的 Java 路径 ----
    w = LaunchWorker(
        game_dir=r"F:\.minecraft", folder="1.20.1",
        java_path=r"C:\nonexistent\javaw.exe",
        memory_gb=4, username="kokop", uuid="43465a85-8a83-36d3-8a93-ae2ee0cc2baa",
        user_type="legacy", jvm_extra="", width=854, height=480, isolate_dir=False,
    )
    w.fail.connect(lambda m: result.__setitem__("fail", m))
    w.exited.connect(lambda c: result.__setitem__("exited", c))
    w.start()
    t0 = time.time()
    while time.time() - t0 < 60 and result["fail"] is None and result["exited"] is None:
        app.processEvents()
        time.sleep(0.2)
    check("A: 错误 Java 路径 -> 报错", result["fail"] is not None,
          str(result["fail"])[:120])
    check("A: 报错为中文且可读", result["fail"] and "Java" in str(result["fail"]),
          str(result["fail"])[:120])

    # ---- 场景 B：损坏的版本 JSON（临时目录，不污染真实目录） ----
    tmp = os.path.join(ROOT, ".testtmp", "broken")
    shutil.rmtree(os.path.join(ROOT, ".testtmp"), ignore_errors=True)
    vdir = os.path.join(tmp, "versions", "broken-ver")
    os.makedirs(vdir, exist_ok=True)
    with open(os.path.join(vdir, "broken-ver.json"), "w", encoding="utf-8") as f:
        f.write("{ 这不是合法 JSON !!")
    try:
        build_launch_command(tmp, "broken-ver", "java", memory_gb=4)
        check("B: 损坏版本 -> 抛错", False, "未抛出异常")
    except LauncherError as e:
        check("B: 损坏版本 -> 抛错", True)
        check("B: 错误信息中文可读", bool(str(e)) and ("JSON" in str(e) or "读取" in str(e)),
              str(e)[:120])
    except Exception as e:
        check("B: 损坏版本 -> 抛错（异常类型正确）", False,
              "%s: %s" % (type(e).__name__, e))

    # 不存在的版本
    try:
        build_launch_command(r"F:\.minecraft", "不存在版本xyz", "java")
        check("B2: 不存在版本 -> 抛错", False, "未抛出异常")
    except LauncherError as e:
        check("B2: 不存在版本 -> 抛错", True, str(e)[:100])
        check("B2: 错误信息含版本名", "不存在版本xyz" in str(e))

    # ---- 场景 C：网络下载失败（不可达地址，快速失败） ----
    try:
        meta.download_file("https://127.0.0.1:9/unreachable.bin",
                           os.path.join(tmp, "unreachable.bin"),
                           source="bmclapi", timeout=3, retries=1)
        check("C: 网络失败 -> 抛错", False, "未抛出异常")
    except LauncherError as e:
        check("C: 网络失败 -> 抛错", True)
        check("C: 错误信息中文可读", "下载失败" in str(e) or "无法连接" in str(e),
              str(e)[:120])

    # ---- 场景 D：UI 层错误提示路径（弹窗逻辑不卡死） ----
    from PyQt5.QtWidgets import QMessageBox
    from launcher.ui.main_window import AppContext, MainWindow
    ctx = AppContext(ROOT)
    win = MainWindow(ctx)
    win.apply_theme()
    win.show()
    for _ in range(6):
        app.processEvents()
        time.sleep(0.05)

    dialogs = []
    orig_exec = QMessageBox.exec_

    def fake_exec(self):
        dialogs.append(self.text())
        return 0

    QMessageBox.exec_ = fake_exec
    # _on_fail(w, msg)：w 需为对象（内部 setattr/成员判断），用轻量替身
    class _FakeWorker:
        _finished = False
    win.home._on_fail(_FakeWorker(), "游戏进程启动失败：系统找不到指定的文件。")
    check("D: fail 弹窗被触发且文本可读", bool(dialogs) and "找不到指定的文件" in dialogs[0],
          (dialogs[0][:80] if dialogs else "无弹窗"))
    check("D: 状态栏显示错误", "启动失败" in win.home.status.text(),
          win.home.status.text()[:100])
    QMessageBox.exec_ = orig_exec

    # ---- 日志确实记录了错误 ----
    time.sleep(0.8)
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        logc = f.read()
    check("日志：场景A启动失败已记录", "Java 路径无效" in logc)

    win.close()
    shutil.rmtree(os.path.join(ROOT, ".testtmp"), ignore_errors=True)

    print()
    print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main()
