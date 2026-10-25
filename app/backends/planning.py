from app.planner import build_plan

def plan_interface(router,desired_interface,get_interface_state):
    """Build a Part 2 plan from backend status."""
    status_response = get_interface_state(router, desired_interface["name"])
    if status_response.get("status") != "ok":
        return status_response

    if status_response.get("result") == "not_found":
        current_interface = None
    else:
        current_interface = status_response.get("interface")

    return build_plan(desired_interface, current_interface)
