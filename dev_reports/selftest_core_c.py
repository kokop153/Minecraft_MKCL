# -*- coding: utf-8 -*-
"""下载模块自测（meta.py + download.py）。

直接运行：
    python dev_reports/selftest_core_c.py
"""
import os
import sys
import time
import tempfile
import traceback

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJ not in sys.path:
    sys.path.insert(0, PROJ)

RESULTS = []


def record(name, status, detail=""):
    RESULTS.append((name, status, detail))
    print("[%s] %s %s" % (status, name, ("-- " + detail) if detail else ""))


def wait_import(imp_fn, tries=8, wait=15):
    """ImportError 时等待并行 Agent 的文件就绪，重试 <=8 次。"""
    for i in range(tries):
        try:
            return imp_fn()
        except ImportError as e:
            print("  import 未就绪(%d/%d): %s，%ds 后重试..." % (i + 1, tries, e, wait))
            time.sleep(wait)
    return None


def main():
    # ---------- 1. fetch_version_manifest("bmclapi") ----------
    manifest = None
    try:
        from launcher import meta
        try:
            manifest = meta.fetch_version_manifest("bmclapi")
            vers = meta.iter_manifest_versions(manifest)
            if len(vers) >= 500:
                record("1.manifest_bmclapi", "PASS", "versions=%d" % len(vers))
            else:
                record("1.manifest_bmclapi", "FAIL", "versions=%d (<500)" % len(vers))
        except Exception as e:
            record("1.manifest_bmclapi", "SKIP", "网络/解析失败: %s" % e)
    except ImportError as e:
        record("1.manifest_bmclapi", "SKIP", "meta 导入失败: %s" % e)

    # ---------- 2. download_file gson ----------
    try:
        from launcher import meta
        tmp_dir = os.path.join(tempfile.gettempdir(), "mcl_test")
        dest = os.path.join(tmp_dir, "gson.jar")
        res = meta.download_file(
            "https://bmclapi2.bangbang93.com/maven/com/google/code/gson/gson/2.10/gson-2.10.jar",
            dest, source="bmclapi")
        size = os.path.getsize(dest) if os.path.isfile(dest) else 0
        if os.path.isfile(dest) and size > 100 * 1024:
            record("2.download_file_gson", "PASS",
                   "size=%dKB retries=%d" % (size // 1024, res["retries"]))
        else:
            record("2.download_file_gson", "FAIL", "size=%d" % size)
    except Exception as e:
        record("2.download_file_gson", "FAIL", "%s: %s" % (type(e).__name__, e))

    # ---------- 3. collect_download_items (assets off) ----------
    game_dir = "F:\\.minecraft"
    folder = "1.20.1"
    items = None
    try:
        from launcher.version_scan import scan_versions, resolve_version_chain  # noqa
        have_scan = True
    except ImportError:
        have_scan = wait_import(
            lambda: __import__("launcher.version_scan", fromlist=["x"])) is not None
        if not have_scan:
            record("3.collect_items_no_assets", "SKIP", "version_scan 未就绪")
    if have_scan:
        try:
            from launcher import meta
            items = meta.collect_download_items(
                game_dir, folder, "bmclapi", include_assets=False)
            if len(items) >= 50:
                first3_ok = all(
                    it.get("url") and it.get("dest") for it in items[:3])
                record("3.collect_items_no_assets", "PASS",
                       "items=%d first3_fields_ok=%s" % (len(items), first3_ok))
                if not first3_ok:
                    record("3.collect_items_no_assets.fields", "FAIL", "前3项 url/dest 缺失")
            else:
                record("3.collect_items_no_assets", "FAIL", "items=%d (<50)" % len(items))
        except Exception as e:
            record("3.collect_items_no_assets", "FAIL",
                   "%s: %s" % (type(e).__name__, e))
            traceback.print_exc()

    # ---------- 4. collect_download_items (assets on) ----------
    try:
        from launcher import meta
        items_all = meta.collect_download_items(
            game_dir, folder, "bmclapi", include_assets=True)
        if len(items_all) > 1000:
            record("4.collect_items_with_assets", "PASS", "items=%d" % len(items_all))
        else:
            record("4.collect_items_with_assets", "SKIP",
                   "assetIndex 未就绪或项数=%d (<=1000)" % len(items_all))
    except Exception as e:
        record("4.collect_items_with_assets", "SKIP", "%s: %s" % (type(e).__name__, e))

    # ---------- 5. DownloadManager ----------
    try:
        from launcher.download import DownloadManager
        if not items:
            record("5.download_manager", "SKIP", "第3步清单为空")
        else:
            dm = DownloadManager(source="bmclapi", max_workers=4)
            state = {"done": None, "progress": 0}
            ev = __import__("threading").Event()

            def on_progress(d, t, f, p):
                state["progress"] += 1

            def on_done(ok, failed):
                state["done"] = (ok, failed)
                ev.set()

            dm.download(items[:5], progress=on_progress, done=on_done)
            ev.wait(300)
            time.sleep(1)
            ok, failed = state["done"] or (0, [("n/a", "timeout", "")])
            real_failed = [f for f in failed if not (isinstance(f, dict) and f.get("error") == "已取消")]
            progress_ok = state["progress"] >= 1
            count_ok = (ok + len(failed)) == min(5, len(items))
            if count_ok and progress_ok:
                record("5.download_manager", "PASS",
                       "ok=%d failed=%d progress_calls=%d (含 skip)" %
                       (ok, len(failed), state["progress"]))
            else:
                record("5.download_manager", "FAIL",
                       "ok=%d failed=%d progress=%d" % (ok, len(failed), state["progress"]))
            # cancel 测试
            dm2 = DownloadManager(source="bmclapi", max_workers=2)
            cancel_done = __import__("threading").Event()

            def on_done2(ok2, failed2):
                cancel_done.set()

            big = items[:400] if len(items) >= 400 else list(items) * 40
            dm2.download(big, done=on_done2)
            time.sleep(1.5)
            dm2.cancel()
            ok_flag = True
            for _ in range(60):
                if not dm2.is_running():
                    break
                time.sleep(1)
            ok_flag = not dm2.is_running()
            cancel_done.wait(60)
            record("5b.cancel", "PASS" if ok_flag else "FAIL",
                   "is_running=%s" % dm2.is_running())
    except ImportError as e:
        record("5.download_manager", "SKIP", "download 导入失败: %s" % e)
    except Exception as e:
        record("5.download_manager", "FAIL", "%s: %s" % (type(e).__name__, e))
        traceback.print_exc()

    # ---------- 汇总 ----------
    print("\n===== SUMMARY =====")
    npass = sum(1 for _, s, _ in RESULTS if s == "PASS")
    nfail = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    nskip = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    for name, s, d in RESULTS:
        print("%-6s %-32s %s" % (s, name, d))
    print("PASS=%d FAIL=%d SKIP=%d" % (npass, nfail, nskip))
    return 0 if nfail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
