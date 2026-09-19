package blog;

import java.util.Map;

// Consistent JSON error envelope on every error response (plan.md criterion
// #5), no stack traces leaking. AppException carries the HTTP status and the
// stable error code; App wires a single Javalin exception handler that turns
// it into {"error":{"code","message"}}.
public final class Http {

    public static final class AppException extends RuntimeException {
        public final int status;
        public final String code;

        public AppException(int status, String code, String message) {
            super(message);
            this.status = status;
            this.code = code;
        }
    }

    public static AppException badRequest(String code, String message) {
        return new AppException(400, code, message);
    }

    public static AppException unauthorized(String code, String message) {
        return new AppException(401, code, message);
    }

    public static AppException forbidden(String code, String message) {
        return new AppException(403, code, message);
    }

    public static AppException notFound(String code, String message) {
        return new AppException(404, code, message);
    }

    public static AppException conflict(String code, String message) {
        return new AppException(409, code, message);
    }

    public static AppException internal(String code, String message) {
        return new AppException(500, code, message);
    }

    public static Map<String, Object> envelope(String code, String message) {
        return Map.of("error", Map.of("code", code, "message", message));
    }

    private Http() {
    }
}
