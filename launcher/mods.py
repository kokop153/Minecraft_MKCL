# -*- coding: utf-8 -*-
"""模组 / 整合包下载（Modrinth API v2）。

套用 PCL2 下载风格：仅做「浏览 + 取下载项」，真正落盘复用
launcher.download.DownloadManager 并发管线（与版本文件下载同一套机制）。

Modrinth 为公开免费 API，无需密钥；下载地址走 cdn.modrinth.com /
api.modrinth.com，不会被 bmclapi 镜像改写。
"""
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from launcher import meta
from launcher.errors import LauncherError

MODRINTH_API = "https://api.modrinth.com/v2"
_UA = "MKCL-Launcher/2.1 (mod download)"

# 主流加载器（用于过滤与展示）
LOADERS = ("fabric", "forge", "quilt", "neoforge", "liteloader", "rift")

# 常用 MC 版本快捷项（"全部" 用空串表示）
QUICK_MC_VERSIONS = (
    "", "1.21.11", "1.21.8", "1.21.4", "1.21.1", "1.20.6", "1.20.4",
    "1.20.1", "1.19.4", "1.19.2", "1.18.2", "1.16.5", "1.12.2", "1.7.10",
)


# --------------------------------------------------------------------------
# 底层 HTTP（与 meta.py 同风格：UA + 退避重试）
# --------------------------------------------------------------------------
def _open_json(url: str, timeout: float = 20, retries: int = 2):
    last = None
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:  # urllib 各类异常 + JSON 解码
            last = e
            if attempt < max(1, retries) - 1:
                time.sleep(1.5 ** attempt)
    raise LauncherError(
        "无法连接 Modrinth（请检查网络）",
        detail="%s: %s (%s)" % (type(last).__name__, last, url[:120]),
    )


def _open_bytes(url: str, timeout: float = 30, retries: int = 3):
    last = None
    for attempt in range(max(1, retries)):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            last = e
            if attempt < max(1, retries) - 1:
                time.sleep(1.5 ** attempt)
    raise LauncherError(
        "下载图标失败", detail="%s: %s (%s)" % (type(last).__name__, last, url[:120]),
    )


# --------------------------------------------------------------------------
# 搜索与版本查询
# --------------------------------------------------------------------------
def search_projects(query="", project_type="mod", mc_version=None, loader=None,
                    index="relevance", limit=30, offset=0):
    """搜索 Modrinth 项目（mod / modpack）。

    返回 (hits, total_hits)。hits 为已归一化的项目字典列表。
    """
    facets = [["project_type:%s" % project_type]]
    if mc_version:
        facets.append(["versions:%s" % mc_version])
    if loader:
        facets.append(["categories:%s" % loader])
    params = {
        "query": query or "",
        "facets": json.dumps(facets),
        "index": index,
        "limit": int(limit),
        "offset": int(offset),
    }
    url = "%s/search?%s" % (MODRINTH_API, urllib.parse.urlencode(params))
    data = _open_json(url)
    return [_normalize_hit(h) for h in (data.get("hits") or [])], \
        int(data.get("total_hits") or 0)


def _normalize_hit(h: dict) -> dict:
    return {
        "id": h.get("project_id") or h.get("id") or "",
        "slug": h.get("slug") or "",
        "title": h.get("title") or "(未命名)",
        "description": (h.get("description") or "").strip(),
        "icon_url": h.get("icon_url") or "",
        "author": h.get("author") or "",
        "project_type": h.get("project_type") or "",
        "downloads": int(h.get("downloads") or 0),
        "follows": int(h.get("follows") or 0),
        "categories": h.get("display_categories") or h.get("categories") or [],
        "versions": h.get("versions") or [],       # 支持的全部 MC 版本
        "date_modified": (h.get("date_modified") or "")[:10],
    }


