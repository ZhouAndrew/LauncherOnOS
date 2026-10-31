# wordpress_diagnose_today.sh — WordPress 今日故障只读诊断

> 分类：WordPress · 状态：当前版本 · 风险：中 · 启动器：register

## 功能

收集系统日志、WordPress/Apache/PHP/MySQL/Redis 状态、修改时间窗口内的文件信息以及 HTTP 测试结果，并保存到文本诊断报告。

## 用法

```bash
bash wordpress_diagnose_today.sh --help
bash wordpress_diagnose_today.sh
bash wordpress_diagnose_today.sh --since "2026-10-24 06:00:00" --until "2026-10-24 10:30:00"
```

## 参数与选项

- `--wp-path PATH`：WordPress 根目录，默认 `/var/www/html/wordpress`。
- `--web-user USER`：默认 `www-data`。
- `--since DATETIME`：默认今天 00:00。
- `--until DATETIME`：默认今天 12:00。
- `--output-dir DIR`：默认用户桌面，不可写时改用 `/tmp`。
- `-h`、`--help`：帮助。

## 依赖与运行环境

- 需要 Linux、sudo、WP-CLI、systemd/journalctl 和多种诊断工具。
- 有固定针对 Apache2、MySQL、PHP、Redis 的检查项。

## 输出与副作用

- 通常只读扫描和查询，不主动修复或更改 WordPress 内容。
- 会写 `wordpress_diagnose_YYYYMMDD_HHMMSS.txt` 报告，并读取系统日志。
- 部分 `wp check-update`/校验命令可能访问网络或触发缓存/状态读取，不能等同“完全零副作用”。

## 注意事项

- 诊断报告可能包含域名、内部路径、IP、请求日志与环境信息；发送给他人前先脱敏。
- 需要 sudo 权限，注意报告的本地访问权限。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/wordpress_diagnose_today.sh`。
- 源文件 SHA-256：`e822a137054abce10207abb159a2f981f230e3e775f1c63e136441855c4c7f0a`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
