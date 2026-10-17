"""Back up and update Cnblogs posts, with legacy SQLite conversion support.

Usage:
    uv run cnblogs.py backup
    uv run cnblogs.py upload --dry-run
    uv run cnblogs.py images
    uv run cnblogs.py database
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import time
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen
import xmlrpc.client

from dotenv import load_dotenv
import yaml


def _parse_time(t):
    """Parse a legacy SQLite timestamp, returning None for invalid values."""
    try:
        return int(time.mktime(datetime.datetime.strptime(t, "%Y-%m-%d %H:%M:%S").timetuple()))
    except ValueError:
        return None


def _load_blogs_from_db():
    """Read post rows and column names from the first matching SQLite export."""
    db_files = glob.glob("cnblogs_blog_*.db")
    if not db_files:
        raise FileNotFoundError("No matching database file found.")
    conn = sqlite3.connect(db_files[0])
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blog_Content")
    blogs = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    conn.close()
    return blogs, columns


def _export_blogs_to_markdown(blogs, columns, output_dir="blogs"):
    """Export SQLite rows to ID-named files with YAML front matter.

    Args:
        blogs: Database rows containing post content and metadata.
        columns: Column names corresponding to each row.
        output_dir: Destination directory.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for blog_row in blogs:
        blog = dict(zip(columns, blog_row))
        front_matter = {
            "id": blog["Id"],
            "title": blog["Title"],
            "date": blog["DateAdded"],
            "updated": blog["DateUpdated"],
            "blog_id": blog["BlogId"],
            "post_type": blog["PostType"],
            "is_markdown": bool(blog["IsMarkdown"]),
            "is_active": bool(blog["IsActive"]),
            "access_permission": blog["AccessPermission"],
        }

        if blog["SourceUrl"]:
            front_matter["source_url"] = blog["SourceUrl"]
        if blog["Description"]:
            front_matter["description"] = blog["Description"]
        if blog["EntryName"]:
            front_matter["entry_name"] = blog["EntryName"]
        if blog["CreatedTime"]:
            front_matter["created_time"] = blog["CreatedTime"]
        if blog["AutoDesc"]:
            front_matter["auto_desc"] = blog["AutoDesc"]

        content = f"---\n{yaml.dump(front_matter, default_flow_style=False, allow_unicode=True)}---\n{blog['Body']}"

        filename = f"{front_matter['id']}.md"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        created_time = blog.get("CreatedTime", "")
        updated_time = blog.get("DateUpdated", "")

        ctime = _parse_time(created_time)
        mtime = _parse_time(updated_time)
        if ctime and mtime:
            os.utime(filepath, (ctime, mtime))
        elif ctime:
            os.utime(filepath, (ctime, ctime))
        elif mtime:
            os.utime(filepath, (mtime, mtime))


