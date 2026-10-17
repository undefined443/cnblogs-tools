"""Upload local edits tracked by a complete database export."""

import datetime
import json
import xmlrpc.client

import yaml

from .post_files import digest, parse_post, read_post, save_snapshot


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
    categories = list(metadata.get("categories", original.get("categories", [])))
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
            "mt_keywords": metadata.get("tags", original.get("mt_keywords", "")),
            "mt_excerpt": metadata.get("description", original.get("mt_excerpt", "")),
        }
    )
    return post


def upload_posts(client, output_dir, dry_run=False):
    """Upload local edits tracked by the complete database export.

    Args:
        client: Authenticated MetaWeblog client; unused in dry-run mode.
        output_dir: Directory containing posts and the complete export baseline.
        dry_run: List local changes without making network requests.
    """
    snapshot = json.loads((output_dir / ".backup.json").read_text())
    changes = []
    for post_id, baseline in snapshot["posts"].items():
        target = output_dir / f"{post_id}.md"
        if not target.exists():
            continue
        content = read_post(target)
        if digest(content) == baseline["hash"]:
            continue
        metadata, body = parse_post(content)
        if str(metadata["id"]) != post_id or str(metadata["blog_id"]) != snapshot["blog_id"]:
            raise ValueError(f"Post or blog ID mismatch: {target.name}")
        changes.append((post_id, metadata, body, content))
    if changes:
        print("MetaWeblog cannot verify access permissions; publish does not mean public/private.")
    if dry_run:
        for post_id, metadata, _, _ in changes:
            permission = metadata.get("access_permission")
            status = "Would update" if permission == "Anonymous" else "Blocked"
            print(f"{status} {post_id}; publish={metadata.get('publish')!r}; access_permission={permission!r}")
        print(f"Dry run: {len(changes)} changed posts; no network requests made.")
        return
    # Reject private and unverified posts before making any remote requests.
    blocked = [post_id for post_id, metadata, _, _ in changes if metadata.get("access_permission") != "Anonymous"]
    if blocked:
        raise ValueError(
            "Upload blocked for private or unknown access permissions: "
            + ", ".join(blocked)
            + ". Only upload confirmed public posts (access_permission: Anonymous); "
            "publish controls publication, not visibility."
        )
    # Validate every publication choice before updating any remote post.
    missing = [post_id for post_id, metadata, _, _ in changes if type(metadata.get("publish")) is not bool]
    if missing:
        raise ValueError("Set publish to true or false before uploading: " + ", ".join(missing))
    for post_id, metadata, body, content in changes:
        current = client.get_post(post_id)
        post = _post_for_upload(metadata, body, current)
        result = client.edit_post(post_id, post, metadata["publish"])
        if not result:
            raise ValueError(f"The server did not confirm update of post {post_id}.")
        metadata.pop("publish")
        content = f"---\n{yaml.safe_dump(metadata, allow_unicode=True, sort_keys=True)}---\n{body}"
        target = output_dir / f"{post_id}.md"
        target.write_text(content, encoding="utf-8", newline="")
        snapshot["posts"][post_id] = {"hash": digest(content)}
        save_snapshot(output_dir, snapshot)
        print(f"Updated post {post_id}.")
    print(f"Uploaded {len(changes)} changed posts.")
