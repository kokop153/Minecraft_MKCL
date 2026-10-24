# -*- coding: utf-8 -*-
"""模组下载页（PCL 风格）：「模组」与「整合包」两个模块。

- 模组：按关键词 / MC 版本 / 加载器搜索 Modrinth 上的单个模组，
  下载到指定游戏版本的 mods 目录（复用 launcher.download.DownloadManager）。
- 整合包：搜索 Modrinth 整合包（.mrpack），下载并解压导入为一个独立实例。
"""
import os
import tempfile

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QListWidget, QListWidgetItem, QProgressBar, QFrame,
    QMessageBox, QButtonGroup, QStackedWidget, QDialog, QFormLayout,
    QCheckBox,
)

from launcher import mods
from launcher.ui.workers import (
    ModSearchWorker, ModVersionsWorker, ModIconWorker, ModDepsWorker,
    ScanWorker, DownloadJob,
)


def _fmt_num(n: int) -> str:
    n = int(n or 0)
    if n >= 1_000_000:
        return "%.1fM" % (n / 1_000_000)
    if n >= 1_000:
        return "%.1fK" % (n / 1_000)
    return str(n)


def _type_label(t: str) -> str:
    return {"mod": "模组", "modpack": "整合包"}.get(t, t)


def _guess_loader(folder: str, game_dir: str) -> str:
    """从版本目录的 json id 猜测加载器。"""
    import json as _json
    jp = os.path.join(game_dir, "versions", folder, folder + ".json")
    if not os.path.isfile(jp):
        return ""
    try:
        with open(jp, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception:
        return ""
    vid = str(data.get("id") or "").lower()
    for k in ("neoforge", "forge", "fabric", "quilt", "liteloader"):
        if k in vid:
            return k
    return ""


# --------------------------------------------------------------------------
# 结果列表项（图标 + 标题 + 描述 + 元信息）
# --------------------------------------------------------------------------
class _ModItem(QWidget):
    def __init__(self, hit, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFixedSize(46, 46)
        self.icon.setStyleSheet("border-radius:9px;")
        row.addWidget(self.icon)

        col = QVBoxLayout()
        col.setSpacing(3)
        title = QLabel(hit["title"])
        title.setObjectName("cardTitle")
        desc = QLabel(hit["description"] or "—")
        desc.setObjectName("subText")
        desc.setWordWrap(True)
        desc.setMaximumHeight(32)
        cats = " · ".join(hit.get("categories") or [])[:40]
        meta_txt = "⬇ %s 下载 · %s · 支持 %d 个版本%s" % (
            _fmt_num(hit.get("downloads")),
            _type_label(hit.get("project_type")),
            len(hit.get("versions") or []),
            (" · " + cats) if cats else "",
        )
        meta = QLabel(meta_txt)
        meta.setObjectName("subText")
        col.addWidget(title)
        col.addWidget(desc)
        col.addWidget(meta)
        row.addLayout(col, 1)
        self._pid = hit.get("id")


# --------------------------------------------------------------------------
# 通用：搜索结果列表卡片
# --------------------------------------------------------------------------
class _SearchPanel(QWidget):
    selected = pyqtSignal(dict)

    def __init__(self, ctx, project_type, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.project_type = project_type
        self.hits = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        ctrl = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索%s…" % _type_label(self.project_type))
        self.search.returnPressed.connect(self.do_search)
        ctrl.addWidget(self.search, 1)

        self.mc_cb = QComboBox()
        for v in mods.QUICK_MC_VERSIONS:
            self.mc_cb.addItem("全部版本" if not v else v, v)
        ctrl.addWidget(self.mc_cb)

        if self.project_type == "mod":
            loaders = ("", "fabric", "forge", "quilt", "neoforge")
        else:
            loaders = ("", "fabric", "forge", "quilt", "neoforge")
        self.loader_cb = QComboBox()
        for k in loaders:
            self.loader_cb.addItem("全部加载器" if not k else k.capitalize(), k)
        ctrl.addWidget(self.loader_cb)

        self.search_btn = QPushButton("搜索")
        self.search_btn.setObjectName("primaryBtn")
        self.search_btn.clicked.connect(self.do_search)
        ctrl.addWidget(self.search_btn)
        root.addLayout(ctrl)

        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(10, 10, 10, 10)
        cv.setSpacing(6)
        self.list = QListWidget()
        self.list.setSpacing(2)
        self.list.currentItemChanged.connect(self._on_current)
        cv.addWidget(self.list, 1)
        self.info = QLabel("点击「搜索」开始浏览 Modrinth 资源")
        self.info.setObjectName("subText")
        cv.addWidget(self.info)
        root.addWidget(card, 1)

        self.search_worker = None
        self.icon_worker = None

    def do_search(self):
        game_dir = self.ctx.config.game_dir
        if not game_dir:
            QMessageBox.information(self, "提示", "请先在「设置」配置游戏目录。")
            return
        mc = self.mc_cb.currentData() or ""
        loader = self.loader_cb.currentData() or ""
        q = (self.search.text() or "").strip()
        self.info.setText("正在从 Modrinth 搜索%s…" % _type_label(self.project_type))
        self.search_btn.setEnabled(False)
        self.search_worker = ModSearchWorker(q, self.project_type, mc, loader, 0)
        self.search_worker.ok.connect(self._on_search_ok)
        self.search_worker.fail.connect(self._on_search_fail)
        self.search_worker.start()

    def _on_search_ok(self, hits, total):
        self.search_btn.setEnabled(True)
        self.hits = hits
        self.list.clear()
        if not hits:
            self.info.setText("没有找到匹配的%s。" % _type_label(self.project_type))
            return
        for h in hits:
            it = QListWidgetItem()
            widget = _ModItem(h)
            it.setSizeHint(widget.sizeHint())
            it.setData(Qt.UserRole, h)
            self.list.addItem(it)
            self.list.setItemWidget(it, widget)
        self.info.setText("共找到 %d 个%s" % (total, _type_label(self.project_type)))
        # 加载图标
        self.icon_worker = ModIconWorker(hits)
        self.icon_worker.ok.connect(self._on_icons)
        self.icon_worker.start()

    def _on_icons(self, icon_map):
        for i in range(self.list.count()):
            it = self.list.item(i)
            w = self.list.itemWidget(it)
            pid = it.data(Qt.UserRole).get("id")
            data = icon_map.get(pid)
            if not data or not w:
                continue
            img = QImage()
            if img.loadFromData(data):
                pix = QPixmap.fromImage(img).scaled(
                    46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                w.icon.setPixmap(pix)

    def _on_search_fail(self, msg):
        self.search_btn.setEnabled(True)
        self.list.clear()
        self.info.setText("搜索失败：%s" % msg)

    def _on_current(self, cur, _prev):
        if not cur:
            self.selected.emit({})
            return
        self.selected.emit(cur.data(Qt.UserRole) or {})

    def current_hit(self):
        it = self.list.currentItem()
        if not it:
            return {}
        return it.data(Qt.UserRole) or {}


# --------------------------------------------------------------------------
# 模组模块：下载单个模组到指定版本
# --------------------------------------------------------------------------
class ModsTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        self.search_panel = _SearchPanel(self.ctx, "mod", self)
        root.addWidget(self.search_panel, 3)

        # 下载卡片
        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(8)
        self.detail = QLabel("选中上方模组以查看下载选项")
        self.detail.setObjectName("subText")
        self.detail.setWordWrap(True)
        cv.addWidget(self.detail)

        dl_row = QHBoxLayout()
        dl_row.addWidget(QLabel("目标版本"))
        self.target_cb = QComboBox()
        self.target_cb.setMinimumWidth(180)
        dl_row.addWidget(self.target_cb, 1)
        self.dl_btn = QPushButton("下载到该版本")
        self.dl_btn.setObjectName("primaryBtn")
        self.dl_btn.setEnabled(False)
        self.dl_btn.clicked.connect(self._download)
        dl_row.addWidget(self.dl_btn)
        cv.addLayout(dl_row)

        self.dep_chk = QCheckBox("同时下载必需前置（如 Fabric API 等库依赖）")
        self.dep_chk.setChecked(True)
        cv.addWidget(self.dep_chk)

        # 进度
        self.status = QLabel("空闲")
        self.status.setObjectName("subText")
        cv.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        cv.addWidget(self.progress)
        cv.addWidget(self.cancel_btn)
        root.addWidget(card, 0)

        self.search_panel.selected.connect(self._on_selected)
        self.versions_worker = None
        self.deps_worker = None
        self.job = None
        self._targets = []
        self._mc = ""
        self._loader = ""
        self._main_items = []
        self._dep_items = []
        self._mods_folder = ""

    def load_targets(self):
        game_dir = self.ctx.config.game_dir
        self.target_cb.clear()
        self._targets = []
        if not game_dir:
            self.target_cb.addItem("（未配置游戏目录）")
            return
        self._scan_worker = ScanWorker(game_dir)
        self._scan_worker.ok.connect(self._on_scanned)
        self._scan_worker.fail.connect(lambda m: self.target_cb.addItem("（扫描失败）"))
        self._scan_worker.start()

    def _on_scanned(self, versions):
        self.target_cb.clear()
        self._targets = [v.folder for v in versions]
        for v in versions:
            self.target_cb.addItem(
                "%s（%s）" % (v.folder, v.mc_version), v.folder)

    def _on_selected(self, hit):
        if not hit:
            self.detail.setText("选中上方模组以查看下载选项")
            self.dl_btn.setEnabled(False)
            return
        cats = " · ".join(hit.get("categories") or [])
        ver = (hit.get("versions") or [])
        ver_txt = ("%s … %s" % (ver[0], ver[-1])) if ver else "—"
        self.detail.setText(
            "<b>%s</b><br>作者：%s　下载：%s　支持版本：%s%s" % (
                hit.get("title"), hit.get("author"),
                _fmt_num(hit.get("downloads")), ver_txt,
                ("<br>分类：" + cats) if cats else ""))
        self.dl_btn.setEnabled(bool(self.target_cb.currentData()))

    def _download(self):
        hit = self.search_panel.current_hit() if self.search_panel else {}
        if not hit:
            QMessageBox.information(self, "提示", "请先选择一个模组。")
            return
        folder = self.target_cb.currentData()
        if not folder:
            QMessageBox.information(self, "提示", "请先选择目标版本。")
            return
        game_dir = self.ctx.config.game_dir
        self._mc = self._mc_of(folder, game_dir)
        self._loader = _guess_loader(folder, game_dir)
        self.status.setText("正在解析 %s 的可用版本与前置依赖…" % hit.get("title"))
        self.dl_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.versions_worker = ModVersionsWorker(hit["id"], self._mc, self._loader)
        self.versions_worker.ok.connect(lambda vs: self._on_versions(hit, folder, vs))
        self.versions_worker.fail.connect(lambda m: self._fail(m))
        self.versions_worker.start()

    def _mc_of(self, folder, game_dir):
        import json as _json
        jp = os.path.join(game_dir, "versions", folder, folder + ".json")
        try:
            with open(jp, "r", encoding="utf-8") as f:
                return str(_json.load(f).get("id") or "")
        except Exception:
            return ""

    def _on_versions(self, hit, folder, versions):
        if not versions:
            self._fail("该模组没有兼容「%s」的版本，请换一个目标版本。"
                      % folder)
            return
        ver = versions[0]  # 已按发布时间倒序（API 默认）
        game_dir = self.ctx.config.game_dir
        pf = mods.resolve_mods_folder(
            game_dir, folder, self.ctx.config.per_version, self.ctx.config.auto_isolate)
        self._mods_folder = pf
        items = mods.build_mod_download_items(ver, pf)
        if not items:
            self._fail("该版本没有可下载的文件。")
            return
        self._main_items = items
        # 解析前置依赖（必需 + 可选）
        self.deps_worker = ModDepsWorker(ver, self._mc, self._loader, pf)
        self.deps_worker.ok.connect(
            lambda disp, dep_items: self._on_deps(hit, folder, items, disp, dep_items))
        self.deps_worker.fail.connect(
            lambda m: self._on_deps(hit, folder, items, [], []))
        self.deps_worker.start()

    def _on_deps(self, hit, folder, items, display, dep_items):
        self._dep_items = dep_items
        base = self.detail.text()
        if display:
            lines = "<br><b>前置依赖：</b>"
            for title, dtype in display:
                tag = "必需" if dtype == "required" else "可选"
                lines += "<br>· %s（%s）" % (title, tag)
        else:
            lines = "<br><b>前置依赖：</b>无"
        self.detail.setText(base + lines)

        all_items = list(items)
        if self.dep_chk.isChecked():
            all_items += dep_items
        if dep_items and self.dep_chk.isChecked():
            self.status.setText("正在下载 %s + %d 个必需前置 → %s/mods …" % (
                hit.get("title"), len(dep_items), folder))
        else:
            self.status.setText("正在下载 %s → %s/mods …" % (hit.get("title"), folder))
        self.progress.setRange(0, len(all_items))
        self.progress.setValue(0)
        self.cancel_btn.setEnabled(True)
        self._run_job(all_items)

    def _run_job(self, items):
        self.job = DownloadJob(source=self.ctx.config.download_source or "bmclapi")
        b = self.job.bridge
        b.progress.connect(self._on_progress)
        b.finished.connect(self._on_done)
        b.failed.connect(self._on_job_error)
        self.job.start(items)

    def _on_progress(self, done, total, name, pct):
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(done)
        self.status.setText("正在下载 %s（%d / %d）" % (name, done, total))

    def _on_done(self, ok_count, failed):
        self.cancel_btn.setEnabled(False)
        self.dl_btn.setEnabled(True)
        if not failed:
            msg = "模组已下载到该版本的 mods 目录"
            if self._dep_items and self.dep_chk.isChecked():
                msg += "（含 %d 个必需前置）" % len(self._dep_items)
            msg += "，启动对应版本即可生效。"
            self.status.setText("✅ 下载完成：%d 个文件已放入 mods 目录。" % ok_count)
            QMessageBox.information(self, "完成", msg)
        else:
            self.status.setText("⚠ 下载完成：%d 成功，%d 失败。" % (ok_count, len(failed)))
            first = failed[0]
            QMessageBox.warning(self, "部分失败",
                "%d 个文件下载失败。\n示例：%s" % (len(failed), first.get("dest")))

    def _on_job_error(self, msg):
        self.status.setText("下载出错：%s" % msg)
        self.cancel_btn.setEnabled(False)
        self.dl_btn.setEnabled(True)

    def _fail(self, msg):
        self.status.setText("⚠ " + msg)
        self.dl_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        QMessageBox.warning(self, "无法下载", msg)

    def _cancel(self):
        if self.job:
            self.job.cancel()
            self.status.setText("正在取消…")


# --------------------------------------------------------------------------
# 整合包模块：导入 .mrpack 为独立实例
# --------------------------------------------------------------------------
class ImportModpackDialog(QDialog):
    def __init__(self, name, targets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入整合包")
        self.resize(420, 160)
        form = QFormLayout(self)
        self.name_edit = QLineEdit(name)
        form.addRow("实例名称", self.name_edit)
        self.base_cb = QComboBox()
        for t in targets:
            self.base_cb.addItem(t, t)
        if not targets:
            self.base_cb.addItem("（请先准备一个加载器版本）")
        form.addRow("基础加载器版本", self.base_cb)
        tip = QLabel("整合包将继承所选加载器版本，并创建独立实例。")
        tip.setObjectName("subText")
        tip.setWordWrap(True)
        form.addRow(tip)
        row = QHBoxLayout()
        ok = QPushButton("开始导入")
        ok.setObjectName("primaryBtn")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(ok)
        row.addWidget(cancel)
        form.addRow(row)

    def result_data(self):
        return self.name_edit.text().strip(), self.base_cb.currentData()


class ModpackTab(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        self.search_panel = _SearchPanel(self.ctx, "modpack", self)
        root.addWidget(self.search_panel, 3)

        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(8)
        self.detail = QLabel("选中上方整合包以查看导入选项")
        self.detail.setObjectName("subText")
        self.detail.setWordWrap(True)
        cv.addWidget(self.detail)
        self.import_btn = QPushButton("导入为整合包客户端")
        self.import_btn.setObjectName("primaryBtn")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self._import)
        cv.addWidget(self.import_btn)
        self.status = QLabel("空闲")
        self.status.setObjectName("subText")
        cv.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        cv.addWidget(self.progress)
        root.addWidget(card, 0)

        self.search_panel.selected.connect(self._on_selected)
        self.versions_worker = None
        self.job = None
        self._targets = []

    def load_targets(self):
        game_dir = self.ctx.config.game_dir
        self._targets = []
        if not game_dir:
            return
        self._scan_worker = ScanWorker(game_dir)
        self._scan_worker.ok.connect(lambda vs: self._targets.__setitem__(
            slice(None), [v.folder for v in vs]))
        self._scan_worker.start()

    def _on_selected(self, hit):
        if not hit:
            self.detail.setText("选中上方整合包以查看导入选项")
            self.import_btn.setEnabled(False)
            return
        cats = " · ".join(hit.get("categories") or [])
        ver = (hit.get("versions") or [])
        ver_txt = ("%s … %s" % (ver[0], ver[-1])) if ver else "—"
        self.detail.setText(
            "<b>%s</b><br>作者：%s　下载：%s　支持版本：%s%s" % (
                hit.get("title"), hit.get("author"),
                _fmt_num(hit.get("downloads")), ver_txt,
                ("<br>分类：" + cats) if cats else ""))
        self.import_btn.setEnabled(True)

    def _import(self):
        hit = self.search_panel.current_hit() if self.search_panel else {}
        if not hit:
            return
        # 选版本
        self.versions_worker = ModVersionsWorker(hit["id"], None, None)
        self.versions_worker.ok.connect(lambda vs: self._on_pack_versions(hit, vs))
        self.versions_worker.fail.connect(
            lambda m: QMessageBox.warning(self, "失败", m))
        self.versions_worker.start()
        self.status.setText("正在获取整合包版本…")
        self.import_btn.setEnabled(False)

    def _on_pack_versions(self, hit, versions):
        self.import_btn.setEnabled(True)
        if not versions:
            QMessageBox.warning(self, "失败", "该整合包没有可下载的版本。")
            return
        ver = versions[0]
        dlg = ImportModpackDialog(hit.get("title", "modpack"), self._targets, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        name, base = dlg.result_data()
        if not name:
            QMessageBox.warning(self, "提示", "请输入实例名称。")
            return
        if not base:
            QMessageBox.warning(self, "提示",
                "请先在「下载」页准备一个对应的加载器（Forge/Fabric 等）版本作为基础。")
            return
        self._do_import(hit, ver, name, base)

    def _do_import(self, hit, ver, name, base):
        game_dir = self.ctx.config.game_dir
        new_folder = mods._sanitize(name)
        instance_root = os.path.join(game_dir, "versions", new_folder)
        if os.path.exists(instance_root):
            QMessageBox.warning(self, "提示", "实例文件夹已存在：%s" % new_folder)
            return
        # 取 primary 的 .mrpack 文件
        files = ver.get("files") or []
        mr = next((f for f in files if f.get("primary")), files[0] if files else None)
        if not mr or not mr.get("url"):
            QMessageBox.warning(self, "失败", "整合包版本缺少下载文件。")
            return
        self.status.setText("正在下载整合包 %s …" % ver["name"])
        self.progress.setRange(0, 0)  # 忙碌态
        try:
            tmp = os.path.join(tempfile.gettempdir(), new_folder + ".mrpack")
            mods.download_modpack_archive(mr["url"], tmp)
        except Exception as e:
            self.progress.setRange(0, 100)
            QMessageBox.critical(self, "下载失败", str(e))
            return
        try:
            items, index, mc, loader = mods.import_modpack(tmp, instance_root, base)
        except Exception as e:
            self.progress.setRange(0, 100)
            QMessageBox.critical(self, "导入失败", str(e))
            return
        mods.write_modpack_version_json(instance_root, new_folder, base, mc, loader)
        if not items:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.status.setText("✅ 整合包已导入（无额外需下载文件）。")
            self._finish_import(new_folder)
            return
        self.status.setText("正在下载整合包内嵌文件（%d 个）…" % len(items))
        self.progress.setRange(0, len(items))
        self.progress.setValue(0)
        self.job = DownloadJob(source=self.ctx.config.download_source or "bmclapi")
        b = self.job.bridge
        b.progress.connect(lambda d, t, n, p: (
            self.progress.setValue(d),
            self.status.setText("正在导入 %s（%d / %d）" % (n, d, t))))
        b.finished.connect(lambda ok, failed: self._on_import_done(
            new_folder, ok, failed, base))
        b.failed.connect(lambda m: self.status.setText("导入出错：%s" % m))
        self.job.start(items)

    def _on_import_done(self, new_folder, ok_count, failed, base):
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        if failed:
            self.status.setText("⚠ 整合包导入完成：%d 成功，%d 失败（部分文件可能需手动补齐）。"
                               % (ok_count, len(failed)))
            QMessageBox.warning(self, "部分失败",
                "%d 个内嵌文件下载失败，可在「版本」页补全或重试。" % len(failed))
        else:
            self.status.setText("✅ 整合包已导入为实例：%s（继承自 %s）。" % (new_folder, base))
            QMessageBox.information(self, "完成",
                "整合包已导入为独立实例「%s」。\n请到「版本选择」中设为当前版本并启动。"
                % new_folder)
        self._finish_import(new_folder)

    def _finish_import(self, new_folder):
        # 通知版本页刷新（通过父窗口）
        win = self.window()
        vp = getattr(win, "versions_page", None)
        if vp and hasattr(vp, "refresh"):
            vp.refresh()
