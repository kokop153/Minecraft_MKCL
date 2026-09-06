# -*- coding: utf-8 -*-
"""下载页：版本清单浏览、下载版本、补全缺失文件、进度与重试。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QComboBox, QProgressBar, QFrame,
    QMessageBox, QInputDialog,
)

from launcher import meta
from launcher.ui.workers import (
    ManifestWorker, VersionJsonDownloadWorker, CollectItemsWorker, DownloadJob,
)

_TYPE_LABEL = {"release": "正式版", "snapshot": "快照", "old_alpha": "远古 Alpha",
               "old_beta": "远古 Beta"}


class DownloadsPage(QWidget):
    def __init__(self, ctx, win):
        super().__init__()
        self.ctx = ctx
        self.win = win
        self.manifest_versions = []
        self.manifest_worker = None
        self.json_worker = None
        self.collect_worker = None
        self.job = None
        self._fix_folder = ""
        self._failed_items = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("下载")
        title.setStyleSheet("font-size:17px;font-weight:600;")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(QLabel("下载源"))
        self.source_cb = QComboBox()
        self.source_cb.addItem("BMCLAPI 国内镜像", "bmclapi")
        self.source_cb.addItem("Mojang 官方源", "official")
        idx = self.source_cb.findData(self.ctx.config.download_source or "bmclapi")
        self.source_cb.setCurrentIndex(max(0, idx))
        self.source_cb.currentIndexChanged.connect(self._on_source_changed)
        head.addWidget(self.source_cb)
        head.addWidget(QLabel("类型"))
        self.type_cb = QComboBox()
        for label, data in (("全部", ""), ("正式版", "release"), ("快照", "snapshot"),
                            ("远古版", "old")):
            self.type_cb.addItem(label, data)
        self.type_cb.currentIndexChanged.connect(lambda *_: self._apply_filter())
        head.addWidget(self.type_cb)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索版本号…")
        self.search.setFixedWidth(180)
        self.search.textChanged.connect(lambda *_: self._apply_filter())
        head.addWidget(self.search)
        self.refresh_btn = QPushButton("刷新清单")
        self.refresh_btn.clicked.connect(self.refresh)
        head.addWidget(self.refresh_btn)
        root.addLayout(head)

        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(10)
        self.list = QListWidget()
        self.list.setAlternatingRowColors(False)
        cv.addWidget(self.list, 1)
        self.list_info = QLabel("清单未加载")
        self.list_info.setObjectName("subText")
        cv.addWidget(self.list_info)
        dl_btns = QHBoxLayout()
        self.dl_btn = QPushButton("下载所选版本")
        self.dl_btn.setObjectName("primaryBtn")
        self.dl_btn.clicked.connect(self._download_selected)
        self.fix_cur_btn = QPushButton("补全当前版本文件")
        self.fix_cur_btn.setToolTip("检查当前版本缺失的库/资产/主 jar 并补全")
        self.fix_cur_btn.clicked.connect(self._fix_current)
        dl_btns.addWidget(self.dl_btn)
        dl_btns.addWidget(self.fix_cur_btn)
        dl_btns.addStretch(1)
        cv.addLayout(dl_btns)
        root.addWidget(card, 1)

        # 进度卡片
        prog_card = QFrame()
        prog_card.setObjectName("card")
        pv = QVBoxLayout(prog_card)
        pv.setContentsMargins(14, 12, 14, 12)
        pv.setSpacing(8)
        self.status = QLabel("空闲")
        self.status.setObjectName("subText")
        pv.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        pv.addWidget(self.progress)
        cancel_row = QHBoxLayout()
        self.cancel_btn = QPushButton("取消下载")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        self.retry_btn = QPushButton("重试失败项")
        self.retry_btn.setEnabled(False)
        self.retry_btn.clicked.connect(self._retry_failed)
        cancel_row.addWidget(self.cancel_btn)
        cancel_row.addWidget(self.retry_btn)
        cancel_row.addStretch(1)
        pv.addLayout(cancel_row)
        root.addWidget(prog_card)

    # ---------- 清单 ----------
    def refresh(self):
        source = self.source_cb.currentData() or "bmclapi"
        self.list_info.setText("正在从 %s 获取版本清单…" % (
            "BMCLAPI" if source == "bmclapi" else "Mojang 官方源"))
        self.refresh_btn.setEnabled(False)
        self.manifest_worker = ManifestWorker(source)
        self.manifest_worker.ok.connect(self._on_manifest)
        self.manifest_worker.fail.connect(self._on_manifest_fail)
        self.manifest_worker.start()

    def _on_manifest(self, manifest):
        self.refresh_btn.setEnabled(True)
        self.manifest_versions = list(meta.iter_manifest_versions(manifest))
        self._apply_filter()
        self.list_info.setText("清单获取成功：共 %d 个版本" % len(self.manifest_versions))

    def _on_manifest_fail(self, msg):
        self.refresh_btn.setEnabled(True)
        self.list.clear()
        self.list_info.setText("清单获取失败：%s（可切换下载源后重试）" % msg)
        self.status.setText("⚠ 清单获取失败：%s" % msg)

    def _apply_filter(self):
        kw = (self.search.text() or "").strip().lower()
        tsel = self.type_cb.currentData() or ""
        self.list.clear()
        for v in self.manifest_versions:
            vid = v.get("id") or ""
            vtype = v.get("type") or ""
            if kw and kw not in vid.lower():
                continue
            if tsel == "old":
                if vtype not in ("old_alpha", "old_beta"):
                    continue
            elif tsel and vtype != tsel:
                continue
            label = "%s　%s　%s" % (
                vid,
                _TYPE_LABEL.get(vtype, vtype),
                (v.get("releaseTime") or "")[:10],
            )
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, v)
            self.list.addItem(it)

    # ---------- 下载版本 json ----------
    def _download_selected(self):
        it = self.list.currentItem()
        if not it:
            QMessageBox.information(self, "提示", "请先在列表中选择一个版本。")
            return
        if self._busy():
            return
        v = it.data(Qt.UserRole)
        game_dir = self.ctx.config.game_dir
        if not game_dir:
            QMessageBox.warning(self, "提示", "请先在设置中配置游戏目录。")
            return
        source = self.source_cb.currentData() or "bmclapi"
        vid = v.get("id")
        self._set_busy("正在下载版本 %s 的 JSON…" % vid, busy=True)
        self.json_worker = VersionJsonDownloadWorker(v, source, game_dir)
        self.json_worker.ok.connect(self._on_json_ok)
        self.json_worker.fail.connect(self._on_json_fail)
        self.json_worker.start()

    def _on_json_ok(self, json_path):
        self.status.setText("版本 JSON 已下载：%s" % json_path)
        folder = None
        with open(json_path, "r", encoding="utf-8") as f:
            import json as _json
            folder = (_json.load(f).get("id")) or None
        if not folder:
            import os
            folder = os.path.basename(os.path.dirname(json_path))
        self.win.versions_page.refresh()
        self._start_fix(folder)

    def _on_json_fail(self, msg):
        self._set_busy("下载失败：%s" % msg, busy=False)
        QMessageBox.critical(self, "下载失败", msg + "\n\n可切换下载源后重试。")

    # ---------- 补全文件 ----------
    def _fix_current(self):
        folder = self.ctx.config.current_version
        if not folder:
            QMessageBox.information(self, "提示", "尚未选择当前版本。")
            return
        if self._busy():
            return
        self._start_fix(folder)

    def start_fix(self, folder):
        """供版本页调用：补全指定版本文件。"""
        if self._busy():
            QMessageBox.information(self, "提示", "已有下载任务进行中，请等待完成或取消。")
            return
        self._start_fix(folder)

    def _start_fix(self, folder):
        game_dir = self.ctx.config.game_dir
        source = self.source_cb.currentData() or "bmclapi"
        self._fix_folder = folder
        self._set_busy("正在分析版本 %s 的文件完整性…" % folder, busy=True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.collect_worker = CollectItemsWorker(game_dir, folder, source)
        self.collect_worker.ok.connect(self._on_collect)
        self.collect_worker.fail.connect(self._on_collect_fail)
        self.collect_worker.start()

    def _on_collect(self, missing, total):
        if not missing:
            self._set_busy("✅ 版本 %s 的 %d 个文件全部就绪，无需补全。" % (self._fix_folder, total),
                           busy=False)
            return
        self._failed_items = missing
        self.status.setText(
            "版本 %s 共 %d 个文件，其中 %d 个缺失/损坏，开始下载…" % (self._fix_folder, total, len(missing))
        )
        self.progress.setRange(0, len(missing))
        self.progress.setValue(0)
        self.cancel_btn.setEnabled(True)
        self.job = DownloadJob(source=self.source_cb.currentData() or "bmclapi")
        b = self.job.bridge
        b.progress.connect(self._on_progress)
        b.finished.connect(self._on_done)
        b.failed.connect(self._on_job_error)
        self.job.start(missing)

    def _on_collect_fail(self, msg):
        self._set_busy("分析失败：%s" % msg, busy=False)
        QMessageBox.critical(self, "分析失败", msg)

    def _on_progress(self, done, total, name, pct):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.status.setText("正在下载 %s（%d / %d）" % (name, done, total))

    def _on_done(self, ok_count, failed):
        self.cancel_btn.setEnabled(False)
        if not failed:
            self._set_busy("✅ 下载完成：%d 个文件全部成功。" % ok_count, busy=False)
            self.retry_btn.setEnabled(False)
            self.win.versions_page.refresh()
            return
        self._set_busy(
            "⚠ 下载完成：%d 成功，%d 失败。可点击「重试失败项」。" % (ok_count, len(failed)),
            busy=False,
        )
        self._failed_items = failed
        self.retry_btn.setEnabled(True)
        self.win.versions_page.refresh()
        first = failed[0]
        QMessageBox.warning(
            self, "部分下载失败",
            "%d 个文件下载失败。\n示例：%s\n错误：%s" % (
                len(failed), first.get("dest") or "", first.get("error") or ""),
        )

    def _on_job_error(self, msg):
        self._set_busy("下载出错：%s" % msg, busy=False)
        self.cancel_btn.setEnabled(False)

    def _retry_failed(self):
        items = getattr(self, "_failed_items", None)
        if not items or self._busy():
            return
        self.status.setText("重试 %d 个失败文件…" % len(items))
        self.progress.setRange(0, len(items))
        self.progress.setValue(0)
        self.cancel_btn.setEnabled(True)
        self.job = DownloadJob(source=self.source_cb.currentData() or "bmclapi")
        b = self.job.bridge
        b.progress.connect(self._on_progress)
        b.finished.connect(self._on_done)
        b.failed.connect(self._on_job_error)
        self.job.start(items)
        self.retry_btn.setEnabled(False)

    def _cancel(self):
        if self.job:
            self.job.cancel()
            self.status.setText("正在取消…")

    # ---------- 辅助 ----------
    def _busy(self):
        running = (self.json_worker and self.json_worker.isRunning()) or \
                  (self.collect_worker and self.collect_worker.isRunning()) or \
                  (self.job and self.job.is_running())
        if running:
            QMessageBox.information(self, "提示", "已有下载任务进行中，请等待完成或取消。")
        return bool(running)

    def _set_busy(self, text, busy):
        self.status.setText(text)
        self.dl_btn.setEnabled(not busy)
        self.fix_cur_btn.setEnabled(not busy)
        if not busy:
            self.cancel_btn.setEnabled(False)
            self.progress.setRange(0, 100)
            if "✅" not in text and "⚠" not in text and "全部就绪" not in text:
                self.progress.setValue(0)

    def _on_source_changed(self):
        self.ctx.config.download_source = self.source_cb.currentData() or "bmclapi"
        self.ctx.config.save()
        self.refresh()
        self.win.home.refresh()
