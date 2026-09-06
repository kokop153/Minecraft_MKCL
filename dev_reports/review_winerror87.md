# WinError 87 修复审查报告（review_winerror87）

- 审查人：启动修复审查员（独立代码审查）
- 日期：2026-09-01
- 审查对象：`launcher/launch.py`（resolve_java_for_launch / launch_game 前置校验）、`launcher/version_scan.py`（derive_mc_version）、`launcher/ui/workers.py`（LaunchWorker.run）、`launcher/java_utils.py`（pick_java_for 等）、`launcher/ui/home_page.py`（on_launch 传参）、`main.py`
- 方法：通读全部相关源码 + 全仓硬编码 grep + 用项目自带 Python 实际调用 derive_mc_version / launch_game / resolve_java_for_launch 做黑盒验证（临时目录在系统 %TEMP%，已清理，未改动仓库任何代码文件）

---

## 一、总体结论：**有保留通过**

WinError 87 的根因（UI"自动选择"存空串 → 空串作为 `command[0]` 传给 `Popen` → 系统级 WinError 87）已被有效封堵：

1. `resolve_java_for_launch` 保证"绝不返回空串"，空值走自动选择，手动路径校验存在性，全部失败路径抛可读中文 `LauncherError`（实测 6 类分支全部命中）。
2. `launch_game` 前置校验（空命令/空 Java/空参数/非字符串参数/Java 文件不存在/workdir 不存在）在 `Popen` 之前拦截，实测全部返回中文错误而非系统级 OSError。
3. `LaunchWorker.run` 在构建命令前调用 `resolve_java_for_launch`，全应用只有 `home_page.on_launch` 一个 LaunchWorker 构造点、只有 `launch_game` 一个 `Popen` 启动点，无绕过路径。
4. 硬编码检查通过：`launcher/` 与 `main.py` 无任何硬编码版本 id（含 "fps1.20.1"），版本 id 全部来自 config/参数。
5. 端到端实测：空 java_path + 真实系统 Java 探测 → 自动选中 javaw.exe（按推导版本匹配 major），链路可用。

**保留原因**：新引入的 `derive_mc_version` 存在一个会实际影响自动选 Java 正确性的缺陷（问题 1）：Fabric 官方安装器默认版本 id（`fabric-loader-0.16.14-1.20.1` 这类 loader 版本在前）会被推导成 `0.16.14`，进而把 Java 要求降为 8、自动选择会挑最老的 Java，导致新版 Fabric 实例必然启动失败（UnsupportedClassVersionError 之类）。该缺陷不回归 WinError 87 本身，但削弱本次修复的核心卖点"按版本智能匹配"。

---

## 二、问题清单

### 问题 1（严重度：中偏高）derive_mc_version 首个"版本样"匹配优先，loader 版本会抢占 MC 版本

- **位置**：`launcher/version_scan.py` — `_MC_VER_RE` 与 `derive_mc_version()` 前段（`for cand in (info.mc_version, info.folder, info.name)` 循环）
- **说明**：正则 `\d+\.\d+(?:\.\d+)?(?:-pre\d+)?` 对每个候选取 `re.search` 的**第一个**匹配。Fabric 官方安装器创建的默认 id/文件夹名 `fabric-loader-0.16.14-1.20.1` 第一个匹配是 loader 版本 `0.16.14`（实测见验证 C-3），直接返回，后续的继承链/intermediary 兜底全部不可达。`_required_major("0.16.14")` 返回 8（`parts[0] != 1`），于是 `pick_java_for` 在"满足 major>=8 的候选里挑 major 最小"的策略下**挑最老的 Java**。后果：机器上同时有 Java 8 + Java 21 时，MC 1.21.x Fabric 实例会拿到 Java 8 → 必然启动失败；只有 Java 17/21 时拿到 17，1.21 实例同样起不来。同类输入 `"Fabric 0.16.14 1.20.1"` 也推导为 `0.16.14`（实测 B-5/B-6）。任务给定的 4 个用例中 `"1.20.1-Fabric 0.16.14-OptiFine_I6"` 因 MC 版本在前而侥幸正确，但真实 Fabric 官方命名恰好是 loader 版本在前的形态，命中概率不低。
- **建议**：对每个候选用 `findall` 收集**全部**版本样匹配，优先接受以 `1.` 开头（或首位为 1 且 major 合理）的匹配；若无 `1.x` 形态匹配再落到继承链/intermediary 兜底。或等价方案：候选匹配结果先过 `_required_major` 的 sanity（`parts[0] == 1`）不通过就继续找下一个来源。