def get_versions(project_id, mc_version=None, loader=None):
    """获取项目全部版本，按 mc_version / loader 过滤，返回归一化版本列表。"""
    url = "%s/project/%s/version" % (MODRINTH_API, project_id)
    raw = _open_json(url)
    out = []
    for v in raw or []:
        gv = v.get("game_versions") or []
        ld = v.get("loaders") or []
        if mc_version and mc_version not in gv:
            continue
        if loader and loader not in ld:
            continue
        files = []
        for f in (v.get("files") or []):
            files.append({
                "id": f.get("id"),
                "name": f.get("filename"),
                "size": int(f.get("size") or 0),
                "url": f.get("url"),
                "sha1": (f.get("hashes") or {}).get("sha1", ""),
                "primary": bool(f.get("primary")),
            })
        out.append({
            "id": v.get("id"),
            "name": v.get("name"),
            "version_number": v.get("version_number"),
            "game_versions": gv,
            "loaders": ld,
            "date_published": (v.get("date_published") or "")[:10],
            "files": files,
            "dependencies": v.get("dependencies") or [],
        })
    # 按发布日期倒序，最新版本在前（pick[0] = 最新兼容版）
    out.sort(key=lambda x: x.get("date_published") or "", reverse=True)
    return out


def get_project(project_id):
    """获取单个项目详情（含 body / 更多字段）。"""
    url = "%s/project/%s" % (MODRINTH_API, project_id)
    return _open_json(url)


def get_project_title(project_id):
    """获取项目标题（依赖展示用）。失败返回 project_id。"""
    try:
        p = get_project(project_id)
        return p.get("title") or project_id
    except Exception:
        return project_id


def get_version(version_id):
    """获取单个版本详情（用于 version_id 形式的依赖反查 project_id）。"""
    url = "%s/version/%s" % (MODRINTH_API, version_id)
    return _open_json(url)


def _dep_project_id(dep: dict) -> str:
    """从依赖项里拿到 project_id；若只有 version_id 则反查。"""
    pid = dep.get("project_id") or ""
    if pid:
        return pid
    vid = dep.get("version_id") or ""
    if vid:
        try:
            return get_version(vid).get("project_id") or ""
        except Exception:
            return ""
    return ""


def build_dependency_items(deps, mc_version, loader, mods_folder):
    """为模组的「前置依赖」构建下载项。

    - 只处理 dependency_type == "required" 且为 mod 类型项目的依赖；
    - 跳过 loader 类项目（modloader）以免把加载器 jar 塞进 mods 目录；
    - 取每个依赖在 (mc_version, loader) 下的最新兼容版本文件；
    - 按目标文件名去重。
    返回 {"items": [...], "titles": {project_id: title}}。
    """
    items = []
    seen = set()
    titles = {}
    for dep in (deps or []):
        dtype = dep.get("dependency_type") or ""
        if dtype != "required":
            continue
        pid = _dep_project_id(dep)
        if not pid:
            continue
        try:
            proj = get_project(pid)
        except Exception:
            continue
        if (proj.get("project_type") or "") == "modloader":
            continue  # 加载器本身不作为 mod 前置下载
        titles[pid] = proj.get("title") or pid
        vs = get_versions(pid, mc_version, loader)
        if not vs:
            continue
        for it in build_mod_download_items(vs[0], mods_folder):
            base = os.path.basename(it["dest"])
            if base in seen:
                continue
            seen.add(base)
            items.append(it)
    return {"items": items, "titles": titles}


def collect_required_dependency_titles(deps):
    """列出全部前置依赖（含 required / optional）的展示信息，
    供 UI 展示『前置』清单。返回 [(title, type), ...]，title 未知的用 project_id 占位。
    """
    out = []
    for dep in (deps or []):
        dtype = dep.get("dependency_type") or ""
        if dtype in ("incompatible", "embedded"):
            continue
        pid = _dep_project_id(dep)
        if not pid:
            continue
        try:
            title = get_project_title(pid)
        except Exception:
            title = pid
        out.append((title, dtype))
    return out


# --------------------------------------------------------------------------
# 下载项构建（喂给 DownloadManager）
# --------------------------------------------------------------------------
def resolve_mods_folder(game_dir, folder, per_version=None, auto_isolate=True):
    """返回某版本实际生效的 mods 目录，与 launch.py 的 isolate 逻辑保持一致。"""
    iso = bool(auto_isolate)
    pv = per_version or {}
    entry = pv.get(folder) or {}
    if isinstance(entry, dict) and "isolate" in entry:
        iso = bool(entry["isolate"])
    version_dir = os.path.join(game_dir, "versions", folder)
    if iso:
        return os.path.join(version_dir, "mods")
    return os.path.join(game_dir, "mods")


