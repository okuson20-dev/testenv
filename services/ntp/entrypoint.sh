#!/bin/sh
set -e
PORT="${NTP_PORT:-123}"

cat > /etc/chrony/chrony.conf <<EOF
port ${PORT}
cmdport 0
local stratum 8
allow all
makestep 1.0 3
rtcsync
driftfile /var/lib/chrony/drift
logdir /var/log/chrony
EOF

echo "NTP server listening on UDP ${PORT}"
exec chronyd -d -s -f /etc/chrony/chrony.conf
