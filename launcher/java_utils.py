# -*- coding: utf-8 -*-
"""Java 运行时探测与按 MC 版本选 Java（Windows）。"""
import glob
import os
import re
import subprocess
from dataclasses import dataclass


@dataclass
class JavaRuntime:
    path: str      # java.exe 完整路径
    version: str   # 完整版本号，如 "21.0.5"
    major: int     # 主版本号，如 21
    vendor: str    # 供应商猜测，如 "Temurin"；猜不出为 ""
    is_javaw: str  # 同目录 javaw.exe 路径；没有为 ""
    is_64: bool = True   # 64 位 JVM 标志；32 位 JVM 堆上限仅约 1.5G


_VENDOR_HINTS = (
    ("temurin", "Temurin"),
    ("adoptopenjdk", "AdoptOpenJDK"),
    ("graalvm", "GraalVM"),
    ("zulu", "Zulu"),
    ("corretto", "Corretto"),
    ("dragonwell", "Dragonwell"),
    ("liberica", "Liberica"),
    ("microsoft", "Microsoft"),
    ("hotspot", "HotSpot"),
    ("java(tm) se", "Oracle"),
    ("openjdk", "OpenJDK"),
)

_DRIVE_LETTERS = ("C:", "D:", "E:", "F:", "G:")


def _registry_java_homes():
    """读注册表 HKLM\\SOFTWARE\\JavaSoft 递归子键的 JavaHome / MachineDir 值。"""
    homes = []
    try:
        import winreg
    except ImportError:
        return homes
    base = r"SOFTWARE\JavaSoft"

    def walk(sub):
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base + (("\\" + sub) if sub else ""))
        except OSError:
            return
        try:
            i = 0
            while True:
                try:
                    name, val, _t = winreg.EnumValue(key, i)
                except OSError:
                    break
                if name in ("JavaHome", "MachineDir") and isinstance(val, str) and val:
                    homes.append(val)
                i += 1
            j = 0
            while True:
                try:
                    subkey = winreg.EnumKey(key, j)
                except OSError:
                    break
                walk((sub + "\\" + subkey) if sub else subkey)
                j += 1
        finally:
            key.Close()

    walk("")
    return homes


def _normalize_bin_dir(p: str) -> str:
    """把 exe 路径 / bin 目录 / 主目录统一归一化为 bin 目录。"""
    p = os.path.expandvars(os.path.expanduser(str(p).strip()))
    low = p.lower()
    if low.endswith("java.exe") or low.endswith("javaw.exe"):
        return os.path.dirname(p)
    if os.path.basename(p).lower() == "bin":
        return p
    inner = os.path.join(p, "bin")
    if os.path.isdir(inner):
        return inner
    return p


def _candidate_dirs(extra_paths=None):
    dirs, seen = [], set()

    def add(p):
        if not p:
            return
        try:
            d = os.path.normpath(_normalize_bin_dir(p))
        except OSError:
            return
        if d in seen:
            return
        seen.add(d)
        dirs.append(d)

    for p in (extra_paths or []):
        add(p)
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        add(java_home)
    for h in _registry_java_homes():
        add(h)
    local_app = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    patterns = [
        r"C:\Program Files\Java\*\bin",
        r"C:\Program Files (x86)\Java\*\bin",
        os.path.join(local_app, "Programs", "Java", "*", "bin") if local_app else "",
        os.path.join(appdata, ".minecraft", "runtime", "*", "bin") if appdata else "",
    ]
    for drive in _DRIVE_LETTERS:
        patterns.append(os.path.join(drive + os.sep, "MSL", "Java*", "bin"))
    for pat in patterns:
        if not pat:
            continue
        try:
            for d in glob.glob(pat):
                add(d)
        except OSError:
            pass
    return dirs


def _major_of(version: str) -> int:
    m = re.match(r"^(\d+)(?:\.(\d+))?", version)
    if not m:
        return 0
    a, b = int(m.group(1)), m.group(2)
    if a == 1 and b is not None:
        return int(b)
    return a


def _guess_vendor(text: str) -> str:
    low = text.lower()
    for kw, name in _VENDOR_HINTS:
        if kw in low:
            return name
    return ""


