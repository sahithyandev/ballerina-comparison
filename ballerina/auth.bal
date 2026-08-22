// Password hashing (ballerina/crypto's native bcrypt) and JWT issue/validate
// (plan.md criterion #4: HS256, secret+expiry from env).
import ballerina/crypto;
import ballerina/http;
import ballerina/jwt;

function hashPassword(string password) returns string {
    string|crypto:Error hash = crypto:hashBcrypt(password);
    return hash is string ? hash : "";
}

function checkPassword(string hash, string password) returns boolean {
    boolean|crypto:Error 'match = crypto:verifyBcrypt(password, hash);
    return 'match is boolean && 'match;
}

function issueToken(int userId) returns string|error {
    jwt:IssuerConfig issuerConfig = {
        username: userId.toString(),
        issuer: "blog-ballerina",
        audience: ["blog-api"],
        expTime: jwtExpirySeconds,
        signatureConfig: {
            algorithm: jwt:HS256,
            config: jwtSecret
        }
    };
    return jwt:issue(issuerConfig);
}

function parseToken(string token) returns int|error {
    jwt:ValidatorConfig validatorConfig = {
        issuer: "blog-ballerina",
        audience: "blog-api",
        signatureConfig: {
            secret: jwtSecret
        }
    };
    jwt:Payload payload = check jwt:validate(token, validatorConfig);
    string? sub = payload.sub;
    if sub is () {
        return error("token has no subject");
    }
    return check int:fromString(sub);
}

// Reads and validates the bearer token directly from the request, rather
// than a blanket interceptor, since only some resources need it.
function extractUserId(http:Request req) returns int|error {
    string|http:HeaderNotFoundError authHeader = req.getHeader("Authorization");
    if authHeader is http:HeaderNotFoundError || !authHeader.startsWith("Bearer ") {
        return error("missing bearer token");
    }
    return parseToken(authHeader.substring(7));
}
