# -*- coding: utf-8 -*-
"""主窗口：PCL CE 风格 —— 无边框 + 蓝色顶栏（居中胶囊导航）+ 页面栈 + 日志查看器。"""
import os

from PyQt5.QtCore import (
    Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QAbstractAnimation, QSize,
)
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QDialog, QPlainTextEdit, QMessageBox, QFrame, QLayout,
    QGraphicsOpacityEffect, QSizeGrip,
)

from launcher.ui.home_page import HomePage
from launcher.ui.versions_page import VersionsPage
from launcher.ui.downloads_page import DownloadsPage
from launcher.ui.process_page import ProcessPage
from launcher.ui.settings_page import SettingsPage
from launcher.ui.theme import (
    build_qss, glyph_icon, GLYPHS, DEFAULT_ACCENT, LEGACY_DEFAULT_ACCENT,
    accent_dark, current_palette, style_combo_popup,
)

_PAGES = (
    ("home", "启动"),
    ("versions", "版本"),
    ("downloads", "下载"),
    ("process", "进程"),
    ("settings", "设置"),
)


class AppContext:
    """全局共享状态：配置 + 账号 + 根目录。"""

    def __init__(self, base_dir: str):
        from launcher.config import AppConfig
        from launcher.accounts import AccountStore
        self.base_dir = base_dir
        self.config = AppConfig(base_dir)
        self.accounts = AccountStore(base_dir)
        # 旧 demo 的 username 迁移为离线账号
        legacy = getattr(self.config, "_legacy_username", "")
        cur = self.accounts.current()
        if cur is None and legacy:
            migrated = self.accounts.migrate_legacy_username(legacy)
            if migrated:
                self.accounts.save()


