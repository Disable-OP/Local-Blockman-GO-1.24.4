package com.localapi;

import android.content.Context;
import android.os.Environment;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.util.zip.GZIPInputStream;

import org.json.JSONObject;

/**
 * Stages and runs the on-device GameServer (arm64 C++ binary, engine 10068).
 *
 * Layout on the device:
 *   filesDir/gameserver-bundle/          — runtime bundle (tar.gz from the
 *                                          localapi-assets release): resource.cfg,
 *                                          engineVersion.json, ScriptSetting.csv,
 *                                          GameSetting/, Setting/, recipe/, bt/,
 *                                          scripts/BedWar/ (merged plugin tree),
 *                                          maps/g1008/m1008_2/
 *   nativeLibraryDir/libgameserver.so    — the binary, packaged as jniLibs so it
 *                                          lands in an executable app dir
 *   /storage/emulated/<runtime-id>/SandBoxOL/BlockMan/config/  — the client's own
 *                                          config dir (client.log lives here);
 *                                          the GameServer's logdir is set there
 *                                          too, so the engine writes server.log
 *                                          right next to it. The storage id is
 *                                          resolved at RUNTIME (never hardcoded).
 *
 * The server reads its RoomGameConfig from ./serverConfig.json in its CWD
 * (dev/server/src/main.cpp: argc==1 -> getTestRGConfig("serverConfig.json")).
 */
public final class GameServerManager {
    /** RakNet listen port the engine will be pointed at via Dispatch.gaddr. */
    public static final int GAME_PORT = 31108;

    /** The room this manager configures the engine with (serverConfig.json):
     *  a BedWar g1008 room on map m1008_2. Dispatch pins every join to THIS
     *  game while the server is alive (Handlers.dispatch) — the engine is
     *  server-authoritative, so whatever hall card the player tapped, the
     *  room they join runs the game the on-device server actually hosts. */
    public static final String ENGINE_GAME_ID = "g1008";
    public static final String ENGINE_MAP_ID = "m1008_2";

    /** The engine version the CLIENT (1.24.4, classic resources path) sends
     *  in C2SPacketCheckCSVersion - its own engineVersion.json (assets/
     *  resources/Media) says 10068. The server must report the SAME value
     *  or C2SPacketLogin is refused (C2SInitPacketHandles: version mismatch
     *  -> S2CPacketCheckCSVersionResult{success=false} -> the client logs
     *  "check version fail, server version = 10000" and drops the link
     *  BEFORE ever sending the login - run 38096189424).
     *  KEPT for the host rig + callers: the RUNTIME value is the line's
     *  clientEngineVersion (GsLine, seed asset gs-line.json) — 10068 for
     *  the 1.24.4 line, 10078 for the 2.8.2 line. */
    public static final int CLIENT_ENGINE_VERSION = 10068;
    public static final String ENGINE_GAME_NAME = "BedWar";

    private static final String BUNDLE_DIR = "gameserver-bundle";
    private static final String STAGE_VERSION_FILE = "stage-version";
    /** @deprecated the RUNTIME stage marker is the line's stageVersion
     *  (DEFAULT_LINE.stageVersion keeps this value for the 1.24.4 line). */
    private static final String STAGE_VERSION = "g1008-b2"; // bump to restage

    /** Script-tree overlay marker: completes the merged BedWar plugin tree
     *  with the BaseGame mirror files the engine's Lua loader needs. */
    private static final String OVERLAY_VERSION_FILE = "overlay-version";
    /** v4 = v3 + friendlier Bedwars AI: the overlay now carries patched
     *  AIConfig.csv (archeryHitRate 0.3->0.12, archeryDamage 3#5->1#2,
     *  attackCd 1#3->2#4, archeryCd 3#6->4#8, followRange 30->20,
     *  archeryRange 25->18, followTime 8->4) + AiPlayerConfig.csv
     *  (row 107: team 3's second attacker -> gatherer) + a recomputed
     *  checksums.md5, all copied over the staged bundle's map dir
     *  (maps/g1008/m1008_2) at apply time. The bot wave still fires and
     *  the match still starts — the AFK human now survives minutes
     *  instead of dying every ~4-8s to knockback void falls. */
    /** v5 (2026-10-11): WebService:Pay's hardcoded http://127.0.0.1:8080
     *  purchase URL -> self.ServerHttpHost (the 18080 holder) — the in-game
     *  shop's /pay/api/v2/inner/pay/users/purchase/game/props never had a
     *  listener on 8080, so every prop buy silently failed (the physical-
     *  phone tester's "buy works but no item"). v4's friendly-AI csvs carry
     *  forward unchanged. */
    private static final String OVERLAY_VERSION = "bedwar-full-5"; // bump to re-apply

    /**
     * Engine line — DATA-DRIVEN so ONE server dex serves both client lines.
     *
     * The 2.8.2 client (engine 10078) APK ships a seed asset
     * assets/localapi/gs-line.json (LocalServer copies it to
     * filesDir/localapi/gs_line.json); the 1.24.4 client ships NONE and
     * gets exactly the proven defaults below — byte-identical behavior to
     * every green run before this change (zero regression by construction).
     *
     * The g10078 line (verified against the g10078 runtime bundle, session
     * 66/cron):
     *   - clientEngineVersion 10078 — the 2.8.2 client's engineVersion.json
     *     says 10078; the server must report the same (C2S version gate).
     *   - bundle gameserver-runtime-g10078.tar.gz — hosts the SAME room
     *     (ScriptSetting g1008 BedWar, maps/g1008/m1008_2, scriptdir
     *     scripts/BedWar) with 10078-era Lua + 10078 id_mappings + the 20
     *     fresh CDN mca; its own engineVersion.json already says 10078.
     *   - applyOverlay=false — the 10078-era WebService.lua is already
     *     config-driven (self.ServerHttpHost = blockymodsRewardAddr) and
     *     the bundle carries the tuned csvs inline; the 10068 overlay
     *     would only CLOBBER the 10078 scripts (docs §8 risk).
     *   - a distinct stageVersion so a device that stages both lines
     *     restages cleanly (per-line markers, never shared).
     */
    static final class GsLine {
        final String id;
        final int clientEngineVersion;
        final String stageVersion;
        final boolean applyOverlay;
        GsLine(String id, int clientEngineVersion, String stageVersion,
               boolean applyOverlay) {
            this.id = id;
            this.clientEngineVersion = clientEngineVersion;
            this.stageVersion = stageVersion;
            this.applyOverlay = applyOverlay;
        }
    }

