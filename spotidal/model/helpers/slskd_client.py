"""Thin `requests`-based wrapper around the `slskd` REST API.

Endpoint paths/payloads below follow slskd's publicly documented v0 API as
of writing, but have NOT been verified against a live instance -- that is
M0 in PLAN-SOULSEEK.md. Confirm these against `slskd`'s own Swagger UI
(`<base_url>/swagger`) during implementation before relying on them, and
keep any corrections scoped to this module -- callers only see the plain
dicts returned below, never raw slskd response shapes.
"""

import os
import time

import requests


class SlskdError(Exception):
    """Raised when `slskd` is unreachable or returns an error response."""


class SlskdClient:
    def __init__(self, base_url, api_key_env="SLSKD_API_KEY", timeout=20):
        self._base_url = base_url.rstrip("/")
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            raise SlskdError(
                f"{api_key_env} is not set; export the slskd API key before using Soulseek"
            )
        self._session = requests.Session()
        self._session.headers.update({"X-API-Key": api_key})
        self._timeout = timeout

    def _request(self, method, path, retries=3, **kwargs):
        url = f"{self._base_url}{path}"
        last_error = None
        for attempt in range(retries):
            try:
                response = self._session.request(method, url, timeout=self._timeout, **kwargs)
            except requests.exceptions.RequestException as error:
                last_error = error
            else:
                if response.status_code < 500:
                    response.raise_for_status()
                    return response
                last_error = requests.exceptions.HTTPError(
                    f"{response.status_code} from slskd", response=response
                )
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
        raise SlskdError(f"slskd request failed: {method} {path}: {last_error}")

    def search(self, query, timeout_seconds=30, max_results=100):
        """Submit a search; returns the search id to poll with get_search_results."""
        response = self._request("POST", "/api/v0/searches", json={
            "searchText": query,
            "searchTimeout": timeout_seconds * 1000,
            "fileLimit": max_results,
        })
        return response.json()["id"]

    def get_search_results(self, search_id):
        """Return a flat list of candidate file dicts (one slskd "file" per
        entry, with the owning username merged in) once the search settles."""
        response = self._request("GET", f"/api/v0/searches/{search_id}")
        data = response.json()
        results = []
        for entry in data.get("responses", []):
            username = entry.get("username")
            for file in entry.get("files", []):
                results.append({**file, "username": username})
        return results

    def queue_download(self, username, filename, size):
        """Enqueue a transfer. Returns slskd's ack; the transfer itself is
        tracked by (username, filename), there's no separate transfer id."""
        self._request("POST", f"/api/v0/transfers/downloads/{username}", json=[
            {"filename": filename, "size": size}
        ])
        return {"username": username, "filename": filename}

    def get_transfer(self, username, filename):
        response = self._request("GET", f"/api/v0/transfers/downloads/{username}")
        for transfer in response.json():
            if transfer.get("filename") == filename:
                return transfer
        return None

    def cancel_transfer(self, username, filename):
        self._request("DELETE", f"/api/v0/transfers/downloads/{username}/{filename}")
