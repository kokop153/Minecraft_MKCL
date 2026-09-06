# -*- coding: utf-8 -*-
"""下载源与文件下载模块：清单获取、镜像 URL 映射、原子下载。"""
import json
import os
import time
import urllib.error
import urllib.request
import hashlib

SOURCES = {
    "bmclapi": "https://bmclapi2.bangbang93.com",
    "official": "https://piston-meta.mojang.com",
}

_MANIFEST_URLS = {
    "bmclapi": "https://bmclapi2.bangbang93.com/version_manifest/v2",
    "official": "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
}

# bmclapi 兼容备用路径（老端点可能 404，退回镜像官方路径）
_MANIFEST_FALLBACKS = {
    "bmclapi": ["https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"],
    "official": ["https://piston-meta.mojang.com/mc/game/version_manifest.json"],
}

_UA = "MCLauncher/2.0"

_CHUNK = 64 * 1024  # 64KB 流式下载


def _open_url(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_version_manifest(source: str = "bmclapi", timeout: float = 20):
    """获取版本清单（v2）。失败抛 LauncherError。"""
    from launcher.errors import LauncherError
    urls = [_MANIFEST_URLS.get(source, "")]
    urls += _MANIFEST_FALLBACKS.get(source, [])
    urls = [u for u in urls if u]
    last_e = None
    for url in urls:
        try:
            with _open_url(url, timeout) as resp:
                data = resp.read()
            return json.loads(data.decode("utf-8"))
        except Exception as e:  # urllib.error.HTTPError/URLError/timeout/JSON 错误
            last_e = e
    raise LauncherError(
        "无法连接下载源，请检查网络或在设置中切换下载源",
        detail="%s: %s (%s)" % (type(last_e).__name__, last_e, urls[0]),
    )


def iter_manifest_versions(manifest: dict):
    """遍历清单版本列表，原样返回 versions 列表。"""
    return manifest.get("versions", []) or []


# bmclapi 镜像域名映射表：(原域名, 前缀替换)
_MIRROR_MAP = [
    ("piston-meta.mojang.com/", "bmclapi2.bangbang93.com/"),
    ("piston-data.mojang.com/", "bmclapi2.bangbang93.com/"),
    ("launcher.mojang.com/", "bmclapi2.bangbang93.com/"),
    ("libraries.minecraft.net/", "bmclapi2.bangbang93.com/maven/"),
    ("resources.download.minecraft.net/", "bmclapi2.bangbang93.com/assets/"),
]


def mirror_url(url: str, source: str = "bmclapi") -> str:
    """official→原样；bmclapi→按域名映射替换。"""
    if source != "bmclapi" or not url:
        return url
    for orig, repl in _MIRROR_MAP:
        if url.startswith("https://" + orig) or url.startswith("http://" + orig):
            prefix = "https://" if url.startswith("https://") else "http://"
            return prefix + repl + url[len(prefix) + len(orig):]
    return url


def sha1_ok(path: str, expect: str) -> bool:
    """校验文件 sha1 是否匹配 expect（expect 为空视为通过）。"""
    if not expect:
        return True
    if not os.path.isfile(path):
        return False
    h = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(_CHUNK), b""):
                h.update(chunk)
    except OSError:
        return False
    return h.hexdigest().lower() == str(expect).lower()


