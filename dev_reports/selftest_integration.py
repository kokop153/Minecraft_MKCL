# -*- coding: utf-8 -*-
"""集成自测：版本扫描 -> 继承链 -> Java 选择 -> 启动命令构建 -> 下载管理器。

真实环境：F:\\.minecraft（70+ 版本）、BMCLAPI 镜像。
下载测试在临时目录进行，不污染真实游戏目录。
"""
import os
import sys
import time
import json
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from launcher.errors import LauncherError
from launcher.logsetup import setup_logging
from launcher.version_scan import scan_versions, resolve_version_chain
from launcher.java_utils import find_javas, pick_java_for
from launcher.launch import build_launch_command
from launcher import meta
from launcher.download import DownloadManager

PASS = []
FAIL = []

# 版本/目录参数化：命令行参数 > 项目 config.json > 默认值
_cfg_path = os.path.join(ROOT, "config.json")
_cfg = {}
if os.path.isfile(_cfg_path):
    with open(_cfg_path, "r", encoding="utf-8") as _f:
        _cfg = json.load(_f)
GAME_DIR = sys.argv[2] if len(sys.argv) > 2 else (_cfg.get("game_dir") or r"F:\.minecraft")
TARGET_VERSION = sys.argv[1] if len(sys.argv) > 1 else (_cfg.get("current_version") or "1.20.1")


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("PASS", name, detail)
    else:
        FAIL.append(name)
        print("FAIL", name, detail)


