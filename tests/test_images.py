"""Verify image downloads, caching, and Markdown updates with local HTTP."""

import contextlib
import io
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.request import urlopen

from cnblogs_tools import cli, images, post_files


class ImagesTest(unittest.TestCase):
    """Check behavior through actual HTTP response objects."""

    def setUp(self):
        """Create isolated files and a local service for each test."""
        self.temp = tempfile.TemporaryDirectory()
        self.posts = Path(self.temp.name) / "blogs"
        self.posts.mkdir()
        self.images = Path(self.temp.name) / "image-hosting"
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                """Serve image bytes or a deliberate HTTP failure."""
                owner.requests.append(self.path)
                if self.path.endswith("missing.png"):
                    self.send_error(404)
                    return
                body = self.path.encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                """Keep HTTP fixture logs out of test output."""
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        base = f"http://127.0.0.1:{self.server.server_port}"
        self.fetch = patch.object(
            images, "urlopen", side_effect=lambda url, timeout: urlopen(base + urlsplit(url).path, timeout=timeout)
        )
        self.fetch.start()

    def tearDown(self):
        """Close the local service and remove temporary files."""
        self.fetch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def _migrate(self):
        """Run image migration against the local HTTP fixture."""
        with contextlib.redirect_stdout(io.StringIO()):
            images.migrate_images(self.posts, "https://example.com/", self.images)

    def test_preserves_metadata_and_separates_same_filename(self):
        """Verify preserves metadata and separates same filename."""
        first = "https://s2.loli.net/2025/01/01/same-name.png"
        second = "https://s2.loli.net/2025/01/02/same-name.png"
        prefix = '---\r\nid: 1\r\ntitle: "中文"\r\nsource_url: ' + first + "\r\n---\r\n"
        target = self.posts / "1.md"
        target.write_bytes((prefix + f"![a]({first})\r\n![b]({second})\r\n").encode())
        self._migrate()
        content = post_files.read_post(target)
        self.assertTrue(content.startswith(prefix))
        self.assertIn("https://example.com/image-hosting/2025/01/01/same-name.png", content)
        self.assertIn("https://example.com/image-hosting/2025/01/02/same-name.png", content)
        self.assertIn("\r\n![b]", content)
        self.assertEqual((self.images / "2025/01/01/same-name.png").read_bytes(), b"/2025/01/01/same-name.png")
        self.assertEqual((self.images / "2025/01/02/same-name.png").read_bytes(), b"/2025/01/02/same-name.png")

    def test_reuses_cache_and_is_idempotent(self):
        """Verify reuses cache and is idempotent."""
        url = "https://s2.loli.net/2025/01/01/image.png"
        for post_id in (1, 2):
            (self.posts / f"{post_id}.md").write_text(f"---\nid: {post_id}\n---\n![image]({url})")
        self._migrate()
        before = (self.posts / "1.md").stat().st_mtime_ns
        self._migrate()
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(before, (self.posts / "1.md").stat().st_mtime_ns)

    def test_failed_download_keeps_post_and_removes_partial_file(self):
        """Verify failed download keeps post and removes partial file."""
        content = "---\nid: 1\n---\n![a](https://s2.loli.net/2025/01/01/good.png)\n![b](https://s2.loli.net/2025/01/01/missing.png)"
        target = self.posts / "1.md"
        target.write_text(content)
        with self.assertRaises(OSError):
            self._migrate()
        self.assertEqual(target.read_text(), content)
        self.assertEqual([p.name for p in (self.images / "2025/01/01").iterdir()], ["good.png"])

    def test_unmatched_urls_are_unchanged(self):
        """Verify unmatched urls are unchanged."""
        content = "---\nid: 1\n---\n![image](https://example.org/image.png)"
        target = self.posts / "1.md"
        target.write_text(content)
        self._migrate()
        self.assertEqual(target.read_text(), content)
        self.assertEqual(self.requests, [])

    def test_cli_does_not_require_blog_credentials(self):
        """Verify cli does not require blog credentials."""
        with (
            patch.dict(os.environ, {"ENDPOINT": "https://example.com"}, clear=True),
            patch("sys.argv", ["cnblogs", "images", "--output", str(self.posts)]),
            patch.object(cli, "load_api_config", side_effect=AssertionError("API credentials must not be loaded")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            cli.main()
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
