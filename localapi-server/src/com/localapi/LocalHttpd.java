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

        // Skin icons: streamed straight from the local icon store (extracted
        // once from the downloaded icon pack; CDN proxy on a cache miss).
        // Served before the Retrofit routing — the client's image loader hits
        // this URL directly (iconUrl fields are rewritten to it).
        if ("GET".equals(verb) && uri != null
                && uri.startsWith("/localapi/skins/icons/")) {
            return serveSkinIcon(uri.substring("/localapi/skins/icons/".length()));
        }

        // Game icons: the REAL official art for the hosted rooms (extracted
        // from the in-APK gameicons seed pack). Served before the Retrofit
        // routing — the hall's image loader hits this URL directly (the
        // catalog's gameCoverPic fields are rewritten to it).
        if ("GET".equals(verb) && uri != null
                && uri.startsWith("/localapi/games/icons/")) {
            return serveGameIcon(uri.substring("/localapi/games/icons/".length()));
        }

        // Official map/skin-resource assets (MapAssets/DressRes): the engine
        // and the dress updater download zips/csv/yml from the original CDN
        // object-key paths — served here from the local pack store.
        // RUN-11 EVIDENCE (38482545272): the engine's HttpDownloader HEADs
        // the map zip FIRST (content-length + range probe) — HEAD fell
        // through to the generic route ("UNMAPPED HEAD ... generic ok") and
        // answered the 35-byte JSON envelope; downloadByRange then assembled
        // a 35-byte "zip" and died on "the final file corrupted" (errCode 6)
        // for EVERY map join (Bedwars hall + Skyblock alike). HEAD answers
        // the real length; ranged GETs answer 206 + Content-Range.
        if (uri != null && isAssetUri(uri)) {
            if ("HEAD".equals(verb)) return headAsset(uri);
            if ("GET".equals(verb)) return serveAsset(uri, session);
        }

        final byte[] rawBody = readBody(session);
        final String body = new String(rawBody, java.nio.charset.StandardCharsets.UTF_8);
        final byte[] fileBytes = extractMultipartFile(session, rawBody);

        final java.util.Map<String, String> pathParams = new java.util.HashMap<>();
        final String fUri = uri;
        final String fBody = body;
        final String verb0 = verb;
        final Handlers.Ctx ctx = new Handlers.Ctx() {
            public String verb() {
                return verb0;
            }

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

    /** The CDN-object-key asset families the engine fetches directly. */
    private static boolean isAssetUri(String uri) {
        return uri.startsWith("/sandbox/games/maps/")
                || uri.startsWith("/sandbox/games/plugins/")
                || uri.startsWith("/sandbox/games/app-game-engine-resources/")
                || uri.startsWith("/sandbox/dresses/dress-resources/");
    }

    /**
     * HEAD /sandbox/... — the engine's HttpDownloader probes the asset
     * length + range support here before the ranged GET (run-11 lesson).
     * NanoHTTPD 2.3.1 prints the manual Content-Length header verbatim
     * (sendContentLengthHeaderIfNotAlreadyPresent) and sendBody breaks
     * immediately on the empty stream — a clean header-only answer.
     */
    private Response headAsset(String uri) {
        byte[] data = uri.startsWith("/sandbox/dresses/dress-resources/")
                ? DressRes.packBytes(store)
                : MapAssets.fileBytes(store, uri.substring(1));
        if (data == null) {
            L.i("ASSET HEAD miss " + uri);
            return newFixedLengthResponse(Response.Status.NOT_FOUND, "text/plain", "");
        }
        Response r = newFixedLengthResponse(Response.Status.OK,
                assetMime(uri), "");
        setFixedContentLength(r, data.length);
        r.addHeader("Accept-Ranges", "bytes");
        L.i("ASSET HEAD " + uri + " " + data.length + "b");
        return r;
    }

    /**
     * NanoHTTPD 2.3.1 prints "Content-Length: <pending>" UNCONDITIONALLY in
     * sendContentLengthHeaderIfNotAlreadyPresent — adding a manual
     * Content-Length header would print the line TWICE (identical values;
     * the engine's HttpDownloader parses this header on its range probe,
     * run-11). Setting the Response's private contentLength field makes
     * pending itself the real length: one clean header, empty body
     * (sendBody breaks immediately on the empty stream). Falls back to the
     * manual header (duplicate, identical — client-tolerated) on any
     * reflection failure.
     */
    private static void setFixedContentLength(Response r, long len) {
        try {
            java.lang.reflect.Field f = Response.class
                    .getDeclaredField("contentLength");
            f.setAccessible(true);
            f.setLong(r, len);
        } catch (Throwable t) {
            r.addHeader("Content-Length", String.valueOf(len));
        }
    }

    private static String assetMime(String uri) {
        String lower = uri.toLowerCase(java.util.Locale.US);
        if (lower.endsWith(".zip")) return "application/zip";
        if (lower.endsWith(".csv")) return "text/csv";
        if (lower.endsWith(".yml") || lower.endsWith(".yaml")) return "text/yaml";
        if (lower.endsWith(".md5") || lower.endsWith(".ini")
                || lower.endsWith(".txt")) return "text/plain";
        return "application/octet-stream";
    }

    /**
     * GET /sandbox/games/maps/<key> and /sandbox/dresses/dress-resources/<key>
     * — official map + decorate assets served from the local packs (packs are
     * sha256/md5-verified against the release manifests, so bytes served are
     * the bytes on GitHub). key is the original CDN object key minus the
     * leading slash; dress-resource requests resolve to the decorate pack.
     * Honors single-range requests (the engine's downloadByRange: 206 +
     * Content-Range + the slice) — run-11 lesson.
     */
    private Response serveAsset(String uri, IHTTPSession session) {
        byte[] data = uri.startsWith("/sandbox/dresses/dress-resources/")
                ? DressRes.packBytes(store)
                : MapAssets.fileBytes(store, uri.substring(1));
        if (data == null) {
            L.i("ASSET miss " + uri);
            return respond("{\"code\":0,\"message\":\"asset not available\"}");
        }
        String mime = assetMime(uri);
        String range = session.getHeaders().get("range");
        if (range != null && range.startsWith("bytes=")) {
            long[] slice = parseByteRange(range, data.length);
            if (slice == null) {
                Response bad = newFixedLengthResponse(
                        Response.Status.RANGE_NOT_SATISFIABLE, "text/plain", "");
                bad.addHeader("Content-Range", "bytes */" + data.length);
                L.i("ASSET " + uri + " range unsatisfiable: " + range);
                return bad;
            }
            int start = (int) slice[0], end = (int) slice[1];
            InputStream in = new ByteArrayInputStream(
                    data, start, end - start + 1);
            Response r = newFixedLengthResponse(Response.Status.PARTIAL_CONTENT,
                    mime, in, end - start + 1L);
            r.addHeader("Content-Range", "bytes " + start + "-" + end
                    + "/" + data.length);
            r.addHeader("Accept-Ranges", "bytes");
            r.addHeader("Access-Control-Allow-Origin", "*");
            L.i("ASSET " + uri + " " + (end - start + 1) + "b range ["
                    + start + "-" + end + "] of " + data.length);
            return r;
        }
        InputStream in = new ByteArrayInputStream(data);
        Response r = newFixedLengthResponse(Response.Status.OK, mime, in, data.length);
        r.addHeader("Access-Control-Allow-Origin", "*");
        r.addHeader("Cache-Control", "max-age=86400");
        L.i("ASSET " + uri + " " + data.length + "b " + mime);
        return r;
    }

    /**
     * "bytes=start-end" | "bytes=start-" -> {start, end} clamped to
     * [0, len-1], or null when unsatisfiable. Suffix ranges ("bytes=-N")
     * are not used by the engine's downloader — answered unsatisfiable.
     */
    private static long[] parseByteRange(String range, long len) {
        try {
            String spec = range.substring("bytes=".length()).trim();
            int dash = spec.indexOf('-');
            if (dash <= 0) return null;           // suffix or malformed
            long start = Long.parseLong(spec.substring(0, dash).trim());
            String endPart = spec.substring(dash + 1).trim();
            long end = endPart.isEmpty() ? len - 1 : Long.parseLong(endPart);
            if (end >= len) end = len - 1;
            if (start < 0 || start > end || start >= len) return null;
            return new long[]{start, end};
        } catch (Throwable t) {
            return null;
        }
    }

    /** GET /localapi/skins/icons/<id>.png — one skin icon's bytes. */
    private Response serveSkinIcon(String name) {
        long id = -1;
        try {
            id = Long.parseLong(name.replaceAll("\\.[a-zA-Z]+$", ""));
        } catch (Throwable ignore) {
            // falls through to the miss response
        }
        byte[] data = id > 0 ? Skins.iconBytes(store, id) : null;
        if (data == null) {
            L.i("SKINICON miss " + name);
            return respond("{\"code\":0,\"message\":\"icon not available\"}");
        }
        String mime = Skins.sniffMime(data);
        InputStream in = new ByteArrayInputStream(data);
        Response r = newFixedLengthResponse(Response.Status.OK, mime, in, data.length);
        r.addHeader("Access-Control-Allow-Origin", "*");
        r.addHeader("Cache-Control", "max-age=86400");
        L.i("SKINICON " + id + " " + data.length + "b " + mime);
        return r;
    }

    /** GET /localapi/games/icons/<gid>.png — one game's official icon bytes. */
    private Response serveGameIcon(String name) {
        byte[] data = GameIcons.bytes(store, name);
        if (data == null) {
            L.i("GAMEICON miss " + name);
            return respond("{\"code\":0,\"message\":\"icon not available\"}");
        }
        String mime = Skins.sniffMime(data);
        InputStream in = new ByteArrayInputStream(data);
        Response r = newFixedLengthResponse(Response.Status.OK, mime, in, data.length);
        r.addHeader("Access-Control-Allow-Origin", "*");
        r.addHeader("Cache-Control", "max-age=86400");
        L.i("GAMEICON " + name + " " + data.length + "b " + mime);
        return r;
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
        // INTERNAL: the on-device GameServer's Lua WebService calls these
        // inner endpoints (serverConfig blockymodsRewardAddr /
        // gameDataServiceAddr point HERE since v0.6.25-innerhttp). The
        // login-critical one is /user/api/v1/inner/user/details - without
        // data the Lua refuses the whole login (S2CPacketLoginResult
        // code=3, emErrGetUserAttrFail; run 38115464141).
        if (cleanUri.startsWith("/user/api/v1/inner/")
                || cleanUri.startsWith("/activity/api/v1/inner/")
                || cleanUri.startsWith("/gameaide/api/v1/inner/")
                || cleanUri.startsWith("/game/api/v1/inner/")
                || cleanUri.startsWith("/game/api/v1/users/games/settlement")
                || cleanUri.startsWith("/pay/api/v1/pay/inner/")
                || cleanUri.startsWith("/pay/api/v1/inner/")
                || cleanUri.startsWith("/pay/pay/api/v1/inner/")
                || cleanUri.startsWith("/pay/api/v2/inner/")
                || cleanUri.startsWith("/api/v2/game/data")) {
            try {
                return Handlers.gameServerInner(ctx, store);
            } catch (Throwable t) {
                L.e("gs-inner handler threw: " + t);
                return "{\"code\":0,\"message\":\"ok\",\"data\":null}";
            }
        }
        if (cleanUri.equals("/v1/joinbridge")) {
            // INTERNAL: the UI process's JoinBridge asks THIS holder to
            // guarantee a monitor-linked engine and push the join attrs.
            // Cross-process by design: the monitor/engine ownership lives
            // in the holder, never in the (churned) UI process.
            try {
                return Handlers.joinBridge(ctx, store);
            } catch (Throwable t) {
                L.e("joinbridge handler threw: " + t);
                return "{\"code\":1,\"pushed\":false,\"gameConnected\":false,\"error\":\"thrown\"}";
            }
        }
        if (cleanUri.equals("/v1/dispatch-party")) {
            // INTERNAL (engine 10078): GameGroupManager.takeGroupStart's
            // group dispatch — the Lua reaches it through OUR disp-cluster
            // dispUrl answer. Must precede the RoutingTable (which knows
            // /v1/dispatch but not the -party variant).
            try {
                return Handlers.dispatchParty(ctx, store);
            } catch (Throwable t) {
                L.e("dispatch-party handler threw: " + t);
                return "{\"code\":0,\"message\":\"error\",\"data\":null}";
            }
        }
        if (cleanUri.startsWith("/config/files/player-identity-config")) {
            // INTERNAL (engine 10078): WebService.GetPlayerIdentityCache.
            // ONLY this file name — the RoutingTable owns every OTHER
            // /config/files/{name} (check-version, banner, sensitive words,
            // ads-cd... 14 app-facing handlers; a blanket prefix hijacked
            // them and broke the suite).
            try {
                return Handlers.gameServerInner(ctx, store);
            } catch (Throwable t) {
                L.e("gs-inner config threw: " + t);
                return "{\"code\":0,\"message\":\"ok\",\"data\":null}";
            }
        }
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
