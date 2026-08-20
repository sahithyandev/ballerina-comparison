'use strict';

const config = require('./config');
const { Store } = require('./store');
const { Checker } = require('./profanity');
const { buildApp } = require('./app');

const cfg = config.load();
const store = new Store(cfg.dbPath);
const profanity = new Checker(cfg.profanityUrl, cfg.profanityTimeoutMs);

const app = buildApp({
  store,
  profanity,
  jwtSecret: cfg.jwtSecret,
  jwtExpirySeconds: cfg.jwtExpirySeconds,
});

app.listen(cfg.port, () => {
  console.log(JSON.stringify({ level: 'info', msg: 'listening', port: cfg.port }));
});
