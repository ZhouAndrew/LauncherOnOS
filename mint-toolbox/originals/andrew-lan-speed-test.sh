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
Usage:
  ./andrew-lan-speed-test.sh
      Detect a wired adapter and optionally enter the IP of an iperf3 server.

  ./andrew-lan-speed-test.sh 192.168.1.50
      Test connectivity to the specified device.

  ./andrew-lan-speed-test.sh --server
      Run a foreground iperf3 server (Ctrl+C to stop).

  ./andrew-lan-speed-test.sh --cable-test
      Run ethtool cable diagnostics.
      Warning: this test may interrupt connectivity. Do not use over SSH.

Optional environment variables:
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
  say "Installing missing components: ${missing[*]}"
  sudo -v || exit 1
  sudo apt-get update || exit 1
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}" || exit 1
else
  good "Required components installed: ethtool / iperf3 / iproute2"
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
  bad "No supported wired adapter was found."
  exit 1
}

say "Detected wired adapter: $IFACE"

IP4="$(ip -4 -o addr show dev "$IFACE" scope global 2>/dev/null | awk '{print $4}' | head -n1 || true)"
DRIVER="$(ethtool -i "$IFACE" 2>/dev/null | awk -F': ' '/^driver:/ {print $2}' || true)"
SPEED="$(ethtool "$IFACE" 2>/dev/null | awk -F': ' '/^[[:space:]]*Speed:/ {print $2}' || true)"
DUPLEX="$(ethtool "$IFACE" 2>/dev/null | awk -F': ' '/^[[:space:]]*Duplex:/ {print $2}' || true)"
AUTONEG="$(ethtool "$IFACE" 2>/dev/null | awk -F': ' '/^[[:space:]]*Auto-negotiation:/ {print $2}' || true)"
LINK="$(ethtool "$IFACE" 2>/dev/null | awk -F': ' '/^[[:space:]]*Link detected:/ {print $2}' || true)"

printf '  IPv4            : %s\n' "${IP4:-none}"
printf '  Driver          : %s\n' "${DRIVER:-unknown}"
printf '  Speed           : %s\n' "${SPEED:-unknown}"
printf '  Duplex          : %s\n' "${DUPLEX:-unknown}"
printf '  Auto-negotiation: %s\n' "${AUTONEG:-unknown}"
printf '  Link detected   : %s\n' "${LINK:-unknown}"

if [[ "$LINK" != "yes" ]]; then
  bad "No physical link detected. Check the cable, connectors, and router/switch ports."
  exit 2
fi

case "$SPEED" in
  1000Mb/s|2500Mb/s|5000Mb/s|10000Mb/s)
    good "Negotiated link speed: $SPEED"
    ;;
  100Mb/s)
    warn "The link is only 100 Mb/s. If both devices support gigabit, check cables, connectors, and ports."
    ;;
  10Mb/s)
    warn "The link is only 10 Mb/s, which is unexpectedly slow."
    ;;
  *)
    warn "Cannot determine negotiated speed: ${SPEED:-unknown}"
    ;;
esac

[[ "$DUPLEX" == "Full" ]] || warn "Current duplex mode is not Full: ${DUPLEX:-unknown}"

# ---- Optional cable diagnostic ---------------------------------------------
if [[ "$MODE" == "cable" ]]; then
  say "Preparing cable diagnostics"
  if [[ -n "${SSH_CONNECTION:-}" || -n "${SSH_TTY:-}" ]]; then
    bad "SSH detected. Cable diagnostics may interrupt the link, so the operation was cancelled."
    exit 3
  fi

  warn "ethtool --cable-test may briefly disconnect the link."
  read -r -p "Running in a local terminal? Type YES to continue: " ans
  [[ "$ans" == "YES" ]] || { echo "Cancelled."; exit 0; }

  if sudo ethtool --cable-test "$IFACE"; then
    echo
    sudo ethtool --cable-test-tdr "$IFACE" 2>/dev/null || true
  else
    warn "The adapter or driver may not support ethtool cable-test."
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
  say "Starting iperf3 server"
  echo "Local address: ${IP4:-check with ip addr}"
  echo "Port: $PORT"
  echo
  echo "If UFW blocks access, allow LAN-only TCP/$PORT。"
  echo "Keep this window open and run on the other device:"
  echo "  iperf3 -c <local-IP> -P $PARALLEL -t $DURATION"
  echo
  exec iperf3 -s -p "$PORT"
fi

# ---- Client mode ------------------------------------------------------------
if [[ -z "$PEER" ]]; then
  echo
  read -r -p "Peer iperf3 server IP (blank: link inspection only): " PEER
fi

if [[ -z "$PEER" ]]; then
  say "Link inspection complete"
  echo "To test throughput, run on another device:"
  echo "  iperf3 -s"
  echo
  echo "Then run again:"
  echo "  $0 <peer-IP>"
  exit 0
fi

say "Checking peer: $PEER"
if ping -c 3 -W 1 "$PEER"; then
  good "Peer is reachable"
else
  warn "No ping response; a firewall may block ICMP. Trying iperf3 anyway."
fi

say "Forward TCP throughput: andrew -> $PEER"
if ! iperf3 -c "$PEER" -p "$PORT" -P "$PARALLEL" -t "$DURATION" -O 2; then
  bad "Cannot connect to the iperf3 server."
  echo
  echo "First run on the peer:"
  echo "  iperf3 -s -p $PORT"
  echo
  echo "On Windows, allow the Private network profile if prompted by the firewall."
  exit 4
fi

say "Reverse TCP throughput: $PEER -> andrew"
iperf3 -c "$PEER" -p "$PORT" -P "$PARALLEL" -t "$DURATION" -O 2 -R || \
  warn "Reverse test failed. The forward result is still valid."

# ---- Error counters after test ---------------------------------------------
RXE1="$(read_counter rx_errors)"
TXE1="$(read_counter tx_errors)"
RXD1="$(read_counter rx_dropped)"
TXD1="$(read_counter tx_dropped)"

say "Interface error-counter changes during testing"
printf '  RX errors : %d -> %d  (increase %d)\n' "$RXE0" "$RXE1" "$((RXE1-RXE0))"
printf '  TX errors : %d -> %d  (increase %d)\n' "$TXE0" "$TXE1" "$((TXE1-TXE0))"
printf '  RX dropped: %d -> %d  (increase %d)\n' "$RXD0" "$RXD1" "$((RXD1-RXD0))"
printf '  TX dropped: %d -> %d  (increase %d)\n' "$TXD0" "$TXD1" "$((TXD1-TXD0))"

say "Interpreting results"
cat <<'EOF'
For a 1000 Mb/s link:
  • Measured TCP throughput of about 900-950 Mb/s is normally healthy.
  • About 90-95 Mb/s with Speed=100Mb/s means the negotiated link is 100 Mb/s.
  • If Speed=1000Mb/s but throughput is low, also inspect the peer, switch/router, CPU, and driver.
    iperf3 alone cannot prove a cable fault.
  • If RX/TX errors keep increasing, inspect the cable, connectors, and ports.

Note:
  iperf3 measures the entire path from the local system to the peer.
  To isolate a cable, simplify the path and use a gigabit-or-faster wired peer.
EOF
