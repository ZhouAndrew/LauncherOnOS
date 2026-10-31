# import_wechat_export — 将微信聊天导出内容导入 WordPress

> 分类：WordPress · 状态：实用工具 / 高风险 · 风险：高 · 启动器：register

## 功能

将 WeChatDataAnalysis 的会话导出目录同步到 WordPress uploads，并为每个 `messages-unlocked.html` 创建或更新一篇文章，内嵌 HTML 聊天记录。

## 用法

```bash
import_wechat_export /absolute/path/to/export --dry-run
import_wechat_export /absolute/path/to/export
```

## 参数与选项

- `[export_dir]`：导出根目录，默认当前目录，要求包含 `conversations/`。
- `--dry-run`：不执行 rsync 复制与 WordPress 修改。

## 依赖与运行环境

- WordPress 根目录在源码中固定为 `/var/www/html/wordpress`。
- 需要 `wp`、`sudo`/`runuser`、`rsync`，WordPress 用户 `www-data`；可能依赖 `unlock_wechat_export` 命令。

## 输出与副作用

- 正常模式通过 `rsync -a --delete` 同步数据到 `wp-content/uploads/wechat-archive/<导出目录名>`：目标中多余文件可能被删除。
- 创建或更新 WordPress `post`（不创建 `page`），更新元数据并刷新缓存。
- **重要：即使 `--dry-run`，如果缺少解锁后的 HTML，脚本仍可能先自动调用 `unlock_wechat_export`，从而生成 `messages-unlocked.html`。

## 注意事项

- 涉及聊天隐私与公开网页权限，使用前确认站点访问控制。
- 删除同步目标的风险来自 `rsync --delete`，务必备份上传目录。
- `--dry-run` 不是全程零写入保证，应先在副本导出目录中试验。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/import_wechat_export`。
- 源文件 SHA-256：`99c2e4cb2afd3aefdc05ab6358f482eaef3a6be706e44272fec0c74554474dd2`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
