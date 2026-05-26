#!/bin/sh
set -e

SERVER_IP="${DHCP_SERVER_IP:?DHCP_SERVER_IP required}"
PORT="${DHCP_PORT:-67}"
RANGE_START="${RANGE_START:?RANGE_START required}"
RANGE_END="${RANGE_END:?RANGE_END required}"
LEASE="${LEASE_TIME:-12h}"
GATEWAY="${GATEWAY:?GATEWAY required}"

# dnsmasq DHCP only (no DNS on this instance)
cat > /etc/dnsmasq.conf <<EOF
interface=eth0
bind-interfaces
port=0
dhcp-range=${RANGE_START},${RANGE_END},${LEASE}
dhcp-option=3,${GATEWAY}
dhcp-option=6,${SERVER_IP}
dhcp-authoritative
log-dhcp
EOF

echo "DHCP server ${SERVER_IP} range ${RANGE_START}-${RANGE_END} (UDP ${PORT}, dnsmasq uses 67)"
exec dnsmasq -d --conf-file=/etc/dnsmasq.conf
