"""Check the installed CLI and working-directory based configuration."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cnblogs_dump import cli
from cnblogs_dump.config import load_api_config


class CliTest(unittest.TestCase):
    """Verify process-level entry points without calling a hosted service."""

    def test_installed_help_outside_project(self):
        """The console script must work outside the repository."""
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(["cnblogs", "--help"], cwd=directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("backup", "upload", "images", "database"):
            self.assertIn(command, result.stdout)

    def test_dry_run_uses_cwd_without_credentials(self):
        """A local dry-run must not need API settings or write a snapshot."""
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "posts"
            output.mkdir()
            content = json.dumps({"endpoint": "https://example.com", "blog_id": "42", "posts": {}})
            (output / ".backup.json").write_text(content)
            environment = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("CNBLOGS_") and key not in ("TOKEN", "USERNAME")
            }
            result = subprocess.run(
                ["cnblogs", "upload", "--dry-run", "--output", "posts"],
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual((output / ".backup.json").read_text(), content)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0 changed posts", result.stdout)

    def test_invalid_dry_run_does_not_dispatch(self):
        """Reject unsupported dry-run commands before accessing files or credentials."""
        with (
            patch("sys.argv", ["cnblogs", "backup", "--dry-run"]),
            patch.object(cli, "_run") as dispatch,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as error:
                cli.main()
        self.assertEqual(error.exception.code, 2)
        dispatch.assert_not_called()

    def test_api_error_does_not_expose_credentials(self):
        """Only the fault code should reach the CLI error message."""
        import xmlrpc.client

        with (
            patch("sys.argv", ["cnblogs", "backup"]),
            patch.object(cli, "_run", side_effect=xmlrpc.client.Fault(401, "secret-token")),
        ):
            with self.assertRaises(SystemExit) as error:
                cli.main()
        self.assertIn("401", str(error.exception))
        self.assertNotIn("secret-token", str(error.exception))

    def test_config_explicit_endpoint_and_redacted_repr(self):
        """An explicit endpoint wins and the token is excluded from repr."""
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.chdir(directory),
            patch.dict(
                os.environ,
                {
                    "CNBLOGS_USERNAME": "login",
                    "CNBLOGS_TOKEN": "secret-token",
                    "CNBLOGS_BLOG_NAME": "ignored",
                    "CNBLOGS_URL": "https://rpc.cnblogs.com/metaweblog/example",
                },
                clear=True,
            ),
        ):
            config = load_api_config()
        self.assertEqual(config.endpoint, "https://rpc.cnblogs.com/metaweblog/example")
        self.assertNotIn("secret-token", repr(config))

    def test_missing_credentials_fail_before_network(self):
        """Missing settings produce an actionable error without an API request."""
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.chdir(directory),
            patch.dict(os.environ, {}, clear=True),
        ):
            with self.assertRaisesRegex(ValueError, "CNBLOGS_USERNAME and CNBLOGS_TOKEN"):
                load_api_config()


if __name__ == "__main__":
    unittest.main()
