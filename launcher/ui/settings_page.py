# -*- coding: utf-8 -*-
"""设置页（PCL CE 风格）：左侧分组导航（游戏/工具/关于）+ 右侧分区页面。

分区：账号 / 启动选项 / 游戏内存 / Java / 实例管理 / 个性化 / 杂项 / 软件信息 / 日志与数据。
"""
import os

from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QColor, QDesktopServices
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QListWidget, QListWidgetItem, QSlider, QFrame,
    QMessageBox, QInputDialog, QFileDialog, QSpinBox, QScrollArea,
    QColorDialog, QSizePolicy, QCheckBox, QRadioButton, QButtonGroup,
    QStackedWidget, QProgressBar,
)

from launcher.ui.workers import JavaScanWorker
from launcher.ui.theme import PRESET_COLORS, accent_soft, ElideLabel
from launcher.launch import (
    system_memory_info, auto_memory_gb, max_memory_gb, resolve_window_size,
    java_heap_cap_gb,
)

# 分组导航结构：(分组键, 分组名, [(分区键, 分区名), ...])
_SECTIONS = (
    ("game", "游戏", (
        ("account", "账号"),
        ("launch", "启动选项"),
        ("memory", "游戏内存"),
        ("java", "Java"),
        ("instance", "实例管理"),
    )),
    ("tools", "工具", (
        ("theme", "个性化"),
        ("misc", "杂项"),
    )),
    ("about", "关于", (
        ("info", "软件信息"),
        ("logs", "日志与数据"),
    )),
)

_ISOLATE_ITEMS = (("隔离所有实例（推荐）", True),
                  ("不隔离，共用游戏目录", False))
_SIZE_ITEMS = (("默认 854 × 480", "default"),
               ("最大化", "maximized"),
               ("全屏", "fullscreen"),
               ("自定义…", "custom"))
_IP_ITEMS = (("Java 默认", "java"),
             ("优先 IPv4", "ipv4"),
             ("优先 IPv6", "ipv6"))
_VIS_ITEMS = (("游戏启动后仍保持不变", "keep"),
              ("最小化启动器", "minimize"),
              ("游戏启动后退出启动器", "exit"))
_PRIORITY_ITEMS = (("低", "low"),
                   ("中（平衡）", "normal"),
                   ("高", "high"),
                   ("实时（可能不稳定）", "realtime"))


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


def _row(*widgets, stretch_last=True):
    row = QHBoxLayout()
    for w in widgets:
        if isinstance(w, int):
            row.addSpacing(w)
        else:
            row.addWidget(w)
    if stretch_last:
        row.addStretch(1)
    return row


