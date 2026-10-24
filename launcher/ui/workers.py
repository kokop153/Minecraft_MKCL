# -*- coding: utf-8 -*-
"""后台工作线程：扫描 / Java 检测 / 清单 / 下载桥 / 启动 / 进程管理。"""
import json
import logging
import os
import time

from PyQt5.QtCore import QThread, pyqtSignal, QObject

from launcher.errors import LauncherError
from launcher.version_scan import scan_versions
from launcher.java_utils import find_javas
from launcher.accounts import offline_uuid
from launcher.launch import (
    build_launch_command,
    launch_game,
    resolve_java_for_launch,
    derive_mc_version_for,
    validate_jvm_heap,
    effective_heap_gb,
    begin_launch_record,
    update_launch_record,
    finish_launch_record,
    prune_launch_records,
)
from launcher import meta
from launcher import mods
from launcher import modloaders


def _err_text(e: Exception) -> str:
    return str(e) if isinstance(e, LauncherError) else "%s: %s" % (type(e).__name__, e)


class ScanWorker(QThread):
    """扫描版本目录。"""
    ok = pyqtSignal(object)      # list[VersionInfo]
    fail = pyqtSignal(str)

    def __init__(self, game_dir, parent=None):
        super().__init__(parent)
        self.game_dir = game_dir

    def run(self):
        try:
            self.ok.emit(scan_versions(self.game_dir))
        except Exception as e:
            logging.error("版本扫描失败：%s ｜ detail: %s", e, getattr(e, "detail", ""))
            self.fail.emit(_err_text(e))


class JavaScanWorker(QThread):
    """探测系统 Java。"""
    ok = pyqtSignal(object)      # list[JavaRuntime]
    fail = pyqtSignal(str)

    def run(self):
        try:
            self.ok.emit(find_javas())
        except Exception as e:
            logging.error("Java 检测失败：%s", _err_text(e))
            self.fail.emit(_err_text(e))


class ManifestWorker(QThread):
    """获取下载源版本清单。"""
    ok = pyqtSignal(object)      # manifest dict
    fail = pyqtSignal(str)

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = source

    def run(self):
        try:
            self.ok.emit(meta.fetch_version_manifest(self.source))
        except Exception as e:
            logging.error("清单获取失败（%s）：%s ｜ detail: %s",
                          self.source, e, getattr(e, "detail", ""))
            self.fail.emit(_err_text(e))


class CollectItemsWorker(QThread):
    """收集某版本缺失下载项（补全文件）。"""
    ok = pyqtSignal(object, int)   # (missing_items, total_items)
    fail = pyqtSignal(str)

    def __init__(self, game_dir, folder, source, parent=None):
        super().__init__(parent)
        self.game_dir = game_dir
        self.folder = folder
        self.source = source

    def run(self):
        try:
            items = meta.collect_download_items(self.game_dir, self.folder, self.source)
        except Exception as e:
            logging.error("收集下载清单失败（%s）：%s", self.folder, _err_text(e))
            self.fail.emit("收集下载清单失败：%s（%s）" % (e, type(e).__name__))
            return
        missing = []
        import os
        for it in items:
            dest = it.get("dest") or ""
            if dest and not (os.path.isfile(dest) and meta.sha1_ok(dest, it.get("sha1", ""))):
                missing.append(it)
        self.ok.emit(missing, len(items))


class DownloadBridge(QObject):
    """把 DownloadManager 的线程回调转成 Qt 信号。"""
    progress = pyqtSignal(int, int, str, float)
    finished = pyqtSignal(int, list)
    failed = pyqtSignal(str)


class DownloadJob(QObject):
    """一次下载任务的桥接：download(items) 后信号驱动 UI。"""

    def __init__(self, source="bmclapi", parent=None):
        super().__init__(parent)
        self.source = source
        self.manager = None
        self.bridge = DownloadBridge()

    def start(self, items):
        from launcher.download import DownloadManager
        self.manager = DownloadManager(source=self.source, max_workers=6)
        b = self.bridge
        self.manager.download(
            items,
            progress=lambda d, t, n, p: b.progress.emit(d, t, n, p),
            done=lambda ok, failed: b.finished.emit(ok, failed),
            error=lambda e: b.failed.emit(str(e)),
        )

    def cancel(self):
        if self.manager:
            self.manager.cancel()

    def is_running(self):
        return bool(self.manager and self.manager.is_running())


