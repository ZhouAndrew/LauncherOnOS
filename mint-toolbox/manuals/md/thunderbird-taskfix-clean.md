# thunderbird-taskfix-clean — Thunderbird TaskFix Clean 启动器

> 分类：CalDAV 与 Thunderbird · 状态：独立测试入口 · 风险：中 · 启动器：register

## 功能

用 TaskFix Clean 版的独立程序和独立 Profile 启动 Thunderbird。

## 用法

```bash
thunderbird-taskfix-clean [Thunderbird 参数]
```

## 参数与选项

- 全部参数透传 Thunderbird；没有脚本级选项。

## 依赖与运行环境

- 固定程序 `/home/andrew/.local/opt/thunderbird-taskfix-clean-153.1.0/thunderbird`。
- 固定数据 `/home/andrew/.local/share/thunderbird-taskfix-clean/profile`。

## 输出与副作用

- 启动 Thunderbird；实际数据修改由外部程序完成。

## 注意事项

- 不同 Profile 之间的数据不会自动共享；不要误以为它能恢复旧数据。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/thunderbird-taskfix-clean`。
- 源文件 SHA-256：`26279a4cc4adf4624669d4a49313fe83f1f3f209550733fc833cb490eb0b1f0f`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
