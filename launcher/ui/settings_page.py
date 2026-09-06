# -*- coding: utf-8 -*-
"""设置页：账号管理、Java、内存、JVM 参数、游戏目录、下载源、外观、窗口、数据。"""
import os

from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QListWidget, QListWidgetItem, QSlider, QFrame,
    QMessageBox, QInputDialog, QFileDialog, QSpinBox, QScrollArea,
    QColorDialog, QSizePolicy, QCheckBox,
)

from launcher.ui.workers import JavaScanWorker
from launcher.ui.theme import PRESET_COLORS, accent_soft


def _card(title=None):
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 13, 16, 13)
    v.setSpacing(9)
    if title:
        t = QLabel(title)
        t.setObjectName("cardTitle")
        v.addWidget(t)
    return f, v


class SettingsPage(QWidget):
    def __init__(self, ctx, win):
        super().__init__()
        self.ctx = ctx
        self.win = win
        self.java_worker = None
        self.detected_javas = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        title = QLabel("设置")
        title.setStyleSheet("font-size:17px;font-weight:600;")
        root.addWidget(title)

        # ---- 账号 ----
        card, v = _card("账号（离线模式）")
        self.acc_list = QListWidget()
        self.acc_list.setMaximumHeight(120)
        v.addWidget(self.acc_list)
        row = QHBoxLayout()
        b_add = QPushButton("添加离线账号")
        b_add.setObjectName("primaryBtn")
        b_add.clicked.connect(self._add_account)
        b_cur = QPushButton("设为当前")
        b_cur.clicked.connect(self._set_current_account)
        b_del = QPushButton("删除所选账号")
        b_del.clicked.connect(self._remove_account)
        row.addWidget(b_add)
        row.addWidget(b_cur)
        row.addWidget(b_del)
        row.addStretch(1)
        v.addLayout(row)
        root.addWidget(card)

        # ---- Java ----
        card, v = _card("Java 运行时")
        self.java_cb = QComboBox()
        self.java_cb.addItem("自动选择（按游戏版本智能匹配）", "")
        self.java_cb.currentIndexChanged.connect(self._on_java_changed)
        v.addWidget(self.java_cb)
        self.java_hint = QLabel("")
        self.java_hint.setObjectName("subText")
        self.java_hint.setWordWrap(True)
        v.addWidget(self.java_hint)
        row = QHBoxLayout()
        b_scan = QPushButton("重新检测 Java")
        b_scan.clicked.connect(self._scan_java)
        b_link = QPushButton("没有 Java？前往下载页")
        b_link.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl("https://adoptium.net/temurin/releases/")))
        row.addWidget(b_scan)
        row.addWidget(b_link)
        row.addStretch(1)
        v.addLayout(row)
        root.addWidget(card)

        # ---- 内存与 JVM ----
        card, v = _card("内存与 JVM")
        mem_row = QHBoxLayout()
        mem_row.addWidget(QLabel("最大内存："))
        self.mem_slider = QSlider(Qt.Horizontal)
        self.mem_slider.setRange(1, 32)
        self.mem_slider.setValue(self.ctx.config.memory_gb or 4)
        self.mem_value = QLabel("%d GB" % (self.ctx.config.memory_gb or 4))
        self.mem_value.setMinimumWidth(52)
        self.mem_slider.valueChanged.connect(self._on_mem_changed)
        mem_row.addWidget(self.mem_slider, 1)
        mem_row.addWidget(self.mem_value)
        v.addLayout(mem_row)
        jvm_row = QHBoxLayout()
        jvm_row.addWidget(QLabel("额外 JVM 参数："))
        self.jvm_edit = QLineEdit(self.ctx.config.jvm_extra_args or "")
        self.jvm_edit.setPlaceholderText("如：-XX:+UseZGC（可选，空格分隔）")
        self.jvm_edit.editingFinished.connect(self._on_jvm_changed)
        jvm_row.addWidget(self.jvm_edit, 1)
        v.addLayout(jvm_row)
        root.addWidget(card)

        # ---- 游戏目录与下载源 ----
        card, v = _card("目录与下载源")
        self.auto_iso_cb = QCheckBox("新版本默认开启隔离游戏目录（推荐，避免共享 mods 跨版本冲突）")
        self.auto_iso_cb.setChecked(bool(self.ctx.config.auto_isolate))
        self.auto_iso_cb.toggled.connect(self._on_auto_isolate)
        v.addWidget(self.auto_iso_cb)
        g_row = QHBoxLayout()
        g_row.addWidget(QLabel("游戏目录："))
        self.game_dir_edit = QLineEdit(self.ctx.config.game_dir or "")
        self.game_dir_edit.editingFinished.connect(self._on_game_dir_changed)
        g_row.addWidget(self.game_dir_edit, 1)
        b_browse = QPushButton("浏览…")
        b_browse.clicked.connect(self._browse_game_dir)
        g_row.addWidget(b_browse)
        v.addLayout(g_row)
        s_row = QHBoxLayout()
        s_row.addWidget(QLabel("下载源："))
        self.source_cb = QComboBox()
        self.source_cb.addItem("BMCLAPI 国内镜像（推荐）", "bmclapi")
        self.source_cb.addItem("Mojang 官方源", "official")
        idx = self.source_cb.findData(self.ctx.config.download_source or "bmclapi")
        self.source_cb.setCurrentIndex(max(0, idx))
        self.source_cb.currentIndexChanged.connect(self._on_source_changed)
        s_row.addWidget(self.source_cb, 1)
        v.addLayout(s_row)
        root.addWidget(card)

        # ---- 外观 ----
        card, v = _card("外观（主题色）")
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("主题色："))
        self._swatches = []
        for hexc in PRESET_COLORS:
            b = QPushButton()
            b.setFixedSize(QSize(30, 30))
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(hexc)
            b.setStyleSheet(
                "QPushButton{background:%s;border:2px solid #FFFFFF;border-radius:15px;}"
                "QPushButton:hover{border-color:#4B5563;}" % hexc
            )
            b.clicked.connect(lambda _=False, c=hexc: self._set_accent(c))
            color_row.addWidget(b)
            self._swatches.append(b)
        b_custom = QPushButton("自定义…")
        b_custom.clicked.connect(self._pick_custom_color)
        color_row.addWidget(b_custom)
        color_row.addStretch(1)
        v.addLayout(color_row)
        root.addWidget(card)

        # ---- 窗口 ----
        card, v = _card("窗口")
        w_row = QHBoxLayout()
        w_row.addWidget(QLabel("窗口尺寸："))
        w_row.addWidget(QLabel("宽"))
        self.w_spin = QSpinBox()
        self.w_spin.setRange(640, 3840)
        self.w_spin.setValue((self.ctx.config.window or {}).get("width", 980))
        self.w_spin.editingFinished.connect(self._on_window_changed)
        w_row.addWidget(self.w_spin)
        w_row.addWidget(QLabel("高"))
        self.h_spin = QSpinBox()
        self.h_spin.setRange(480, 2160)
        self.h_spin.setValue((self.ctx.config.window or {}).get("height", 640))
        self.h_spin.editingFinished.connect(self._on_window_changed)
        w_row.addWidget(self.h_spin)
        w_row.addStretch(1)
        v.addLayout(w_row)
        root.addWidget(card)

        # ---- 数据 ----
        card, v = _card("数据与日志")
        d_row = QHBoxLayout()
        b_log = QPushButton("打开日志文件夹")
        b_log.clicked.connect(self._open_logs)
        b_cfg = QPushButton("打开数据文件夹")
        b_cfg.clicked.connect(self._open_data)
        d_row.addWidget(b_log)
        d_row.addWidget(b_cfg)
        d_row.addStretch(1)
        v.addLayout(d_row)
        self.path_hint = QLabel("")
        self.path_hint.setObjectName("subText")
        self.path_hint.setWordWrap(True)
        v.addWidget(self.path_hint)
        root.addWidget(card)

        root.addStretch(1)

    # ---------- 刷新 ----------
    def refresh(self):
        self._refresh_accounts()
        self._refresh_paths()
        if not self.java_worker or not self.java_worker.isRunning():
            self._fill_java_combo(keep=True)

    def _refresh_accounts(self):
        self.acc_list.clear()
        cur = self.ctx.accounts.current_name
        for acc in self.ctx.accounts.list():
            mark = "　✓ 当前" if acc.name == cur else ""
            it = QListWidgetItem("%s%s\nUUID: %s" % (acc.name, mark, acc.uuid))
            it.setData(Qt.UserRole, acc.name)
            self.acc_list.addItem(it)

    def _refresh_paths(self):
        base = self.ctx.base_dir
        self.path_hint.setText(
            "配置：%s ｜ 账号：%s ｜ 日志：%s" % (
                os.path.join(base, "config.json"),
                os.path.join(base, "accounts.json"),
                os.path.join(base, "logs", "launcher.log"),
            )
        )

    # ---------- 账号 ----------
    def _add_account(self):
        name, ok = QInputDialog.getText(self, "添加离线账号", "角色名（1-16 个字符）：")
        if not ok:
            return
        try:
            acc = self.ctx.accounts.add_offline(name)
            self.ctx.accounts.set_current(acc.name)
            self.ctx.accounts.save()
        except Exception as e:
            QMessageBox.warning(self, "添加失败", str(e))
            return
        self._refresh_accounts()
        self.win.home.refresh()

    def _set_current_account(self):
        it = self.acc_list.currentItem()
        if not it:
            QMessageBox.information(self, "提示", "请先选择一个账号。")
            return
        name = it.data(Qt.UserRole)
        self.ctx.accounts.set_current(name)
        self.ctx.accounts.save()
        self._refresh_accounts()
        self.win.home.refresh()

    def _remove_account(self):
        it = self.acc_list.currentItem()
        if not it:
            QMessageBox.information(self, "提示", "请先选择要删除的账号。")
            return
        name = it.data(Qt.UserRole)
        if QMessageBox.question(self, "确认删除", "确定删除账号「%s」吗？" % name) == QMessageBox.Yes:
            self.ctx.accounts.remove(name)
            self.ctx.accounts.save()
            self._refresh_accounts()
            self.win.home.refresh()

    # ---------- Java ----------
    def _scan_java(self):
        self.java_hint.setText("正在检测系统 Java 运行时…")
        self.java_worker = JavaScanWorker()
        self.java_worker.ok.connect(self._on_java_scanned)
        self.java_worker.fail.connect(self._on_java_fail)
        self.java_worker.start()

    def _on_java_scanned(self, javas):
        self.detected_javas = javas
        self._fill_java_combo(keep=True)
        self.java_hint.setText(
            "检测到 %d 个 Java 运行时。低于游戏要求的版本会被自动跳过（推荐留空使用自动选择）。"
            % len(javas)
        )

    def _on_java_fail(self, msg):
        self.java_hint.setText("Java 检测失败：%s" % msg)

    def _fill_java_combo(self, keep=True):
        cur = self.ctx.config.java_path or ""
        self.java_cb.blockSignals(True)
        self.java_cb.clear()
        self.java_cb.addItem("自动选择（按游戏版本智能匹配）", "")
        for j in self.detected_javas:
            label = "%s ｜ %s (%s)" % (j.path, j.version, j.vendor or "Unknown")
            self.java_cb.addItem(label, j.path)
        idx = self.java_cb.findData(cur)
        if idx >= 0:
            self.java_cb.setCurrentIndex(idx)
        elif cur:
            self.java_cb.addItem("手动指定：%s" % cur, cur)
            self.java_cb.setCurrentIndex(self.java_cb.count() - 1)
        self.java_cb.blockSignals(False)
        if not self.detected_javas:
            self.java_hint.setText("尚未检测：点击「重新检测 Java」扫描系统中的 Java。")

    def _on_java_changed(self):
        self.ctx.config.java_path = self.java_cb.currentData() or ""
        self.ctx.config.save()
        self.win.home.refresh()

    # ---------- 内存 / JVM ----------
    def _on_mem_changed(self, val):
        self.mem_value.setText("%d GB" % val)
        self.ctx.config.memory_gb = int(val)
        self.ctx.config.save()
        self.win.home.refresh()

    def _on_jvm_changed(self):
        self.ctx.config.jvm_extra_args = self.jvm_edit.text().strip()
        self.ctx.config.save()

    # ---------- 目录 / 源 ----------
    def _browse_game_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择游戏目录（.minecraft）",
                                             self.ctx.config.game_dir or "")
        if not d:
            return
        self.game_dir_edit.setText(d)
        self._on_game_dir_changed()

    def _on_game_dir_changed(self):
        d = self.game_dir_edit.text().strip()
        if d == self.ctx.config.game_dir:
            return
        self.ctx.config.game_dir = d
        self.ctx.config.save()
        if d:
            self.win.versions_page.refresh()
        self.win.home.refresh()

    def _on_source_changed(self):
        self.ctx.config.download_source = self.source_cb.currentData() or "bmclapi"
        self.ctx.config.save()
        self.win.home.refresh()

    def _on_auto_isolate(self, checked):
        self.ctx.config.auto_isolate = bool(checked)
        self.ctx.config.save()
        self.win.versions_page.refresh()
        self.win.home.refresh()

    # ---------- 外观 ----------
    def _set_accent(self, hexc):
        self.ctx.config.theme_color = hexc
        self.ctx.config.save()
        self.win.apply_theme()

    def _pick_custom_color(self):
        c = QColorDialog.getColor(QColor(self.ctx.config.theme_color), self, "选择主题色")
        if c.isValid():
            self._set_accent(c.name())

    # ---------- 窗口 ----------
    def _on_window_changed(self):
        win_cfg = dict(self.ctx.config.window or {})
        win_cfg["width"] = int(self.w_spin.value())
        win_cfg["height"] = int(self.h_spin.value())
        self.ctx.config.window = win_cfg
        self.ctx.config.save()
        self.win.resize(win_cfg["width"], win_cfg["height"])

    # ---------- 数据 ----------
    def _open_logs(self):
        d = os.path.join(self.ctx.base_dir, "logs")
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def _open_data(self):
        os.startfile(self.ctx.base_dir)