class LogDialog(QDialog):
    def __init__(self, log_path, parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self.setWindowTitle("启动日志")
        self.resize(760, 480)
        v = QVBoxLayout(self)
        self.view = QPlainTextEdit()
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        v.addWidget(self.view, 1)
        row = QHBoxLayout()
        b_refresh = QPushButton("刷新")
        b_refresh.clicked.connect(self.reload)
        b_all = QPushButton("打开日志文件夹")
        b_all.clicked.connect(self._open_dir)
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        row.addWidget(b_refresh)
        row.addWidget(b_all)
        row.addStretch(1)
        row.addWidget(close)
        v.addLayout(row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.reload)
        self.timer.start(3000)
        self.reload()

    def reload(self):
        self.view.setPlainText(self._tail(self.log_path, 256 * 1024))
        sb = self.view.verticalScrollBar()
        sb.setValue(sb.maximum())

    @staticmethod
    def _tail(path, nbytes):
        try:
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                if size > nbytes:
                    f.seek(size - nbytes)
                data = f.read(nbytes).decode("utf-8", errors="replace")
            return data
        except OSError:
            return "(日志文件尚未生成)"

    def _open_dir(self):
        d = os.path.dirname(self.log_path)
        if os.path.isdir(d):
            os.startfile(d)


class TitleBar(QFrame):
    """PCL CE 式蓝色顶栏：标题 + 居中胶囊导航 + 窗口控制按钮；支持拖拽与双击最大化。"""

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.win = win
        self.setObjectName("topBar")
        self.setFixedHeight(48)
        self._build_ui()

    def _build_ui(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 8, 0)
        row.setSpacing(8)

        title = QLabel("MKCL")
        title.setObjectName("topTitle")
        row.addWidget(title)
        badge = QLabel("CE")
        badge.setObjectName("topBadge")
        row.addWidget(badge)
        row.addStretch(1)

        # 居中胶囊导航
        self.pills = {}
        for key, text in _PAGES:
            b = QPushButton("  " + text)
            b.setObjectName("navPill")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIconSize(QSize(14, 14))
            b.setIcon(glyph_icon(GLYPHS[key], "#FFFFFF", 13))
            b.clicked.connect(lambda _=False, k=key: self.win.goto(k))
            row.addWidget(b)
            self.pills[key] = b
        row.addStretch(1)

        b_log = QPushButton("日志")
        b_log.setObjectName("winBtn")
        b_log.setCursor(Qt.PointingHandCursor)
        b_log.clicked.connect(self.win.open_log_dialog)
        row.addWidget(b_log)

        b_min = QPushButton()
        b_min.setObjectName("winBtn")
        b_min.setCursor(Qt.PointingHandCursor)
        b_min.setIcon(glyph_icon(GLYPHS["minimize"], "#FFFFFF", 12))
        b_min.setIconSize(QSize(13, 13))
        b_min.setFixedSize(34, 30)
        b_min.clicked.connect(self.win.showMinimized)
        row.addWidget(b_min)

        b_close = QPushButton()
        b_close.setObjectName("closeBtn")
        b_close.setCursor(Qt.PointingHandCursor)
        b_close.setIcon(glyph_icon(GLYPHS["close"], "#FFFFFF", 12))
        b_close.setIconSize(QSize(13, 13))
        b_close.setFixedSize(34, 30)
        b_close.clicked.connect(self.win.close)
        row.addWidget(b_close)

    def refresh_pill_icons(self, accent: str):
        """选中胶囊的图标换成深色，未选中保持白色。"""
        for key, b in self.pills.items():
            color = accent_dark(accent) if b.isChecked() else "#FFFFFF"
            b.setIcon(glyph_icon(GLYPHS[key], color, 13))

    # ---------- 拖拽 / 双击最大化 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.win._drag_offset = e.globalPos() - self.win.frameGeometry().topLeft()
            self.win._drag_active = True

    def mouseMoveEvent(self, e):
        if getattr(self.win, "_drag_active", False) and (e.buttons() & Qt.LeftButton):
            if self.win.isMaximized():
                return
            self.win.move(e.globalPos() - self.win._drag_offset)

    def mouseReleaseEvent(self, _e):
        self.win._drag_active = False

    def mouseDoubleClickEvent(self, _e):
        self.win.toggle_maximized()


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("MKCL启动器")
        self._page_anim = None
        self._drag_offset = None
        self._drag_active = False
        # 旧版默认主题色软迁移为 PCL 蓝
        if (ctx.config.theme_color or "") in ("", LEGACY_DEFAULT_ACCENT):
            ctx.config.theme_color = DEFAULT_ACCENT
            ctx.config.save()
        self._build_ui()
        self._restore_window_geometry()

    def _restore_window_geometry(self):
        """恢复上次窗口尺寸/位置，并钳制到合法范围。

        历史上 QLabel minimumSizeHint 顶宽布局的 bug 会把窗口撑到上万像素，
        该尺寸一旦被 closeEvent 存进 config.json，下次启动就会恢复成爆炸宽度。
        这里对持久化值做钳制：宽度不低于 900、不超出屏幕可用宽度。
        """
        from PyQt5.QtGui import QGuiApplication
        scr = QGuiApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else None
        max_w = avail.width() if avail else 3840
        max_h = avail.height() if avail else 2160
        wcfg = self.ctx.config.window or {}
        w = max(900, min(int(wcfg.get("width", 980) or 980), max_w))
        h = max(580, min(int(wcfg.get("height", 640) or 640), max_h))
        self.resize(w, h)
        # 位置越界（窗口整体在屏幕外）时回中，避免「启动器看不见」
        if avail is not None:
            x = int(wcfg.get("x", -1) or -1)
            y = int(wcfg.get("y", -1) or -1)
            if x < 0 or y < 0 or x + 100 > avail.right() or y + 100 > avail.bottom():
                self.move(max(0, (avail.width() - w) // 2),
                          max(0, (avail.height() - h) // 2))
            else:
                self.move(x, y)

    def _build_ui(self):
        # PCL CE：无边框窗口，蓝色顶栏即标题栏
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        # SetNoConstraint：任何子控件的 minimumSizeHint 都不再写入本布局的
        # minimumSize，从根源杜绝「长路径/命令行把窗口撑到上万像素」；
        # 窗口最小尺寸由下方显式设定，内容超出时裁切而非爆炸。
        outer.setSizeConstraint(QLayout.SetNoConstraint)

        # ---- 顶栏 ----
        self.title_bar = TitleBar(self)
        outer.addWidget(self.title_bar)

        # ---- 页面栈 ----
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        self.home = HomePage(self.ctx, self)
        self.versions_page = VersionsPage(self.ctx, self)
        self.downloads = DownloadsPage(self.ctx, self)
        self.process_page = ProcessPage(self.ctx, self)
        self.settings = SettingsPage(self.ctx, self)
        for w in (self.home, self.versions_page, self.downloads,
                  self.process_page, self.settings):
            self.stack.addWidget(w)

        # 右下角缩放手柄（无边框窗口保留拖拽调尺寸能力）
        self._grip = QSizeGrip(central)
        self._grip.setFixedSize(16, 16)
        self._grip.raise_()
        self._grip.move(central.width() - 16, central.height() - 16)

        self.nav_buttons = self.title_bar.pills
        self.goto("home")

        # 显式最小尺寸替代「布局顶算出来的 minimumSize」
        self.setMinimumSize(QSize(900, 580))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if getattr(self, "_grip", None):
            self._grip.move(self.width() - 17, self.height() - 17)
            self._grip.raise_()

    def toggle_maximized(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    # ---------- 导航 ----------
    def goto(self, key):
        idx = {"home": 0, "versions": 1, "downloads": 2,
               "process": 3, "settings": 4}.get(key, 0)
        if self.stack.currentIndex() == idx:
            self._select_nav(key)
            return
        self.stack.setCurrentIndex(idx)
        self._select_nav(key)
        self._fade_in(self.stack.currentWidget())
        if key == "home":
            self.home.refresh()
        elif key == "versions" and not self.versions_page.versions:
            self.versions_page.refresh()
        elif key == "downloads" and not self.downloads.client_tab.manifest_versions:
            self.downloads.refresh()
        elif key == "process":
            self.process_page.refresh()
        elif key == "settings":
            self.settings.refresh()

    def _select_nav(self, key):
        for k, b in self.nav_buttons.items():
            b.setChecked(k == key)
        self.title_bar.refresh_pill_icons(self.ctx.config.theme_color or DEFAULT_ACCENT)

    def _fade_in(self, w):
        """页面切换淡入动画（220ms，OutCubic）。"""
        old = self._page_anim
        if old is not None:
            try:
                if old.state() == QAbstractAnimation.Running:
                    old.stop()
            except RuntimeError:
                pass  # 上一动画已被 deleteLater 回收
            self._page_anim = None
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: w.setGraphicsEffect(None))
        anim.finished.connect(anim.deleteLater)
        anim.start()
        self._page_anim = anim

    # ---------- 主题 ----------
    def apply_theme(self):
        from PyQt5.QtWidgets import QApplication, QComboBox
        accent = self.ctx.config.theme_color or DEFAULT_ACCENT
        dark = (getattr(self.ctx.config, "theme_mode", "light") == "dark")
        QApplication.instance().setStyleSheet(build_qss(accent, dark=dark))
        self.title_bar.refresh_pill_icons(accent)
        # QComboBox 弹出列表：应用级 QSS 对 popup 顶层窗口不可靠（原生白框），
        # 改用 widget 级内联样式，随主题切换刷新
        p = current_palette(accent, dark)
        for combo in self.findChildren(QComboBox):
            style_combo_popup(combo, p)

    # ---------- 日志 ----------
    def open_log_dialog(self):
        from launcher.logsetup import get_log_path
        dlg = LogDialog(get_log_path(self.ctx.base_dir), self)
        dlg.exec_()

    # ---------- 生命周期 ----------
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_booted", False):
            self._booted = True
            if (self.ctx.config.window or {}).get("maximized"):
                self.showMaximized()
            # 首屏数据
            self.versions_page.refresh()
            self.downloads.refresh()
            self.settings._scan_java()   # 后台预填 Java 列表
            self.home.refresh()

    def closeEvent(self, event):
        w = self.ctx.config.window or {}
        w = dict(w)
        if self.isMaximized():
            w["maximized"] = True
        else:
            w["maximized"] = False
            w["width"] = self.width()
            w["height"] = self.height()
            w["x"] = self.x()
            w["y"] = self.y()
        self.ctx.config.window = w
        self.ctx.config.save()
        running = self.home.running_games()
        # 「游戏启动后退出启动器」：用户已授权自动退出，不再弹确认
        if running and not getattr(self, "_auto_exit", False):
            ret = QMessageBox.question(
                self, "退出 MKCL",
                "有 %d 个游戏正在运行。退出启动器后游戏将继续独立运行，确定退出吗？" % running,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if ret != QMessageBox.Yes:
                event.ignore()
                return
        self.home.stop_watching()
        event.accept()
