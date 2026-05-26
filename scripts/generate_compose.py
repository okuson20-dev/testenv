#!/usr/bin/env python3
"""Generate docker-compose.yml and per-service configs from config/lab.yaml."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from defaults import DEFAULT_PORTS, SERVICE_TYPES  # noqa: E402
from host_network import detect_host_network  # noqa: E402

FROM_HOST_TOKENS = frozenset({"from_host", "host", "physical"})
AUTO_TOKENS = frozenset({"auto", "default"})


def load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        return json.loads(text)
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "YAML config requires PyYAML: pip install -r requirements.txt\n"
            "Or use JSON: config/lab.json (see config/lab.json.example)"
        ) from exc
    return yaml.safe_load(text)


def _is_from_host(value) -> bool:
    return isinstance(value, str) and value.strip().lower() in FROM_HOST_TOKENS


def _is_auto(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in AUTO_TOKENS)


def _subnet_gateway(subnet: str) -> str:
    base = subnet.split("/")[0]
    parts = base.split(".")
    parts[-1] = "1"
    return ".".join(parts)


def _needs_host_detect(cfg: dict) -> bool:
    host_cfg = cfg.get("host", {})
    if _is_from_host(host_cfg.get("gateway")):
        return True
    router = cfg.get("router", {})
    if _is_from_host(router.get("upstream_gateway")):
        return True
    for seg in cfg.get("segments", []):
        if _is_from_host(seg.get("gateway")):
            return True
    for svc in cfg.get("services", {}).values():
        if not svc.get("enabled", True):
            continue
        gw = svc.get("options", {}).get("gateway")
        if _is_from_host(gw):
            return True
    return False


def apply_host_network(cfg: dict) -> dict:
    """Resolve from_host / auto gateway tokens using the host OS routing table."""
    out = copy.deepcopy(cfg)
    host_cfg = out.get("host", {})
    iface = host_cfg.get("interface") or None
    detected: dict | None = None

    if _needs_host_detect(out):
        try:
            detected = detect_host_network(iface)
        except RuntimeError as exc:
            raise SystemExit(
                f"Cannot read default gateway from host NIC: {exc}\n"
                "Set an explicit IP in config, or run on Windows with an active LAN connection."
            ) from exc
        gen = ROOT / "generated"
        gen.mkdir(parents=True, exist_ok=True)
        (gen / "host-network.json").write_text(
            json.dumps(detected, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    physical_gw = detected["gateway"] if detected else None

    if detected:
        print(
            f"Host NIC: {detected.get('interface')} "
            f"ip={detected.get('host_ip')} gateway={physical_gw}",
            file=sys.stderr,
        )

    for seg in out.get("segments", []):
        gw = seg.get("gateway")
        if _is_auto(gw):
            seg["gateway"] = _subnet_gateway(seg["subnet"])
        elif _is_from_host(gw):
            if not physical_gw:
                raise ValueError("from_host gateway requested but detection failed")
            seg["gateway"] = physical_gw

    router = out.setdefault("router", {})
    upstream = router.get("upstream_gateway")
    if upstream is None and _is_from_host(host_cfg.get("gateway")):
        upstream = "from_host"
    if _is_from_host(upstream):
        router["upstream_gateway"] = physical_gw

    out["_host_network"] = detected
    return out


def validate(cfg: dict) -> None:
    seg_names = {s["name"] for s in cfg["segments"]}
    seg_by_name = {s["name"]: s for s in cfg["segments"]}

    for name, svc in cfg.get("services", {}).items():
        if not svc.get("enabled", True):
            continue
        stype = svc["type"]
        if stype not in SERVICE_TYPES:
            raise ValueError(f"Unknown service type '{stype}' for {name}")
        seg = svc.get("segment")
        if seg not in seg_names:
            raise ValueError(f"Service {name}: unknown segment '{seg}'")
        ip = svc.get("ip")
        if not ip:
            raise ValueError(f"Service {name}: ip is required")
        subnet = seg_by_name[seg]["subnet"]
        prefix = subnet.split("/")[1]
        net_base = ".".join(subnet.split("/")[0].split(".")[:3])
        if not ip.startswith(net_base.rsplit(".", 1)[0]):
            # loose check: same /24 third octet for typical lab subnets
            pass  # allow any IP in custom subnets; Docker will reject invalid


def enabled_services(cfg: dict) -> dict[str, dict]:
    return {
        name: svc
        for name, svc in cfg.get("services", {}).items()
        if svc.get("enabled", True)
    }


def build_networks(cfg: dict) -> dict:
    networks: dict = {}
    for seg in cfg["segments"]:
        name = seg["name"]
        networks[name] = {
            "driver": "bridge",
            "ipam": {
                "config": [{"subnet": seg["subnet"], "gateway": seg.get("gateway")}],
            },
        }
    return networks


def port_publish(
    publish: bool,
    host_port: int | None,
    container_port: int,
    proto: str,
) -> list[str]:
    if not publish or host_port is None:
        return []
    mapping = f"{host_port}:{container_port}"
    if proto == "udp":
        return [f"{mapping}/udp"]
    if proto == "tcp":
        return [mapping]
    return [mapping]


def resolve_host_port(svc: dict, stype: str, publish: bool) -> int | None:
    """Host port for publish. Explicit host_port, or port field when publish_ports is true."""
    if not publish:
        return None
    if "host_port" in svc:
        return int(svc["host_port"])
    if "port" in svc:
        return int(svc["port"])
    return int(DEFAULT_PORTS[stype])


def service_port(svc: dict, stype: str) -> int:
    return int(svc.get("port", DEFAULT_PORTS[stype]))


def build_compose(cfg: dict) -> dict:
    publish = cfg.get("publish_ports", False)
    host_net = cfg.get("_host_network") or {}
    physical_gw = host_net.get("gateway") if host_net else None
    services_cfg = enabled_services(cfg)
    networks = build_networks(cfg)

    compose: dict = {
        "services": {},
        "networks": networks,
    }

    # Router connects all segments
    if cfg.get("router", {}).get("enabled", True):
        router_nets = {}
        for seg in cfg["segments"]:
            gw = seg.get("gateway")
            if gw:
                router_nets[seg["name"]] = {"ipv4_address": gw}
            else:
                router_nets[seg["name"]] = {}
        router_cfg = cfg.get("router", {})
        upstream = router_cfg.get("upstream_gateway") or physical_gw or ""
        compose["services"]["router"] = {
            "build": {"context": "./services/router"},
            "container_name": "lab-router",
            "hostname": "router",
            "cap_add": ["NET_ADMIN"],
            "sysctls": {"net.ipv4.ip_forward": "1"},
            "restart": "unless-stopped",
            "extra_hosts": ["host.docker.internal:host-gateway"],
            "environment": {
                "UPSTREAM_GW": str(upstream),
                "UPSTREAM_VIA": str(router_cfg.get("upstream_via", "auto")),
            },
            "networks": router_nets,
        }

    for name, svc in services_cfg.items():
        stype = svc["type"]
        seg = svc["segment"]
        ip = svc["ip"]
        port = service_port(svc, stype)
        host_port = resolve_host_port(svc, stype, publish)
        container = f"lab-{name.replace('_', '-')}"

        base = {
            "container_name": container,
            "hostname": name.replace("_", "-"),
            "restart": "unless-stopped",
            "networks": {seg: {"ipv4_address": ip}},
        }

        if stype == "ntp":
            compose["services"][name] = {
                **base,
                "build": {"context": "./services/ntp"},
                "environment": {"NTP_PORT": str(port)},
                "ports": port_publish(publish, host_port, port, "udp"),
            }
        elif stype == "dns":
            compose["services"][name] = {
                **base,
                "build": {"context": "./services/dns"},
                "environment": {"DNS_PORT": str(port)},
                "ports": port_publish(publish, host_port, port, "udp")
                + port_publish(publish, host_port, port, "tcp"),
            }
        elif stype == "dhcp":
            opts = svc.get("options", {})
            compose["services"][name] = {
                **base,
                "build": {"context": "./services/dhcp"},
                "environment": {
                    "DHCP_SERVER_IP": ip,
                    "DHCP_PORT": str(port),
                    "RANGE_START": opts.get("range_start", _default_range_start(cfg, seg)),
                    "RANGE_END": opts.get("range_end", _default_range_end(cfg, seg)),
                    "LEASE_TIME": opts.get("lease_time", "12h"),
                    "GATEWAY": _dhcp_gateway(cfg, svc, seg, physical_gw),
                },
                "cap_add": ["NET_ADMIN"],
                "ports": port_publish(publish, host_port, port, "udp"),
            }
        elif stype == "syslog":
            compose["services"][name] = {
                **base,
                "build": {"context": "./services/syslog"},
                "environment": {"SYSLOG_PORT": str(port)},
                "ports": port_publish(publish, host_port, port, "udp")
                + port_publish(publish, host_port, port, "tcp"),
                "volumes": [f"./generated/{name}/logs:/var/log/network-lab"],
            }
        elif stype == "snmp":
            opts = svc.get("options", {})
            compose["services"][name] = {
                **base,
                "build": {"context": "./services/snmp"},
                "environment": {
                    "SNMP_PORT": str(port),
                    "SNMP_COMMUNITY": opts.get("community", "public"),
                },
                "ports": port_publish(publish, host_port, port, "udp"),
            }

    return compose


def _segment_by_name(cfg: dict, name: str) -> dict:
    for s in cfg["segments"]:
        if s["name"] == name:
            return s
    raise KeyError(name)


def _segment_gateway(cfg: dict, seg_name: str) -> str:
    seg = _segment_by_name(cfg, seg_name)
    gw = seg.get("gateway")
    if gw and not _is_auto(gw) and not _is_from_host(gw):
        return str(gw)
    return _subnet_gateway(seg["subnet"])


def _dhcp_gateway(cfg: dict, svc: dict, seg_name: str, physical_gw: str | None) -> str:
    opts = svc.get("options", {})
    gw = opts.get("gateway")
    if _is_from_host(gw):
        return physical_gw or _segment_gateway(cfg, seg_name)
    if _is_auto(gw) or gw is None:
        return _segment_gateway(cfg, seg_name)
    return str(gw)


def _default_range_start(cfg: dict, seg_name: str) -> str:
    base = _segment_by_name(cfg, seg_name)["subnet"].split("/")[0]
    parts = base.split(".")
    parts[-1] = "100"
    return ".".join(parts)


def _default_range_end(cfg: dict, seg_name: str) -> str:
    base = _segment_by_name(cfg, seg_name)["subnet"].split("/")[0]
    parts = base.split(".")
    parts[-1] = "200"
    return ".".join(parts)


def write_service_configs(cfg: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, svc in enabled_services(cfg).items():
        stype = svc["type"]
        svc_dir = out_dir / name
        svc_dir.mkdir(parents=True, exist_ok=True)

        if stype == "dns":
            zone = svc.get("options", {}).get("zone", "lab.local")
            (svc_dir / "named.conf").write_text(
                _dns_named_conf(svc["ip"], zone, service_port(svc, stype)),
                encoding="utf-8",
            )
            (svc_dir / "db.lab.local").write_text(
                _dns_zone_file(zone, svc["ip"], name),
                encoding="utf-8",
            )
        elif stype == "snmp":
            community = svc.get("options", {}).get("community", "public")
            (svc_dir / "snmpd.conf").write_text(
                _snmpd_conf(community, service_port(svc, stype)),
                encoding="utf-8",
            )


def _dns_named_conf(ip: str, zone: str, port: int) -> str:
    return f"""options {{
    directory "/var/bind";
    listen-on port {port} {{ any; }};
    listen-on-v6 port {port} {{ none; }};
    allow-query {{ any; }};
    recursion yes;
    forwarders {{ 8.8.8.8; 1.1.1.1; }};
}};

