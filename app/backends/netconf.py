from ipaddress import IPv4Interface
import os
import socket
import xml.etree.ElementTree as ET

from app.backends.planning import plan_interface as planning_plan_interface

def get_interface_state(router,interface_name,netconf_get_config=None):
    """Return normalized interface status using NETCONF."""
    filter_xml = (
        '<interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces">\n'
        '  <interface>\n'
        f'    <name>{interface_name}</name>\n'
        '  </interface>\n'
        '</interfaces>'
    )

    if netconf_get_config is None:
        user = os.getenv("ROUTER_USER", "")
        password = os.getenv("ROUTER_PASS", "")

        def netconf_get_config(r, f_xml):
            from ncclient import manager
            with manager.connect(
                host=r,
                port=830,
                username=user,
                password=password,
                hostkey_verify=False,
                timeout=15,
            ) as m:
                resp = m.get_config(source="running", filter=("subtree", f_xml))
                return resp.xml

    try:
        xml_text = netconf_get_config(router, filter_xml)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, socket.timeout, TimeoutError):
        return {"status": "error", "result": "connection_failed"}
    except Exception as exc:
        exc_name = type(exc).__name__
        if "Authentication" in exc_name:
            return {"status": "error", "result": "authentication_failed"}
        if "SSH" in exc_name or "SessionClose" in exc_name or "Timeout" in exc_name or "Connection" in exc_name:
            return {"status": "error", "result": "connection_failed"}
        return {"status": "error", "result": "backend_failed"}

    try:
        root = ET.fromstring(xml_text)
        iface_elem = root.find(".//{urn:ietf:params:xml:ns:yang:ietf-interfaces}interface")
        if iface_elem is None:
            return {"status": "ok", "result": "not_found", "interface": None}

        name_elem = iface_elem.find("{urn:ietf:params:xml:ns:yang:ietf-interfaces}name")
        name = name_elem.text.strip() if (name_elem is not None and name_elem.text) else interface_name

        desc_elem = iface_elem.find("{urn:ietf:params:xml:ns:yang:ietf-interfaces}description")
        description = desc_elem.text.strip() if (desc_elem is not None and desc_elem.text) else None

        enabled_elem = iface_elem.find("{urn:ietf:params:xml:ns:yang:ietf-interfaces}enabled")
        if enabled_elem is not None and enabled_elem.text and enabled_elem.text.strip().lower() == "false":
            admin_state = "down"
        else:
            admin_state = "up"

        ip_elem = iface_elem.find(".//{urn:ietf:params:xml:ns:yang:ietf-ip}ip")
        mask_elem = iface_elem.find(".//{urn:ietf:params:xml:ns:yang:ietf-ip}netmask")
        if ip_elem is not None and ip_elem.text and mask_elem is not None and mask_elem.text:
            ip = ip_elem.text.strip()
            mask = mask_elem.text.strip()
            prefixlen = IPv4Interface(f"{ip}/{mask}").network.prefixlen
            ipv4 = f"{ip}/{prefixlen}"
        else:
            ipv4 = None

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


def plan_interface(router,desired_interface,netconf_get_config=None):
    """Return create/update/no_change plan using NETCONF status."""
    return planning_plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, netconf_get_config=netconf_get_config),
    )

def apply_interface(router,desired_interface,netconf_edit_config=None):
    """Apply complete desired interface state using NETCONF."""
    name = desired_interface["name"]
    number = name[len("Loopback"):].strip()
    ipv4_obj = IPv4Interface(desired_interface["ipv4"])
    address = str(ipv4_obj.ip)
    mask = str(ipv4_obj.network.netmask)
    description = desired_interface["description"]
    shutdown_line = "\n            <shutdown/>" if desired_interface.get("admin_state") == "down" else ""

    config_xml = (
        '<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">\n'
        '  <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">\n'
        '    <interface>\n'
        '      <Loopback nc:operation="replace">\n'
        f'        <name>{number}</name>\n'
        f'        <description>{description}</description>\n'
        '        <ip>\n'
        '          <address>\n'
        '            <primary>\n'
        f'              <address>{address}</address>\n'
        f'              <mask>{mask}</mask>\n'
        '            </primary>\n'
        '          </address>\n'
        f'        </ip>{shutdown_line}\n'
        '      </Loopback>\n'
        '    </interface>\n'
        '  </native>\n'
        '</config>'
    )

    if netconf_edit_config is None:
        user = os.getenv("ROUTER_USER", "")
        password = os.getenv("ROUTER_PASS", "")

        def netconf_edit_config(r, c_xml):
            from ncclient import manager
            with manager.connect(
                host=r,
                port=830,
                username=user,
                password=password,
                hostkey_verify=False,
                timeout=15,
            ) as m:
                m.edit_config(target="running", config=c_xml)

    try:
        netconf_edit_config(router, config_xml)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, socket.timeout, TimeoutError):
        return {"status": "error", "result": "connection_failed"}
    except Exception as exc:
        exc_name = type(exc).__name__
        if "Authentication" in exc_name:
            return {"status": "error", "result": "authentication_failed"}
        if "SSH" in exc_name or "SessionClose" in exc_name or "Timeout" in exc_name or "Connection" in exc_name:
            return {"status": "error", "result": "connection_failed"}
        return {"status": "error", "result": "backend_failed"}

    return {"status": "ok", "result": "applied"}