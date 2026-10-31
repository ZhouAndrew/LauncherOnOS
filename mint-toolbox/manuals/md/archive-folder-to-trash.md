# archive-folder-to-trash — 文件夹打包后移入回收站

> 分类：文件与归档 · 状态：可用逻辑 / 待实机验收 · 风险：高 · 启动器：install

## 功能

将指定文件夹压缩为带时间戳的 `.tar.gz`，测试归档可读取，然后将源文件夹放入桌面回收站。

## 用法

```bash
archive-folder-to-trash "$HOME/Videos/OldFolder"
archive-folder-to-trash "$HOME/Videos/OldFolder" "$HOME/Archives"
```

## 参数与选项

- `FOLDER`（必需）：待归档的目录。
- `OUTPUT_DIR`（可选）：输出目录，默认源文件夹父目录。
- 没有 `--dry-run`、`--help`。

## 依赖与运行环境

- Bash、tar、realpath、date；优先 `gio trash`，否则 `trash-put`。

## 输出与副作用

- 输出 `${文件夹名}-${YYYYMMDD-HHMMSS}.tar.gz`。
- 打包成功后调用 gio/trash-put 将整个源目录移入回收站。

## 注意事项

- 这是移动目录的修改型脚本，不是仅创建备份；不要对重要目录盲目运行。
- 归档验证只调用 `tar -tzf` 验证可列出条目，不等同于与源目录逐字节比对。
- 命令执行前检查磁盘剩余空间及回收站可用性。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/archive-folder-to-trash`。
- 源文件 SHA-256：`5a45db7bebe43664fc67b6e976b3b43b3cabf274f09043a77911e600a1399e31`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

可作为 standalone 源码脚本由 `launcheronos install` 管理；执行前仍须确认系统依赖和硬编码路径。
