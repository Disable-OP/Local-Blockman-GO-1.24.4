#!/usr/bin/env python3
"""fetch_release_asset.py — download an asset by name from the newest release
that contains it (prereleases included; `gh release download` skips them).

Usage: fetch_release_asset.py <asset-name> <output-file>
Requires GH_TOKEN env var.
"""
import json
import os
import sys
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "Disable-OP/Local-Blockman-GO-1.24.4")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
API = "https://api.github.com"


def api(url: str, accept: str = "application/vnd.github+json"):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": accept,
        "User-Agent": "localapi-ci",
    })
    return urllib.request.urlopen(req)


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: fetch_release_asset.py <asset-name> <output>")
    name, out = sys.argv[1], sys.argv[2]
    if not TOKEN:
        sys.exit("error: GH_TOKEN not set")
    # Paginate ALL releases: the repo grows one wip release per build and
    # the base APK lives on the OLDEST release (v0.1.0-pipeline) — with 51
    # releases a flat per_page=50 page-1 listing dropped it and the build
    # died with "asset not found" (run 37823358959). Walk every page.
    releases = []
    page = 1
    while True:
        batch = json.load(api(f"{API}/repos/{REPO}/releases?per_page=100&page={page}"))
        releases.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    # Pick the release whose APK ASSET was UPLOADED most recently.
    # Release created_at is unreliable here: several tags share
    # backdated timestamps (wip-57 and wip-58 both read
    # 2026-10-07T14:13:42Z while their assets were built ~7h apart),
    # so the old release-order sort could tie-break onto a STALE dex —
    # a full session was spent chasing a "non-effective server fix"
    # that the device never received (session 39, run 37766895731).
    # Asset updated_at is the real build-freshness signal.
    cands = [(a["updated_at"], rel, a) for rel in releases
             for a in rel.get("assets", []) if a["name"] == name]
    if not cands:
        sys.exit(f"error: asset {name!r} not found in any release of {REPO}")
    _, rel, a = max(cands, key=lambda x: x[0])
    print(f"downloading {name} from release {rel['tag_name']} "
          f"(asset built {a['updated_at']})")
    with api(a["url"], accept="application/octet-stream") as r, open(out, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    print(f"saved {out} ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
