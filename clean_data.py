#!/usr/bin/env python3
"""
clean_data.py
Reads 宏福苑入標.csv → graph_data.json (graphology / Sigma.js format)
"""

import csv, json, re

# ── Constants ──────────────────────────────────────────────────────────────────
ESTATE_LABEL = '宏福苑'
WINNERS      = {'宏業建築工程有限公司', '鴻毅建築師有限公司'}
TYPE_MAP     = {'顧問': 'consultant', '承建商': 'contractor'}
INPUT_PATH   = '/Users/angelkyt/claude_bid/宏福苑入標.csv'
OUTPUT_PATH  = '/Users/angelkyt/claude_bid/graph_data.json'

# 曹德光 is explicitly flagged as two different people with the same name
DISAMBIG_RULES = {
    ('曹德光', '亞太建築顧問有限公司'): '曹德光①',
    ('曹德光', '宏業建築工程有限公司'): '曹德光②',
}

# Strings inside 「」 that are NOT company names
SKIP_CO_NAMES = {'董事王'}

COLOR = dict(
    estate='#2ecc71', consultant='#e67e22',
    contractor='#9b59b6', external='#888888', person='#ffffff'
)
EDGE_COLOR = dict(
    bid_winner='#e74c3c', bid_loser='#1abc9c',
    person_co='#555555',  co_co='#888888'
)
NODE_SIZE = dict(estate=20, consultant=12, contractor=12, external=8, person=6)

# ── Stores ─────────────────────────────────────────────────────────────────────
nodes, edges, _edge_set = {}, [], set()

def add_node(key, label, ntype, criminal='', political=''):
    if key not in nodes:
        nodes[key] = dict(
            label=label, nodeType=ntype,
            color=COLOR[ntype], size=NODE_SIZE[ntype],
            criminalRecord=criminal, politicalRecord=political,
            x=0.0, y=0.0
        )
    else:
        n = nodes[key]
        for field, val in (('criminalRecord', criminal), ('politicalRecord', political)):
            if val and val not in n[field]:
                n[field] = (n[field] + '\n' + val).strip()

def add_edge(src, tgt, etype):
    pair = (min(src, tgt), max(src, tgt), etype)
    if pair in _edge_set:
        return
    _edge_set.add(pair)
    edges.append(dict(
        source=src, target=tgt,
        attributes=dict(edgeType=etype, color=EDGE_COLOR.get(etype, '#888888'), size=1)
    ))

# ── Helpers ────────────────────────────────────────────────────────────────────
def nkey(prefix, label):
    return prefix + '_' + re.sub(r'[\s（）【】()]', '', label)

def split_names(s):
    return [n.strip() for n in re.split(r'[，,、]', s) if n.strip()]

def co_in(text):
    return re.findall(r'「([^」]+)」', text)

def sentences_for(text, name):
    frags = [p.strip() for p in re.split(r'[。\n；]', text) if name in p]
    return '。'.join(frags)

# External company cache
_ext = {}

def get_co_key(short, bmap):
    if short in SKIP_CO_NAMES:
        return None
    if short in bmap:
        return bmap[short]
    # Prefer matches where full name STARTS WITH the short name (most specific)
    candidates = [(full, key) for full, key in bmap.items()
                  if short in full and len(short) >= 2]
    if candidates:
        starts = [(f, k) for f, k in candidates if f.startswith(short)]
        best = starts if starts else candidates
        best.sort(key=lambda x: len(x[0]))   # shortest full name wins
        return best[0][1]
    if short not in _ext:
        key = nkey('ext', short)
        _ext[short] = key
        add_node(key, short, 'external')
    return _ext[short]

def strip_owner_context(text):
    """Remove 「A」...旗下 so only the directly-linked company remains."""
    return re.sub(r'「[^」]+」[^，。\n]{0,20}旗下', '', text)

def p_key_for(name, co):
    label = DISAMBIG_RULES.get((name, co), name)
    return nkey('p', label)

# ── 1. Read CSV ─────────────────────────────────────────────────────────────────
rows = []
with open(INPUT_PATH, encoding='utf-8') as f:
    for row in csv.reader(f):
        while len(row) < 6:
            row.append('')
        rows.append(row)
rows = rows[1:]  # drop header

# ── 2. Estate node ──────────────────────────────────────────────────────────────
EK = nkey('estate', ESTATE_LABEL)
add_node(EK, ESTATE_LABEL, 'estate')

# ── 3. Bidder company nodes ─────────────────────────────────────────────────────
bmap = {}  # full name → key
for r in rows:
    co, typ = r[0].strip(), r[1].strip()
    ntype = TYPE_MAP.get(typ, 'external')
    key = nkey('co', co)
    add_node(key, co, ntype, r[4].strip(), r[5].strip())
    bmap[co] = key

# ── 4. Estate ↔ bidder edges ─────────────────────────────────────────────────────
for r in rows:
    co = r[0].strip()
    etype = 'bid_winner' if co in WINNERS else 'bid_loser'
    add_edge(EK, bmap[co], etype)

