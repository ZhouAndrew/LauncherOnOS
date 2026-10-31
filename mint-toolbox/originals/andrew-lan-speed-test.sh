#!/usr/bin/env bash
# andrew-lan-speed-test.sh
# Linux Mint / Ubuntu / Debian: Ethernet link + LAN throughput tester
# Usage:
#   ./andrew-lan-speed-test.sh
#   ./andrew-lan-speed-test.sh 192.168.1.50
#   ./andrew-lan-speed-test.sh --server
#   ./andrew-lan-speed-test.sh --cable-test

set -u

PORT="${PORT:-5201}"
DURATION="${DURATION:-15}"
PARALLEL="${PARALLEL:-4}"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
good() { printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!!]\033[0m %s\n' "$*"; }
bad()  { printf '\033[1;31m[XX]\033[0m %s\n' "$*"; }

usage() {
  cat <<'EOF'
用法：
  ./andrew-lan-speed-test.sh
      自动检测有线网卡；可交互输入另一台运行 iperf3 server 的设备 IP。

  ./andrew-lan-speed-test.sh 192.168.1.50
      直接测试到指定设备。

  ./andrew-lan-speed-test.sh --server
      把本机作为 iperf3 server（前台运行，Ctrl+C 停止）。

  ./andrew-lan-speed-test.sh --cable-test
      运行 ethtool 网线诊断。
      注意：这个测试可能暂时断开网络，不要在 SSH 会话中使用。

可选环境变量：
  PORT=5201 DURATION=15 PARALLEL=4 ./andrew-lan-speed-test.sh 192.168.1.50
EOF
}

MODE="client"
PEER=""

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  --server)
    MODE="server"
    ;;
  --cable-test)
    MODE="cable"
    ;;
  "")
    ;;
  *)
    PEER="$1"
    ;;
esac

# ---- Install dependencies ----------------------------------------------------
missing=()
command -v ethtool >/dev/null 2>&1 || missing+=(ethtool)
command -v iperf3  >/dev/null 2>&1 || missing+=(iperf3)
command -v ip      >/dev/null 2>&1 || missing+=(iproute2)

if ((${#missing[@]})); then
  say "缺少组件，自动安装：${missing[*]}"
  sudo -v || exit 1
  sudo apt-get update || exit 1
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}" || exit 1
else
  good "所需组件已安装：ethtool / iperf3 / iproute2"
fi

# ---- Detect wired interface -------------------------------------------------
detect_iface() {
  local dev

  # Prefer interface used by default route, if it is an Ethernet device.
  dev="$(ip route show default 2>/dev/null | awk '/default/ {print $5; exit}')"
  if [[ -n "${dev:-}" && -d "/sys/class/net/$dev" && -e "/sys/class/net/$dev/device" && ! -d "/sys/class/net/$dev/wireless" ]]; then
    if ethtool "$dev" >/dev/null 2>&1; then
      printf '%s\n' "$dev"
      return 0
    fi
  fi

  # Otherwise choose the first non-loopback interface understood by ethtool.
  for dev in /sys/class/net/*; do
    dev="${dev##*/}"
    [[ "$dev" == "lo" ]] && continue
    [[ -e "/sys/class/net/$dev/device" ]] || continue
    [[ -d "/sys/class/net/$dev/wireless" ]] && continue
    if ethtool "$dev" >/dev/null 2>&1; then
      printf '%s\n' "$dev"
      return 0
    fi
  done
  return 1
}

IFACE="$(detect_iface)" || {
  bad "没有找到可测试的有线网卡。"
  exit 1
}

say "检测到有线网卡：$IFACE"

IP4="$(ip -4 -o addr show dev "$IFACE" scope global 2>/dev/null | awk '{print $4}' | head -n1 || true)"
DRIVER="$(ethtool -i "$IFACE" 2>/dev/null | awk -F': ' '/^driver:/ {print $2}' || true)"
SPEED="$(ethtool "$IFACE" 2>/dev/null | awk -F': ' '/^[[:space:]]*Speed:/ {print $2}' || true)"
DUPLEX="$(ethtool "$IFACE" 2>/dev/null | awk -F': ' '/^[[:space:]]*Duplex:/ {print $2}' || true)"
AUTONEG="$(ethtool "$IFACE" 2>/dev/null | awk -F': ' '/^[[:space:]]*Auto-negotiation:/ {print $2}' || true)"
LINK="$(ethtool "$IFACE" 2>/dev/null | awk -F': ' '/^[[:space:]]*Link detected:/ {print $2}' || true)"

printf '  IPv4            : %s\n' "${IP4:-无}"
printf '  Driver          : %s\n' "${DRIVER:-未知}"
printf '  Speed           : %s\n' "${SPEED:-未知}"
printf '  Duplex          : %s\n' "${DUPLEX:-未知}"
printf '  Auto-negotiation: %s\n' "${AUTONEG:-未知}"
printf '  Link detected   : %s\n' "${LINK:-未知}"

if [[ "$LINK" != "yes" ]]; then
  bad "没有检测到物理链路。检查网线、路由器/交换机端口和水晶头。"
  exit 2
fi

case "$SPEED" in
  1000Mb/s|2500Mb/s|5000Mb/s|10000Mb/s)
    good "链路已协商到 $SPEED"
    ;;
  100Mb/s)
    warn "链路只有 100 Mb/s。若两端都是千兆设备，这通常值得重点检查网线/水晶头/端口。"
    ;;
  10Mb/s)
    warn "链路只有 10 Mb/s，明显异常。"
    ;;
  *)
    warn "无法自动判断当前协商速率：${SPEED:-未知}"
    ;;
