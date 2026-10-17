"""Download referenced images and migrate URLs in local post bodies."""

import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from .post_files import parse_post, read_post


def _download_image(url: str, image_dir: Path) -> str:
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


def migrate_images(output_dir: Path, endpoint: str, image_dir: Path = Path("image-hosting")) -> None:
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
        content = read_post(target)
        _, body = parse_post(content)
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
