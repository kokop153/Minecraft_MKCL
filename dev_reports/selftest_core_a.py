# -*- coding: utf-8 -*-
"""基础模块 A 组自测：accounts / config / java_utils。纯 assert + PASS 打印。"""
import json
import os
import shutil
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from launcher.accounts import AccountStore, offline_uuid  # noqa: E402
from launcher.config import AppConfig  # noqa: E402
from launcher.java_utils import find_javas, pick_java_for  # noqa: E402


def test_offline_uuid():
    u1 = offline_uuid("kokop")
    u2 = offline_uuid("kokop")
    assert u1 == u2, "同名两次 UUID 不一致: %s vs %s" % (u1, u2)
    assert len(u1) == 36 and u1.count("-") == 4, "UUID 格式不对: %s" % u1
    assert u1[14] == "3", "version 位应为 3: %s" % u1
    assert u1[19] in "89ab", "variant 位非法: %s" % u1
    print("PASS offline_uuid 稳定且 version 位合法 -> %s" % u1)


def test_config():
    base = tempfile.mkdtemp(prefix="mcl_cfg_")
    try:
        cfg = AppConfig(base)
        cfg.load()
        cfg.set("memory_gb", 8)
        cfg.set("theme_color", "#334455")
        cfg.set("current_version", "1.20.1")
        cfg.window["width"] = 1200
        cfg.save()

        cfg2 = AppConfig(base)
        cfg2.load()
        assert cfg2.get("memory_gb") == 8, "memory_gb 往返不一致"
        assert cfg2.get("theme_color") == "#334455", "theme_color 往返不一致"
        assert cfg2.get("current_version") == "1.20.1", "current_version 往返不一致"
        assert cfg2.window["width"] == 1200, "window.width 往返不一致"
        with open(os.path.join(base, "config.json"), "r", encoding="utf-8") as f:
            raw = json.load(f)
        assert "username" not in raw and "_legacy_username" not in raw, "legacy 用户名不应落盘"
        print("PASS AppConfig load->set->save->reload 一致，legacy 字段不落盘")

        # 损坏 JSON -> 备份为 .bak 并回默认值
        with open(os.path.join(base, "config.json"), "w", encoding="utf-8") as f:
            f.write("{broken json!!!")
        cfg3 = AppConfig(base)
        cfg3.load()
        assert cfg3.get("memory_gb") == 4, "损坏后应回默认 memory_gb=4"
        assert cfg3.get("theme_color") == "#4A8F72", "损坏后应回默认 theme_color"
        assert os.path.isfile(os.path.join(base, "config.json.bak")), "损坏文件应备份为 config.json.bak"
        print("PASS AppConfig 损坏 JSON -> config.json.bak + 默认值")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_accounts():
    base = tempfile.mkdtemp(prefix="mcl_acc_")
    try:
        store = AccountStore(base)
        acc = store.add_offline("kokop")
        assert acc.uuid == offline_uuid("kokop"), "离线 UUID 计算不一致"
        assert store.set_current("kokop") is True
        store.save()

        store2 = AccountStore(base)
        cur = store2.current()
        assert cur is not None and cur.name == "kokop", "持久化后 current 应为 kokop"
        dup = store2.add_offline("kokop")
        assert dup.uuid == acc.uuid and len(store2.list()) == 1, "重名应返回已有账号"
        assert store2.remove("kokop") is True
        assert store2.current() is None
        store2.save()

        store3 = AccountStore(base)
        assert store3.list() == [], "删除并保存后应为空"
        store3.migrate_legacy_username("legacyplayer")
        assert store3.current() is not None and store3.current().name == "legacyplayer", "legacy 用户名迁移失败"

        for bad in ("", "a/b", "a:b", "name" * 6):
            try:
                store3.add_offline(bad)
                raise AssertionError("非法角色名未被拒绝: %r" % bad)
            except Exception:
                pass
        print("PASS AccountStore 增/查/删 + 迁移 + 非法名校验")
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_java():
    javas = find_javas([r"F:\MSL\Java21\bin\javaw.exe"])
    summary = [(j.path, j.version, j.major, j.vendor, bool(j.is_javaw)) for j in javas]
    print("  find_javas -> %d 个: %s" % (len(javas), summary))
    assert any(j.major == 21 for j in javas), "结果中应包含 major==21 的 Java"
    pick = pick_java_for("1.20.1", javas)
    assert pick is not None, "1.20.1 应能选到 Java"
    assert pick.major >= 17, "1.20.1 至少需要 Java 17"
    pick2 = pick_java_for("1.20.5", javas)
    assert pick2 is not None and pick2.major >= 21, "1.20.5+ 至少需要 Java 21"
    print("PASS find_javas 含 major==21；pick_java_for('1.20.1')/%s(major=%d) 非空" % (pick.path, pick.major))


def main():
    test_offline_uuid()
    test_config()
    test_accounts()
    test_java()
    print("ALL PASS core_a")


if __name__ == "__main__":
    main()
