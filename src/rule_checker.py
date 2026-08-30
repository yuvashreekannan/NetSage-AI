"""
rule_checker.py
----------------
Deterministic (non-AI) rule checker for common Cisco network configuration
mistakes. This is Stage 3 of the NetSage AI project.

This script does NOT call any AI model. It applies fixed Python logic to a
structured description ("snapshot") of a network's configuration, and flags
six common mistake types required by the project brief:

    1. Duplicate IP addresses
    2. Wrong subnet masks
    3. Gateway mismatch
    4. Interface down
    5. Missing VLAN
    6. Missing routes

INPUT:  a JSON file describing hosts, router interfaces, switch ports,
        VLANs, trunks, and routes (see network_data_sample.json for the
        exact shape expected).

OUTPUT: printed flags in the terminal + appended rows in
        results/rule_flags.csv
"""

import json
import csv
import ipaddress
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# STEP 1: Load the input file
# ---------------------------------------------------------------------------
def load_network_data(json_path):
    """Read the JSON snapshot file and return it as a Python dictionary."""
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# STEP 2: The six rule-checking functions
# Each one takes the full data dictionary and returns a list of "flag"
# dictionaries. An empty list means "no problem found for this rule".
# ---------------------------------------------------------------------------

def check_duplicate_ips(data):
    """Rule 1: Two different hosts should never have the same IP address."""
    flags = []
    seen_ips = {}
    for host in data.get("hosts", []):
        ip = host.get("ip")
        if not ip:
            continue
        if ip in seen_ips:
            flags.append({
                "rule": "duplicate_ip",
                "severity": "High",
                "message": f"Duplicate IP {ip} found on both "
                           f"'{seen_ips[ip]}' and '{host['name']}'.",
                "evidence": f"{seen_ips[ip]} and {host['name']} both use {ip}"
            })
        else:
            seen_ips[ip] = host["name"]
    return flags


def check_wrong_subnet_mask(data):
    """Rule 2: Hosts meant to be on the same subnet must share the same mask."""
    flags = []

    # First check each host's IP/mask pair is even valid.
    for host in data.get("hosts", []):
        ip, mask = host.get("ip"), host.get("mask")
        if not ip or not mask:
            continue
        try:
            ipaddress.ip_interface(f"{ip}/{mask}")
        except ValueError:
            flags.append({
                "rule": "wrong_subnet_mask",
                "severity": "Medium",
                "message": f"Host '{host['name']}' has an invalid subnet "
                           f"mask '{mask}'.",
                "evidence": f"{host['name']}: {ip}/{mask}"
            })

    # Then check hosts that are SUPPOSED to be on the same subnet
    # (grouped by the "intended_subnet" label) actually agree on the mask.
    groups = {}
    for host in data.get("hosts", []):
        label = host.get("intended_subnet")
        if label:
            groups.setdefault(label, []).append(host)

    for label, hosts in groups.items():
        masks_used = {h.get("mask") for h in hosts if h.get("mask")}
        if len(masks_used) > 1:
            names = ", ".join(h["name"] for h in hosts)
            flags.append({
                "rule": "wrong_subnet_mask",
                "severity": "Medium",
                "message": f"Hosts intended for subnet '{label}' have "
                           f"inconsistent masks: {sorted(masks_used)}.",
                "evidence": f"{names} -> masks {sorted(masks_used)}"
            })
    return flags


def check_gateway_mismatch(data):
    """Rule 3: A host's gateway IP must match an actual router interface IP."""
    flags = []
    router_ips = {
        iface["ip"] for iface in data.get("router_interfaces", [])
        if iface.get("ip")
    }

    for host in data.get("hosts", []):
        gw = host.get("gateway")
        if gw and gw not in router_ips:
            flags.append({
                "rule": "gateway_mismatch",
                "severity": "Medium",
                "message": f"Host '{host['name']}' gateway {gw} does not "
                           f"match any configured router interface IP.",
                "evidence": f"{host['name']} gateway={gw}, "
                            f"known router IPs={sorted(router_ips)}"
            })
    return flags


def check_interface_down(data):
    """Rule 4: Any router or switch interface reported down/admin-down."""
    flags = []
    all_interfaces = data.get("router_interfaces", []) + data.get("switch_ports", [])
    for iface in all_interfaces:
        status = str(iface.get("status", "")).lower()
        if "down" in status:
            flags.append({
                "rule": "interface_down",
                "severity": "High",
                "message": f"Interface {iface.get('name')} on "
                           f"{iface.get('device')} is '{iface.get('status')}'.",
                "evidence": f"{iface.get('device')} {iface.get('name')}: "
                            f"{iface.get('status')}"
            })
    return flags