class SettingsPage(QWidget):
    def __init__(self, ctx, win):
        super().__init__()
        self.ctx = ctx
        self.win = win
        self.java_worker = None
        self.detected_javas = []
        self._build_ui()
        self.refresh()

    # ---------- 整体结构 ----------
    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # ---- 左侧分组导航 ----
        nav = QFrame()
        nav.setObjectName("settingsNav")
        nav.setFixedWidth(168)
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(10, 12, 10, 12)
        nv.setSpacing(4)
        self.nav_buttons = {}
        for _gkey, gname, items in _SECTIONS:
            gh = QLabel(gname)
            gh.setObjectName("groupHeader")
            nv.addWidget(gh)
            for key, text in items:
                b = QPushButton(text)
                b.setObjectName("settingsNavBtn")
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, k=key: self._show(k))
                nv.addWidget(b)
                self.nav_buttons[key] = b
        nv.addStretch(1)
        root.addWidget(nav)

        # ---- 右侧分区栈 ----
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.pages = {}
        self.pages["account"] = self._page_account()
        self.pages["launch"] = self._page_launch()
        self.pages["memory"] = self._page_memory()
        self.pages["java"] = self._page_java()
        self.pages["instance"] = self._page_instance()
        self.pages["theme"] = self._page_theme()
        self.pages["misc"] = self._page_misc()
        self.pages["info"] = self._page_info()
        self.pages["logs"] = self._page_logs()
        for k in ("account", "launch", "memory", "java", "instance",
                  "theme", "misc", "info", "logs"):
            self.stack.addWidget(self.pages[k])
        self._show("launch")

    def _show(self, key):
        idx = {"account": 0, "launch": 1, "memory": 2, "java": 3,
               "instance": 4, "theme": 5, "misc": 6, "info": 7, "logs": 8}.get(key, 1)
        self.stack.setCurrentIndex(idx)
        for k, b in self.nav_buttons.items():
            b.setChecked(k == key)
        if key == "memory":
            self._refresh_memory()

    # ---------- 分区：账号 ----------
    def _page_account(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        card, v = _card("账号（离线模式）")
        self.acc_list = QListWidget()
        self.acc_list.setMaximumHeight(150)
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
        hint = QLabel("离线账号使用本地 UUID，仅能进入单人游戏与允许离线的服务器；"
                      "正版登录可前往 PCL CE / HMCL 等启动器使用。")
        hint.setObjectName("subText")
        hint.setWordWrap(True)
        v.addWidget(hint)
        root.addWidget(card)
        root.addStretch(1)
        return page

    # ---------- 分区：启动选项 ----------
    def _page_launch(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        card, v = _card("启动选项")

        self.isolate_cb = QComboBox()
        for text, val in _ISOLATE_ITEMS:
            self.isolate_cb.addItem(text, val)
        idx = self.isolate_cb.findData(bool(self.ctx.config.auto_isolate))
        self.isolate_cb.setCurrentIndex(max(0, idx))
        self.isolate_cb.currentIndexChanged.connect(self._on_isolate_mode)
        v.addLayout(_row(QLabel("默认实例隔离"), self.isolate_cb))

        self.size_cb = QComboBox()
        for text, val in _SIZE_ITEMS:
            self.size_cb.addItem(text, val)
        idx = self.size_cb.findData(getattr(self.ctx.config, "window_size_mode", "default"))
        self.size_cb.setCurrentIndex(max(0, idx))
        self.size_cb.currentIndexChanged.connect(self._on_size_mode)
        v.addLayout(_row(QLabel("游戏窗口大小"), self.size_cb))

        self.custom_size_row = QHBoxLayout()
        self.custom_size_row.addWidget(QLabel("　宽度"))
        self.w_spin = QSpinBox()
        self.w_spin.setRange(320, 7680)
        self.w_spin.setValue(getattr(self.ctx.config, "window_width", 854))
        self.w_spin.editingFinished.connect(self._on_custom_size)
        self.custom_size_row.addWidget(self.w_spin)
        self.custom_size_row.addWidget(QLabel("高度"))
        self.h_spin = QSpinBox()
        self.h_spin.setRange(240, 4320)
        self.h_spin.setValue(getattr(self.ctx.config, "window_height", 480))
        self.h_spin.editingFinished.connect(self._on_custom_size)
        self.custom_size_row.addWidget(self.h_spin)
        self.custom_size_row.addStretch(1)
        v.addLayout(self.custom_size_row)
        self._toggle_custom_size()

        self.auth_cb = QComboBox()
        self.auth_cb.addItem("离线模式（当前）", "offline")
        self.auth_cb.addItem("设备代码流（暂不支持）", "device")
        self.auth_cb.model().item(1).setEnabled(False)
        self.auth_cb.setCurrentIndex(0)
        v.addLayout(_row(QLabel("正版验证方式"), self.auth_cb))

        self.ip_cb = QComboBox()
        for text, val in _IP_ITEMS:
            self.ip_cb.addItem(text, val)
        idx = self.ip_cb.findData(getattr(self.ctx.config, "ip_preference", "java"))
        self.ip_cb.setCurrentIndex(max(0, idx))
        self.ip_cb.currentIndexChanged.connect(self._on_ip)
        v.addLayout(_row(QLabel("IP 协议偏好"), self.ip_cb))

        self.vis_cb = QComboBox()
        for text, val in _VIS_ITEMS:
            self.vis_cb.addItem(text, val)
        idx = self.vis_cb.findData(getattr(self.ctx.config, "launcher_visibility", "keep"))
        self.vis_cb.setCurrentIndex(max(0, idx))
        self.vis_cb.currentIndexChanged.connect(self._on_visibility)
        v.addLayout(_row(QLabel("启动器可见性"), self.vis_cb))

        self.prio_cb = QComboBox()
        for text, val in _PRIORITY_ITEMS:
            self.prio_cb.addItem(text, val)
        idx = self.prio_cb.findData(getattr(self.ctx.config, "process_priority", "normal"))
        self.prio_cb.setCurrentIndex(max(0, idx))
        self.prio_cb.currentIndexChanged.connect(self._on_priority)
        v.addLayout(_row(QLabel("进程优先级"), self.prio_cb))

        self.msg_edit = QLineEdit(getattr(self.ctx.config, "custom_message", "") or "")
        self.msg_edit.setPlaceholderText("如：我的整合包测试服 · 显示在启动器标题栏")
        self.msg_edit.editingFinished.connect(self._on_message)
        v.addLayout(_row(QLabel("自定义信息"), self.msg_edit))

        root.addWidget(card)
        root.addStretch(1)
        return page

    # ---------- 分区：游戏内存 ----------
    def _page_memory(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        card, v = _card("游戏内存")

        self.mem_auto_rb = QRadioButton("自动配置（按物理内存智能分配，推荐）")
        self.mem_custom_rb = QRadioButton("自定义")
        self.mem_group = QButtonGroup(self)
        self.mem_group.addButton(self.mem_auto_rb)
        self.mem_group.addButton(self.mem_custom_rb)
        auto_default = bool(getattr(self.ctx.config, "memory_auto", True))
        self.mem_auto_rb.setChecked(auto_default)
        self.mem_custom_rb.setChecked(not auto_default)
        self.mem_auto_rb.toggled.connect(self._on_memory_mode)
        v.addWidget(self.mem_auto_rb)
        v.addWidget(self.mem_custom_rb)

        slider_row = QHBoxLayout()
        self.mem_slider = QSlider(Qt.Horizontal)
        self.mem_max = max_memory_gb()
        self.mem_slider.setRange(1, self.mem_max)
        self.mem_slider.setValue(int(self.ctx.config.memory_gb or 4))
        self.mem_slider.valueChanged.connect(self._on_mem_changed)
        self.mem_value = QLabel("%d GB" % (self.ctx.config.memory_gb or 4))
        self.mem_value.setMinimumWidth(52)
        slider_row.addWidget(self.mem_slider, 1)
        slider_row.addWidget(self.mem_value)
        v.addLayout(slider_row)
        self.mem_slider.setEnabled(not auto_default)

        self.mem_bar = QProgressBar()
        self.mem_bar.setRange(0, 100)
        self.mem_bar.setValue(0)
        self.mem_bar.setFixedHeight(10)
        v.addWidget(self.mem_bar)

        bar_row = QHBoxLayout()
        # ElideLabel：避免长串文本的 minimumSizeHint 顶宽布局
        self.mem_used = ElideLabel("已使用内存 — / —")
        self.mem_used.setObjectName("subText")
        bar_row.addWidget(self.mem_used)
        bar_row.addStretch(1)
        self.mem_alloc = ElideLabel("游戏分配 —")
        self.mem_alloc.setObjectName("subText")
        bar_row.addWidget(self.mem_alloc)
        v.addLayout(bar_row)

        row = QHBoxLayout()
        b_refresh = QPushButton("重新检测内存")
        b_refresh.clicked.connect(self._refresh_memory)
        row.addWidget(b_refresh)
        row.addStretch(1)
        v.addLayout(row)

        hint = QLabel("自动配置会根据物理内存选择：≤4GB→1G，≤8GB→2G，≤16GB→4G，>16GB→6G。"
                      "分配过大可能导致系统卡顿，请留出至少 2GB 给系统与其他程序。")
        hint.setObjectName("subText")
        hint.setWordWrap(True)
        v.addWidget(hint)

        root.addWidget(card)
        root.addStretch(1)
        self._refresh_memory()
        return page

    # ---------- 分区：Java ----------
    def _page_java(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

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

        card2, v2 = _card("高级 JVM 参数")
        self.jvm_edit = QLineEdit(self.ctx.config.jvm_extra_args or "")
        self.jvm_edit.setPlaceholderText("如：-XX:+UseZGC（可选，空格分隔）")
        self.jvm_edit.editingFinished.connect(self._on_jvm_changed)
        v2.addWidget(self.jvm_edit)
        hint = QLabel("仅在确知参数含义时填写，错误参数可能导致游戏无法启动。")
        hint.setObjectName("subText")
        hint.setWordWrap(True)
        v2.addWidget(hint)
        root.addWidget(card2)

        root.addStretch(1)
        return page

    # ---------- 分区：实例管理 ----------
    def _page_instance(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        card, v = _card("游戏目录与实例")
        g_row = QHBoxLayout()
        g_row.addWidget(QLabel("游戏目录："))
        self.game_dir_edit = QLineEdit(self.ctx.config.game_dir or "")
        self.game_dir_edit.editingFinished.connect(self._on_game_dir_changed)
        g_row.addWidget(self.game_dir_edit, 1)
        b_browse = QPushButton("浏览…")
        b_browse.clicked.connect(self._browse_game_dir)
        b_open = QPushButton("打开目录")
        b_open.clicked.connect(self._open_game_dir)
        g_row.addWidget(b_browse)
        g_row.addWidget(b_open)
        v.addLayout(g_row)
        hint = QLabel("开启「隔离所有实例」后，每个版本的 mods / 存档 / 配置都放在 "
                      "versions/<版本名>/ 下，互不污染；关闭后所有版本共用游戏目录。"
                      "该默认值可在「启动选项」中随时更改。")
        hint.setObjectName("subText")
        hint.setWordWrap(True)
        v.addWidget(hint)
        root.addWidget(card)
        root.addStretch(1)
        return page

    # ---------- 分区：个性化 ----------
    def _page_theme(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        card, v = _card("主题色")
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

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("界面明暗："))
        self.theme_mode_cb = QComboBox()
        self.theme_mode_cb.addItem("明亮", "light")
        self.theme_mode_cb.addItem("暗黑", "dark")
        idx = self.theme_mode_cb.findData(
            getattr(self.ctx.config, "theme_mode", "light") or "light")
        self.theme_mode_cb.setCurrentIndex(max(0, idx))
        self.theme_mode_cb.currentIndexChanged.connect(self._on_theme_mode_changed)
        mode_row.addWidget(self.theme_mode_cb, 1)
        mode_row.addStretch(1)
        v.addLayout(mode_row)
        root.addWidget(card)

        card2, v2 = _card("启动器窗口")
        w_row = QHBoxLayout()
        w_row.addWidget(QLabel("窗口尺寸："))
        w_row.addWidget(QLabel("宽"))
        self.win_w_spin = QSpinBox()
        self.win_w_spin.setRange(640, 3840)
        self.win_w_spin.setValue((self.ctx.config.window or {}).get("width", 980))
        self.win_w_spin.editingFinished.connect(self._on_window_changed)
        w_row.addWidget(self.win_w_spin)
        w_row.addWidget(QLabel("高"))
        self.win_h_spin = QSpinBox()
        self.win_h_spin.setRange(480, 2160)
        self.win_h_spin.setValue((self.ctx.config.window or {}).get("height", 640))
        self.win_h_spin.editingFinished.connect(self._on_window_changed)
        w_row.addWidget(self.win_h_spin)
        w_row.addStretch(1)
        v2.addLayout(w_row)
        hint = QLabel("修改后立即应用到当前窗口；双击顶部蓝色标题栏可最大化 / 还原。")
        hint.setObjectName("subText")
        hint.setWordWrap(True)
        v2.addWidget(hint)
        root.addWidget(card2)

        root.addStretch(1)
        return page

    # ---------- 分区：杂项 ----------
    def _page_misc(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        card, v = _card("下载源")
        s_row = QHBoxLayout()
        s_row.addWidget(QLabel("下载源："))
        self.source_cb = QComboBox()
        self.source_cb.addItem("BMCLAPI 国内镜像（推荐）", "bmclapi")
        self.source_cb.addItem("Mojang 官方源", "official")
        idx = self.source_cb.findData(self.ctx.config.download_source or "bmclapi")
        self.source_cb.setCurrentIndex(max(0, idx))
        self.source_cb.currentIndexChanged.connect(self._on_source_changed)
        s_row.addWidget(self.source_cb, 1)
        s_row.addStretch(1)
        v.addLayout(s_row)
        hint = QLabel("BMCLAPI 为国内镜像，下载原版客户端与依赖库更快；"
                      "官方源速度较慢但数据最新。")
        hint.setObjectName("subText")
        hint.setWordWrap(True)
        v.addWidget(hint)
        root.addWidget(card)
        root.addStretch(1)
        return page

    # ---------- 分区：软件信息 ----------
    def _page_info(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        card, v = _card("软件信息")
        info = [
            ("软件名称", "MKCL Launcher CE"),
            ("当前版本", "2.1"),
            ("界面风格", "PCL CE（Plain Craft Launcher Community Edition）"),
            ("技术栈", "Python + PyQt5"),
            ("数据源", "BMCLAPI（客户端/库）· Modrinth（模组/整合包）"),
            ("模组端", "Fabric / Quilt / Forge / NeoForge"),
            ("许可协议", "见项目仓库"),
        ]
        grid = QGridLayout()
        grid.setVerticalSpacing(7)
        for i, (k, val) in enumerate(info):
            kk = QLabel(k)
            kk.setObjectName("subText")
            kk.setFixedWidth(88)
            vv = QLabel(val)
            vv.setWordWrap(True)
            vv.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(kk, i, 0)
            grid.addWidget(vv, i, 1)
        v.addLayout(grid)
        row = QHBoxLayout()
        b_log = QPushButton("查看日志")
        b_log.clicked.connect(self.win.open_log_dialog)
        row.addWidget(b_log)
        row.addStretch(1)
        v.addLayout(row)
        root.addWidget(card)
        root.addStretch(1)
        return page

    # ---------- 分区：日志与数据 ----------
    def _page_logs(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        card, v = _card("日志与数据")
        d_row = QHBoxLayout()
        b_log = QPushButton("打开日志文件夹")
        b_log.clicked.connect(self._open_logs)
        b_cfg = QPushButton("打开数据文件夹")
        b_cfg.clicked.connect(self._open_data)
        b_view = QPushButton("查看日志")
        b_view.clicked.connect(self.win.open_log_dialog)
        d_row.addWidget(b_log)
        d_row.addWidget(b_cfg)
        d_row.addWidget(b_view)
        d_row.addStretch(1)
        v.addLayout(d_row)
        # ElideLabel：三个长路径串（minHint 1241px）会顶宽布局，改单行省略
        self.path_hint = ElideLabel("")
        self.path_hint.setObjectName("subText")
        v.addWidget(self.path_hint)
        root.addWidget(card)
        root.addStretch(1)
        return page

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
        if QMessageBox.question(
                self, "确认删除",
                "确定删除账号「%s」吗？" % name) == QMessageBox.Yes:
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
            bits = "64 位" if getattr(j, "is_64", True) else "32 位"
            label = "%s ｜ %s (%s, %s)" % (
                j.path, j.version, j.vendor or "Unknown", bits)
            self.java_cb.addItem(label, j.path)
        idx = self.java_cb.findData(cur)
        if idx >= 0:
            self.java_cb.setCurrentIndex(idx)
        elif cur:
            self.java_cb.addItem("手动指定：%s" % cur, cur)
            self.java_cb.setCurrentIndex(self.java_cb.count() - 1)
        self.java_cb.blockSignals(False)
        if getattr(self, "mem_slider", None) is not None:
            self._refresh_mem_slider_cap()
        if not self.detected_javas:
            self.java_hint.setText("尚未检测：点击「重新检测 Java」扫描系统中的 Java。")

    def _on_java_changed(self):
        self.ctx.config.java_path = self.java_cb.currentData() or ""
        self.ctx.config.save()
        self._refresh_mem_slider_cap()
        self.win.home.refresh()

    def _refresh_mem_slider_cap(self):
        """按当前所选 Java 的位数调整内存滑块上限。

        32 位 JVM 堆上限仅约 1.5G，超出会导致 JVM 创建失败
        （"Could not create the Java Virtual Machine" 系统错误框）。
        """
        cap = self.mem_max
        jp = self.java_cb.currentData() or ""
        if jp:
            cap = min(cap, java_heap_cap_gb(jp) or self.mem_max)
        self.mem_slider.setMaximum(max(1, int(cap)))

    def _on_jvm_changed(self):
        self.ctx.config.jvm_extra_args = self.jvm_edit.text().strip()
        self.ctx.config.save()

    # ---------- 目录 ----------
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

    def _open_game_dir(self):
        d = self.ctx.config.game_dir
        if d and os.path.isdir(d):
            os.startfile(d)

    # ---------- 启动选项 ----------
    def _on_isolate_mode(self):
        self.ctx.config.auto_isolate = bool(self.isolate_cb.currentData())
        self.ctx.config.save()
        self.win.versions_page.refresh()
        self.win.home.refresh()

    def _toggle_custom_size(self):
        custom = (self.size_cb.currentData() == "custom")
        for i in range(self.custom_size_row.count()):
            item = self.custom_size_row.itemAt(i)
            if item and item.widget():
                item.widget().setVisible(custom)

    def _on_size_mode(self):
        mode = self.size_cb.currentData() or "default"
        self.ctx.config.window_size_mode = mode
        self.ctx.config.save()
        self._toggle_custom_size()
        self.win.home.refresh()

    def _on_custom_size(self):
        self.ctx.config.window_width = int(self.w_spin.value())
        self.ctx.config.window_height = int(self.h_spin.value())
        self.ctx.config.save()
        self.win.home.refresh()

    def _on_ip(self):
        self.ctx.config.ip_preference = self.ip_cb.currentData() or "java"
        self.ctx.config.save()

    def _on_visibility(self):
        self.ctx.config.launcher_visibility = self.vis_cb.currentData() or "keep"
        self.ctx.config.save()

    def _on_priority(self):
        self.ctx.config.process_priority = self.prio_cb.currentData() or "normal"
        self.ctx.config.save()

    def _on_message(self):
        self.ctx.config.custom_message = self.msg_edit.text().strip()
        self.ctx.config.save()
        self.win.home.refresh()

    # ---------- 内存 ----------
    def _on_memory_mode(self):
        auto = self.mem_auto_rb.isChecked()
        self.ctx.config.memory_auto = auto
        self.ctx.config.save()
        self.mem_slider.setEnabled(not auto)
        self._refresh_memory()
        self.win.home.refresh()

    def _on_mem_changed(self, val):
        self.mem_value.setText("%d GB" % val)
        self.ctx.config.memory_gb = int(val)
        self.ctx.config.save()
        self._refresh_memory()
        self.win.home.refresh()

    def _refresh_memory(self):
        total, avail = system_memory_info()
        used = max(0, total - avail)
        if total:
            gib = 1024 ** 3
            self.mem_bar.setValue(int(used * 100 / total))
            self.mem_used.setText("已使用内存 %.1f GiB / 已安装 %.1f GiB"
                                  % (used / gib, total / gib))
        else:
            self.mem_bar.setValue(0)
            self.mem_used.setText("已使用内存 — / —")
        if self.ctx.config.memory_auto:
            alloc = auto_memory_gb()
            self.mem_alloc.setText("游戏分配 %d GB（自动）" % alloc)
        else:
            self.mem_alloc.setText("游戏分配 %d GB" % (self.ctx.config.memory_gb or 4))

    # ---------- 外观 ----------
    def _set_accent(self, hexc):
        self.ctx.config.theme_color = hexc
        self.ctx.config.save()
        self.win.apply_theme()

    def _pick_custom_color(self):
        c = QColorDialog.getColor(QColor(self.ctx.config.theme_color), self, "选择主题色")
        if c.isValid():
            self._set_accent(c.name())

    def _on_theme_mode_changed(self):
        self.ctx.config.theme_mode = self.theme_mode_cb.currentData() or "light"
        self.ctx.config.save()
        self.win.apply_theme()
        self.win.home.update()   # 触发主页背景重绘（留白/留黑渐变）

    def _on_window_changed(self):
        win_cfg = dict(self.ctx.config.window or {})
        win_cfg["width"] = int(self.win_w_spin.value())
        win_cfg["height"] = int(self.win_h_spin.value())
        self.ctx.config.window = win_cfg
        self.ctx.config.save()
        self.win.resize(win_cfg["width"], win_cfg["height"])

    # ---------- 下载源 ----------
    def _on_source_changed(self):
        self.ctx.config.download_source = self.source_cb.currentData() or "bmclapi"
        self.ctx.config.save()
        self.win.home.refresh()

    # ---------- 数据 ----------
    def _open_logs(self):
        d = os.path.join(self.ctx.base_dir, "logs")
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def _open_data(self):
        os.startfile(self.ctx.base_dir)