    /** The proven 1.24.4 line — the defaults when no seed asset ships. */
    private static final GsLine DEFAULT_LINE =
            new GsLine("g1008", 10068, "g1008-b2", true);

    private static volatile GsLine sLine;

    /** Resolve the engine line (seed file wins, defaults otherwise). */
    private static GsLine line(Context ctx) {
        GsLine l = sLine;
        if (l != null) return l;
        synchronized (GameServerManager.class) {
            if (sLine == null) sLine = readLine(ctx);
            return sLine;
        }
    }

    /** Parse filesDir/localapi/gs_line.json (LocalServer seeds it from the
     *  APK asset). Any absence/corruption falls back to DEFAULT_LINE. */
    private static GsLine readLine(Context ctx) {
        try {
            Context c = ctx != null ? ctx : sAppContext;
            if (c == null) return DEFAULT_LINE;
            File f = new File(new File(c.getFilesDir(), "localapi"),
                    "gs_line.json");
            if (!f.isFile()) return DEFAULT_LINE;
            byte[] b = new byte[(int) Math.min(f.length(), 4096)];
            FileInputStream in = new FileInputStream(f);
            int n = in.read(b);
            in.close();
            JSONObject o = new JSONObject(new String(b, 0, Math.max(0, n),
                    "UTF-8"));
            String id = o.optString("line", DEFAULT_LINE.id);
            if (!id.matches("g[0-9]+")) id = DEFAULT_LINE.id; // paranoia
            int ver = o.optInt("clientEngineVersion",
                    DEFAULT_LINE.clientEngineVersion);
            String stage = o.optString("stageVersion", id + "-b1");
            boolean overlay = o.optBoolean("applyOverlay",
                    DEFAULT_LINE.applyOverlay);
            GsLine l = new GsLine(id, ver, stage, overlay);
            L.i("gs: engine line " + l.id + " engine=" + l.clientEngineVersion
                    + " stage=" + l.stageVersion + " overlay=" + l.applyOverlay);
            return l;
        } catch (Throwable t) {
            L.e("gs: gs-line parse failed -> defaults: " + t);
            return DEFAULT_LINE;
        }
    }

    /** Engine-faithful runtime layout: the server CWD is <bundle>/server
     *  (resource.cfg reads ../client/), while GameServerManager's staging
     *  dir stays the bundle root. The staged tarball is itself rooted at
     *  bundle/ (build_runtime_bundle.py layout), so the real root may be
     *  <staging>/bundle — detect instead of assuming (run 210 lesson: the
     *  server never found resource.cfg one level short). */
    private static File bundleRoot() {
        File nested = new File(sBundleDir, "bundle");
        return new File(nested, "server").isDirectory() ? nested : sBundleDir;
    }

    private static File serverDir() {
        return new File(bundleRoot(), "server");
    }

    private static final Object LOCK = new Object();
    private static Process sProcess;
    private static File sBundleDir;
    private static File sLogDir;
    private static boolean sAttempted;
    private static Context sAppContext;
    private static final Object KICK_LOCK = new Object();
    private static boolean sKickRunning;

    private GameServerManager() {}

    /** Release base — same release the map/dress packs ride. */
    private static final String RELEASE_BASE = System.getProperty(
            "localapi.gsReleaseBase",
            "https://github.com/Disable-OP/Local-Blockman-GO-1.24.4"
                    + "/releases/download/localapi-assets");

    private static String releaseBase() {
        return RELEASE_BASE;
    }

    private static String bundleUrl() {
        // engine-line aware: g1008 (1.24.4) | g10078 (2.8.2) — both assets
        // ride the same localapi-assets release.
        return releaseBase() + "/gameserver-runtime-"
                + line(sAppContext).id + ".tar.gz";
    }

    private static String overlayUrl() {
        return releaseBase() + "/servergame-bedwar-full.tar.gz";
    }

    private static String serverUrl() {
        return releaseBase() + "/libgameserver-arm64.so";
    }

