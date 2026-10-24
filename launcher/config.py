# -*- coding: utf-8 -*-
"""应用配置：默认值 + 容错加载 + 原子保存。"""
import json
import os

_STR_FIELDS = ("java_path", "game_dir", "current_version", "jvm_extra_args",
               "theme_color", "download_source", "theme_mode",
               "window_size_mode", "process_priority", "ip_preference",
               "launcher_visibility", "custom_message")


class AppConfig:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self._path = os.path.join(base_dir, "config.json")
        self._set_defaults()
        self._legacy_username = ""
        self.load()

    def _set_defaults(self):
        self.java_path = ""
        self.game_dir = ""
        self.current_version = ""
        self.memory_gb = 4
        self.jvm_extra_args = ""
        self.theme_color = "#4C5FE8"
        self.theme_mode = "light"
        # ---- 启动选项 ----
        self.window_size_mode = "default"     # default / maximized / fullscreen / custom
        self.window_width = 854               # 自定义模式下的游戏窗口宽
        self.window_height = 480              # 自定义模式下的游戏窗口高
        self.process_priority = "normal"      # low / normal / high / realtime
        self.ip_preference = "java"           # java / ipv4 / ipv6
        self.launcher_visibility = "keep"     # keep / minimize / exit
        self.custom_message = ""              # 自定义信息（显示在启动器标题栏）
        self.memory_auto = True               # 内存自动配置
        self.download_source = "bmclapi"
        self.window = {"width": 980, "height": 640, "maximized": False, "x": None, "y": None}
        self.per_version = {}
        self.auto_isolate = True

    # ---------- load ----------
    def load(self):
        """读 <base_dir>/config.json。缺失用默认；损坏则备份为 .bak 后用默认。返回 self。"""
        self._set_defaults()
        self._legacy_username = ""
        if not os.path.isfile(self._path):
            return self
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("config root is not a dict")
        except (ValueError, OSError):
            try:
                os.replace(self._path, self._path + ".bak")
            except OSError:
                pass
            return self
        self._apply(data)
        return self

    def _apply(self, data: dict):
        """逐字段类型防御：类型不对就保留默认值。"""
        for key in _STR_FIELDS:
            v = data.get(key)
            if isinstance(v, str):
                setattr(self, key, v)
        v = data.get("memory_gb")
        if isinstance(v, int) and not isinstance(v, bool):
            self.memory_gb = v
        v = data.get("username")  # 旧 demo 键：单独留给外部做账号迁移
        if isinstance(v, str):
            self._legacy_username = v
        v = data.get("window")
        if isinstance(v, dict):
            win = dict(self.window)
            for k in ("width", "height"):
                if isinstance(v.get(k), int) and not isinstance(v.get(k), bool):
                    win[k] = v[k]
            if isinstance(v.get("maximized"), bool):
                win["maximized"] = v["maximized"]
            for k in ("x", "y"):
                val = v.get(k)
                if val is None or (isinstance(val, int) and not isinstance(val, bool)):
                    win[k] = val
            self.window = win
        v = data.get("per_version")
        if isinstance(v, dict):
            self.per_version = dict(v)
        v = data.get("auto_isolate")
        if isinstance(v, bool):
            self.auto_isolate = v
        for key in ("window_width", "window_height"):
            v = data.get(key)
            if isinstance(v, int) and not isinstance(v, bool) and 100 <= v <= 16384:
                setattr(self, key, v)
        v = data.get("memory_auto")
        if isinstance(v, bool):
            self.memory_auto = v

    # ---------- save ----------
    def save(self):
        """原子写 config.json（tmp -> os.replace），只写持久化字段。"""
        data = {
            "java_path": self.java_path,
            "game_dir": self.game_dir,
            "current_version": self.current_version,
            "memory_gb": self.memory_gb,
            "jvm_extra_args": self.jvm_extra_args,
            "theme_color": self.theme_color,
            "theme_mode": self.theme_mode,
            "window_size_mode": self.window_size_mode,
            "window_width": self.window_width,
            "window_height": self.window_height,
            "process_priority": self.process_priority,
            "ip_preference": self.ip_preference,
            "launcher_visibility": self.launcher_visibility,
            "custom_message": self.custom_message,
            "memory_auto": bool(self.memory_auto),
            "download_source": self.download_source,
            "window": dict(self.window),
            "per_version": dict(self.per_version),
            "auto_isolate": bool(self.auto_isolate),
        }
        os.makedirs(self.base_dir, exist_ok=True)
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)

    # ---------- 泛化读写 ----------
    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def set(self, key: str, value):
        setattr(self, key, value)
