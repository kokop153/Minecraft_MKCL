# 基础模块 A 组报告（core_a）

日期：2026-08-31 19:18 (GMT+8)
Python：`C:\Program Files\AutoClaw\resources\python\python.exe`
项目根：`C:\Users\LiXiaoHao\.openclaw-autoclaw\workspace\minecraft-launcher`

## 文件清单（本组创建，共 8 个）

- `launcher/__init__.py` — 包标识注释
- `launcher/errors.py` — `LauncherError(message, detail="")`，`str(e)` 返回 message
- `launcher/logsetup.py` — `setup_logging(base_dir)`（logs/launcher.log，RotatingFileHandler 1MB×5 utf-8 + StreamHandler，幂等）、`get_log_path(base_dir)`
- `launcher/config.py` — `AppConfig`：默认值、容错 load（损坏→`config.json.bak`+默认）、原子 save（tmp→os.replace）、`get/set`、旧 demo 键映射（`username`→`self._legacy_username`，不落盘）
- `launcher/accounts.py` — `offline_uuid`（与 Java nameUUIDFromBytes 一致的 v3 UUID）、`Account` dataclass、`AccountStore`（accounts.json，原子写；add_offline 校验非空/≤16 字符/无 `\/:*?"<>|`，重名返回已有；remove/current/set_current/migrate_legacy_username）
- `launcher/java_utils.py` — `JavaRuntime` dataclass、`find_javas(extra_paths=None)`、`pick_java_for(mc_version, javas, preferred="")`
- `dev_reports/selftest_core_a.py` — 自测脚本（纯 assert + PASS 打印）
- `dev_reports/report_core_a.md` — 本报告

## 要点

- **offline_uuid**：MD5("OfflinePlayer:"+name) → b[6]=(b[6]&0x0F)|0x30、b[8]=(b[8]&0x3F)|0x80 → UUID v3 格式。实测 `kokop` → `43465a85-8a83-36d3-8a93-ae2ee0cc2baa`，第 3 段以 `3` 开头，variant 位合法，两次调用一致。
- **AppConfig**：`__init__` 设默认后自动 `load()`（无文件即默认，可再显式 load）；逐字段类型防御（str/int/dict/bool/None 分别校验，bool 不算 int）；损坏 JSON 先 `os.replace` 成 `config.json.bak` 再用默认；save 只写 9 个持久化字段，`_legacy_username` 永不落盘。
- **AccountStore**：`__init__` 自动 load；save 原子写；`migrate_legacy_username` 仅在列表为空且 name 非空时生效。
- **find_javas**：候选来源 = extra_paths → JAVA_HOME → 注册表 HKLM\SOFTWARE\JavaSoft 递归（JavaHome/MachineDir）→ glob（Program Files×2、LOCALAPPDATA、.minecraft\runtime\*\bin、C:~G: 盘 `\MSL\Java*\bin`）。候选取目录下 `java.exe` 跑 `-version`（stderr）解析；`is_javaw` 记录同目录 `javaw.exe` 的完整路径（无则 ""）；vendor 按 Temurin/GraalVM/Zulu/Corretto/Microsoft/HotSpot/Oracle/OpenJDK 等关键词猜测；realpath 去重、上限 12、找不到返回空列表。
- **pick_java_for**：需求映射 1.20.5+→21、1.18~1.20.4→17、1.17.x→16、其余→8（required=8 时 min-major 规则天然优先 JDK8）。preferred 存在且探测满足最低 major 时包装成 JavaRuntime 直接返回；否则在满足条件的候选里选 major 最接近需求的，同 major 版本号新者优先。
- **实测环境发现**：本机共探到 6 个 Java —— F:\MSL\Java21 (21.0.5, HotSpot)、JDK 26.0.2、x86 JRE 1.8.0_371、.minecraft runtime 21.0.7/17.0.15 (Microsoft)、jre-legacy 1.8.0_51。`pick_java_for("1.20.1")` 正确选中 17.0.15（major 最接近 17），而非 21/26。

## 问题 / 备注（给下游模块）

1. `JavaRuntime.is_javaw` 是**字符串**（javaw.exe 路径，无则 ""），不是布尔——按规格 "is_javaw 记录其路径" 实现，launch 模块启动游戏时用它选 javaw。
2. `AppConfig.__init__` 会自动 `load()`；显式再调 `load()` 无副作用（重置为文件内容/默认）。
3. 配置损坏时只备份最近一次损坏文件（`.bak` 被覆盖），属预期行为。
4. `find_javas` 探测依赖 `java -version` 子进程（单个 20s 超时）；候选目录不存在 `java.exe` 时静默跳过，不会报错。
5. 注册表/双 JRE 场景未做 WOW6432Node 特殊处理（64 位 Python 默认视图已覆盖本机全部 6 个 Java）。

## 自测命令与完整输出

命令（workdir=项目根）：

```
& "C:\Program Files\AutoClaw\resources\python\python.exe" dev_reports\selftest_core_a.py
```

输出：

```
PASS offline_uuid 稳定且 version 位合法 -> 43465a85-8a83-36d3-8a93-ae2ee0cc2baa
PASS AppConfig load->set->save->reload 一致，legacy 字段不落盘
PASS AppConfig 损坏 JSON -> config.json.bak + 默认值
PASS AccountStore 增/查/删 + 迁移 + 非法名校验
  find_javas -> 6 个: [('F:\\MSL\\Java21\\bin\\java.exe', '21.0.5', 21, 'HotSpot', True), ('C:\\Program Files\\Java\\jdk-26.0.2\\bin\\java.exe', '26.0.2', 26, 'HotSpot', True), ('C:\\Program Files (x86)\\Java\\jre-1.8\\bin\\java.exe', '1.8.0_371', 8, 'HotSpot', True), ('C:\\Users\\LiXiaoHao\\AppData\\Roaming\\.minecraft\\runtime\\java-runtime-delta\\bin\\java.exe', '21.0.7', 21, 'Microsoft', True), ('C:\\Users\\LiXiaoHao\\AppData\\Roaming\\.minecraft\\runtime\\java-runtime-gamma-snapshot\\bin\\java.exe', '17.0.15', 17, 'Microsoft', True), ('C:\\Users\\LiXiaoHao\\AppData\\Roaming\\.minecraft\\runtime\\jre-legacy\\bin\\java.exe', '1.8.0_51', 8, 'HotSpot', True)]
PASS find_javas 含 major==21；pick_java_for('1.20.1')/C:\Users\LiXiaoHao\AppData\Roaming\.minecraft\runtime\java-runtime-gamma-snapshot\bin\java.exe(major=17) 非空
ALL PASS core_a
```

## 结论

**全部 PASS（4/4 测试组，ALL PASS core_a）。**