    /**
     * Stage the runtime bundle + fetch the server binary into the bundle dir.
     * Best effort: any failure leaves the previous stage intact and only means
     * "no gameplay server this boot" — the map-phase behavior is untouched.
     */
    public static void ensure(Context context) {
        synchronized (LOCK) {
            if (sAttempted) return;
            sAttempted = true;
            sAppContext = context.getApplicationContext();
            try {
                File files = context.getFilesDir();
                sBundleDir = new File(files, BUNDLE_DIR);
                final GsLine ln = line(context);
                File marker = new File(sBundleDir, STAGE_VERSION_FILE);
                boolean needStage = !marker.exists()
                        || !ln.stageVersion.equals(readText(marker));
                if (needStage) {
                    L.i("gs: staging runtime bundle (line " + ln.id + ") ...");
                    File tar = download(bundleUrl(), "gameserver-runtime.tar.gz",
                            128 * 1024 * 1024);
                    untarGz(tar, sBundleDir);
                    writeText(marker, ln.stageVersion);
                    L.i("gs: bundle staged at " + sBundleDir);
                }
                // Complete the BedWar plugin tree (BaseGame mirror files).
                // Also re-applies after a re-stage so overlay and bundle stay
                // in lockstep. The g10078 line SKIPS this (its bundle already
                // carries the full 10078-era tree inline; the 10068 overlay
                // would clobber it — docs/10078_GAME_SERVER_UPDATE.md §8).
                if (ln.applyOverlay) {
                    ensureScriptOverlay();
                } else {
                    L.i("gs: script overlay skipped (line " + ln.id
                            + " ships the scripts inline)");
                }
                // The binary rides the APK as jniLibs (nativeLibraryDir). When
                // the APK does not carry it yet (older build), fall back to a
                // release download into the bundle dir.
                if (findBinary(context) == null) {
                    File dl = download(serverUrl(), "libgameserver.so",
                            80 * 1024 * 1024);
                    File dst = new File(sBundleDir, "libgameserver.so");
                    if (!dl.renameTo(dst)) {
                        copy(dl, dst);
                    }
                    // filesDir exec: allowed for legacy targetSdk apps only;
                    // chmod +x for good measure.
                    try {
                        Runtime.getRuntime().exec(
                                new String[]{"chmod", "755", dst.getAbsolutePath()})
                                .waitFor();
                    } catch (Throwable ignored) {}
                }
            } catch (Throwable t) {
                L.e("gs: ensure failed: " + t);
                // allow a later kick() to retry the staging (a failed 64MB
                // download must not be permanent for this process)
                sAttempted = false;
            }
        }
    }

    /**
     * Complete the staged bundle's merged BedWar plugin tree
     * (<bundleRoot>/server/scripts/BedWar) with the BaseGame mirror files:
     * base/Base.lua, base/util/class.lua + the other base.util helpers,
     * base/define/*, base/task/LuaTimer.lua, common/config/ItemConfig.lua,
     * game/config/*, hall/config/*, common/info|manager/* and Loader.lua.
     *
     * v2 also drops the OFFICIAL m1008_2 server-side config sidecars into
     * the map dir: SkillConfig.csv (the v0.6.23 verdict's gate —
     * game/config/GameConfig.lua:137 SkillConfig:init(FileUtil
     * .getConfigFromCsv("SkillConfig.csv")) asserts the file exists;
     * without it onGameInit aborts after GameConfig:init and the room
     * never initializes join/team logic) + id_mappings.ini (Server.cpp
     * reads <mapdir>/id_mappings.ini for custom blocks). Both extracted
     * from the official maps.tar.gz room-service sidecars
     * (m1008_2.1619441309722.SkillConfig.csv /
     * m1008_2.1597134108034.id_mappings.ini). The stale sidecar .mca
     * region files are deliberately NOT shipped: the newer official map
     * zip (already staged + mapExistsAndValid-verified) contains the
     * merged terrain.
     *
     * WITHOUT the script half the engine's Lua load dies at BaseMain.lua:19
     * ("module 'base.Base' not found") and then at ScriptMain.lua:3
     * ("attempt to index global 'BaseListener' (a nil value)") — both seen
     * verbatim in server.log (run 38109076258) — so the world runs with NO
     * game logic and every join lands in the engine's watch-mode fallback
     * (spectator), which is exactly the S2CPacketSetWatchMode(true) verdict
     * of session 58 cont. 6.
     *
     * The overlay is additive (scripts/BedWar = 304-file tree = the
     * previous 230 + 74 BaseGame files, zero path collisions, verified;
     * maps/g1008/m1008_2 = 2 official sidecars) and idempotent via its
     * own version marker. serverConfig scriptdir is UNCHANGED — the
     * engine contract (scriptdir/base/BaseMain.lua + scriptdir/
     * ScriptMain.lua + optional scriptdir/Loader.lua) holds as-is.
     */
    private static void ensureScriptOverlay() {
        try {
            File marker = new File(sBundleDir, OVERLAY_VERSION_FILE);
            if (marker.exists() && OVERLAY_VERSION.equals(readText(marker))) {
                return;
            }
            L.i("gs: applying script overlay " + OVERLAY_VERSION + " ...");
            File tar = download(overlayUrl(), "servergame-bedwar-full.tar.gz",
                    8 * 1024 * 1024);
            untarGz(tar, serverDir());
            writeText(marker, OVERLAY_VERSION);
            File tree = new File(new File(serverDir(), "scripts"), "BedWar");
            int n = 0;
            File[] kids = tree.listFiles();
            if (kids != null) n = kids.length;
            L.i("gs: script overlay applied -> " + tree + " (" + n
                    + " top-level entries)");
        } catch (Throwable t) {
            L.e("gs: script overlay failed: " + t);
        }
    }

    /**
     * Lazy engine boot hook for the join moment (dispatch): the FIRST app
     * boot can still be downloading the 64MB runtime bundle when its
     * one-shot startIfPossible finds resource.cfg missing and gives up —
     * and nothing ever retried in that process (run 38073049374: the first
     * boot never started the engine at all; only the Phase-D relaunch did).
     * Dispatch is THE join moment: retry the boot here, in the background.
     * Idempotent: isAlive early-return + single-flight guard.
     *
     * @return true when a boot attempt is now in flight (the caller may
     *         briefly wait for gameAddr() to become non-null); false when
     *         no boot is possible (host rig / no context) or already alive.
     */
    public static boolean kick() {
        if (isAlive()) return false;
        final Context app = sAppContext;
        if (app == null) return false;
        synchronized (KICK_LOCK) {
            if (sKickRunning) return true;
            sKickRunning = true;
        }
        Thread t = new Thread(new Runnable() {
            @Override public void run() {
                try {
                    ensure(app);
                    startIfPossible(app);
                } catch (Throwable t2) {
                    L.e("gs: kick failed: " + t2);
                } finally {
                    synchronized (KICK_LOCK) { sKickRunning = false; }
                }
            }
        }, "LocalApiGsKick");
        t.setDaemon(true);
        t.start();
        return true;
    }

