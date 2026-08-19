// Profanity-check client: timeout + fail-open (plan.md criterion #6). Any
// error or timeout is treated as "clean" and logged, so a down dependency
// never blocks a user's write — mirrors go/internal/profanity.
import ballerina/http;
import ballerina/log;

final http:Client profanityClient = check new (profanityUrl, timeout = profanityTimeoutSeconds);

type CheckResponse record {
    boolean clean;
    string[] matches?;
};

function isClean(string text) returns boolean {
    CheckResponse|error result = profanityClient->post("/check", {text});
    if result is error {
        log:printWarn("profanity check failed, allowing content", 'error = result);
        return true;
    }
    return result.clean;
}
