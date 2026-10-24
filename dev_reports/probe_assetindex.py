# -*- coding: utf-8 -*-
import os, sys, io, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from launcher.logsetup import setup_logging
setup_logging(ROOT)
from launcher.launch import build_launch_command
from launcher.version_scan import scan_versions, resolve_version_chain, derive_mc_version

GAME_DIR = r"F:\.minecraft"
info = next(v for v in scan_versions(GAME_DIR) if v.folder == "fps1.20.1")
data = resolve_version_chain(info)
print("json assetIndex:", json.dumps(data.get("assetIndex"), ensure_ascii=False)[:120])
print("json arguments.game 含 --assetIndex?:",
      any(isinstance(x, str) and x == "--assetIndex" for x in (data.get("arguments") or {}).get("game") or []))
print("json minecraftArguments:", str(data.get("minecraftArguments"))[:120])

cmd = build_launch_command(GAME_DIR, "fps1.20.1",
    r"C:\Users\LiXiaoHao\AppData\Roaming\.minecraft\runtime\java-runtime-gamma-snapshot\bin\javaw.exe",
    memory_gb=4, username="kokop", uuid="43465a85-8a83-36d3-8a93-ae2ee0cc2baa",
    isolate_dir=True)
c = cmd["command"]
i = c.index("--assetIndex")
print("构建命令 --assetIndex 值:", repr(c[i+1]))
print("构建命令 --assetsDir 值:", repr(c[c.index("--assetsDir")+1]))
