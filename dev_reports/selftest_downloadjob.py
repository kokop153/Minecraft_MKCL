# -*- coding: utf-8 -*-
"""复现用户崩溃路径：下载页 _on_collect -> DownloadJob.start(missing) -> 回调完成。"""
import os, sys, io, time, json, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

tmp = os.path.join(ROOT, ".testtmp", "downloadjob")
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(tmp, exist_ok=True)

from launcher import meta
from launcher.ui.workers import DownloadJob

# 用一个真实小文件（BMCLAPI 的版本 json，几十 KB）模拟"缺失文件"下载项
mvs = meta.iter_manifest_versions(meta.fetch_version_manifest("bmclapi"))
item = next(v for v in mvs if v.get("type") == "release")
dest = os.path.join(tmp, item["id"] + ".json")
items = [{"url": item["url"], "dest": dest, "size": int(item.get("size") or 0), "sha1": item.get("sha1", "")}]

state = {"progress": [], "done": None, "error": None}
job = DownloadJob(source="bmclapi")
assert hasattr(job, "source") and job.source == "bmclapi", "source 属性缺失（原崩溃点）"
job.bridge.progress.connect(lambda d, t, n, p: state["progress"].append((d, t, n)))
job.bridge.finished.connect(lambda ok, failed: state.__setitem__("done", (ok, failed)))
job.bridge.failed.connect(lambda e: state.__setitem__("error", e))
job.start(items)   # ← 用户崩溃的这一行

t0 = time.time()
while time.time() - t0 < 60 and state["done"] is None and state["error"] is None:
    app.processEvents()
    time.sleep(0.2)

ok = state["done"] is not None and state["done"][0] == 1 and not state["done"][1]
print("source attr:", job.source)
print("progress cb:", len(state["progress"]), "条")
print("done:", state["done"])
print("file exists:", os.path.isfile(dest), os.path.getsize(dest) if os.path.isfile(dest) else -1, "bytes")
print("sha1 ok:", meta.sha1_ok(dest, items[0]["sha1"]))
print("error:", state["error"])
shutil.rmtree(tmp, ignore_errors=True)
print("DOWNLOADJOB_E2E", "PASS" if ok and os.path.isfile(dest) is False else ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