    /** Launch the GameServer if the bundle + binary are ready. */
    public static void startIfPossible(Context context) {
        synchronized (LOCK) {
            if (isAlive()) return;
            spawnLocked(context);
        }
    }

    /**
     * Join-time guarantee (called from JoinBridge's thread, BEFORE startGame
     * posts): the monitor link must be up and owned by THIS holder, and the
     * engine behind it must be a process this holder spawned. A STALE engine
     * (spawned by a now-dead holder) keeps RakNet 31108 alive - the client
     * CAN connect to it - but its monitor link died with the old holder, so
     * the attrs have nowhere to land and the engine can never validate the
     * C2S login (no S2CPacketLoginResult -> emConnectTimeout, run
     * 38091124122). Sweeping + respawning is SAFE here: the client engine
     * boots only after startGame is posted, so it will connect to the FRESH
     * engine whose monitor is linked to THIS holder.
     *
     * RATE LIMIT (run 38097963853): the callers poll every ~1s and each
     * call used to sweep+respawn immediately - the fresh engine (boot ~2-4s
     * to the RoomClient monitor connect) was killed by the NEXT call's
     * sweep before it could ever link, so gameConnected() stayed false
     * forever. After a respawn, give the engine a 9s window before the
     * next sweep+respawn is allowed.
     */
    private static long sLastRespawnMs;

    public static void ensureLiveEngine() {
        synchronized (LOCK) {
            try {
                if (!LocalServer.isServingLoopback()) return;
                if (isAlive() && MonitorServer.gameConnected()) return;
                // SWEEP FIRST, then rebind: an ORPHANED engine (spawned by a
                // dead holder) INHERITED the old holder's listening fd, so
                // 18081 stays bound with NO accept loop behind it - new
                // MonitorServer.start() calls fail with EADDRINUSE and the
                // fresh engines' connects pile into the dead backlog and
                // then get refused (runs 38096189424/38097963853/
                // 38099558911). killall/pkill do not exist in redroid - the
                // /proc walk is the reliable kill.
                killStaleEngines();
                try { Thread.sleep(400L); }
                catch (InterruptedException ie) { return; }
                MonitorServer.start(); // now bindable
                if (isAlive() && MonitorServer.gameConnected()) return;
                long now = System.currentTimeMillis();
                if (now - sLastRespawnMs < 9000L) {
                    return; // a fresh engine is booting - let it connect
                }
                sLastRespawnMs = now;
                L.i("gs: ensureLiveEngine: monitor-linked engine missing"
                        + " (alive=" + isAlive() + " connected="
                        + MonitorServer.gameConnected() + ") - respawning");
                spawnLocked(sAppContext);
            } catch (Throwable t) {
                L.e("gs: ensureLiveEngine failed: " + t);
            }
        }
    }

    /**
     * Kill every live libgameserver process this uid can see. killall and
     * pkill are NOT present in the redroid system image (toybox lacks them)
     * - the /proc walk + kill is what actually works. Orphaned engines from
     * dead holders hold the monitor listener fd (inherited at spawn), so
     * this sweep is ALSO what frees 18081 for the next bind.
     */
    private static void killStaleEngines() {
        // best-effort shells first (harmless if missing)
        try {
            java.lang.Process k = Runtime.getRuntime().exec(
                    new String[]{"killall", "libgameserver.so"});
            k.waitFor();
        } catch (Throwable ignored) {}
        try {
            java.lang.Process k = Runtime.getRuntime().exec(
                    new String[]{"/system/bin/sh", "-c",
                            "pkill -f libgameserver.so 2>/dev/null"});
            k.waitFor();
        } catch (Throwable ignored) {}
        // /proc walk: the reliable kill (same-uid processes only)
        File proc = new File("/proc");
        File[] entries = proc.listFiles();
        if (entries == null) return;
        StringBuilder pids = new StringBuilder();
        for (File e : entries) {
            String name = e.getName();
            boolean numeric = name.length() > 0;
            for (int i = 0; i < name.length() && numeric; i++) {
                char c = name.charAt(i);
                if (c < '0' || c > '9') numeric = false;
            }
            if (!numeric || !e.isDirectory()) continue;
            java.io.FileInputStream in = null;
            try {
                in = new java.io.FileInputStream(new File(e, "cmdline"));
                byte[] buf = new byte[512];
                int n = in.read(buf);
                if (n <= 0) continue;
                String cmd = new String(buf, 0, n, "UTF-8");
                if (cmd.contains("libgameserver")) {
                    pids.append(name).append(' ');
                }
            } catch (Throwable ignored) {
            } finally {
                if (in != null) try { in.close(); } catch (Throwable ignored) {}
            }
        }
        if (pids.length() > 0) {
            L.i("gs: stale-engine /proc sweep kill: " + pids.toString().trim());
            try {
                java.lang.Process k = Runtime.getRuntime().exec(new String[]{
                        "/system/bin/sh", "-c", "kill -9 " + pids});
                k.waitFor();
            } catch (Throwable ignored) {}
        }
    }

    /**
     * The engine loads engineVersion.json through the ResourceGroupManager;
     * the server's resource.cfg mounts ONLY ../client/... paths (no ./), and
     * the bundle ships the file at bundle/server/engineVersion.json where NO
     * group can see it ("Cannot locate a resource [engineVersion.json] in
     * resource group [General] or any other group", run 38096189424) ->
     * EngineVersionSetting defaults to 10000 -> the client's C2S version
     * 10068 is rejected BEFORE the login -> ID_CONNECTION_LOST.
     * Write the file into the MOUNTED ../client/ dir (bundle/client/) - the
     * app's filesDir is writable, no bundle rebuild needed.
     */
    private static void ensureEngineVersionFile() {
        try {
            File clientDir = new File(bundleRoot(), "client");
            if (!clientDir.isDirectory()) {
                L.e("gs: engineVersion: client dir missing: " + clientDir);
                return;
            }
            File f = new File(clientDir, "engineVersion.json");
            final int ver = line(sAppContext).clientEngineVersion;
            // Overwrite when the staged file disagrees with the line (a
            // re-stage swaps bundles; the g10078 bundle's own file already
            // says 10078 and is then kept byte-identical).
            if (f.isFile() && f.length() > 0
                    && readText(f).contains("\"engineVersion\": " + ver)) {
                return;
            }
            writeText(f, "{\n  \"engineVersion\": " + ver
                    + ",\n  \"useCmd\": \"true\",\n  \"logLevel\": \"debug\"\n}\n");
            L.i("gs: engineVersion.json written -> " + f + " (" + ver + ")");
        } catch (Throwable t) {
            L.e("gs: engineVersion.json write failed: " + t);
        }
    }