# ── 5. Person nodes from col 3 + person→bidder edges ────────────────────────────
for r in rows:
    co = r[0].strip()
    for name in split_names(r[2]):
        label = DISAMBIG_RULES.get((name, co), name)
        p_key = nkey('p', label)
        crim  = sentences_for(r[4], name)
        pol   = sentences_for(r[5], name)
        add_node(p_key, label, 'person', crim, pol)
        add_edge(p_key, bmap[co], 'person_co')

# ── 6. Cross-company links from col 4 ───────────────────────────────────────────
for r in rows:
    co, links = r[0].strip(), r[3].strip()
    if not links:
        continue
    people_here = split_names(r[2])
    items = [i.strip().rstrip('。') for i in re.split(r'\d+[）)]\s*', links) if i.strip()]

    for item in items:
        if '同名同姓' in item:
            continue

        # Company-to-company link: item starts with 「
        if item.lstrip().startswith('「'):
            cos = co_in(item)
            if len(cos) >= 2:
                k1 = get_co_key(cos[0], bmap)
                k2 = get_co_key(cos[1], bmap)
                if k1 and k2:
                    add_edge(k1, k2, 'co_co')
            continue

        # Person → company links
        mentioned = [name for name in people_here if name in item]
        if not mentioned:
            continue
        targets = co_in(strip_owner_context(item))
        for name in mentioned:
            pk = p_key_for(name, co)
            for t in targets:
                tk = get_co_key(t, bmap)
                if tk:
                    add_edge(pk, tk, 'person_co')

# ── 7. People in records (col 5/6) but NOT in col 3 ─────────────────────────────
PATTERNS = [
    # 「Company」前董事/創辦人/董事 PersonName followed by year/comma/曾/捲
    (re.compile(r'「([^」]+)」(?:前董事|創辦人|董事)([^\s，。（「]{2,4}?)(?=\s*(?:\d|曾|捲|，))'), 'co_first'),
    # 現任/前 董事 PersonName 捲入/曾
    (re.compile(r'(?:現任|前)?董事([^\s，。（「]{2,4}?)(?:捲入|曾)'), 'co_self'),
]

for r in rows:
    co_key = bmap[r[0].strip()]
    known  = set(split_names(r[2]))
    all_text = r[4] + '\n' + r[5]
    if not all_text.strip():
        continue

    found = {}  # pname → (p_key, linked_co_key)
    for pat, ptype in PATTERNS:
        for m in pat.finditer(all_text):
            if ptype == 'co_first':
                co_short = m.group(1)
                pname    = m.group(2).strip()
                linked   = get_co_key(co_short, bmap) or co_key
            else:
                pname  = m.group(1).strip()
                linked = co_key

            if pname in known:
                continue
            if len(pname) < 2 or len(pname) > 4:
                continue
            if any(x in pname for x in ['有限', '工程', '建築', '公司', '事務']):
                continue

            pk = nkey('p', pname)
            if pname not in found:
                found[pname] = (pk, linked)

    for pname, (pk, lk) in found.items():
        crim = sentences_for(r[4], pname)
        pol  = sentences_for(r[5], pname)
        add_node(pk, pname, 'person', crim, pol)
        add_edge(pk, lk, 'person_co')

# ── 8. Write output ──────────────────────────────────────────────────────────────
graph = {
    'attributes': {'name': '宏福苑維修工程關係圖'},
    'nodes': [{'key': k, 'attributes': v} for k, v in nodes.items()],
    'edges': [{'key': f'e_{i}', **e}       for i, e in enumerate(edges)],
}

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(graph, f, ensure_ascii=False, indent=2)

# ── Report ───────────────────────────────────────────────────────────────────────
by_type = {}
for v in nodes.values():
    by_type[v['nodeType']] = by_type.get(v['nodeType'], 0) + 1

by_edge = {}
for e in edges:
    t = e['attributes']['edgeType']
    by_edge[t] = by_edge.get(t, 0) + 1

print(f"✓  Saved → {OUTPUT_PATH}")
print(f"\n   Nodes: {len(nodes)}")
for k in ('estate', 'consultant', 'contractor', 'external', 'person'):
    print(f"      {k:<12} {by_type.get(k, 0)}")
print(f"\n   Edges: {len(edges)}")
for k in ('bid_winner', 'bid_loser', 'person_co', 'co_co'):
    print(f"      {k:<20} {by_edge.get(k, 0)}")

# ── Spot-check: list all person nodes ────────────────────────────────────────────
print("\n   People nodes:")
for k, v in sorted(nodes.items()):
    if v['nodeType'] == 'person':
        flags = []
        if v['criminalRecord']:   flags.append('C')
        if v['politicalRecord']:  flags.append('P')
        flag_str = f"[{','.join(flags)}]" if flags else ''
        print(f"      {v['label']:<12} {flag_str}")
