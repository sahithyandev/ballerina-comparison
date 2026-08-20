"""Calls the mock profanity-check stub with a timeout and fails open: any
error or timeout is treated as "clean" and logged, so a down dependency
never blocks a user's write (plan.md criterion #6). Mirrors
go/internal/profanity/profanity.go.
"""
import logging

import httpx

log = logging.getLogger("profanity")


class Checker:
    def __init__(self, url: str, timeout: float):
        self.url = url
        self.timeout = timeout

    async def is_clean(self, text: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.url}/check", json={"text": text})
        except httpx.HTTPError as e:
            log.warning("profanity check unreachable, allowing content: %s", e)
            return True

        if resp.status_code != 200:
            log.warning("profanity check returned non-200, allowing content: %s", resp.status_code)
            return True

        try:
            return bool(resp.json()["clean"])
        except (ValueError, KeyError) as e:
            log.warning("profanity check response unreadable, allowing content: %s", e)
            return True
