# -*- coding: utf-8 -*-
"""离线账号管理：离线 UUID、账号存储（accounts.json）。"""
import datetime
import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, field

from .errors import LauncherError

_INVALID_CHARS = set('\\/:*?"<>|')


def offline_uuid(name: str) -> str:
    """Minecraft 离线模式 UUID，与 Java UUID.nameUUIDFromBytes 完全一致。"""
    b = bytearray(hashlib.md5(("OfflinePlayer:" + name).encode("utf-8")).digest())
    b[6] = (b[6] & 0x0F) | 0x30
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


@dataclass
class Account:
    name: str
    uuid: str
    user_type: str = "offline"
    created_at: str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds"))


class AccountStore:
    """存 <base_dir>/accounts.json：{"current_name": str|None, "accounts": [...]}"""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.path = os.path.join(base_dir, "accounts.json")
        self.current_name = None
        self.accounts = []
        self.load()

    def load(self):
        """缺失/损坏 -> 空存储。"""
        self.current_name = None
        self.accounts = []
        if not os.path.isfile(self.path):
            return self
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            return self
        if not isinstance(data, dict):
            return self
        cn = data.get("current_name")
        self.current_name = cn if isinstance(cn, str) else None
        arr = data.get("accounts")
        if isinstance(arr, list):
            for item in arr:
                if not isinstance(item, dict):
                    continue
                name, uid = item.get("name"), item.get("uuid")
                if not isinstance(name, str) or not isinstance(uid, str):
                    continue
                ut = item.get("user_type")
                ca = item.get("created_at")
                self.accounts.append(Account(
                    name=name,
                    uuid=uid,
                    user_type=ut if isinstance(ut, str) else "offline",
                    created_at=ca if isinstance(ca, str) else "",
                ))
        return self

    def save(self):
        """原子写 accounts.json。"""
        data = {
            "current_name": self.current_name,
            "accounts": [asdict(a) for a in self.accounts],
        }
        os.makedirs(self.base_dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def list(self):
        return list(self.accounts)

    def add_offline(self, name: str) -> Account:
        name = (name or "").strip()
        if not name:
            raise LauncherError("角色名不能为空")
        if len(name) > 16:
            raise LauncherError("角色名不能超过 16 个字符")
        for ch in name:
            if ch in _INVALID_CHARS:
                raise LauncherError('角色名包含非法字符 \\ / : * ? " < > |')
        for acc in self.accounts:
            if acc.name == name:
                return acc
        acc = Account(name=name, uuid=offline_uuid(name))
        self.accounts.append(acc)
        return acc

    def remove(self, name: str) -> bool:
        for i, acc in enumerate(self.accounts):
            if acc.name == name:
                self.accounts.pop(i)
                if self.current_name == name:
                    self.current_name = None
                return True
        return False

    def current(self):
        for acc in self.accounts:
            if acc.name == self.current_name:
                return acc
        return None

    def set_current(self, name: str) -> bool:
        for acc in self.accounts:
            if acc.name == name:
                self.current_name = name
                return True
        return False

    def migrate_legacy_username(self, name: str):
        """列表为空且 name 非空时，把旧 demo 用户名迁移为离线账号并设为当前。"""
        if not self.accounts and name:
            self.add_offline(name)
            self.set_current(name)
        return self.current()
