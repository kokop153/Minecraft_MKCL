# 下载模块自测报告（core_c：meta.py + download.py）

- 日期：2026-08-31
- Python：C:\Program Files\AutoClaw\resources\python\python.exe
- 命令：`& "C:\Program Files\AutoClaw\resources\python\python.exe" dev_reports\selftest_core_c.py`
- 退出码：0

## 结果汇总：PASS=6 FAIL=0 SKIP=0

```
[PASS] 1.manifest_bmclapi -- versions=908
[PASS] 2.download_file_gson -- size=279KB retries=0
[PASS] 3.collect_items_no_assets -- items=89 first3_fields_ok=True
[PASS] 4.collect_items_with_assets -- items=3682
[PASS] 5.download_manager -- ok=5 failed=0 progress_calls=5 (含 skip)
[PASS] 5b.cancel -- is_running=False
```

## 说明

1. **manifest**：bmclapi 清单端点 `https://bmclapi2.bangbang93.com/version_manifest/v2` 返回 404（首跑曾 SKIP）。meta.fetch_version_manifest 已加兼容备用路径 `/mc/game/version_manifest_v2.json`（镜像官方路径），修复后返回 908 个版本（≥500 通过）。
2. **download_file**：gson-2.10.jar（279KB > 100KB 阈值）经 bmclapi 镜像下载成功，0 重试，tmp+replace 原子落盘。
3. **collect_download_items(include_assets=False)**：F:\.minecraft 的 1.20.1 共 89 项（jar 1 + 库 88），前 3 项 url/dest 均非空。
4. **collect_download_items(include_assets=True)**：3682 项（含 assetIndex 索引 + ~3592 个 assets 对象，>1000 通过）。
5. **DownloadManager**：前 5 项并发下载（4 workers），done 回调 ok=5 failed=0（已存在的文件按 sha1 跳过），progress 被调 5 次；cancel() 后 is_running 最终 False。

## 集成注意（给主 Agent / 并行 Agent）

- `version_scan.scan_versions()` 返回 `VersionInfo` dataclass（属性访问），`resolve_version_chain(info)` 直接接收 VersionInfo、返回 merged dict——meta.py 已按此适配。
- `meta._rules_allow()` 是与 launch.py 一致的 rules 过滤副本（os=windows + 标准 features），若 launch.py 行为有变需同步。
- bmclapi 域名映射：piston-meta/piston-data/launcher.mojang.com → bmclapi/；libraries.minecraft.net → bmclapi/maven/；resources.download.minecraft.net → bmclapi/assets/。
