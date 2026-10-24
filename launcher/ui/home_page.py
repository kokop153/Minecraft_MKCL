# -*- coding: utf-8 -*-
"""主页：一键启动（可连续多次/多实例并行）、当前版本/账号卡片、游戏输出与状态。"""
import os
import time

from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QDesktopServices, QPainter, QLinearGradient, QColor,
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QProgressBar, QPlainTextEdit, QFrame, QMessageBox, QGraphicsOpacityEffect,
    QSpinBox,
)
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, QAbstractAnimation

from launcher.ui.workers import LaunchWorker, MultiLaunchWorker
from launcher.launch import auto_memory_gb, resolve_window_size


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
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 左侧半透明深色面板（PCL 式）----
        side = QWidget()
        side.setObjectName("sidePanel")
        side.setFixedWidth(272)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(20, 30, 20, 20)
        sv.setSpacing(6)

        self.avatar_btn = QPushButton("?")
        self.avatar_btn.setObjectName("avatarBtn")
        self.avatar_btn.setFixedSize(64, 64)
        self.avatar_btn.setCursor(Qt.PointingHandCursor)
        self.avatar_btn.setToolTip("点击管理账号")
        self.avatar_btn.clicked.connect(lambda: self.win.goto("settings"))
        av_row = QHBoxLayout()
        av_row.addStretch(1)
        av_row.addWidget(self.avatar_btn)
        av_row.addStretch(1)
        sv.addLayout(av_row)
        sv.addSpacing(10)

        self.side_name = QPushButton("未登录")
        self.side_name.setObjectName("sideGhost")
        self.side_name.setCursor(Qt.PointingHandCursor)
        self.side_name.setToolTip("点击管理账号")
        self.side_name.clicked.connect(lambda: self.win.goto("settings"))
        sv.addWidget(self.side_name, 0, Qt.AlignHCenter)

        self.side_sub = QLabel("离线验证 · MKCL")
        self.side_sub.setObjectName("sideSub")
        self.side_sub.setAlignment(Qt.AlignCenter)
        sv.addWidget(self.side_sub)

        sv.addStretch(1)

        # 复合启动按钮：大标题 + 版本小字
        self.launch_btn = QPushButton()
        self.launch_btn.setObjectName("bigLaunch")
        self.launch_btn.setMinimumHeight(72)
        self.launch_btn.setCursor(Qt.PointingHandCursor)
        self.launch_btn.setToolTip("启动当前选中的游戏版本")
        self.launch_btn.clicked.connect(self.on_launch)
        lb = QVBoxLayout(self.launch_btn)
        lb.setContentsMargins(8, 0, 8, 0)
        lb.setSpacing(2)
        self.launch_title = QLabel("启动游戏")
        self.launch_title.setObjectName("launchTitle")
        self.launch_title.setAlignment(Qt.AlignCenter)
        self.launch_sub = QLabel("未选择版本")
        self.launch_sub.setObjectName("launchSub")
        self.launch_sub.setAlignment(Qt.AlignCenter)
        lb.addStretch(1)
        lb.addWidget(self.launch_title)
        lb.addWidget(self.launch_sub)
        lb.addStretch(1)
        sv.addWidget(self.launch_btn)
        self._pulse_anim = None

        btns = QHBoxLayout()
        btns.setSpacing(10)
        b_ver = QPushButton("版本选择")
        b_ver.setObjectName("outlineBtn")
        b_ver.setCursor(Qt.PointingHandCursor)
        b_ver.clicked.connect(lambda: self.win.goto("versions"))
        b_set = QPushButton("启动设置")
        b_set.setObjectName("outlineBtn")
        b_set.setCursor(Qt.PointingHandCursor)
        b_set.clicked.connect(lambda: self.win.goto("settings"))
        btns.addWidget(b_ver, 1)
        btns.addWidget(b_set, 1)
        sv.addLayout(btns)

        root.addWidget(side)

        # ---- 右侧玻璃浮层 ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(20, 20, 20, 20)
        rv.setSpacing(16)

        # 问候头部
        self.greet = QLabel("欢迎回来")
        self.greet.setObjectName("heroGreet")
        rv.addWidget(self.greet)
        self.greet_sub = QLabel("准备开始今天的游戏之旅")
        self.greet_sub.setObjectName("heroGreetSub")
        rv.addWidget(self.greet_sub)
        rv.addSpacing(2)

        # 运行状态卡
        status_card = QFrame()
        status_card.setObjectName("glassCard")
        scv = QVBoxLayout(status_card)
        scv.setContentsMargins(18, 15, 18, 15)
        scv.setSpacing(10)
        st_row = QHBoxLayout()
        t1 = QLabel("运行状态")
        t1.setObjectName("cardTitle")
        st_row.addWidget(t1)
        st_row.addStretch(1)
        self.stop_all_btn = QPushButton("停止全部游戏")
        self.stop_all_btn.setObjectName("glassBtn")
        self.stop_all_btn.hide()
        self.stop_all_btn.clicked.connect(self._stop_all_games)
        st_row.addWidget(self.stop_all_btn)
        scv.addLayout(st_row)

        st_line = QHBoxLayout()
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(9, 9)
        self.status_dot.setStyleSheet("background:#9CA3AF;border-radius:4px;")
        st_line.addWidget(self.status_dot)
        self.status = QLabel("就绪")
        self.status.setObjectName("subText")
        self.status.setWordWrap(False)
        st_line.addWidget(self.status, 1)
        scv.addLayout(st_line)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # 忙碌态
        self.progress.hide()
        scv.addWidget(self.progress)

        # 信息行：单行省略号，避免长路径折行
        self.info_labels = {}
        for key in ("游戏目录", "Java 运行时", "内存分配", "下载源"):
            k = QLabel(key)
            k.setObjectName("subText")
            k.setFixedWidth(88)
            v = QLabel("—")
            v.setWordWrap(False)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setToolTip("")
            self.info_labels[key] = v
            line = QHBoxLayout()
            line.setSpacing(10)
            line.addWidget(k)
            line.addWidget(v, 1)
            scv.addLayout(line)

        multi_row = QHBoxLayout()
        ml = QLabel("并行客户端数")
        ml.setObjectName("subText")
        multi_row.addWidget(ml)
        self.multi_spin = QSpinBox()
        self.multi_spin.setRange(1, 6)
        self.multi_spin.setValue(1)
        self.multi_spin.setToolTip(
            "一次同时启动多个客户端（每实例独立目录与离线账号，实例 2 起账号名自动加序号）。\n"
            "启动后按钮不会被锁定，可以继续点击追加更多实例。")
        multi_row.addWidget(self.multi_spin)
        self.multi_hint = QLabel("启动后可继续点击叠加实例")
        self.multi_hint.setObjectName("subText")
        multi_row.addWidget(self.multi_hint, 1)
        scv.addLayout(multi_row)
        rv.addWidget(status_card)
        self._add_shadow(status_card)

        # 游戏输出卡
        log_card = QFrame()
        log_card.setObjectName("glassCard")
        lcv = QVBoxLayout(log_card)
        lcv.setContentsMargins(18, 15, 18, 15)
        lcv.setSpacing(10)
        t2 = QLabel("游戏输出")
        t2.setObjectName("cardTitle")
        lcv.addWidget(t2)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("homeLog")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        lcv.addWidget(self.log_view, 1)
        rv.addWidget(log_card, 1)
        self._add_shadow(log_card)

        root.addWidget(right, 1)

    def _add_shadow(self, card):
        """卡片柔和投影，增强浮层感。"""
        from PyQt5.QtWidgets import QGraphicsDropShadowEffect
        dark = (getattr(self.ctx.config, "theme_mode", "light") == "dark")
        eff = QGraphicsDropShadowEffect(card)
        eff.setBlurRadius(26)
        eff.setXOffset(0)
        eff.setYOffset(6)
        eff.setColor(QColor(0, 0, 0, 110) if dark else QColor(20, 28, 48, 36))
        card.setGraphicsEffect(eff)

    def _elide(self, text, px=460):
        from PyQt5.QtGui import QFontMetrics
        return QFontMetrics(self.font()).elidedText(
            str(text or ""), Qt.ElideMiddle, max(80, px))

    def paintEvent(self, event):
        """主页背景：明亮主题留白渐变 / 暗黑主题留黑渐变。"""
        p = QPainter(self)
        dark = (getattr(self.ctx.config, "theme_mode", "light") == "dark")
        top = QColor("#1A1D26") if dark else QColor("#F5F6FA")
        bottom = QColor("#0B0D12") if dark else QColor("#E3E8F0")
        g = QLinearGradient(0.0, 0.0, 0.0, float(self.height()))
        g.setColorAt(0.0, top)
        g.setColorAt(1.0, bottom)
        p.fillRect(self.rect(), g)

    # ---------- 活跃状态汇总 ----------
    def running_games(self) -> int:
        alive = sum(1 for w in self._workers if w.game_running())
        alive += sum(mw.alive_count() for mw in self._multi_workers)
        return alive

    def _update_activity(self, reset_status: bool = True):
        """根据 worker 列表刷新状态栏 / 呼吸灯 / 停止按钮。

        reset_status=False 时不覆盖状态栏文本（启动失败等场景需要
        保留错误信息，不被「就绪」抹掉）。
        """
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
            if alive == 0 and reset_status:
                self.status.setText("就绪")
        # 状态圆点：有游戏在跑 = 绿色，否则灰色
        self.status_dot.setStyleSheet(
            "background:%s;border-radius:4px;" % ("#22C55E" if alive else "#9CA3AF"))
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
        name = acc.name if acc else "未登录"
        self.avatar_btn.setText((name[0].upper() if acc else "?"))
        self.side_name.setText(name)
        self.side_sub.setText(("离线账号 · %s" % (acc.user_type or "legacy")) if acc
                              else "离线验证 · MKCL")
        self.greet.setText("欢迎回来，%s" % name)
        self.greet_sub.setText("今天想玩哪个版本？在下方启动，或前往「版本」切换。")
        self.launch_title.setText("启动游戏")
        self.launch_sub.setText(self._elide(ver, 200))
        self.launch_sub.setToolTip(ver)
        self.launch_btn.setToolTip("启动版本：%s" % ver)
        auto_iso = bool(cfg.auto_isolate)
        entry = (cfg.per_version or {}).get(cfg.current_version) or {}
        iso = entry["isolate"] if "isolate" in entry else auto_iso
        iso_text = "（版本隔离）" if iso else ""
        gd = (cfg.game_dir or "未设置") + iso_text
        self._set_info("游戏目录", gd)
        java = cfg.java_path if cfg.java_path else "自动选择（按版本智能匹配）"
        self._set_info("Java 运行时", java)
        if getattr(cfg, "memory_auto", False):
            self._set_info("内存分配", "%d GB（自动配置）" % auto_memory_gb())
        else:
            self._set_info("内存分配", "%d GB" % (cfg.memory_gb or 4))
        self._set_info("下载源",
            "BMCLAPI 国内镜像" if cfg.download_source == "bmclapi" else "Mojang 官方源")
        # 自定义信息：显示在启动器标题栏
        msg = (getattr(cfg, "custom_message", "") or "").strip()
        self.win.setWindowTitle("MKCL启动器" + (" · %s" % msg if msg else ""))
        # 启动按钮不因已有游戏运行而禁用（支持连续追加启动）

    def _set_info(self, key, full_text):
        v = self.info_labels.get(key)
        if not v:
            return
        v.setText(self._elide(full_text))
        v.setToolTip(full_text)

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

    def _launch_params(self, cfg):
        """按设置解析启动参数：内存（自动/自定义）、窗口模式、优先级、IP 偏好。"""
        if getattr(cfg, "memory_auto", False):
            mem = auto_memory_gb()
        else:
            mem = int(cfg.memory_gb or 4)
        w, h, fs = resolve_window_size(
            getattr(cfg, "window_size_mode", "default"),
            getattr(cfg, "window_width", 854),
            getattr(cfg, "window_height", 480))
        return {
            "memory_gb": int(mem),
            "width": w, "height": h, "fullscreen": fs,
            "priority": getattr(cfg, "process_priority", "normal") or "normal",
            "ip_preference": getattr(cfg, "ip_preference", "java") or "java",
        }

    def _apply_launcher_visibility(self):
        """游戏稳定运行后，按设置处理启动器自身：保持不变 / 最小化 / 退出。"""
        vis = getattr(self.ctx.config, "launcher_visibility", "keep")
        try:
            if vis == "minimize":
                self.win.showMinimized()
            elif vis == "exit":
                self.win._auto_exit = True
                self.win.close()
        except Exception:
            pass

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
        p = self._launch_params(cfg)
        w = LaunchWorker(
            game_dir=cfg.game_dir,
            folder=cfg.current_version,
            java_path=cfg.java_path if (cfg.java_path and os.path.isfile(cfg.java_path)) else "",
            memory_gb=p["memory_gb"],
            username=acc.name,
            uuid=acc.uuid,
            user_type=acc.user_type or "legacy",
            jvm_extra=cfg.jvm_extra_args or "",
            width=p["width"], height=p["height"],
            isolate_dir=isolate,
            instance_tag=instance_tag,
            base_dir=self.ctx.base_dir,
            priority=p["priority"],
            fullscreen=p["fullscreen"],
            ip_preference=p["ip_preference"],
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
        self._apply_launcher_visibility()

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
        # 保留「启动失败：…」状态文本，不被 _update_activity 重置为「就绪」
        self._update_activity(reset_status=False)

    # ---------- 多实例 ----------
    def _launch_multi(self, count):
        cfg = self.ctx.config
        acc = self.ctx.accounts.current()
        p = self._launch_params(cfg)
        mw = MultiLaunchWorker(
            base_dir=self.ctx.base_dir,
            game_dir=cfg.game_dir,
            folder=cfg.current_version,
            java_path=cfg.java_path if (cfg.java_path and os.path.isfile(cfg.java_path)) else "",
            count=count,
            memory_gb=p["memory_gb"],
            username=acc.name,
            jvm_extra=cfg.jvm_extra_args or "",
            width=p["width"], height=p["height"],
            priority=p["priority"],
            fullscreen=p["fullscreen"],
            ip_preference=p["ip_preference"],
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
