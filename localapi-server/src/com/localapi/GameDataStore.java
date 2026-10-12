package com.localapi;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * The GameServer engine's Lua DBManager persistence (engine 10078 line):
 * WebService GetUserGameData / SaveUserGameData hit the holder's
 * /api/v2/game/data and this store backs them.
 *
 * WHY A REAL STORE (not the code=0/null degradation): the 10078 decompiled
 * DBManager KICKS THE PLAYER on player-data failure —
 *   load:  getGameData retries 3x on nil data, then kickOutPlayer +
 *          GetDBDataErrorEvent (DBManager.lua ~154);
 *   save:  saveGameData retries 3x on code!=1, then PushFailedRecord >= 3 ->
 *          kickOutPlayer + SaveDBDataErrorEvent (DBManager.lua ~210).
 * The green 10068 line dodges this because its runtime bundle carries the
 * private-server isLocalDb patch (WebService.lua line 4: game data
 * round-trips to game_cache/*.db files, HTTP never fires). The decompiled
 * 10078 WebService.lua has NO such patch — the HTTP path is load-bearing.
 *
 * SHAPE CONTRACT (from the decompiled callers):
 *   GET  /api/v2/game/data?userId&subKey&tableName
 *        -> hit:   {"code":1,"data":<blob>}              (formatData: data)
 *        -> miss:  {"code":11,...}  (WebService.GetUserGameData maps
 *           code 11 -> {__first=true} = the official "no record yet";
 *           data null + code 0 would retry-then-kick instead)
 *   POST /api/v2/game/data?tableName   body: [{"userId","subKey",...fields}]
 *        -> {"code":1,...}  (saveGameData treats code!=1 as failure ->
 *           retry -> kick; code 3 would trigger the re-read storm path)
 *
 * The blob is stored AS SENT (the {userId, subKey, ...} entry verbatim) —
 * the Lua addCache strips userId/subKey/__first keys on load, mirroring the
 * official service and the 10068 isLocalDb file round-trip.
 *
 * Layout: <stateDir>/localapi/gamedata/<tableName>.json — one JSON object
 * keyed "<userId>#<subKey>" -> blob. Atomic tmp+rename writes (the same
 * torn-write discipline as StateStore). Instances are cached per directory
 * so every request path shares one in-memory map.
 */
public final class GameDataStore {

    private static final Map<String, GameDataStore> BY_ROOT = new HashMap<>();

    private final File dir;
    private final Map<String, JSONObject> tables = new HashMap<>();

    private GameDataStore(File dir) {
        this.dir = dir;
        //noinspection ResultOfMethodCallIgnored
        dir.mkdirs();
    }

    /** Per-state-root singleton (Handlers has no constructor hook for this). */
    public static GameDataStore at(File stateBaseDir) {
        File root = new File(stateBaseDir, "gamedata");
        String key = root.getAbsolutePath();
        synchronized (BY_ROOT) {
            GameDataStore s = BY_ROOT.get(key);
            if (s == null) {
                s = new GameDataStore(root);
                BY_ROOT.put(key, s);
            }
            return s;
        }
    }

    /** The stored blob for userId#subKey, or null when the record is absent. */
    public JSONObject get(String table, String userId, String subKey) {
        return getBlob(sanitize(table), String.valueOf(userId),
                String.valueOf(subKey));
    }

    /** Upserts the blob and persists the table atomically. */
    public void put(String table, String userId, String subKey, JSONObject blob) {
        putBlob(sanitize(table), String.valueOf(userId),
                String.valueOf(subKey), blob);
    }

    private synchronized JSONObject getBlob(String safeTable, String uid,
                                            String subKey) {
        JSONObject entry = table(safeTable).optJSONObject(uid + "#" + subKey);
        return entry == null ? null : new JSONObject(entry.toString());
    }

    private synchronized void putBlob(String safeTable, String uid,
                                      String subKey, JSONObject blob) {
        JSONObject t = table(safeTable);
        t.put(uid + "#" + subKey, blob);
        persist(safeTable, t);
    }

    /** Loads (once) and returns the table map. Callers hold the monitor. */
    private JSONObject table(String safeTable) {
        JSONObject t = tables.get(safeTable);
        if (t != null) return t;
        t = new JSONObject();
        File f = fileFor(safeTable);
        if (f.exists() && f.length() > 0) {
            try {
                byte[] buf = new byte[(int) f.length()];
                FileInputStream in = new FileInputStream(f);
                int total = 0;
                while (total < buf.length) {
                    int n = in.read(buf, total, buf.length - total);
                    if (n < 0) break;
                    total += n;
                }
                in.close();
                if (total > 0) {
                    t = new JSONObject(new String(buf, 0, total,
                            StandardCharsets.UTF_8));
                }
            } catch (Throwable t2) {
                L.e("gamedata load " + safeTable + " failed, starting fresh: "
                        + t2);
                t = new JSONObject();
            }
        }
        tables.put(safeTable, t);
        return t;
    }

    private void persist(String safeTable, JSONObject t) {
        try {
            File f = fileFor(safeTable);
            File tmp = new File(f.getParentFile(), f.getName() + ".tmp");
            byte[] bytes = t.toString().getBytes(StandardCharsets.UTF_8);
            FileOutputStream out = new FileOutputStream(tmp);
            out.write(bytes);
            out.close();
            if (!tmp.renameTo(f)) {
                // rename can fail across odd filesystems; fall back to a
                // direct write (the tmp file is deleted either way)
                FileOutputStream out2 = new FileOutputStream(f);
                out2.write(bytes);
                out2.close();
                //noinspection ResultOfMethodCallIgnored
                tmp.delete();
            }
        } catch (Throwable t2) {
            L.e("gamedata persist " + safeTable + " failed: " + t2);
        }
    }

    private File fileFor(String safeTable) {
        return new File(dir, safeTable + ".json");
    }

    /** Table names come from the engine (DBManager:getGameType(), "g1008").
     *  Keep [A-Za-z0-9._-]; anything else (or empty) folds to "default" /
     *  underscores so the file name can never escape the gamedata dir. */
    private static String sanitize(String name) {
        if (name == null || name.length() == 0) return "default";
        String s = name.replaceAll("[^A-Za-z0-9._-]", "_");
        return s.length() == 0 ? "default" : s;
    }
}
