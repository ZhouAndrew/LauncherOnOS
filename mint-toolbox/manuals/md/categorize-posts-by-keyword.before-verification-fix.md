# categorize-posts-by-keyword.before-verification-fix — 按关键词设置 WordPress 分类：验证修复前快照

> 分类：WordPress · 状态：历史快照 / 禁止默认启动 · 风险：高 · 启动器：skip

## 功能

当前分类脚本在验证修复前的代码快照，供差异追溯，不是首选可执行版本。

## 用法

```bash
（存档，不建议运行；使用 categorize-posts-by-keyword）
```

## 参数与选项

- 沿用相近的关键词/分类参数和 --dry-run / --yes 等开关。

## 依赖与运行环境

- WP-CLI、Python3、WordPress。

## 输出与副作用

- 执行可能批量修改 WordPress 分类。

## 注意事项

- 名字表示“验证修复前”，不应被扫描器误识别为推荐工具。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/categorize-posts-by-keyword.before-verification-fix`。
- 源文件 SHA-256：`afc18e2c290d1d7ca8d9d016c99333d5d6e0a466e7764f2ec130005938569149`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

不建议安装、运行或默认在交互菜单中展示；仅保留手册供追溯。
