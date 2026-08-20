// Calls the mock profanity-check stub with a timeout and fails open: any
// error or timeout is treated as "clean" and logged, so a down dependency
// never blocks a user's write (plan.md criterion #6). Mirrors
// go/internal/profanity/profanity.go. Uses the global fetch (stable since
// Node 18) — no HTTP client dependency needed.
'use strict';

class Checker {
  constructor(url, timeoutMs) {
    this.url = url;
    this.timeoutMs = timeoutMs;
  }

  async isClean(text) {
    let resp;
    try {
      resp = await fetch(`${this.url}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      console.warn('profanity check unreachable, allowing content:', err.message);
      return true;
    }

    if (!resp.ok) {
      console.warn('profanity check returned non-200, allowing content:', resp.status);
      return true;
    }

    try {
      const result = await resp.json();
      return Boolean(result.clean);
    } catch (err) {
      console.warn('profanity check response unreadable, allowing content:', err.message);
      return true;
    }
  }
}

module.exports = { Checker };
