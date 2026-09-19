package blog;

import at.favre.lib.crypto.bcrypt.BCrypt;
import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.interfaces.DecodedJWT;

import java.time.Duration;
import java.time.Instant;
import java.util.Date;

// Password hashing and JWT issue/validate (plan.md criterion #4: JWT bearer
// auth, HS256, secret + expiry from env). bcrypt via at.favre.lib, JWT via
// com.auth0:java-jwt — the two primitives Ballerina needs Java interop for
// and Bun/Node get natively, here just two small JVM libraries.
public final class Auth {

    public static String hashPassword(String password) {
        return BCrypt.withDefaults().hashToString(BCrypt.MIN_COST + 4, password.toCharArray());
    }

    public static boolean checkPassword(String hash, String password) {
        return BCrypt.verifyer().verify(password.toCharArray(), hash).verified;
    }

    public static String issueToken(String secret, Duration expiry, long userId) {
        Instant now = Instant.now();
        return JWT.create()
                .withClaim("user_id", userId)
                .withIssuedAt(Date.from(now))
                .withExpiresAt(Date.from(now.plus(expiry)))
                .sign(Algorithm.HMAC256(secret));
    }

    // Returns the user id, or throws if the token is missing/expired/forged.
    public static long parseToken(String secret, String token) {
        DecodedJWT jwt = JWT.require(Algorithm.HMAC256(secret)).build().verify(token);
        return jwt.getClaim("user_id").asLong();
    }

    private Auth() {
    }
}
