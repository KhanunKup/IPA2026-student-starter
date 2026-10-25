from ipaddress import IPv4Interface
import json
import os
from pathlib import Path
import subprocess

def default_run_playbook(variables):
    """Execute Ansible playbook locally or inside container."""
    repo_root = Path(__file__).resolve().parents[2]
    playbook = repo_root / "ansible" / "apply_interface.yml"
    inventory = repo_root / "ansible" / "inventory.ini"
    user = os.getenv("ROUTER_USER", "")
    password = os.getenv("ROUTER_PASS", "")

    extra_vars = {
        **variables,
        "ansible_user": user,
        "ansible_password": password,
        "ansible_host": variables["router"],
    }
    cmd = [
        "ansible-playbook",
        "-i",
        str(inventory),
        str(playbook),
        "--extra-vars",
        json.dumps(extra_vars),
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        out = (res.stdout + res.stderr).lower()
        if "authentication" in out or "permission denied" in out:
            raise PermissionError("Ansible authentication failed")
        elif "unreachable" in out or "timed out" in out or "connection refused" in out:
            raise ConnectionError("Ansible connection failed")
        else:
            raise RuntimeError(f"Ansible playbook execution failed: {res.stderr}")


def apply_interface(router,desired_interface,run_playbook=None):
    """Apply complete desired interface state using Ansible."""
    if run_playbook is None:
        run_playbook = default_run_playbook

    ipv4_obj = IPv4Interface(desired_interface["ipv4"])
    variables = {
        "router": router,
        "interface_name": desired_interface["name"],
        "description": desired_interface["description"],
        "ipv4_address": str(ipv4_obj.ip),
        "netmask": str(ipv4_obj.network.netmask),
        "shutdown": desired_interface.get("admin_state") == "down",
    }

    try:
        run_playbook(variables)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except ConnectionError:
        return {"status": "error", "result": "connection_failed"}
    except Exception as exc:
        exc_name = type(exc).__name__
        if "Authentication" in exc_name:
            return {"status": "error", "result": "authentication_failed"}
        if "Timeout" in exc_name or "Connection" in exc_name or "Unreachable" in exc_name:
            return {"status": "error", "result": "connection_failed"}
        return {"status": "error", "result": "backend_failed"}

    return {"status": "ok", "result": "applied"}
