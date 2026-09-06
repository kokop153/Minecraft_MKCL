# -*- coding: utf-8 -*-
"""Maven GAV 坐标工具：解析 group:artifact:version[:classifier][@ext]。"""


def gav_to_path(name: str) -> str:
    """把 Maven 坐标转换为相对 libraries 根目录的路径。

    net.fabricmc:fabric-loader:0.18.4
        -> net/fabricmc/fabric-loader/0.18.4/fabric-loader-0.18.4.jar
    org.example:lib:1.0:natives-win
        -> org/example/lib/1.0/lib-1.0-natives-win.jar
    解析失败返回 ""。
    """
    base = str(name or "").split("@")[0]
    parts = base.split(":")
    if len(parts) == 3:
        g, a, v = parts
        cls = ""
    elif len(parts) == 4:
        g, a, v, cls = parts
        cls = "-" + cls
    else:
        return ""
    if not (g and a and v):
        return ""
    return "%s/%s/%s/%s-%s%s.jar" % (
        g.replace(".", "/"), a, v, a, v, cls,
    )


def gav_to_url(name: str, repo_url: str = "https://libraries.minecraft.net/") -> str:
    """Maven 坐标 + 仓库根 -> 完整下载 URL。"""
    rel = gav_to_path(name)
    if not rel:
        return ""
    return (repo_url or "https://libraries.minecraft.net/").rstrip("/") + "/" + rel
