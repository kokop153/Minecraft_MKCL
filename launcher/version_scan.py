# -*- coding: utf-8 -*-
"""版本扫描与继承链解析。"""
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from launcher.errors import LauncherError

# 从任意字符串中提取真实 MC 版本号（只认 1.x 形态，避免把 Fabric loader 版本 0.x.y 之类误判为 MC 版本）
_MC_VER_RE = re.compile(r"(?<![\d.])1\.\d+(?:\.\d+)?(?:-pre\d+)?")


@dataclass
class VersionInfo:
    folder: str
    game_dir: str
    json_path: str
    jar_path: str
    name: str
    base: str  # inheritsFrom 的父版本名，无继承为 ""
    mc_version: str
    valid: bool
    reason: str


def scan_versions(game_dir: str) -> List[VersionInfo]:
    versions_root = os.path.join(game_dir, "versions")
    if not os.path.isdir(versions_root):
        raise LauncherError(
            "游戏目录不存在：" + game_dir,
            detail="未找到 versions 目录：" + versions_root,
        )
    results: List[VersionInfo] = []
    try:
        folders = sorted(os.listdir(versions_root))
    except OSError as e:
        raise LauncherError("读取 versions 目录失败：" + str(e), detail=versions_root)
    for folder in folders:
        vdir = os.path.join(versions_root, folder)
        if not os.path.isdir(vdir):
            continue
        json_path = os.path.join(vdir, folder + ".json")
        if not os.path.isfile(json_path):
            candidates = sorted(
                f for f in os.listdir(vdir) if f.lower().endswith(".json")
            )
            if candidates:
                json_path = os.path.join(vdir, candidates[0])
            else:
                results.append(
                    VersionInfo(
                        folder=folder,
                        game_dir=game_dir,
                        json_path="",
                        jar_path=os.path.join(vdir, folder + ".jar"),
                        name=folder,
                        base="",
                        mc_version=folder,
                        valid=False,
                        reason="版本目录中没有 json 文件",
                    )
                )
                continue
        info = VersionInfo(
            folder=folder,
            game_dir=game_dir,
            json_path=json_path,
            jar_path=os.path.join(vdir, folder + ".jar"),
            name=folder,
            base="",
            mc_version=folder,
            valid=True,
            reason="",
        )
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            info.valid = False
            info.reason = "版本 json 解析失败：" + str(e)
            results.append(info)
            continue
        info.mc_version = str(data.get("id") or folder)
        info.name = str(data.get("id") or folder)
        info.base = str(data.get("inheritsFrom") or "")
        results.append(info)
    results.sort(key=lambda v: v.folder)
    return results


def _load_json(json_path: str, folder: str) -> dict:
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise LauncherError(
            "读取版本 json 失败：" + folder,
            detail=json_path + "：" + str(e),
        )


def _merge(child: dict, parent: dict, chain: List[str]) -> dict:
    merged = dict(parent)
    merged.update({k: v for k, v in child.items() if k != "inheritsFrom"})

    # libraries：子在前，按 (name, url) 去重
    libs = []
    seen = set()
    for lib in list(child.get("libraries") or []) + list(parent.get("libraries") or []):
        key = (lib.get("name"), lib.get("url"))
        if key in seen:
            continue
        seen.add(key)
        libs.append(lib)
    merged["libraries"] = libs

    # mainClass：子有则子
    merged["mainClass"] = child.get("mainClass") or parent.get("mainClass")

    # minecraftArguments：父子都有 → "父 子"
    cargs = child.get("minecraftArguments")
    pargs = parent.get("minecraftArguments")
    if cargs and pargs:
        merged["minecraftArguments"] = str(pargs) + " " + str(cargs)
    else:
        merged["minecraftArguments"] = cargs or pargs or ""

    # arguments（新格式）：game/jvm 父+子拼接
    cargs_new = child.get("arguments") or {}
    pargs_new = parent.get("arguments") or {}
    if cargs_new or pargs_new:
        new_arguments: Dict[str, list] = {}
        for side in ("game", "jvm"):
            cside = cargs_new.get(side)
            pside = pargs_new.get(side)
            if cside is not None and pside is not None:
                new_arguments[side] = list(pside) + list(cside)
            else:
                side_val = cside if cside is not None else pside
                if side_val is not None:
                    new_arguments[side] = list(side_val)
        merged["arguments"] = new_arguments

    # assetIndex：子没有用父
    if not child.get("assetIndex") and parent.get("assetIndex"):
        merged["assetIndex"] = parent["assetIndex"]

    merged["_chain"] = list(chain)
    return merged


def resolve_version_chain(info: VersionInfo) -> dict:
    data = _load_json(info.json_path, info.folder)
    if not data.get("inheritsFrom"):
        out = json.loads(json.dumps(data))  # 深拷贝
        out["_chain"] = []
        return out

    chain: List[str] = []
    visited = {info.folder}

    def resolve(folder: str) -> dict:
        if folder in visited:
            raise LauncherError(
                "版本继承链存在循环：" + folder,
                detail="chain=" + str(chain),
            )
        visited.add(folder)
        chain.append(folder)
        parent_json = os.path.join(
            info.game_dir, "versions", folder, folder + ".json"
        )
        if not os.path.isfile(parent_json):
            raise LauncherError(
                "找不到父版本：" + folder,
                detail="缺少 " + parent_json,
            )
        pdata = _load_json(parent_json, folder)
        if pdata.get("inheritsFrom"):
            grand = resolve(str(pdata["inheritsFrom"]))
            return _merge(pdata, grand, chain)
        return json.loads(json.dumps(pdata))

    parent_name = str(data["inheritsFrom"])
    parent_data = resolve(parent_name)
    merged = _merge(data, parent_data, chain)
    logging.info(
        "版本继承链解析完成：%s -> %s", info.folder, " -> ".join(merged["_chain"])
    )
    return merged


def get_version_mc_version(info: VersionInfo) -> str:
    return info.mc_version


def derive_mc_version(info: VersionInfo) -> str:
    """从版本信息推导真实 Minecraft 版本号（用于 Java 版本匹配）。

    自定义文件夹名（如 my1.20.1、1.21.11红石生电优化）的 id 往往不是纯版本号，
    且 Fabric 官方安装器的默认 id（形如 fabric-loader-0.x.y-1.20.1）里 loader 版本在前，
    因此只采信 1.x 形态的匹配。按优先级依次尝试：
      1. 版本 json 的 id / 文件夹名中的版本号模式
      2. 继承链父版本（祖先 folder）中的版本号
      3. Fabric intermediary 库坐标中的版本（net.fabricmc:intermediary:1.20.1）
      4. inheritsFrom 字段本身
    全部失败时回退原始 mc_version。
    """
    for cand in (info.mc_version, info.folder, info.name):
        m = _MC_VER_RE.search(str(cand or ""))
        if m:
            return m.group(0)
    try:
        data = resolve_version_chain(info)
    except LauncherError:
        data = {}
    for anc in reversed(data.get("_chain") or []):
        m = _MC_VER_RE.search(str(anc))
        if m:
            return m.group(0)
    for lib in data.get("libraries") or []:
        nm = str((lib or {}).get("name") or "")
        if "intermediary" in nm:
            parts = nm.split(":")
            if len(parts) >= 3 and parts[2]:
                return parts[2]
    m = _MC_VER_RE.search(str(info.base or ""))
    if m:
        return m.group(0)
    return info.mc_version
