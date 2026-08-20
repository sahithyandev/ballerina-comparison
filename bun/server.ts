import * as config from './config';
import { Store } from './store';
import { Checker } from './profanity';
import { buildApp } from './app';

const cfg = config.load();
const store = new Store(cfg.dbPath);
const profanity = new Checker(cfg.profanityUrl, cfg.profanityTimeoutMs);

const app = buildApp({
  store,
  profanity,
  jwtSecret: cfg.jwtSecret,
  jwtExpirySeconds: cfg.jwtExpirySeconds,
});

app.listen(Number(cfg.port), () => {
  console.log(JSON.stringify({ level: 'info', msg: 'listening', port: cfg.port }));
});
