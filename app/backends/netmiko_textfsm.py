import os
import socket

def get_interface_state(router,interface_name,netmiko_get=None):
    """Return normalized interface status using Netmiko + TextFSM."""
    if netmiko_get is None:
        user = os.getenv("ROUTER_USER", "")
        password = os.getenv("ROUTER_PASS", "")

        def netmiko_get(r, iface_name):
            from netmiko import ConnectHandler
            device = {
                "device_type": "cisco_ios",
                "host": r,
                "username": user,
                "password": password,
                "fast_cli": False,
            }
            with ConnectHandler(**device) as net_connect:
                ip_info = net_connect.send_command(
                    f"show ip interface {iface_name}",
                    use_textfsm=True,
                )
                descriptions = net_connect.send_command(
                    "show interfaces description",
                    use_textfsm=True,
                )
                return (
                    ip_info if isinstance(ip_info, list) else [],
                    descriptions if isinstance(descriptions, list) else [],
                )

    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, socket.timeout, TimeoutError):
        return {"status": "error", "result": "connection_failed"}
    except Exception as exc:
        exc_name = type(exc).__name__
        if "Authentication" in exc_name:
            return {"status": "error", "result": "authentication_failed"}
        if "Timeout" in exc_name or "Connection" in exc_name:
            return {"status": "error", "result": "connection_failed"}
        return {"status": "error", "result": "backend_failed"}

    if not ip_info or not isinstance(ip_info, list):
        return {"status": "ok", "result": "not_found", "interface": None}

    entry = ip_info[0]
    if not isinstance(entry, dict) or not entry.get("interface"):
        return {"status": "ok", "result": "not_found", "interface": None}

    link_status = str(entry.get("link_status", "")).lower()
    if "administratively down" in link_status:
        admin_state = "down"
    else:
        admin_state = "up"

    ip_addresses = entry.get("ip_address", [])
    prefixes = entry.get("prefix_length", [])
    if ip_addresses and prefixes:
        ipv4 = f"{ip_addresses[0]}/{prefixes[0]}"
    else:
        ipv4 = None

    short_name = interface_name
    if interface_name.lower().startswith("loopback"):
        short_name = "Lo" + interface_name[len("Loopback"):]

    desc_val = None
    if isinstance(descriptions, list):
        for d in descriptions:
            if isinstance(d, dict):
                port = str(d.get("port", "")).strip()
                if port.lower() in (interface_name.lower(), short_name.lower()):
                    desc_val = d.get("description")
                    break

    return {
        "status": "ok",
        "result": "found",
        "interface": {
            "name": interface_name,
            "ipv4": ipv4,
            "description": desc_val,
            "admin_state": admin_state,
        },
    }


def delete_interface(router,interface_name,netmiko_delete=None):
    """Delete an interface using Netmiko."""
    if netmiko_delete is None:
        user = os.getenv("ROUTER_USER", "")
        password = os.getenv("ROUTER_PASS", "")

        def netmiko_delete(r, iface_name):
            st = get_interface_state(r, iface_name)
            if st.get("status") == "ok" and st.get("result") == "not_found":
                return "not_found"

            from netmiko import ConnectHandler
            device = {
                "device_type": "cisco_ios",
                "host": r,
                "username": user,
                "password": password,
                "fast_cli": False,
            }
            with ConnectHandler(**device) as net_connect:
                net_connect.send_config_set([f"no interface {iface_name}"])

            st2 = get_interface_state(r, iface_name)
            if st2.get("status") == "ok" and st2.get("result") == "not_found":
                return "deleted"
            raise RuntimeError(f"Failed to delete interface {iface_name}")

    try:
        del_result = netmiko_delete(router, interface_name)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, socket.timeout, TimeoutError):
        return {"status": "error", "result": "connection_failed"}
    except Exception as exc:
        exc_name = type(exc).__name__
        if "Authentication" in exc_name:
            return {"status": "error", "result": "authentication_failed"}
        if "Timeout" in exc_name or "Connection" in exc_name:
            return {"status": "error", "result": "connection_failed"}
        return {"status": "error", "result": "backend_failed"}

    if del_result == "deleted":
        return {"status": "ok", "result": "deleted"}
    if del_result == "not_found":
        return {"status": "ok", "result": "not_found", "interface": None}

    return {"status": "error", "result": "backend_failed"}
