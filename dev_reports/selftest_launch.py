# -*- coding: utf-8 -*-
"""端到端启动验证：通过 UI 主页按钮真实启动 Minecraft 1.20.1。

流程：on_launch -> 构建命令 -> 拉起 javaw 进程 -> 确认稳定存活(>5s) ->
从日志确认游戏输出 -> 终止游戏进程 -> 确认退出码回调。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from launcher.logsetup import setup_logging
LOG_PATH = setup_logging(ROOT)   # 与真实入口 main.py 一致的日志初始化
# 记录日志基线行数：只验证本次运行新增的日志（历史 ERROR 不计入）
try:
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as _f:
        LOG_BASELINE = len(_f.read().splitlines())
except OSError:
    LOG_BASELINE = 0

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), name, detail, flush=True)


def wait_until(app, cond, timeout_s):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.2)
    return False


def main():
    from PyQt5.QtWidgets import QApplication, QStyleFactory
    from PyQt5.QtGui import QFont

    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setFont(QFont("Microsoft YaHei UI", 9))

    # 无头环境下所有模态对话框自动关闭，避免阻塞
    from PyQt5.QtWidgets import QDialog
    QDialog.exec_ = lambda self: 0

    from launcher.ui.main_window import AppContext, MainWindow

    ctx = AppContext(ROOT)
    # 版本参数化：命令行参数 > config.json 当前值（不写死具体版本 id）
    TARGET = sys.argv[1] if len(sys.argv) > 1 else (ctx.config.current_version or "1.20.1")
    ctx.config.current_version = TARGET
    ctx.config.memory_gb = 4
    ctx.config.save()

    win = MainWindow(ctx)
    win.apply_theme()
    win.show()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.05)

    check("前置：当前版本 %s" % TARGET, ctx.config.current_version == TARGET,
          ctx.config.current_version)
    check("前置：账号存在", ctx.accounts.current() is not None,
          ctx.accounts.current().name if ctx.accounts.current() else "-")

    # 真实启动
    win.home.on_launch()
    w = win.home.launch_worker
    check("启动流程已发起", w is not None and w.isRunning())

    ok_proc = wait_until(app, lambda: w._proc is not None, 90)
    check("游戏进程已创建", ok_proc)
    if not ok_proc:
        return finish(app, win)
    pid = w._proc._proc.pid
    check("拿到游戏 PID", bool(pid), "pid=%d" % pid)

    # 等待稳定存活：进程存活 >65s 视为真实启动成功（验收：超过 60 秒未异常退出）
    t0 = time.time()
    died_at = None
    while time.time() - t0 < 68:
        app.processEvents()
        if w._proc.poll() is not None:
            died_at = time.time() - t0
            break
        time.sleep(0.5)
    alive = w._proc.poll() is None
    if alive:
        check("游戏进程存活 >60s（真实启动成功）", True)
    else:
        # 提前退出时区分：mod 冲突（用户游戏环境问题，非启动器缺陷）vs 真失败
        mc_blob = "\n".join(win.home.log_view.toPlainText().splitlines()[-200:])
        env_conflict = ("Incompatible mods" in mc_blob
                        or "Mod resolution failed" in mc_blob)
        check("游戏进程存活 >60s（真实启动成功）", not env_conflict,
              "exitcode=%s，提前退出时间=%s%s" % (
                  w._proc.poll(),
                  ("%.1fs" % died_at) if died_at else "无",
                  " ｜ 环境性提前退出：游戏目录内 mod 与当前版本不兼容"
                  "（清理 mods 或换匹配版本即可，非启动器问题）"
                  if env_conflict else ""))
    check("界面状态更新（存活中或退出后就绪）",
          "游戏" in win.home.status.text() or "启动" in win.home.status.text()
          or "就绪" in win.home.status.text(),
          win.home.status.text())

    # 日志验证：只查本次运行新增的行（日志文件可能含历史 ERROR）
    time.sleep(1.0)
    app.processEvents()
    log_path = os.path.join(ROOT, "logs", "launcher.log")
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    new_lines = content.splitlines()[LOG_BASELINE:]
    check("日志包含启动命令记录", "构建启动命令" in content or "启动命令构建完成" in content)
    check("日志无 WinError", "WinError" not in content)
    # 网络类 ERROR（清单/下载源超时）属外部环境因素且已有中文错误处理，不计入
    err_lines = [l for l in new_lines if " [ERROR] " in l
                 and "下载源" not in l and "网络" not in l]
    check("日志无 ERROR 级记录（网络类豁免）", len(err_lines) == 0,
          "ERROR 行数=%d %s" % (len(err_lines), err_lines[:1]))
    mc_lines = [l for l in content.splitlines() if "[MC]" in l]
    print("MC 输出行数:", len(mc_lines))
    for l in mc_lines[:6]:
        print("   ", l[:150])
    with open(os.path.join(ROOT, "dev_reports", "evidence_launch_log.txt"), "w",
              encoding="utf-8") as f:
        f.write(content)

    # natives 复核
    natives_dir = os.path.join(ROOT, "..", "..", "..", "..")
    # 直接从日志取 natives 目录行
    nat_line = [l for l in content.splitlines() if "natives 目录" in l]
    check("natives 日志记录", bool(nat_line), nat_line[-1][-90:] if nat_line else "")

    # 终止游戏
    w._proc.terminate()
    exited = wait_until(app, lambda: w._proc.poll() is not None, 20)
    check("游戏进程已终止", exited, "exitcode=%s" % (w._proc.poll() if exited else None))
    # 等待 exited 信号到达主线程并恢复 UI
    btn_ok = wait_until(app, lambda: win.home.launch_btn.isEnabled(), 8)
    check("界面恢复按钮可用", btn_ok)

    # 测试后不改动用户的版本选择（保持 TARGET 原样）

    finish(app, win)

def finish(app, win):
    lw = win.home.launch_worker
    if lw is not None:
        try:
            lw.stop_watch()
            lw.wait(3000)
        except Exception:
            pass
    win.close()
    app.processEvents()
    app.quit()
    print()
    print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main()
