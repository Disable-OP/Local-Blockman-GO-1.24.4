package com.localapi;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import fi.iki.elonen.NanoHTTPD;

/**
 * The loopback HTTP daemon. Binds 127.0.0.1 only. Routes every request
 * through RoutingTable (generated from the app's own Retrofit interfaces):
 * "H:<name>" entries run real state-backed handlers, everything else gets a
 * schema-true default ({"code":1,"data":[]} for list endpoints etc.) so the
 * Gson models never crash on a type mismatch.
 */
public class LocalHttpd extends NanoHTTPD {

    private static final String TAG_OK = "application/json";
    private final StateStore store;
    private boolean started;

    public LocalHttpd(int port, StateStore store) {
        super("127.0.0.1", port);
        this.store = store;
    }

    @Override
    public void start(int timeout, boolean daemon) throws java.io.IOException {
        super.start(timeout, daemon);
        this.started = true;
    }

    @Override
    public void stop() {
        this.started = false;
        super.stop();
    }

    public boolean isUp() {
        return started;
    }

    @Override
    public Response serve(final IHTTPSession session) {
        final String verb = session.getMethod().name();
        final String uri = session.getUri();

        // LocalServer.probeServing() liveness probe — answer silently (no REQ/
        // RES/UNMAPPED log noise in the diagnostics, the probe runs every few
        // seconds from every non-holder app process).
        if (uri != null && uri.endsWith("/health")) {
            return respond("{\"code\":1,\"data\":\"ok\"}");
        }

        // Uploaded files are served back at /files/<id> (the URL returned by
        // the upload handlers). Plain GET, served before the Retrofit routing.
        if ("GET".equals(verb) && uri != null && uri.startsWith("/files/")) {
            return serveStoredFile(uri.substring("/files/".length()));
        }

        final byte[] rawBody = readBody(session);
        final String body = new String(rawBody, java.nio.charset.StandardCharsets.UTF_8);
        final byte[] fileBytes = extractMultipartFile(session, rawBody);

        final java.util.Map<String, String> pathParams = new java.util.HashMap<>();
        final String fUri = uri;
        final String fBody = body;
        final Handlers.Ctx ctx = new Handlers.Ctx() {
            public String query(String name) {
                List<String> vals = session.getParameters().get(name);
                return (vals == null || vals.isEmpty()) ? null : vals.get(0);
            }

            public java.util.List<String> queryValues(String name) {
                List<String> vals = session.getParameters().get(name);
                return vals == null ? java.util.Collections.<String>emptyList() : vals;
            }

            public String header(String name) {
                String v = session.getHeaders().get(name);
                if (v == null && name.equals("userid")) {
                    v = session.getHeaders().get("user-id");
                }
                if (v == null && name.equals("access-token")) {
                    v = session.getHeaders().get("accesstoken");
                }
                return v;
            }

            public String body() {
                return fBody;
            }

            public byte[] fileBytes() {
                return fileBytes;
            }

            public String path() {
                return fUri;
            }

            public String pathParam(String name) {
                return pathParams.get(name);
            }
        };

        long t0 = System.nanoTime();
        String json = route(verb, uri, ctx, pathParams);
        // Session-28 observability: the RES line now carries latency +
        // auth-state (spec: method/route/status/latency/auth/size/result).
        // Fields APPENDED — the automation's RES assertions are substring
        // prefix checks and stay compatible. auth=tok means an Access-Token
        // header was present (not that it resolved — handlers own that).
        long ms = (System.nanoTime() - t0) / 1_000_000L;
        String auth = ctx.header("access-token") == null ? "anon" : "tok";
        L.i("REQ " + verb + " " + uri
                + (fBody.isEmpty() ? "" : " body=" + Handlers.abbrev(fBody)));
        L.i("RES " + verb + " " + uri + " " + json.length() + "b " + envelopeCode(json)
                + " " + ms + "ms auth=" + auth);
        return respond(json);
    }

    /** Leading "code":N from an envelope JSON — traffic observability for UI assertions. */
    private static String envelopeCode(String json) {
        if (json == null) return "code=?";
        int i = json.indexOf("\"code\":");
        if (i < 0) return "code=?";
        i += 7;
        int j = i;
        while (j < json.length() && (Character.isDigit(json.charAt(j))
                || (j == i && json.charAt(j) == '-'))) j++;
        return (j > i) ? "code=" + json.substring(i, j) : "code=?";
    }

    /** GET /files/<id> — serve an uploaded file's bytes with its stored type. */
    private Response serveStoredFile(String id) {
        try {
            org.json.JSONObject meta = store.fileMeta(id);
            byte[] data = store.readFile(id);
            if (meta == null || data == null) {
                return respond("{\"code\":0,\"message\":\"file not found\"}");
            }
            String type = meta.optString("fileType", "");
            String mime = type != null && type.contains("/") ? type
                    : (type != null && !type.isEmpty() ? "image/" + type : "application/octet-stream");
            InputStream in = new ByteArrayInputStream(data);
            Response r = newFixedLengthResponse(Response.Status.OK, mime, in, data.length);
            r.addHeader("Access-Control-Allow-Origin", "*");
            L.i("FILE " + id + " " + data.length + "b " + mime);
            return r;
        } catch (Throwable t) {
            L.e("file serve failed: " + t);
            return respond("{\"code\":0,\"message\":\"file serve failed\"}");
        }
    }

