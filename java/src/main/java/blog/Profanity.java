package blog;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

// Calls the mock profanity-check stub with a timeout and fails open: any
// error, timeout, non-2xx, or unparseable body is treated as "clean" and
// logged, so a down dependency never blocks a user's write (plan.md
// criterion #6). Uses the stdlib java.net.http.HttpClient — no dependency,
// unlike Rust's reqwest or Python's httpx.
public final class Profanity {

    private static final Logger log = LoggerFactory.getLogger(Profanity.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final String url;
    private final Duration timeout;
    private final HttpClient client;

    public Profanity(String url, Duration timeout) {
        this.url = url;
        this.timeout = timeout;
        this.client = HttpClient.newHttpClient();
    }

    public boolean isClean(String text) {
        try {
            String payload = MAPPER.writeValueAsString(Map.of("text", text));
            HttpRequest req = HttpRequest.newBuilder(URI.create(url + "/check"))
                    .timeout(timeout)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload))
                    .build();
            HttpResponse<String> resp = client.send(req, HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() / 100 != 2) {
                log.warn("profanity check returned {}, allowing content", resp.statusCode());
                return true;
            }
            JsonNode body = MAPPER.readTree(resp.body());
            return body.path("clean").asBoolean(true);
        } catch (Exception e) {
            log.warn("profanity check unreachable, allowing content: {}", e.toString());
            return true;
        }
    }
}
