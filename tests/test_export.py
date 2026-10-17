"""Test the complete database export download and validation flow."""

import io
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

from cnblogs_tools import export


class ExportTest(unittest.TestCase):
    """Verify export selection, archive validation, and safe persistence."""

    def setUp(self) -> None:
        """Prepare a valid database archive and export response."""
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.filename = "cnblogs_blog_example.20261017120000.db"
        self.database = self._create_database()
        self.archive = self._create_archive(self.database)
        self.config = SimpleNamespace(token="secret-token")
        self.record = {
            "fileName": self.filename,
            "blogId": 42,
            "id": 17,
            "exportedPostCount": 2,
        }

    def tearDown(self) -> None:
        """Remove temporary database files."""
        self.temp.cleanup()

    def _create_database(self) -> bytes:
        """Create a small database matching the export table contract."""
        path = self.root / self.filename
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("CREATE TABLE blog_Content (Id INTEGER)")
            connection.executemany("INSERT INTO blog_Content VALUES (?)", [(1,), (2,)])
        return path.read_bytes()

    def _create_archive(self, database: bytes) -> bytes:
        """Package database bytes under a nested path as the API does."""
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
            zipped.writestr(f"exports/{self.filename}", database)
        return archive.getvalue()

    def _download(self, archive: bytes | None = None, record: dict[str, Any] | None = None) -> Path:
        """Run the download using a mocked export service and archive response."""
        response = io.BytesIO(self.archive if archive is None else archive)
        opener = Mock()
        opener.open.return_value = response
        target_dir = self.root / "backups"
        with (
            patch.object(export, "_get_export", return_value=self.record if record is None else record),
            patch.object(export, "build_opener", return_value=opener),
            redirect_stdout(io.StringIO()),
        ):
            target = export.download_database(self.config, target_dir)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://export.cnblogs.com/blogs/42/exports/17")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        return target

    def test_downloads_valid_database_from_nested_archive(self) -> None:
        """Save a validated database from the API archive."""
        target = self._download()
        self.assertEqual(target, self.root / "backups" / self.filename)
        self.assertEqual(target.read_bytes(), self.database)
        self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_reuses_identical_existing_database(self) -> None:
        """Allow a repeated download when the database is unchanged."""
        target = self._download()
        self.assertEqual(self._download(), target)

    def test_refuses_to_replace_different_existing_database(self) -> None:
        """Preserve a local database when the downloaded copy differs."""
        target = self.root / "backups" / self.filename
        target.parent.mkdir()
        target.write_bytes(b"local database")
        with self.assertRaises(FileExistsError):
            self._download()
        self.assertEqual(target.read_bytes(), b"local database")

    def test_rejects_invalid_archive(self) -> None:
        """Reject a response that is not a ZIP archive."""
        with self.assertRaisesRegex(ValueError, "valid ZIP archive"):
            self._download(archive=b"not a zip")

    def test_rejects_database_with_wrong_post_count(self) -> None:
        """Reject a structurally valid export with an unexpected post count."""
        record = {**self.record, "exportedPostCount": 3}
        with self.assertRaisesRegex(ValueError, "integrity or article-count check"):
            self._download(record=record)
        self.assertFalse((self.root / "backups" / self.filename).exists())


if __name__ == "__main__":
    unittest.main()
