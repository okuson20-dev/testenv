#!/bin/sh
set -e

echo 1 > /proc/sys/net/ipv4/ip_forward
iptables -P FORWARD ACCEPT 2>/dev/null || true

echo "Router interfaces:"
ip -4 addr show scope global

# 外向き: Docker ホスト経由（物理NICのデフォルトGWはホストが保持）
if [ "$UPSTREAM_VIA" = "auto" ] || [ -z "$UPSTREAM_VIA" ]; then
  if getent ahosts host.docker.internal >/dev/null 2>&1; then
    HOST_IP=$(getent ahosts host.docker.internal | awk 'NR==1 {print $1}')
    ROUTE=$(ip route get "$HOST_IP" 2>/dev/null || true)
    DEV=$(echo "$ROUTE" | awk '/ dev / {for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')
    VIA=$(echo "$ROUTE" | awk '/ via / {for(i=1;i<=NF;i++) if($i=="via"){print $(i+1); exit}}')
    if [ -n "$DEV" ]; then
      if [ -n "$VIA" ]; then
        ip route replace default via "$VIA" dev "$DEV" 2>/dev/null || true
      else
        ip route replace default dev "$DEV" 2>/dev/null || true
      fi
      echo "Default route via Docker host ($HOST_IP) dev $DEV"
    fi
  fi
elif [ -n "$UPSTREAM_VIA" ]; then
  ip route replace default via "$UPSTREAM_VIA" 2>/dev/null || true
fi

if [ -n "$UPSTREAM_GW" ]; then
  echo "Physical NIC default gateway (reference): $UPSTREAM_GW"
fi

exec sleep infinity
