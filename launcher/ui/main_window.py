# -*- coding: utf-8 -*-
"""主窗口：左侧导航（主页/版本/下载/设置）+ 页面栈 + 日志查看器。"""
import os

from PyQt5.QtCore import (
    Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QAbstractAnimation,
)
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QStackedWidget, QDialog, QPlainTextEdit, QMessageBox, QFrame,
    QGraphicsOpacityEffect,
)


from launcher.ui.home_page import HomePage
from launcher.ui.versions_page import VersionsPage
from launcher.ui.downloads_page import DownloadsPage
from launcher.ui.process_page import ProcessPage
from launcher.ui.settings_page import SettingsPage
from launcher.ui.theme import build_qss

_PAGES = (
    ("home", "主页"),
    ("versions", "版本选择"),
    ("downloads", "下载"),
    ("process", "进程管理"),
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
        self.view.setReadOnly(True)
        self.view.setStyleSheet(
            "QPlainTextEdit{background:#FBFCFD;border:1px solid #E5E9EF;"
            'border-radius:10px;font-family:"Consolas",monospace;font-size:12px;}'
        )
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


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("MKCL启动器")
        self._page_anim = None
        self._build_ui()
        self.resize((ctx.config.window or {}).get("width", 980),
                    (ctx.config.window or {}).get("height", 640))

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---- 左侧导航 ----
        nav = QFrame()
        nav.setObjectName("navPanel")
        nav.setFixedWidth(196)
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(14, 20, 14, 16)
        nv.setSpacing(6)
        t = QLabel("MKCL")
        t.setObjectName("navTitle")
        nv.addWidget(t)
        st = QLabel("MKCL v2.1")
        st.setObjectName("navSubtitle")
        nv.addWidget(st)
        nv.addSpacing(10)

        self.nav_buttons = {}
        for key, text in _PAGES:
            b = QPushButton(text)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.goto(k))
            nv.addWidget(b)
            self.nav_buttons[key] = b
        nv.addStretch(1)

        b_log = QPushButton("查看日志")
        b_log.setObjectName("navBtn")
        b_log.setCursor(Qt.PointingHandCursor)
        b_log.clicked.connect(self.open_log_dialog)
        nv.addWidget(b_log)
        foot = QLabel("离线账号-BMCLAPI 镜像")
        foot.setObjectName("navSubtitle")
        foot.setWordWrap(True)
        nv.addWidget(foot)
        layout.addWidget(nav)

        # ---- 页面栈 ----
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.home = HomePage(self.ctx, self)
        self.versions_page = VersionsPage(self.ctx, self)
        self.downloads = DownloadsPage(self.ctx, self)
        self.process_page = ProcessPage(self.ctx, self)
        self.settings = SettingsPage(self.ctx, self)
        for w in (self.home, self.versions_page, self.downloads,
                  self.process_page, self.settings):
            self.stack.addWidget(w)
        self.goto("home")

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
        elif key == "downloads" and not self.downloads.manifest_versions:
            self.downloads.refresh()
        elif key == "process":
            self.process_page.refresh()
        elif key == "settings":
            self.settings.refresh()

    def _select_nav(self, key):
        for k, b in self.nav_buttons.items():
            b.setChecked(k == key)

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
        app = self.window().windowHandle()
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(
            build_qss(self.ctx.config.theme_color or "#4A8F72")
        )

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
        if running:
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
