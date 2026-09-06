# -*- coding: utf-8 -*-
"""双实例真实启动验证（无 GUI 依赖）：MultiLaunchWorker 端到端。"""
import os, sys, time, json, glob
ROOT = r"C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher"
sys.path.insert(0, ROOT)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from launcher.logsetup import setup_logging
LOG_PATH = setup_logging(ROOT)
from PyQt5.QtCore import QCoreApplication
app = QCoreApplication(sys.argv)

from launcher.ui.main_window import AppContext
from launcher.ui.workers import MultiLaunchWorker

ctx = AppContext(ROOT)
prev_ver = ctx.config.current_version
ctx.config.current_version = "fps1.20.1"
ctx.config.memory_gb = 2
ctx.config.save()

PASS, FAIL = [], []
def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(("PASS" if c else "FAIL"), n, d, flush=True)

started = {}
exited = {}
fail_msg = []
mw = MultiLaunchWorker(base_dir=ROOT, game_dir=ctx.config.game_dir,
                       folder="fps1.20.1", java_path="", count=2,
                       memory_gb=2, username="kokop")
mw.instance_started.connect(lambda k, p: started.__setitem__(k, p))
mw.instance_exited.connect(lambda k, c: exited.__setitem__(k, c))
mw.fail.connect(lambda m: fail_msg.append(m))

mw.start()
check("多实例流程发起", mw.isRunning())

t0 = time.time()
while time.time() - t0 < 150 and len(started) < 2 and not fail_msg:
    app.processEvents(); time.sleep(0.2)
check("两个实例均已拉起", len(started) >= 2, "pids=%s fail=%s" % (sorted(started.values()), fail_msg))

t0 = time.time(); min_alive = 99
while time.time() - t0 < 35:
    app.processEvents()
    alive = mw.alive_count()
    min_alive = min(min_alive, alive)
    if alive == 0: break
    time.sleep(0.5)
check("双实例并行存活 ≥30s（最少同时存活=%d）" % min_alive, min_alive >= 2)

mw.stop_all()
t0 = time.time()
while time.time() - t0 < 30 and mw.alive_count() > 0:
    app.processEvents(); time.sleep(0.3)
check("全部实例已停止", mw.alive_count() == 0)

# 台账校验
leds = sorted(glob.glob(os.path.join(ROOT, "logs", "launches", "launch-*.json")),
              key=os.path.getmtime)[-2:]
recs = []
for p in leds:
    with open(p, "r", encoding="utf-8") as f:
        recs.append(json.load(f))
multi_recs = [r for r in recs if isinstance(r.get("instance"), int)]
check("台账含 instance 字段（2 条）", len(multi_recs) == 2,
      str([(r.get("instance"), r.get("pid"), r.get("status"), r.get("username")) for r in multi_recs]))
if len(multi_recs) == 2:
    check("两实例 workdir 独立", multi_recs[0]["workdir"] != multi_recs[1]["workdir"],
          "%s | %s" % (os.path.basename(multi_recs[0]["workdir"]),
                       os.path.basename(multi_recs[1]["workdir"])))
    check("两实例账号 kokop / kokop2",
          sorted(r.get("username") for r in multi_recs) == ["kokop", "kokop2"],
          str([r.get("username") for r in multi_recs]))
    check("台账命令无空参数", all("" not in r.get("command") for r in multi_recs))
    check("台账记录 PID", all(isinstance(r.get("pid"), int) for r in multi_recs))

for k in (1, 2):
    wd = os.path.join(r"F:\.minecraft\versions\fps1.20.1", "multi-%d" % k)
    check("实例 %d 独立目录落盘" % k, os.path.isdir(wd), wd)

with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
    logc = f.read()
check("日志全程无 [WinError 87]", "[WinError 87]" not in logc)

ctx.config.current_version = prev_ver
ctx.config.save()

print()
print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", FAIL); sys.exit(1)