def _probe(java_exe: str):
    """运行 java -version（信息输出在 stderr），解析失败返回 None。

    返回 (version, major, vendor, is_64)：is_64 依据输出中的
    "64-Bit" 标记（32 位 Client VM 不输出该标记）。
    """
    try:
        proc = subprocess.run(
            [java_exe, "-version"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stderr or "") + "\n" + (proc.stdout or "")
    m = re.search(r'version "([^"]+)"', text)
    if not m:
        return None
    version = m.group(1)
    major = _major_of(version)
    if major <= 0:
        return None
    return version, major, _guess_vendor(text), ("64-Bit" in text)


def find_javas(extra_paths=None, max_count: int = 12):
    """扫描本机 Java：extra_paths + JAVA_HOME + 注册表 + 常见目录 glob。

    每个候选取其目录下 java.exe 并用 -version 探测；解析失败丢弃。
    按 os.path.realpath(java.exe) 去重，上限 max_count；找不到返回空列表。
    """
    results, seen_real = [], set()
    for d in _candidate_dirs(extra_paths):
        java_exe = os.path.join(d, "java.exe")
        if not os.path.isfile(java_exe):
            continue
        real = os.path.realpath(java_exe)
        if real in seen_real:
            continue
        probe = _probe(java_exe)
        if probe is None:
            continue
        version, major, vendor, is_64 = probe
        javaw = os.path.join(d, "javaw.exe")
        seen_real.add(real)
        results.append(JavaRuntime(
            path=java_exe,
            version=version,
            major=major,
            vendor=vendor,
            is_javaw=javaw if os.path.isfile(javaw) else "",
            is_64=is_64,
        ))
        if len(results) >= max_count:
            break
    return results


def _required_major(mc_version: str) -> int:
    """1.20.5+ -> 21；1.18~1.20.4 -> 17；1.17.x -> 16；1.13~1.16 -> 8；更旧/无法识别 -> 8。"""
    parts = []
    for seg in str(mc_version).split("."):
        if seg.isdigit():
            parts.append(int(seg))
        else:
            break
    if len(parts) < 2 or parts[0] != 1:
        return 8
    minor = parts[1]
    patch = parts[2] if len(parts) >= 3 else 0
    if minor >= 21:
        return 21
    if minor == 20:
        return 21 if patch >= 5 else 17
    if minor >= 18:
        return 17
    if minor == 17:
        return 16
    return 8


def _ver_key(version: str):
    return tuple(int(x) for x in re.findall(r"\d+", version or ""))


def _resolve_java_exe(p: str) -> str:
    p = os.path.expandvars(os.path.expanduser(str(p).strip()))
    low = os.path.basename(p).lower()
    if low in ("java.exe", "javaw.exe"):
        return p
    if low == "bin":
        return os.path.join(p, "java.exe")
    cand = os.path.join(p, "bin", "java.exe")
    if os.path.isfile(cand):
        return cand
    return os.path.join(p, "java.exe")


def pick_java_for(mc_version: str, javas, preferred: str = ""):
    """按 MC 版本挑 Java。

    preferred 能 os.path.exists 且满足最低版本时，探测后包装成 JavaRuntime 返回；
    否则在满足最低 major 的候选里选 major 最接近需求的（同 major 取版本号新的）。
    找不到返回 None。
    """
    required = _required_major(mc_version)

    if preferred:
        exe = _resolve_java_exe(preferred)
        if os.path.isfile(exe):
            probe = _probe(exe)
            if probe is not None and probe[1] >= required:
                d = os.path.dirname(exe)
                javaw = os.path.join(d, "javaw.exe")
                return JavaRuntime(
                    path=exe,
                    version=probe[0],
                    major=probe[1],
                    vendor=probe[2],
                    is_javaw=javaw if os.path.isfile(javaw) else "",
                    is_64=probe[3],
                )

    ok = [j for j in (javas or []) if j.major >= required]
    if not ok:
        return None
    # major 升序（最接近需求）；同 major 时 64 位优先（32 位堆上限仅约
    # 1.5G，选了会导致 -Xmx 超限、JVM 创建失败弹原生错误框）；再按版本号新的
    return min(ok, key=lambda j: (
        j.major, not j.is_64, tuple(-n for n in _ver_key(j.version))))
