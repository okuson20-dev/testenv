#!/bin/sh
set -e
PORT="${DNS_PORT:-53}"

if [ ! -f /etc/bind/named.conf ]; then
  echo "Missing /etc/bind/named.conf (run generate_compose.py)" >&2
  exit 1
fi

echo "DNS server (BIND) port ${PORT}"
exec named -g -c /etc/bind/named.conf
