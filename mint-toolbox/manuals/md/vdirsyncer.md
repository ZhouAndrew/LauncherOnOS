# vdirsyncer — vdirsyncer pipx 入口

> 分类：CalDAV 与 Thunderbird · 状态：外部程序入口 · 风险：取决于参数 · 启动器：register

## 功能

调用 pipx 环境中的第三方 `vdirsyncer.cli.app`，用于日历/联系人等同步流程。

## 用法

```bash
vdirsyncer --help
vdirsyncer [第三方子命令及参数]
```

## 参数与选项

- 本脚本不解析选项；详情取决于已安装的 vdirsyncer 版本。

## 依赖与运行环境

- 固定解释器 `/home/andrew/.local/share/pipx/venvs/vdirsyncer/bin/python`。
- 需 pipx 安装的 vdirsyncer 及其独立配置。

## 输出与副作用

- 具体同步命令可能修改本地或远端数据，单靠此入口不能确认。

## 注意事项

- pipx 入口，不可独立复制安装，适合 `register`。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/vdirsyncer`。
- 源文件 SHA-256：`d6e2387c1f1373c6ba26426207c9fa0a9b3e6cdae38bc94c1b7e9748c1f3afae`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