def main():
    log_path = setup_logging(ROOT)
    check("logsetup", os.path.isfile(log_path), log_path)

    # ---- 1. 版本扫描（真实游戏目录） ----
    GAME_DIR = r"F:\.minecraft"
    versions = scan_versions(GAME_DIR)
    print("scan_versions -> %d 个版本" % len(versions))
    check("scan>=70", len(versions) >= 70, "actual=%d" % len(versions))
    folders = [v.folder for v in versions]
    check("scan has %s" % TARGET_VERSION, TARGET_VERSION in folders,
          "target=%s" % TARGET_VERSION)
    invalid = [v for v in versions if not v.valid]
    print("invalid versions:", len(invalid), [v.folder for v in invalid][:5])

    # ---- 2. 继承链解析（Fabric+OptiFine 叠层） ----
    target = "1.20.1-Fabric 0.16.14-OptiFine_I6"
    info = next(v for v in versions if v.folder == target)
    merged = resolve_version_chain(info)
    check("chain merged dict", isinstance(merged, dict) and merged.get("mainClass"))
    print("  mainClass =", merged.get("mainClass"))
    print("  _chain =", merged.get("_chain"))
    print("  libraries =", len(merged.get("libraries") or []))
    check("chain libs>20", len(merged.get("libraries") or []) > 20)
    args_new = (merged.get("arguments") or {})
    check("chain arguments merged",
          bool(args_new.get("game")) and bool(args_new.get("jvm")))

    # ---- 3. Java 探测与选择 ----
    javas = find_javas()
    print("find_javas -> %d 个" % len(javas))
    for j in javas:
        print("  ", j.path, j.version, "major=", j.major, j.vendor)
    check("javas>=4", len(javas) >= 4)
    jr = pick_java_for("1.20.1", javas)
    print("pick_java_for('1.20.1') ->", jr.path if jr else None)
    check("pick java ok", jr is not None and jr.major >= 17)
    javaw = jr.is_javaw or jr.path
    check("javaw exists", os.path.isfile(javaw), javaw)

    # ---- 4. 启动命令构建（真实版本，参数来自 config/命令行） ----
    print("build target version:", TARGET_VERSION)
    cmd = build_launch_command(
        GAME_DIR, TARGET_VERSION, javaw,
        memory_gb=4, username="kokop",
        uuid="43465a85-8a83-36d3-8a93-ae2ee0cc2baa",
        width=854, height=480,
    )
    print("command args:", len(cmd["command"]))
    print("workdir:", cmd["workdir"])
    print("missing_libs:", len(cmd["missing_libs"]), cmd["missing_libs"][:3])
    check("cmd has -Xmx4G", "-Xmx4G" in cmd["command"])
    check("cmd has -cp", "-cp" in cmd["command"])
    check("cmd workdir ok", os.path.isdir(cmd["workdir"]))
    check("cmd natives dir", os.path.isdir(cmd["natives_dir"]))
    dlls = [f for f in os.listdir(cmd["natives_dir"]) if f.lower().endswith(".dll")]
    print("natives dlls:", len(dlls), dlls[:5])
    check("natives dlls>0", len(dlls) > 0)
    print("missing_libs 总数 =", len(cmd["missing_libs"]))
    # fps1.20.1 是真实可玩版本，库应齐全
    check("no missing libs", len(cmd["missing_libs"]) == 0)

    # ---- 5. 清单获取（BMCLAPI 镜像） ----
    manifest = meta.fetch_version_manifest("bmclapi")
    mvs = meta.iter_manifest_versions(manifest)
    print("manifest versions:", len(mvs))
    check("manifest>100", len(mvs) > 100)
    rel = [v for v in mvs if v.get("type") == "release"]
    check("manifest has releases", len(rel) > 0)
    latest = rel[0]["id"]
    print("latest release:", latest)

    # ---- 6. 下载链路（临时目录，不污染真实目录） ----
    tmp_game = os.path.join(ROOT, ".testtmp", "game")
    shutil.rmtree(os.path.join(ROOT, ".testtmp"), ignore_errors=True)
    os.makedirs(os.path.join(tmp_game, "versions"), exist_ok=True)
    item = next(v for v in mvs if v.get("id") == latest)
    json_path = meta.download_version(item, "bmclapi", tmp_game)
    check("version json downloaded", os.path.isfile(json_path), json_path)
    print("json size:", os.path.getsize(json_path))

    items = meta.collect_download_items(tmp_game, latest, "bmclapi")
    print("collect_download_items:", len(items), "项")
    check("collect items>100", len(items) > 100)
    # 客户端 jar 在列表里
    jar_items = [i for i in items if i["dest"].endswith(".jar") and "versions" in i["dest"]]
    check("client jar in items", len(jar_items) >= 1)
    idx_items = [i for i in items if os.path.sep + "indexes" + os.path.sep in i["dest"]]
    print("index items:", len(idx_items))

    # ---- 7. DownloadManager 并发下载（只下 2 个小文件：索引 json + 首个库） ----
    small = idx_items[:1]
    lib_items = [i for i in items if i["dest"].endswith(".jar") and "libraries" in i["dest"]]
    if lib_items:
        small.append(lib_items[0])
    result = {"progress": [], "done": None, "error": None}

    def on_progress(done, total, name, pct):
        result["progress"].append((done, total, name, pct))

    def on_done(ok, failed):
        result["done"] = (ok, failed)

    dm = DownloadManager(source="bmclapi", max_workers=4)
    dm.download(small, on_progress, on_done, lambda e: result.__setitem__("error", e))
    for _ in range(120):
        if result["done"] is not None:
            break
        time.sleep(0.5)
    check("download done cb", result["done"] is not None)
    if result["done"]:
        ok, failed = result["done"]
        print("download ok=%d failed=%d" % (ok, len(failed)))
        for f in failed:
            print("  failed:", f)
        check("download ok==all", ok == len(small) and not failed,
              "ok=%d total=%d" % (ok, len(small)))
        for it in small:
            check("file exists " + os.path.basename(it["dest"]),
                  os.path.isfile(it["dest"]) and meta.sha1_ok(it["dest"], it.get("sha1", "")),
                  "%d bytes" % (os.path.getsize(it["dest"]) if os.path.isfile(it["dest"]) else -1))
    check("no download error", result["error"] is None)
    check("progress cb fired", len(result["progress"]) > 0)

    shutil.rmtree(os.path.join(ROOT, ".testtmp"), ignore_errors=True)

    print()
    print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main()
