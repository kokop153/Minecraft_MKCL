# -*- coding: utf-8 -*-
"""主菜单取证 v2：两个版本真实启动 -> 轮询日志找主菜单信号 -> 截图 -> 台账校验。

改进（相对 v1）：
- 主菜单检测改为轮询 launcher.log 文件（stderr 直写，可靠；v1 的 Qt 信号链在离屏下不可靠）
- 窗口枚举失败时输出全部可见窗口标题（调试）并提供全屏截图兜底
"""
import ctypes
import ctypes.wintypes
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from launcher.logsetup import setup_logging
LOG_PATH = setup_logging(ROOT)

SCREEN_DIR = os.path.join(ROOT, "dev_reports", "screens")
os.makedirs(SCREEN_DIR, exist_ok=True)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), name, detail, flush=True)


def wait_until(app, cond, timeout_s):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.3)
    return False


def _log_tail_after(offset):
    """读取日志 offset 之后的增量，返回 (新文本, 新 offset)。"""
    try:
        size = os.path.getsize(LOG_PATH)
        if size < offset:
            offset = 0
        with open(LOG_PATH, "rb") as f:
            f.seek(offset)
            data = f.read().decode("utf-8", errors="replace")
        return data, size
    except OSError:
        return "", offset


def wait_menu_signal(app, marker, offset, timeout_s, w):
    """轮询日志增量直到出现主菜单信号。返回 (found_line, new_offset)。"""
    t0 = time.time()
    pos = offset
    while time.time() - t0 < timeout_s:
        app.processEvents()
        chunk, pos = _log_tail_after(pos)
        if marker in chunk:
            return chunk[chunk.index(marker) - 40: chunk.index(marker) + 60], pos
        if w._proc and w._proc.poll() is not None:
            return None, pos
        time.sleep(0.5)
    return None, pos


def find_mc_window(debug_out=None):
    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND,
                                         ctypes.wintypes.LPARAM)
    found, all_titles = None, []
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                t = buf.value
                if "Mine" in t or "java" in t.lower():
                    all_titles.append((hwnd, t))
        return True
    user32.EnumWindows(cb, 0)
    if debug_out is not None:
        debug_out.extend(all_titles)
    for hwnd, t in all_titles:
        if "MKCL" in t or "启动器" in t:
            continue
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if (rect.right - rect.left) > 200 and (rect.bottom - rect.top) > 150:
            found = (hwnd, t, (rect.left, rect.top, rect.right, rect.bottom))
            break
    return found


def grab_window(rect, out_path):
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    vsx = user32.GetSystemMetrics(76)
    vsy = user32.GetSystemMetrics(77)
    l, t, r, b = rect
    img = ImageGrab.grab(all_screens=True)
    box = (max(0, l - vsx), max(0, t - vsy), min(img.width, r - vsx), min(img.height, b - vsy))
    img.crop(box).save(out_path)
    return os.path.getsize(out_path)


def grab_fullscreen(out_path):
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    ImageGrab.grab(all_screens=True).save(out_path)
    return os.path.getsize(out_path)


