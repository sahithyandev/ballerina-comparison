// Env-var config (plan.md criterion #9). Missing JWT_SECRET fails startup,
// no silent insecure default — mirrors go/internal/config/config.go and
// node/config.js. Bun auto-loads `.env` from cwd, so no dotenv dependency.

const UNITS: Record<string, number> = { ns: 1e-9, us: 1e-6, ms: 1e-3, s: 1, m: 60, h: 3600 };

export function parseDuration(s: string): number {
  const m = /^(\d+(?:\.\d+)?)(ns|us|ms|s|m|h)$/.exec(s);
  if (!m) throw new Error(`invalid duration: ${s}`);
  return Number(m[1]) * UNITS[m[2]];
}

export interface Config {
  port: string;
  dbPath: string;
  jwtSecret: string;
  jwtExpirySeconds: number;
  profanityUrl: string;
  profanityTimeoutMs: number;
}

export function load(env: Record<string, string | undefined> = process.env): Config {
  const jwtSecret = env.JWT_SECRET || '';
  if (!jwtSecret) {
    console.error('config error: JWT_SECRET is required');
    process.exit(1);
  }

  return {
    port: env.PORT || '8080',
    dbPath: env.DB_PATH || './blog.db',
    jwtSecret,
    jwtExpirySeconds: parseDuration(env.JWT_EXPIRY || '24h'),
    profanityUrl: env.PROFANITY_URL || 'http://localhost:9090',
    profanityTimeoutMs: parseDuration(env.PROFANITY_TIMEOUT || '2s') * 1000,
  };
}
