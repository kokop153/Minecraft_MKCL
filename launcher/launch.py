# -*- coding: utf-8 -*-
"""启动引擎： natives 解压、启动命令构建、游戏进程封装、启动台账。"""
import datetime
import glob
import json
import logging
import os
import platform
import re
import shlex
import subprocess
import threading
import zipfile
from typing import Callable, Dict, List, Optional

from launcher.errors import LauncherError
from launcher.version_scan import (
    VersionInfo,
    scan_versions,
    resolve_version_chain,
    derive_mc_version,
)
from launcher.maven import gav_to_path


def _is_foreign_natives(path: str) -> bool:
    """非当前平台的 natives 库（linux/macos/freebsd），不进 Windows classpath。"""
    return bool(
        re.search(
            r"natives-(linux|macos|freebsd|solaris|unix|arm64|aarch64)",
            str(path).lower(),
        )
    )


# 多实例/连续启动时并发构建命令，natives 解压目标可能重叠，加锁串行化
_natives_lock = threading.Lock()


def _rules_allow(rules, features: Dict[str, bool], os_name: str = "windows") -> bool:
    if not rules:
        return True
    # 存在 rules 时：逐条判断是否在当前平台生效，最后一条生效规则决定 allow；
    # 无任何生效规则 → 默认 False（否则 osx/linux 专属库会被误加，
    # 且 -XstartOnFirstThread 这类 mac 专属 JVM 参数会导致 Windows 上 JVM 启动失败）
    allow = False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        clause = rule.get("os") or {}
        ok = True
        if clause:
            rname = clause.get("name")
            rarch = clause.get("arch")
            if rname and rname != os_name:
                ok = False
            if rarch:
                is64 = platform.machine() in ("AMD64", "x86_64", "ARM64")
                ok = ok and ((rarch == "x86_64" and is64) or (rarch == "x86" and not is64))
        feat = rule.get("features")
        if isinstance(feat, dict) and feat:
            for k, v in feat.items():
                if features.get(k, False) != bool(v):
                    ok = False
                    break
        if ok:
            allow = bool(rule.get("allow", True))
    return allow


_FEATURES = {
    "has_custom_resolution": True,
    "is_demo_user": False,
    "has_custom_logo": False,
    "has_quick_plays_support": False,
    "is_quick_play_singleplayer": False,
    "is_quick_play_multiplayer": False,
    "is_quick_play_realms": False,
    "is_quick_play": False,
}


def _substitute(token: str, mapping: Dict[str, str]) -> str:
    if not isinstance(token, str):
        return token

    def repl(m):
        return mapping.get(m.group(1), "0")

    return re.sub(r"\$\{([^}]+)\}", repl, token)


def extract_natives(version_data: dict, version_dir: str, folder: str,
                    target_subdir: Optional[str] = None) -> str:
    natives_dir = (os.path.join(version_dir, target_subdir)
                   if target_subdir
                   else os.path.join(version_dir, folder + "-natives"))
    try:
        os.makedirs(natives_dir, exist_ok=True)
    except OSError as e:
        raise LauncherError(
            "无法创建 natives 解压目录：%s" % natives_dir,
            detail="%s: %s" % (type(e).__name__, e),
        )
    arch = "x86_64" if platform.machine() in ("AMD64", "x86_64", "ARM64") else "x86"
    accepted = {"natives-windows", "natives-windows-64", "natives-windows-" + arch}
    libraries_root = os.path.dirname(os.path.dirname(version_dir))
    for lib in version_data.get("libraries") or []:
        if not _rules_allow(lib.get("rules"), _FEATURES):
            continue
        natives = lib.get("natives")
        if not natives:
            continue
        classifier = None
        if isinstance(natives, dict):
            for key in ("windows", "windows-64", "windows-" + arch):
                if key in natives:
                    classifier = natives[key]
                    break
            if classifier is None:
                continue
        elif isinstance(natives, str):
            if natives not in accepted:
                continue
            classifier = natives
        else:
            continue
        classifiers = (lib.get("downloads") or {}).get("classifiers") or {}
        art = classifiers.get(classifier)
        if not art or not art.get("path"):
            continue
        jar_path = os.path.normpath(
            os.path.join(libraries_root, "libraries", *art["path"].split("/"))
        )
        if not os.path.isfile(jar_path):
            logging.warning("natives jar 缺失，跳过：%s", jar_path)
            continue
        try:
            with zipfile.ZipFile(jar_path) as zf:
                for name in zf.namelist():
                    if name.startswith("META-INF/"):
                        continue
                    if not name.lower().endswith(".dll"):
                        continue
                    target = os.path.join(natives_dir, os.path.basename(name))
                    with zf.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
        except (OSError, zipfile.BadZipFile) as e:
            logging.warning("解压 natives 失败 %s：%s", jar_path, e)
    logging.info("natives 目录：%s", natives_dir)
    return natives_dir


