#!/bin/sh
set -e

if [ ! -f /etc/snmp/snmpd.conf ]; then
  COMMUNITY="${SNMP_COMMUNITY:-public}"
  PORT="${SNMP_PORT:-161}"
  cat > /etc/snmp/snmpd.conf <<EOF
agentAddress udp:${PORT}
rocommunity ${COMMUNITY}
sysLocation Network Lab
sysContact lab@local
EOF
fi

PORT="${SNMP_PORT:-161}"
echo "SNMP agent UDP ${PORT}"
exec snmpd -f -Lo
