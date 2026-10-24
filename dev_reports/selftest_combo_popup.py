# -*- coding: utf-8 -*-
"""验证：QComboBox 弹窗白框修复 + SpinBox/滚动条去箭头。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QApplication, QComboBox, QSpinBox, QScrollArea, QStyleFactory,
    QStyle, QStyleOptionSlider, QLabel, QVBoxLayout, QWidget,
)
from PyQt5.QtGui import QFont, QPalette
from PyQt5.QtCore import Qt

from launcher.ui.main_window import AppContext, MainWindow
from launcher.ui.theme import build_qss, current_palette, style_combo_popup

FAILS = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print("[%s] %s%s" % (tag, name, (" | " + str(detail)) if detail else ""))
    if not cond:
        FAILS.append(name)


def px(img, x, y):
    p = img.pixel(x, y)
    return ((p >> 16) & 255, (p >> 8) & 255, p & 255)


app = QApplication(sys.argv)
app.setStyle(QStyleFactory.create("Fusion"))
app.setFont(QFont("Microsoft YaHei UI", 9))
ctx = AppContext(os.getcwd())

# ============ 1. QComboBox popup 主题化（明暗双主题） ============
for mode in ("dark", "light"):
    ctx.config.theme_mode = mode
    p = current_palette("#4C5FE8", mode == "dark")
    card = tuple(int(p["card"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    combo = QComboBox()
    combo.addItems(["离线模式（当前）", "设备代码流（暂不支持）", "微软登录（暂不支持）"])
    combo.resize(240, 34)
    combo.show()
    style_combo_popup(combo, p)
    app.processEvents()

    combo.showPopup()
    app.processEvents()
    view = combo.view()
    container = view.parent()
    cimg = container.grab().toImage()
    vimg = view.grab().toImage()

    # 外框容器圆角区（原来露原生白底的位置；避开选中项区域）
    edge = px(cimg, 2, cimg.height() - 3)
    check("%s popup 外框底部边缘为 card 色（非白）" % mode,
          edge == card, "edge=%s card=%s" % (edge, card))
    # view 非选中区背景（底部空白）
    vbg = px(vimg, vimg.width() // 2, vimg.height() - 3)
    check("%s popup 列表背景为 card 色" % mode,
          vbg == card, "bg=%s" % (vbg,))
    # view 有内联样式且含 item/selected 规则
    vs = view.styleSheet()
    check("%s popup view 已设内联样式（item+selected+scrollbar）" % mode,
          "::item" in vs and "::item:selected" in vs and "QScrollBar" in vs)
    check("%s popup 外框容器已设内联样式" % mode,
          p["card"].lower() in container.styleSheet().lower())
    # 选中项背景：palette.Highlight 已被改写为 selected_bg
    sel = tuple(int(p["selected_bg"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    check("%s popup 选中项背景为 selected_bg" % mode,
          tuple(view.palette().color(QPalette.Highlight).getRgb()[:3]) == sel,
          "hl=%s want=%s" % (view.palette().color(QPalette.Highlight).name(), sel))
    found_sel = False
    for y in range(2, vimg.height() - 2):
        for x in range(2, vimg.width() - 2, 3):
            if px(vimg, x, y) == sel:
                found_sel = True
                break
        if found_sel:
            break
    check("%s popup 选中区像素为 selected_bg" % mode, found_sel,
          "sel=%s" % (sel,))
    combo.hidePopup()
    combo.close()

# ============ 2. SpinBox 无箭头（明暗双主题） ============
for mode in ("dark", "light"):
    ctx.config.theme_mode = mode
    app.setStyleSheet(build_qss("#4C5FE8", dark=(mode == "dark")))
    spin = QSpinBox()
    spin.setRange(1, 64)
    spin.setValue(8)
    spin.resize(160, 34)
    spin.show()
    app.processEvents()

    # 用 style 查询 up/down 按钮矩形：高度应为 0（箭头区被隐藏）
    st = app.style()
    opt = QStyleOptionSlider()
    opt.initFrom(spin)
    opt.rect = spin.rect()
    up = st.subControlRect(QStyle.CC_SpinBox, opt, QStyle.SC_SpinBoxUp, spin)
    dn = st.subControlRect(QStyle.CC_SpinBox, opt, QStyle.SC_SpinBoxDown, spin)
    check("%s SpinBox up-button 区域高度为 0" % mode, up.height() == 0,
          "rect=%dx%d" % (up.width(), up.height()))
    check("%s SpinBox down-button 区域高度为 0" % mode, dn.height() == 0,
          "rect=%dx%d" % (dn.width(), dn.height()))

    # 像素兜底：右侧 20px 区域不应有 text 色三角形实心像素
    img = spin.grab().toImage()
    txt = tuple(int(p2["text"].lstrip("#")[i:i + 2], 16)
                for p2 in [current_palette("#4C5FE8", mode == "dark")]
                for i in (0, 2, 4))
    right_arrow_pixels = 0
    for y in range(2, img.height() - 2):
        for x in range(img.width() - 20, img.width() - 2):
            c = px(img, x, y)
            if c == txt:
                right_arrow_pixels += 1
    check("%s SpinBox 右侧无 text 色箭头像素" % mode, right_arrow_pixels == 0,
          "px=%d" % right_arrow_pixels)
    spin.close()

# ============ 3. QScrollBar 无箭头 + 可见（不用滚轮替换） ============
for mode in ("dark", "light"):
    ctx.config.theme_mode = mode
    app.setStyleSheet(build_qss("#4C5FE8", dark=(mode == "dark")))
    inner = QWidget()
    lay = QVBoxLayout(inner)
    for i in range(40):
        lay.addWidget(QLabel("条目 %d" % i))
    sa = QScrollArea()
    sa.setWidget(inner)
    sa.resize(300, 200)
    sa.show()
    app.processEvents()

    sb = sa.verticalScrollBar()
    check("%s 滚动条可见（不用滚轮替换）" % mode,
          sb.isVisible() and sb.width() >= 8,
          "visible=%s w=%d" % (sb.isVisible(), sb.width()))

    st = app.style()
    opt = QStyleOptionSlider()
    opt.initFrom(sb)
    opt.orientation = Qt.Vertical
    add = st.subControlRect(QStyle.CC_ScrollBar, opt,
                            QStyle.SC_ScrollBarAddLine, sb)
    sub = st.subControlRect(QStyle.CC_ScrollBar, opt,
                            QStyle.SC_ScrollBarSubLine, sb)
    # 高度为 0 = 箭头按钮区被收掉（箭头不可见）；宽度是 subcontrol 占位，无所谓
    check("%s 滚动条 add-line 区域高度为 0（无下箭头）" % mode,
          add.height() == 0, "rect=%dx%d" % (add.width(), add.height()))
    check("%s 滚动条 sub-line 区域高度为 0（无上箭头）" % mode,
          sub.height() == 0, "rect=%dx%d" % (sub.width(), sub.height()))

    # 像素兜底：滚动条顶部/底部边缘无实心箭头像素（箭头若残留会是深色）
    sbi = sb.grab().toImage()
    txt = current_palette("#4C5FE8", mode == "dark")["text"]
    txtc = tuple(int(txt.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    arrow_like = 0
    for y in (0, 1, sbi.height() - 2, sbi.height() - 1):
        for x in range(sbi.width()):
            if px(sbi, x, y) == txtc:
                arrow_like += 1
    check("%s 滚动条上下边缘无 text 色箭头像素" % mode, arrow_like == 0,
          "px=%d" % arrow_like)
    sa.close()

# ============ 4. 主窗口 apply_theme 自动刷新全部 combo popup ============
ctx.config.theme_mode = "dark"
win = MainWindow(ctx)
win.apply_theme()
win.resize(980, 640)
win.show()
app.processEvents()
from PyQt5.QtWidgets import QComboBox as _CB
combos = win.findChildren(_CB)
check("主窗口存在 QComboBox 且全部已打内联样式",
      len(combos) > 0 and all(c.view().styleSheet() for c in combos),
      "count=%d" % len(combos))
win.close()

print()
if FAILS:
    print("RESULT: %d FAILED -> %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("RESULT: ALL PASS")
