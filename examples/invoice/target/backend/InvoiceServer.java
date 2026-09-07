import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.math.BigDecimal;
import java.util.LinkedHashMap;

/** Reference implementation for the bounded example; not a generic translator output. */
public class InvoiceServer {
    public static void main(String[] args) throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 8100), 0);
        server.createContext("/api/invoice", exchange -> {
            var params = new LinkedHashMap<String, String>();
            String query = exchange.getRequestURI().getRawQuery();
            if (query != null) for (String pair : query.split("&")) {
                String[] p = pair.split("=", 2);
                params.put(URLDecoder.decode(p[0], StandardCharsets.UTF_8),
                    p.length > 1 ? URLDecoder.decode(p[1], StandardCharsets.UTF_8) : "");
            }
            String id = params.get("id");
            String body;
            int status;
            if (id == null || id.isEmpty()) {
                status = 400;
                body = "{\"error\":\"Id requried!\"}"; // Preserve the documented typo.
            } else if (!id.equals("42")) {
                status = 404; body = "{\"error\":\"Not found\"}";
            } else {
                status = 200;
                String amount = new BigDecimal("9007199254740993.10").toPlainString();
                body = "{\"id\":\"42\",\"amount\":\"" + amount + "\"}";
            }
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
            exchange.sendResponseHeaders(status, bytes.length);
            try (var stream = exchange.getResponseBody()) { stream.write(bytes); }
        });
        server.start();
        System.out.println("Reference Java API: http://127.0.0.1:8100");
    }
}
