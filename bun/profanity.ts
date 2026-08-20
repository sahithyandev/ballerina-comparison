// Calls the mock profanity-check stub with a timeout and fails open: any
// error or timeout is treated as "clean" and logged, so a down dependency
// never blocks a user's write (plan.md criterion #6). Mirrors
// node/profanity.js — global fetch + AbortSignal.timeout, no HTTP client
// dependency needed.

export class Checker {
  constructor(private url: string, private timeoutMs: number) {}

  async isClean(text: string): Promise<boolean> {
    let resp: Response;
    try {
      resp = await fetch(`${this.url}/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (err) {
      console.warn('profanity check unreachable, allowing content:', (err as Error).message);
      return true;
    }

    if (!resp.ok) {
      console.warn('profanity check returned non-200, allowing content:', resp.status);
      return true;
    }

    try {
      const result = (await resp.json()) as { clean?: boolean };
      return Boolean(result.clean);
    } catch (err) {
      console.warn('profanity check response unreadable, allowing content:', (err as Error).message);
      return true;
    }
  }
}
