package blog;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Entry point: load config, open the db, start Javalin. Structured JSON
// logging (plan.md criterion #8) is configured in logback.xml.
public final class Main {

    private static final Logger log = LoggerFactory.getLogger(Main.class);

    public static void main(String[] args) {
        Config cfg;
        try {
            cfg = Config.load();
        } catch (RuntimeException e) {
            log.error("config error: {}", e.getMessage());
            System.exit(1);
            return;
        }

        Store store = new Store(cfg.dbPath());
        Profanity profanity = new Profanity(cfg.profanityUrl(), cfg.profanityTimeout());

        App.build(cfg, store, profanity).start("0.0.0.0", Integer.parseInt(cfg.port()));
        log.info("listening on {}", cfg.port());
    }

    private Main() {
    }
}
