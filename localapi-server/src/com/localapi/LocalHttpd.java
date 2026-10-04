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

    public boolean isUp() {
        return started;
    }

    @Override
    public Response serve(final IHTTPSession session) {
        final String verb = session.getMethod().name();
        final String uri = session.getUri();
        final String body = readBody(session);

        final java.util.Map<String, String> pathParams = new java.util.HashMap<>();
        final String fBody = body;
        final Handlers.Ctx ctx = new Handlers.Ctx() {
            public String query(String name) {
                List<String> vals = session.getParameters().get(name);
                return (vals == null || vals.isEmpty()) ? null : vals.get(0);
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

            public String pathParam(String name) {
                return pathParams.get(name);
            }
        };

        String json = route(verb, uri, ctx, pathParams);
        L.i("REQ " + verb + " " + uri
                + (fBody.isEmpty() ? "" : " body=" + Handlers.abbrev(fBody)));
        L.i("RES " + verb + " " + uri + " " + json.length() + "b");
        return respond(json);
    }

    /**
     * Raw body reader: drains exactly Content-Length bytes from the socket so
     * keep-alive connections stay in sync. NanoHTTPD 2.3.1's parseBody hides
     * JSON bodies of PUT requests, so we read them ourselves.
     */
    private static String readBody(IHTTPSession session) {
        try {
            String len = session.getHeaders().get("content-length");
            if (len == null) {
                return "";
            }
            int n = Integer.parseInt(len.trim());
            if (n <= 0) {
                return "";
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
            return new String(buf, 0, off, StandardCharsets.UTF_8);
        } catch (Throwable t) {
            L.e("body read failed: " + t);
            return "";
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
