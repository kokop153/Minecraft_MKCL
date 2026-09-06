# -*- coding: utf-8 -*-
"""derive_mc_version 二轮修复验证：审查员全部用例 + fabric 官方 id。"""
import os, sys, io, json
ROOT = r"C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher"
sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from launcher.version_scan import VersionInfo, derive_mc_version
from launcher.java_utils import _required_major

def vi(folder, name=None):
    return VersionInfo(folder=folder, game_dir="X", json_path="", jar_path="",
                       name=name or folder, base="", mc_version=name or folder,
                       valid=True, reason="")

cases = [
    ("fps1.20.1", "1.20.1"),
    ("1.21.5", "1.21.5"),
    ("1.20.1-Fabric 0.16.14-OptiFine_I6", "1.20.1"),
    ("1.21.11红石生电优化", "1.21.11"),
    ("fabric-loader-0.16.14-1.20.1", "1.20.1"),
    ("Fabric 0.16.14 1.20.1", "1.20.1"),
    ("my1.20.1", "1.20.1"),
]
results = []
ok = True
for folder, expect in cases:
    got = derive_mc_version(vi(folder))
    rm = _required_major(got)
    passed = (got == expect) and (rm != 8 or expect.split(".")[0] == "1" and rm == 8 and False)
    # 期望：推导值一致；且 required_major 与期望版本匹配
    exp_major = {"1.20.1": 17, "1.21.5": 21, "1.21.11": 21}[expect]
    passed = (got == expect) and (rm == exp_major)
    results.append({"input": folder, "derived": got, "expected": expect,
                    "required_major": rm, "pass": passed})
    print(("PASS" if passed else "FAIL"), folder, "->", got, "major=%d" % rm)
    ok = ok and passed

# 无法推导的兜底行为（审查问题2：记录为已知限制）
weird = derive_mc_version(vi("11451419191800's Redstone Optimization"))
print("INFO 无可推导信息回退:", weird)

with open(os.path.join(ROOT, "dev_reports", "evidence_derive_fix2.json"), "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("DERIVE_FIX2_ALL_OK" if ok else "DERIVE_FIX2_FAILED")
sys.exit(0 if ok else 1)
