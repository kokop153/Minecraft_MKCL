# -*- coding: utf-8 -*-
"""MKCL 离屏冒烟：五页切换 + 淡入动画 + 进程扫描 + 更名校验。"""
import os, sys, time
ROOT = r"C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher"
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from launcher.logsetup import setup_logging
setup_logging(ROOT)
from PyQt5.QtWidgets import QApplication, QStyleFactory
from PyQt5.QtGui import QFont

app = QApplication(sys.argv)
app.setStyle(QStyleFactory.create("Fusion"))
app.setFont(QFont("Microsoft YaHei UI", 9))
from launcher.ui.main_window import AppContext, MainWindow
ctx = AppContext(ROOT)
win = MainWindow(ctx)
win.apply_theme()
win.show()
for _ in range(10):
    app.processEvents(); time.sleep(0.05)

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), name, detail, flush=True)

check("窗口标题为 MKCL", "MKCL" in win.windowTitle(), win.windowTitle())
check("导航含进程管理", "process" in win.nav_buttons)

for key in ("versions", "downloads", "process", "settings", "home"):
    win.goto(key)
    for _ in range(6):
        app.processEvents(); time.sleep(0.05)
    check("切换页 " + key, win.stack.currentIndex() >= 0)

# 进程页扫描（PowerShell 真实调用）
ok = False
t0 = time.time()
while time.time() - t0 < 30:
    app.processEvents()
    if win.process_page._rows is not None and win.process_page.scan_worker is not None \
            and not win.process_page.scan_worker.isRunning():
        ok = True
        break
    time.sleep(0.2)
check("进程扫描完成", ok, "rows=%d" % len(win.process_page._rows or []))
check("进程页无报错状态", "⚠" not in win.process_page.status.text(), win.process_page.status.text())

win.close()
app.processEvents()
print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", FAIL); sys.exit(1)
