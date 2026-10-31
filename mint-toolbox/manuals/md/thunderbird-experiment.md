# thunderbird-experiment — Thunderbird 实验版：备份后启动

> 分类：CalDAV 与 Thunderbird · 状态：实验入口 · 风险：高 · 启动器：register

## 功能

检查是否有 Thunderbird 进程在运行；将实验用 TaskFix Profile 完整备份后，再用独立的 Thunderbird 实验版启动。

## 用法

```bash
thunderbird-experiment
```

## 参数与选项

- 额外参数原样传给 Thunderbird 实验版。

## 依赖与运行环境

- 固定程序路径 `/home/andrew/.local/opt/thunderbird-experiment-153.1.0/thunderbird`。
- 固定 Profile `/home/andrew/.local/share/thunderbird-taskfix/profile`。
- 备份目录 `/home/andrew/Thunderbird-Experiment-Backups`。

## 输出与副作用

- 每次启动前复制完整 Profile 到带时间戳的备份目录。
- 使用与工作 TaskFix 版本相同的 Profile 启动实验 Thunderbird。

## 注意事项

- 程序副本虽然独立，但数据 Profile 是共享的；禁止与其他 Thunderbird 同时运行。
- 不要把它误解为独立实验数据目录。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/thunderbird-experiment`。
- 源文件 SHA-256：`64221c35edda6d5171de65c0945c7113a68e76df467b6db8d1cf8415e42a1b4c`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
