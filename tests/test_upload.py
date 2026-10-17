"""Exercise full-export baselines and uploads through a local XML-RPC server."""

import contextlib
import copy
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
import xmlrpc.client
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

import yaml

from cnblogs_tools import config, database, post_files, upload
from cnblogs_tools.metaweblog import MetaWeblogClient


class Handler(SimpleXMLRPCRequestHandler):
    """Accept the same path shape as the hosted service."""

    rpc_paths = ("/metaweblog/example",)


class UploadTest(unittest.TestCase):
    """Verify upload baselines, XML encoding, and update behavior."""

    def setUp(self):
        """Create isolated files and a local service for each test."""
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name) / "blogs"
        self._edits: list[tuple[str, dict[str, Any], bool]] = []
        self.failure: bool = False
        self.posts: dict[str, dict[str, Any]] = {
            "1": {
                "postid": 1,
                "title": "A & <B>",
                "description": "# Original\r\n\r\nA & <B>\r\n---\r\nEnd",
                "dateCreated": xmlrpc.client.DateTime("20250102T03:04:05"),
                "categories": ["[Markdown]", "Category"],
                "mt_keywords": "one,two",
                "mt_excerpt": "Summary",
                "mt_text_more": "",
            },
            "2": {
                "postid": 2,
                "title": "HTML",
                "description": "<p>Hello &amp; goodbye</p>",
                "dateCreated": xmlrpc.client.DateTime("20250102T03:04:05"),
                "categories": ["Category"],
                "mt_keywords": "",
                "mt_excerpt": "",
                "mt_text_more": "",
            },
        }
        self.http: SimpleXMLRPCServer = SimpleXMLRPCServer(("127.0.0.1", 0), requestHandler=Handler, logRequests=False)
        self.http.register_function(cast(Any, self._get_post), "metaWeblog.getPost")
        self.http.register_function(cast(Any, self._edit_post), "metaWeblog.editPost")
        self.thread: threading.Thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint: str = f"http://127.0.0.1:{self.http.server_address[1]}/metaweblog/example"
        self.client: MetaWeblogClient = MetaWeblogClient(config.ApiConfig("login", "secret<&>", self.endpoint))

    def tearDown(self):
        """Close the local service and remove temporary files."""
        self.client.close()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def _auth(self, username: str, token: str) -> None:
        """Verify credentials decoded from the XML-RPC request."""
        self.assertEqual((username, token), ("login", "secret<&>"))

    def _get_post(self, post_id: str, username: str, token: str) -> dict[str, Any]:
        """Return a fixture post after validating its ID type."""
        self._auth(username, token)
        self.assertIsInstance(post_id, str)
        return self.posts[post_id]

    def _edit_post(self, post_id: str, username: str, token: str, post: dict[str, Any], publish: bool) -> bool:
        """Record an update and simulate success or an API fault."""
        self._auth(username, token)
        self._edits.append((post_id, copy.deepcopy(post), publish))
        if self.failure:
            raise xmlrpc.client.Fault(500, "Update failed")
        self.posts[post_id].update(post)
        return True

    def _backup(self) -> None:
        """Create a complete-export baseline for the fixture posts."""
        self.output.mkdir(parents=True, exist_ok=True)
        snapshot: dict[str, Any] = {"blog_id": "42", "posts": {}}
        for post_id, post in self.posts.items():
            metadata = {
                "id": int(post_id),
                "title": post["title"],
                "date": str(post["dateCreated"]),
                "blog_id": 42,
                "is_markdown": "[Markdown]" in post["categories"],
                "is_active": True,
                "access_permission": "Anonymous",
            }
            front_matter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=True)
            content = f"---\n{front_matter}---\n{post['description']}"
            target = self.output / f"{post_id}.md"
            if not target.exists() or post_files.read_post(target) != content:
                target.write_text(content, encoding="utf-8")
            snapshot["posts"][post_id] = {"hash": post_files.digest(content)}
        (self.output / ".backup.json").write_text(json.dumps(snapshot), encoding="utf-8")

    def _upload(self, dry_run: bool = False) -> None:
        """Run an upload or local dry-run without progress output."""
        with contextlib.redirect_stdout(io.StringIO()):
            upload.upload_posts(None if dry_run else self.client, self.output, dry_run)

    def _edit(self, post_id: str = "1", publish: bool = True) -> None:
        """Modify a fixture post and explicitly choose its publication flag."""
        target = self.output / f"{post_id}.md"
        metadata, body = post_files.parse_post(post_files.read_post(target))
        metadata["publish"] = publish
        front_matter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=True)
        target.write_text(f"---\n{front_matter}---\n{body}\nNew text & <tag>", encoding="utf-8")

    def test_backup_preserves_format_and_is_idempotent(self):
        """Verify backup preserves format and is idempotent."""
        self._backup()
        for post_id in self.posts:
            meta, body = post_files.parse_post(post_files.read_post(self.output / f"{post_id}.md"))
            self.assertEqual(body, self.posts[post_id]["description"])
            self.assertNotIn("publish", meta)
            self.assertEqual(meta["access_permission"], "Anonymous")
        self.assertFalse(post_files.parse_post(post_files.read_post(self.output / "2.md"))[0]["is_markdown"])
        before = (self.output / "1.md").stat().st_mtime_ns
        self._backup()
        self.assertEqual(before, (self.output / "1.md").stat().st_mtime_ns)
        self.assertNotIn("secret", (self.output / ".backup.json").read_text())

    def test_successful_upload_preserves_categories_and_updates_baseline(self):
        """Verify successful upload preserves categories and updates baseline."""
        self._backup()
        self._edit()
        self._upload()
        self.assertEqual(len(self._edits), 1)
        _, post, publish = self._edits[0]
        self.assertTrue(publish)
        self.assertEqual(post["categories"], ["[Markdown]", "Category"])
        self.assertEqual(post["mt_keywords"], "one,two")
        self.assertEqual(post["mt_text_more"], "")
        self.assertEqual(post["title"], "A & <B>")
        self.assertIsInstance(post["dateCreated"], xmlrpc.client.DateTime)
        self._upload()
        self.assertEqual(len(self._edits), 1)

    def test_html_upload_and_draft_intent(self):
        """Verify html upload and draft intent."""
        self._backup()
        self._edit("2", publish=False)
        self._upload()
        self.assertFalse(self._edits[0][2])
        self.assertNotIn("[Markdown]", self._edits[0][1]["categories"])
        self.assertTrue(self._edits[0][1]["description"].startswith("<p>"))

    def test_missing_publish_skips_only_that_post(self):
        """Verify a post without explicit publication intent is skipped."""
        self._backup()
        self._edit("1")
        target = self.output / "2.md"
        target.write_text(
            post_files.read_post(target).replace("access_permission: null", "access_permission: Anonymous")
            + "\nChanged"
        )
        self._upload()
        self.assertEqual([edit[0] for edit in self._edits], ["1"])
        self._upload(dry_run=True)
        self.assertEqual([edit[0] for edit in self._edits], ["1"])

    def test_private_permission_skips_only_that_post(self):
        """Skip private posts while uploading eligible public posts."""
        self._backup()
        self._edit("1")
        self._edit("2", publish=False)
        target = self.output / "2.md"
        target.write_text(
            post_files.read_post(target).replace("access_permission: Anonymous", "access_permission: OwnerByUser")
        )
        with patch.object(self.client, "get_post", wraps=self.client.get_post) as get_post:
            self._upload()
            get_post.assert_called_once_with("1")
        self.assertEqual([edit[0] for edit in self._edits], ["1"])

    def test_unknown_permissions_skip_upload(self):
        """Skip posts with missing or unknown visibility metadata."""
        self._backup()
        self._edit()
        target = self.output / "1.md"
        original = post_files.read_post(target)
        for permission in ("access_permission: null\n", ""):
            with self.subTest(permission=permission):
                target.write_text(original.replace("access_permission: Anonymous\n", permission))
                self._upload()
        self.assertEqual(self._edits, [])

    def test_dry_run_reports_skipped_permissions_without_network(self):
        """Show visibility restrictions without requiring a live client."""
        self._backup()
        self._edit()
        target = self.output / "1.md"
        target.write_text(
            post_files.read_post(target).replace("access_permission: Anonymous", "access_permission: OwnerByUser")
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            upload.upload_posts(None, self.output, dry_run=True)
        self.assertIn("1 private or unknown skipped", output.getvalue())
        self.assertIn("Private or unknown IDs: 1", output.getvalue())
        self.assertEqual(self._edits, [])

    def test_upload_uses_current_remote_fields(self):
        """Verify upload preserves fields from the current remote post."""
        self._backup()
        self._edit("1")
        self._edit("2")
        self.posts["2"]["title"] = "Remote change"
        self._upload()
        self.assertEqual(len(self._edits), 2)

    def test_fault_does_not_advance_baseline(self):
        """Verify fault does not advance baseline."""
        self._backup()
        before = (self.output / ".backup.json").read_text()
        self._edit()
        self.failure = True
        with self.assertRaises(xmlrpc.client.Fault):
            self._upload()
        self.assertEqual(before, (self.output / ".backup.json").read_text())

    def test_credentials_precedence_and_aliases(self):
        """Verify credentials precedence and aliases."""
        previous = Path.cwd()
        os.chdir(self.temp.name)
        try:
            Path(".env").write_text("CNBLOGS_USERNAME=file-user\nCNBLOGS_TOKEN=file-token\nCNBLOGS_BLOG_NAME=example\n")
            with patch.dict(os.environ, {"CNBLOGS_USERNAME": "env-user", "CNBLOGS_TOKEN": "env-token"}, clear=True):
                self.assertEqual(
                    config.load_api_config(),
                    config.ApiConfig("env-user", "env-token", "https://rpc.cnblogs.com/metaweblog/example"),
                )
            Path(".env").write_text("USERNAME=legacy-user\nTOKEN=legacy-token\n")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    config.load_api_config(),
                    config.ApiConfig("legacy-user", "legacy-token", "https://rpc.cnblogs.com/metaweblog/legacy-user"),
                )
        finally:
            os.chdir(previous)

    def test_database_requires_backup_directory(self):
        """Report the expected location when there are no backups."""
        with contextlib.chdir(self.temp.name):
            with self.assertRaisesRegex(FileNotFoundError, "backups/"):
                database.convert_database(self.output)

    def test_legacy_sqlite_conversion(self):
        """Verify legacy sqlite conversion."""
        columns = [
            "Id",
            "Title",
            "DateAdded",
            "DateUpdated",
            "BlogId",
            "PostType",
            "IsMarkdown",
            "IsActive",
            "AccessPermission",
            "SourceUrl",
            "Description",
            "EntryName",
            "CreatedTime",
            "AutoDesc",
            "Body",
        ]
        row = (
            1,
            "Legacy",
            "2025-01-02 03:04:05",
            "2025-01-02 03:04:05",
            42,
            1,
            1,
            1,
            0,
            "",
            "",
            "",
            "",
            "",
            "# Legacy",
        )
        backup_dir = Path(self.temp.name) / "backups"
        backup_dir.mkdir()
        db_path = backup_dir / "cnblogs_blog_test.20261017141356.db"
        with contextlib.closing(sqlite3.connect(db_path)) as db, db:
            db.execute("CREATE TABLE blog_Content (" + ",".join(columns) + ")")
            db.execute("INSERT INTO blog_Content VALUES (" + ",".join("?" for _ in row) + ")", row)
        # A newer filesystem timestamp must not override the export timestamp.
        older = backup_dir / "cnblogs_blog_test.20260701015053.db"
        with contextlib.closing(sqlite3.connect(older)) as db, db:
            db.execute("CREATE TABLE blog_Content (" + ",".join(columns) + ")")
            older_row: list[object] = list(row)
            older_row[1] = "Older"
            older_row[-1] = "Older export"
            db.execute("INSERT INTO blog_Content VALUES (" + ",".join("?" for _ in row) + ")", older_row)
        os.utime(db_path, (1, 1))
        (Path(self.temp.name) / "cnblogs_blog_test.20270101000000.db").write_text("Ignore root files")
        previous = Path.cwd()
        os.chdir(self.temp.name)
        try:
            database.convert_database(self.output)
            self.assertTrue((self.output / "1.md").read_text().endswith("# Legacy"))
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
