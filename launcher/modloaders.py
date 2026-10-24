# -*- coding: utf-8 -*-
"""模组端（加载器）安装：Fabric / Quilt / Forge / NeoForge。

- Fabric / Quilt：纯 JSON 元数据安装（无需运行 Java）。
  取加载器版本 json 写入 versions/<folder>/<folder>.json（inheritsFrom 原版），
  再复用 collect_download_items 把加载器库 + 原版客户端/资源一并下载。
- Forge / NeoForge：下载官方安装器 jar，用本机 Java 运行
  `java -jar installer.jar --installClient <gameDir>`（经典安装方式）。

所有网络请求复用 mods / meta 的容错管线。
"""
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET

from launcher import meta
from launcher.errors import LauncherError
from launcher.mods import _open_json

FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"
BMCLAPI = "https://bmclapi2.bangbang93.com"
NEO_MAVEN = "https://maven.neoforged.net/releases"

LOADERS = ("fabric", "quilt", "forge", "neoforge")


def _text_get(url: str, timeout: float = 25, retries: int = 2):
    last = None
    for attempt in range(max(1, retries)):
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "MKCL-Launcher/2.1"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:
            last = e
            if attempt < max(1, retries) - 1:
                time.sleep(1.5 ** attempt)
    raise LauncherError("无法连接加载器源", detail="%s: %s" % (type(last).__name__, last))


def _ver_key(version: str):
    return tuple(int(x) for x in re.findall(r"\d+", version or ""))


# --------------------------------------------------------------------------
# 版本列举（UI 下拉用）
# --------------------------------------------------------------------------
def list_loader_versions(loader: str, mc_version: str):
    """返回 [{value, label}]（按版本号倒序）。网络失败抛 LauncherError。"""
    if loader == "fabric":
        return _list_fabric_loaders()
    if loader == "quilt":
        return _list_quilt_loaders()
    if loader == "forge":
        return _list_forge_versions(mc_version)
    if loader == "neoforge":
        return _list_neoforge_versions()
    return []


def _list_fabric_loaders(limit=20):
    data = _open_json("%s/versions/loader" % FABRIC_META)
    arr = [v.get("version") for v in (data or []) if v.get("version")]
    arr.sort(key=_ver_key, reverse=True)
    arr = arr[:limit]
    return [{"value": v, "label": v} for v in arr]


def _list_quilt_loaders(limit=20):
    data = _open_json("%s/versions/loader" % QUILT_META)
    arr = [v.get("version") for v in (data or []) if v.get("version")]
    arr.sort(key=_ver_key, reverse=True)
    arr = arr[:limit]
    return [{"value": v, "label": v} for v in arr]


def _list_forge_versions(mc_version: str):
    if not mc_version:
        return []
    data = _open_json("%s/forge/minecraft/%s" % (BMCLAPI, mc_version))
    out = []
    for e in (data or []):
        ver = e.get("version") or ""
        if not ver:
            continue
        out.append({"value": ver, "label": "%s (build %s)" % (ver, e.get("build"))})
    out.sort(key=lambda o: _ver_key(o["value"]), reverse=True)
    return out


def _list_neoforge_versions(limit=20):
    xml = _text_get("%s/net/neoforged/neoforge/maven-metadata.xml" % NEO_MAVEN)
    root = ET.fromstring(xml)
    vers = []
    for v in root.iter("version"):
        t = (v.text or "").strip()
        if t:
            vers.append(t)
    vers.sort(key=_ver_key, reverse=True)
    vers = vers[:limit]
    return [{"value": v, "label": v} for v in vers]


# --------------------------------------------------------------------------
# Fabric / Quilt：取版本 json
# --------------------------------------------------------------------------
def fetch_loader_version_json(loader: str, mc_version: str, loader_version: str):
    """返回 (folder, version_json_dict)。仅 Fabric / Quilt 使用。"""
    if loader == "fabric":
        return _fetch_fabric(mc_version, loader_version)
    if loader == "quilt":
        return _fetch_quilt(mc_version, loader_version)
    raise LauncherError("该加载器不支持 JSON 方式安装：%s" % loader)


