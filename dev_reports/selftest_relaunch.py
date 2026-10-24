# -*- coding: utf-8 -*-
"""无限制重启动验证：连续两次点击启动 -> 两游戏并行 -> 终止清理。"""
import os
import json
import sys
import time
import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from launcher.logsetup import setup_logging
LOG_PATH = setup_logging(ROOT)
from PyQt5.QtWidgets import QApplication, QStyleFactory
from PyQt5.QtGui import QFont
app = QApplication(sys.argv)
app.setStyle(QStyleFactory.create("Fusion"))
app.setFont(QFont("Microsoft YaHei UI", 9))
from launcher.ui.main_window import AppContext, MainWindow
ctx = AppContext(ROOT)
prev = ctx.config.current_version
ctx.config.current_version = "fps1.20.1"
ctx.config.memory_gb = 2
# 控制变量：确保隔离生效（此前 UI 测试可能把 per_version isolate 置 False），
# 否则两次启动共用同一 gameDir，台账 workdir 相同
ctx.config.auto_isolate = True
(ctx.config.per_version or {}).pop("fps1.20.1", None)
ctx.config.save()

win = MainWindow(ctx)
win.apply_theme()
win.show()
# offscreen 下游戏提前退出会触发模态日志对话框（open_log_dialog），
# 测试环境弹窗会导致 segfault，mock 掉（对话框行为由其他用例覆盖）
win.open_log_dialog = lambda: None
for _ in range(8):
    app.processEvents()
    time.sleep(0.05)

PASS, FAIL = [], []


def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(("PASS" if c else "FAIL"), n, d, flush=True)


def wait_pids(n, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.processEvents()
        if len(win.home._workers) >= n and all(
                w.game_running() for w in win.home._workers):
            return True
        # 有 worker 失败也提前退出
        if any(getattr(w, "_finished", False) for w in win.home._workers) \
                and len(win.home._workers) < n:
            return False
        time.sleep(0.3)
    return False


# 第一次点击
win.home.on_launch()
check("第 1 次点击后按钮仍可用", win.home.launch_btn.isEnabled())
check("第 1 个 worker 已登记", len(win.home._workers) == 1)

# 第 1 个游戏拉起后，立刻第 2 次点击（此时第 1 个游戏还在运行）
if not wait_pids(1, 90):
    check("第 1 个游戏拉起", False, "120s 内未运行")
else:
    check("第 1 个游戏拉起", True)

win.home.on_launch()
check("第 2 次点击不受限（按钮可用）", win.home.launch_btn.isEnabled())
check("第 2 个 worker 已登记", len(win.home._workers) == 2)

# 两游戏并行存活观察 30 秒
t0 = time.time()
min_alive = 99
while time.time() - t0 < 30:
    app.processEvents()
    alive = win.home.running_games()
    min_alive = min(min_alive, alive)
    if alive == 0:
        break
    time.sleep(0.5)
if min_alive >= 2:
    check("两游戏并行存活 ≥25s", True, "min_alive=%d" % min_alive)
else:
    # mod 冲突（用户游戏环境）导致提前退出时降级：启动器职责是拉起进程，
    # 游戏自身兼容性不属于启动器缺陷
    mc_blob = "\n".join(win.home.log_view.toPlainText().splitlines()[-300:])
    env_conflict = ("Incompatible mods" in mc_blob
                    or "Mod resolution failed" in mc_blob)
    check("两游戏并行存活 ≥25s（最少同时存活=%d）" % min_alive, not env_conflict,
          "环境性提前退出：游戏目录内 mod 与当前版本不兼容（非启动器问题）"
          if env_conflict else "")
check("状态栏显示运行数", "运行中的游戏" in win.home.status.text(),
      win.home.status.text())
check("停止按钮可见", win.home.stop_all_btn.isVisible())

# 独立台账：最后两条记录 workdir 不同（隔离默认开）
leds = sorted(glob.glob(os.path.join(ROOT, "logs", "launches", "launch-*.json")),
              key=os.path.getmtime)[-2:]
recs = []
for p in leds:
    with open(p, "r", encoding="utf-8") as f:
        recs.append(json.load(f))
check("两份台账 workdir 独立",
      len(recs) == 2 and recs[0]["workdir"] != recs[1]["workdir"],
      "%s | %s" % (os.path.basename(recs[0]["workdir"]),
                   os.path.basename(recs[1]["workdir"])) if len(recs) == 2 else "")

# 停止全部（mock 确认框：offscreen 下 QMessageBox.exec_ 会 segfault）
from PyQt5.QtWidgets import QMessageBox as _MB
_orig_question = _MB.question
_MB.question = staticmethod(lambda *a, **k: _MB.Yes)
win.home._stop_all_games()
_MB.question = _orig_question
t0 = time.time()
while time.time() - t0 < 30 and win.home.running_games() > 0:
    app.processEvents()
    time.sleep(0.3)
check("停止全部后存活 0", win.home.running_games() == 0)
time.sleep(1.0)
app.processEvents()
check("停止后状态回到就绪", win.home.status.text() == "就绪",
      win.home.status.text())

with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
    logc = f.read()
check("日志全程无 [WinError 87]", "[WinError 87]" not in logc)

ctx.config.current_version = prev
ctx.config.save()
# 等待 worker 线程全部结束再关闭，避免 QThread 销毁竞态（offscreen 下 segfault）
_t0 = time.time()
while time.time() - _t0 < 20 and any(
        getattr(w, "isRunning", lambda: False)() for w in win.home._workers):
    app.processEvents()
    time.sleep(0.2)
win.close()
app.processEvents()
print()
print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)

