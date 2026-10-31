# create-subject-page.sh — 创建 WordPress 学科索引页面

> 分类：WordPress · 状态：当前版本 · 风险：高 · 启动器：install

## 功能

在 WordPress 指定父页面下，为一个或多个学科创建/更新同名标签和学科子页面，并插入按标签筛选的 Gutenberg Query Loop。

## 用法

```bash
create-subject-page.sh Physics
create-subject-page.sh English Math Physics Chemistry Biology
PARENT_TITLE="My Project" PER_PAGE=10 create-subject-page.sh Physics
```

## 参数与选项

- 参数为一个或多个学科名称（位置参数）。
- `WP_PATH`（默认 `/var/www/html/wordpress`）；`PARENT_TITLE`（默认 `My Project`）。
- `PER_PAGE`（默认 `10`）；`FORCE=1` 允许覆盖不属于该脚本管理的同名子页面。
- 脚本没有显式 `--help` 或 `--dry-run`。

## 依赖与运行环境

- WP-CLI 和可工作的 WordPress 安装。

## 输出与副作用

- 新建 WordPress 标签、发布子页面，或更新既有托管页面正文和元数据。
- 跳过其他位置的同名页面，以减少重复与错位。

## 注意事项

- `FORCE=1` 会改写已有页面的正文，应先备份。
- 无 dry-run；请先确认父页面、站点路径与学科名称。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/create-subject-page.sh`。
- 源文件 SHA-256：`5131abd128b9ace905648a864ee9c227aab89a8fb6fb96177429a014b346005c`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

可作为 standalone 源码脚本由 `launcheronos install` 管理；执行前仍须确认系统依赖和硬编码路径。