zone "{zone}" IN {{
    type master;
    file "/etc/bind/db.{zone}";
}};
"""


def _dns_zone_file(zone: str, ip: str, hostname: str) -> str:
    serial = "2026052601"
    return f"""$TTL 86400
@   IN  SOA {hostname}.{zone}. admin.{zone}. (
        {serial} ; serial
        3600       ; refresh
        1800       ; retry
        604800     ; expire
        86400 )    ; minimum
    IN  NS  {hostname}.{zone}.
{hostname}  IN  A   {ip}
ns          IN  A   {ip}
gateway     IN  A   {ip.rsplit('.', 1)[0]}.1
"""


def _snmpd_conf(community: str, port: int) -> str:
    return f"""agentAddress udp:{port}
rocommunity {community}
sysLocation Network Lab
sysContact lab@local
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate docker-compose from lab.yaml")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=None,
        help="Path to lab.yaml or lab.json (default: config/lab.json or lab.yaml)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "docker-compose.yml",
    )
    args = parser.parse_args()

    if args.config is None:
        for candidate in (ROOT / "config" / "lab.yaml", ROOT / "config" / "lab.json"):
            if candidate.exists():
                args.config = candidate
                break
        else:
            args.config = ROOT / "config" / "lab.json.example"

    if not args.config.exists():
        print(f"Config not found: {args.config}", file=sys.stderr)
        print("Copy: config/lab.json.example -> config/lab.json", file=sys.stderr)
        return 1

    cfg = load_config(args.config)
    cfg = apply_host_network(cfg)
    validate(cfg)
    compose = build_compose(cfg)

    gen_dir = ROOT / "generated"
    write_service_configs(cfg, gen_dir)

    # Mount generated DNS/SNMP configs into compose
    compose = _inject_config_volumes(compose, cfg, gen_dir)

    _write_compose(compose, args.output)

    enabled = list(enabled_services(cfg).keys())
    profiles_path = ROOT / "generated" / "enabled-services.txt"
    profiles_path.parent.mkdir(parents=True, exist_ok=True)
    profiles_path.write_text("\n".join(enabled), encoding="utf-8")

    print(f"Generated {args.output}")
    print(f"Enabled services: {', '.join(enabled) or '(none)'}")
    return 0


