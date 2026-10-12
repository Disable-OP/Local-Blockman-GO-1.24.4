#!/usr/bin/env python3
"""gen_drive_ca.py — the pristine-client drive PKI (delta-13 architecture).

Generates, with the openssl CLI only (no Python deps):
  <out>/ca.pem           the drive CA (install into the device SYSTEM store)
  <out>/ca.key           the CA key (KEEP OFF THE DEVICE)
  <out>/server.key       leaf key (packaged into the PKCS#12 only)
  <out>/server.pem       leaf cert, SANs = every redirected host
  <out>/chain.pem        leaf + CA (what the holder actually serves)
  <out>/server.p12       the holder keystore  -> stage as <filesDir>/drive/server.p12
  <out>/<subject_hash_old>.0  Android cacerts-ready CA file (push to
                         /system/etc/security/cacerts/, mode 644)
  <out>/tls.port         convenience file for the holder's drive/ dir

The leaf validity is 825 days (the Android 9+ limit applies to user-store
anchors; we install into the SYSTEM store, but 825 stays well inside every
policy and outlives the drive comfortably). The SAN list is the full host
inventory the pristine 2.8.2 client can reach after the /etc/hosts redirect
(docs/ON_DEVICE_DRIVE.md): the metadata base (d32gv25kv9q34j.cloudfront.net),
its failover (d401m01aifavw.cloudfront.net) and the sandboxol API/CDN hosts.

Usage:
  python3 scripts/gen_drive_ca.py [--out DIR] [--pass PW] [--tls-port N] [--force]

Defaults: --out <repo>/drive, --pass drive, --tls-port 443.
Idempotent: exits 0 without touching anything when the material exists
(pass --force to regenerate).
"""
import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The redirected-host inventory (docs/ON_DEVICE_DRIVE.md §2). The first two
# are the cloudfront pair from patch_urls_282.py / docs §13; the sandboxol
# trio covers the API/CDN layer; loopback names keep adb curl checks honest.
SAN_HOSTS = [
    "d32gv25kv9q34j.cloudfront.net",
    "d401m01aifavw.cloudfront.net",
    "mods.sandboxol.com",
    "staticgs.sandboxol.com",
    "static.sandboxol.com",
    "game.sandboxol.com",
    "localhost",
]
SAN_IPS = ["127.0.0.1"]

CA_DAYS = 3650
LEAF_DAYS = 825  # Android's leaf-validity ceiling — respected even though
                 # this CA ships into the SYSTEM store.


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("FAILED: %s\n%s%s" % (" ".join(cmd), r.stdout, r.stderr))
        sys.exit(1)
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(REPO, "drive"))
    ap.add_argument("--pass", dest="pw", default="drive")
    ap.add_argument("--tls-port", type=int, default=443)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    p12 = os.path.join(out, "server.p12")
    if os.path.isfile(p12) and not args.force:
        print("exists: %s (use --force to regenerate)" % p12)
        return

    os.makedirs(out, exist_ok=True)
    ca_key = os.path.join(out, "ca.key")
    ca_pem = os.path.join(out, "ca.pem")
    key = os.path.join(out, "server.key")
    csr = os.path.join(out, "server.csr")
    pem = os.path.join(out, "server.pem")
    chain = os.path.join(out, "chain.pem")
    ext = os.path.join(out, "server-san.cnf")

    print("== drive CA (10y) ==")
    sh(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", ca_key, "-out", ca_pem, "-days", str(CA_DAYS),
        "-subj", "/O=BlockyNexus/CN=BlockyNexus Drive CA",
        "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign"])

    print("== leaf (SANs: %d hosts + loopback) ==" % len(SAN_HOSTS))
    san = ",".join(["DNS:" + h for h in SAN_HOSTS] + ["IP:" + i for i in SAN_IPS])
    with open(ext, "w") as f:
        f.write("[req]\ndistinguished_name=dn\n[dn]\nCN=drive.localapi\n"
                "[ext]\nsubjectAltName=%s\n"
                "keyUsage=critical,digitalSignature,keyEncipherment\n"
                "extendedKeyUsage=serverAuth\n"
                "basicConstraints=CA:FALSE\n" % san)
    sh(["openssl", "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", key, "-out", csr, "-days", str(LEAF_DAYS),
        "-subj", "/O=BlockyNexus/CN=drive.localapi",
        "-config", ext])
    sh(["openssl", "x509", "-req", "-in", csr, "-CA", ca_pem, "-CAkey", ca_key,
        "-CAcreateserial", "-out", pem, "-days", str(LEAF_DAYS),
        "-extfile", ext, "-extensions", "ext"])

    with open(chain, "w") as f:
        f.write(open(pem).read() + open(ca_pem).read())

    print("== holder PKCS#12 ==")
    sh(["openssl", "pkcs12", "-export", "-inkey", key, "-in", chain,
        "-out", p12, "-passout", "pass:" + args.pw, "-name", "localapi-drive"])

    print("== android cacerts file (subject_hash_old) ==")
    h = sh(["openssl", "x509", "-subject_hash_old", "-noout", "-in", ca_pem])
    h = h.strip().splitlines()[-1].strip()
    hash0 = os.path.join(out, "%s.0" % h)
    with open(hash0, "w") as f:
        f.write(open(ca_pem).read())

    with open(os.path.join(out, "tls.port"), "w") as f:
        f.write(str(args.tls_port))

    print("\nOK — drive material in %s" % out)
    print("  holder stage : server.p12 (+ tls.port=%d) -> <filesDir>/drive/"
          % args.tls_port)
    print("  device store : %s -> /system/etc/security/cacerts/ (mode 644)"
          % os.path.basename(hash0))
    print("  next         : docs/ON_DEVICE_DRIVE.md")


if __name__ == "__main__":
    main()
