# -*- coding: utf-8 -*-
"""v2：把游戏窗口置顶（SetWindowPos TOPMOST→NOTOPMOST）后截屏，处理最小化。"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time
import io

ROOT = r"C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

targets = []
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hwnd, _):
    if user32.IsWindowVisible(hwnd):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            t = buf.value
            if "Minecraft" in t and "MKCL" not in t and "启动器" not in t:
                targets.append((hwnd, t))
    return True
user32.EnumWindows(EnumProc(cb), 0)
print("候选:", [(h, t) for h, t in targets])
assert targets, "未找到游戏窗口"
hwnd, title = targets[0]

# 若最小化则还原
if user32.IsIconic(hwnd):
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    time.sleep(1.0)

# 置顶再取消置顶（保持层级在顶但不永远置顶）
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x2, 0x1, 0x40
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
time.sleep(0.6)
user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
time.sleep(1.2)

# 校验是否真的在最前
fg = user32.GetForegroundWindow()
n = user32.GetWindowTextLengthW(fg)
buf = ctypes.create_unicode_buffer(n + 1)
user32.GetWindowTextW(fg, buf, n + 1)
print("当前前台窗口:", buf.value)

rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
vsx, vsy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
from PIL import ImageGrab
img = ImageGrab.grab(all_screens=True)
box = (max(0, rect.left - vsx), max(0, rect.top - vsy),
       min(img.width, rect.right - vsx), min(img.height, rect.bottom - vsy))
out = os.path.join(ROOT, "dev_reports", "screens", "menu_pack1211_live.png")
img.crop(box).save(out)
print("截图:", out, os.path.getsize(out), "bytes", "rect:", (rect.left, rect.top, rect.right, rect.bottom))
