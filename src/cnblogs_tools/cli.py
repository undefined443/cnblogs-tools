"""Parse CLI arguments and dispatch commands to their implementation modules."""

import argparse
import xmlrpc.client
from pathlib import Path

from .config import load_api_config, load_image_endpoint
from .database import convert_database
from .export import download_database
from .images import migrate_images
from .metaweblog import MetaWeblogClient
from .upload import upload_posts


def _run(args: argparse.Namespace) -> None:
    """Dispatch a parsed command without changing the working directory."""
    if args.dry_run:
        upload_posts(None, args.output, dry_run=True)
    elif args.action == "images":
        migrate_images(args.output, load_image_endpoint())
    elif args.action == "database":
        convert_database(args.output)
    elif args.action == "backup":
        database_path = download_database(load_api_config(), Path("backups"))
        convert_database(args.output, database_path)
    else:
        with MetaWeblogClient(load_api_config()) as client:
            upload_posts(client, args.output)


def main() -> None:
    """Run a command and report configuration, transport, or API errors."""
    parser = argparse.ArgumentParser(
        description="Back up complete Cnblogs exports and update posts through MetaWeblog."
    )
    parser.add_argument("action", choices=("backup", "upload", "images", "database"), nargs="?", default="backup")
    parser.add_argument("--output", type=Path, default=Path("blogs"), help="Post directory (default: blogs).")
    parser.add_argument("--dry-run", action="store_true", help="List uploads without accessing the network.")
    args = parser.parse_args()
    if args.dry_run and args.action != "upload":
        parser.error("--dry-run is only supported for upload")
    try:
        _run(args)
    except xmlrpc.client.Fault as error:
        raise SystemExit(f"MetaWeblog request failed (fault {error.faultCode}).") from None
    except xmlrpc.client.ProtocolError as error:
        raise SystemExit(f"MetaWeblog HTTP request failed ({error.errcode}).") from None
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