def build_launch_command(
    game_dir: str,
    folder: str,
    java_path: str,
    memory_gb: int = 4,
    username: str = "Player",
    uuid: str = "",
    user_type: str = "legacy",
    access_token: str = "0",
    jvm_extra: str = "",
    width: int = 854,
    height: int = 480,
    isolate_dir: bool = False,
    instance_tag: str = "",
) -> dict:
    logging.info("构建启动命令：%s", folder)
    versions = scan_versions(game_dir)
    info: Optional[VersionInfo] = next(
        (v for v in versions if v.folder == folder), None
    )
    if info is None:
        raise LauncherError("找不到版本：" + folder, detail="game_dir=" + game_dir)
    data = resolve_version_chain(info)

    version_dir = os.path.join(game_dir, "versions", folder)
    natives_subdir = ("multi-" + str(instance_tag) + "\\natives") if instance_tag else None
    with _natives_lock:
        natives_dir = extract_natives(data, version_dir, folder, target_subdir=natives_subdir)
    if instance_tag:
        # 多实例模式：每实例独立 gameDir（options/logs/saves/mods 互不干扰）
        workdir = os.path.join(version_dir, "multi-" + str(instance_tag))
    elif isolate_dir:
        workdir = version_dir
    else:
        workdir = game_dir
    try:
        os.makedirs(workdir, exist_ok=True)
    except OSError as e:
        raise LauncherError(
            "无法创建游戏工作目录：%s" % workdir,
            detail="%s: %s" % (type(e).__name__, e),
        )
    libraries_dir = os.path.join(game_dir, "libraries")

    # ---- classpath（先构建，供 ${classpath} 映射） ----
    missing_libs: List[str] = []
    classpath_entries: List[str] = []
    jar_name = data.get("jar") or data.get("id") or folder
    version_jar = os.path.join(version_dir, str(jar_name) + ".jar")
    if not os.path.isfile(version_jar):
        found = False
        for ancestor in data.get("_chain") or []:
            cand = os.path.join(
                game_dir, "versions", ancestor,
                str(data.get("jar") or ancestor) + ".jar",
            )
            if os.path.isfile(cand):
                version_jar = cand
                found = True
                break
        if not found:
            missing_libs.append(version_jar)
    if os.path.isfile(version_jar):
        classpath_entries.append(version_jar)
    for lib in data.get("libraries") or []:
        if not _rules_allow(lib.get("rules"), _FEATURES):
            continue
        art = (lib.get("downloads") or {}).get("artifact")
        if art and art.get("path"):
            if _is_foreign_natives(art.get("path")):
                continue
            lib_path = os.path.join(libraries_dir, *art["path"].split("/"))
            if not os.path.isfile(lib_path):
                missing_libs.append(lib_path)
            classpath_entries.append(lib_path)
        elif lib.get("name"):
            # Maven 布局库（Fabric/Forge 安装器 json 常见：无 downloads 字段，
            # 只有 GAV 坐标 + 仓库 url，与 PCL/HMCL 同样按坐标推导路径）
            rel = gav_to_path(lib["name"])
            if not rel:
                continue
            lib_path = os.path.join(libraries_dir, *rel.split("/"))
            if not os.path.isfile(lib_path):
                missing_libs.append(lib_path)
            classpath_entries.append(lib_path)
    classpath = ";".join(classpath_entries)
    logging.info(
        "classpath 条目数=%d 缺失=%d", len(classpath_entries), len(missing_libs)
    )

    # ---- JVM 参数 ----
    n = int(memory_gb)
    jvm: List[str] = [
        "-Xmx{}G".format(n),
        "-Xms{}G".format(min(2, n)),
        "-Xmn{}".format("256m" if n <= 4 else "512m"),
        "-XX:+UseG1GC",
        "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200",
        "-XX:+UnlockExperimentalVMOptions",
        "-XX:+DisableExplicitGC",
        "-XX:+AlwaysPreTouch",
        "-Dfml.ignoreInvalidMinecraftCertificates=true",
        "-Dfml.ignorePatchDiscrepancies=true",
        "-Dlog4j2.formatMsgNoLookups=true",
        "-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump",
        "-Djava.library.path=" + natives_dir,
        "-Djna.tmpdir=" + natives_dir,
        "-Dorg.lwjgl.system.SharedLibraryExtractPath=" + natives_dir,
        "-Dio.netty.native.workdir=" + natives_dir,
    ]
    jvm_mapping = {
        "natives_directory": natives_dir,
        "library_directory": libraries_dir,
        "classpath_separator": ";",
        "classpath": classpath,
        "launcher_name": "MKCLauncher",
        "launcher_version": "1.0",
    }
    for item in (data.get("arguments") or {}).get("jvm") or []:
        # 部分 json（如 MSL 生成）把 -cp ${classpath} 写进 jvm 参数里，引擎统一自行拼接，跳过
        if item == "-cp" or item == "${classpath}":
            continue
        if isinstance(item, str):
            jvm.append(_substitute(item, jvm_mapping))
        elif isinstance(item, dict):
            if _rules_allow(item.get("rules"), _FEATURES):
                val = item.get("value")
                if val is None:
                    continue
                vals = val if isinstance(val, list) else [val]
                for v in vals:
                    if v == "-cp" or v == "${classpath}":
                        continue
                    jvm.append(_substitute(v, jvm_mapping))
    if jvm_extra:
        try:
            jvm.extend(shlex.split(jvm_extra, posix=False))
        except ValueError:
            jvm.extend(jvm_extra.split())

    # ---- 游戏参数 ----
    asset_index = ((data.get("assetIndex") or {}).get("id")) or ""
    if not asset_index:
        # 自定义 json 可能缺 assetIndex：从同大版本（major.minor 相同）的其他版本 json 回退
        try:
            mc_ver = derive_mc_version(info)
            prefix = ".".join(mc_ver.split(".")[:2])
            for v in versions:
                if v.folder == folder or not v.valid:
                    continue
                try:
                    with open(v.json_path, "r", encoding="utf-8") as vf:
                        aid = ((json.load(vf).get("assetIndex") or {}).get("id")) or ""
                except (OSError, ValueError):
                    continue
                vmc = derive_mc_version(v)
                if aid and vmc.split(".")[:2] == mc_ver.split(".")[:2]:
                    asset_index = aid
                    logging.info("版本 %s 缺 assetIndex，回退用同大版本 %s 的索引 %s",
                                 folder, v.folder, aid)
                    break
        except LauncherError:
            pass
    if not asset_index:
        logging.warning("版本 %s 无法确定 assetIndex，--assetIndex 将为空", folder)
    game_mapping = {
        "auth_player_name": username,
        "version_name": folder,
        "game_directory": workdir,
        "assets_root": os.path.join(game_dir, "assets"),
        "asset_index_name": asset_index,
        # Fabric 安装器变体：部分自定义 json 写作 ${assets_index_name}（多个 s）
        "assets_index_name": asset_index,
        "auth_uuid": uuid,
        "auth_access_token": access_token,
        "user_type": user_type,
        "user_properties": "{}",
        "version_type": data.get("type") or "launcher",
        "resolution_width": str(width),
        "resolution_height": str(height),
        "clientid": "0",
        "auth_xuid": "0",
        "quick_play_path": "",
    }
    game_args: List[str] = []
    new_args = (data.get("arguments") or {}).get("game")
    old_args = data.get("minecraftArguments")
    if new_args:
        feats = dict(_FEATURES)
        feats["has_custom_resolution"] = True
        for item in new_args:
            if isinstance(item, str):
                game_args.append(_substitute(item, game_mapping))
            elif isinstance(item, dict):
                if _rules_allow(item.get("rules"), feats):
                    val = item.get("value")
                    if val is None:
                        continue
                    vals = val if isinstance(val, list) else [val]
                    for v in vals:
                        game_args.append(_substitute(v, game_mapping))
    elif old_args:
        tokens = str(old_args).split()
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.startswith("-") and i + 1 < len(tokens):
                game_args.append(tok)
                game_args.append(_substitute(tokens[i + 1], game_mapping))
                i += 2
            else:
                game_args.append(_substitute(tok, game_mapping))
                i += 1
    else:
        raise LauncherError(
            "版本 json 中没有可用的游戏参数定义", detail="folder=" + folder
        )

    if "--width" not in game_args:
        game_args.extend(["--width", str(width), "--height", str(height)])

    main_class = str(data.get("mainClass") or "")
    command = [java_path] + jvm + ["-cp", classpath, main_class] + game_args
    logging.info(
        "启动命令构建完成：mainClass=%s 参数总数=%d", main_class, len(command)
    )
    return {
        "command": command,
        "workdir": workdir,
        "classpath": classpath,
        "natives_dir": natives_dir,
        "version_json": info.json_path,
        "missing_libs": missing_libs,
    }


