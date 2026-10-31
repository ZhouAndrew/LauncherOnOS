# anki-flow-patched — Anki Flow 特制启动器

> 分类：Anki 与学习 · 状态：已弃用 / 仅存档 · 风险：低 · 启动器：skip

## 功能

在旧 Anki Flow 源码目录以 `ANKIDEV=0` 启动 `run`，透传所有参数。

## 用法

```bash
anki-flow-patched [原始启动器参数]
```

## 参数与选项

- 本脚本没有独立选项；所有参数原样传给目标 `run`。

## 依赖与运行环境

- 需要 `${XDG_DATA_HOME:-$HOME/.local/share}/anki-flow/backend/anki-26.08.1/run` 存在且可执行。
- 可选读取 `~/.cargo/env`。

## 输出与副作用

- 启动外部 Anki Flow 程序，本脚本自身不编辑 Anki 数据。

## 注意事项

- 属于已经放弃的 Anki Flow 旧项目，建议在 LauncherOnOS 中默认隐藏，而不是当作正常可安装工具。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/anki-flow-patched`。
- 源文件 SHA-256：`36d6220bc1230e2050520dfd12a6c04ef698ca2728506c86d5b10290754298d1`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

不建议安装、运行或默认在交互菜单中展示；仅保留手册供追溯。
