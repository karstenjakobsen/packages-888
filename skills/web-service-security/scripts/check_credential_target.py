"""Compare synthetic credential destinations without performing requests."""

import ipaddress
import re

URL = re.compile(r"(https?)://([^/?#]+)([^#]*)", re.IGNORECASE | re.ASCII)
AUTHORITY = re.compile(r"(\[[0-9a-fA-F:.]+\]|[a-zA-Z0-9.-]+)(?::([0-9]{1,5}))?")
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
NUMERIC_TAIL = re.compile(r"(?:[0-9]+|0x[0-9a-f]*)")
TARGET = re.compile(r"(?:[a-zA-Z0-9._~!$&'()*+,;=:@/?-]|%[0-9a-fA-F]{2})*")


def parse_url(value):
    if type(value) is not str:
        raise ValueError
    match = URL.fullmatch(value)
    if match is None:
        raise ValueError
    scheme, authority, target = match.groups()
    match = AUTHORITY.fullmatch(authority)
    if match is None or TARGET.fullmatch(target) is None or target.startswith("//"):
        raise ValueError
    host, port_text = match.groups()
    host = host.lower()
    if host.startswith("["):
        host = str(ipaddress.IPv6Address(host[1:-1]))
    else:
        labels = host.split(".")
        if len(host) > 253 or any(LABEL.fullmatch(label) is None for label in labels):
            raise ValueError
        if NUMERIC_TAIL.fullmatch(labels[-1]):
            host = str(ipaddress.IPv4Address(host))
    scheme = scheme.lower()
    port = (443 if scheme == "https" else 80) if port_text is None else int(port_text)
    if not 1 <= port <= 65535:
        raise ValueError
    return (scheme, host, port), target


def review(data):
    if type(data) is not dict or set(data) != {"intended_origin", "request_url", "redirects"}:
        raise ValueError
    origin, tail = parse_url(data["intended_origin"])
    if origin[0] != "https" or tail not in ("", "/") or type(data["redirects"]) is not list:
        raise ValueError
    destinations = [parse_url(url)[0] for url in [data["request_url"], *data["redirects"]]]
    if any(destination[0] != "https" for destination in destinations):
        return "blocked https_required"
    if any(destination != origin for destination in destinations):
        return "blocked different_origin"
    return "reviewable same_https_origin"


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
