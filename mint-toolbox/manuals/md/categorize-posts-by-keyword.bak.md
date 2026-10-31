# categorize-posts-by-keyword.bak — 按关键词设置 WordPress 分类：旧备份

> 分类：WordPress · 状态：历史备份 / 禁止默认启动 · 风险：高 · 启动器：skip

## 功能

`categorize-posts-by-keyword` 的历史备份版本，仅为回溯与对照保留；包含相似的批量分类变更逻辑。

## 用法

```bash
（存档，不建议运行；使用 categorize-posts-by-keyword 的当前版本）
```

## 参数与选项

- 旧版也定义 `--dry-run`、`--yes`、`--title-only` 与关键词/分类参数；不保证与当前版一致。

## 依赖与运行环境

- WP-CLI、Python3、WordPress；参见当前版本手册。

## 输出与副作用

- 执行可能批量修改 WordPress 分类。

## 注意事项

- 它是 `.bak` 历史备份，不应该作为 LauncherOnOS 可安装/启动的正式工具。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/categorize-posts-by-keyword.bak`。
- 源文件 SHA-256：`2a2ffeccfeac65b9f74454a279fec8058f30a1ff4dc1986d65bce1ba2ec0f3c1`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

不建议安装、运行或默认在交互菜单中展示；仅保留手册供追溯。
