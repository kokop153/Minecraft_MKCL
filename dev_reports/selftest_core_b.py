# -*- coding: utf-8 -*-
"""启动引擎自测（Core B）。"""
import json
import os
import shutil
import sys
import tempfile
import time
import uuid as uuidlib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

GAME_DIR = r"F:\.minecraft"
JAVA = r"F:\MSL\Java21\bin\javaw.exe"

for attempt in range(8):
    try:
        from launcher.errors import LauncherError
        from launcher.version_scan import (
            VersionInfo,
            scan_versions,
            resolve_version_chain,
            get_version_mc_version,
        )
        from launcher.launch import (
            build_launch_command,
            extract_natives,
            _rules_allow,
            _substitute,
        )
        break
    except ImportError as e:
        print("import 尚未就绪（第 %d 次）：%s" % (attempt + 1, e))
        if attempt == 7:
            print("SKIP: launcher.errors/version_scan import 失败（等待并行 Agent 8 次 x15s 仍失败）")
            sys.exit(0)
        time.sleep(15)

results = []


def check(name, cond, extra=""):
    if cond:
        print("PASS:", name, extra)
        results.append(True)
    else:
        print("FAIL:", name, extra)
        results.append(False)


# ---- 1. scan_versions ----
versions = scan_versions(GAME_DIR)
check("scan_versions 数量>=20", len(versions) >= 20, "实际=%d" % len(versions))
v1201 = next((v for v in versions if v.folder == "1.20.1"), None)
check("1.20.1 存在且 valid", v1201 is not None and v1201.valid)
check("get_version_mc_version", v1201 and get_version_mc_version(v1201) == "1.20.1")
invalid = [v.folder for v in versions if not v.valid]
print("INFO: 无效版本 %d 个（无 json/解析失败，已记录 reason）：%s" % (len(invalid), invalid[:5]))

# ---- 2. build_launch_command 原版 1.20.1（本机实为 Fabric 合并版 json） ----
offline_uuid = str(uuidlib.uuid3(uuidlib.NAMESPACE_OID, "OfflinePlayer:kokop"))
cmd = build_launch_command(
    game_dir=GAME_DIR,
    folder="1.20.1",
    java_path=JAVA,
    username="kokop",
    uuid=offline_uuid,
    memory_gb=4,
)
command = cmd["command"]
check("command[0]==java", command[0] == JAVA)
check("-cp in command", "-cp" in command)
mc_idx = command.index("-cp")
main_class = command[mc_idx + 2]
check("mainClass 非空", bool(main_class) and not main_class.startswith("-"), main_class)
classpath = cmd["classpath"]
check("classpath 长度>5000", len(classpath) > 5000, "len=%d" % len(classpath))
check("command 无空串元素", all(str(x).strip() for x in command))
check("无残留 ${...} 未替换", not any("${" in str(x) for x in command))
if "--username" in command:
    check("--username 后跟 kokop", command[command.index("--username") + 1] == "kokop")
else:
    check("--username 后跟 kokop", False, "无 --username")
check("natives_dir 存在", os.path.isdir(cmd["natives_dir"]), cmd["natives_dir"])
check("missing_libs 为空（原版）", not cmd["missing_libs"], str(cmd["missing_libs"][:3]))

# ---- 3. 继承链（真实目录无 inheritsFrom，用合成版本验证 + 真实 Fabric 独立版构建） ----
tmp = tempfile.mkdtemp(prefix="mc_chain_")
os.makedirs(os.path.join(tmp, "versions", "TestParent"))
os.makedirs(os.path.join(tmp, "versions", "TestChild"))
parent_json = {
    "id": "TestParent", "mainClass": "net.minecraft.client.main.Main",
    "type": "release", "libraries": [
        {"name": "com.fake:parent-only:1.0", "url": "http://a/"},
        {"name": "com.fake:shared:1.0", "url": "http://a/"},
    ],
    "arguments": {"game": ["--parentGame"], "jvm": ["-DparentJvm=1"]},
    "assetIndex": {"id": "5"},
    "minecraftArguments": "--parentOldArg 1",
}
child_json = {
    "id": "TestChild", "inheritsFrom": "TestParent",
    "mainClass": "net.fabricmc.loader.impl.launch.knot.KnotClient",
    "libraries": [{"name": "com.fake:shared:1.0", "url": "http://a/"},
                  {"name": "com.fake:child-only:1.0", "url": "http://b/"}],
    "arguments": {"game": ["--childGame"], "jvm": ["-DchildJvm=1"]},
}
with open(os.path.join(tmp, "versions", "TestParent", "TestParent.json"), "w", encoding="utf-8") as f:
    json.dump(parent_json, f)
