# -*- coding: utf-8 -*-
"""验证「32 位 Java 导致 JVM 创建失败」修复。

检查项：
1. find_javas 正确识别位数（本机 32 位 jre-1.8 / 64 位 jre-legacy 等）
2. pick_java_for(MC 1.16.5) 在同 major Java 8 里优先选 64 位
3. effective_heap_gb：32 位 + 4G → 钳制为 1G；64 位不钳制
4. validate_jvm_heap：32 位 + 4G 抛中文 LauncherError（含 32 位提示）；
   64 位 + 4G 通过；32 位 + 1G 通过（钳制后值）
5. 修复前复现命令（-Xmx4G on 32位）确实返回非 0
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher.java_utils import find_javas, pick_java_for
from launcher.launch import (
    effective_heap_gb, validate_jvm_heap, java_heap_cap_gb,
)
from launcher.errors import LauncherError

FAILS = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    print("[%s] %s%s" % (tag, name, (" | " + str(detail)) if detail else ""))
    if not cond:
        FAILS.append(name)


javas = find_javas()
print("检测到 %d 个 Java：" % len(javas))
for j in javas:
    print("  %-64s v=%-11s major=%-3d %s"
          % (j.path, j.version, j.major, "64位" if j.is_64 else "32位"))
check("至少检测到 1 个 Java", len(javas) >= 1)

by_bits = {}
for j in javas:
    by_bits.setdefault(j.is_64, []).append(j)
check("本机同时存在 32 位与 64 位 Java",
      True in by_bits and False in by_bits,
      "64位=%d 32位=%d" % (len(by_bits.get(True, [])),
                           len(by_bits.get(False, []))))

# ---- 2. 自动选择：MC 1.16.5（required=8）时同 major 优先 64 位 ----
if False in by_bits:
    jr = pick_java_for("1.16.5", javas)
    check("MC 1.16.5 自动选择优先 64 位", jr is not None and jr.is_64,
          "picked=%s (%s)" % (jr.path if jr else None,
                              "64" if jr and jr.is_64 else "32"))
    # 旧行为复现：直接按版本号排序会选 32 位 1.8.0_371（最新版号）
    old_pick = min([j for j in javas if j.major == 8],
                   key=lambda j: (j.major, tuple(
                       -int(n) for n in __import__("re").findall(r"\d+", j.version))))
    print("  对照：旧逻辑（版本号新优先）会选 %s（%s）"
          % (old_pick.path, "64" if old_pick.is_64 else "32"))

# ---- 3. 堆钳制 ----
java32 = by_bits.get(False, [None])[0]
java64 = by_bits.get(True, [None])[0]
if java32:
    check("effective_heap_gb(32位, 4G) = 1",
          effective_heap_gb(java32.path, 4) == 1)
    check("effective_heap_gb(32位, 1G) = 1（不放大不缩小）",
          effective_heap_gb(java32.path, 1) == 1)
    check("java_heap_cap_gb(32位) = 1", java_heap_cap_gb(java32.path) == 1)
if java64:
    check("effective_heap_gb(64位, 4G) = 4（不钳制）",
          effective_heap_gb(java64.path, 4) == 4)
    check("java_heap_cap_gb(64位) = 0（不限）",
          java_heap_cap_gb(java64.path) == 0)

# ---- 4. 启动前预检 ----
if java32:
    # 修复前复现：32 位 + -Xmx4G 确实失败（用户截图同款错误）
    import subprocess
    proc = subprocess.run([java32.path, "-Xmx4G", "-version"],
                          capture_output=True, text=True, timeout=30)
    check("复现确认：32位 + -Xmx4G 失败（修复前用户所见错误）",
          proc.returncode != 0,
          (proc.stderr or "").strip().splitlines()[:1])
    # 预检：抛中文 LauncherError
    try:
        validate_jvm_heap(java32.path, 4)
        check("validate_jvm_heap(32位, 4G) 应抛错", False, "未抛错")
    except LauncherError as e:
        check("validate_jvm_heap(32位, 4G) 抛中文 LauncherError",
              "32 位" in e.detail and "Java" in str(e),
              str(e))
    # 钳制后的值预检通过
    try:
        validate_jvm_heap(java32.path, effective_heap_gb(java32.path, 4))
        check("validate_jvm_heap(32位, 钳制后1G) 通过", True)
    except LauncherError as e:
        check("validate_jvm_heap(32位, 钳制后1G) 通过", False, str(e))
if java64:
    try:
        validate_jvm_heap(java64.path, 4)
        check("validate_jvm_heap(64位, 4G) 通过", True)
    except LauncherError as e:
        check("validate_jvm_heap(64位, 4G) 通过", False, str(e))

print()
if FAILS:
    print("RESULT: %d FAILED -> %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("RESULT: ALL PASS")
