# web2menu — 把网站添加到 Cinnamon 应用菜单

> 分类：桌面与启动器 · 状态：当前版本 · 风险：中 · 启动器：install

## 功能

获取网页标题与 favicon，为指定 URL 生成 Linux Mint / Cinnamon `.desktop` 菜单项。

## 用法

```bash
web2menu https://example.org
web2menu https://example.org --name "Example Site"
web2menu
```

## 参数与选项

- `[url]`：网页地址，未提供时交互输入。
- `--name NAME`：自定义启动项名称。

## 依赖与运行环境

- Python3 标准库，`xdg-open`；需要网络才能获得站点元数据和图标（失败时会降级）。
- 生成用户级 `.desktop` 文件与网页图标；可选调用 `update-desktop-database`。

## 输出与副作用

- 写入用户的 `~/.local/share/applications` 及 `~/.local/share/icons/web-apps` 等路径。
- 菜单项通过 `xdg-open` 使用默认浏览器打开网址。

## 注意事项

- 会对输入地址发起网络请求；只使用可信的 URL。
- 它不是安装网站软件，只是创建应用菜单快捷入口。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/web2menu`。
- 源文件 SHA-256：`67d1da82ee503c610cd473c0f71653ae57aafe07d7a8a0d085fc32f2a7f6e708`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

可作为 standalone 源码脚本由 `launcheronos install` 管理；执行前仍须确认系统依赖和硬编码路径。