class VersionJsonDownloadWorker(QThread):
    """下载某版本的 json 到游戏目录。"""
    ok = pyqtSignal(str)         # json path
    fail = pyqtSignal(str)

    def __init__(self, meta_item, source, game_dir, parent=None):
        super().__init__(parent)
        self.item = meta_item
        self.source = source
        self.game_dir = game_dir

    def run(self):
        try:
            self.ok.emit(meta.download_version(self.item, self.source, self.game_dir))
        except Exception as e:
            logging.error("版本 json 下载失败：%s ｜ detail: %s",
                          e, getattr(e, "detail", ""))
            self.fail.emit(_err_text(e))


class ProcessScanWorker(QThread):
    """扫描本机 javaw/java 进程（进程管理页）。"""
    ok = pyqtSignal(list)      # [{pid,name,mem_mb,started,cmdline,version,mkcl}]
    fail = pyqtSignal(str)

    _PS = (
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
        "$ErrorActionPreference='SilentlyContinue';"
        "Get-CimInstance Win32_Process -Filter \"Name='javaw.exe' OR Name='java.exe'\" | "
        "Select-Object ProcessId,Name,CommandLine,CreationDate,WorkingSetSize | "
        "ConvertTo-Json -Compress -Depth 3"
    )

    @staticmethod
    def _version_from_cmdline(cl):
        import re
        hits = re.findall(r"versions[/\\]+([^\\/\"']+?)[/\\]+", cl or "")
        return hits[-1] if hits else ""

    def run(self):
        import subprocess as sp
        try:
            r = sp.run(["powershell", "-NoProfile", "-Command", self._PS],
                       capture_output=True, timeout=20)
            raw = r.stdout.decode("utf-8", errors="replace").strip()
            data = json.loads(raw) if raw else []
        except Exception as e:
            self.fail.emit("进程扫描失败：%s" % _err_text(e))
            return
        if isinstance(data, dict):
            data = [data]
        rows = []
        for d in data or []:
            if not isinstance(d, dict):
                continue
            try:
                pid = int(d.get("ProcessId") or 0)
            except (TypeError, ValueError):
                continue
            cl = str(d.get("CommandLine") or "")
            rows.append({
                "pid": pid,
                "name": str(d.get("Name") or "java"),
                "mem_mb": round((int(d.get("WorkingSetSize") or 0) / 1048576), 1),
                "started": str(d.get("CreationDate") or "")[:19].replace("T", " "),
                "cmdline": cl,
                "version": self._version_from_cmdline(cl),
            })
        rows.sort(key=lambda x: x["pid"])
        self.ok.emit(rows)


class KillWorker(QThread):
    """taskkill 强制结束指定 PID 列表。"""
    ok = pyqtSignal(list)      # [(pid, success, msg)]
    fail = pyqtSignal(str)

    def __init__(self, pids, parent=None):
        super().__init__(parent)
        self.pids = list(pids or [])

    def run(self):
        import subprocess as sp
        results = []
        for pid in self.pids:
            try:
                r = sp.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=15)
                good = (r.returncode == 0)
                msg = (r.stdout or r.stderr).decode("utf-8", "replace").strip()[:120]
                results.append((pid, good, msg))
                logging.info("结束进程 PID=%s -> %s", pid, "成功" if good else msg)
            except Exception as e:
                results.append((pid, False, _err_text(e)))
        self.ok.emit(results)


