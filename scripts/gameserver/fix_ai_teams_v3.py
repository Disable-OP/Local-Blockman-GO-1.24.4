#!/usr/bin/env python3
"""fix_ai_teams_v3.py — extend the BedWar-family maps' AiPlayerConfig.csv to
EIGHT AI teams (the static-prep half of delta 19's per-game bot waves).

THE FACTS (verified against bundle v3 + the June-2021 source trees):

- The 2021 gate is `PlayerManager:isPlayerEnough(GameConfig.startPlayers)`
  (WaitingPlayerTask), and startPlayers/teamPlayers come from the MAP's own
  config.yml:  g1061 solo = 8 x 1 (8 seats), g1062 duo = 16 x 2 (16 seats),
  g1008 proven = 16 x 4. The monitor's robot wave completes the seats.
- The wave pushes R2G_USER_ATTR robots (isRobot=true, robotId=1 = AI group 1,
  team = the cycle index). PlayerAIListener.onDynamicAttrInit turns each one
  into `AITeamManager:newAi(robotId, teamId, ...)`; addAItoTeam then picks the
  first UNUSED config row of `AIPlayerConfig:getConfigs(groupId, teamId)` —
  and SILENTLY SKIPS the robot when the team has no rows.
- The shipped maps' AiPlayerConfig.csv covers teams 1..4 ONLY (16 rows:
  4 slots x 4 teams; solo/duo csvs are byte-identical). The maps themselves
  are EIGHT-team (8 island colours: blue cyan gray green pink red white
  yellow) — so a naive 1..4 team cycle parks 7 solo bots on 4 islands and
  leaves every AI on teams 5..8 brainless.

THE FIX: append teams 5..8 (16 rows, ids 117..132) cloning team 1's row
pattern (weight 200/300/400/500 = 拆床/攻击/采集/防守 spread; the item/dress
group ids already exist in the same csvs' AiItemConfig/AiDressConfig tables
and are team-agnostic). Tab-separated, 8 fields per row, exactly like the
source rows. Idempotent: a csv that already carries a teamId=5 row is left
untouched.

Usage:  fix_ai_teams_v3.py <bundle-server-dir>   (e.g. .../bundle/server)
The assembler (assemble_multigame_v3.py) runs it automatically after wiring
the family maps, so a full rebuild carries the fix too.
"""
import os
import sys

# gid/map -> the csv to extend (the two rooms that carry a player-count gate
# AND an 8-team map; the hall is a lobby with no AI csv, the 2020 g1008 room
# is 4x4 and already covered).
TARGETS = [
    "maps/g1061/m1061_1",
    "maps/g1062/m1062_1",
]

# teams 5..8, ids 117..132, cloning team 1's four-slot pattern.
TEMPLATE = [
    (200, "201020", "102", "拆床"),
    (300, "102030", "101", "攻击"),
    (400, "301010", "103", "采集"),
    (500, "401010", "104", "防守"),
]
NEW_TEAMS = [5, 6, 7, 8]
FIRST_ID = 117


def rows_for_team(team_id, start_id):
    out = []
    for i, (weight, item_group, dress_group, note) in enumerate(TEMPLATE):
        rid = start_id + i
        out.append("\t".join([str(rid), "1", str(team_id), str(weight),
                              item_group, dress_group, "", note]))
    return out


def fix_map(map_dir):
    csv_path = os.path.join(map_dir, "AiPlayerConfig.csv")
    if not os.path.isfile(csv_path):
        return "skip (no AiPlayerConfig.csv): %s" % map_dir
    with open(csv_path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    # idempotence: any existing teamId=5 row means we already ran
    for ln in lines:
        cols = ln.split("\t")
        if len(cols) >= 3 and cols[2].strip() == "5":
            return "skip (teams 5-8 already present): %s" % map_dir
    next_id = FIRST_ID
    added = []
    for team_id in NEW_TEAMS:
        rows = rows_for_team(team_id, next_id)
        added.extend(rows)
        next_id += len(TEMPLATE)
    for r in added:
        assert len(r.split("\t")) == 8, "row field count drifted: %r" % r
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines + added) + "\n")
    return "extended %s: +%d rows (teams %s, ids %d..%d), %d -> %d rows" % (
        map_dir, len(added), "-".join(str(t) for t in NEW_TEAMS),
        FIRST_ID, FIRST_ID + len(added) - 1, len(lines),
        len(lines) + len(added))


def fix_bundle(server_dir):
    results = []
    for rel in TARGETS:
        results.append(fix_map(os.path.join(server_dir, rel)))
    return results


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    server_dir = os.path.abspath(sys.argv[1])
    if not os.path.isdir(server_dir):
        print("FATAL: not a directory: %s" % server_dir)
        sys.exit(1)
    for r in fix_bundle(server_dir):
        print("== " + r)
    sys.exit(0)


if __name__ == "__main__":
    main()
