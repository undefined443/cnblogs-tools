"""Upload local edits tracked by a complete database export."""

import datetime
import json
import xmlrpc.client
from pathlib import Path
from typing import Any

import yaml

from .metaweblog import MetaWeblogClient
from .post_files import digest, parse_post, read_post, save_snapshot


def _post_for_upload(metadata: dict[str, Any], body: str, original: dict[str, Any]) -> dict[str, Any]:
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


def upload_posts(client: MetaWeblogClient | None, output_dir: Path, dry_run: bool = False) -> None:
    """Upload local edits tracked by the complete database export.

    Args:
        client: Authenticated MetaWeblog client; unused in dry-run mode.
        output_dir: Directory containing posts and the complete export baseline.
        dry_run: List local changes without making network requests.
    """
    snapshot: dict[str, Any] = json.loads((output_dir / ".backup.json").read_text())
    changes: list[tuple[str, dict[str, Any], str, str]] = []
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
    skipped_permissions = [
        (post_id, metadata) for post_id, metadata, _, _ in changes if metadata.get("access_permission") != "Anonymous"
    ]
    skipped_publish = [
        (post_id, metadata)
        for post_id, metadata, _, _ in changes
        if metadata.get("access_permission") == "Anonymous" and type(metadata.get("publish")) is not bool
    ]
    uploadable = [
        item
        for item in changes
        if item[1].get("access_permission") == "Anonymous" and type(item[1].get("publish")) is bool
    ]
    if dry_run:
        print(
            f"Dry run: {len(uploadable)} public posts ready; {len(skipped_permissions)} private or unknown skipped; "
            f"{len(skipped_publish)} need an explicit publish choice. No network requests made."
        )
        if skipped_permissions:
            print("Private or unknown IDs: " + ", ".join(post_id for post_id, _ in skipped_permissions))
        if skipped_publish:
            print("Missing publish choice IDs: " + ", ".join(post_id for post_id, _ in skipped_publish))
        return
    assert client is not None
    for post_id, metadata, body, content in uploadable:
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
    print(
        f"Uploaded {len(uploadable)} posts; skipped {len(skipped_permissions)} private or unknown and "
        f"{len(skipped_publish)} without an explicit publish choice."
    )
    if skipped_permissions:
        print("Private or unknown IDs: " + ", ".join(post_id for post_id, _ in skipped_permissions))
    if skipped_publish:
        print("Missing publish choice IDs: " + ", ".join(post_id for post_id, _ in skipped_publish))
