# -*- coding: utf-8 -*-
"""多实例冒烟：命令构建层面验证 3 实例的独立性（不拉起真实进程）。"""
import os, sys, io, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from launcher.launch import build_launch_command
from launcher.accounts import offline_uuid

GAME_DIR = r"F:\.minecraft"
JAVA = r"C:\Users\LiXiaoHao\AppData\Roaming\.minecraft\runtime\java-runtime-gamma-snapshot\bin\javaw.exe"
out = {}
for k in (1, 2, 3):
    uname = "kokop" if k == 1 else ("kokop" + str(k))[:16]
    cmd = build_launch_command(GAME_DIR, "fps1.20.1", JAVA, memory_gb=2,
                               username=uname, uuid=offline_uuid(uname),
                               user_type="legacy", isolate_dir=True,
                               instance_tag=str(k))
    c = cmd["command"]
    workdir = cmd["workdir"]
    gd = c[c.index("--gameDir") + 1]
    un = c[c.index("--username") + 1]
    out[k] = {"workdir": workdir, "gameDir_arg": gd, "username": un,
              "natives": cmd["natives_dir"], "missing": len(cmd["missing_libs"])}
    print("实例%d: workdir=%s username=%s natives=%s 缺库=%d" %
          (k, workdir, un, cmd["natives_dir"], len(cmd["missing_libs"])))
ok = (out[1]["workdir"] != out[2]["workdir"] != out[3]["workdir"]
      and out[1]["username"] == "kokop" and out[2]["username"] == "kokop2"
      and all(v["missing"] == 0 for v in out.values()))
with open(os.path.join(ROOT, "dev_reports", "evidence_multi_build.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("MULTI_BUILD", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
