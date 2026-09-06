# Core B 自测报告 — 启动引擎（version_scan.py + launch.py）

- 日期：2026-08-31 19:18 ~ 19:40 (GMT+8)
- 执行者：启动引擎 Agent（subagent）
- Python：C:\Program Files\AutoClaw\resources\python\python.exe
- 结论：**PASS（31/31）**

## 交付文件

| 文件 | 说明 |
|---|---|
| launcher/version_scan.py | VersionInfo(dataclass)、scan_versions、resolve_version_chain、get_version_mc_version |
| launcher/launch.py | _rules_allow、_FEATURES、_substitute、extract_natives、build_launch_command、GameProcess、launch_game |
| dev_reports/selftest_core_b.py | 自测脚本（31 项断言） |

errors.py / logsetup.py 由并行 Agent 提供，import 一次成功，未触发 15s 重试。

## 环境实测数据

- 游戏目录：F:\.minecraft，扫描到 **77 个版本文件夹**，其中 74 个有效、3 个无效（无 json/解析失败，已记录中文 reason）：`1.21.1-NeoForge_21.1.222`、`26.1-pre-2`、`LC`
- "1.20.1"：valid=True，mc_version="1.20.1"。注意：本机该版本 json 已被 MSL 合并了 Fabric（mainClass=net.fabricmc.loader.impl.launch.knot.KnotClient，jvm 参数里含 `-DFabricMcEmu= net.minecraft.client.main.Main `）
- Java：F:\MSL\Java21\bin\javaw.exe

## 自测结果（31/31 PASS）

```
PASS: scan_versions 数量>=20 实际=77
PASS: 1.20.1 存在且 valid
PASS: get_version_mc_version
INFO: 无效版本 3 个（无 json/解析失败，已记录 reason）：['1.21.1-NeoForge_21.1.222', '26.1-pre-2', 'LC']
PASS: command[0]==java
PASS: -cp in command
PASS: mainClass 非空 net.fabricmc.loader.impl.launch.knot.KnotClient
PASS: classpath 长度>5000 len=5477
PASS: command 无空串元素
PASS: 无残留 ${...} 未替换
PASS: --username 后跟 kokop
PASS: natives_dir 存在 F:\.minecraft\versions\1.20.1\1.20.1-natives
PASS: missing_libs 为空（原版） []
PASS: resolve_version_chain 成功
PASS: 合并后 mainClass=子
PASS: 合并 libraries 去重子在前(3 项) ['com.fake:shared:1.0', 'com.fake:child-only:1.0', 'com.fake:parent-only:1.0']
PASS: 合并 arguments game=父+子
PASS: 合并 arguments jvm=父+子
PASS: assetIndex 用父
PASS: _chain 记录祖先 ['TestParent']
PASS: 循环继承抛 LauncherError
PASS: 真实 Fabric 版 build_launch_command 不抛异常 missing=0
PASS: 旧格式版本 build_launch_command 不抛异常 folder=1.12.2-Forge_14.23.5.2859 missing=1
PASS: 1.20.1 无 natives 声明（1.19+ 正常，LWJGL 自带平台 jar） natives声明=False
INFO: 1.20.1 无 natives 声明，.dll 由 LWJGL 平台 jar 自行加载
PASS: 旧格式版本 extract_natives 解压出 .dll natives声明=True dll数=11
PASS: _rules_allow 无 rules
PASS: _rules_allow os 匹配 allow
PASS: _rules_allow os 不匹配→False
PASS: _rules_allow mac 参数不上 Windows
PASS: _rules_allow 无生效规则默认 False
PASS: _substitute 未知置 0
PASS: _substitute 已知替换

====== 汇总：PASS=31 FAIL=0 ======
```

## 关键数字

- 版本总数：**77**（有效 74 / 无效 3）
- 1.20.1 classpath 长度：**5477**（missing_libs=0）
- mainClass：net.fabricmc.loader.impl.launch.knot.KnotClient（本机 1.20.1 实为 Fabric 合并版）
- 旧格式 1.12.2-Forge_14.23.5.2859：构建成功，missing=1（lwjgl-platform natives jar 本机缺失，不阻断）
- extract_natives 旧格式版本：解压出 **11 个 .dll**（text2speech/jinput 等）；1.20.1 无 natives 声明（1.19+ 特性，LWJGL 平台 jar 自行加载，属正常）

## 实现要点与偏差说明

1. **_rules_allow 默认值**：任务书写 "（allow=True）"，实测按 default-True 会让 mac 专属 JVM 参数 `-XstartOnFirstThread`（osx allow 规则）进入 Windows 命令导致 JVM 启动失败，且 osx/linux 专属库全部进入 missing_libs。故实现为 **"存在 rules 时无生效规则→False"**（与 Prism Launcher 一致；官方 json 对此类场景均用 allow+os 配对，不受影响）。已在自测中验证 mac 参数不上 Windows。
2. **MSL 风格 json 的 `-cp ${classpath}`**：本机多个版本 json 把 `-cp`、`${classpath}` 写进 jvm 参数，引擎统一跳过这两个 token，由 build_launch_command 自行拼接唯一的 `-cp <classpath> <mainClass>`；jvm 映射含 classpath/launcher_name/launcher_version/natives_directory/library_directory/classpath_separator。
3. **真实目录无 inheritsFrom**：MSL 把继承链合并成单 json，77 个版本 base 全为空；继承链逻辑用合成父子版本（临时目录）验证，含循环继承抛 LauncherError。
4. **旧格式 minecraftArguments**：键值成对输出（含空格路径不碎），孤立末 token 直接替换输出；1.12.2-Forge 构建通过。
5. classpath 缺失库仍 append（保持命令完整）并记入 missing_libs，不阻断启动。
6. launch_game：Popen(stdout=PIPE, stderr=STDOUT, utf-8 replace)，守护线程逐行读输出→logging+on_output（异常吞掉）；GameProcess 提供 poll/wait/terminate/returncode；OSError→LauncherError 中文。本自测未实际拉起 JVM 进程（仅构建命令），launch_game 待联调阶段验证。