class GameProcess:
    """Popen 封装：后台线程读输出。"""

    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        t = threading.Thread(target=self._pump, daemon=True)
        t.start()

    def _pump(self):
        try:
            for line in self._proc.stdout:
                logging.info("[MC] %s", line.rstrip())
        except (OSError, ValueError):
            pass

    def poll(self):
        return self._proc.poll()

    def wait(self, timeout: Optional[float] = None):
        return self._proc.wait(timeout=timeout)

    def terminate(self):
        try:
            self._proc.terminate()
        except OSError:
            pass

    @property
    def returncode(self):
        return self._proc.returncode


def resolve_java_for_launch(game_dir: str, folder: str, java_path: str) -> str:
    """解析启动用的 Java 可执行文件路径（javaw.exe / java.exe）。

    java_path 非空且文件存在时直接使用；否则进入自动选择：
    探测系统全部 Java -> 推导真实 MC 版本 -> 按版本需求选最合适的运行时。
    任何失败都抛出可读的中文 LauncherError，绝不返回空串。
    """
    java_path = str(java_path or "").strip()
    if java_path:
        if not os.path.isfile(java_path):
            raise LauncherError(
                "配置的 Java 路径无效（文件不存在）：%s" % java_path,
                detail="请在设置中重新检测并选择有效的 Java 运行时",
            )
        logging.info("使用手动指定的 Java：%s", java_path)
        return java_path

    # ---- 自动选择：探测系统 Java ----
    from launcher.java_utils import find_javas, pick_java_for

    versions = scan_versions(game_dir)
    info = next((v for v in versions if v.folder == folder), None)
    if info is None:
        raise LauncherError("找不到版本：" + folder, detail="game_dir=" + game_dir)
    mc_version = derive_mc_version(info)
    javas = find_javas()
    if not javas:
        raise LauncherError(
            "未找到可用的 Java 运行时，无法启动游戏",
            detail="请安装 Java（建议 https://adoptium.net/temurin/releases/ ）"
                   "或在启动器设置中手动指定 Java 路径",
        )
    jr = pick_java_for(mc_version, javas)
    if jr is None:
        have = ", ".join("%s(%d)" % (j.version, j.major) for j in javas)
        raise LauncherError(
            "没有适配 Minecraft %s 的 Java（已检测到：%s）" % (mc_version, have),
            detail="请在设置中手动指定符合版本要求的 Java 路径",
        )
    resolved = jr.is_javaw or jr.path
    logging.info("自动选择 Java：%s（%s，major=%d，适配 MC %s）",
                 resolved, jr.version, jr.major, mc_version)
    return resolved


