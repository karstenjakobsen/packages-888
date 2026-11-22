"""Exercise the real pinned release offline when its four public inputs are available."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT.parents[1] / "connectors/local-nomad"))
import batch
import install
import release

BUNDLE = os.environ.get("NOMAD_TEST_RELEASE_DIR")


@unittest.skipUnless(BUNDLE, "set NOMAD_TEST_RELEASE_DIR to the cached public release bundle")
class SignedBundleTest(unittest.TestCase):
    def test_signed_install_material_and_job_render(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "cluster"
            private = root / "private"
            corrupt = True

            def download(url, target):
                shutil.copyfile(Path(BUNDLE) / target.name, target)
                if corrupt and target.name == release.SIGNATURE:
                    with target.open("r+b") as signature:
                        signature.write(b"broken")

            old_umask = os.umask(0o077)
            self.addCleanup(os.umask, old_umask)
            with patch.object(install, "ROOT", root), patch.object(release, "download", download):
                with self.assertRaises(subprocess.CalledProcessError):
                    install.prepare(os.getuid())
                self.assertFalse(root.exists())
                corrupt = False
                record = install.prepare(os.getuid())

            binary = private / "nomad"
            self.assertIn("Nomad v" + record["version"], install.run([binary, "version"]))
            self.assertEqual(record["nomad"], release.sha256(binary))
            install.check_private_state(private)
            self.assertEqual(len(install.secret_file(private / "management.token")), 36)
            # Instantiate a real connector TLS context with the generated CA and CLI pair.
            install.Api(private)
            config = private / "agent.hcl"
            config.write_text(config.read_text().replace("/var/lib/catalog-nomad", str(root)))
            install.run([binary, "config", "validate", config])

            job = batch.job_spec("squares", (PROJECT / "examples/squares.py").read_bytes())
            rendered = install.run([binary, "job", "run", "-output", "-json", "-"],
                                   input=json.dumps({"Job": job}))
            spec = json.loads(rendered)["Job"]
            self.assertEqual(spec["ID"], job["ID"])
            task = spec["TaskGroups"][0]["Tasks"][0]
            original = job["TaskGroups"][0]["Tasks"][0]
            self.assertEqual(task["Config"], original["Config"])
            template, = task["Templates"]
            for key, value in original["Templates"][0].items():
                self.assertEqual(template[key], value)
            (private / "bootstrap.pending").unlink()
            with self.assertRaisesRegex(RuntimeError, "Raft database"):
                install.check_private_state(private)
