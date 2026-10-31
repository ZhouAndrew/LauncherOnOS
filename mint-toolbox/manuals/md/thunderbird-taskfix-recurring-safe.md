# thunderbird-taskfix-recurring-safe — Thunderbird TaskFix Recurring Safe 启动器

> 分类：CalDAV 与 Thunderbird · 状态：独立测试入口 · 风险：中 · 启动器：register

## 功能

用 Recurring Safe TaskFix 程序与独立 Profile 启动 Thunderbird，也可显式选择系统 Profile。

## 用法

```bash
thunderbird-taskfix-recurring-safe
thunderbird-taskfix-recurring-safe --system-profile
```

## 参数与选项

- `--system-profile`：不指定独立 Profile；其余参数原样传递 Thunderbird。

## 依赖与运行环境

- 固定程序 `/home/andrew/.local/opt/thunderbird-taskfix-recurring-safe-153.1.0/thunderbird`。
- 固定数据 `/home/andrew/.local/share/thunderbird-taskfix-recurring-safe/profile`。

## 输出与副作用

- 启动 Thunderbird；数据修改依赖使用的 Profile。

## 注意事项

- 尽量保持独立 Profile；使用系统 Profile 时先关闭其他 Thunderbird 实例。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/thunderbird-taskfix-recurring-safe`。
- 源文件 SHA-256：`2fd0d0880895d24bf146d03395e195c1fd0e4651ba38d932fd3960487cc7591e`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