def _fetch_fabric(mc_version: str, loader_version: str):
    arr = _open_json("%s/versions/loader/%s/%s" % (
        FABRIC_META, mc_version, loader_version))
    if not arr:
        # 退而求其次：直接用 profile/json 端点
        try:
            prof = _open_json("%s/versions/loader/%s/%s/profile/json" % (
                FABRIC_META, loader_version, mc_version))
        except Exception:
            prof = None
        if prof:
            folder = (prof.get("id")
                      or "fabric-loader-%s-%s" % (loader_version, mc_version))
            return folder, prof
        raise LauncherError("Fabric 未找到兼容组合：%s / %s（请换一个加载器版本）"
                           % (mc_version, loader_version))
    entry = arr[0]
    url = entry.get("url")
    if not url:
        raise LauncherError("Fabric 版本元数据缺少 profile 地址")
    prof = _open_json(url)
    folder = prof.get("id") or "fabric-loader-%s-%s" % (loader_version, mc_version)
    return folder, prof


def _fetch_quilt(mc_version: str, loader_version: str):
    data = _open_json("%s/versions/loader/%s/%s" % (
        QUILT_META, mc_version, loader_version))
    lm = (data or {}).get("launcherMeta") or {}
    if not lm:
        raise LauncherError("Quilt 版本元数据缺少 launcherMeta")
    folder = "quilt-loader-%s-%s" % (loader_version, mc_version)
    libs = []
    for grp in ("common", "client", "development"):
        for l in (lm.get("libraries", {}).get(grp) or []):
            libs.append({"name": l.get("name"), "url": l.get("url") or ""})
    prof = {
        "id": folder,
        "inheritsFrom": mc_version,
        "releaseTime": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "time": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "type": "release",
        "mainClass": (lm.get("mainClass") or {}).get("client", ""),
        "arguments": {"game": [], "jvm": []},
        "libraries": libs,
    }
    return folder, prof


def write_loader_version_json(game_dir: str, folder: str, prof: dict):
    vdir = os.path.join(game_dir, "versions", folder)
    os.makedirs(vdir, exist_ok=True)
    path = os.path.join(vdir, folder + ".json")
    with open(path, "w", encoding="utf-8") as f:
        import json as _json
        _json.dump(prof, f, ensure_ascii=False, indent=2)
    return path


# --------------------------------------------------------------------------
# Forge / NeoForge：安装器
# --------------------------------------------------------------------------
def loader_installer_url(loader: str, mc_version: str, loader_version: str) -> str:
    if loader == "forge":
        return ("%s/maven/net/minecraftforge/forge/%s-%s/"
                "forge-%s-%s-installer.jar") % (
            BMCLAPI, mc_version, loader_version, mc_version, loader_version)
    if loader == "neoforge":
        return "%s/net/neoforged/neoforge/%s/neoforge-%s-installer.jar" % (
            NEO_MAVEN, loader_version, loader_version)
    raise LauncherError("该加载器不支持安装器方式：%s" % loader)


def resolve_java_for_installer(mc_version: str) -> str:
    from launcher.java_utils import find_javas, pick_java_for
    javas = find_javas()
    jr = pick_java_for(mc_version, javas)
    if not jr:
        raise LauncherError(
            "未找到适配 Minecraft %s 的 Java 运行时" % mc_version,
            detail="请在设置中配置 Java 后重试",
        )
    return jr.path


def run_installer(installer_path: str, game_dir: str, java_exe: str) -> None:
    """运行 Forge/NeoForge 安装器（--installClient）。失败抛 LauncherError。"""
    try:
        proc = subprocess.run(
            [java_exe, "-jar", installer_path, "--installClient", game_dir],
            capture_output=True, text=True, errors="replace", timeout=900,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise LauncherError("加载器安装器运行超时（>15 分钟）", detail=installer_path)
    except OSError as e:
        raise LauncherError("无法运行加载器安装器：%s" % e, detail=installer_path)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:]
        raise LauncherError(
            "加载器安装失败（退出码 %d）" % proc.returncode, detail=tail)
