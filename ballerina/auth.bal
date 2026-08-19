// Password hashing (Java interop onto jBCrypt — see Ballerina.toml) and JWT
// issue/validate (plan.md criterion #4: HS256, secret+expiry from env).
import ballerina/http;
import ballerina/jballerina.java;
import ballerina/jwt;

// jBCrypt's methods take/return java.lang.String, which Java interop needs
// as an opaque `handle`, not Ballerina's `string` — hence the conversions.
function bcryptGensalt() returns handle = @java:Method {
    'class: "org.mindrot.jbcrypt.BCrypt",
    name: "gensalt"
} external;

function bcryptHashpw(handle password, handle salt) returns handle = @java:Method {
    'class: "org.mindrot.jbcrypt.BCrypt",
    name: "hashpw"
} external;

function bcryptCheckpw(handle password, handle hash) returns boolean = @java:Method {
    'class: "org.mindrot.jbcrypt.BCrypt",
    name: "checkpw"
} external;

function hashPassword(string password) returns string {
    handle salt = bcryptGensalt();
    handle hash = bcryptHashpw(java:fromString(password), salt);
    return java:toString(hash) ?: "";
}

function checkPassword(string hash, string password) returns boolean {
    return bcryptCheckpw(java:fromString(password), java:fromString(hash));
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