class MultiLaunchWorker(QThread):
    """多实例并行启动：每实例独立 gameDir（versions/<v>/multi-<批次>-<k>）与独立离线账号。"""
    import itertools
    _BATCH_SEQ = itertools.count(1)
    stage = pyqtSignal(str)
    instance_started = pyqtSignal(int, int)     # idx(1-based), pid
    instance_output = pyqtSignal(int, str)      # idx, line
    instance_exited = pyqtSignal(int, int)      # idx, code
    finished_all = pyqtSignal(int)              # 存活数
    fail = pyqtSignal(str)

    def __init__(self, base_dir, game_dir, folder, java_path, count,
                 memory_gb, username, jvm_extra="", width=854, height=480,
                 priority="normal", fullscreen=False, ip_preference="java",
                 parent=None):
        super().__init__(parent)
        self._base_dir = base_dir
        self._args = (game_dir, folder, java_path, max(1, int(count)),
                      memory_gb, username, jvm_extra, width, height,
                      str(priority or "normal"), bool(fullscreen),
                      str(ip_preference or "java"))
        self._procs = []      # [(idx, GameProcess, rec_path)]
        self._stop = False

    def stop_all(self):
        self._stop = True
        for idx, gp, rec in list(self._procs):
            try:
                if gp.poll() is None:
                    gp.terminate()
                    finish_launch_record(rec, status="stopped", exit_code=gp.poll())
            except Exception:
                pass

    def detach(self):
        """关闭启动器时调用：停止监控，但游戏进程继续独立运行。"""
        self._stop = True
        for idx, gp, rec in list(self._procs):
            if gp.poll() is None:
                finish_launch_record(rec, status="detached")

    def alive_count(self):
        return sum(1 for _i, gp, _r in self._procs if gp.poll() is None)

    def run(self):
        game_dir, folder, java_path, count, memory_gb, username, \
            jvm_extra, width, height, priority, fullscreen, ip_preference = self._args
        base_dir = self._base_dir
        batch = next(MultiLaunchWorker._BATCH_SEQ)

        def tag_for(k):
            return "%s-%d" % (batch, k)
        try:
            self.stage.emit("正在检测 Java 运行时…")
            java_path = resolve_java_for_launch(game_dir, folder, java_path)
            self.stage.emit("使用 Java：%s" % java_path)
            self._java = java_path
            # 启动前验证 -Xmx：失败给中文提示，避免 JVM 弹系统原生错误框
            validate_jvm_heap(java_path, effective_heap_gb(java_path, memory_gb))

            for k in range(1, count + 1):
                if self._stop:
                    break
                self.stage.emit("正在启动第 %d / %d 个实例…" % (k, count))
                uname = username if k == 1 else (username + str(k))[:16]
                uuid_k = offline_uuid(uname)
                tag = tag_for(k)
                cmd = build_launch_command(
                    game_dir, folder, java_path,
                    memory_gb=memory_gb, username=uname, uuid=uuid_k,
                    user_type="legacy", jvm_extra=jvm_extra,
                    width=width, height=height,
                    isolate_dir=True, instance_tag=tag,
                    fullscreen=fullscreen, ip_preference=ip_preference,
                )
                cmd["priority"] = priority
                rec = begin_launch_record(self._base_dir, folder)
                update_launch_record(rec, instance=k, mc_version=derive_mc_version_for(game_dir, folder),
                                     java=java_path, command=cmd["command"],
                                     workdir=cmd["workdir"],
                                     natives_dir=cmd["natives_dir"],
                                     classpath_entries=len(cmd["classpath"].split(";")) if cmd.get("classpath") else 0,
                                     missing_libs=len(cmd.get("missing_libs") or []),
                                     username=uname, status="built")
                gp = launch_game(cmd, on_output=lambda line, kk=k: self.instance_output.emit(kk, line))
                self._procs.append((k, gp, rec))
                self.instance_started.emit(k, gp._proc.pid)
                update_launch_record(rec, pid=gp._proc.pid, status="running")
                if k < count:
                    time.sleep(1.0)   # 错峰启动，避免同盘 IO 风暴

            if self._stop:
                self.finished_all.emit(self.alive_count())
                return

            self.stage.emit("全部实例已拉起，监控中…")
            exited_set = set()
            while not self._stop:
                for idx, gp, rec in self._procs:
                    if idx in exited_set:
                        continue
                    code = gp.poll()
                    if code is not None:
                        exited_set.add(idx)
                        finish_launch_record(rec, status="exited", exit_code=code)
                        logging.info("实例 %d 退出，退出码 %s", idx, code)
                        self.instance_exited.emit(idx, code)
                if len(exited_set) >= len(self._procs):
                    break
                alive = len(self._procs) - len(exited_set)
                self.stage.emit("存活实例：%d / %d" % (alive, len(self._procs)))
                time.sleep(0.5)
            alive = self.alive_count()
            self.finished_all.emit(alive)
        except LauncherError as e:
            logging.error("多实例启动失败：%s ｜ detail: %s", e, getattr(e, "detail", ""))
            self.fail.emit(str(e))
        except Exception as e:
            logging.error("多实例启动失败（未预期）：%s: %s", type(e).__name__, e)
            self.fail.emit("%s: %s" % (type(e).__name__, e))