def _read_post(path):
    """Read a post without normalizing body line endings."""
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _digest(content):
    """Return a content hash for detecting local edits."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _serialize_post(post):
    """Convert XML-RPC dates to strings for the backup snapshot."""
    return {key: str(value) if isinstance(value, xmlrpc.client.DateTime) else value for key, value in post.items()}


def _render_post(post, blog_id):
    """Render editable front matter and the original post body."""
    metadata = {
        "id": post["postid"],
        "title": post["title"],
        "date": str(post["dateCreated"]),
        "blog_id": blog_id,
        "categories": post.get("categories", []),
        "is_markdown": "[Markdown]" in post.get("categories", []),
        "source_url": post.get("permalink", post.get("link", "")),
        "tags": post.get("mt_keywords", ""),
        "description": post.get("mt_excerpt", ""),
        "publish": None,
    }
    front_matter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
    return f"---\n{front_matter}---\n{post['description']}"


def _backup_posts(server, username, token, endpoint, output_dir, count):
    """Save remote posts without overwriting local edits.

    Args:
        server: XML-RPC proxy for the configured blog.
        username: Cnblogs login username.
        token: MetaWeblog access token.
        endpoint: Configured XML-RPC endpoint.
        output_dir: Directory for posts and the synchronization snapshot.
        count: Maximum number of recent posts to request.
    """
    blogs = server.blogger.getUsersBlogs("", username, token)
    blog_name = urlsplit(endpoint).path.rstrip("/").split("/")[-1]
    blog = next(
        (blog for blog in blogs if urlsplit(blog["url"]).path.strip("/").casefold() == blog_name.casefold()), None
    )
    if blog is None:
        raise ValueError("CNBLOGS_BLOG_NAME or CNBLOGS_URL does not match an accessible blog.")
    blog_id = str(blog["blogid"])
    snapshot_path = output_dir / ".backup.json"
    snapshot = (
        json.loads(snapshot_path.read_text())
        if snapshot_path.exists()
        else {
            "endpoint": endpoint,
            "blog_id": blog_id,
            "posts": {},
        }
    )
    if snapshot["endpoint"] != endpoint or snapshot["blog_id"] != blog_id:
        raise ValueError("The output directory belongs to a different blog.")
    posts = server.metaWeblog.getRecentPosts(blog_id, username, token, count)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    skipped = 0
    for post in posts:
        post_id = str(post["postid"])
        target = output_dir / f"{post_id}.md"
        baseline = snapshot["posts"].get(post_id)
        if target.exists():
            local = _read_post(target)
            # Untracked files and edited backups must not be overwritten.
            if baseline is None or _digest(local) != baseline["hash"]:
                skipped += 1
                print(f"Skipped local changes: {target.name}")
                continue
        content = _render_post(post, blog_id)
        if not target.exists() or _read_post(target) != content:
            target.write_text(content, encoding="utf-8")
        snapshot["posts"][post_id] = {
            "hash": _digest(content),
            "post": _serialize_post(post),
        }
        saved += 1
    _save_snapshot(output_dir, snapshot)
    print(f"Fetched {len(posts)} posts; saved {saved}; preserved {skipped} locally edited files.")
    print("Scope: posts returned by MetaWeblog; total coverage is not guaranteed by this API.")


def _save_snapshot(output_dir, snapshot):
    """Atomically persist the baseline after successful synchronization."""
    target = output_dir / ".backup.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def _parse_post(content):
    """Extract YAML front matter without changing the post body."""
    match = re.fullmatch(r"---\r?\n(.*?)^---[ \t]*\r?\n(.*)", content, re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError("Invalid YAML front matter.")
    return yaml.safe_load(match[1]), match[2]


def _post_for_upload(metadata, body, original):
    """Build an editable post while retaining returned extension fields."""
    fields = (
        "mt_text_more",
        "mt_allow_comments",
        "mt_allow_pings",
        "mt_convert_breaks",
        "wp_slug",
        "enclosure",
        "source",
    )
    post = {key: original[key] for key in fields if key in original}
    categories = list(metadata["categories"])
    if metadata["is_markdown"] and "[Markdown]" not in categories:
        categories.append("[Markdown]")
    elif not metadata["is_markdown"]:
        categories = [category for category in categories if category != "[Markdown]"]
    post.update(
        {
            "title": metadata["title"],
            "description": body,
            "dateCreated": xmlrpc.client.DateTime(datetime.datetime.fromisoformat(str(metadata["date"]))),
            "categories": categories,
            "mt_keywords": metadata["tags"],
            "mt_excerpt": metadata["description"],
        }
    )
    return post


def _upload_posts(server, username, token, output_dir, dry_run=False):
    """Upload local edits after checking publication intent and remote conflicts.

    Args:
        server: XML-RPC proxy; unused in dry-run mode.
        username: Cnblogs login username.
        token: MetaWeblog access token.
        output_dir: Directory containing posts and the backup snapshot.
        dry_run: List local changes without making network requests.
    """
    snapshot = json.loads((output_dir / ".backup.json").read_text())
    changes = []
    for post_id, baseline in snapshot["posts"].items():
        target = output_dir / f"{post_id}.md"
        if not target.exists():
            continue
        content = _read_post(target)
        if _digest(content) == baseline["hash"]:
            continue
        metadata, body = _parse_post(content)
        if str(metadata["id"]) != post_id or str(metadata["blog_id"]) != snapshot["blog_id"]:
            raise ValueError(f"Post or blog ID mismatch: {target.name}")
        post = _post_for_upload(metadata, body, baseline["post"])
        changes.append((post_id, metadata, post, content))
    if dry_run:
        for post_id, metadata, _, _ in changes:
            print(f"Would update {post_id}; publish={metadata.get('publish')!r}")
        print(f"Dry run: {len(changes)} changed posts; no network requests made.")
        return
    # Validate every publication choice before updating any remote post.
    missing = [post_id for post_id, metadata, _, _ in changes if type(metadata.get("publish")) is not bool]
    if missing:
        raise ValueError("Set publish to true or false before uploading: " + ", ".join(missing))
    for post_id, _, _, _ in changes:
        current = server.metaWeblog.getPost(post_id, username, token)
        if _serialize_post(current) != snapshot["posts"][post_id]["post"]:
            raise ValueError(f"Remote post {post_id} changed after backup; resolve the conflict before uploading.")
    for post_id, metadata, post, content in changes:
        result = server.metaWeblog.editPost(post_id, username, token, post, metadata["publish"])
        if not result:
            raise ValueError(f"The server did not confirm update of post {post_id}.")
        current = server.metaWeblog.getPost(post_id, username, token)
        snapshot["posts"][post_id] = {"hash": _digest(content), "post": _serialize_post(current)}
        _save_snapshot(output_dir, snapshot)
        print(f"Updated post {post_id}.")
    print(f"Uploaded {len(changes)} changed posts.")


def _download_image(url, image_dir):
    """Cache an image atomically, retaining its dated path to avoid collisions."""
    relative = Path(urlsplit(url).path.lstrip("/"))
    target = image_dir / relative
    if target.is_file():
        return relative.as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            with urlopen(url, timeout=60) as response:
                shutil.copyfileobj(response, handle)
            handle.close()
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"Downloaded image: {relative.as_posix()}")
    return relative.as_posix()


def _migrate_images(output_dir, endpoint, image_dir=Path("image-hosting")):
    """Download matching SM.MS images and replace URLs in post bodies.

    Args:
        output_dir: Directory containing backed-up posts.
        endpoint: Base URL where the image-hosting directory will be served.
        image_dir: Local image cache directory.
    """
    if not output_dir.is_dir():
        raise FileNotFoundError(f"Post directory not found: {output_dir}")
    pattern = re.compile(r"https://s2[.]loli[.]net/[0-9]+/[0-9]+/[0-9]+/[A-Za-z0-9_-]+[.][A-Za-z0-9]+")
    modified = 0
    for target in sorted(output_dir.glob("*.md")):
        content = _read_post(target)
        _, body = _parse_post(content)
        urls = dict.fromkeys(pattern.findall(body))
        if not urls:
            continue
        migrated = body
        for url in urls:
            relative = _download_image(url, image_dir)
            replacement = f"{endpoint.rstrip('/')}/{image_dir.name}/{relative}"
            migrated = migrated.replace(url, replacement)
        # Update only after every image in this post has downloaded successfully.
        target.write_text(content[: len(content) - len(body)] + migrated, encoding="utf-8")
        modified += 1
        print(f"Replaced image URLs: {target.name}")
    print(f"Updated image URLs in {modified} posts.")


def _api_config():
    """Load credentials, giving existing environment variables precedence."""
    load_dotenv(".env", override=False)
    username = os.environ.get("CNBLOGS_USERNAME") or os.environ.get("USERNAME", "")
    token = os.environ.get("CNBLOGS_TOKEN") or os.environ.get("TOKEN", "")
    blog_name = os.environ.get("CNBLOGS_BLOG_NAME", username)
    endpoint = os.environ.get("CNBLOGS_URL") or f"https://rpc.cnblogs.com/metaweblog/{blog_name}"
    if not username or not token:
        raise ValueError("Set CNBLOGS_USERNAME and CNBLOGS_TOKEN in the environment or .env.")
    return username, token, endpoint


def main():
    """Back up posts, upload edits, migrate images, or convert a legacy database."""
    parser = argparse.ArgumentParser(description="Back up and update Cnblogs posts through MetaWeblog.")
    parser.add_argument("action", choices=("backup", "upload", "images", "database"), nargs="?", default="backup")
    parser.add_argument("--output", type=Path, default=Path("blogs"), help="Post directory (default: blogs).")
    parser.add_argument("--count", type=int, default=1000000, help="Maximum recent posts to request during backup.")
    parser.add_argument("--dry-run", action="store_true", help="List uploads without accessing the network.")
    args = parser.parse_args()
    if args.dry_run:
        if args.action != "upload":
            parser.error("--dry-run is only supported for upload")
        _upload_posts(None, "", "", args.output, dry_run=True)
        return
    if args.action == "images":
        load_dotenv(".env", override=False)
        endpoint = os.environ.get("ENDPOINT", "").rstrip("/")
        if not endpoint:
            raise ValueError("Set ENDPOINT in the environment or .env before migrating images.")
        _migrate_images(args.output, endpoint)
        return
    if args.action == "database":
        blogs, columns = _load_blogs_from_db()
        _export_blogs_to_markdown(blogs, columns, str(args.output))
        return
    if args.count < 1:
        parser.error("--count must be positive")
    username, token, endpoint = _api_config()
    socket.setdefaulttimeout(60)
    with xmlrpc.client.ServerProxy(endpoint) as server:
        if args.action == "backup":
            _backup_posts(server, username, token, endpoint, args.output, args.count)
        else:
            snapshot = json.loads((args.output / ".backup.json").read_text())
            if snapshot["endpoint"] != endpoint:
                raise ValueError("The configured endpoint differs from the backup endpoint.")
            _upload_posts(server, username, token, args.output)


if __name__ == "__main__":
    try:
        main()
    except xmlrpc.client.Fault as error:
        raise SystemExit(f"MetaWeblog request failed (fault {error.faultCode}).") from None
    except xmlrpc.client.ProtocolError as error:
        raise SystemExit(f"MetaWeblog HTTP request failed ({error.errcode}).") from None
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