### 问题 2（严重度：低）完全无法推导时回退"最老 Java"策略

- **位置**：`launcher/version_scan.py` `derive_mc_version()` 末尾回退 `return info.mc_version`；`launcher/java_utils.py` `pick_java_for()` 的 `min(ok, key=(major, -version))`
- **说明**：实测 `"11451419191800's Redstone Optimization"`（id/文件夹/继承/intermediary 全无版本信息）→ derive 返回原串 → `_required_major` = 8 → 自动选择会挑机器上**最老**的 Java。对一个"未知新版本"实例，挑 Java 8 是最坏猜测（现代版本至少要 17/21）。
- **建议**：版本无法推导时反向取"最高 major"的 Java（如 `pick_java_for` 提供 `prefer_newest_fallback` 参数），或在该场景于 UI 明确提示"未能识别版本，请手动选择 Java"。

### 问题 3（严重度：低）bad_idx 校验把"非字符串参数"也报成"参数为空"，措辞误导

- **位置**：`launcher/launch.py` `launch_game()` 中 `bad_idx` 检查与错误文案
- **说明**：实测 `command=[sys.executable, 123]` → 报错 `"启动命令第 [1] 项参数为空，已阻止启动"`，但 123 非空，问题其实是"类型不是字符串"。拦截本身正确（非 str 会令 Popen 抛 TypeError），仅文案不准。
- **建议**：区分两类违规：`not isinstance(a, str)` → "第 N 项参数不是字符串"；`a == ""` → "第 N 项参数为空"。

### 问题 4（严重度：低）错误 detail 声称"完整命令已写入日志"，但代码从未输出完整命令

- **位置**：`launcher/launch.py` `launch_game()` bad_idx 分支 detail 文案
- **说明**：`build_launch_command` 只记录 mainClass 与参数总数，`launch_game` 在校验**之后**才记录 java/workdir/参数总数；bad_idx 抛错前没有任何一处把完整 command 写日志。排障时用户按提示去日志里找"完整命令"会扑空。
- **建议**：抛错前 `logging.error("启动命令：%r", command)`（可按需脱敏），或把 detail 改为与实际日志内容一致。

### 问题 5（严重度：低）build_launch_command 中 workdir/natives 目录创建的 OSError 未包装为 LauncherError

- **位置**：`launcher/launch.py` `build_launch_command()` 内 `os.makedirs(workdir, exist_ok=True)` 与 `extract_natives()` 内 `os.makedirs(natives_dir, exist_ok=True)`
- **说明**：任务点名的"isolate_dir 的 workdir 创建失败"分支：若创建失败（权限/磁盘问题），`PermissionError`/`OSError` 直接冒泡到 `LaunchWorker.run` 的通用 `except Exception`，UI 显示 `PermissionError: ...` 形式的错误——可用、不崩溃，但不符合本次修复"系统级错误转中文 LauncherError"的统一风格。
- **建议**：这两处 `os.makedirs` 包 `try/except OSError` → `LauncherError("无法创建游戏工作目录/natives 目录：...", detail=...)`。

### 问题 6（严重度：信息）手工编辑过的 accounts.json 若缺 uuid/name 字段，_substitute 会抛 TypeError（既有问题，非本次引入）

- **位置**：`launcher/launch.py` `_substitute()` 的 `repl`（mapping 值为 None 时 `re.sub` 的替换函数返回 None → TypeError）；上游 `launcher/accounts.py` `load()` 允许 `uuid=None`
- **说明**：空串 uuid（`""`）会被 bad_idx 以中文错误拦截（可接受）；但 None 值会在 `_substitute` 内变成 TypeError，走 worker 兜底显示。另：json 无 assetIndex 时 `${asset_index_name}` 替换为空串，会被 bad_idx 拦截——对残缺 json 属于合理拦截，但排障时需知道"合法空串占位符"也会被拦。
- **建议**：`game_mapping` 构造时统一 `str(x or "")`（如 `auth_uuid`、`auth_player_name`），把 None 归一为空串交给 bad_idx 拦截。

### 问题 7（严重度：信息）pick_java_for 的 preferred 参数在启动链路成为死代码；手动配置目录形式 Java 路径被静默转自动

