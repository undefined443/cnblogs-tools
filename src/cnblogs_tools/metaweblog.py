"""Provide authenticated MetaWeblog operations over XML-RPC."""

from __future__ import annotations

import xmlrpc.client
from typing import Any

from .config import ApiConfig


class _TimeoutTransport(xmlrpc.client.SafeTransport):
    """Apply a timeout to HTTPS connections without changing global defaults."""

    def make_connection(self, host: Any) -> Any:
        """Create or reuse an HTTPS connection with a bounded timeout."""
        connection = super().make_connection(host)
        connection.timeout = 60
        return connection


class _TimeoutHTTPTransport(xmlrpc.client.Transport):
    """Apply the same timeout when using an HTTP endpoint."""

    def make_connection(self, host: Any) -> Any:
        """Create or reuse an HTTP connection with a bounded timeout."""
        connection = super().make_connection(host)
        connection.timeout = 60
        return connection


class MetaWeblogClient:
    """Expose the operations needed for backups and updates."""

    def __init__(self, config: ApiConfig) -> None:
        """Initialize a proxy with credentials supplied as method arguments."""
        self.endpoint = config.endpoint
        self._username = config.username
        self._token = config.token
        transport = _TimeoutTransport() if config.endpoint.startswith("https://") else _TimeoutHTTPTransport()
        self._server = xmlrpc.client.ServerProxy(config.endpoint, transport=transport)

    def __enter__(self) -> MetaWeblogClient:
        """Return this client for use in a context manager."""
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        """Close the underlying HTTP connection."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection."""
        self._server("close")()

    def get_post(self, post_id: str) -> Any:
        """Read a post using its string ID."""
        return self._server.metaWeblog.getPost(str(post_id), self._username, self._token)

    def edit_post(self, post_id: str, post: dict[str, Any], publish: bool) -> Any:
        """Update a post with an explicitly chosen publication flag."""
        return self._server.metaWeblog.editPost(str(post_id), self._username, self._token, post, publish)