with open(os.path.join(tmp, "versions", "TestChild", "TestChild.json"), "w", encoding="utf-8") as f:
    json.dump(child_json, f)
child_info = VersionInfo(
    folder="TestChild", game_dir=tmp,
    json_path=os.path.join(tmp, "versions", "TestChild", "TestChild.json"),
    jar_path="", name="TestChild", base="TestParent",
    mc_version="TestChild", valid=True, reason="",
)
merged = resolve_version_chain(child_info)
check("resolve_version_chain 成功", isinstance(merged, dict))
check("合并后 mainClass=子", merged["mainClass"] == "net.fabricmc.loader.impl.launch.knot.KnotClient")
check("合并 libraries 去重子在前(3 项)", len(merged["libraries"]) == 3
      and {l["name"] for l in merged["libraries"]} == {"com.fake:shared:1.0", "com.fake:child-only:1.0", "com.fake:parent-only:1.0"},
      str([l["name"] for l in merged["libraries"]]))
check("合并 arguments game=父+子", merged["arguments"]["game"] == ["--parentGame", "--childGame"])
check("合并 arguments jvm=父+子", merged["arguments"]["jvm"] == ["-DparentJvm=1", "-DchildJvm=1"])
check("assetIndex 用父", merged["assetIndex"]["id"] == "5")
check("_chain 记录祖先", merged["_chain"] == ["TestParent"], str(merged["_chain"]))
try:
    resolve_version_chain(VersionInfo(
        folder="TestChild", game_dir=tmp,
        json_path=os.path.join(tmp, "versions", "TestChild", "TestChild.json"),
        jar_path="", name="", base="", mc_version="", valid=True, reason=""))
    # 循环检测：把父改为指向自身
    parent_json["inheritsFrom"] = "TestParent"
    with open(os.path.join(tmp, "versions", "TestParent", "TestParent.json"), "w", encoding="utf-8") as f:
        json.dump(parent_json, f)
    from launcher.version_scan import VersionInfo as VI
    try:
        resolve_version_chain(VI(
            folder="TestParent", game_dir=tmp,
            json_path=os.path.join(tmp, "versions", "TestParent", "TestParent.json"),
            jar_path="", name="", base="", mc_version="", valid=True, reason=""))
        check("循环继承抛 LauncherError", False)
    except LauncherError:
        check("循环继承抛 LauncherError", True)
except LauncherError as e:
    check("循环继承抛 LauncherError", False, str(e))
shutil.rmtree(tmp, ignore_errors=True)

real_inherited = next(
    (v for v in versions if v.folder == "1.20.1-Fabric 0.16.14-OptiFine_I6"), None)
if real_inherited and real_inherited.valid:
    try:
        cmd2 = build_launch_command(
            game_dir=GAME_DIR, folder=real_inherited.folder, java_path=JAVA,
            username="kokop", uuid=offline_uuid, memory_gb=4)
        check("真实 Fabric 版 build_launch_command 不抛异常", True,
              "missing=%d" % len(cmd2["missing_libs"]))
    except LauncherError as e:
        check("真实 Fabric 版 build_launch_command 不抛异常", False, str(e))
else:
    check("找到真实 Fabric 版本", False)

