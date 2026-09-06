# -*- coding: utf-8 -*-
"""日志初始化：滚动文件 + 控制台，幂等。"""
import logging
import os
from logging.handlers import RotatingFileHandler

_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def get_log_path(base_dir: str) -> str:
    """返回日志文件路径（不创建目录）。"""
    return os.path.join(base_dir, "logs", "launcher.log")


def setup_logging(base_dir: str) -> str:
    """初始化根 logger：RotatingFileHandler(1MB x 5, utf-8) + StreamHandler。

    幂等：已有指向同一日志文件的 handler 时直接返回路径，不重复添加。
    """
    log_path = get_log_path(base_dir)
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, RotatingFileHandler):
            try:
                if os.path.abspath(getattr(h, "baseFilename", "")) == os.path.abspath(log_path):
                    return log_path
            except Exception:
                pass
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    fh = RotatingFileHandler(log_path, maxBytes=1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FMT))
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(fh)
    root.addHandler(sh)
    if root.level == logging.NOTSET or root.level > logging.INFO:
        root.setLevel(logging.INFO)
    return log_path