    /**
     * Multipart file-part extractor for the @Multipart upload endpoints
     * (POST /user/api/v1/file, /user/api/v1/{version}/directory/file).
     * Returns the first file part's raw bytes, or null when the request is
     * not multipart.
     */
    private static byte[] extractMultipartFile(IHTTPSession session, byte[] raw) {
        try {
            String ctype = session.getHeaders().get("content-type");
            if (ctype == null || !ctype.toLowerCase(java.util.Locale.US)
                    .contains("multipart/form-data")) {
                return null;
            }
            String boundary = null;
            for (String piece : ctype.split(";")) {
                String p = piece.trim();
                if (p.startsWith("boundary=")) {
                    boundary = p.substring("boundary=".length());
                    if (boundary.startsWith("\"") && boundary.endsWith("\"")
                            && boundary.length() >= 2) {
                        boundary = boundary.substring(1, boundary.length() - 1);
                    }
                }
            }
            if (boundary == null || boundary.isEmpty() || raw.length == 0) {
                return null;
            }
            byte[] delim = ("--" + boundary).getBytes(java.nio.charset.StandardCharsets.UTF_8);
            // first boundary position
            int start = indexOf(raw, delim, 0);
            if (start < 0) return null;
            int partHead = start + delim.length;
            // skip the trailing -- of the final boundary if present
            if (partHead + 1 < raw.length && raw[partHead] == '-' && raw[partHead + 1] == '-') {
                return null;
            }
            // headers end at CRLFCRLF; body runs to the next CRLF + boundary
            int hdrEnd = indexOf(raw, "\r\n\r\n".getBytes(java.nio.charset.StandardCharsets.UTF_8), partHead);
            if (hdrEnd < 0) return null;
            int bodyStart = hdrEnd + 4;
            int next = indexOf(raw, delim, bodyStart);
            if (next < 0) return null;
            int bodyEnd = next - 2; // strip the CRLF before the boundary
            if (bodyEnd <= bodyStart) return null;
            byte[] out = new byte[bodyEnd - bodyStart];
            System.arraycopy(raw, bodyStart, out, 0, out.length);
            return out;
        } catch (Throwable t) {
            L.e("multipart parse failed: " + t);
            return null;
        }
    }

    /** Byte-array indexOf (no dependencies). */
    private static int indexOf(byte[] hay, byte[] needle, int from) {
        if (needle.length == 0 || hay.length < needle.length) return -1;
        outer:
        for (int i = Math.max(0, from); i <= hay.length - needle.length; i++) {
            for (int j = 0; j < needle.length; j++) {
                if (hay[i + j] != needle[j]) continue outer;
            }
            return i;
        }
        return -1;
    }

    /**
     * Raw body reader: drains exactly Content-Length bytes from the socket so
     * keep-alive connections stay in sync. NanoHTTPD 2.3.1's parseBody hides
     * JSON bodies of PUT requests, so we read them ourselves. Returns the raw
     * bytes (multipart uploads are binary — never re-encode from a String).
     */
    private static byte[] readBody(IHTTPSession session) {
        try {
            String len = session.getHeaders().get("content-length");
            if (len == null) {
                return new byte[0];
            }
            int n = Integer.parseInt(len.trim());
            if (n <= 0) {
                return new byte[0];
            }
            byte[] buf = new byte[n];
            java.io.InputStream in = session.getInputStream();
            int off = 0;
            while (off < n) {
                int r = in.read(buf, off, n - off);
                if (r < 0) {
                    break;
                }
                off += r;
            }
            return buf;
        } catch (Throwable t) {
            L.e("body read failed: " + t);
            return new byte[0];
        }
    }

    private String route(String verb, String uri, Handlers.Ctx ctx,
                         java.util.Map<String, String> pathParams) {
        String cleanUri = uri == null ? "/" : (uri.length() > 1 ? uri.replaceAll("/+$", "") : uri);
        String kind;
        try {
            RoutingTable.Match m = RoutingTable.match(verb, cleanUri);
            if (m != null) {
                kind = m.kind;
                pathParams.putAll(m.params);
            } else {
                kind = null;
            }
        } catch (Throwable t) {
            L.e("routing table lookup failed: " + t);
            kind = null;
        }
        if (kind == null) {
            // Unknown to the app's own Retrofit map — still answer OK so no
            // caller can hard-fail; log loudly for API-surface expansion.
            L.i("UNMAPPED " + verb + " " + cleanUri + " -> generic ok");
            return Handlers.envelope("obj", null);
        }
        if (kind.startsWith("H:")) {
            try {
                return Handlers.handle(kind.substring(2), ctx, store);
            } catch (Throwable t) {
                L.e("handler " + kind + " threw: " + t);
                return Handlers.envelope("obj", null);
            }
        }
        return Handlers.envelope(kind, null);
    }

    private static Response respond(String json) {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        InputStream in = new ByteArrayInputStream(bytes);
        Response r = newFixedLengthResponse(Response.Status.OK, TAG_OK, in, bytes.length);
        r.addHeader("Access-Control-Allow-Origin", "*");
        return r;
    }
}
