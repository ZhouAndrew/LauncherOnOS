# caldav-assistant-thunderbird-host-experimental — CalDAV Assistant Thunderbird 原生消息主机入口

> 分类：CalDAV 与 Thunderbird · 状态：实验入口 · 风险：中 · 启动器：register

## 功能

直接启动独立虚拟环境里的 Python `host/native_host.py`，供 Thunderbird 扩展的 Native Messaging 通信使用。

## 用法

```bash
（由 Thunderbird 的 Native Messaging 机制调用；不建议在普通终端中直接操作）
```

## 参数与选项

- 脚本不解析或转发参数。

## 依赖与运行环境

- 依赖固定路径 `/home/andrew/.local/share/caldav-assistant-thunderbird-experimental/venv/bin/python` 及 `host/native_host.py`。

## 输出与副作用

- 启动原生消息主机进程；具体数据行为取决于未随本文件提供的外部 `native_host.py`。

## 注意事项

- 这里只包含 2 行包装器，不能据此推断服务端能力或保证可独立运行。
- 此入口不应与普通命令行工具一样在菜单中直接启动。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/caldav-assistant-thunderbird-host-experimental`。
- 源文件 SHA-256：`72b51f24241eeca67cdf3e731e8e4bc6095a31591b75199a8a44f76ceed85d1b`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
