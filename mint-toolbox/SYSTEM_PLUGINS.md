# Mint Toolbox 系统扩展（v0.3.0）

打开主窗口的「系统扩展…」，或运行 `mint-toolbox --plugins`。
启用会通过系统授权安装随附 deb，禁用会卸载对应包。取消授权不改变开关状态。
界面读取 dpkg 状态，不使用独立的布尔开关伪装已安装。未配置完成的包会显示异常状态。
现有「用户工具」登记及禁用功能保持独立。

```bash
mint-toolbox --plugin-list
mint-toolbox --plugin-enable zip-trash
mint-toolbox --plugin-disable zip-trash
```

管理员授权使用 pkexec；需要 apt-get、dpkg-query 和 dpkg-deb。
安装依赖时可能需要联网。随附 deb 的 SHA-256、包名、版本和架构会在安装前核对。
卸载只指定扩展包，不执行 autoremove；系统安装的依赖会保留。
扩展属于系统级功能，安装/卸载影响所有用户。

## 第一个扩展：压缩为 ZIP 并删除

适用：Linux Mint Cinnamon 的 Nemo。通过 Nemo 原生 action 接口提供右键菜单，
文件和文件夹可同目录多选，仅支持本地文件。
Nemo 官方格式参考：https://github.com/linuxmint/nemo/blob/master/files/usr/share/nemo/actions/sample.nemo_action

1. 右键选择「压缩为 ZIP 并删除」，确认后开始压缩。
2. 调用系统 zip 在原目录生成临时 ZIP，调用 unzip 检验。
3. 逐项比较 ZIP 内容的 SHA-256 与原文件，检查原文件是否变化。
4. 同目录发布 ZIP，不覆盖已有名称；重名自动追加编号。
5. 通过 `gio trash` 将原文件移入系统回收站，可由文件管理器恢复。

单选输出 `<原名称>.zip`；多选输出 `Archive.zip`。
不调用永久删除命令。压缩或校验失败时保留原文件；回收站不支持或部分失败时保留 ZIP，报告错误。
符号链接、设备、套接字等特殊文件暂不支持，遇到时整体拒绝。
ZIP 不保留全部 Linux ACL/扩展属性；不要用它替代系统备份。
检测能发现常见的处理中修改，但不能锁住其他程序；压缩时请暂停编辑选中文件。

扩展依赖由 deb 声明：Python 3.10+、zip、unzip、GIO、Zenity、Nemo。
通常新开 Nemo 窗口即可看到菜单；未刷新时注销再登录。
不要以 root 身份启动整个工具箱；仅安装/卸载时需要系统授权。

## 构建与验证

```bash
python3 packaging/build.py
python3 -m unittest discover -s tests -v
```

构建脚本更新 `debs/` 与 `system-plugins.json`，扩展包没有维护脚本。
新增扩展：在 packaging 中添加打包内容，生成独立 deb，在清单加入唯一 ID、
包名、版本、deb 相对路径及 SHA-256。管理器共享安装、卸载和状态回读机制。
只随附经审核的扩展包，不将用户工具清单视为系统安装指令。

本次容器验证：48 项测试，46 通过、2 跳过（图形环境、真实 GIO 缺失）；
真实 zip/unzip 内容验证通过，隔离 dpkg 根目录安装/状态读取/卸载通过。
隔离根目录没有依赖数据库，包生命周期检查使用 --force-depends，仅用于测试包文件落盘与移除；
正式管理器使用 apt 安装依赖，不使用该参数。
尚未完成 Linux Mint 桌面中的 pkexec 授权和 Nemo 菜单实机验收。
