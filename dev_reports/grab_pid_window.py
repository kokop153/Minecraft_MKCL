# -*- coding: utf-8 -*-
"""枚举窗口找 16136 的游戏窗口并截图。"""
import ctypes, ctypes.wintypes as wt, os, sys, time, io
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
hits, allwin = [], []
EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hwnd, _):
    if user32.IsWindowVisible(hwnd):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        n = user32.GetWindowTextLengthW(hwnd)
        t = ""
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            t = buf.value
        allwin.append((hwnd, pid.value, t))
        if pid.value == 16136 and t:
            hits.append((hwnd, t))
    return True
user32.EnumWindows(EnumProc(cb), 0)
print("16136 的可见窗口:", hits)
print("全部可见窗口(前12):", [(h, p, t[:30]) for h, p, t in allwin[:12]])
if not hits:
    print("NO_WINDOW_FOR_16136")
    sys.exit(1)
hwnd, title = hits[0]
if user32.IsIconic(hwnd):
    user32.ShowWindow(hwnd, 9); time.sleep(1.0)
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x2, 0x1, 0x40
user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
time.sleep(0.6)
user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
time.sleep(1.2)
rect = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(rect))
vsx, vsy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
from PIL import ImageGrab
img = ImageGrab.grab(all_screens=True)
box = (max(0, rect.left - vsx), max(0, rect.top - vsy),
       min(img.width, rect.right - vsx), min(img.height, rect.bottom - vsy))
out = os.path.join(ROOT, "dev_reports", "screens", "menu_pid16136_live.png")
img.crop(box).save(out)
print("截图:", out, os.path.getsize(out), "bytes, 标题:", title)