def check_missing_vlan(data):
    """Rule 5: Ports assigned to VLANs that don't exist, or VLANs not
    permitted across a trunk link."""
    flags = []
    configured_vlans = {v["id"] for v in data.get("vlans", [])}

    # 5a: a switch port assigned to a VLAN ID that isn't in the VLAN database
    for port in data.get("switch_ports", []):
        vlan_id = port.get("vlan")
        if vlan_id is not None and vlan_id not in configured_vlans:
            flags.append({
                "rule": "missing_vlan",
                "severity": "High",
                "message": f"Port {port.get('name')} on {port.get('device')} "
                           f"is assigned to VLAN {vlan_id}, which does not "
                           f"exist in the VLAN database.",
                "evidence": f"{port.get('device')} {port.get('name')} -> "
                            f"VLAN {vlan_id}"
            })

    # 5b: a VLAN that exists is not permitted across a trunk (excluding VLAN 1)
    for trunk in data.get("trunks", []):
        allowed = set(trunk.get("allowed_vlans", []))
        for vlan_id in configured_vlans:
            if vlan_id != 1 and vlan_id not in allowed:
                flags.append({
                    "rule": "missing_vlan",
                    "severity": "Medium",
                    "message": f"VLAN {vlan_id} is not permitted on trunk "
                               f"{trunk.get('port')} ({trunk.get('device')}).",
                    "evidence": f"Trunk {trunk.get('device')} "
                                f"{trunk.get('port')} allowed={sorted(allowed)}"
                })
    return flags


def check_missing_routes(data):
    """Rule 6: Every subnet listed in 'expected_subnets' should either be
    directly connected to a router interface, or present in the routing
    table. If neither, it's a missing route."""
    flags = []

    configured_routes = set()
    for route in data.get("routes", []):
        try:
            net = ipaddress.ip_network(f"{route['network']}/{route['mask']}",
                                        strict=False)
            configured_routes.add(str(net))
        except (ValueError, KeyError):
            continue

    for subnet in data.get("expected_subnets", []):
        try:
            net = ipaddress.ip_network(subnet, strict=False)
        except ValueError:
            continue

        if str(net) in configured_routes:
            continue
        if _is_directly_connected(data, net):
            continue

        flags.append({
            "rule": "missing_route",
            "severity": "High",
            "message": f"No route found for expected subnet {subnet}.",
            "evidence": f"routing table has {sorted(configured_routes)}"
        })
    return flags


def _is_directly_connected(data, network):
    """Helper: True if a router interface's subnet matches the given network."""
    for iface in data.get("router_interfaces", []):
        ip, mask = iface.get("ip"), iface.get("mask")
        if ip and mask:
            try:
                if ipaddress.ip_interface(f"{ip}/{mask}").network == network:
                    return True
            except ValueError:
                continue
    return False


# ---------------------------------------------------------------------------
# STEP 3: Run every rule together
# ---------------------------------------------------------------------------
ALL_CHECKS = [
    check_duplicate_ips,
    check_wrong_subnet_mask,
    check_gateway_mismatch,
    check_interface_down,
    check_missing_vlan,
    check_missing_routes,
]


def run_all_checks(data):
    """Run all 6 rules and combine their results into one list."""
    all_flags = []
    for check_function in ALL_CHECKS:
        all_flags.extend(check_function(data))
    return all_flags


# ---------------------------------------------------------------------------
# STEP 4: Save results to CSV (appends one row per flag)
# ---------------------------------------------------------------------------
def save_flags_to_csv(flags, case_id, output_path):
    file_already_exists = Path(output_path).exists()
    with open(output_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["case_id", "rule", "severity", "message", "evidence"]
        )
        if not file_already_exists:
            writer.writeheader()

        if not flags:
            writer.writerow({
                "case_id": case_id, "rule": "none", "severity": "None",
                "message": "No issues detected by rule checker.", "evidence": ""
            })
        else:
            for flag in flags:
                writer.writerow({"case_id": case_id, **flag})


# ---------------------------------------------------------------------------
# STEP 5: Command-line entry point
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python rule_checker.py <path_to_network_data.json> [case_id]")
        sys.exit(1)

    json_path = sys.argv[1]
    case_id = sys.argv[2] if len(sys.argv) > 2 else Path(json_path).stem

    data = load_network_data(json_path)
    flags = run_all_checks(data)

    print(f"\n=== Rule Checker Results for case: {case_id} ===")
    if not flags:
        print("No issues detected.")
    else:
        for flag in flags:
            print(f"[{flag['severity']}] {flag['rule']}: {flag['message']}")

    output_path = Path(__file__).resolve().parent.parent / "results" / "rule_flags.csv"
    output_path.parent.mkdir(exist_ok=True)
    save_flags_to_csv(flags, case_id, output_path)
    print(f"\nSaved {len(flags) if flags else 1} row(s) to {output_path}")


if __name__ == "__main__":
    main()
