# -*- coding: utf-8 -*-
"""进程管理页：扫描本机 Minecraft（javaw/java）进程，一键停止指定进程。"""
import json
import os

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QCheckBox,
)

from launcher.ui.workers import ProcessScanWorker, KillWorker


class ProcessPage(QWidget):
    def __init__(self, ctx, win):
        super().__init__()
        self.ctx = ctx
        self.win = win
        self.scan_worker = None
        self.kill_worker = None
        self._rows = []
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("进程管理")
        title.setStyleSheet("font-size:17px;font-weight:600;")
        head.addWidget(title)
        head.addStretch(1)
        self.count_label = QLabel("—")
        self.count_label.setObjectName("subText")
        head.addWidget(self.count_label)
        self.auto_cb = QCheckBox("每 5 秒自动刷新")
        self.auto_cb.setChecked(True)
        self.auto_cb.toggled.connect(
            lambda on: self._timer.start() if on else self._timer.stop())
        head.addWidget(self.auto_cb)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh)
        head.addWidget(btn_refresh)
        root.addLayout(head)

        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(10)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["PID", "版本", "内存", "启动时间", "来源"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        cv.addWidget(self.table, 1)

        self.detail = QLabel("选中一行可查看完整命令行")
        self.detail.setObjectName("subText")
        self.detail.setWordWrap(True)
        self.table.itemSelectionChanged.connect(self._show_detail)
        cv.addWidget(self.detail)

        btns = QHBoxLayout()
        b_kill = QPushButton("停止选中进程")
        b_kill.setObjectName("primaryBtn")
        b_kill.clicked.connect(self._kill_selected)
        b_all = QPushButton("停止全部 Minecraft 进程")
        b_all.clicked.connect(self._kill_all)
        btns.addWidget(b_kill)
        btns.addWidget(b_all)
        btns.addStretch(1)
        cv.addLayout(btns)
        root.addWidget(card, 1)

        self.status = QLabel("空闲")
        self.status.setObjectName("subText")
        root.addWidget(self.status)

    # ---------- 数据 ----------
    def _mkcl_pids(self):
        """从启动台账收集本启动器拉起过的 PID -> 版本。"""
        d = os.path.join(self.ctx.base_dir, "logs", "launches")
        mapping = {}
        try:
            for name in os.listdir(d):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(d, name), "r", encoding="utf-8") as f:
                        rec = json.load(f)
                    pid = rec.get("pid")
                    if isinstance(pid, int):
                        mapping[pid] = rec.get("version") or "?"
                except (OSError, ValueError):
                    continue
        except OSError:
            pass
        return mapping

    def refresh(self):
        if self.scan_worker and self.scan_worker.isRunning():
            return
        self.scan_worker = ProcessScanWorker()
        self.scan_worker.ok.connect(self._on_scanned)
        self.scan_worker.fail.connect(self._on_scan_fail)
        self.scan_worker.start()

    def _on_scanned(self, rows):
        self._rows = rows
        mkcl = self._mkcl_pids()
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            ver = r.get("version") or "未识别"
            src = "MKCL 启动（%s）" % mkcl[r["pid"]] if r["pid"] in mkcl else "其他启动器"
            for col, text in enumerate((
                    str(r["pid"]), ver, "%.0f MB" % r["mem_mb"],
                    r["started"] or "—", src)):
                it = QTableWidgetItem(text)
                it.setData(Qt.UserRole, r)
                self.table.setItem(row, col, it)
        self.count_label.setText("共 %d 个 Java 进程" % len(rows))
        if rows:
            self.status.setText(
                "选中一行后点击「停止选中进程」；「停止全部」会结束列表内所有 Java 进程。")
        else:
            self.status.setText("当前没有运行中的 Minecraft 进程。")

    def _on_scan_fail(self, msg):
        self.status.setText("⚠ %s" % msg)

    def _selected_row(self):
        it = self.table.currentItem()
        if not it:
            return None
        return it.data(Qt.UserRole)

    def _show_detail(self):
        r = self._selected_row()
        if not r:
            return
        cl = r.get("cmdline") or ""
        self.detail.setText(("PID %s ｜ %s" % (r["pid"], cl))[:600] or "（无命令行）")

    # ---------- 停止 ----------
    def _kill_selected(self):
        r = self._selected_row()
        if not r:
            QMessageBox.information(self, "提示", "请先在表格中选中要停止的进程。")
            return
        if QMessageBox.question(
                self, "确认停止",
                "确定强制结束进程 PID %d（%s）吗？\n未保存的游戏进度会丢失。"
                % (r["pid"], r.get("version") or "未识别版本"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._run_kill([r["pid"]])

    def _kill_all(self):
        if not self._rows:
            QMessageBox.information(self, "提示", "当前没有可停止的 Minecraft 进程。")
            return
        pids = [r["pid"] for r in self._rows]
        if QMessageBox.question(
                self, "确认全部停止",
                "确定强制结束全部 %d 个 Minecraft 进程吗？\n未保存的游戏进度会丢失。"
                % len(pids),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._run_kill(pids)

    def _run_kill(self, pids):
        if self.kill_worker and self.kill_worker.isRunning():
            return
        self.status.setText("正在结束 %d 个进程…" % len(pids))
        self.kill_worker = KillWorker(pids)
        self.kill_worker.ok.connect(self._on_killed)
        self.kill_worker.fail.connect(lambda m: self.status.setText("⚠ " + m))
        self.kill_worker.start()

    def _on_killed(self, results):
        good = [p for p, s, _ in results if s]
        bad = [(p, m) for p, s, m in results if not s]
        self.status.setText(
            "已结束 %d 个进程%s" % (len(good),
                                  ("；失败：%s" % bad) if bad else ""))
        self.refresh()