- **位置**：`launcher/launch.py` `resolve_java_for_launch()`（未向 `pick_java_for` 传 preferred）；`launcher/ui/home_page.py` on_launch 的 `java_path=cfg.java_path if (cfg.java_path and os.path.isfile(cfg.java_path)) else ""`
- **说明**：设置页下拉只存具体 exe 路径或空串，因此 preferred/`_resolve_java_exe`（目录→bin/java.exe 归一）在真实链路不可达。用户 config 里若是目录路径（手改配置文件），home_page 预过滤会把失效路径静默转成自动选择——行为上是改善（避免 WinError），但"配置的 Java 路径无效"这一手动分支错误对 UI 用户实际不可触发，提示仅对其他调用方有意义。非缺陷，记录备查。

---

## 三、硬编码搜索结果（自 grep 证据）

搜索命令（PowerShell，全仓 *.py，排除 __pycache__/.git）：

```
Get-ChildItem -Path <项目根> -Recurse -File -Filter *.py |
  Where-Object { $_.FullName -notmatch '__pycache__|\.git' } |
  Select-String -Pattern 'fps1|1\.2[0-9]\.[0-9]|1\.1[6-9]\.[0-9]|0\.16\.14'
```

命中摘要（相对项目根）：

| 文件 | 行 | 内容 | 判定 |
|---|---|---|---|
| `launcher/version_scan.py` | 12 / 203 / 207 | 注释与 docstring 中的示例（"my1.20.1"、"1.21.11红石生电优化"、intermediary 示例） | 注释，非逻辑，**通过** |
| `launcher/java_utils.py` | 207 | `_required_major` docstring 示例（1.20.5/1.18~1.20.4/1.17.x/1.13~1.16） | 注释，**通过** |
| `dev_reports/selftest_*.py` | 多处 | 自测脚本中的测试夹具（"fps1.20.1"、"1.20.1" 等） | 测试数据，不进启动链路，**通过** |
| `legacy_demo/脚本生成.py` | 10 / 91 | `VERSION = "1.20.1"` | 独立 demo 脚本；已验证 `launcher/` 内无任何 `legacy_demo` import，**通过** |
| `main.py` | — | 无任何版本号字面量 | **通过** |

补充：`Select-String -Pattern 'Popen|launch_game|LaunchWorker\(|java_path'` 证明 `subprocess.Popen` 仅存在于 `launcher/launch.py:450`（启动唯一入口）与 `java_utils` 的探测（`subprocess.run`，带 timeout/异常保护）；`LaunchWorker(` 仅 `home_page.py:193` 一处构造。

**结论：启动链路（launcher/ + main.py）无硬编码版本 id，版本 id 全部来自 config / 函数参数 / 版本扫描。**

---

## 四、实际执行的验证命令与输出摘要

环境：Windows PowerShell，`"C:\Program Files\AutoClaw\resources\python\python.exe"`（-X utf8）。测试脚本经 base64 包装注入 `python -c`（规避 PowerShell 引号转换），构造 `VersionInfo` 直接调用模块函数；继承链/intermediary 用例使用**系统 %TEMP% 下的临时目录**造 json（不在仓库内），测试后已 `rmtree` 清理。未修改任何 `launcher/` 代码。

### A. 正则行为（_MC_VER_RE.findall）

```
findall('fps1.20.1')                                -> ['1.20.1']
findall('fabric-loader-0.16.14-1.20.1')             -> ['0.16.14', '1.20.1']   ← 首个匹配是 loader 版本
findall("11451419191800's Redstone Optimization")   -> []
findall('Fabric 0.16.14 1.20.1')                    -> ['0.16.14', '1.20.1']
```

### B. derive_mc_version（纯字符串用例，无 json 文件）

```
derive('fps1.20.1')                              -> '1.20.1'    required_major=17   ✅
derive('1.21.5')                                 -> '1.21.5'    required_major=21   ✅
derive('1.20.1-Fabric 0.16.14-OptiFine_I6')      -> '1.20.1'    required_major=17   ✅
derive("11451419191800's Redstone Optimization") -> 原串回退     required_major=8    ⚠ 问题2
derive('fabric-loader-0.16.14-1.20.1')           -> '0.16.14'   required_major=8    ❌ 问题1
derive('Fabric 0.16.14 1.20.1')                  -> '0.16.14'   required_major=8    ❌ 问题1
derive('1.21.11红石生电优化')                     -> '1.21.11'  required_major=21   ✅
```

