# thunderbird-taskfix — Thunderbird TaskFix 独立启动器

> 分类：CalDAV 与 Thunderbird · 状态：安装环境专用入口 · 风险：中 · 启动器：register

## 功能

通过固定的 Thunderbird TaskFix 程序副本，默认使用独立 Profile 启动；支持切换到系统默认 Profile。

## 用法

```bash
thunderbird-taskfix
thunderbird-taskfix --system-profile
```

## 参数与选项

- `--system-profile`：不指定独立 Profile，使用 Thunderbird 正常 Profile。
- 其他参数透传 Thunderbird。

## 依赖与运行环境

- 固定程序 `/home/andrew/.local/opt/thunderbird-taskfix-153.1.0/thunderbird`。
- 独立数据 `/home/andrew/.local/share/thunderbird-taskfix/profile`。

## 输出与副作用

- 可以创建独立 Profile 目录、启动 Thunderbird；Thunderbird 本体可写入其 Profile。

## 注意事项

- 使用 `--system-profile` 前务必关闭正常 Thunderbird 实例，避免意外路由到其他进程。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/thunderbird-taskfix`。
- 源文件 SHA-256：`1936f1b748d0c72b674396a0a2dcbe445518e4b2e878c5f023d275199e8fefeb`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