def _write_compose(compose: dict, path: Path) -> None:
    """Write docker-compose.yml (stdlib YAML emitter, no PyYAML required)."""
    lines = ["# Generated by scripts/generate_compose.py — do not edit manually", ""]
    _emit_value(compose, lines, 0)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _emit_value(value, lines: list[str], indent: int) -> None:
    if isinstance(value, dict):
        _emit_dict(value, lines, indent)
    elif isinstance(value, list):
        _emit_list(value, lines, indent)
    else:
        lines.append("  " * indent + _yaml_scalar(value))


def _emit_dict(data: dict, lines: list[str], indent: int) -> None:
    pad = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            if not value:
                lines.append(f"{pad}{key}: {{}}")
            else:
                lines.append(f"{pad}{key}:")
                _emit_dict(value, lines, indent + 1)
        elif isinstance(value, list):
            if not value:
                lines.append(f"{pad}{key}: []")
            else:
                lines.append(f"{pad}{key}:")
                _emit_list(value, lines, indent + 1)
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar(value)}")


def _emit_list(items: list, lines: list[str], indent: int) -> None:
    pad = "  " * indent
    for item in items:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{pad}- {{}}")
                continue
            first_key = next(iter(item))
            first_val = item[first_key]
            if isinstance(first_val, (dict, list)):
                lines.append(f"{pad}-")
                _emit_value(first_val, lines, indent + 2)
                for key, value in list(item.items())[1:]:
                    if isinstance(value, dict):
                        lines.append(f"{pad}  {key}:")
                        _emit_dict(value, lines, indent + 2)
                    elif isinstance(value, list):
                        lines.append(f"{pad}  {key}:")
                        _emit_list(value, lines, indent + 2)
                    else:
                        lines.append(f"{pad}  {key}: {_yaml_scalar(value)}")
            else:
                lines.append(f"{pad}- {first_key}: {_yaml_scalar(first_val)}")
                for key, value in list(item.items())[1:]:
                    lines.append(f"{pad}  {key}: {_yaml_scalar(value)}")
        else:
            lines.append(f"{pad}- {_yaml_scalar(item)}")


def _yaml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text or any(c in text for c in ":{}[]&*#?|-<>=!%@\"'\\"):
        return json.dumps(text)
    return text


def _inject_config_volumes(compose: dict, cfg: dict, gen_dir: Path) -> dict:
    out = copy.deepcopy(compose)
    for name, svc in enabled_services(cfg).items():
        if name not in out.get("services", {}):
            continue
        stype = svc["type"]
        if stype == "dns":
            out["services"][name].setdefault("volumes", [])
            out["services"][name]["volumes"].extend(
                [
                    f"./generated/{name}/named.conf:/etc/bind/named.conf:ro",
                    f"./generated/{name}/db.lab.local:/etc/bind/db.{svc.get('options', {}).get('zone', 'lab.local')}:ro",
                ]
            )
        elif stype == "snmp":
            out["services"][name].setdefault("volumes", [])
            out["services"][name]["volumes"].append(
                f"./generated/{name}/snmpd.conf:/etc/snmp/snmpd.conf:ro"
            )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
