#!/bin/sh
set -e
PORT="${SYSLOG_PORT:-514}"

mkdir -p /var/log/network-lab

cat > /etc/rsyslog.conf <<EOF
module(load="imudp")
input(type="imudp" port="${PORT}")

module(load="imtcp")
input(type="imtcp" port="${PORT}")

*.* /var/log/network-lab/messages.log
EOF

echo "Syslog listening TCP/UDP ${PORT}"
exec rsyslogd -n
