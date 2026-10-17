"""Load CLI configuration from the working directory and environment."""

from dataclasses import dataclass, field
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class ApiConfig:
    """MetaWeblog credentials and endpoint, excluding the token from repr."""

    username: str
    token: str = field(repr=False)
    endpoint: str


def load_api_config():
    """Read API settings, preferring existing environment variables."""
    load_dotenv(".env", override=False)
    username = os.environ.get("CNBLOGS_USERNAME") or os.environ.get("USERNAME", "")
    token = os.environ.get("CNBLOGS_TOKEN") or os.environ.get("TOKEN", "")
    blog_name = os.environ.get("CNBLOGS_BLOG_NAME", username)
    endpoint = os.environ.get("CNBLOGS_URL") or f"https://rpc.cnblogs.com/metaweblog/{blog_name}"
    if not username or not token:
        raise ValueError("Set CNBLOGS_USERNAME and CNBLOGS_TOKEN in the environment or .env.")
    return ApiConfig(username, token, endpoint)


def load_image_endpoint():
    """Read the image hosting base URL without requiring API credentials."""
    load_dotenv(".env", override=False)
    endpoint = os.environ.get("ENDPOINT", "").rstrip("/")
    if not endpoint:
        raise ValueError("Set ENDPOINT in the environment or .env before migrating images.")
    return endpoint
