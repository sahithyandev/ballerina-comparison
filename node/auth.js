// Password hashing and JWT issue/validate (plan.md criterion #4: JWT bearer
// auth, HS256, secret+expiry from env). Mirrors go/internal/auth/auth.go.
'use strict';

const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');

function hashPassword(password) {
  return bcrypt.hashSync(password, 10);
}

function checkPassword(hash, password) {
  return bcrypt.compareSync(password, hash);
}

class InvalidToken extends Error {}

function issueToken(secret, expirySeconds, userId) {
  return jwt.sign({ user_id: userId }, secret, { algorithm: 'HS256', expiresIn: expirySeconds });
}

function parseToken(secret, token) {
  try {
    const claims = jwt.verify(token, secret, { algorithms: ['HS256'] });
    return claims.user_id;
  } catch {
    throw new InvalidToken();
  }
}

module.exports = { hashPassword, checkPassword, issueToken, parseToken, InvalidToken };
