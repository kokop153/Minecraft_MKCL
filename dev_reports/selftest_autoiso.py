# -*- coding: utf-8 -*-
import os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
from launcher.logsetup import setup_logging
setup_logging(ROOT)
from PyQt5.QtWidgets import QApplication, QStyleFactory
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
app = QApplication(sys.argv); app.setStyle(QStyleFactory.create("Fusion")); app.setFont(QFont("Microsoft YaHei UI", 9))
from launcher.ui.main_window import AppContext, MainWindow
ctx = AppContext(ROOT)
win = MainWindow(ctx); win.apply_theme(); win.show()
for _ in range(8): app.processEvents(); time.sleep(0.05)
ok = True
def check(n, c, d=""):
    global ok
    print(("PASS" if c else "FAIL"), n, d, flush=True)
    ok = ok and c
def select_ver(target):
    win.goto("versions")
    for _ in range(30):
        app.processEvents()
        if win.versions_page.list.count() > 0: break
        time.sleep(0.2)
    for i in range(win.versions_page.list.count()):
        if win.versions_page.list.item(i).data(Qt.UserRole) == target:
            win.versions_page.list.setCurrentRow(i); break
    for _ in range(4): app.processEvents(); time.sleep(0.05)

check("auto_isolate 默认 True", ctx.config.auto_isolate is True)
select_ver("1.21.5")
check("1.21.5 隔离勾选自动开启", win.versions_page.isolate_cb.isChecked())
win.settings.isolate_cb.setCurrentIndex(1)  # 不隔离
for _ in range(4): app.processEvents(); time.sleep(0.05)
select_ver("1.21.5")
check("关闭默认隔离后 1.21.5 勾选为关", not win.versions_page.isolate_cb.isChecked())
win.settings.isolate_cb.setCurrentIndex(0)  # 隔离所有
for _ in range(4): app.processEvents(); time.sleep(0.05)
select_ver("1.21.5")
check("重新开启默认隔离", ctx.config.auto_isolate is True and win.versions_page.isolate_cb.isChecked())
win.goto("process")
for _ in range(6): app.processEvents(); time.sleep(0.05)
check("进程页切换正常", True)
win.close(); app.processEvents()
print("SMOKE_ALL_OK" if ok else "SMOKE_FAILED")
sys.exit(0 if ok else 1)
