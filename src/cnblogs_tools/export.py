"""Download complete SQLite backups through the Cnblogs export API."""

import datetime
import json
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

_API = "https://write.cnblogs.com/api/blogExports"
_EXPORT = "https://export.cnblogs.com"


class _RedirectHandler(HTTPRedirectHandler):
    """Remove authorization when a download redirects to another host."""

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        redirected = super().redirect_request(request, file_pointer, code, message, headers, new_url)
        if redirected is not None and urlsplit(request.full_url).hostname != urlsplit(new_url).hostname:
            redirected.remove_header("Authorization")
            redirected.remove_header("Authorization-type")
        return redirected


def _request_json(url, config, data=None):
    """Send an authenticated request to the backup API."""
    request = Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {config.token}",
            "Authorization-Type": "pat",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def _get_export(config):
    """Use today's export or create and wait for today's backup task."""
    records = _request_json(f"{_API}?pageIndex=1&pageSize=10", config)["items"]
    if not records:
        current = _request_json(_API, config, data=b"")
    else:
        latest = max(records, key=lambda record: record["dateAdded"])
        latest_date = datetime.datetime.fromisoformat(latest["dateAdded"]).astimezone().date()
        if latest_date == datetime.datetime.now().astimezone().date():
            current = latest
        else:
            current = _request_json(_API, config, data=b"")
    deadline = time.monotonic() + 600
    while current["status"] in (0, 1, 2):
        if time.monotonic() >= deadline:
            raise TimeoutError("The Cnblogs export task did not finish within 10 minutes.")
        time.sleep(5)
        current = _request_json(f"{_API}/{current['id']}", config)
    if current["status"] != 3:
        raise ValueError(f"Cnblogs export task failed (status {current['status']}).")
    return current


def download_database(config, backup_dir):
    """Download, validate, and save the latest complete SQLite export."""
    record = _get_export(config)
    filename = Path(record["fileName"]).name
    if not filename.startswith("cnblogs_blog_") or not filename.endswith(".db"):
        raise ValueError("The export API returned an unexpected database filename.")
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / filename
    url = f"{_EXPORT}/blogs/{record['blogId']}/exports/{record['id']}"
    request = Request(url, headers={"Authorization": f"Bearer {config.token}", "Authorization-Type": "pat"})
    with tempfile.TemporaryDirectory(prefix="cnblogs-export-") as temporary_dir:
        archive = Path(temporary_dir) / "export.zip"
        with build_opener(_RedirectHandler()).open(request, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        try:
            exported = zipfile.ZipFile(archive)
        except zipfile.BadZipFile as error:
            raise ValueError("The Cnblogs export response is not a valid ZIP archive.") from error
        with exported:
            if exported.testzip() is not None:
                raise ValueError("The downloaded Cnblogs archive is damaged.")
            member = next((entry for entry in exported.infolist() if Path(entry.filename).name == filename), None)
            if member is None:
                raise ValueError("The downloaded archive does not contain the expected database.")
            database = Path(temporary_dir) / filename
            with exported.open(member) as source, database.open("wb") as output:
                shutil.copyfileobj(source, output)
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
            count = connection.execute("SELECT COUNT(*) FROM blog_Content").fetchone()[0]
        if integrity != "ok" or count != record["exportedPostCount"]:
            raise ValueError("The downloaded database failed its integrity or article-count check.")
        if target.exists():
            with target.open("rb") as existing, database.open("rb") as downloaded:
                if existing.read() != downloaded.read():
                    raise FileExistsError(f"A different database already exists: {target}")
        else:
            with database.open("rb") as source, target.with_suffix(".db.tmp").open("wb") as output:
                shutil.copyfileobj(source, output)
            target.with_suffix(".db.tmp").replace(target)
    print(f"Downloaded {count} posts to {target}.")
    return target
