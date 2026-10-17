"""Convert legacy Cnblogs SQLite exports to local post files."""

import datetime
import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import yaml


def _parse_time(value: str) -> int | None:
    """Parse a legacy SQLite timestamp, returning None for invalid values."""
    try:
        return int(time.mktime(datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S").timetuple()))
    except ValueError:
        return None


def _read_database(path: Path) -> tuple[list[tuple[Any, ...]], list[str]]:
    """Read post rows and column names from a SQLite export."""
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        cursor = connection.execute("SELECT * FROM blog_Content")
        blogs = cursor.fetchall()
        columns = [description[0] for description in cursor.description or []]
    return blogs, columns


def _render_blog(blog: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Render one database row as Markdown with YAML front matter."""
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
    for column, key in (
        ("SourceUrl", "source_url"),
        ("Description", "description"),
        ("EntryName", "entry_name"),
        ("CreatedTime", "created_time"),
        ("AutoDesc", "auto_desc"),
    ):
        if blog[column]:
            front_matter[key] = blog[column]
    content = f"---\n{yaml.dump(front_matter, default_flow_style=False, allow_unicode=True)}---\n{blog['Body']}"
    return content, front_matter


def _export_blogs_to_markdown(
    blogs: list[tuple[Any, ...]],
    columns: list[str],
    output_dir: Path,
    previous: dict[str, str] | None = None,
) -> None:
    """Export rows and report local changes and remote conflicts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    local_only: list[str] = []
    conflicts: list[str] = []
    untracked: list[str] = []
    baseline: dict[str, dict[str, str]] = {}
    for row in blogs:
        blog = dict(zip(columns, row))
        content, front_matter = _render_blog(blog)
        post_id = str(front_matter["id"])
        target = output_dir / f"{post_id}.md"
        baseline[post_id] = {"hash": hashlib.sha256(content.encode("utf-8")).hexdigest()}
        if target.exists():
            local = target.read_text(encoding="utf-8")
            previous_content = previous.get(str(front_matter["id"])) if previous else None
            if local not in (content, previous_content):
                if previous_content is None:
                    untracked.append(post_id)
                elif content == previous_content:
                    local_only.append(post_id)
                else:
                    conflicts.append(post_id)
                continue
        if not target.exists() or target.read_text(encoding="utf-8") != content:
            target.write_text(content, encoding="utf-8", newline="")
        created_time = _parse_time(blog.get("CreatedTime", ""))
        updated_time = _parse_time(blog.get("DateUpdated", ""))
        if created_time and updated_time:
            os.utime(target, (created_time, updated_time))
        elif created_time or updated_time:
            timestamp = created_time if created_time is not None else updated_time
            if timestamp is not None:
                os.utime(target, (timestamp, timestamp))
        saved += 1
    snapshot: dict[str, Any] = {"blog_id": str(dict(zip(columns, blogs[0]))["BlogId"]), "posts": baseline}
    temporary = output_dir / ".backup.json.tmp"
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output_dir / ".backup.json")
    print(f"Converted {saved} posts.")
    print(f"Preserved local-only edits: {len(local_only)}.")
    print(f"Preserved posts changed both locally and remotely: {len(conflicts)}.")
    print(f"Preserved posts without a previous-export baseline: {len(untracked)}.")
    for label, post_ids in (
        ("Conflicts", conflicts),
        ("Local-only edits", local_only),
        ("No previous baseline", untracked),
    ):
        if post_ids:
            print(f"{label} (post IDs): {', '.join(post_ids)}")


def convert_database(output_dir: Path, database_path: Path | None = None) -> None:
    """Convert the latest SQLite export and preserve edits against the prior export."""
    databases = sorted(Path("backups").glob("cnblogs_blog_*.db"), key=lambda path: path.stem.rsplit(".", 1)[-1])
    if database_path is None:
        if not databases:
            raise FileNotFoundError("No matching database file found in backups/.")
        database_path = databases[-1]
    database_path = Path(database_path)
    previous: dict[str, str] = {}
    older = [path for path in databases if path != database_path]
    if older:
        rows, columns = _read_database(older[-1])
        for row in rows:
            blog = dict(zip(columns, row))
            content, front_matter = _render_blog(blog)
            previous[str(front_matter["id"])] = content
    blogs, columns = _read_database(database_path)
    _export_blogs_to_markdown(blogs, columns, Path(output_dir), previous)
