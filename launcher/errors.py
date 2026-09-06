# -*- coding: utf-8 -*-
"""启动器基础异常。"""


class LauncherError(Exception):
    """启动器统一异常：str(e) 返回 message，detail 存补充信息。"""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:
        return self.message
