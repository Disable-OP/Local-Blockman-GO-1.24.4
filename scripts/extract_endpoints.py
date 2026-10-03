#!/usr/bin/env python3
"""extract_endpoints.py — parse Retrofit smali interfaces into endpoint inventory.

Reads apktool_out smali, finds all interface files with retrofit2/http
annotations, extracts (verb, path, method, extras) tuples, writes
JSON + a markdown draft for docs/ENDPOINTS.md.
"""
import json
import re
import sys
from pathlib import Path

APKTOOL = Path('/home/z/my-project/work/apktool_out')
OUT_JSON = Path('/home/z/my-project/work/endpoints.json')
OUT_MD = Path('/home/z/my-project/work/endpoints_draft.md')

VERBS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']
ANN_RE = re.compile(r'Lretrofit2/http/(' + '|'.join(VERBS) + r');')
VALUE_RE = re.compile(r'value\s*=\s*"([^"]*)"')
PATH_RE = re.compile(r'path\s*=\s*"([^"]*)"')
METHOD_RE = re.compile(r'^\.method\s+(?:public\s+)?(?:abstract\s+)?(\S+)\(([^)]*)\)')


def parse_interface(path: Path):
    text = path.read_text(errors='replace')
    results = []
    pending = None  # (verb, path) waiting for method name
    current_method = None
    in_annotation = False
    ann_verb = None
    ann_path = None
    for line in text.splitlines():
        s = line.strip()
        m = METHOD_RE.match(s)
        if m:
            # flush pending annotation
            if pending and current_method:
                results.append({'verb': pending[0], 'path': pending[1],
                                'method': current_method, 'params': pending_params})
            current_method = m.group(1)
            pending = None
            pending_params = s
            continue
        if s.startswith('.annotation') and 'Lretrofit2/http/' in s:
            am = ANN_RE.search(s)
            if am:
                in_annotation = True
                ann_verb = am.group(1)
                ann_path = ''
            continue
        if in_annotation:
            if s.startswith('.end annotation'):
                if ann_verb:
                    pending = (ann_verb, ann_path)
                in_annotation = False
                ann_verb = None
                continue
            vm = VALUE_RE.search(s)
            if vm and not ann_path:
                ann_path = vm.group(1)
            pm = PATH_RE.search(s)
            if pm:
                ann_path = pm.group(1)
    if pending and current_method:
        results.append({'verb': pending[0], 'path': pending[1],
                        'method': current_method, 'params': pending_params})
    return results


def main():
    files = sorted(APKTOOL.glob('smali*/com/sandboxol/**/I*Api.smali'))
    # also catch non-I*Api retrofit interfaces
    all_api = {f for f in files}
    inventory = {}
    for f in sorted(all_api):
        eps = parse_interface(f)
        if eps:
            rel = str(f.relative_to(APKTOOL))
            key = '/'.join(p for p in rel.split('/') if not p.startswith('smali')).replace('.smali', '')
            inventory[key] = eps
    OUT_JSON.write_text(json.dumps(inventory, indent=1))
    with OUT_MD.open('w') as md:
        md.write('# Endpoint inventory (extracted from smali)\n\n')
        total = 0
        for key, eps in inventory.items():
            md.write(f'## {key} — {len(eps)} endpoints\n\n')
            md.write('| Verb | Path | Smali method |\n|---|---|---|\n')
            for e in eps:
                total += 1
                md.write(f'| {e["verb"]} | `{e["path"]}` | `{e["method"]}` |\n')
            md.write('\n')
    print(f'interfaces: {len(inventory)}  endpoints: {total}')
    print(f'wrote {OUT_JSON} and {OUT_MD}')


if __name__ == '__main__':
    main()
