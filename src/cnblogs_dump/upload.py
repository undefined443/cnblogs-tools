"""Upload local edits after checking publication intent and remote conflicts."""

import datetime
import json
import xmlrpc.client

from .backup import digest, parse_post, read_post, save_snapshot, serialize_post


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


def upload_posts(client, output_dir, dry_run=False):
    """Upload local edits after checking publication intent and remote conflicts.

    Args:
        client: Authenticated MetaWeblog client; unused in dry-run mode.
        output_dir: Directory containing posts and the backup snapshot.
        dry_run: List local changes without making network requests.
    """
    snapshot = json.loads((output_dir / ".backup.json").read_text())
    if not dry_run and snapshot["endpoint"] != client.endpoint:
        raise ValueError("The configured endpoint differs from the backup endpoint.")
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
        current = client.get_post(post_id)
        if serialize_post(current) != snapshot["posts"][post_id]["post"]:
            raise ValueError(f"Remote post {post_id} changed after backup; resolve the conflict before uploading.")
    for post_id, metadata, post, content in changes:
        result = client.edit_post(post_id, post, metadata["publish"])
        if not result:
            raise ValueError(f"The server did not confirm update of post {post_id}.")
        current = client.get_post(post_id)
        snapshot["posts"][post_id] = {"hash": digest(content), "post": serialize_post(current)}
        save_snapshot(output_dir, snapshot)
        print(f"Updated post {post_id}.")
    print(f"Uploaded {len(changes)} changed posts.")
