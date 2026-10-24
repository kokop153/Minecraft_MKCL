# -*- coding: utf-8 -*-
"""版本选择页：扫描列表、搜索、设为当前、隔离/共享目录、补全文件入口。"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QCheckBox, QMessageBox, QFrame,
)

from launcher.ui.workers import ScanWorker


class VersionsPage(QWidget):
    def __init__(self, ctx, win):
        super().__init__()
        self.ctx = ctx
        self.win = win
        self.versions = []
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("版本选择")
        title.setStyleSheet("font-size:17px;font-weight:600;")
        head.addWidget(title)
        head.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("subText")
        head.addWidget(self.count_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索版本…")
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(self._apply_filter)
        head.addWidget(self.search)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(self.refresh)
        head.addWidget(refresh)
        root.addLayout(head)

        # 列表卡片
        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(10)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._use_version)
        self.list.currentItemChanged.connect(lambda *_: self._update_detail())
        cv.addWidget(self.list, 1)

        detail = QLabel("选中版本以查看详情")
        detail.setObjectName("subText")
        detail.setWordWrap(True)
        self.detail = detail
        cv.addWidget(detail)

        # 标签缩短，解释文字移到 tooltip：长标签 minHint 892px 会顶宽布局
        self.isolate_cb = QCheckBox("为该版本使用隔离游戏目录")
        self.isolate_cb.setToolTip(
            "默认开启；saves/mods/config 独立存放，避免跨版本模组冲突")
        self.isolate_cb.toggled.connect(self._on_isolate_toggle)
        cv.addWidget(self.isolate_cb)

        btns = QHBoxLayout()
        self.btn_use = QPushButton("设为当前版本")
        self.btn_use.setObjectName("primaryBtn")
        self.btn_use.clicked.connect(self._use_version)
        self.btn_launch = QPushButton("启动此版本")
        self.btn_launch.clicked.connect(self._launch_version)
        self.btn_fix = QPushButton("补全缺失文件")
        self.btn_fix.setToolTip("扫描该版本缺失的库/资产/主 jar，并从下载源补全")
        self.btn_fix.clicked.connect(self._fix_files)
        self.btn_folder = QPushButton("打开版本文件夹")
        self.btn_folder.clicked.connect(self._open_folder)
        btns.addWidget(self.btn_use)
        btns.addWidget(self.btn_launch)
        btns.addWidget(self.btn_fix)
        btns.addWidget(self.btn_folder)
        btns.addStretch(1)
        cv.addLayout(btns)
        root.addWidget(card, 1)

        self.tip = QLabel("")
        self.tip.setObjectName("subText")
        self.tip.setWordWrap(True)
        root.addWidget(self.tip)

    # ---------- 数据 ----------
    def refresh(self):
        game_dir = self.ctx.config.game_dir
        if not game_dir:
            self.tip.setText("尚未设置游戏目录：请前往「设置」配置游戏目录后刷新。")
            self.list.clear()
            return
        self.tip.setText("正在扫描 %s …" % game_dir)
        self.btn_use.setEnabled(False)
        self.worker = ScanWorker(game_dir)
        self.worker.ok.connect(self._on_scanned)
        self.worker.fail.connect(self._on_scan_fail)
        self.worker.start()

    def _on_scanned(self, versions):
        self.versions = versions
        invalid = [v for v in versions if not v.valid]
        self.count_label.setText("共 %d 个版本（%d 个异常）" % (len(versions), len(invalid)))
        self._apply_filter()
        cur = self.ctx.config.current_version
        if cur:
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole) == cur:
                    self.list.setCurrentRow(i)
                    break
        self.tip.setText(
            "扫描完成。双击或点「设为当前版本」选用；「启动此版本」会临时以所选版本启动。"
            % ()
        )

    def _on_scan_fail(self, msg):
        self.list.clear()
        self.tip.setText("扫描失败：%s" % msg)

    def _apply_filter(self):
        kw = (self.search.text() or "").strip().lower()
        cur = self.ctx.config.current_version
        self.list.clear()
        for v in self.versions:
            text = v.folder
            if kw and kw not in text.lower():
                continue
            label = text
            if v.base:
                label += "　[继承自 %s]" % v.base
            if not v.valid:
                label += "　⚠ %s" % v.reason
            if text == cur:
                label += "　✓ 当前"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, text)
            self.list.addItem(it)

    def _selected(self):
        it = self.list.currentItem()
        if not it:
            return None
        folder = it.data(Qt.UserRole)
        return next((v for v in self.versions if v.folder == folder), None)

    def _update_detail(self):
        v = self._selected()
        if not v:
            self.detail.setText("选中版本以查看详情")
            self.btn_use.setEnabled(False)
            return
        self.btn_use.setEnabled(True)
        jar_ok = os.path.isfile(v.jar_path)
        size_kb = int(os.path.getsize(v.json_path) / 1024) if v.json_path and os.path.isfile(v.json_path) else 0
        self.detail.setText(
            "目录名：%s　|　游戏版本：%s　|　版本 JSON：%d KB　|　主 jar：%s"
            % (v.folder, v.mc_version, size_kb,
               "存在" if jar_ok else "缺失（可补全文件）")
        )
        iso_cfg = self.ctx.config.per_version or {}
        iso = bool(iso_cfg.get(v.folder, {}).get("isolate",
                   self.ctx.config.auto_isolate))
        self.isolate_cb.blockSignals(True)
        self.isolate_cb.setChecked(iso)
        self.isolate_cb.blockSignals(False)

    def _on_isolate_toggle(self, checked):
        v = self._selected()
        if not v:
            return
        pv = dict(self.ctx.config.per_version or {})
        entry = dict(pv.get(v.folder) or {})
        entry["isolate"] = bool(checked)
        pv[v.folder] = entry
        self.ctx.config.per_version = pv
        self.ctx.config.save()
        self.win.home.refresh()

    def _use_version(self, *_):
        v = self._selected()
        if not v:
            return
        if not v.valid:
            QMessageBox.warning(self, "无法选择", "该版本无效：%s" % v.reason)
            return
        self.ctx.config.current_version = v.folder
        self.ctx.config.save()
        self._apply_filter()
        # 重建列表后重新选中当前版本，保持上下文
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == v.folder:
                self.list.setCurrentRow(i)
                break
        self._update_detail()
        self.win.home.refresh()
        self.tip.setText("已将当前版本设为：%s" % v.folder)

    def _launch_version(self):
        self._use_version()
        if self.ctx.config.current_version == (self._selected().folder if self._selected() else ""):
            self.win.goto("home")
            self.win.home.on_launch()

    def _fix_files(self):
        v = self._selected()
        if not v:
            QMessageBox.information(self, "提示", "请先选中一个版本。")
            return
        if not self.ctx.config.game_dir:
            QMessageBox.warning(self, "提示", "请先设置游戏目录。")
            return
        self.win.goto("downloads")
        self.win.downloads.start_fix(v.folder)

    def _open_folder(self):
        v = self._selected()
        if not v:
            return
        d = os.path.join(self.ctx.config.game_dir, "versions", v.folder)
        if os.path.isdir(d):
            os.startfile(d)
