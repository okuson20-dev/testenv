"""Default ports per service type."""

DEFAULT_PORTS = {
    "ntp": 123,
    "dns": 53,
    "dhcp": 67,
    "syslog": 514,
    "snmp": 161,
}

SERVICE_TYPES = frozenset(DEFAULT_PORTS.keys())
