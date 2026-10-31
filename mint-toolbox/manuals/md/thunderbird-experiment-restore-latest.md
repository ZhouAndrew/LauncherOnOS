# thunderbird-experiment-restore-latest — 恢复最近的 Thunderbird 实验前备份

> 分类：CalDAV 与 Thunderbird · 状态：维护 / 恢复工具 · 风险：极高 · 启动器：register

## 功能

从最近一次 `-before-experiment` 备份恢复 Thunderbird TaskFix Profile，恢复前先将当前 Profile 再备份，并要求用户键入 YES。

## 用法

```bash
thunderbird-experiment-restore-latest
```

## 参数与选项

- 无命令行参数；交互确认必须键入 `YES`。

## 依赖与运行环境

- 使用 `/home/andrew/.local/share/thunderbird-taskfix/profile`。
- 读取 `/home/andrew/Thunderbird-Experiment-Backups` 中最近的实验前快照。

## 输出与副作用

- 关闭 Thunderbird 后运行；将当前 Profile 移至带时间戳的旧目录，再将备份副本替换为工作 Profile。
- 创建恢复前应急备份。

## 注意事项

- 会整体切换 Thunderbird Profile；重要邮件、日历或任务状态可能回退。
- 恢复完成后检查数据一致性，不要在 Thunderbird 仍运行时恢复。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/thunderbird-experiment-restore-latest`。
- 源文件 SHA-256：`e0f927f84ecdb3ef7fcb37c8522280904cda538d219a66db369c3b910bc6be08`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