### C. derive_mc_version（%TEMP% 真实 json 文件）

```
继承链(id乱码+inherits)      : derive('fps-test')                 -> '1.20.1'   required=17  ✅（乱码 id 走 _chain 祖先）
intermediary(id无版本)       : derive('custom-fabric')            -> '1.21.5'   required=21  ✅
fabric官方id+intermediary    : derive('fabric-loader-0.16.14-1.20.1') -> '0.16.14' required=8 ❌ 问题1：json 内明明有
    net.fabricmc:intermediary:1.20.1 兜底，却因 id 正则先命中 0.16.14 而不可达
```

### D. resolve_java_for_launch 错误路径

```
手动路径不存在   -> LauncherError('配置的 Java 路径无效（文件不存在）：C:\nonexistent\javaw.exe')            ✅
game_dir无效+空串java -> LauncherError('游戏目录不存在：<路径>'), detail='未找到 versions 目录…'             ✅
game_dir无效+None java -> 同上（str(None or '') 归一后同样进入校验）                                        ✅
```

### E. 端到端自动选择（真实 find_javas，%TEMP% 游戏目录，fps-test → 推导 1.20.1 → 需 major≥17）

```
auto-select -> 'C:\Users\LiXiaoHao\AppData\Roaming\.minecraft\runtime\java-runtime-gamma-snapshot\bin\javaw.exe'
```

（本机实选 Java 17 gamma 运行时，与"满足最低 major 且 major 最接近"策略一致 ✅）

### F. launch_game 前置校验（全部在 Popen 之前拦截）

```
空命令            -> LauncherError('启动命令为空，无法启动游戏')                  ✅
Java空串          -> LauncherError('未获取到 Java 路径，无法启动游戏')             ✅
空参数(索引2)     -> LauncherError('启动命令第 [2] 项参数为空，已阻止启动')        ✅
非字符串参数(int) -> LauncherError('启动命令第 [1] 项参数为空，已阻止启动')        ✅ 拦截有效，文案误导（问题3）
Java文件不存在    -> LauncherError('Java 可执行文件不存在：C:\nonexistent\javaw.exe') ✅
workdir不存在     -> LauncherError('游戏工作目录不存在：Z:\definitely\missing')   ✅
```

### G. 其他静态确认（无需运行）

- `jvm_extra` 空串/`shlex.split` 不产生空 token，无空串注入路径 ✅
- `_substitute` 未知占位符兜底为 `"0"`，已知空值仅 assetIndex 缺失（会被 F 类拦截，见问题 6）⚠
- `_on_fail` 弹窗引导：所有新增错误文案均含 "Java" 子串，"下载 Java"按钮引导可正常触发 ✅（回归通过）
- home_page 对失效 java_path 的预过滤 + workers 前置 resolve：手动有效路径行为不变 ✅（回归通过）
- 设置页 `_on_java_changed` 存空串 = "自动选择"，与修复前根因一致，现被 worker 侧兜住 ✅

---

## 五、回归风险评估小结

| 场景 | 修复前 | 修复后 | 判定 |
|---|---|---|---|
| config java_path 为空（WinError 87 根因） | 空串直入 Popen → WinError 87 | 自动选择按版本挑 Java；无 Java 时中文报错 | ✅ 修复 |
| config java_path 有效 | 直接使用 | 直接使用（isfile 双重校验） | ✅ 无回归 |
| config java_path 失效 | Popen 系统级报错 | home_page 预过滤转自动选择 / resolve 抛中文错误 | ✅ 改善 |
| 系统无任何 Java | WinError 87 或 JVM 报错 | "未找到可用的 Java 运行时" + Adoptium 引导弹窗 | ✅ 改善 |
| Fabric 官方 id（loader 版本在前） | 与 Java 选择无关（旧逻辑不选版本） | **可能选到过老 Java → 启动失败** | ⚠ 问题 1 |
| 残缺 json（空 mainClass/空参数） | JVM 端晦涩报错或 WinError | 中文"参数为空/命令为空"拦截 | ✅ 改善 |

**最终判定：有保留通过。** 建议合并前优先处理问题 1（derive_mc_version 优先采信 `1.x` 形态匹配），问题 2~5 可随后续迭代处理。