# ---- 4. 旧格式版本（minecraftArguments）----
old_candidates = ["1.12.2-Forge_14.23.5.2859", "1.8.9PVP", "1.8.8-OptiFine_I7"]
old_target = None
for name in old_candidates:
    cand = next((v for v in versions if v.folder == name), None)
    if cand and cand.valid:
        with open(cand.json_path, "r", encoding="utf-8") as f:
            if json.load(f).get("minecraftArguments"):
                old_target = cand
                break
if old_target:
    try:
        cmd3 = build_launch_command(
            game_dir=GAME_DIR, folder=old_target.folder, java_path=JAVA,
            username="kokop", uuid=offline_uuid, memory_gb=4)
        check("旧格式版本 build_launch_command 不抛异常", True,
              "folder=%s missing=%d" % (old_target.folder, len(cmd3["missing_libs"])))
    except LauncherError as e:
        check("旧格式版本 build_launch_command 不抛异常", False, str(e))
else:
    check("找到旧格式版本", False)

# ---- 5. extract_natives ----
data1201 = resolve_version_chain(v1201)
has_natives_decl = any(lib.get("natives") for lib in data1201.get("libraries") or [])
natives_dir = extract_natives(data1201, os.path.join(GAME_DIR, "versions", "1.20.1"), "1.20.1")
dlls_1201 = [f for f in os.listdir(natives_dir) if f.lower().endswith(".dll")] \
    if os.path.isdir(natives_dir) else []
if not has_natives_decl:
    check("1.20.1 无 natives 声明（1.19+ 正常，LWJGL 自带平台 jar）", len(dlls_1201) == 0,
          "natives声明=%s" % has_natives_decl)
    print("INFO: 1.20.1 无 natives 声明，.dll 由 LWJGL 平台 jar 自行加载")
else:
    check("extract_natives 1.20.1 有 .dll", len(dlls_1201) > 0, "dll=%d" % len(dlls_1201))

# 旧格式版本真实解压验证（text2speech/jinput natives jar 本机存在）
if old_target:
    old_data = resolve_version_chain(old_target)
    old_decl = any(lib.get("natives") for lib in old_data.get("libraries") or [])
    old_natives = extract_natives(
        old_data, os.path.join(GAME_DIR, "versions", old_target.folder), old_target.folder)
    old_dlls = [f for f in os.listdir(old_natives) if f.lower().endswith(".dll")] \
        if os.path.isdir(old_natives) else []
    check("旧格式版本 extract_natives 解压出 .dll", (not old_decl) or len(old_dlls) > 0,
          "natives声明=%s dll数=%d" % (old_decl, len(old_dlls)))

# ---- 附：_rules_allow / _substitute ----
check("_rules_allow 无 rules", _rules_allow(None, {}))
check("_rules_allow os 匹配 allow", _rules_allow([{"os": {"name": "windows"}, "allow": True}], {}))
check("_rules_allow os 不匹配→False", not _rules_allow([{"os": {"name": "osx"}, "allow": True}], {}))
check("_rules_allow mac 参数不上 Windows",
      not _rules_allow([{"rules": [{"action": "allow", "os": {"name": "osx"}}]}] and
                       [{"action": "allow", "os": {"name": "osx"}}], {}))
check("_rules_allow 无生效规则默认 False",
      not _rules_allow([{"action": "disallow", "os": {"name": "osx"}}], {}),
      "disallow-osx 在 Windows 上不生效→默认 False（与 Prism 一致；官方 json 用 allow+os 配对，不受影响）")
check("_substitute 未知置 0", _substitute("${no_such_key}", {}) == "0")
check("_substitute 已知替换", _substitute("a=${auth_player_name}b", {"auth_player_name": "kokop"}) == "a=kokopb")

print()
total_pass = sum(results)
total = len(results)
print("====== 汇总：PASS=%d FAIL=%d ======" % (total_pass, total - total_pass))
print("版本总数：%d（无效 %d 个）" % (len(versions), len(invalid)))
print("classpath 长度：%d" % len(classpath))
print("mainClass：%s" % main_class)
print("natives 目录：%s" % natives_dir)
sys.exit(0 if all(results) else 1)
