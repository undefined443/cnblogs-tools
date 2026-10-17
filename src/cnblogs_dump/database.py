"""Convert legacy Cnblogs SQLite exports to local post files."""

import datetime
import glob
import os
import sqlite3
import time

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


def convert_database(output_dir):
    """Convert the first SQLite export in the working directory."""
    blogs, columns = _load_blogs_from_db()
    _export_blogs_to_markdown(blogs, columns, str(output_dir))