class LaunchWorker(QThread):
    """构建启动命令并拉起游戏进程。"""
    stage = pyqtSignal(str)          # 阶段文本
    output = pyqtSignal(str)         # 游戏输出行
    started = pyqtSignal(int)        # PID
    stable = pyqtSignal()            # 进程稳定存活（约 5 秒）
    exited = pyqtSignal(int)         # 退出码
    fail = pyqtSignal(str)

    def __init__(self, game_dir, folder, java_path, memory_gb, username, uuid,
                 user_type, jvm_extra, width, height, isolate_dir, base_dir=None,
                 instance_tag="", priority="normal", fullscreen=False,
                 ip_preference="java", parent=None):
        super().__init__(parent)
        self._args = (game_dir, folder, java_path, memory_gb, username, uuid,
                      user_type, jvm_extra, width, height, isolate_dir,
                      str(instance_tag or ""), str(priority or "normal"),
                      bool(fullscreen), str(ip_preference or "java"))
        self._base_dir = base_dir
        self._rec = None
        self._proc = None
        self._stop = False

    def _finish_rec(self, status, exit_code=None, error=None):
        if self._rec:
            finish_launch_record(self._rec, status=status,
                                 exit_code=exit_code, error=error)

    def run(self):
        game_dir, folder, java_path, memory_gb, username, uuid, user_type, \
            jvm_extra, width, height, isolate_dir, instance_tag, \
            priority, fullscreen, ip_preference = self._args
        self._rec = begin_launch_record(self._base_dir, folder)
        try:
            # Java 动态解析：手动路径校验有效性，空值时按版本自动选择
            self.stage.emit("正在检测 Java 运行时…")
            java_path = resolve_java_for_launch(game_dir, folder, java_path)
            self.stage.emit("使用 Java：%s" % java_path)
            update_launch_record(self._rec, java=java_path,
                                 mc_version=derive_mc_version_for(game_dir, folder),
                                 status="resolving")
            # 启动前验证 -Xmx：失败给中文提示，避免 JVM 弹系统原生错误框
            validate_jvm_heap(java_path, effective_heap_gb(java_path, memory_gb))

            self.stage.emit("正在解压 natives 并构建启动命令…")
            cmd = build_launch_command(
                game_dir, folder, java_path,
                memory_gb=memory_gb, username=username, uuid=uuid,
                user_type=user_type,
                jvm_extra=jvm_extra, width=width, height=height,
                isolate_dir=isolate_dir,
                instance_tag=instance_tag,
                fullscreen=fullscreen, ip_preference=ip_preference,
            )
            cmd["priority"] = priority
            update_launch_record(
                self._rec, command=cmd["command"], workdir=cmd["workdir"],
                natives_dir=cmd["natives_dir"],
                classpath_entries=len(cmd["classpath"].split(";")) if cmd.get("classpath") else 0,
                missing_libs=len(cmd.get("missing_libs") or []),
                status="built",
            )
            if cmd.get("missing_libs"):
                self.stage.emit(
                    "警告：有 %d 个库文件缺失，游戏可能无法启动（可在版本页补全文件）"
                    % len(cmd["missing_libs"])
                )
            self.stage.emit("正在启动游戏进程…")
            gp = launch_game(cmd, on_output=lambda line: self.output.emit(line))
            self._proc = gp
            self.started.emit(gp._proc.pid)
            update_launch_record(self._rec, pid=gp._proc.pid, status="running")
            alive_start = time.time()
            stable_sent = False
            while not self._stop:
                code = gp.poll()
                if code is not None:
                    logging.info("游戏进程退出，退出码 %s", code)
                    self._finish_rec("exited", exit_code=code)
                    self.exited.emit(code)
                    return
                if not stable_sent and time.time() - alive_start >= 5:
                    stable_sent = True
                    self.stable.emit()
                time.sleep(0.5)
            # stop 请求：不杀游戏进程（由用户决定），仅结束监控
            self._finish_rec("detached")
        except LauncherError as e:
            logging.error("启动失败：%s ｜ detail: %s", e, getattr(e, "detail", ""))
            self._finish_rec("failed", error=str(e))
            self.fail.emit(str(e))
        except Exception as e:
            logging.error("启动失败（未预期异常）：%s: %s", type(e).__name__, e)
            self._finish_rec("failed", error="%s: %s" % (type(e).__name__, e))
            self.fail.emit("%s: %s" % (type(e).__name__, e))

    def stop_watch(self):
        self._stop = True

    def game_running(self) -> bool:
        """游戏进程是否仍在运行。"""
        gp = self._proc
        return bool(gp is not None and gp.poll() is None)

    def terminate_game(self):
        """强制结束游戏进程并结台账。"""
        if self.game_running():
            try:
                self._proc.terminate()
            except Exception:
                pass

    def alive_pids(self) -> list:
        return [self._proc._proc.pid] if self.game_running() else []