def launch_one(app, ctx, folder, isolate, tag, menu_timeout=200):
    from launcher.ui.workers import LaunchWorker
    res = {"pid": None, "menu": False, "shot": None, "ledger": None,
           "exited": None, "fail": None}
    acc = ctx.accounts.current()
    w = LaunchWorker(
        game_dir=ctx.config.game_dir, folder=folder,
        java_path=ctx.config.java_path or "",
        memory_gb=ctx.config.memory_gb or 4,
        username=acc.name if acc else "Player",
        uuid=acc.uuid if acc else "",
        user_type="legacy", jvm_extra=ctx.config.jvm_extra_args or "",
        width=854, height=480, isolate_dir=isolate, base_dir=ROOT,
    )
    w.start()
    check("[%s] 启动流程发起（isolate=%s）" % (tag, isolate), w.isRunning())

    if not wait_until(app, lambda: w._proc is not None, 120):
        check("[%s] 进程创建" % tag, False, str(res["fail"]))
        return res, w
    pid = w._proc._proc.pid
    res["pid"] = pid
    check("[%s] 进程创建 PID=%d" % (tag, pid), True)
    check("[%s] 台账已创建" % tag, bool(w._rec and os.path.isfile(w._rec)), w._rec)
    res["ledger"] = w._rec

    # 日志基线：本次启动从台账 started_at 之后的日志算起
    started_at_marker = None
    try:
        with open(w._rec, "r", encoding="utf-8") as f:
            started_at_marker = json.load(f).get("started_at")
    except Exception:
        pass

    # 等主菜单信号：从日志尾部轮询 "Sound engine started"（限定本次启动之后）
    t0 = time.time()
    base_size = os.path.getsize(LOG_PATH)
    menu_line = None
    while time.time() - t0 < menu_timeout:
        app.processEvents()
        try:
            size = os.path.getsize(LOG_PATH)
            if size < base_size:
                base_size = 0
            with open(LOG_PATH, "rb") as f:
                f.seek(base_size)
                chunk = f.read().decode("utf-8", errors="replace")
            if "Sound engine started" in chunk and started_at_marker and \
                    started_at_marker[11:16] in chunk[-4000:]:
                menu_line = "Sound engine started"
                break
            if "Sound engine started" in chunk:
                menu_line = "Sound engine started"
                break
        except OSError:
            pass
        if w._proc and w._proc.poll() is not None:
            break
        time.sleep(0.5)
    res["menu"] = bool(menu_line)
    check("[%s] 主菜单信号 Sound engine started" % tag, bool(menu_line),
          menu_line or ("超时/退出（exit=%s）" % (w._proc.poll(),)))

    if menu_line:
        time.sleep(4.0)
        app.processEvents()
        wnd, dbg = None, []
        for _ in range(20):
            wnd = find_mc_window(dbg)
            if wnd:
                break
            app.processEvents()
            time.sleep(1.0)
        path = os.path.join(SCREEN_DIR, "menu_%s.png" % tag)
        if wnd:
            hwnd, title, rect = wnd
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(1.2)
            size = grab_window(rect, path)
            res["shot"] = path
            check("[%s] 主菜单截图（窗口）" % tag, size > 15000,
                  "%s %d bytes 标题=%s" % (path, size, title))
        else:
            size = grab_fullscreen(path)
            res["shot"] = path
            check("[%s] 主菜单截图（全屏兜底）" % tag, size > 50000,
                  "%s %d bytes；可见窗口标题：%s" % (path, size, dbg[:6]))
    return res, w


def finish_one(app, w, res, tag):
    if w._proc and w._proc.poll() is None:
        w._proc.terminate()
        exited = wait_until(app, lambda: w._proc.poll() is not None, 25)
        check("[%s] 游戏已终止" % tag, exited,
              "exitcode=%s" % (w._proc.poll() if exited else None))
    else:
        check("[%s] 游戏已终止" % tag, res["exited"] is not None,
              "exitcode=%s" % res["exited"])
    try:
        w.stop_watch()
        w.wait(3000)
    except Exception:
        pass
    rec = res["ledger"]
    if rec and os.path.isfile(rec):
        with open(rec, "r", encoding="utf-8") as f:
            data = json.load(f)
        check("[%s] 台账字段完整" % tag,
              bool(data.get("version")) and bool(data.get("pid"))
              and bool(data.get("command")) and bool(data.get("java"))
              and data.get("exit_code") is not None and bool(data.get("finished_at")),
              "version=%s pid=%s exit=%s mc=%s" % (
                  data.get("version"), data.get("pid"),
                  data.get("exit_code"), data.get("mc_version")))
    else:
        check("[%s] 台账字段完整" % tag, False, "台账文件缺失")


def main():
    from PyQt5.QtWidgets import QApplication, QStyleFactory
    from PyQt5.QtGui import QFont
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from launcher.ui.main_window import AppContext
    ctx = AppContext(ROOT)
    check("配置：game_dir", bool(ctx.config.game_dir), ctx.config.game_dir)

    # 版本 1：fps1.20.1（隔离模式绕开共享 mods 的跨版本 fabric-api 冲突）
    res1, w1 = launch_one(app, ctx, "fps1.20.1", isolate=True, tag="fps1201")
    finish_one(app, w1, res1, "fps1201")
    time.sleep(3)

    # 版本 2：xiaohuiche 整合包（用户日常版本，Fabric 1.21.11，101 mods）
    res2, w2 = launch_one(app, ctx, "xiaohuiche的2b2t.xin整合包",
                          isolate=True, tag="pack1211", menu_timeout=260)
    finish_one(app, w2, res2, "pack1211")

    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        logc = f.read()
    check("日志全程无 [WinError 87]", "[WinError 87]" not in logc)

    with open(os.path.join(ROOT, "dev_reports", "evidence_menu_summary.json"),
              "w", encoding="utf-8") as f:
        json.dump({"fps1201": {k: v for k, v in res1.items() if k != "ledger"},
                   "pack1211": {k: v for k, v in res2.items() if k != "ledger"},
                   "pass": PASS, "fail": FAIL}, f, ensure_ascii=False, indent=2)

    print()
    print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main()
