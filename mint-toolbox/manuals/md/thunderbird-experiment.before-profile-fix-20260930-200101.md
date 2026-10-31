# thunderbird-experiment.before-profile-fix-20260930-200101 — Thunderbird 实验启动器：旧 Profile 修复前快照

> 分类：CalDAV 与 Thunderbird · 状态：历史快照 / 禁止默认启动 · 风险：极高 · 启动器：skip

## 功能

2026-09-30 的旧实验启动脚本，仍指向当时的 `~/.thunderbird/4vs0bf41.default-esr-1` Profile。

## 用法

```bash
（历史参考，禁止默认运行）
```

## 参数与选项

- 任何参数原样透传给当时的 Thunderbird 实验程序。

## 依赖与运行环境

- 固定旧版程序和旧 Profile 路径。

## 输出与副作用

- 启动前备份旧 Profile，自动删除最早的多余实验备份以只保留最近 7 份，然后启动 Thunderbird。

## 注意事项

- 包含备份清理的 `rm -rf`；与现行实验版路径不同，不能作为当前恢复流程使用。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/thunderbird-experiment.before-profile-fix-20260930-200101`。
- 源文件 SHA-256：`8f4e95f8d65732ec261c0ea917f6b9d12d2aa8e69dc73d1a6322104705809cc9`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

不建议安装、运行或默认在交互菜单中展示；仅保留手册供追溯。
