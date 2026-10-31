# Mint Toolbox v0.3.0 — Linux 实用工具集

本工具集按 **Microsoft PowerToys 的使用思路**整理多个独立脚本，但并非 Microsoft 产品，也不包含任何 PowerToys 代码。

**目标：** 用户先看到功能用途，再填写必要参数，随后调用原脚本。所有原有脚本及 CLI 参数均保留；不会偷偷改动业务逻辑。

新增 **系统扩展管理器**：通过安装/卸载随附 deb 启用和禁用系统功能。首个扩展为 Nemo 右键「压缩为 ZIP 并删除」。详见 [系统扩展说明](SYSTEM_PLUGINS.md)。

## 安装（Linux Mint / Ubuntu）

在解压目录内执行：

```bash
bash install.sh
```

安装完毕后，在应用菜单中搜索 **Mint 实用工具集**，也可输入 `mint-toolbox` 启动。

建议安装系统组件：

```bash
sudo apt install python3-tk zenity
```

- GUI 主界面：Python 标准库 `tkinter`，不需要 Electron / Web 服务。
- **文件和文件夹选择**：优先用 **Zenity GTK 系统文件选择器**；没有 Zenity 时用 Tk 自带文件选择器。
- 任务运行：打开系统终端显示进度、保留 sudo、交互提示、原脚本的终端行为。
- 手册：单击 **阅读图文手册**，在默认浏览器打开预生成的离线 HTML（由 Pandoc 在打包时转换）。不显示 Markdown 源码。
- 没有桌面环境：自动降级到 TUI，可用 `mint-toolbox --tui` 明确选择。

## 命令行模式（保留原能力）

```bash
mint-toolbox --list
mint-toolbox --info extract_pdf_images.py
mint-toolbox --manual extract_pdf_images.py
mint-toolbox --run extract_pdf_images.py ~/Documents/a.pdf --output ~/Pictures
```

原来的脚本也保存在 `~/.local/share/mint-toolbox/originals/`，可以单独运行。例如：

```bash
bash ~/.local/share/mint-toolbox/originals/andrew-lan-speed-test.sh --help
```

## 新增：分类、移除状态与用户扩展槽（v0.2）

- GUI 顶部有 **分类** 和 **状态** 两个筛选器，默认只看“可用”。可切换到“已移除”“已归档”“外部依赖”“文件缺失”，旧工具不再混在常用列表里。
- 现有 24 个原始入口保留：16 个列为日常可用、3 个依赖外部环境、4 个已归档、1 个（Anki Flow）已移除。**“可用”仅指入口可选，不代表实机验收通过。**
- 点击 **＋ 添加用户工具…**，用系统原生文件对话框选脚本，填写显示名称和分类，即可注册用户扩展；无需改源码。
- 支持“标记已移除 / 恢复”，以及只对用户扩展生效的“取消注册”。这些操作不会删除脚本。
- 用户扩展配置单独保存在 `~/.config/mint-toolbox/extensions/`，升级安装保留原配置；脚本仍从原位置运行。
- 扩展可选关联现有手册；也可以使用 JSON 清单声明多个图形操作、文件/目录字段和 CLI 参数。详见 [EXTENSIONS.md](EXTENSIONS.md)。

新增 CLI：

```bash
mint-toolbox --list --all
mint-toolbox --categories
mint-toolbox --extension-add ~/bin/my-tool.sh --name '我的工具' --category '用户扩展'
mint-toolbox --extensions
```

## 工具状态：禁用与移除分别保留（v0.2.1）

这两个状态**互不替代**：

| 操作 | 列表表现 | 能否运行 | 原脚本、手册与扩展配置 | 恢复方式 |
| --- | --- | --- | --- | --- |
| 禁用 | 转入“已禁用”，可搜索 | 不可运行 | 全部保留 | “启用工具” |
| 标记已移除 | 转入“已移除”，可搜索 | 不可运行 | 全部保留 | “恢复” |
| 取消注册（仅用户扩展） | 从目录移走 | 不可通过工具集运行 | 原脚本和独立手册保留；扩展注册清单删除 | 重新添加 |

“已移除”和“已禁用”可以**同时存在**。例如：先禁用，再标记已移除，恢复后仍然是禁用状态；必须另行启用才能运行。归档和外部依赖状态也不会因为“启用”而变成可用。