def derive_mc_version_for(game_dir: str, folder: str) -> str:
    """不依赖 UI 的版本推导：扫描定位文件夹后调 derive_mc_version；找不到回退 folder。"""
    try:
        info = next(v for v in scan_versions(game_dir) if v.folder == folder)
        return derive_mc_version(info)
    except LauncherError:
        return folder


# ---------------- 启动台账（每次启动一份 JSON，可追踪版本/命令/PID/退出码） ----------------

def _launch_dir(base_dir: str) -> str:
    return os.path.join(base_dir, "logs", "launches")


def _write_record(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def prune_launch_records(base_dir: str, keep: int = 50) -> None:
    """台账瘦身：只保留最近 keep 份启动记录。"""
    if not base_dir:
        return
    d = _launch_dir(base_dir)
    files = sorted(glob.glob(os.path.join(d, "launch-*.json")))
    for p in files[:-keep] if len(files) > keep else []:
        try:
            os.remove(p)
        except OSError:
            pass


def begin_launch_record(base_dir: Optional[str], folder: str) -> Optional[str]:
    """启动开始时创建台账；base_dir 为空时跳过（返回 None）。返回台账路径。"""
    if not base_dir:
        return None
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r'[\\/:*?"<>|]+', "_", str(folder))[:40] or "unknown"
    d = _launch_dir(base_dir)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    path = os.path.join(d, "launch-%s-%s.json" % (ts, safe))
    _write_record(path, {
        "version": folder,
        "mc_version": None,
        "java": None,
        "command": None,
        "workdir": None,
        "natives_dir": None,
        "classpath_entries": None,
        "missing_libs": None,
        "pid": None,
        "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "preparing",
        "exit_code": None,
        "finished_at": None,
        "error": None,
    })
    prune_launch_records(base_dir)
    return path


