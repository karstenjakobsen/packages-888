import json
import sys

with open(sys.argv[1], encoding="utf-8") as fixture:
    evidence = json.load(fixture)
rows = iter(evidence["transcript"])

def request(method, request_id, params):
    sent = next(rows)["send"]
    assert sent == {"jsonrpc": "2.0", "method": method, "id": request_id, "params": params}
    reply = next(rows)["receive"]
    assert (reply["jsonrpc"], reply["id"]) == ("2.0", request_id) and "error" not in reply
    return reply["result"]

initial = request("initialize", 1, evidence["transcript"][0]["send"]["params"])
assert initial["protocolVersion"] == "2025-06-18"
assert initial["serverInfo"] == {"name": "mcp-digitalocean", "version": "1.4.1"}
assert "tools" in initial["capabilities"]
assert next(rows)["send"] == {"jsonrpc": "2.0", "method": "notifications/initialized"}

tools, cursors, params = {}, set(), {}
for request_id in range(2, 22):
    page = request("tools/list", request_id, params)
    for tool in page["tools"]:
        assert tool["name"] not in tools
        tools[tool["name"]] = tool
    cursor = page.get("nextCursor")
    if cursor is None:
        break
    assert isinstance(cursor, str) and cursor and cursor not in cursors
    cursors.add(cursor)
    params = {"cursor": cursor}
else:
    raise AssertionError("Discovery exceeded the page limit")

assert next(rows, None) is None
assert len(tools) == evidence["toolCount"] == 55
assert evidence["pages"] == 1 + len(cursors)
assert evidence["apiRequests"] == evidence["exitCode"] == 0
assert evidence["stdinClosed"] and evidence["fixtureClosed"]

required_properties = {
    "domain-create": "Name IPAddress",
    "domain-delete": "Name",
    "domain-get": "Name",
    "domain-list": "",
    "domain-record-create": "Domain Type Name Data",
    "domain-record-delete": "Domain RecordID",
    "domain-record-edit": "Domain RecordID Type Name Data",
    "domain-record-get": "Domain RecordID",
    "domain-record-list": "Domain",
}
assert {name for name in tools if name.startswith("domain-")} == set(required_properties)
for name, fields in required_properties.items():
    schema = tools[name]["inputSchema"]
    required = set(fields.split())
    assert schema["type"] == "object" and set(schema["required"]) == required, name
    optional = {"Page", "PerPage"} if name.endswith("-list") else set()
    assert set(schema["properties"]) == required | optional, name
    for key, prop in schema["properties"].items():
        assert prop["type"] == ("number" if key in optional | {"RecordID"} else "string"), (name, key)
    if optional:
        assert schema["properties"]["Page"]["default"] == 1
        assert schema["properties"]["PerPage"]["default"] == 20

print(f"v1.4.1 discovery: {len(tools)} tools, {evidence['pages']} page(s), 9 DNS inputs, zero API requests, clean shutdown")
