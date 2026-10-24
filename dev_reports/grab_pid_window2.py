# -*- coding: utf-8 -*-
import ctypes, ctypes.wintypes as wt, os, sys, time, io
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
hwnd = 724138  # Minecraft* 1.21.11
print("IsIconic:", user32.IsIconic(hwnd))
if user32.IsIconic(hwnd):
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    time.sleep(1.5)
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x2, 0x1, 0x40
user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
time.sleep(0.5)
user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
time.sleep(1.0)
rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
print("rect:", rect.left, rect.top, rect.right, rect.bottom)
vsx, vsy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
from PIL import ImageGrab
img = ImageGrab.grab(all_screens=True)
print("virtual screen:", vsx, vsy, img.width, img.height)
box = (max(0, rect.left - vsx), max(0, rect.top - vsy),
       min(img.width, rect.right - vsx), min(img.height, rect.bottom - vsy))
print("box:", box)
assert box[2] > box[0] and box[3] > box[1], "裁剪框仍为空"
out = os.path.join(ROOT, "dev_reports", "screens", "menu_pid16136_live.png")
img.crop(box).save(out)
print("截图:", out, os.path.getsize(out), "bytes")