    /** Preconditions + config + stale sweep + launch. Callers hold LOCK. */
    private static void spawnLocked(Context context) {
        try {
            // ONLY the process that actually serves the local API may
            // own the engine: standby/watchdog sibling processes used
            // to spawn their own engine seconds after the holder's
            // (run 38073049374: engines at 17:51:16 + 17:51:22 from two
            // live processes - the second lost the RakNet 31108 bind
            // for good). The engine's monitor + dispatch state are
            // in-process, so engine ownership MUST follow the holder.
            if (!LocalServer.isServingLoopback()) {
                L.i("gs: not started (this process does not serve the "
                        + "local API - standby sibling)");
                return;
            }
                File bin = findBinary(context);
                File cwd = serverDir();
                // NOTE: serverConfig.json is OWNED by this manager and is
                // (re)written below on every start — it must NOT be a
                // precondition (run 210: the old check required the file to
                // already exist, but only this method creates it -> the
                // server could never start). Only the binary and the
                // engine-faithful resource.cfg are real preconditions.
                File cfg = new File(cwd, "serverConfig.json");
                if (bin == null
                        || !new File(cwd, "resource.cfg").exists()) {
                    L.i("gs: not started (binary=" + (bin != null)
                            + " resource.cfg="
                            + new File(cwd, "resource.cfg").exists() + " cwd="
                            + cwd + ")");
                    return;
                }
                MonitorServer.start();
                if (MonitorServer.boundPort() == 0) {
                    L.e("gs: not started (no bindable monitor port)");
                    return;
                }
                sLogDir = resolveLogDir(context);
                writeServerConfig(cfg);
                ensureEngineVersionFile();
                // Kill stale engine instances from earlier app boots FIRST:
                // every boot spawned a new libgameserver while old ones kept
                // running (isAlive() only tracks THIS boot's Process object).
                // A stale engine still holding RakNet 31108 makes the fresh
                // engine's bind fail for its WHOLE lifetime
                // ("m_isRaknetAlive == false" in server.log, run
                // 38073049374: two engines 6s apart, the second never
                // listenable) — the client can then never join. Best
                // effort: killall/pkill may not exist; errors ignored.
                try {
                    java.lang.Process k = Runtime.getRuntime().exec(
                            new String[]{"killall", "libgameserver.so"});
                    k.waitFor();
                } catch (Throwable ignored) {}
                try {
                    java.lang.Process k = Runtime.getRuntime().exec(
                            new String[]{"/system/bin/sh", "-c",
                                    "pkill -f libgameserver.so 2>/dev/null"});
                    k.waitFor();
                } catch (Throwable ignored) {}
                try { Thread.sleep(400); }
                catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
                L.i("gs: stale engine sweep done, launching");
                // Pass the config as argv[1] (the engine's
                // getRGConfigFromCmdline path, main.cpp argc>1). The argc==1
                // getTestRGConfig path reads a COMPLETELY DIFFERENT key set
                // (gameId/serverPort/monitorAddr/...) UNGUARDED — a config
                // in our key shape is UB there (run 212: SIGSEGV fault addr
                // 0x2 ~100ms after exec, every launch). The cmdline path
                // reads exactly the keys writeServerConfig emits, all
                // HasMember-guarded, including logdir/scriptdir/mapdir.
                String cfgJson;
                {
                    byte[] b = new byte[(int) Math.min(cfg.length(), 65536)];
                    java.io.FileInputStream in = new java.io.FileInputStream(cfg);
                    int n = in.read(b);
                    in.close();
                    cfgJson = new String(b, 0, Math.max(0, n), "UTF-8");
                }
                ProcessBuilder pb = new ProcessBuilder(bin.getAbsolutePath(), cfgJson);
                pb.directory(cwd);          // CWD: resource.cfg lives here
                pb.redirectErrorStream(true);
                sProcess = pb.start();
                final Process p = sProcess;
                Thread pump = new Thread(() -> {
                    try {
                        java.io.BufferedReader r = new java.io.BufferedReader(
                                new java.io.InputStreamReader(p.getInputStream()));
                        String line;
                        while ((line = r.readLine()) != null) {
                            L.gs(line);
                        }
                    } catch (Throwable ignored) {}
                }, "LocalApiGsPump");
                pump.setDaemon(true);
                pump.start();
                L.i("gs: launched pid=" + pid() + " logdir=" + sLogDir
                        + " port=" + GAME_PORT);
        } catch (Throwable t) {
            L.e("gs: start failed: " + t);
        }
    }

    public static boolean isAlive() {
        Process p = sProcess;
        return p != null && p.isAlive();
    }

    /** Dispatch.gaddr target while the gameplay server runs. */
    public static String gameAddr() {
        return isAlive() ? ("127.0.0.1:" + GAME_PORT) : null;
    }

    /** Push this user's room attributes after a dispatch was served. */
    public static void notifyDispatch(long uid, String requestId, int sex,
                                      String name, int vip, String country) {
        if (isAlive() && MonitorServer.gameConnected()) {
            MonitorServer.pushUserAttr(uid, requestId, sex, name, vip, country);
        }
    }

