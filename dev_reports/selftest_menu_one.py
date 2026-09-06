# -*- coding: utf-8 -*-
"""单版本取证：fps1.20.1 隔离启动 -> 主菜单 -> 截图 -> 台账 -> 终止。"""
import os, sys, time, json
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "selftest_menu.py"),
     encoding="utf-8").read().split('def main()')[0])  # 复用函数定义

from PyQt5.QtWidgets import QApplication, QStyleFactory
from PyQt5.QtGui import QFont
app = QApplication(sys.argv)
app.setStyle(QStyleFactory.create("Fusion"))
app.setFont(QFont("Microsoft YaHei UI", 9))
from launcher.ui.main_window import AppContext
ctx = AppContext(ROOT)

res, w = launch_one(app, ctx, "fps1.20.1", isolate=True, tag="fps1201",
                    menu_timeout=220)
finish_one(app, w, res, "fps1201")

with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
    logc = f.read()
check("日志全程无 [WinError 87]", "[WinError 87]" not in logc)

# 记录截图判据摘要
if res["shot"]:
    with open(res["shot"], "rb") as f:
        head = f.read(8)
    check("截图文件为有效 PNG", head.startswith(b"\x89PNG"), res["shot"])

print()
print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
