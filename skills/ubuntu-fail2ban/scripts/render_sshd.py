"""Render an SSH jail in a private staging directory."""
import argparse
import ipaddress
import json
from pathlib import Path
import re
import sys


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def integer(value, name, upper):
    if type(value) is not int or not 1 <= value <= upper:
        raise ValueError(f"{name} must be an integer from 1 to {upper}")
    return value


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F.:]+(?:/[0-9]+)?", value):
        raise ValueError("allowlist entries must be literal IP addresses or CIDRs")
    if "/" in value:
        return str(ipaddress.ip_network(value, strict=True))
    return str(ipaddress.ip_address(value))


def render(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    backend = data.get("backend")
    if backend not in ("systemd", "polling"):
        raise ValueError("backend must be systemd or polling")
    keys = {"backend", "ports", "allowlist", "banaction", "maxretry", "findtime", "bantime"}
    if backend == "polling":
        keys.add("logpath")
    if data.keys() != keys:
        raise ValueError("missing or unexpected keys for selected backend")

    ports = data["ports"]
    if not isinstance(ports, list) or not ports:
        raise ValueError("ports must be a nonempty array")
    ports = sorted({integer(port, "port", 65535) for port in ports})
    allowlist = data["allowlist"]
    if not isinstance(allowlist, list) or not allowlist:
        raise ValueError("allowlist must be a nonempty array")
    allowlist = sorted({address(entry) for entry in allowlist})
    action = data["banaction"]
    if not isinstance(action, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", action):
        raise ValueError("banaction must be a simple installed action name")
    lines = [
        "[sshd]", "enabled = true", "filter = sshd", f"backend = {backend}",
        "protocol = tcp", "port = " + ",".join(map(str, ports)),
        "ignoreip = " + " ".join(allowlist), f"banaction = {action}",
    ]
    for key in ("maxretry", "findtime", "bantime"):
        lines.append(f"{key} = {integer(data[key], key, 2147483647)}")
    if backend == "polling":
        logpath = data["logpath"]
        if (not isinstance(logpath, str)
                or not re.fullmatch(r"(?:/[A-Za-z0-9_.-]+)+", logpath)
                or any(part in (".", "..") for part in logpath.split("/"))):
            raise ValueError("logpath must be a literal absolute file path")
        lines.append(f"logpath = {logpath}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve() or (
            args.output.exists() and args.output.samefile(args.input)
        ):
            raise ValueError("input and output must be distinct")
        data = json.loads(args.input.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        rendered = render(data)
        args.output.write_bytes(rendered.encode("utf-8"))
    except (OSError, ValueError) as error:
        print(f"render_sshd: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