    // ------------------------------------------------------------------

    /**
     * Pre-place the engine's map bundle where the CLIENT engine's
     * MapManager::n (mapExistsAndValid) expects it, so the engine's own
     * downloader is never needed: its native PathUtil::CreateDir fails on
     * the emulated-storage dir chain ("error code 17, dir [storage/emulated/]",
     * run 38089237461) and CGame::onDownloadMapFailure aborts after two
     * tries — the RakNet connect then never happens.
     *
     * Expected layout (MapManager.cpp lines 36-107):
     *   <root>/<spelling>/BlockMan/map/m1008_2/                     (dir)
     *   <root>/<spelling>/BlockMan/map/m1008_2/<mapNameReal>.zip    (file)
     *   <root>/<spelling>/BlockMan/map/m1008_2/<mapNameReal>/       (extracted,
     *                                    with a verifying checksums.md5)
     * A stale <mapNameReal>_temp.zip (broken-transfer marker) is removed.
     *
     * The zip source is the same file the local server serves at
     * /sandbox/games/maps/<zipName> (the official map bundle). Idempotent:
     * existing byte-identical zip + extracted dir are left untouched.
     * Both "SandboxOL" (the engine's own spelling seen in client.log) and
     * "SandBoxOL" (the app's logdir spelling) are covered.
     */
    public static void ensureEngineMap() {
        try {
            StateStore store = MapAssets.store();
            if (store == null) {
                L.e("gs: ensureEngineMap: no store yet");
                return;
            }
            JSONObject entry = MapAssets.entryForGame(ENGINE_GAME_ID);
            String zipName = entry == null ? "" : entry.optString("zipName");
            if (zipName == null || zipName.isEmpty() || !zipName.endsWith(".zip")) {
                L.e("gs: ensureEngineMap: no map bundle entry for "
                        + ENGINE_GAME_ID);
                return;
            }
            File zip = MapAssets.resolveUri(store, "sandbox/games/maps/" + zipName);
            if (zip == null || !zip.isFile()) {
                L.e("gs: ensureEngineMap: bundle not staged yet (" + zipName + ")");
                return;
            }
            String mapNameReal = zipName.substring(0, zipName.length() - 4);
            int placed = 0;
            File ext = Environment.getExternalStorageDirectory();
            File[] roots = (ext != null)
                    ? new File[]{ext, new File("/storage/emulated/0")}
                    : new File[]{new File("/storage/emulated/0")};
            for (File root : roots) {
                if (root == null) continue;
                for (String spelling : new String[]{"SandboxOL", "SandBoxOL"}) {
                    File mapIdDir = new File(root,
                            spelling + "/BlockMan/map/" + ENGINE_MAP_ID);
                    if (placeMap(mapIdDir, zip, mapNameReal)) placed++;
                }
            }
            // SCOPED-STORAGE roots (2.8.2 line): targetSdk 29 on Android 11+
            // cannot mkdir in the emulated-storage root (the smoke evidence:
            // "placeMap: mkdirs failed: /storage/emulated/0/SandBoxOL/...").
            // The app-OWN external dirs stay writable — cover both spellings
            // there too; a misplaced tree is harmless (placeMap is
            // idempotent and the engine reads only the root it resolves).
            try {
                Context c = sAppContext;
                File own = c != null ? c.getExternalFilesDir(null) : null;
                if (own != null) {
                    for (String spelling : new String[]{"SandboxOL", "SandBoxOL"}) {
                        File mapIdDir = new File(own,
                                spelling + "/BlockMan/map/" + ENGINE_MAP_ID);
                        if (placeMap(mapIdDir, zip, mapNameReal)) placed++;
                    }
                }
            } catch (Throwable ignored) {}
            L.i("gs: ensureEngineMap placed " + placed + " map tree(s) ("
                    + zipName + ", " + zip.length() + " B)");
        } catch (Throwable t) {
            L.e("gs: ensureEngineMap failed: " + t);
        }
    }

    /** Copy + extract the map bundle into mapIdDir. Returns true when the
     *  extracted tree exists afterwards. Never throws. */
    private static boolean placeMap(File mapIdDir, File zip, String mapNameReal) {
        try {
            if (!mapIdDir.isDirectory() && !mapIdDir.mkdirs()) {
                L.e("gs: placeMap: mkdirs failed: " + mapIdDir);
                return false;
            }
            File dstZip = new File(mapIdDir, mapNameReal + ".zip");
            if (!dstZip.isFile() || dstZip.length() != zip.length()) {
                copy(zip, dstZip);
            }
            // broken-transfer marker must not survive (mapExistsAndValid
            // refuses to run when it exists)
            new File(mapIdDir, mapNameReal + "_temp.zip").delete();
            File exDir = new File(mapIdDir, mapNameReal);
            File sum = new File(exDir, "checksums.md5");
            if (!sum.isFile()) {
                // wipe any partial tree first: mapExistsAndValid also checks
                // the file COUNT against the md5 entries, so a truncated
                // extraction would fail verification forever
                deleteRecursive(exDir);
                unzipZip(dstZip, exDir);
            }
            return exDir.isDirectory()
                    && new File(exDir, "checksums.md5").isFile();
        } catch (Throwable t) {
            L.e("gs: placeMap " + mapIdDir + " failed: " + t);
            return false;
        }
    }

    /** Recursive delete (partial extraction cleanup). */
    private static void deleteRecursive(File f) {
        try {
            File[] kids = f.listFiles();
            if (kids != null) {
                for (File k : kids) deleteRecursive(k);
            }
            f.delete();
        } catch (Throwable ignored) {}
    }

