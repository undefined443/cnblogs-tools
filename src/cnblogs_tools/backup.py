"""Back up remote posts and manage local post files and sync snapshots."""

import hashlib
import json
import re
import xmlrpc.client
from urllib.parse import urlsplit

import yaml


def read_post(path):
    """Read a post without normalizing body line endings."""
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def digest(content):
    """Return a content hash for detecting local edits."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def serialize_post(post):
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
        "access_permission": None,
    }
    front_matter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
    return f"---\n{front_matter}---\n{post['description']}"


def save_snapshot(output_dir, snapshot):
    """Atomically persist the baseline after successful synchronization."""
    target = output_dir / ".backup.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def parse_post(content):
    """Extract YAML front matter without changing the post body."""
    match = re.fullmatch(r"---\r?\n(.*?)^---[ \t]*\r?\n(.*)", content, re.MULTILINE | re.DOTALL)
    if match is None:
        raise ValueError("Invalid YAML front matter.")
    return yaml.safe_load(match[1]), match[2]


def backup_posts(client, output_dir, count):
    """Save remote posts without overwriting local edits.

    Args:
        client: Authenticated MetaWeblog client.
        output_dir: Directory for posts and the synchronization snapshot.
        count: Maximum number of recent posts to request.
    """
    endpoint = client.endpoint
    blogs = client.get_blogs()
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
    posts = client.get_recent_posts(blog_id, count)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    skipped = 0
    for post in posts:
        post_id = str(post["postid"])
        target = output_dir / f"{post_id}.md"
        baseline = snapshot["posts"].get(post_id)
        if target.exists():
            local = read_post(target)
            # Untracked files and edited backups must not be overwritten.
            if baseline is None or digest(local) != baseline["hash"]:
                skipped += 1
                print(f"Skipped local changes: {target.name}")
                continue
        content = _render_post(post, blog_id)
        if not target.exists() or read_post(target) != content:
            target.write_text(content, encoding="utf-8")
        snapshot["posts"][post_id] = {
            "hash": digest(content),
            "post": serialize_post(post),
        }
        saved += 1
    save_snapshot(output_dir, snapshot)
    print(f"Fetched {len(posts)} posts; saved {saved}; preserved {skipped} locally edited files.")
    print("Scope: posts returned by MetaWeblog; total coverage is not guaranteed by this API.")
