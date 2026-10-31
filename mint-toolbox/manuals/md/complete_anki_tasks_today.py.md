# complete_anki_tasks_today.py — 完成今日到期的 Anki CalDAV 任务

> 分类：CalDAV 与 Thunderbird · 状态：实用工具 / 待服务端验收 · 风险：高 · 启动器：register

## 功能

遍历指定 CalDAV 用户的 Calendar Collections，筛选指定日期到期、标题包含关键词且未完成的 VTODO，然后批量标为完成。

## 用法

```bash
python3 complete_anki_tasks_today.py --dry-run
python3 complete_anki_tasks_today.py --date 2026-10-24 --keyword Anki
CALDAV_USERNAME=andrew python3 complete_anki_tasks_today.py --dry-run
```

## 参数与选项

- `--username USER`：默认 `andrew`。
- `--timezone TZ`：默认 `Asia/Shanghai`。
- `--keyword TEXT`：标题包含指定文本，区分大小写；默认 `Anki`。
- `--date YYYY-MM-DD`：默认对应时区的今天。
- `--dry-run`：只预览任务，不执行完成操作。

## 依赖与运行环境

- CalDAV 地址在源码里固定为 `http://andrew.local:5232/andrew/`。
- 使用 `CALDAV_USERNAME` 和 `CALDAV_PASSWORD` 环境变量，未提供密码则交互询问。
- 首次启动会建立 `~/.local/share/complete-anki-tasks-today/venv`，通过 pip 安装 `caldav==3.2.1` 和 `tzdata`；需要 Python3 和网络。

## 输出与副作用

- 非预览模式会对所有匹配 VTODO 调用 CalDAV 完成动作（含安全处理重复规则参数）。
- 不逐个询问确认，也未实现逐项撤销。

## 注意事项

- 强烈建议先运行 `--dry-run`，避免大量任务误完成。
- CalDAV 连接使用 HTTP，若网络不可信，认证信息存在传输风险。
- 源码未显示执行修改后的独立 read-back 验证；不能将它视为已符合 Thunderbird 插件的验证冻结标准。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/complete_anki_tasks_today.py`。
- 源文件 SHA-256：`62579fa335109e3977905ff66d02be310d6b5e5ab54ef4f5d2f84b07b4ef8aae`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