GUI 在同一工具的操作区同时保留“启用/禁用”和“标记已移除/恢复”；TUI 与 CLI 同样支持。查看手册不受状态限制。

```bash
mint-toolbox --disable extract_pdf_images.py
mint-toolbox --enable extract_pdf_images.py
mint-toolbox --mark-removed extract_pdf_images.py
mint-toolbox --restore extract_pdf_images.py
mint-toolbox --info extract_pdf_images.py
mint-toolbox --list --all
```

禁用信息独立保存至 `~/.config/mint-toolbox/disabled.json`；移除记录仍保存在 `~/.config/mint-toolbox/state.json`。升级时均保留。

## v0.2.2 — 筛选器保持不变、完整命令公开

- GUI 的 **分类、状态、搜索** 完全由用户控制。禁用／启用、标记已移除／恢复、添加用户扩展及取消注册时，程序**不会主动切换或重置筛选器**。
- 如果状态变更后选中工具不再符合当前筛选条件，该工具不会被强制插回左侧列表；右侧仍显示它的详情和可用的管理操作，并明确提示当前筛选条件未改变。不会突然跳选其他工具。
- GUI 右侧始终有 **实际命令（完整可复制）** 文本区和 **复制命令** 按钮。选择工具后显示真实执行入口；填写图形操作参数后显示包含所有已填写参数的最终命令。
- GUI 打开的终端会先打印执行命令。CLI 的 `--info` 展示原程序命令与 `mint-toolbox --run` 调用方式；`--run` 和 TUI 执行时也会显示完整命令。含空格路径和参数按 Shell 安全引号显示，实际执行继续直接传递参数列表，不使用 `shell=True`。
- 这两处仅修改**交互表现**，保留“禁用”和“移除”独立状态、风险确认、原生文件选择器、离线手册、脚本及其参数行为。

## 功能分组与限制

- **文件**：PDF 内嵌图片提取、文件夹归档到回收站。
- **网络**：LAN 链路与吞吐测试；网线诊断前会提醒断网风险。
- **WordPress**：关键词分类（提供真正 `--dry-run`）、学科页面生成、只读故障诊断、Anki 历史 PDF 回填。
- **微信导出**：解锁 HTML、预览导入、导入 WordPress。注意原导入脚本的 `--dry-run` 在缺少解锁 HTML 时可能先生成文件。
- **CalDAV / Thunderbird**：Anki 任务预览与完成、独立 Thunderbird 启动和实验备份恢复。
- **开发工具 / 外部程序**：仅提供说明和原 CLI，不给无法验证的第三方组件虚构图形参数。
- 历史备份、已废弃的 Anki Flow 和 Native Messaging 主机保留在包中；可用状态筛选查看其资料，但不提供普通图形启动操作。

## 安全与兼容

- 本包的原始脚本来自用户提供的 `bin.zip`，每个文件和原手册 SHA-256 核对相符，**未在此环境执行这些个人脚本**。
- 危险数据修改在 GUI 中要求键入“执行”；原脚本可能再次要求确认。
- 打开界面、搜索、看说明 **不会执行原脚本**。
- 部分脚本绑定原机器安装路径 `/home/andrew`、WordPress、CalDAV、Thunderbird 等环境；独立入口的实际主体和 Python venv 不包含在包中。
- 大型 `.extract_pdf_images_venv` 属于机器相关依赖，未重复打包；原 `extract_pdf_images.py` 会按自己的原有逻辑尝试准备运行环境（可能安装 PyMuPDF）。
- `--run` 直接传递参数并保留原脚本行为；请不要对不信任来源的脚本执行。
- **没有在你的 Linux Mint 真机完成 GUI、GTK、系统服务与数据修改验收**，因此这是可安装并经过自动化逻辑测试的整合版本，不是已实机验收的正式版。

## 开发者检查

```bash
python3 -m unittest discover -s tests -v
```

源码设计：一个工具入口 `toolbox.py`，独立扩展清单加载器 `extensions.py`，一个描述索引 `catalog.json`，原脚本存储在 `originals/`，手册在 `manuals/md/` 与 `manuals/html/`。不需要脚本自己重复实现菜单。
