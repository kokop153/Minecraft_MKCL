# -*- coding: utf-8 -*-
"""验证「进程页点行窗口爆炸」修复 + 全局宽度炸弹扫描。

检查项：
1. 选中带 600+ 字符命令行的行 → 窗口 minimumSize 恒为 (900,580)、宽不被顶爆
2. 全页面控件扫描：无任何控件的 minimumSizeHint 宽度 > 900（窗口最小宽）
3. ElideLabel 行为：长文本省略显示 + tooltip 全文 + resize 重新省略
4. 五页 render 冒烟（明暗双主题）
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from PyQt5.QtWidgets import QApplication, QLabel, QTableWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication

from launcher.ui.main_window import AppContext, MainWindow
from launcher.ui.theme import ElideLabel, build_qss

FAILS = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print("[%s] %s%s" % (tag, name, (" | " + str(detail)) if detail else ""))
    if not cond:
        FAILS.append(name)


app = QApplication(sys.argv)
ctx = AppContext(os.getcwd())
# 控制变量：固定非最大化启动，避免 config 里残留的 maximized=True
# 触发 showMaximized 干扰宽度断言（offscreen 下时序不稳定）
_w = dict(ctx.config.window or {})
_w.update({"maximized": False, "width": 980, "height": 640})
ctx.config.window = _w
ctx.config.save()

# ============ 1. 明暗双主题下的窗口尺寸稳定性 ============
for mode in ("dark", "light"):
    ctx.config.theme_mode = mode
    win = MainWindow(ctx)
    win.apply_theme()          # 与 main.py 启动流程一致：构造后应用 QSS
    win.resize(980, 640)
    win.show()
    app.processEvents()

    base_w = win.width()
    base_min = win.minimumSize()
    check("%s 初始窗口宽 980（配置恢复 + 未被顶爆）" % mode,
          base_w == 980, "w=%d" % base_w)
    check("%s minimumSize=(900,580)" % mode,
          (base_min.width(), base_min.height()) == (900, 580),
          "min=(%d, %d)" % (base_min.width(), base_min.height()))

    # --- 模拟：选中带 600 字符命令行的行（爆炸场景复现） ---
    pp = win.process_page
    long_cl = " ".join(["-Xmx4G"] * 200)  # ~1200 字符命令行
    fake = {"pid": 4242, "cmdline": long_cl, "mem_mb": 1024,
            "started": "2026-10-24 12:00", "version": "1.20.1"}
    pp._rows = [fake]
    pp.table.setRowCount(1)
    it = QTableWidgetItem("4242")
    it.setData(Qt.UserRole, fake)
    pp.table.setItem(0, 0, it)
    pp.table.setCurrentItem(it)          # 触发 itemSelectionChanged → _show_detail
    app.processEvents()

    check("%s 选中长命令行行后窗口宽不变（不爆炸）" % mode,
          win.width() == base_w, "w=%d base=%d" % (win.width(), base_w))
    check("%s 选中长命令行行后 minimumSize 仍 (900,580)" % mode,
          (win.minimumSize().width(), win.minimumSize().height()) == (900, 580),
          "min=(%d, %d)" % (win.minimumSize().width(),
                            win.minimumSize().height()))

    # detail 标签：显示省略文本、tooltip 是全文、宽度不炸
    d = pp.detail
    check("%s detail 已省略（不含 1200 字符全文）" % mode,
          len(d.text()) < len(long_cl), "len=%d" % len(d.text()))
    check("%s detail tooltip 含完整命令行" % mode, long_cl in (d.toolTip() or ""))
    check("%s detail minHint 宽 < 900" % mode,
          d.minimumSizeHint().width() < 900,
          "minHint=%d" % d.minimumSizeHint().width())

    # --- 切到设置页触发 _refresh_paths（长路径串） ---
    win.goto("settings")
    app.processEvents()
    sp = win.settings
    sp._refresh_paths()
    app.processEvents()
    check("%s 设置页路径串后 minimumSize 仍 (900,580)" % mode,
          (win.minimumSize().width(), win.minimumSize().height()) == (900, 580),
          "min=(%d, %d)" % (win.minimumSize().width(),
                            win.minimumSize().height()))
    check("%s path_hint minHint 宽 < 900" % mode,
          sp.path_hint.minimumSizeHint().width() < 900,
          "minHint=%d" % sp.path_hint.minimumSizeHint().width())

    # --- 版本页（isolate 短标签） ---
    win.goto("versions")
    app.processEvents()
    vp = win.versions_page
    check("%s isolate_cb minHint 宽 < 900" % mode,
          vp.isolate_cb.minimumSizeHint().width() < 900,
          "minHint=%d" % vp.isolate_cb.minimumSizeHint().width())
    check("%s isolate_cb 标签短且有 tooltip" % mode,
          len(vp.isolate_cb.text()) <= 20 and bool(vp.isolate_cb.toolTip()),
          repr(vp.isolate_cb.text()))

    win.close()

# ============ 2. 全局控件宽度炸弹扫描（暗黑主题） ============
ctx.config.theme_mode = "dark"
win = MainWindow(ctx)
win.apply_theme()
win.resize(980, 640)
win.show()
app.processEvents()

for page in (win.home, win.versions_page, win.downloads,
             win.process_page, win.settings):
    name = type(page).__name__
    bombs = []

    def scan(w, _name=name, _bombs=bombs):
        for lbl in w.findChildren(QLabel):
            mw = lbl.minimumSizeHint().width()
            if mw > 900:
                _bombs.append(("%s minHint=%d text=%r" % (
                    type(lbl).__name__, mw, lbl.text()[:40])))
        # 复选框的长标签也是经典炸弹源
        from PyQt5.QtWidgets import QCheckBox
        for cb in w.findChildren(QCheckBox):
            mw = cb.minimumSizeHint().width()
            if mw > 900:
                _bombs.append("QCheckBox minHint=%d text=%r" % (
                    mw, cb.text()[:40]))

    scan(page)
    check("%s 无宽度炸弹控件(>900px)" % name, not bombs,
          "; ".join(bombs[:4]))
win.close()

# ============ 3. ElideLabel 单元行为 ============
lbl = ElideLabel("x" * 500)
lbl.resize(200, 20)
app.processEvents()
check("ElideLabel 长文本已省略", len(lbl.text()) < 500 and "…" in lbl.text(),
      "len=%d" % len(lbl.text()))
check("ElideLabel tooltip 为全文", lbl.toolTip() == "x" * 500)
lbl.resize(400, 20)
app.processEvents()
check("ElideLabel resize 后重新省略（更长）",
      "…" in lbl.text() and len(lbl.text()) < 500,
      "len=%d" % len(lbl.text()))
lbl.setText("短文本")
app.processEvents()
check("ElideLabel 短文本原样显示", lbl.text() == "短文本")
check("ElideLabel 空文本不报错", ElideLabel("").text() == "")

# ============ 4. 主题 QSS 覆盖 ElideLabel 颜色（明暗双主题） ============
from PyQt5.QtGui import QPalette
for mode, want in (("dark", "#98a2b3"), ("light", "#6b7280")):
    # 注意 build_qss 签名：(accent, dark: bool)
    app.setStyleSheet(build_qss("#4C5FE8", dark=(mode == "dark")))
    el = ElideLabel("测试文字颜色")
    el.setObjectName("subText")
    el.show()
    app.processEvents()
    c = el.palette().color(QPalette.WindowText)
    check("%s ElideLabel#subText 文字色=%s" % (mode, want),
          c.name().lower() == want, "got=%s" % c.name())
    el.close()

print()
if FAILS:
    print("RESULT: %d FAILED -> %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("RESULT: ALL PASS")
