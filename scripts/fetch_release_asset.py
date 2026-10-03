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
    releases = json.load(api(f"{API}/repos/{REPO}/releases?per_page=50"))
    for rel in sorted(releases, key=lambda r: r["created_at"], reverse=True):
        for a in rel.get("assets", []):
            if a["name"] == name:
                print(f"downloading {name} from release {rel['tag_name']}")
                with api(a["url"], accept="application/octet-stream") as r, open(out, "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                print(f"saved {out} ({os.path.getsize(out)} bytes)")
                return
    sys.exit(f"error: asset {name!r} not found in any release of {REPO}")


if __name__ == "__main__":
    main()
