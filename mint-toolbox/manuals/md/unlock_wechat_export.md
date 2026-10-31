# unlock_wechat_export — 处理微信导出 HTML 的显示限制

> 分类：文件与归档 · 状态：敏感转换工具 · 风险：中 · 启动器：install

## 功能

批量处理 `conversations/*/messages.html`，移除脚本识别的完整性验证/隐藏元素，并生成同目录 `messages-unlocked.html`。

## 用法

```bash
unlock_wechat_export /absolute/path/to/export
unlock_wechat_export /absolute/path/to/export --overwrite
```

## 参数与选项

- `[root]`：导出目录，默认当前目录。
- `--overwrite`：覆盖已存在的 `messages-unlocked.html`。

## 依赖与运行环境

- Python3 标准库；输入目录须包含 `conversations/*/messages.html`。

## 输出与副作用

- 向各会话目录写入 `messages-unlocked.html`；不删除原始 `messages.html`。

## 注意事项

- 这是 HTML 内容转换，不代表真实性验证通过；移除完整性检查后不能再据此证明数据完整或可信。
- 仅处理有权访问的导出内容；原文件应保留作验证基准。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/unlock_wechat_export`。
- 源文件 SHA-256：`9001a32bcae434dfedd5c67f7a5147af02b22e7231456dba5a37178e0ae1550b`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

可作为 standalone 源码脚本由 `launcheronos install` 管理；执行前仍须确认系统依赖和硬编码路径。
