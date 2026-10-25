from ipaddress import IPv4Interface
import os
import requests

from app.backends.planning import plan_interface as planning_plan_interface

def get_interface_state(router,interface_name,http_get=None):
    """Return normalized interface status using RESTCONF."""
    if http_get is None:
        user = os.getenv("ROUTER_USER", "")
        password = os.getenv("ROUTER_PASS", "")

        def http_get(url):
            return requests.get(
                url,
                auth=(user, password),
                headers={"Accept": "application/yang-data+json"},
                verify=False,
                timeout=15,
            )

    url = f"https://{router}/restconf/data/ietf-interfaces:interfaces/interface={interface_name}"

    try:
        resp = http_get(url)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    if resp.status_code in (401, 403):
        return {"status": "error", "result": "authentication_failed"}
    if resp.status_code == 404:
        return {"status": "ok", "result": "not_found", "interface": None}
    if resp.status_code != 200:
        return {"status": "error", "result": "backend_failed"}

    try:
        data = resp.json()
        if "ietf-interfaces:interface" in data:
            iface = data["ietf-interfaces:interface"]
        elif "interface" in data:
            iface = data["interface"]
        else:
            return {"status": "error", "result": "backend_failed"}

        name = iface.get("name", interface_name)
        description = iface.get("description", None)
        enabled = iface.get("enabled", True)
        admin_state = "up" if enabled else "down"

        ipv4 = None
        ipv4_container = iface.get("ietf-ip:ipv4") or iface.get("ipv4")
        if isinstance(ipv4_container, dict):
            addresses = ipv4_container.get("address", [])
            if addresses and isinstance(addresses, list):
                first = addresses[0]
                ip = first.get("ip")
                netmask = first.get("netmask")
                if ip and netmask:
                    prefixlen = IPv4Interface(f"{ip}/{netmask}").network.prefixlen
                    ipv4 = f"{ip}/{prefixlen}"

        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": name,
                "ipv4": ipv4,
                "description": description,
                "admin_state": admin_state,
            },
        }
    except Exception:
        return {"status": "error", "result": "backend_failed"}

def plan_interface(router,desired_interface,http_get=None):
    """Return create/update/no_change plan using RESTCONF status."""
    return planning_plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, http_get=http_get),
    )

def apply_interface(router,desired_interface,http_put=None):
    """Apply complete desired interface state using RESTCONF."""
    name = desired_interface["name"]
    number = int(name[len("Loopback"):])
    url = (
        f"https://{router}/restconf/data/"
        f"Cisco-IOS-XE-native:native/interface/Loopback={number}"
    )

    ipv4_obj = IPv4Interface(desired_interface["ipv4"])
    payload_content = {
        "name": number,
        "description": desired_interface["description"],
        "ip": {
            "address": {
                "primary": {
                    "address": str(ipv4_obj.ip),
                    "mask": str(ipv4_obj.network.netmask),
                }
            }
        },
    }

    if desired_interface.get("admin_state") == "down":
        payload_content["shutdown"] = [None]

    payload = {"Cisco-IOS-XE-native:Loopback": payload_content}

    if http_put is None:
        user = os.getenv("ROUTER_USER", "")
        password = os.getenv("ROUTER_PASS", "")

        def http_put(u, json):
            return requests.put(
                u,
                json=json,
                auth=(user, password),
                headers={
                    "Content-Type": "application/yang-data+json",
                    "Accept": "application/yang-data+json",
                },
                verify=False,
                timeout=15,
            )

    try:
        resp = http_put(url, json=payload)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    if resp.status_code in (401, 403):
        return {"status": "error", "result": "authentication_failed"}
    if resp.status_code in (200, 201, 204):
        return {"status": "ok", "result": "applied"}
    return {"status": "error", "result": "backend_failed"}