def download_file(url: str, dest: str, source: str = "bmclapi",
                  timeout: float = 30, retries: int = 3) -> dict:
    """镜像+流式下载到 dest（先 .tmp 再 os.replace），带退避重试。

    返回 {"dest": str, "size": int, "retries": int}；全败抛 LauncherError。
    """
    from launcher.errors import LauncherError
    final_url = mirror_url(url, source)
    dest = os.path.abspath(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".tmp"
    last_err = None
    used_retries = 0
    for attempt in range(max(1, retries)):
        try:
            size = 0
            with _open_url(final_url, timeout) as resp, open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    size += len(chunk)
            os.replace(tmp, dest)
            return {"dest": dest, "size": size, "retries": used_retries}
        except Exception as e:
            last_err = e
            used_retries = attempt + 1
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            if attempt < max(1, retries) - 1:
                time.sleep(2 ** attempt)  # 1s / 2s / 4s
    raise LauncherError(
        "下载失败（已重试 %d 次）：%s" % (used_retries, final_url[:120]),
        detail="%s: %s" % (type(last_err).__name__, last_err),
    )


def download_version(meta_item: dict, source: str, game_dir: str,
                     progress=None) -> str:
    """下载某版本 json 到 <game_dir>/versions/<id>/<id>.json，返回 json 路径。"""
    vid = meta_item.get("id") or "unknown"
    url = meta_item.get("url") or ""
    dest = os.path.join(game_dir, "versions", vid, vid + ".json")
    total = int(meta_item.get("size") or 0)
    if progress:
        try:
            progress(0, 1, vid + ".json", 0.0)
        except Exception:
            pass
    res = download_file(url, dest, source=source)
    if progress:
        try:
            progress(1, 1, vid + ".json", 100.0)
        except Exception:
            pass
    return res["dest"]


# ---------------- rules 过滤（与 launch.py 保持一致的副本） ----------------

_DEFAULT_FEATURES = {
    "has_custom_resolution": True,
    "is_demo_user": False,
    "has_custom_logo": False,
    "has_quick_plays_support": False,
    "is_quick_play_singleplayer": False,
    "is_quick_play_multiplayer": False,
    "is_quick_play_realms": False,
}


def _rules_allow(rules, os_name: str = "windows", features=None) -> bool:
    """Minecraft version json 的 rules 匹配：默认允许，无命中规则保持当前结果。"""
    if not rules:
        return True
    feats = dict(_DEFAULT_FEATURES)
    if features:
        feats.update(features)
    allow = True
    for rule in rules:
        act = rule.get("action")
        os_rule = rule.get("os") or {}
        feat_req = rule.get("features")
        if os_rule:
            name = str(os_rule.get("name", "")).lower()
            if name and name != os_name.lower():
                continue  # 该条规则只针对其他系统，跳过
            arch = os_rule.get("arch")
            if arch:
                import platform
                if str(platform.machine()).lower().find(str(arch).lower()) < 0:
                    continue
        if feat_req:
            if not all(feats.get(k, False) for k in feat_req):
                continue  # 特性不满足，该条不生效
        # 命中：更新结果
        allow = (act == "allow")
    return allow


def collect_download_items(game_dir: str, folder: str, source: str = "bmclapi",
                           include_assets: bool = True, include_libraries: bool = True,
                           include_natives: bool = True) -> list:
    """收集某版本全部下载项（jar / libraries / natives / assets）。

    项结构 {"url","dest","size","sha1"}，可能带 "skip_if_exists": True。
    """
    from launcher.version_scan import scan_versions, resolve_version_chain
    from launcher.maven import gav_to_url

    game_dir = os.path.abspath(game_dir)
    items = []

    versions = scan_versions(game_dir)
    found = None
    for v in versions:
        # VersionInfo 是 dataclass，用属性访问
        if getattr(v, "folder", None) == folder or getattr(v, "name", None) == folder:
            found = v
            break
    if not found:
        return items

    chain_data = resolve_version_chain(found)
    data = chain_data if isinstance(chain_data, dict) else {}
    if not data:
        return items

    # 1) 版本 jar
    client = (data.get("downloads") or {}).get("client") or {}
    jar_name = data.get("jar") or data.get("id") or folder
    if client.get("url"):
        items.append({
            "url": client.get("url", ""),
            "dest": os.path.join(game_dir, "versions", jar_name, jar_name + ".jar"),
            "size": int(client.get("size") or 0),
            "sha1": client.get("sha1", ""),
        })

    # 2) libraries（含 natives-windows）
    if include_libraries:
        for lib in data.get("libraries") or []:
            if not isinstance(lib, dict):
                continue
            if not _rules_allow(lib.get("rules")):
                continue
            downloads = lib.get("downloads") or {}
            artifact = downloads.get("artifact")
            if artifact and artifact.get("url"):
                items.append({
                    "url": artifact.get("url", ""),
                    "dest": os.path.join(game_dir, "libraries", artifact.get("path") or ""),
                    "size": int(artifact.get("size") or 0),
                    "sha1": artifact.get("sha1", ""),
                })
            elif lib.get("name"):
                # Maven 布局库（Fabric/Forge 安装器 json）：按 GAV + 仓库 url 推导
                from launcher.maven import gav_to_path, gav_to_url
                p = gav_to_path(lib["name"])
                if p:
                    url = gav_to_url(lib["name"], lib.get("url") or "https://libraries.minecraft.net/")
                    items.append({
                        "url": url,
                        "dest": os.path.join(game_dir, "libraries", *p.split("/")),
                        "size": 0,
                        "sha1": "",
                    })
            if include_natives:
                natives = lib.get("natives") or {}
                nw = natives.get("windows")
                if nw:
                    classifiers = (downloads.get("classifiers") or {}).get(nw) or {}
                    if classifiers.get("url"):
                        items.append({
                            "url": classifiers.get("url", ""),
                            "dest": os.path.join(
                                game_dir, "libraries", classifiers.get("path") or ""),
                            "size": int(classifiers.get("size") or 0),
                            "sha1": classifiers.get("sha1", ""),
                        })

    # 3) assets
    if include_assets:
        ai = data.get("assetIndex") or {}
        ai_url = ai.get("url")
        ai_id = ai.get("id") or "legacy"
        if ai_url:
            ai_dest = os.path.join(game_dir, "assets", "indexes", ai_id + ".json")
            items.append({
                "url": ai_url,
                "dest": ai_dest,
                "size": int(ai.get("size") or 0),
                "sha1": ai.get("sha1", ""),
            })
            # 读取索引（本地已有则直接读），展开 objects
            index_data = None
            if os.path.isfile(ai_dest):
                try:
                    with open(ai_dest, "r", encoding="utf-8") as f:
                        index_data = json.load(f)
                except Exception:
                    index_data = None
            if index_data is None:
                try:
                    with _open_url(mirror_url(ai_url, source), 30) as resp:
                        index_data = json.loads(resp.read().decode("utf-8"))
                except Exception:
                    index_data = None
            if isinstance(index_data, dict):
                for _, obj in (index_data.get("objects") or {}).items():
                    h = str(obj.get("hash") or "")
                    if not h or len(h) < 2:
                        continue
                    dest = os.path.join(game_dir, "assets", "objects", h[:2], h)
                    item = {
                        "url": "https://resources.download.minecraft.net/%s/%s" % (h[:2], h),
                        "dest": dest,
                        "size": int(obj.get("size") or 0),
                        "sha1": h,
                    }
                    if os.path.isfile(dest) and sha1_ok(dest, h):
                        item["skip_if_exists"] = True
                    items.append(item)
    return items
