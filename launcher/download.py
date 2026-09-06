# -*- coding: utf-8 -*-
"""并发下载管理器（不依赖 Qt）：线程池调度、进度/完成/失败回调、取消。"""
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from launcher import meta
from launcher.errors import LauncherError


class DownloadManager:
    """后台并发下载器。

    download(items, progress, done, error) 立即返回，后台线程调度；
    progress(done, total, current_file, file_pct)、done(ok_count, failed_list)。
    """

    def __init__(self, source: str = "bmclapi", max_workers: int = 6):
        self.source = source
        self.max_workers = max(1, int(max_workers))
        self._cancel = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        self._thread = None

    # ---------- 对外接口 ----------

    def download(self, items, progress=None, done=None, error=None):
        if self.is_running():
            if error:
                try:
                    error(LauncherError("已有下载任务在进行中"))
                except Exception:
                    pass
            return
        items = list(items or [])
        self._cancel.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._run, args=(items, progress, done, error), daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel.set()

    def is_running(self) -> bool:
        if not self._running:
            return False
        t = self._thread
        if t is not None and not t.is_alive():
            with self._lock:
                self._running = False
            return False
        return True

    # ---------- 内部调度 ----------

    def _run(self, items, progress, done, error):
        total = len(items)
        ok_count = 0
        failed = []
        done_items = 0
        if total == 0:
            self._running = False
            if done:
                try:
                    done(0, [])
                except Exception:
                    pass
            return

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futures = [pool.submit(self._download_one, it) for it in items]
            for fut, it in zip(futures, items):
                try:
                    res = fut.result()
                    if res:
                        ok_count += 1
                    else:
                        failed.append({
                            "url": it.get("url", ""),
                            "dest": it.get("dest", ""),
                            "error": "已取消",
                        })
                except LauncherError as e:
                    if self._cancel.is_set():
                        failed.append({
                            "url": it.get("url", ""),
                            "dest": it.get("dest", ""),
                            "error": "已取消",
                        })
                    else:
                        failed.append({
                            "url": it.get("url", ""),
                            "dest": it.get("dest", ""),
                            "error": str(e),
                        })
                except Exception as e:  # 兜底
                    failed.append({
                        "url": it.get("url", ""),
                        "dest": it.get("dest", ""),
                        "error": "%s: %s" % (type(e).__name__, e),
                    })
                done_items += 1
                if progress:
                    try:
                        fname = os.path.basename(it.get("dest") or "")
                        # 近似文件百分比：该项相对整体进度的贡献，映射到 0~100
                        file_pct = min(100.0, done_items * 100.0 / total)
                        progress(done_items, total, fname, file_pct)
                    except Exception:
                        pass

        with self._lock:
            self._running = False
        if done:
            try:
                done(ok_count, failed)
            except Exception:
                pass

    def _download_one(self, item):
        """下载单项；被取消或失败抛 LauncherError/返回 None(跳过成功)。"""
        dest = item.get("dest") or ""
        url = item.get("url") or ""
        sha1 = item.get("sha1") or ""
        # 跳过策略：本地已存在且 sha1 匹配
        if item.get("skip_if_exists") and os.path.isfile(dest) and meta.sha1_ok(dest, sha1):
            return dest
        if os.path.isfile(dest) and sha1 and meta.sha1_ok(dest, sha1):
            return dest
        # 分块粒度的取消检查由 meta.download_file 内部不支持，
        # 这里按项检查取消，取消中的项直接早退。
        if self._cancel.is_set():
            return None
        res = meta.download_file(url, dest, source=self.source, timeout=30, retries=3)
        return res["dest"]
