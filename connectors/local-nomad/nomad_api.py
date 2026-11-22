"""Small HTTPS transport shared by the local installer and batch connector."""
import http.client
import json
import os
import ssl
import time
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

ROOT = Path("/var/lib/catalog-nomad")
NAMESPACE = "catalog-projects"
POLICY = "catalog-batch"
PEER = "127.0.0.1:4647"


class ApiError(RuntimeError):
    def __init__(self, status, method, path):
        self.status = status
        super().__init__(f"Nomad returned HTTP {status} for {method} {path}")


class Api:
    def __init__(self, cert_dir, token=None):
        self.token = token
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.context.load_verify_locations(cafile=cert_dir / "nomad-agent-ca.pem")
        self.context.load_cert_chain(cert_dir / "global-cli-nomad.pem",
                                     cert_dir / "global-cli-nomad-key.pem")

    def call(self, method, path, body=None, *, query=None, plain=False):
        # Fixed destination, pinned CA, no redirects, proxy or ambient Nomad token.
        conn = http.client.HTTPSConnection("127.0.0.1", 4646, timeout=8, context=self.context)
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Nomad-Token"] = self.token
        target = path + ("?" + urlencode(query) if query else "")
        try:
            conn.request(method, target, json.dumps(body) if body is not None else None, headers)
            with conn.getresponse() as response:
                if not 200 <= response.status < 300:
                    # ACL response bodies may contain credentials.
                    raise ApiError(response.status, method, path)
                limit = 1 << 20 if plain else 8 << 20
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise RuntimeError(f"Nomad response exceeded {limit} bytes")
                if plain:
                    return data.decode("utf-8", errors="replace")
                return json.loads(data) if data else None
        finally:
            conn.close()


def secret_file(path):
    with path.open() as f:
        if os.fstat(f.fileno()).st_mode & 0o077:
            raise RuntimeError(f"Restrict permissions on {path}")
        return str(UUID(f.read(128).strip()))


def until(check, seconds, description):
    deadline = time.monotonic() + seconds
    reason = description
    while True:
        try:
            result = check()
            if result:
                return result
        except ApiError as exc:
            if exc.status not in (500, 502, 503, 504):
                raise
            reason = str(exc)
        except ssl.SSLError:
            raise
        except (ConnectionError, TimeoutError) as exc:
            reason = str(exc)
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Timed out waiting for {description} ({reason})")
        time.sleep(1)


def ready(api):
    if api.call("GET", "/v1/status/leader") != PEER or api.call("GET", "/v1/status/peers") != [PEER]:
        return None
    nodes = api.call("GET", "/v1/nodes") or []
    if len(nodes) != 1:
        return None
    node = api.call("GET", "/v1/node/" + str(UUID(nodes[0]["ID"])))
    driver = (node.get("Drivers") or {}).get("docker") or {}
    if (node.get("Status") == "ready" and node.get("SchedulingEligibility") == "eligible"
            and not node.get("DrainStrategy") and driver.get("Detected") and driver.get("Healthy")):
        return {"leader": PEER, "node": node["ID"], "docker": "healthy"}
    return None