    /** Plain zip extraction (entries keep their relative paths). */
    private static void unzipZip(File zip, File intoDir) throws Exception {
        java.util.zip.ZipFile zf = new java.util.zip.ZipFile(zip);
        try {
            java.util.Enumeration<?> en = zf.entries();
            byte[] buf = new byte[64 * 1024];
            while (en.hasMoreElements()) {
                java.util.zip.ZipEntry e = (java.util.zip.ZipEntry) en.nextElement();
                if (e.isDirectory()) continue;
                File out = new File(intoDir, e.getName());
                if (!out.getCanonicalPath().startsWith(
                        intoDir.getCanonicalPath() + File.separator)) {
                    continue; // zip-slip guard
                }
                File parent = out.getParentFile();
                if (parent != null) parent.mkdirs();
                InputStream in = null;
                OutputStream os = null;
                try {
                    in = zf.getInputStream(e);
                    os = new FileOutputStream(out);
                    int n;
                    while ((n = in.read(buf)) > 0) os.write(buf, 0, n);
                } finally {
                    if (in != null) in.close();
                    if (os != null) os.close();
                }
            }
        } finally {
            zf.close();
        }
    }

    // ------------------------------------------------------------------

    /**
     * The client writes client.log into SandBoxOL/BlockMan/config on the
     * FIRST emulated storage root (the user-visible path is
     * /storage/emulated/0/SandBoxOL/BlockMan/config). The <id> differs per
     * device/profile, so it is resolved from the OS at runtime — never
     * hardcoded.
     */
    private static File resolveLogDir(Context context) {
        try {
            File ext = Environment.getExternalStorageDirectory();
            if (ext != null) {
                File dir = new File(new File(new File(ext, "SandBoxOL"), "BlockMan"), "config");
                if (dir.mkdirs() || dir.isDirectory()) {
                    if (dir.canWrite()) return dir;
                }
            }
        } catch (Throwable t) {
            L.e("gs: external storage resolve failed: " + t);
        }
        // Fallback: the app's OWN external files dirs (real package, via
        // the platform API — the old hardcoded com.sandboxol.blockmango
        // path belonged to a different package and never matched the
        // patched app id). Same filesystem family; keeps the server
        // runnable on locked-down storage. The user-visible placement rule
        // prefers the SandBoxOL path above and only lands here on
        // permission failures.
        try {
            // getExternalFilesDir (singular) keeps the compile-time android
            // stubs happy AND is available on every API the patched app runs.
            File o = context.getExternalFilesDir(null);
            if (o != null) {
                File dir = new File(new File(o, "SandBoxOL"), "config");
                if (dir.mkdirs() || dir.isDirectory()) return dir;
            }
        } catch (Throwable ignored) {}
        return new File(String.valueOf(sBundleDir), "logs");
    }

    /**
     * RoomGameConfig JSON — keys exactly as getRGConfigFromCmdline/getTestRGConfig
     * reads them (dev/server/src/main.cpp).
     */
    private static void writeServerConfig(File cfg) throws Exception {
        JSONObject o = new JSONObject();
        o.put("ip", "127.0.0.1");
        o.put("port", GAME_PORT);
        o.put("logdir", sLogDir.getAbsolutePath() + "/");
        o.put("scriptdir", new File(new File(serverDir(), "scripts"), "BedWar")
                .getAbsolutePath());
        o.put("mapdir", new File(new File(new File(serverDir(), "maps"), "g1008"),
                "m1008_2").getAbsolutePath() + "/");
        o.put("id", "g1008");
        o.put("mapid", "m1008_2");
        o.put("name", "BedWar");
        o.put("gtype", "g1008");
        o.put("monitoraddr", "127.0.0.1:" + MonitorServer.boundPort());
        // startPlayers=16 in the map's config.yml: WaitingPlayerTask never
        // fires while the room holds fewer than 16 players AND
        // isPlayerEnough(16) can never pass with maxplayer=8. 16 = 4 teams
        // x teamPlayers(4); the monitor's robot wave completes the seats
        // (v0.6.26-bots).
        o.put("maxplayer", 16);
        o.put("isDebug", false);
        o.put("secret", "pq0194mxoqfh48L362G6R09T737E273X");
        o.put("isChina", false);
        o.put("heartbeatInterval", 5);
        o.put("userConf", "");
        // The engine's Lua WebService hosts: blockymodsRewardAddr becomes
        // WebService.ServerHttpHost (user/details = the LOGIN gate - Lua
        // BasePlayer:initStaticAttr refuses the login with code=3
        // emErrGetUserAttrFail when it returns no data; run 38115464141)
        // and gameDataServiceAddr becomes WebService.DBHttpHost. Both point
        // at THIS holder's LocalHttpd, whose gameServerInner() answers
        // them (v0.6.25-innerhttp).
        o.put("propAddr", "http://127.0.0.1:18080");
        o.put("rankAddr", "http://127.0.0.1:18080");
        o.put("rewardAddr", "http://127.0.0.1:18080");
        o.put("blockymodsUrl", "");
        o.put("blockymodsRewardAddr", "http://127.0.0.1:18080");
        o.put("blockmanUrl", "");
        o.put("gameRankParams", "");
        // JSON "gameDataServiceAddr" -> RoomGameConfig.dbHttpServiceUrl ->
        // WebService.DBHttpHost (main.cpp:125).
        o.put("gameDataServiceAddr", "http://127.0.0.1:18080");
        o.put("gameDataServiceSecondAddr", "http://127.0.0.1:18080");
        o.put("isGameParty", false);
        o.put("private", false);
        o.put("maxWatch", 0);
        JSONObject db = new JSONObject();
        db.put("addr", ""); db.put("user", ""); db.put("password", "");
        db.put("dbname", "");
        o.put("dbconfig", db);
        JSONObject redis = new JSONObject();
        redis.put("ip", ""); redis.put("password", ""); redis.put("port", 0);
        o.put("redisConfig", redis);
        FileOutputStream out = new FileOutputStream(cfg);
        out.write(o.toString().getBytes("UTF-8"));
        out.close();
        L.i("gs: config written -> " + cfg);
    }