def build_mod_download_items(version_entry, mods_folder):
    """为一个 mod 版本构建下载项：优先 primary 文件，否则取第一个文件。"""
    items = []
    files = version_entry.get("files") or []
    if not files:
        return items
    sel = next((f for f in files if f.get("primary")), files[0])
    dest = os.path.join(mods_folder, sel["name"])
    items.append({
        "url": sel["url"],
        "dest": dest,
        "size": sel.get("size") or 0,
        "sha1": sel.get("sha1") or "",
    })
    return items


def _sanitize(name: str) -> str:
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad else c for c in (name or "modpack"))
    out = out.strip().strip(".")
    return out or "modpack"


def download_modpack_archive(url, dest):
    """下载 .mrpack 到 dest（原子写），返回 dest。"""
    res = meta.download_file(url, dest, source="bmclapi", timeout=60, retries=3)
    return res["dest"]


def import_modpack(mrpack_path, instance_root, base_folder=None):
    """解压 .mrpack 的 overrides 到 instance_root，并解析 index 返回需下载的内嵌文件项。

    - 先整体解压（modrinth.index.json 之外的所有条目 = overrides）。
    - 再解析 index：对其中带下载地址且本地尚不存在的文件，追加为下载项。
    返回 (items, index_dict, target_mc, target_loader)。
    """
    items = []
    index = {}
    try:
        with zipfile.ZipFile(mrpack_path) as z:
            for name in z.namelist():
                if name.endswith("modrinth.index.json"):
                    with z.open(name) as fh:
                        index = json.loads(fh.read().decode("utf-8"))
                    continue
                if name.endswith("/") or name.startswith("__MACOSX") \
                        or name.startswith("."):
                    continue
                dest = os.path.join(instance_root, *name.split("/"))
                os.makedirs(os.path.dirname(dest) or instance_root, exist_ok=True)
                with z.open(name) as src, open(dest, "wb") as out:
                    out.write(src.read())
    except LauncherError:
        raise
    except Exception as e:
        raise LauncherError("整合包解压失败：%s" % e, detail=str(e))

    for f in (index.get("files") or []):
        path = f.get("path") or ""
        if not path:
            continue
        dest = os.path.join(instance_root, *path.split("/"))
        if os.path.isfile(dest) and os.path.getsize(dest) > 0:
            continue  # 已由 override 提供
        urls = f.get("downloads") or []
        url = urls[0] if urls else ""
        if not url:
            continue  # 哈希方式无直链：跳过（PCL 也会提示缺失）
        items.append({
            "url": url,
            "dest": dest,
            "size": int(f.get("fileSize") or 0),
            "sha1": (f.get("hashes") or {}).get("sha1", ""),
        })

    mc, loader = _modpack_target(index)
    return items, index, mc, loader


def _modpack_target(index: dict):
    """从 index.dependencies 推导目标 MC 版本与加载器。"""
    deps = index.get("dependencies") or {}
    mc, loader = "", ""
    if isinstance(deps, dict):
        mc = deps.get("minecraft", "")
        for k in ("fabric", "forge", "quilt", "neoforge"):
            if k in deps:
                loader = k
                break
    elif isinstance(deps, list):
        for d in deps:
            if not isinstance(d, dict):
                continue
            pid = str(d.get("project_id") or "")
            ver = d.get("version") or ""
            if pid == "minecraft" or d.get("dependency_type") == "game":
                mc = ver or mc
            elif pid in LOADERS:
                loader = pid
    return mc, loader


def write_modpack_version_json(instance_root, new_folder, base_folder, mc, loader):
    """为导入的整合包写一个 inheritsFrom 基础加载器版本的版本 json，
    使其成为启动器可识别的独立实例。
    """
    version_json = os.path.join(instance_root, new_folder + ".json")
    data = {
        "id": new_folder,
        "inheritsFrom": base_folder,
        "type": "release",
        "releaseTime": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }
    if mc:
        data["releaseTime"] = "%sT00:00:00+08:00" % mc
    os.makedirs(instance_root, exist_ok=True)
    with open(version_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return version_json
