# categorize-posts-by-keyword — 按关键词批量设置 WordPress 分类

> 分类：WordPress · 状态：当前版本 · 风险：高 · 启动器：install

## 功能

按不区分大小写的文字片段搜索文章标题、摘要、正文，预览匹配文章后追加指定分类；修改后再次读取确认。

## 用法

```bash
categorize-posts-by-keyword --dry-run "homework"
categorize-posts-by-keyword "homework" "学习任务"
categorize-posts-by-keyword --title-only --yes "think3" "think3"
```

## 参数与选项

- `<keyword>` 必需；`[category-name]` 可选，默认与关键词相同。
- `--dry-run`：只查询/预览。
- `--yes`：省略输入 YES 的交互确认。
- `--title-only`：只搜索文章标题。
- `-h`、`--help`：帮助。

## 依赖与运行环境

- WP-CLI `wp`、`python3`、可访问的 WordPress 站点。
- `WP_PATH` 默认 `/var/www/html/wordpress`；`POST_TYPE=post`；`POST_STATUS=any`。

## 输出与副作用

- 仅经确认或 `--yes` 后创建不存在的分类，并对匹配文章追加该分类。
- 最终逐篇读取 WordPress 分类，报告校验通过数量。

## 注意事项

- 匹配默认覆盖所有状态的文章（包括非公开状态），运行前优先 `--dry-run`。
- 无撤销功能；`--yes` 会直接修改多篇文章。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/categorize-posts-by-keyword`。
- 源文件 SHA-256：`d53e69ee06d6240183197b3ffd302e48c38caaa46263b337e7b9ecb12d7c945a`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

可作为 standalone 源码脚本由 `launcheronos install` 管理；执行前仍须确认系统依赖和硬编码路径。
