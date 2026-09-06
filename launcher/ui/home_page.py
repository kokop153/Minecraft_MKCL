# -*- coding: utf-8 -*-
"""主页：一键启动（可连续多次/多实例并行）、当前版本/账号卡片、游戏输出与状态。"""
import os
import time

from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QProgressBar, QPlainTextEdit, QFrame, QMessageBox, QGraphicsOpacityEffect,
    QSpinBox,
)
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QAbstractAnimation

from launcher.ui.workers import LaunchWorker, MultiLaunchWorker


def _card() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


class HomePage(QWidget):
    def __init__(self, ctx, win):
        super().__init__()
        self.ctx = ctx
        self.win = win
        self._workers = []        # 单实例 LaunchWorker 列表
        self._multi_workers = []  # 多实例 MultiLaunchWorker 列表
        self.launch_worker = None   # 兼容别名：最近一次的单实例 worker
        self.multi_worker = None    # 兼容别名：最近一次的多实例 worker
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        self.hello = QLabel("欢迎回来 👋")
        self.hello.setObjectName("cardTitle")
        self.hello.setStyleSheet("font-size:17px;")
        root.addWidget(self.hello)

        hero = _card()
        hv = QVBoxLayout(hero)
        hv.setContentsMargins(24, 22, 24, 22)
        hv.setSpacing(14)

        chips = QHBoxLayout()
        chips.setSpacing(12)

        self.ver_card = QPushButton("未选择版本\n点击前往「版本选择」")
        self.ver_card.setObjectName("sideBtn")
        self.ver_card.setMinimumHeight(58)
        self.ver_card.setMinimumWidth(260)
        self.ver_card.clicked.connect(lambda: self.win.goto("versions"))
        chips.addWidget(self.ver_card, 1)

        self.acc_card = QPushButton("未选择账号\n点击前往「设置 · 账号」")
        self.acc_card.setObjectName("sideBtn")
        self.acc_card.setMinimumHeight(58)
        self.acc_card.setMinimumWidth(260)
        self.acc_card.clicked.connect(lambda: self.win.goto("settings"))
        chips.addWidget(self.acc_card, 1)
        hv.addLayout(chips)

        self.launch_btn = QPushButton("启动游戏")
        self.launch_btn.setObjectName("bigLaunch")
        self.launch_btn.setMinimumHeight(74)
        self.launch_btn.setCursor(Qt.PointingHandCursor)
        self.launch_btn.clicked.connect(self.on_launch)
        hv.addWidget(self.launch_btn)
        self._pulse_anim = None

        multi_row = QHBoxLayout()
        self.multi_label = QLabel("并行客户端数")
        self.multi_label.setObjectName("subText")
        multi_row.addWidget(self.multi_label)
        self.multi_spin = QSpinBox()
        self.multi_spin.setRange(1, 6)
        self.multi_spin.setValue(1)
        self.multi_spin.setToolTip(
            "一次同时启动多个客户端（每实例独立目录与离线账号，实例 2 起账号名自动加序号）。\n"
            "启动后按钮不会被锁定，可以继续点击追加更多实例。")
        multi_row.addWidget(self.multi_spin)
        self.multi_hint = QLabel("启动后可继续点击叠加实例；每实例独立目录与账号")
        self.multi_hint.setObjectName("subText")
        multi_row.addWidget(self.multi_hint, 1)
        self.stop_all_btn = QPushButton("停止全部游戏")
        self.stop_all_btn.setObjectName("primaryBtn")
        self.stop_all_btn.hide()
        self.stop_all_btn.clicked.connect(self._stop_all_games)
        multi_row.addWidget(self.stop_all_btn)
        hv.addLayout(multi_row)

        self.status = QLabel("就绪")
        self.status.setObjectName("subText")
        self.status.setWordWrap(True)
        hv.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # 忙碌态
        self.progress.hide()
        hv.addWidget(self.progress)
        root.addWidget(hero)

        # 底部：游戏输出 + 信息
        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        out_card = _card()
        ov = QVBoxLayout(out_card)
        ov.setContentsMargins(18, 14, 18, 14)
        ov.setSpacing(8)
        t1 = QLabel("游戏输出")
        t1.setObjectName("cardTitle")
        ov.addWidget(t1)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        ov.addWidget(self.log_view, 1)
        bottom.addWidget(out_card, 3)

        info_card = _card()
        iv = QVBoxLayout(info_card)
        iv.setContentsMargins(18, 14, 18, 14)
        iv.setSpacing(8)
        t2 = QLabel("概要信息")
        t2.setObjectName("cardTitle")
        iv.addWidget(t2)
        self.info_labels = {}
        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        for i, key in enumerate(("游戏目录", "Java 运行时", "内存分配", "下载源")):
            k = QLabel(key)
            k.setObjectName("subText")
            v = QLabel("—")
            v.setWordWrap(True)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.info_labels[key] = v
            grid.addWidget(k, i, 0)
            grid.addWidget(v, i, 1)
        iv.addLayout(grid)
        iv.addStretch(1)
        btns = QHBoxLayout()
        b1 = QPushButton("打开游戏目录")
        b1.clicked.connect(self._open_game_dir)
        b2 = QPushButton("打开日志")
        b2.clicked.connect(self.win.open_log_dialog)
        btns.addWidget(b1)
        btns.addWidget(b2)
        iv.addLayout(btns)
        bottom.addWidget(info_card, 2)

        root.addLayout(bottom, 1)

    # ---------- 活跃状态汇总 ----------
    def running_games(self) -> int:
        alive = sum(1 for w in self._workers if w.game_running())
        alive += sum(mw.alive_count() for mw in self._multi_workers)
        return alive

    def _update_activity(self):
        """根据 worker 列表刷新状态栏 / 呼吸灯 / 停止按钮。"""
        n_single = sum(1 for w in self._workers if not getattr(w, "_finished", False))
        n_multi = len(self._multi_workers)
        alive = self.running_games()
        if n_single + n_multi > 0:
            self.stop_all_btn.show()
            if alive:
                self._start_pulse()
            self.progress.setVisible(
                any(not getattr(w, "_started_ok", True) for w in self._workers))
        else:
            self.stop_all_btn.hide()
            self._stop_pulse()
            self.progress.hide()
            if alive == 0:
                self.status.setText("就绪")
        return alive

    def _summary_text(self):
        alive = self.running_games()
        return "运行中的游戏：%d 个" % alive if alive else "就绪"

    def _cleanup_worker(self, w):
        if w in self._workers:
            self._workers.remove(w)
        setattr(w, "_finished", True)
        if self.launch_worker is w:
            self.launch_worker = self._workers[-1] if self._workers else None

    # ---------- 数据刷新 ----------
    def refresh(self):
        cfg = self.ctx.config
        acc = self.ctx.accounts.current()
        ver = cfg.current_version or "未选择版本"
        self.ver_card.setText("%s\n游戏版本 · 点击更换" % ver)
        self.acc_card.setText(
            (acc.name if acc else "未选择账号") + "\n离线账号 · 点击管理"
        )
        self.hello.setText(
            "欢迎回来，%s 👋" % (acc.name if acc else "玩家")
        )
        auto_iso = bool(cfg.auto_isolate)
        entry = (cfg.per_version or {}).get(cfg.current_version) or {}
        iso = entry["isolate"] if "isolate" in entry else auto_iso
        iso_text = "（版本隔离）" if iso else ""
        self.info_labels["游戏目录"].setText((cfg.game_dir or "未设置") + iso_text)
        self.info_labels["内存分配"].setText("%d GB" % (cfg.memory_gb or 4))
        self.info_labels["下载源"].setText(
            "BMCLAPI 国内镜像" if cfg.download_source == "bmclapi" else "Mojang 官方源"
        )
        self.info_labels["Java 运行时"].setText(
            cfg.java_path if cfg.java_path else "自动选择（按版本智能匹配）"
        )
        # 启动按钮不因已有游戏运行而禁用（支持连续追加启动）

    def _start_pulse(self):
        if self._pulse_anim is not None:
            return
        eff = QGraphicsOpacityEffect(self.launch_btn)
        self.launch_btn.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self.launch_btn)
        anim.setDuration(1300)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.5, 0.85)
        anim.setEndValue(1.0)
        anim.setLoopCount(-1)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.start(QAbstractAnimation.DeleteWhenStopped)
        self._pulse_anim = anim

    def _stop_pulse(self):
        if self._pulse_anim is not None:
            try:
                self._pulse_anim.stop()
            except Exception:
                pass
            self._pulse_anim = None
        self.launch_btn.setGraphicsEffect(None)

    def _check_config(self):
        cfg = self.ctx.config
        if not cfg.game_dir:
            QMessageBox.warning(self, "无法启动", "请先在「设置」中配置游戏目录。")
            return False
        if not cfg.current_version:
            QMessageBox.warning(self, "无法启动", "请先在「版本选择」页选择一个版本。")
            return False
        if self.ctx.accounts.current() is None:
            QMessageBox.warning(self, "无法启动", "请先在「设置 · 账号」中添加离线账号。")
            return False
        return True

    # ---------- 启动（可连续点击，每次一个新的游戏实例） ----------
    def on_launch(self):
        if not self._check_config():
            return
        count = int(self.multi_spin.value())
        if count > 1:
            self._launch_multi(count)
            return
        cfg = self.ctx.config
        acc = self.ctx.accounts.current()
        entry = (cfg.per_version or {}).get(cfg.current_version) or {}
        isolate = entry["isolate"] if "isolate" in entry else bool(cfg.auto_isolate)
        # 隔离模式下每次启动分配唯一隔离子目录，连续/并行启动互不冲突
        self._launch_seq = getattr(self, "_launch_seq", 0) + 1
        instance_tag = ("%s-%d" % (time.strftime("%H%M%S"), self._launch_seq)) if isolate else ""
        w = LaunchWorker(
            game_dir=cfg.game_dir,
            folder=cfg.current_version,
            java_path=cfg.java_path if (cfg.java_path and os.path.isfile(cfg.java_path)) else "",
            memory_gb=cfg.memory_gb or 4,
            username=acc.name,
            uuid=acc.uuid,
            user_type=acc.user_type or "legacy",
            jvm_extra=cfg.jvm_extra_args or "",
            width=854, height=480,
            isolate_dir=isolate,
            instance_tag=instance_tag,
            base_dir=self.ctx.base_dir,
        )
        w._started_ok = False
        w._stable_seen = False
        self._workers.append(w)
        self.launch_worker = w
        w.stage.connect(lambda s, wk=w: self._on_stage(wk, s))
        w.output.connect(self._on_output)
        w.started.connect(lambda pid, wk=w: self._on_started(wk, pid))
        w.stable.connect(lambda wk=w: self._on_stable(wk))
        w.exited.connect(lambda code, wk=w: self._on_exited(wk, code))
        w.fail.connect(lambda m, wk=w: self._on_fail(wk, m))
        w.start()
        self.status.setText("正在准备启动…")
        self._update_activity()

    def _on_stage(self, w, s):
        if w is self.launch_worker:
            self.status.setText(s)

    def _on_started(self, w, pid):
        w._started_ok = True
        self.log_view.appendPlainText("[启动器] 游戏已拉起，PID %d" % pid)
        self._update_activity()
        self.status.setText(self._summary_text())

    def _on_stable(self, w):
        w._stable_seen = True
        self.log_view.appendPlainText("[启动器] 游戏进程稳定运行中（>5s）")
        self._update_activity()
        self.status.setText(self._summary_text())

    def _on_exited(self, w, code):
        self._cleanup_worker(w)
        stable = getattr(w, "_stable_seen", False)
        if stable and code == 0:
            self.log_view.appendPlainText("[启动器] 游戏已正常退出（退出码 0）")
        elif stable:
            self.log_view.appendPlainText(
                "[启动器] 游戏已退出，退出码 %d，详见日志。" % code)
        else:
            self.log_view.appendPlainText(
                "[启动器] 游戏进程提前退出（退出码 %d），请查看日志排查。" % code)
            self.win.open_log_dialog()
        self._update_activity()
        self.status.setText(self._summary_text())

    def _on_fail(self, w, msg):
        self._cleanup_worker(w)
        self.status.setText("启动失败：%s" % msg)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("启动失败")
        box.setText(msg)
        if "Java" in msg or "java" in msg:
            box.setInformativeText("未检测到可用的 Java 运行时。点击「下载 Java」前往 Adoptium 获取，或在设置中手动指定路径。")
            btn_dl = box.addButton("下载 Java", QMessageBox.AcceptRole)
            box.addButton("知道了", QMessageBox.RejectRole)
            box.exec_()
            if box.clickedButton() is btn_dl:
                QDesktopServices.openUrl(QUrl("https://adoptium.net/temurin/releases/"))
        else:
            box.setInformativeText("详细信息已写入日志文件，可点击「打开日志」查看。")
            btn_log = box.addButton("打开日志", QMessageBox.ActionRole)
            box.addButton("知道了", QMessageBox.RejectRole)
            box.exec_()
            if box.clickedButton() is btn_log:
                self.win.open_log_dialog()
        self._update_activity()

    # ---------- 多实例 ----------
    def _launch_multi(self, count):
        cfg = self.ctx.config
        acc = self.ctx.accounts.current()
        mw = MultiLaunchWorker(
            base_dir=self.ctx.base_dir,
            game_dir=cfg.game_dir,
            folder=cfg.current_version,
            java_path=cfg.java_path if (cfg.java_path and os.path.isfile(cfg.java_path)) else "",
            count=count,
            memory_gb=cfg.memory_gb or 4,
            username=acc.name,
            jvm_extra=cfg.jvm_extra_args or "",
        )
        mw._started_all = False
        self._multi_workers.append(mw)
        self.multi_worker = mw
        mw.stage.connect(lambda s, m=mw: self._on_multi_stage(m, s))
        mw.instance_started.connect(
            lambda k, pid, m=mw: self._on_multi_started(m, k, pid))
        mw.instance_output.connect(
            lambda k, line, m=mw: self.log_view.appendPlainText(
                "[批次%d-实例%d] %s" % (self._multi_workers.index(m) + 1, k, line)))
        mw.instance_exited.connect(
            lambda k, c, m=mw: self.log_view.appendPlainText(
                "[启动器] 批次实例 %d 已退出（退出码 %d）" % (k, c)))
        mw.finished_all.connect(lambda alive, m=mw: self._on_multi_finished(m, alive))
        mw.fail.connect(lambda msg, m=mw: self._on_multi_fail(m, msg))
        mw.start()
        self.status.setText("准备多实例启动（%d 个）…" % count)
        self._update_activity()

    def _on_multi_stage(self, m, s):
        if m is self.multi_worker:
            self.status.setText(s)

    def _on_multi_started(self, m, k, pid):
        self.log_view.appendPlainText(
            "[启动器] 批次实例 %d 已拉起，PID %d" % (k, pid))
        self._update_activity()
        self.status.setText(self._summary_text())

    def _on_multi_finished(self, m, alive):
        if m in self._multi_workers:
            self._multi_workers.remove(m)
        if self.multi_worker is m:
            self.multi_worker = self._multi_workers[-1] if self._multi_workers else None
        self._update_activity()
        self.status.setText(self._summary_text())
        self.win.process_page.refresh()

    def _on_multi_fail(self, m, msg):
        if m in self._multi_workers:
            self._multi_workers.remove(m)
        self.status.setText("多实例启动失败：%s" % msg)
        self.win.open_log_dialog()
        self._update_activity()

    def _stop_all_games(self):
        total = self.running_games()
        if total == 0:
            QMessageBox.information(self, "提示", "当前没有运行中的游戏。")
            return
        if QMessageBox.question(
                self, "确认停止",
                "确定强制结束全部 %d 个运行中的游戏吗？\n未保存的游戏进度会丢失。" % total,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        for w in list(self._workers):
            w.terminate_game()
        for mw in list(self._multi_workers):
            mw.stop_all()
        self.status.setText("正在停止全部游戏…")
        self._update_activity()

    def _on_output(self, line):
        self.log_view.appendPlainText(line)

    def _open_game_dir(self):
        d = self.ctx.config.game_dir
        if d and os.path.isdir(d):
            os.startfile(d)

    # ---------- 生命周期（供主窗口关闭时调用） ----------
    def stop_watching(self):
        """关闭启动器：停止全部监控线程，游戏进程保持运行。"""
        for w in list(self._workers):
            try:
                w.stop_watch()
            except Exception:
                pass
        for mw in list(self._multi_workers):
            try:
                mw.detach()
            except Exception:
                pass
        self._workers.clear()
        self._multi_workers.clear()
