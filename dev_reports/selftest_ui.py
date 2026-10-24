# -*- coding: utf-8 -*-
"""UI 冒烟测试：离屏运行完整界面，逐页截图 + 交互模拟 + 持久化校验。"""
import os
import sys
import time
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SCREEN_DIR = os.path.join(ROOT, "dev_reports", "screens")
os.makedirs(SCREEN_DIR, exist_ok=True)

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL"), name, detail)


def wait_until(app, cond, timeout_s=40):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.1)
    return False


def main():
    from PyQt5.QtWidgets import QApplication, QStyleFactory
    from PyQt5.QtGui import QFont
    from PyQt5.QtCore import Qt

    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from launcher.ui.main_window import AppContext, MainWindow
    from launcher.ui import theme as theme_mod

    ctx = AppContext(ROOT)
    win = MainWindow(ctx)
    win.apply_theme()
    win.show()

    # ---- 1. 启动数据加载 ----
    ok = wait_until(app, lambda: bool(win.versions_page.versions), 40)
    check("版本扫描加载", ok, "count=%d" % len(win.versions_page.versions))
    wait_until(app, lambda: bool(win.downloads.client_tab.manifest_versions), 45)
    manifest_count = len(win.downloads.client_tab.manifest_versions)
    if manifest_count > 100:
        check("清单加载", True, "count=%d" % manifest_count)
    else:
        # 外网（bmclapi）不可达时降级：要求给出中文可读错误（代码路径正确）
        err_text = win.downloads.client_tab.list_info.text()
        check("清单加载（外网不可达，降级验证中文错误提示）",
              "清单获取失败" in err_text and "网络" in err_text,
              "count=%d err=%s" % (manifest_count, err_text[:80]))
    wait_until(app, lambda: len(win.settings.detected_javas) > 0, 40)
    check("Java 检测加载", len(win.settings.detected_javas) >= 4,
          "count=%d" % len(win.settings.detected_javas))

    # ---- 2. 账号迁移（旧 username -> accounts.json） ----
    check("账号迁移 kokop", ctx.accounts.current() is not None
          and ctx.accounts.current().name == "kokop",
          "uuid=%s" % (ctx.accounts.current().uuid if ctx.accounts.current() else "-"))
    acc_path = os.path.join(ROOT, "accounts.json")
    check("accounts.json 落盘", os.path.isfile(acc_path))
    with open(acc_path, "r", encoding="utf-8") as f:
        adata = json.load(f)
    check("accounts.json 内容", adata.get("current_name") == "kokop"
          and adata.get("accounts") and adata["accounts"][0]["uuid"].startswith("43465a85"))

    # ---- 3. 版本页交互：选版本 + 隔离切换 ----
    win.goto("versions")
    app.processEvents()
    target = "1.20.1-Fabric 0.16.14-OptiFine_I6"
    found_row = -1
    for i in range(win.versions_page.list.count()):
        if win.versions_page.list.item(i).data(Qt.UserRole) == target:
            found_row = i
            break
    check("目标版本出现在列表", found_row >= 0, "row=%d" % found_row)
    win.versions_page.list.setCurrentRow(found_row)
    app.processEvents()
    win.versions_page._use_version()
    check("设为当前版本", ctx.config.current_version == target,
          ctx.config.current_version)
    with open(os.path.join(ROOT, "config.json"), "r", encoding="utf-8") as f:
        cdata = json.load(f)
    check("current_version 已持久化", cdata.get("current_version") == target)

    win.versions_page.isolate_cb.setChecked(True)
    app.processEvents()
    with open(os.path.join(ROOT, "config.json"), "r", encoding="utf-8") as f:
        cdata = json.load(f)
    check("隔离目录持久化",
          cdata.get("per_version", {}).get(target, {}).get("isolate") is True)
    win.versions_page.isolate_cb.setChecked(False)
    app.processEvents()

    # ---- 4. 主页状态 ----
    win.goto("home")
    app.processEvents()
    # launch_sub 显示中间省略文本，完整版本名在 tooltip
    home_text = (win.home.launch_sub.toolTip() or "") + "|" + win.home.side_name.text()
    check("主页版本/账号卡片", target in home_text and "kokop" in home_text,
          home_text.replace("\n", " / "))
    check("启动按钮可用", win.home.launch_btn.isEnabled())

    # ---- 5. 设置页交互：主题色切换 + 内存 ----
    win.settings._set_accent("#3B82F6")
    check("主题色切换生效", "#3B82F6" in app.styleSheet())
    with open(os.path.join(ROOT, "config.json"), "r", encoding="utf-8") as f:
        cdata = json.load(f)
    check("主题色持久化", cdata.get("theme_color") == "#3B82F6")
    win.settings._set_accent(theme_mod.DEFAULT_ACCENT)
    check("主题色还原", theme_mod.DEFAULT_ACCENT in app.styleSheet())

    old_mem = ctx.config.memory_gb
    win.settings.mem_slider.setValue(6)
    check("内存调整持久化", ctx.config.memory_gb == 6)
    win.settings.mem_slider.setValue(old_mem)

    # 账号增删
    ctx.accounts.add_offline("TestPlayer")
    ctx.accounts.set_current("TestPlayer")
    ctx.accounts.save()
    win.settings.refresh()
    items = [win.settings.acc_list.item(i).data(Qt.UserRole)
             for i in range(win.settings.acc_list.count())]
    check("账号列表含 TestPlayer", "TestPlayer" in items, str(items))
    ctx.accounts.set_current("kokop")
    ctx.accounts.remove("TestPlayer")
    ctx.accounts.save()
    win.settings.refresh()
    check("账号删除生效", "TestPlayer" not in
          [a.name for a in ctx.accounts.list()])

    # ---- 6. 截图（四页）：尺寸 + 非单一颜色（内容感知） ----
    from PyQt5.QtGui import QImage

    def _img_rich(path):
        img = QImage(path)
        if img.isNull():
            return 0
        colors = set()
        w, h = img.width(), img.height()
        for yy in range(0, h, max(1, h // 40)):
            for xx in range(0, w, max(1, w // 40)):
                colors.add(img.pixel(xx, yy))
        return len(colors)

    shots = [("home", win.home), ("versions", win.versions_page),
             ("downloads", win.downloads), ("settings", win.settings)]
    for key, page in shots:
        win.goto(key)
        win.resize(1080, 720)
        for _ in range(8):
            app.processEvents()
            time.sleep(0.05)
        pix = win.grab()
        path = os.path.join(SCREEN_DIR, "page_%s.png" % key)
        pix.save(path)
        size_ok = os.path.isfile(path) and os.path.getsize(path) > 3000
        check("截图 " + key, size_ok and _img_rich(path) >= 8,
              "%d bytes, %d distinct colors" % (
                  os.path.getsize(path) if os.path.isfile(path) else -1,
                  _img_rich(path)))

    # ---- 7. 重启还原：全新 AppContext 模拟重启 ----
    from launcher.ui.main_window import AppContext as AC2
    ctx2 = AC2(ROOT)
    check("重启还原 current_version", ctx2.config.current_version == target,
          ctx2.config.current_version)
    check("重启还原账号", ctx2.accounts.current() is not None
          and ctx2.accounts.current().name == "kokop")
    check("重启还原下载源", ctx2.config.download_source in ("bmclapi", "official"))
    check("重启还原内存", isinstance(ctx2.config.memory_gb, int))

    win.close()
    app.quit()

    print()
    print("ALL PASS: %d  FAIL: %d" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)


if __name__ == "__main__":
    main()