class ModSearchWorker(QThread):
    """搜索 Modrinth 项目（mod / modpack）。"""
    ok = pyqtSignal(object, int)      # (hits, total_hits)
    fail = pyqtSignal(str)

    def __init__(self, query, project_type, mc_version, loader, offset=0, parent=None):
        super().__init__(parent)
        self.query = query
        self.project_type = project_type
        self.mc_version = mc_version
        self.loader = loader
        self.offset = offset

    def run(self):
        try:
            hits, total = mods.search_projects(
                self.query, self.project_type, self.mc_version,
                self.loader, offset=self.offset)
            self.ok.emit(hits, total)
        except Exception as e:
            logging.error("模组搜索失败：%s ｜ detail: %s",
                          e, getattr(e, "detail", ""))
            self.fail.emit(_err_text(e))


class ModVersionsWorker(QThread):
    """获取某项目的兼容版本列表。"""
    ok = pyqtSignal(object)      # list[version]
    fail = pyqtSignal(str)

    def __init__(self, project_id, mc_version, loader, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.mc_version = mc_version
        self.loader = loader

    def run(self):
        try:
            self.ok.emit(mods.get_versions(self.project_id, self.mc_version, self.loader))
        except Exception as e:
            logging.error("模组版本获取失败：%s", _err_text(e))
            self.fail.emit(_err_text(e))


class ModIconWorker(QThread):
    """批量下载项目图标，回传 {project_id: bytes}（QPixmap 在 GUI 线程构造）。"""
    ok = pyqtSignal(object)      # dict[id -> bytes]
    fail = pyqtSignal(str)

    def __init__(self, hits, parent=None):
        super().__init__(parent)
        self.hits = hits or []

    def run(self):
        out = {}
        try:
            for h in self.hits:
                iu = h.get("icon_url")
                pid = h.get("id")
                if not iu or not pid or pid in out:
                    continue
                try:
                    out[pid] = mods._open_bytes(iu, timeout=20, retries=2)
                except Exception:
                    pass
            self.ok.emit(out)
        except Exception as e:
            self.fail.emit(_err_text(e))


class ModDepsWorker(QThread):
    """解析模组的『前置依赖』：展示清单 + 必需依赖的下载项。"""
    ok = pyqtSignal(object, object)   # (display_list[(title,type)], dep_items)
    fail = pyqtSignal(str)

    def __init__(self, version_entry, mc_version, loader, mods_folder, parent=None):
        super().__init__(parent)
        self.version_entry = version_entry
        self.mc_version = mc_version
        self.loader = loader
        self.mods_folder = mods_folder

    def run(self):
        try:
            deps = self.version_entry.get("dependencies") or []
            display = mods.collect_required_dependency_titles(deps)
            res = mods.build_dependency_items(
                deps, self.mc_version, self.loader, self.mods_folder)
            self.ok.emit(display, res.get("items") or [])
        except Exception as e:
            logging.error("前置依赖解析失败：%s", _err_text(e))
            # 依赖解析失败不应阻断主模组下载，仅返回空
            self.ok.emit([], [])


class LoaderListWorker(QThread):
    """列举某加载器在指定 MC 版本下的可用版本（下拉填充）。"""
    ok = pyqtSignal(str, object)      # (loader, [{value,label}])
    fail = pyqtSignal(str, str)       # (loader, msg)

    def __init__(self, loader, mc_version, parent=None):
        super().__init__(parent)
        self.loader = loader
        self.mc_version = mc_version

    def run(self):
        try:
            opts = modloaders.list_loader_versions(self.loader, self.mc_version)
            self.ok.emit(self.loader, opts)
        except Exception as e:
            logging.error("加载器版本列举失败（%s）：%s", self.loader, _err_text(e))
            self.fail.emit(self.loader, _err_text(e))


class LoaderInstallWorker(QThread):
    """安装模组端（加载器）：Fabric/Quilt 走 JSON + 下载；Forge/NeoForge 走安装器。"""
    stage = pyqtSignal(str)
    progress = pyqtSignal(int, int, str, float)
    finished = pyqtSignal(str)        # 成功消息（含新版本名）
    fail = pyqtSignal(str)

    def __init__(self, loader, mc_version, loader_version, game_dir, source, parent=None):
        super().__init__(parent)
        self.loader = loader
        self.mc_version = mc_version
        self.loader_version = loader_version
        self.game_dir = game_dir
        self.source = source

    def run(self):
        try:
            if self.loader in ("fabric", "quilt"):
                self._install_json()
            else:
                self._install_via_installer()
        except LauncherError as e:
            logging.error("加载器安装失败：%s ｜ detail: %s",
                          e, getattr(e, "detail", ""))
            self.fail.emit(str(e))
        except Exception as e:
            logging.error("加载器安装失败（未预期）：%s: %s", type(e).__name__, e)
            self.fail.emit("%s: %s" % (type(e).__name__, e))

    # ----- Fabric / Quilt -----
    def _install_json(self):
        self.stage.emit("正在获取 %s 加载器版本信息…" % self.loader)
        folder, prof = modloaders.fetch_loader_version_json(
            self.loader, self.mc_version, self.loader_version)
        vdir = os.path.join(self.game_dir, "versions", folder)
        if os.path.isfile(os.path.join(vdir, folder + ".json")):
            self.finished.emit("该加载器版本已存在：%s" % folder)
            return
        modloaders.write_loader_version_json(self.game_dir, folder, prof)
        self.stage.emit("正在收集加载器依赖文件（库 / 客户端 / 资源）…")
        items = meta.collect_download_items(
            self.game_dir, folder, self.source,
            include_assets=True, include_libraries=True, include_natives=True)
        if not items:
            self.finished.emit("已写入 %s 版本 json（无额外需下载文件）。" % folder)
            return
        self.stage.emit("正在下载 %s 加载器文件（%d 个）…" % (folder, len(items)))
        self._download_items(items, "下载 %s" % folder)
        self.finished.emit("✅ 已安装 %s 模组端：%s（请到『版本选择』设为当前版本）"
                           % (self.loader, folder))

    # ----- Forge / NeoForge -----
    def _install_via_installer(self):
        self.stage.emit("正在解析用于安装的 Java 运行时…")
        java_exe = modloaders.resolve_java_for_installer(self.mc_version)
        self.stage.emit("正在下载 %s 安装器…" % self.loader)
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(),
                           "%s-%s-installer.jar" % (self.loader, self.loader_version))
        try:
            if self.loader == "forge":
                meta.download_file(
                    modloaders.loader_installer_url(
                        "forge", self.mc_version, self.loader_version),
                    tmp, source="bmclapi", timeout=120, retries=3)
            else:
                meta.download_file(
                    modloaders.loader_installer_url(
                        "neoforge", self.mc_version, self.loader_version),
                    tmp, source="official", timeout=120, retries=3)
        except LauncherError as e:
            raise LauncherError("下载 %s 安装器失败" % self.loader, detail=str(e))
        self.stage.emit("正在运行 %s 安装器（可能需要几分钟）…" % self.loader)
        modloaders.run_installer(tmp, self.game_dir, java_exe)
        self.finished.emit("✅ 已通过安装器完成 %s 模组端安装（请到『版本选择』刷新并设为当前版本）"
                           % self.loader)

    def _download_items(self, items, label):
        from launcher.download import DownloadManager
        total = len(items)
        done = [0]

        def prog(d, t, n, p):
            done[0] = d
            self.progress.emit(d, t, n, p)

        def done_cb(ok, failed):
            self._ok = ok
            self._failed = failed

        dm = DownloadManager(source=self.source, max_workers=6)
        dm.download(items, progress=prog,
                    done=lambda ok, failed: done_cb(ok, failed), error=lambda e: None)
        # DownloadManager 在后台线程；这里简单轮询完成
        import time as _t
        while dm.is_running():
            _t.sleep(0.2)
        if getattr(self, "_failed", None):
            raise LauncherError(
                "模组端文件下载不完整：%d 个失败" % len(self._failed))
