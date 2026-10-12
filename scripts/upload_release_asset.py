#!/usr/bin/env python3
"""upload_release_asset.py — replace/attach an asset on a GitHub release.
Reads the PAT from the git remote (never logged). Usage:
  upload_release_asset.py <release-tag> <asset-name> <file> [content-type]
"""
import json, os, re, subprocess, sys, urllib.request

REPO = "Disable-OP/Local-Blockman-GO-1.24.4"

def token():
    url = subprocess.run(["git", "-C", "/home/z/Local-Blockman-GO-1.24.4", "remote", "get-url", "origin"],
                         capture_output=True, text=True).stdout.strip()
    m = re.search(r"://([^:]+):([^@]+)@", url)
    if not m:
        sys.exit("no token in remote")
    return m.group(2)

def api(url, accept="application/vnd.github+json", data=None, headers=None, method=None):
    h = {"Authorization": f"Bearer {token()}", "User-Agent": "localapi-ci",
         "Accept": accept}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, data=data, method=method)
    return urllib.request.urlopen(req)

tag = sys.argv[1]
name = sys.argv[2]
path = sys.argv[3]
ctype = sys.argv[4] if len(sys.argv) > 4 else "application/octet-stream"

rel = json.load(api(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}"))
rel_id = rel["id"]
print(f"release {tag} id={rel_id}")

# delete an existing asset with the same name (clobber)
for a in rel.get("assets", []):
    if a["name"] == name:
        api(f"https://api.github.com/repos/{REPO}/releases/assets/{a['id']}", method="DELETE")
        print(f"deleted existing {name} (id={a['id']})")

size = os.path.getsize(path)
up = api(f"https://uploads.github.com/repos/{REPO}/releases/{rel_id}/assets?name={name}",
         accept="application/vnd.github+json",
         data=open(path, "rb").read(),
         headers={"Content-Type": ctype})
out = json.load(up)
print(f"uploaded {out['name']} size={out['size']} state={out['state']}")
assert out["size"] == size, "size mismatch!"
print("OK")
