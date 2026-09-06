# -*- coding: utf-8 -*-
"""回归：两个不同版本 id 构建启动命令，核对 mainClass/natives/classpath/参数随版本变化。"""
import os, sys, json, io
ROOT = r"C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher"
sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from launcher.logsetup import setup_logging
setup_logging(ROOT)
from launcher.launch import build_launch_command
from launcher.version_scan import scan_versions, derive_mc_version
from launcher.java_utils import pick_java_for, find_javas

GAME_DIR = r"F:\.minecraft"
versions = scan_versions(GAME_DIR)
targets = [v for v in versions if v.folder in ("fps1.20.1", "1.21.5")]
javas = find_javas()
out = {}
for info in targets:
    mcver = derive_mc_version(info)
    jr = pick_java_for(mcver, javas)
    java = (jr.is_javaw or jr.path) if jr else ""
    cmd = build_launch_command(GAME_DIR, info.folder, java, memory_gb=4,
                               username="kokop", uuid="43465a85-8a83-36d3-8a93-ae2ee0cc2baa")
    c = cmd["command"]
    icp = c.index("-cp")
    mc = c[icp + 1]
    out[info.folder] = {
        "derived_mc_version": mcver,
        "java_picked": java,
        "java_major": jr.major if jr else None,
        "mainClass": c[icp + 2],
        "natives_dir": cmd["natives_dir"],
        "classpath_entries": len(mc.split(";")),
        "total_args": len(c),
        "missing_libs": len(cmd["missing_libs"]),
        "workdir": cmd["workdir"],
        "java_is_arg0": c[0] == java,
    }
print(json.dumps(out, ensure_ascii=False, indent=2))
with open(os.path.join(ROOT, "dev_reports", "evidence_regress_two_versions.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
a, b = list(out.values())
diff = (a["mainClass"] != b["mainClass"] and a["mainClass"] not in ("", "--username")
        and b["mainClass"] not in ("", "--username")
        and (a["total_args"] != b["total_args"] or a["natives_dir"] != b["natives_dir"]
             or a["derived_mc_version"] != b["derived_mc_version"]
             or a["classpath_entries"] != b["classpath_entries"]))
print("VERSION_PARAMETERIZED_DIFF:", diff)
assert a["java_is_arg0"] and b["java_is_arg0"], "command[0] 必须是解析后的 Java 路径"
print("JAVA_ARG0_OK")
