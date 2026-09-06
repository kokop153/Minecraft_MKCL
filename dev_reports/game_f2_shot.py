# -*- coding: utf-8 -*-
"""游戏内截图：向游戏窗口投递 F2（MC 内置截图键），取游戏自己渲染的帧。"""
import ctypes
import ctypes.wintypes as wt
import glob
import os
import sys
import time
import io

ROOT = r"C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher"
GAME_SHOTS = r"F:\.minecraft\versions\xiaohuiche的2b2t.xin整合包\screenshots"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x0100, 0x0101, 0x0102
VK_F2 = 0x71


def find_game_window():
    hits = []
    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                t = buf.value
                if "Minecraft" in t and "MKCL" not in t and "启动器" not in t:
                    hits.append((hwnd, t))
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    return hits


# 已有截图基线
before = set(glob.glob(os.path.join(GAME_SHOTS, "*.png")))
print("基线截图数:", len(before), flush=True)

wins = find_game_window()
print("游戏窗口:", wins, flush=True)
assert wins, "未找到游戏窗口"
hwnd, title = wins[0]

# 投递 F2 按下/抬起（窗口消息级，无需前台焦点）
lparam_down = 0x00000001  # repeat=1, scancode 低 8 位（F2 scancode=0x3B 仍可省略，MC 读 VK）
user32.PostMessageW(hwnd, WM_KEYDOWN, VK_F2, lparam_down)
time.sleep(0.12)
user32.PostMessageW(hwnd, WM_KEYUP, VK_F2, 0xC0000001)
print("F2 已投递", flush=True)

# 等待游戏保存截图（F2 后 1~4 秒）
new_file = None
for _ in range(20):
    time.sleep(0.5)
    now = set(glob.glob(os.path.join(GAME_SHOTS, "*.png")))
    new = now - before
    if new:
        new_file = max(new, key=os.path.getmtime)
        break
print("新截图:", new_file, flush=True)

if not new_file:
    # 兜底：再试一次带 scancode 的完整序列
    sc = 0x003C0001  # F2 scancode 0x3C? F2=0x3B -> 0x003B0001
    user32.PostMessageW(hwnd, WM_KEYDOWN, VK_F2, 0x003B0001)
    time.sleep(0.12)
    user32.PostMessageW(hwnd, WM_CHAR, 0x00, 0x003B0001)
    user32.PostMessageW(hwnd, WM_KEYUP, VK_F2, 0xC03B0001)
    for _ in range(16):
        time.sleep(0.5)
        now = set(glob.glob(os.path.join(GAME_SHOTS, "*.png")))
        new = now - before
        if new:
            new_file = max(new, key=os.path.getmtime)
            break
    print("重试新截图:", new_file, flush=True)

assert new_file, "游戏未生成截图（F2 未生效）"

# 取到游戏真实渲染帧，复制为交付证据
import shutil
out = os.path.join(ROOT, "dev_reports", "screens", "menu_real_game.png")
shutil.copyfile(new_file, out)
print("游戏内截图已复制:", out, os.path.getsize(out), "bytes", flush=True)
print("来源文件:", new_file)
