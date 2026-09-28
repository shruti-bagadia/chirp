"""Polite HTTP fetching for public job APIs."""

from __future__ import annotations

import time

import httpx

from app.connectors.base import ConnectorError

USER_AGENT = "Chirp/0.1 (personal job search tool; +https://github.com/shruti-bagadia/chirp)"


class HttpFetcher:
    def __init__(self, timeout: float = 20.0, retries: int = 2, pause: float = 1.0) -> None:
        self.client = httpx.Client(
            timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self.retries = retries
        self.pause = pause

    def get_json(self, url: str, params: dict | None = None) -> dict | list:
        return self._json("GET", url, params=params)

    def post_json(self, url: str, json_body: dict) -> dict | list:
        return self._json("POST", url, json=json_body)

    def _json(self, method: str, url: str, **kwargs) -> dict | list:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self.client.request(method, url, **kwargs)
                if r.status_code == 404:
                    raise ConnectorError(f"Board not found: {url}")
                if r.status_code in {429, 500, 502, 503, 504}:
                    raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
                r.raise_for_status()
                return r.json()
            except ConnectorError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                time.sleep(self.pause * (2**attempt))
        raise ConnectorError(f"Couldn't read {url}: {last}")

    def get_text(self, url: str) -> str:
        try:
            r = self.client.get(url)
            r.raise_for_status()
            return r.text
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Couldn't open {url}: {exc}") from exc

    def close(self) -> None:
        self.client.close()
