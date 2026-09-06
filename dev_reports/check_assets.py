# -*- coding: utf-8 -*-
"""资产缺失统计：对比 asset index 的 objects 与磁盘实际文件。只统计，不下载。"""
import json
import os
import sys
import io

ROOT = r"C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ASSETS = r"F:\.minecraft\assets"

out = {}
for name, index_id in (("1.21.5", "24"), ("fps1.20.1", "5"), ("1.21.11包", "32")):
    idx_path = os.path.join(ASSETS, "indexes", index_id + ".json")
    if not os.path.isfile(idx_path):
        out[name] = {"error": "索引不存在 " + index_id}
        continue
    with open(idx_path, "r", encoding="utf-8") as f:
        idx = json.load(f)
    objects = idx.get("objects") or {}
    total = len(objects)
    missing, missing_bytes = 0, 0
    examples = []
    for _, obj in objects.items():
        h = str(obj.get("hash") or "")
        size = int(obj.get("size") or 0)
        p = os.path.join(ASSETS, "objects", h[:2], h)
        if not os.path.isfile(p):
            missing += 1
            missing_bytes += size
            if len(examples) < 5:
                examples.append({"hash": h, "size": size})
    out[name] = {
        "index": index_id,
        "objects_total": total,
        "objects_missing": missing,
        "missing_bytes": missing_bytes,
        "missing_mb": round(missing_bytes / 1048576, 1),
        "examples_missing": examples,
    }
    print(name, "index=" + index_id,
          "total=%d missing=%d (%.1f MB)" % (total, missing, missing_bytes / 1048576))

with open(os.path.join(ROOT, "dev_reports", "evidence_assets_missing.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("saved -> dev_reports/evidence_assets_missing.json")
