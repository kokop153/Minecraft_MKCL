# -*- coding: utf-8 -*-
"""主菜单守望者：等游戏 latest.log 出现 Sound engine started -> TOPMOST 截图 -> 还原层级。"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time
import io

ROOT = r"C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher"
GAME_LOG = r"F:\.minecraft\versions\xiaohuiche的2b2t.xin整合包\logs\latest.log"
OUT = os.path.join(ROOT, "dev_reports", "screens", "menu_pack1211_final.png")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()


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


# 1. 等主菜单信号（最长 6 分钟）
print("等待主菜单信号...", flush=True)
t0 = time.time()
marker_at = None
log_pos = 0
while time.time() - t0 < 360:
    try:
        size = os.path.getsize(GAME_LOG)
        if size < log_pos:
            log_pos = 0
        with open(GAME_LOG, "rb") as f:
            f.seek(log_pos)
            chunk = f.read().decode("utf-8", errors="replace")
        log_pos = size
        if "Sound engine started" in chunk:
            marker_at = time.time()
            print("主菜单信号出现（%.0fs）" % (marker_at - t0), flush=True)
            break
    except OSError:
        pass
    time.sleep(1.0)

assert marker_at, "6 分钟内未等到主菜单信号"

# 2. 等菜单渲染稳定（8 秒）
time.sleep(8.0)

# 3. 找窗口 -> TOPMOST -> 截图 -> 还原
wins = find_game_window()
print("游戏窗口:", wins, flush=True)
assert wins, "未找到游戏窗口"
hwnd, title = wins[0]
if user32.IsIconic(hwnd):
    user32.ShowWindow(hwnd, 9)
    time.sleep(1.5)
user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x2 | 0x1 | 0x40)  # TOPMOST
time.sleep(0.8)
rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
vsx, vsy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
from PIL import ImageGrab
img = ImageGrab.grab(all_screens=True)
box = (max(0, rect.left - vsx), max(0, rect.top - vsy),
       min(img.width, rect.right - vsx), min(img.height, rect.bottom - vsy))
assert box[2] > box[0] and box[3] > box[1], "裁剪框为空"
img.crop(box).save(OUT)
print("截图:", OUT, os.path.getsize(OUT), "bytes", "rect:", (rect.left, rect.top, rect.right, rect.bottom), flush=True)
user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x2 | 0x1 | 0x40)  # 还原层级
print("DONE")
