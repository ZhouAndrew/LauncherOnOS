# Mint Toolbox v0.2：分类与用户扩展

**日常使用不需要编辑 JSON。** 在 Mint Toolbox GUI 中点击 **＋ 添加用户工具…**，使用 Linux Mint 的文件选择器选取脚本或可执行程序，再填写名称、分类和用途。可选取已有 HTML/Markdown 手册。工具立刻出现在相应分类下。

注册扩展时只保存指向原工具的路径，**不复制、不修改、也不执行原脚本**。真正点击“启动工具”后才运行。用户应确保脚本来源可信。

## 分类和状态是两件事

- **分类**：例如“文件与归档”“WordPress”“网络与系统”“用户扩展”。用户增加的工具可以使用任何分类名称。
- **可用**：展示在默认列表；这里只表示程序入口文件存在、未被主动隐藏，并不意味着在实际机器上执行验收过。
- **外部依赖**：只打包了 pipx/虚拟环境等入口，程序主体可能不在工具包内；默认不显示在日常操作中。
- **已归档**：历史备份、旧快照或内部入口；默认不显示、不可从图形按钮运行。
- **已移除**：用户标记下架或已弃用的工具；保留名称和手册，可以在状态筛选中查到并恢复，但不能直接运行。
- **文件缺失**：注册的脚本或可执行文件已经不在原路径；保留说明供排查，但不允许执行。

“标记已移除”和“恢复”只修改 Mint Toolbox 的用户状态；它们**不会删除原脚本或手册**。“取消注册”只适用于用户扩展，删除扩展清单，保留源文件。

## 本地扩展槽

自动创建的位置：

```text
~/.config/mint-toolbox/
├── extensions/
│   ├── user-tool-1234567890.json
│   └── user-other-9876543210.json
└── state.json
```

实际目录遵循 `XDG_CONFIG_HOME`。程序升级和重新安装不会覆盖该目录。清单只包含声明式信息；发现扩展时不导入或执行用户代码。错误清单被单独跳过，其他工具照常使用。命令 `mint-toolbox --extensions` 可查看加载问题。

### 进阶：声明式操作

需要多个图形按钮、文件选择和参数输入时，可将 `examples/user-example.json.example` 复制为上述扩展目录下的 `user-example.json`，修改 `executable` 为**绝对路径**，并使文件中的 `id` 与文件名一致。

支持字段类型：`text`、`file`、`folder`、`file_or_folder` 和 `boolean`。`argv` 使用固定字符串或引用字段的对象，例如：

```json
{"field": "source", "flag": "--input"}
```

此项会把用户选择的路径作为 **一个独立参数**传入程序，而不是拼接 Shell 命令。未填写的可选字段连同 `flag` 一起跳过。布尔字段为真时才附加其 `flag`。最多支持 20 个操作、每个操作 15 个字段。

图形手册优先使用用户指定的 `.html`；若指定 `.md` 且安装了 Pandoc，会生成本地 HTML，未安装时显示自动生成的工具概要。终端优先调用 Glow 阅读 Markdown。

## CLI（不会替换已有原脚本参数）

```bash
mint-toolbox --categories
mint-toolbox --list                  # 默认仅可用
mint-toolbox --list --all            # 包含历史/已移除/外部依赖
mint-toolbox --extension-add ~/bin/my-tool.sh --name '我的工具' --category '用户扩展'
mint-toolbox --extensions
mint-toolbox --mark-removed user-my-tool-xxxxxxxxxx
mint-toolbox --restore user-my-tool-xxxxxxxxxx
mint-toolbox --extension-remove user-my-tool-xxxxxxxxxx
mint-toolbox --run user-my-tool-xxxxxxxxxx --help
```

上面的 `xxxxxxxxxx` 代表注册后打印的真实工具 ID。`--run TOOL ...` 继续将剩余参数原样传递给原工具。

## 限制与安全

- 这是本地用户扩展机制，不是下载市场、系统包管理器或依赖自动安装工具。
- 注册不保证脚本的解释器、外部虚拟环境或系统依赖可用。
- 无需 sudo 创建/移除注册。原脚本运行时可能自行要求权限。
- 不能仅因扩展清单存在就自动执行其代码；运行仍需用户明确操作。
- 内置旧脚本保持原样。需要修改业务逻辑，应独立升级原工具。
- 本地用户扩展清单不会上传到 GitHub，也不随工具包分发。
