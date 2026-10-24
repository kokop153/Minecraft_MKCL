# -*- coding: utf-8 -*-
"""抓取 QComboBox popup 暗黑/明亮主题渲染图，供人工确认白框已消除。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication, QComboBox, QStyleFactory
from PyQt5.QtGui import QFont

from launcher.ui.theme import current_palette, style_combo_popup, build_qss

app = QApplication(sys.argv)
app.setStyle(QStyleFactory.create("Fusion"))
app.setFont(QFont("Microsoft YaHei UI", 9))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screens")
os.makedirs(out, exist_ok=True)

for mode, dark in (("dark", True), ("light", False)):
    app.setStyleSheet(build_qss("#4C5FE8", dark=dark))
    p = current_palette("#4C5FE8", dark)
    combo = QComboBox()
    combo.addItems(["离线模式（当前）", "设备代码流（暂不支持）", "微软登录（暂不支持）"])
    combo.resize(240, 34)
    combo.move(20, 20)
    combo.show()
    style_combo_popup(combo, p)
    app.processEvents()
    combo.showPopup()
    app.processEvents()
    view = combo.view()
    container = view.parent()
    img = container.grab()
    path = os.path.join(out, "combo_popup_%s.png" % mode)
    img.save(path)
    print("saved:", path, img.width(), "x", img.height())
    combo.hidePopup()
    combo.close()
