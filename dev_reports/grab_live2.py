# -*- coding: utf-8 -*-
import ctypes, ctypes.wintypes as wt, os, sys, time, io
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()

# 最新枚举（每次运行都重新拿句柄）
targets = []
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hwnd, _):
    if user32.IsWindowVisible(hwnd):
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            t = buf.value
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if "Minecraft" in t and "MKCL" not in t and "启动器" not in t:
                targets.append((hwnd, t, pid.value))
    return True
user32.EnumWindows(EnumProc(cb), 0)
print("游戏窗口:", targets)
assert targets, "没有游戏窗口"
hwnd, title, pid = targets[0]
print("IsWindow:", user32.IsWindow(hwnd), "IsIconic:", user32.IsIconic(hwnd))

if user32.IsIconic(hwnd):
    user32.ShowWindow(hwnd, 9); time.sleep(1.5)
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x2, 0x1, 0x40
user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
time.sleep(0.5)
user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
time.sleep(1.0)
rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
print("rect:", rect.left, rect.top, rect.right, rect.bottom)
assert (rect.right - rect.left) > 100, "rect 无效"

vsx, vsy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
from PIL import ImageGrab
img = ImageGrab.grab(all_screens=True)
box = (max(0, rect.left - vsx), max(0, rect.top - vsy),
       min(img.width, rect.right - vsx), min(img.height, rect.bottom - vsy))
print("box:", box)
assert box[2] > box[0] and box[3] > box[1], "裁剪框为空"
out = os.path.join(ROOT, "dev_reports", "screens", "menu_pid%d_live.png" % pid)
img.crop(box).save(out)
print("截图成功:", out, os.path.getsize(out), "bytes, 窗口标题:", title, "PID:", pid)
