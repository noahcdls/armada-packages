import pathlib
import tempfile
import unittest

import verify
import fetch


class VersionTests(unittest.TestCase):
    def test_version_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = pathlib.Path(directory) / "manifest"
            for contents, accepted in (
                ('"linuxarm64" { "version" "123" }', True),
                ('"linuxarm64" { "version" "124" }', False),
                ('"linuxarm64" {}', False),
                ('"linuxarm64" { "version" "invalid" }', False),
            ):
                with self.subTest(contents=contents):
                    manifest.write_text(contents)
                    if accepted:
                        verify.verify_version(manifest, "123")
                    else:
                        with self.assertRaisesRegex(SystemExit, "version mismatch"):
                            verify.verify_version(manifest, "123")


class OverrideTests(unittest.TestCase):
    def test_mismatched_override_is_rejected(self):
        contents = '"linuxarm64" { "version" "123" }'
        with self.assertRaisesRegex(ValueError, "version differs"):
            fetch.packages(contents, "124")

    def test_override_requires_package_checksums(self):
        contents = '"linuxarm64" { "version" "123" "bins" { "file" "bins.zip.abc" } }'
        with self.assertRaisesRegex(ValueError, "SHA256"):
            fetch.packages(contents, "123")


class ManifestSelectionTests(unittest.TestCase):
    def test_override_or_live_manifest_uses_the_same_package_checks(self):
        import contextlib
        from unittest.mock import patch

        for version, saved_version in (("123", "123"), ("124", "123"), ("123", None)):
            with self.subTest(version=version, saved_version=saved_version), tempfile.TemporaryDirectory() as directory:
                with contextlib.chdir(directory):
                    feed = pathlib.Path("feed")
                    feed.mkdir()
                    contents = ('"linuxarm64" { "version" "' + version
                                + '" "bins" { "file" "bins.zip.abc" "sha2" "' + "a" * 64 + '" } }')
                    if saved_version:
                        pathlib.Path("manifests").mkdir()
                        pathlib.Path("manifests", saved_version).write_text(contents)

                    def download(command, **kwargs):
                        self.assertEqual(command[-1], f"{fetch.CDN}/{fetch.MANIFEST}")
                        (feed / fetch.MANIFEST).write_text(contents)

                    with patch("fetch.subprocess.run", side_effect=download) as request:
                        self.assertEqual(fetch.prepare_manifest(version, feed), [("bins.zip.abc", "a" * 64)])
                        self.assertEqual(request.call_count, int(version != saved_version))

    def test_bad_override_does_not_fall_back_to_network(self):
        import contextlib
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            pathlib.Path("feed").mkdir()
            pathlib.Path("manifests").mkdir()
            pathlib.Path("manifests/123").write_text('"version" "124"')
            with patch("fetch.subprocess.run") as request:
                with self.assertRaises(ValueError):
                    fetch.prepare_manifest("123", pathlib.Path("feed"))
                request.assert_not_called()


class BuildTests(unittest.TestCase):
    def test_generation_is_offline_and_stale_outputs_are_removed(self):
        import json
        import os
        import shutil
        import subprocess

        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                package = root / "steam-bootstrap"
                package.mkdir()
                shutil.copyfile(pathlib.Path(__file__).with_name("build.sh"), package / "build.sh")
                (root / "toolchain.env").write_text("BUILDER_IMAGE=fixture\n")
                (package / "BASE.env").write_text("STEAM_CLIENT_VERSION=123\n")
                (package / "out").mkdir()
                (package / "out/steam-bootstrap.tar.zst").write_text("old archive")
                (package / "out/version").write_text("old version")
                (package / "work").mkdir()
                (package / "work/cache").touch()
                commands = root / "bin"
                commands.mkdir()
                (commands / "uname").write_text("#!/bin/sh\necho aarch64\n")
                (commands / "podman").write_text(
                    "#!/usr/bin/env python3\nimport json, os, sys\n"
                    "with open(os.environ['CALL_LOG'], 'a') as log: log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                    "if os.environ['FAIL_GENERATION'] == '1' and 'generate.sh' in sys.argv: sys.exit(1)\n"
                )
                for command in commands.iterdir():
                    command.chmod(0o755)
                log = root / "calls"
                env = dict(os.environ, PATH=f"{commands}:{os.environ['PATH']}", CALL_LOG=str(log), FAIL_GENERATION=str(int(failure)))
                result = subprocess.run(["bash", str(package / "build.sh")], env=env)
                self.assertEqual(result.returncode, int(failure))
                calls = [json.loads(line) for line in log.read_text().splitlines()]
                self.assertEqual(len(calls), 3)
                self.assertEqual(calls[-1][calls[-1].index("--network") + 1], "none")
                self.assertTrue(any("fetch.py" in arg for arg in calls[-2]))
                self.assertEqual(list((package / "out").iterdir()), [])
                self.assertTrue((package / "work/cache").exists())


if __name__ == "__main__":
    unittest.main()
