"""Review synthetic management-access evidence offline."""

GATES = {
    "disable_root_ssh": (
        "alternate_admin_fresh_independent_key_login",
        "alternate_admin_sudo_verified",
        "provider_console_recovery_verified",
        "management_session_retained",
    ),
    "disable_password_ssh": ("affected_accounts_key_logins_verified",),
    "restrict_ssh_path": ("effective_listener_verified", "recoverable_rollback"),
    "operator_core_change": (),
}
FAMILY_GATES = {"ipv4": "ipv4_replacement_tested", "ipv6": "ipv6_replacement_tested"}
FLAGS = {flag for gates in GATES.values() for flag in gates} | set(FAMILY_GATES.values())


def unique_choices(values, allowed):
    return (type(values) is list
            and all(type(item) is str and item in allowed for item in values)
            and len(values) == len(set(values)))


def review(plan):
    if type(plan) is not dict or set(plan) != {"actions", "evidence", "affected_families"}:
        raise ValueError
    actions = plan["actions"]
    evidence = plan["evidence"]
    families = plan["affected_families"]
    if (not unique_choices(actions, GATES) or not unique_choices(families, FAMILY_GATES)
            or type(evidence) is not dict or not evidence.keys() <= FLAGS
            or any(value is not None and type(value) is not bool for value in evidence.values())
            or (families and "restrict_ssh_path" not in actions)):
        raise ValueError
    if not actions:
        return "reviewable no_changes_requested"
    if "operator_core_change" in actions:
        return "external-maintenance operator_core_change"
    required = {flag for action in actions for flag in GATES[action]}
    required.update(FAMILY_GATES[family] for family in families)
    missing = sorted(flag for flag in required if evidence.get(flag) is not True)
    if "restrict_ssh_path" in actions and not families:
        missing.append("affected_families_unknown")
    if missing:
        return "blocked " + ",".join(missing)
    return "reviewable prerequisites_reported"


import json
import sys


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def reject_constant(_):
    raise ValueError


def main():
    try:
        if len(sys.argv) != 2:
            raise ValueError
        with open(sys.argv[1], "rb") as source:
            raw = source.read(16385)
        if len(raw) > 16384:
            raise ValueError
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
        result = review(data)
    except (OSError, ValueError, RecursionError):
        result = "blocked invalid_input"
    print(result)


if __name__ == "__main__":
    main()
