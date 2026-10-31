# andrew-lan-speed-test.sh — 局域网网速与网线测试

> 分类：网络与系统 · 状态：使用中 / 待实机验收 · 风险：中 · 启动器：register

## 功能

检查有线网卡的链路速率、双工模式、错误计数；通过 iperf3 测试双向 LAN 吞吐，并可运行网线物理诊断。

## 用法

```bash
andrew-lan-speed-test.sh --help
andrew-lan-speed-test.sh
andrew-lan-speed-test.sh 192.168.1.50
andrew-lan-speed-test.sh --server
andrew-lan-speed-test.sh --cable-test
```

## 参数与选项

- 不带参数：读取链路信息，并可交互输入对端 IP。
- `<IP>`：对指定 iperf3 服务端测试。
- `--server`：本机前台启动 iperf3 服务。
- `--cable-test`：ethtool 网线诊断（可能临时断网）。
- `-h`、`--help`：帮助。

## 依赖与运行环境

- Linux Mint/Ubuntu/Debian；`ip`、`ethtool`、`iperf3`、`ping`。
- 缺少 iproute2 / ethtool / iperf3 时脚本会通过 sudo apt 自动安装。
- 环境变量：`PORT=5201`、`DURATION=15`、`PARALLEL=4`。

## 输出与副作用

- 普通客户端模式主要读取网络状态并产生测试流量。
- `--server` 持续监听指定 TCP 端口，直到终止。
- `--cable-test` 可临时影响网络链路。

## 注意事项

- 不要在远程 SSH 会话执行网线诊断（脚本对此有保护）。
- 对端必须运行 iperf3 服务才能测吞吐；网速结果测的是整条路径。

## 来源与验证

- 来源：用户提供的 `bin.zip` 中的 `bin/andrew-lan-speed-test.sh`。
- 源文件 SHA-256：`259824d6c957e3a30be5f32e8d21ae15a719391d2a53d2571233f4700ff0b3ad`。
- 验证状态：**已静态读取代码；未运行脚本、未验证目标服务/依赖。**

## LauncherOnOS 集成建议

建议使用 `launcheronos register` 注册现有入口，不复制依赖环境或目标程序。
