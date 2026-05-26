#!/usr/bin/env python3
"""Detect default gateway and IPv4 settings from the host's physical (or active) NIC."""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from typing import Any


def detect_host_network(interface: str | None = None) -> dict[str, Any]:
    """
    Returns:
      gateway: default gateway IPv4 (physical/active route)
      interface: interface name / alias
      host_ip: host IPv4 on that interface
      prefix_length: int or None
    """
    system = platform.system()
    if system == "Windows":
        return _detect_windows(interface)
    if system == "Darwin":
        return _detect_unix(interface, "darwin")
    return _detect_unix(interface, "linux")


def _detect_windows(interface: str | None) -> dict[str, Any]:
    ps = r"""
$iface = $env:LAB_INTERFACE
$routes = Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' |
  Where-Object { $_.NextHop -and $_.NextHop -ne '0.0.0.0' } |
  Sort-Object RouteMetric, InterfaceMetric
if ($iface) {
  $routes = $routes | Where-Object { $_.InterfaceAlias -eq $iface }
}
$r = $routes | Select-Object -First 1
if (-not $r) { exit 2 }
$alias = $r.InterfaceAlias
$ip = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias $alias -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notlike '169.254*' } |
  Sort-Object PrefixOrigin |
  Select-Object -First 1
[pscustomobject]@{
  gateway = $r.NextHop
  interface = $alias
  host_ip = if ($ip) { $ip.IPAddress } else { $null }
  prefix_length = if ($ip) { $ip.PrefixLength } else { $null }
} | ConvertTo-Json -Compress
"""
    env = {}
    if interface:
        env["LAB_INTERFACE"] = interface
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            stderr=subprocess.STDOUT,
            env={**__import__("os").environ, **env},
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Windows gateway detection failed: {exc.output}") from exc
    data = json.loads(out)
    return _normalize(data)


def _detect_unix(interface: str | None, flavor: str) -> dict[str, Any]:
    if flavor == "darwin":
        try:
            out = subprocess.check_output(["route", "-n", "get", "default"], text=True, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            raise RuntimeError("macOS route detection failed") from exc
        gw_m = re.search(r"gateway:\s*(\S+)", out)
        if_m = re.search(r"interface:\s*(\S+)", out)
        if not gw_m:
            raise RuntimeError("No default gateway on macOS")
        iface = if_m.group(1) if if_m else ""
        if interface and iface and iface != interface:
            raise RuntimeError(f"Default route is on '{iface}', not '{interface}'")
        host_ip = _darwin_iface_ip(iface)
        return _normalize(
            {
                "gateway": gw_m.group(1),
                "interface": iface,
                "host_ip": host_ip,
                "prefix_length": None,
            }
        )

    # Linux
    try:
        out = subprocess.check_output(["ip", "-4", "route", "show", "default"], text=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError("Linux ip route failed") from exc
    line = out.strip().splitlines()[0] if out.strip() else ""
    if not line:
        raise RuntimeError("No default IPv4 route")
    gw_m = re.search(r"default via (\S+)", line)
    dev_m = re.search(r"dev (\S+)", line)
    if not gw_m:
        raise RuntimeError(f"Cannot parse default route: {line}")
    iface = dev_m.group(1) if dev_m else ""
    if interface and iface and iface != interface:
        raise RuntimeError(f"Default route is on '{iface}', not '{interface}'")
    host_ip = _linux_iface_ip(iface)
    return _normalize(
        {
            "gateway": gw_m.group(1),
            "interface": iface,
            "host_ip": host_ip,
            "prefix_length": None,
        }
    )


def _darwin_iface_ip(iface: str) -> str | None:
    if not iface:
        return None
    try:
        out = subprocess.check_output(["ipconfig", "getifaddr", iface], text=True, stderr=subprocess.DEVNULL)
        return out.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _linux_iface_ip(iface: str) -> str | None:
    if not iface:
        return None
    try:
        out = subprocess.check_output(["ip", "-4", "addr", "show", "dev", iface], text=True)
    except subprocess.CalledProcessError:
        return None
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", out)
    if not m:
        return None
    return m.group(1)


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "gateway": data.get("gateway"),
        "interface": data.get("interface") or "",
        "host_ip": data.get("host_ip"),
        "prefix_length": data.get("prefix_length"),
        "source": platform.system(),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Detect host default gateway from physical/active NIC")
    parser.add_argument("-i", "--interface", help="Use default route on this interface only")
    parser.add_argument("-j", "--json", action="store_true", help="Print JSON")
    args = parser.parse_args()
    try:
        info = detect_host_network(args.interface or None)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"gateway={info['gateway']}")
        print(f"interface={info['interface']}")
        print(f"host_ip={info['host_ip']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
