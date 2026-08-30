"""
test_rule_checker.py
---------------------
Beginner-friendly tests for each of the 6 rules in rule_checker.py.

No test framework (like pytest) is needed. This uses plain Python
'assert' statements: if a rule works correctly, you'll see a PASS line.
If something is broken, Python will raise an AssertionError and tell
you exactly which test failed.

Run it with:
    python test_rule_checker.py
(from inside the src/ folder, with your virtual environment active)
"""

from rule_checker import (
    check_duplicate_ips,
    check_wrong_subnet_mask,
    check_gateway_mismatch,
    check_interface_down,
    check_missing_vlan,
    check_missing_routes,
)


# ---- Rule 1: Duplicate IP -------------------------------------------------
def test_duplicate_ip_detected():
    data = {"hosts": [
        {"name": "PC1", "ip": "10.0.0.5"},
        {"name": "PC2", "ip": "10.0.0.5"},
    ]}
    flags = check_duplicate_ips(data)
    assert len(flags) == 1
    assert flags[0]["rule"] == "duplicate_ip"
    print("PASS: duplicate IP detected correctly")


def test_no_duplicate_ip_false_positive():
    data = {"hosts": [
        {"name": "PC1", "ip": "10.0.0.5"},
        {"name": "PC2", "ip": "10.0.0.6"},
    ]}
    flags = check_duplicate_ips(data)
    assert len(flags) == 0
    print("PASS: no false positive when IPs are unique")


# ---- Rule 2: Wrong subnet mask --------------------------------------------
def test_wrong_subnet_mask_detected():
    data = {"hosts": [
        {"name": "PC1", "ip": "192.168.1.10", "mask": "255.255.255.0", "intended_subnet": "LAN1"},
        {"name": "PC2", "ip": "192.168.1.11", "mask": "255.255.0.0",   "intended_subnet": "LAN1"},
    ]}
    flags = check_wrong_subnet_mask(data)
    assert len(flags) >= 1
    print("PASS: wrong subnet mask detected correctly")


# ---- Rule 3: Gateway mismatch ----------------------------------------------
def test_gateway_mismatch_detected():
    data = {
        "hosts": [{"name": "PC1", "gateway": "192.168.1.99"}],
        "router_interfaces": [{"device": "R1", "name": "Fa0/0", "ip": "192.168.1.1"}]
    }
    flags = check_gateway_mismatch(data)
    assert len(flags) == 1
    print("PASS: gateway mismatch detected correctly")


def test_gateway_match_no_false_positive():
    data = {
        "hosts": [{"name": "PC1", "gateway": "192.168.1.1"}],
        "router_interfaces": [{"device": "R1", "name": "Fa0/0", "ip": "192.168.1.1"}]
    }
    flags = check_gateway_mismatch(data)
    assert len(flags) == 0
    print("PASS: no false positive when gateway matches")


# ---- Rule 4: Interface down -------------------------------------------------
def test_interface_down_detected():
    data = {"router_interfaces": [
        {"device": "R1", "name": "Fa0/0", "status": "administratively down"}
    ]}
    flags = check_interface_down(data)
    assert len(flags) == 1
    print("PASS: interface down detected correctly")


# ---- Rule 5: Missing VLAN ---------------------------------------------------
def test_missing_vlan_detected():
    data = {
        "switch_ports": [{"device": "SW1", "name": "Fa0/5", "vlan": 99, "status": "up"}],
        "vlans": [{"id": 1, "name": "default"}],
        "trunks": []
    }
    flags = check_missing_vlan(data)
    assert len(flags) == 1
    print("PASS: missing VLAN detected correctly")


# ---- Rule 6: Missing route ---------------------------------------------------
def test_missing_route_detected():
    data = {
        "router_interfaces": [{"device": "R1", "name": "Fa0/0", "ip": "192.168.1.1", "mask": "255.255.255.0"}],
        "routes": [],
        "expected_subnets": ["192.168.2.0/24"]
    }
    flags = check_missing_routes(data)
    assert len(flags) == 1
    print("PASS: missing route detected correctly")


def test_route_present_no_false_positive():
    data = {
        "router_interfaces": [{"device": "R1", "name": "Fa0/0", "ip": "192.168.1.1", "mask": "255.255.255.0"}],
        "routes": [{"device": "R1", "network": "192.168.2.0", "mask": "255.255.255.0"}],
        "expected_subnets": ["192.168.2.0/24"]
    }
    flags = check_missing_routes(data)
    assert len(flags) == 0
    print("PASS: no false positive when route already exists")


if __name__ == "__main__":
    test_duplicate_ip_detected()
    test_no_duplicate_ip_false_positive()
    test_wrong_subnet_mask_detected()
    test_gateway_mismatch_detected()
    test_gateway_match_no_false_positive()
    test_interface_down_detected()
    test_missing_vlan_detected()
    test_missing_route_detected()
    test_route_present_no_false_positive()
    print("\nAll 9 tests passed!")