esac

[[ "$DUPLEX" == "Full" ]] || warn "当前不是 Full Duplex：${DUPLEX:-未知}"

# ---- Optional cable diagnostic ---------------------------------------------
if [[ "$MODE" == "cable" ]]; then
  say "准备运行网线物理诊断"
  if [[ -n "${SSH_CONNECTION:-}" || -n "${SSH_TTY:-}" ]]; then
    bad "检测到当前是 SSH 会话。网线诊断可能导致链路暂时中断，因此已取消。"
    exit 3
  fi

  warn "ethtool --cable-test 可能让链路短暂掉线。"
  read -r -p "确认在本机终端运行？输入 YES 继续: " ans
  [[ "$ans" == "YES" ]] || { echo "已取消。"; exit 0; }

  if sudo ethtool --cable-test "$IFACE"; then
    echo
    sudo ethtool --cable-test-tdr "$IFACE" 2>/dev/null || true
  else
    warn "该网卡/驱动可能不支持 ethtool cable-test。"
  fi
  exit 0
fi

# ---- Error counters ---------------------------------------------------------
read_counter() {
  local name="$1"
  cat "/sys/class/net/$IFACE/statistics/$name" 2>/dev/null || echo 0
}

RXE0="$(read_counter rx_errors)"
TXE0="$(read_counter tx_errors)"
RXD0="$(read_counter rx_dropped)"
TXD0="$(read_counter tx_dropped)"

# ---- Server mode ------------------------------------------------------------
if [[ "$MODE" == "server" ]]; then
  say "启动 iperf3 server"
  echo "本机地址：${IP4:-请用 ip addr 查看}"
  echo "端口：$PORT"
  echo
  echo "如果 UFW 阻止访问，可仅对局域网放行 TCP/$PORT。"
  echo "保持这个窗口开启，在另一台设备运行："
  echo "  iperf3 -c <andrew的IP> -P $PARALLEL -t $DURATION"
  echo
  exec iperf3 -s -p "$PORT"
fi

# ---- Client mode ------------------------------------------------------------
if [[ -z "$PEER" ]]; then
  echo
  read -r -p "另一台运行 iperf3 server 的设备 IP（留空则只检查链路）: " PEER
fi

if [[ -z "$PEER" ]]; then
  say "完成链路检查"
  echo "要测真实吞吐，需要另一台设备运行："
  echo "  iperf3 -s"
  echo
  echo "然后重新运行："
  echo "  $0 <对方IP>"
  exit 0
fi

say "检查对端：$PEER"
if ping -c 3 -W 1 "$PEER"; then
  good "对端可达"
else
  warn "Ping 没有响应；可能是防火墙禁 Ping。继续尝试 iperf3。"
fi

say "TCP 正向吞吐：andrew -> $PEER"
if ! iperf3 -c "$PEER" -p "$PORT" -P "$PARALLEL" -t "$DURATION" -O 2; then
  bad "无法连接 iperf3 server。"
  echo
  echo "请先在对方设备运行："
  echo "  iperf3 -s -p $PORT"
  echo
  echo "Windows 若被防火墙询问，请允许“专用网络”。"
  exit 4
fi

say "TCP 反向吞吐：$PEER -> andrew"
iperf3 -c "$PEER" -p "$PORT" -P "$PARALLEL" -t "$DURATION" -O 2 -R || \
  warn "反向测试失败，但正向结果仍有效。"

# ---- Error counters after test ---------------------------------------------
RXE1="$(read_counter rx_errors)"
TXE1="$(read_counter tx_errors)"
RXD1="$(read_counter rx_dropped)"
TXD1="$(read_counter tx_dropped)"

say "测试期间接口错误计数变化"
printf '  RX errors : %d -> %d  (增加 %d)\n' "$RXE0" "$RXE1" "$((RXE1-RXE0))"
printf '  TX errors : %d -> %d  (增加 %d)\n' "$TXE0" "$TXE1" "$((TXE1-TXE0))"
printf '  RX dropped: %d -> %d  (增加 %d)\n' "$RXD0" "$RXD1" "$((RXD1-RXD0))"
printf '  TX dropped: %d -> %d  (增加 %d)\n' "$TXD0" "$TXD1" "$((TXD1-TXD0))"

say "如何判断"
cat <<'EOF'
如果链路是 1000 Mb/s：
  • TCP 实测约 900–950 Mb/s：通常非常正常。
  • 只有约 90–95 Mb/s，同时 Speed=100Mb/s：链路只协商到百兆。
  • Speed=1000Mb/s，但吞吐明显偏低：还要排查对端、交换机/路由器、CPU、驱动等，
    不能只根据 iperf3 断定是网线问题。
  • RX/TX errors 在测试过程中持续增加：值得检查网线、水晶头和网口。

注意：
  iperf3 测的是 andrew 到对端之间的整条路径。
  若要尽量单独验证“这根新网线”，应让中间路径尽可能简单，并确保对端也是千兆或更快的有线设备。
EOF
