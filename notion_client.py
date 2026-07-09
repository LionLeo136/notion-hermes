"""
Notion API client — query, update, archive pages in the Hermes Requests database.
Rate-limited to ~3 req/s with automatic backoff on 429.
"""

import time
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    def __init__(self, token: str, database_id: str):
        self.token = token
        self.database_id = database_id
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            }
        )
        self._last_request_time = 0.0

    # ── rate limiting ──────────────────────────────────────────────

    def _rate_limit(self):
        """Ensure at least 333ms between requests (~3 req/s)."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < 0.34:
            time.sleep(0.34 - elapsed)
        self._last_request_time = time.monotonic()

    def _request(
        self, method: str, path: str, json: Optional[dict] = None
    ) -> requests.Response:
        url = f"{NOTION_API_BASE}/{path.lstrip('/')}"
        resp: Optional[requests.Response] = None
        for attempt in range(4):
            self._rate_limit()
            resp = self.session.request(method, url, json=json)
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                logger.warning(
                    "Notion rate-limited (429). Retrying in %ds (attempt %d/4)",
                    retry_after,
                    attempt + 1,
                )
                time.sleep(retry_after)
                continue
            return resp
        if resp is None:
            raise RuntimeError("No response from Notion (unreachable)")
        return resp  # return last attempt

    # ── query ───────────────────────────────────────────────────────

    def query_pending(self) -> list[dict]:
        """
        Query all rows where Status == 'Pending', sorted by Created ascending.
        Handles pagination automatically.
        Returns list of page dicts (Notion page objects).
        """
        results: list[dict] = []
        has_more = True
        start_cursor: Optional[str] = None

        filter_obj = {
            "filter": {
                "property": "Status",
                "select": {"equals": "Pending"},
            },
            "sorts": [{"timestamp": "created_time", "direction": "ascending"}],
            "page_size": 100,
        }

        while has_more:
            body = {**filter_obj}
            if start_cursor:
                body["start_cursor"] = start_cursor
            resp = self._request(
                "POST", f"/databases/{self.database_id}/query", json=body
            )
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        return results

    def query_all_sorted_by_created(self, descending: bool = True) -> list[dict]:
        """Query ALL rows, sorted by Created desc (for cleanup)."""
        results: list[dict] = []
        has_more = True
        start_cursor: Optional[str] = None

        direction = "descending" if descending else "ascending"
        body_base = {
            "sorts": [{"timestamp": "created_time", "direction": direction}],
            "page_size": 100,
        }

        while has_more:
            body = {**body_base}
            if start_cursor:
                body["start_cursor"] = start_cursor
            resp = self._request(
                "POST", f"/databases/{self.database_id}/query", json=body
            )
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        return results

    # ── update ──────────────────────────────────────────────────────

    def update_row(self, page_id: str, status: Optional[str] = None, result: Optional[str] = None) -> None:
        """
        Update a page's Status and/or Result properties.
        Only sends properties that are provided (not None).
        Result is truncated to 1900 chars (Notion limit ~2000 per rich_text block).
        """
        properties = {}
        if status is not None:
            properties["Status"] = {"select": {"name": status}}
        if result is not None:
            result = result[:1900]
            properties["Result"] = {
                "rich_text": [{"text": {"content": result}}]
            }

        if not properties:
            return  # nothing to update

        resp = self._request(
            "PATCH",
            f"/pages/{page_id}",
            json={"properties": properties},
        )
        resp.raise_for_status()

    # ── archive ───────────────────────────────────────────────────

    def archive_page(self, page_id: str) -> None:
        """Soft-delete a page (move to Trash)."""
        resp = self._request(
            "PATCH",
            f"/pages/{page_id}",
            json={"archived": True},
        )
        resp.raise_for_status()

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def get_title(page: dict) -> str:
        """Extract title text from the 'Request' title property."""
        try:
            title_parts = page["properties"]["Request"]["title"]
            return "".join(part["plain_text"] for part in title_parts)
        except (KeyError, IndexError, TypeError):
            return "(untitled)"

    @staticmethod
    def get_rich_text(page: dict, property_name: str) -> str:
        """Extract plain text from a rich_text property."""
        try:
            parts = page["properties"][property_name]["rich_text"]
            return "".join(part["plain_text"] for part in parts)
        except (KeyError, IndexError, TypeError):
            return ""

    @staticmethod
    def get_status(page: dict) -> str:
        """Extract the current Status value."""
        try:
            return page["properties"]["Status"]["select"]["name"]
        except (KeyError, TypeError):
            return ""

    @staticmethod
    def get_page_id(page: dict) -> str:
        return page["id"]
