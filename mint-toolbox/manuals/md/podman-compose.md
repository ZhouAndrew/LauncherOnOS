# podman-compose — Podman Compose pipx 入口

> 分类：容器与开发 · 状态：外部程序入口 · 风险：取决于参数 · 启动器：register

## 功能

将 CLI 参数交给 pipx 虚拟环境中的 `podman_compose.main`，用于 Podman Compose 项目操作。

## 用法

```bash
podman-compose --help
podman-compose [podman-compose 的子命令及参数]
```

## 参数与选项

- 无自定义选项；所有参数由已安装的第三方 podman-compose 解释。

## 依赖与运行环境

- shebang 固定为 `/home/andrew/.local/share/pipx/venvs/podman-compose/bin/python`，必须在对应系统上有效。
- 需要 pipx 安装的 podman-compose 及其容器运行环境。

## 输出与副作用

- 取决于传入的第三方子命令，可能创建、启动、停止或删除容器。

## 注意事项

- 这是 pipx 自动生成的第三方 entry point，不能视为可单独复制安装的脚本；使用 `register`。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/podman-compose`。
- 源文件 SHA-256：`f6b91f50ef2c54264d3a68588f3e76abe37024f67ec144da6a293e98c09f8dd4`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