    private static File findBinary(Context context) {
        try {
            String nd = context.getApplicationInfo().nativeLibraryDir;
            if (nd != null) {
                File f = new File(nd, "libgameserver.so");
                if (f.exists() && f.canExecute()) return f;
                if (f.exists()) return f;
            }
        } catch (Throwable t) {
            L.e("gs: nativeLibraryDir probe failed: " + t);
        }
        File f = new File(sBundleDir, "libgameserver.so");
        return f.exists() ? f : null;
    }

    private static File download(String url, String name, long maxBytes) throws Exception {
        File dst = new File(String.valueOf(sBundleDir), name);
        File tmp = new File(String.valueOf(sBundleDir), name + ".tmp");
        sBundleDir.mkdirs();
        L.i("gs: downloading " + url);
        java.net.HttpURLConnection c = (java.net.HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(15000);
        c.setReadTimeout(60000);
        c.setInstanceFollowRedirects(true);
        InputStream in = new BufferedInputStream(c.getInputStream());
        OutputStream out = new FileOutputStream(tmp);
        long total = 0;
        byte[] buf = new byte[65536];
        int n;
        while ((n = in.read(buf)) > 0) {
            total += n;
            if (total > maxBytes) throw new Exception("download too large: " + url);
            out.write(buf, 0, n);
        }
        out.close();
        in.close();
        if (!tmp.renameTo(dst)) copy(tmp, dst);
        L.i("gs: downloaded " + dst.getName() + " (" + dst.length() + " bytes)");
        return dst;
    }

    /**
     * Minimal ustar reader (same approach as MapAssets.extractPack): extracts
     * regular files + dirs, skips pax/long-link metadata headers. The bundle
     * is a sha-pinned release asset so this is sufficient.
     */
    private static void untarGz(File tarGz, File dstDir) throws Exception {
        dstDir.mkdirs();
        GZIPInputStream in = new GZIPInputStream(new BufferedInputStream(
                new FileInputStream(tarGz)), 65536);
        byte[] hdr = new byte[512];
        while (readFully(in, hdr)) {
            boolean allZero = true;
            for (int i = 0; i < 512; i++) {
                if (hdr[i] != 0) { allZero = false; break; }
            }
            if (allZero) break; // end-of-archive
            String name = cstr(hdr, 0, 100);
            String prefix = cstr(hdr, 345, 155);
            if (prefix.length() > 0) name = prefix + "/" + name;
            long size = octal(hdr, 124, 12);
            int type = hdr[156] == 0 ? '0' : (hdr[156] & 255);
            if (type == 'x' || type == 'g' || type == 'L' || type == 'K') {
                skipFully(in, ((size + 511) / 512) * 512);
                continue;
            }
            if (type == '5') { // directory
                new File(dstDir, name).mkdirs();
                skipFully(in, size);
            } else if (type == '0' || type == 0) { // regular file
                File out = new File(dstDir, name);
                if (!out.getCanonicalPath().startsWith(dstDir.getCanonicalPath())) {
                    skipFully(in, ((size + 511) / 512) * 512);
                    continue; // tar path traversal guard
                }
                if (out.getParentFile() != null) out.getParentFile().mkdirs();
                FileOutputStream fos = new FileOutputStream(out);
                long left = size;
                byte[] buf = new byte[65536];
                while (left > 0) {
                    int n = in.read(buf, 0, (int) Math.min(buf.length, left));
                    if (n < 0) throw new java.io.EOFException("truncated tar");
                    fos.write(buf, 0, n);
                    left -= n;
                }
                fos.close();
                long pad = (512 - (size % 512)) % 512;
                skipFully(in, pad);
            } else {
                skipFully(in, ((size + 511) / 512) * 512);
            }
        }
        in.close();
    }

    private static boolean readFully(InputStream in, byte[] b) throws Exception {
        int off = 0;
        while (off < b.length) {
            int n = in.read(b, off, b.length - off);
            if (n < 0) return off > 0;
            off += n;
        }
        return true;
    }

    private static void skipFully(InputStream in, long n) throws Exception {
        while (n > 0) {
            long skipped = in.skip(n);
            if (skipped <= 0) {
                if (in.read() < 0) return;
                skipped = 1;
            }
            n -= skipped;
        }
    }

    private static String cstr(byte[] b, int off, int len) {
        int end = off;
        while (end < off + len && end < b.length && b[end] != 0) end++;
        return new String(b, off, end - off).trim();
    }

    private static long octal(byte[] b, int off, int len) {
        long v = 0;
        boolean started = false;
        for (int i = off; i < off + len && i < b.length; i++) {
            byte c = b[i];
            if (c == ' ' || c == 0) {
                if (started) break;
                continue;
            }
            started = true;
            if (c >= '0' && c <= '7') v = (v << 3) + (c - '0');
            else break;
        }
        return v;
    }

    private static void copy(File src, File dst) throws Exception {
        FileInputStream in = new FileInputStream(src);
        FileOutputStream out = new FileOutputStream(dst);
        byte[] buf = new byte[65536];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        out.close();
        in.close();
    }

    private static String readText(File f) {
        try {
            byte[] b = new byte[(int) Math.min(f.length(), 4096)];
            FileInputStream in = new FileInputStream(f);
            int n = in.read(b);
            in.close();
            return new String(b, 0, Math.max(0, n), "UTF-8").trim();
        } catch (Exception e) {
            return "";
        }
    }

    private static void writeText(File f, String s) {
        try {
            f.getParentFile().mkdirs();
            FileOutputStream out = new FileOutputStream(f);
            out.write(s.getBytes("UTF-8"));
            out.close();
        } catch (Exception ignored) {}
    }

    private static long pid() {
        try {
            java.lang.reflect.Field f = Process.class.getDeclaredField("pid");
            f.setAccessible(true);
            return f.getInt(sProcess);
        } catch (Throwable t) {
            return -1;
        }
    }
}