def update_launch_record(path: Optional[str], **fields) -> None:
    """更新台账字段；文件缺失或损坏时静默跳过（不阻断启动）。"""
    if not path or not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.update(fields)
        _write_record(path, data)
    except (OSError, ValueError):
        pass


def finish_launch_record(path: Optional[str], status: str = "exited",
                         exit_code: Optional[int] = None,
                         error: Optional[str] = None) -> None:
    update_launch_record(
        path, status=status, exit_code=exit_code, error=error,
        finished_at=datetime.datetime.now().isoformat(timespec="seconds"),
    )


def launch_game(cmd: dict, on_output: Optional[Callable[[str], None]] = None) -> GameProcess:
    command = cmd.get("command") or []
    workdir = str(cmd.get("workdir") or "")

    # ---- 前置校验：把系统级 WinError 拦截成人能看懂的中文错误 ----
    if not command:
        raise LauncherError(
            "启动命令为空，无法启动游戏",
            detail="请检查版本 json 是否完整（mainClass / libraries）",
        )
    exe = str(command[0] or "").strip()
    if not exe:
        raise LauncherError(
            "未获取到 Java 路径，无法启动游戏",
            detail="请在设置中检测并选择 Java，或检查 config.json 的 java_path",
        )
    bad_empty = [i for i, a in enumerate(command)
                 if isinstance(a, str) and a == ""]
    bad_type = [i for i, a in enumerate(command)
                if not isinstance(a, str)]
    if bad_type:
        logging.error("启动命令含非字符串参数，完整命令：%r", command)
        raise LauncherError(
            "启动命令第 %s 项参数不是字符串，已阻止启动" % (bad_type[:5]),
            detail="完整命令已写入日志，请检查版本 json 参数定义",
        )
    if bad_empty:
        logging.error("启动命令含空参数，完整命令：%r", command)
        raise LauncherError(
            "启动命令第 %s 项参数为空，已阻止启动" % (bad_empty[:5]),
            detail="完整命令已写入日志，请检查版本 json 参数定义",
        )
    if not os.path.isfile(exe):
        raise LauncherError(
            "Java 可执行文件不存在：%s" % exe,
            detail="请在设置中重新检测 Java",
        )
    if not os.path.isdir(workdir):
        raise LauncherError(
            "游戏工作目录不存在：%s" % workdir,
            detail="请确认游戏目录设置是否正确",
        )

    logging.info("启动游戏进程：java=%s，workdir=%s，参数总数=%d",
                 exe, workdir, len(command))
    try:
        proc = subprocess.Popen(
            command,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, ValueError) as e:
        raise LauncherError(
            "游戏进程启动失败：%s（Java：%s）" % (e, exe),
            detail="请确认 Java 版本满足游戏要求，或在设置中更换 Java 路径",
        )

    def pump():
        try:
            for line in proc.stdout:
                stripped = line.rstrip()
                logging.info("[GameLog] %s", stripped)
                if on_output:
                    try:
                        on_output(stripped)
                    except Exception:
                        pass
        except (OSError, ValueError):
            pass

    threading.Thread(target=pump, daemon=True).start()
    return GameProcess(proc)
