"""Install just the pinned Linux AMD64 binary from a verified HashiCorp archive."""
import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "2.1.1"
ARCHIVE = f"nomad_{VERSION}_linux_amd64.zip"
SUMS = f"nomad_{VERSION}_SHA256SUMS"
SIGNATURE = SUMS + ".72D7468F.sig"
BASE = f"https://releases.hashicorp.com/nomad/{VERSION}/"
DIGEST = "073084f7690fdaea756ff1eff8b669b25c3a6c17778f19ae0c47606973ed3f39"
FINGERPRINT = "C874011F0AB405110D02105534365D9472D7468F"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(url, path):
    with urllib.request.urlopen(url, timeout=45) as response, path.open("xb") as f:
        if not response.geturl().startswith("https://"):
            raise RuntimeError("Release download requires HTTPS")
        shutil.copyfileobj(response, f)


def verify(directory):
    keyring = directory / "hashicorp.gpg"
    gpg = ["gpg", "--batch", "--no-options", "--homedir", str(directory), "--no-autostart"]
    subprocess.run(gpg + ["--dearmor", "--output", str(keyring), "hashicorp.asc"],
                   cwd=directory, capture_output=True, check=True)
    signed = subprocess.run(gpg + ["--no-default-keyring", "--keyring", str(keyring), "--no-auto-key-retrieve",
                                   "--status-fd", "1", "--verify", SIGNATURE, SUMS], cwd=directory,
                            capture_output=True, text=True, check=True)
    fingerprints = [line.split()[-1] for line in signed.stdout.splitlines()
                    if line.startswith("[GNUPG:] VALIDSIG ")]
    invalid = ("EXPSIG", "EXPKEYSIG", "REVKEYSIG", "BADSIG", "ERRSIG")
    if fingerprints != [FINGERPRINT] or any(f"[GNUPG:] {code} " in signed.stdout for code in invalid):
        raise RuntimeError("Checksum manifest signature does not match the pinned HashiCorp key")
    entries = [line.split() for line in (directory / SUMS).read_text().splitlines()]
    hashes = [entry[0] for entry in entries if len(entry) == 2 and entry[1] == ARCHIVE]
    if hashes != [DIGEST] or sha256(directory / ARCHIVE) != DIGEST:
        raise RuntimeError("Nomad release checksum mismatch")


def install_binary(destination):
    # This directory and the staging binary are on the target filesystem outside Git.
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        directory = Path(temp)
        download("https://www.hashicorp.com/.well-known/pgp-key.txt", directory / "hashicorp.asc")
        for name in (SUMS, SIGNATURE, ARCHIVE):
            download(BASE + name, directory / name)
        verify(directory)
        with (zipfile.ZipFile(directory / ARCHIVE) as archive, archive.open("nomad") as source,
              (directory / "nomad").open("xb") as binary):
            shutil.copyfileobj(source, binary)
        (directory / "nomad").chmod(0o700)
        os.replace(directory / "nomad", destination)
