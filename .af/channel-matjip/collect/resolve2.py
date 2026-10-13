# 후보 + 카카오 결과 → 확정된 가게 줄 (지역 기준점 개선판). 아직 안 물어본 질의는 q_next.json
import json, re, math, sys, collections, difflib
from parse_lib import addr_core, norm_name
from build_round_a import anchor_terms
import kcache
C = kcache.load()
CH = ['soulmatzip', 'mukbang3man', 'higaengs', 'seoul_namzaa']
HOME = {'soulmatzip': ['서울'], 'mukbang3man': ['서울'], 'seoul_namzaa': ['서울']}          # 채널 기본 지역(제목에 지역이 없을 때)
need = []; needk = set()
def ask(q):
    k = kcache.key(q)
    if k in C: return C[k]
    if k not in needk: needk.add(k); need.append(q)
    return None
def dist(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))

def strip_branch(s):
    t = s.split()
    while len(t) > 1 and re.fullmatch(r'[가-힣A-Za-z0-9]{0,8}(본점|직영점|점|본관|별관|\d호점|분점|지점)', t[-1]): t = t[:-1]
    return ' '.join(t)
def nk(s): return norm_name(s)
def sim(a, b):
    a0, b0 = nk(a), nk(b)
    if not a0 or not b0: return 0
    if a0 == b0: return 1.0
    a1, b1 = nk(strip_branch(a)), nk(strip_branch(b))
    if a1 == b1: return 0.97
    if len(a1) >= 2 and len(b1) >= 2 and (a1 in b1 or b1 in a1):
        sh, lo = sorted((a1, b1), key=len)
        rem = lo.replace(sh, '', 1)
        if re.fullmatch(r'(식당|집|본가|원조|옛날|전문점|본점|직영점|.{0,3}점|하우스|국밥|국수|분식|반점|가든|회관|레스토랑|카페|베이커리|제과|\d+)', rem): return 0.93
        return 0.88 if len(sh) / len(lo) >= 0.6 else (0.8 if len(sh) >= 3 else 0.6)
    return difflib.SequenceMatcher(None, a1, b1).ratio() * 0.95
FOOD = re.compile(r'음식점|카페|간식|제과|베이커리|떡|술집|주점|호프|요리|분식|뷔페|패스트푸드|치킨|도시락|아이스크림|디저트|정육|수산|반찬|식품|시장')
def foody(c): return c.get('g') in ('FD6', 'CE7') or bool(FOOD.search(c.get('c', '')))

METRO = {'서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '세종특별자치시', '서울특별시'}
def lvl_of(name):
    t = name.split()
    if len(t) == 1: return 1, (t[0][:2] in {m[:2] for m in METRO} and not t[0].endswith('도'))
    last = t[-1]
    return (3 if re.search(r'(동|읍|면|리|가|\d동)$', last) else 2), False
def kind_of(p):
    # metro(서울·부산…) / prov(강원도…) / sigun(○○시·○○군) / gu(○○구) / dong / station / spot
    if p.get('st'): return 'station'
    if p.get('spot'): return 'spot'
    t = p['name'].split()
    if len(t) == 1: return 'metro' if p['metro'] else 'prov'
    if re.search(r'(동|읍|면|리|가|\d동)$', t[-1]): return 'dong'
    return 'gu' if t[-1].endswith('구') else 'sigun'
def term_points(t):
    ra = ask({'t': 'a', 'q': t}); rk = ask({'t': 'k', 'q': t})
    if ra is None or rk is None: return None
    out = []
    base = re.sub(r'(특별시|광역시|특별자치시|특별자치도|도|시|군|구)$', '', t)
    if len(base) < 2: base = t
    for x in (ra.get('r') or []):
        if x['t'] == 'REGION' and (t in x['n'] or base in x['n']):
            lv, metro = lvl_of(x['n']); out.append({'term': t, 'lat': x['y'], 'lng': x['x'], 'lvl': lv, 'metro': metro, 'name': x['n']})
    region = bool(out)
    for x in (rk.get('r') or [])[:6]:
        if x.get('g') == 'SW8' and x['n'].startswith(t.rstrip('역')) and (t.endswith('역') or not region):
            out.append({'term': t, 'lat': x['y'], 'lng': x['x'], 'lvl': 4, 'metro': False, 'name': x['n'], 'addr': x['a'], 'st': 1}); break
    if not region and not any(p['lvl'] == 4 for p in out):
        for x in (rk.get('r') or [])[:3]:
            if (x.get('g') in ('AT4', 'MT1', '') and x['n'].replace(' ', '').startswith(t.replace(' ', '')) and not foody(x)):
                if re.search(r'(시장|거리|골목|공원|대학교|대학|역|해수욕장|타운|단지|터미널|마을|궁|성|산|섬|항|포구|호수|지)$', t):
                    out.append({'term': t, 'lat': x['y'], 'lng': x['x'], 'lvl': 3, 'metro': False, 'name': x['n'], 'addr': x['a'], 'spot': 1})
                break
    return out
def where(p): return p.get('addr') or p['name']   # 행정구역 이름이 들어 있는 글
def ok_with(p, b):
    if b['lvl'] == 1: return where(p).split()[0] == b['name'].split()[0]
    if b['lvl'] == 2: return b['name'].split()[-1] in where(p) or dist((p['lat'], p['lng']), (b['lat'], b['lng'])) <= 12
    return True
def in_area(c, anc):
    """카카오 가게 c가 기준 지역 anc 안에 있나(주소로, 경계 근처는 거리로)"""
    k = kind_of(anc); d = dist((anc['lat'], anc['lng']), (c['y'], c['x']))
    a = (c.get('a') or '') + ' ' + (c.get('ra') or '')
    if k in ('metro', 'prov'): return a.split()[0] == anc['name'].split()[0] if a.strip() else False
    if k in ('sigun', 'gu'): return anc['name'].split()[-1] in a or d <= 3
    return d <= 4
def choose(terms):
    pts = {}
    for t in terms:
        r = term_points(t)
        if r is None: return 'wait'
        if r: pts[t] = r
    if not pts: return None
    broad = [min(v, key=lambda p: p['lvl']) for v in pts.values() if min(p['lvl'] for p in v) <= 2]
    allp = sorted([p for v in pts.values() for p in v], key=lambda p: -p['lvl'])
    for p in allp:
        if all(ok_with(p, b) for b in broad if b['term'] != p['term']): return p
    if broad: return min(broad, key=lambda b: (-b['lvl'], b['metro']))
    return allp[0]
def radius(p): return 20000 if p['lvl'] <= 2 else 8000

def addr_geo(a):
    for q in dict.fromkeys([addr_core(a), a]):
        r = ask({'t': 'a', 'q': q})
        if r is None: return None
        for x in (r.get('r') or []):
            if x['t'] in ('ROAD_ADDR', 'REGION_ADDR'):
                return {'lat': x['y'], 'lng': x['x'], 'road': x.get('road') or '', 'n': x['n']}
    return False
def sigungu(a):
    m = re.findall(r'([가-힣]{1,5}(?:시|군|구))(?=\s)', a + ' ')
    return m[-1] if m else ''

stats = collections.Counter(); dropped = []; raws = {}
for ch in CH:
    for v in json.load(open(f'raw/{ch}.json'))['videos']: raws[v[0]] = v[3]
for ch in CH:
    d = json.load(open(f'cand_{ch}.json'))
    res = []
    for r in d['videos']:
        vterms = anchor_terms(r['t'], raws.get(r['id'], '')) + HOME.get(ch, [])
        vanc = None; vdone = False; seen_kid = set(); rows = []
        for e in r['e']:
            row = None
            if e['a']:
                g = addr_geo(e['a'])
                if g is None: stats['wait'] += 1; continue
                if g:
                    if e['n']:
                        kr = ask({'t': 'k', 'q': e['n'], 'x': round(g['lng'], 6), 'y': round(g['lat'], 6), 'r': 500, 'n': 6})
                        if kr is None: stats['wait'] += 1; continue
                        best = max(((sim(e['n'], c['n']), c) for c in (kr.get('r') or []) if foody(c) and dist((g['lat'], g['lng']), (c['y'], c['x'])) <= 0.2), key=lambda t: t[0], default=(0, None))
                        if best[0] >= 0.75:
                            c = best[1]; row = dict(n=e['n'], a=e['a'], lat=c['y'], lng=c['x'], how='addr+name', kid=c['id'], kn=c['n'], kc=c['c'])
                        else:
                            row = dict(n=e['n'], a=e['a'], lat=g['lat'], lng=g['lng'], how='addr')
                    else:
                        cr = [ask({'t': 'c', 'q': code, 'x': round(g['lng'], 6), 'y': round(g['lat'], 6), 'r': 25}) for code in ('FD6', 'CE7')]
                        if any(x is None for x in cr): stats['wait'] += 1; continue
                        core = addr_core(g['road'] or e['a'])
                        hits = {c['id']: c for x in cr for c in (x.get('r') or []) if c.get('ra') and addr_core(c['ra']) == core}
                        if len(hits) == 1:
                            c = list(hits.values())[0]; row = dict(n=c['n'], a=e['a'], lat=c['y'], lng=c['x'], how='addr→kakao name', kid=c['id'], kn=c['n'], kc=c['c'])
                        else: stats['drop-noname' + ('-many' if hits else '')] += 1; continue
                else:
                    if not e['n']: stats['drop-noname-badaddr'] += 1; continue
                    sg = sigungu(e['a']); q = (sg + ' ' + e['n']).strip()
                    kr = ask({'t': 'k', 'q': q, 'n': 8})
                    if kr is None: stats['wait'] += 1; continue
                    best = max(((sim(e['n'], c['n']), c) for c in (kr.get('r') or []) if foody(c) and (not sg or sg in c['a'])), key=lambda t: t[0], default=(0, None))
                    if best[0] >= 0.85:
                        c = best[1]; row = dict(n=e['n'], a=e['a'], lat=c['y'], lng=c['x'], how='badaddr+name', kid=c['id'], kn=c['n'], kc=c['c'])
                    else:
                        row = dict(n=e['n'], a=e['a'], lat=None, lng=None, how='addr-unresolved')
            else:
                if not vdone: vanc = choose(vterms); vdone = True
                if vanc == 'wait': stats['wait'] += 1; continue
                anc = vanc
                if not e.get('ar'):
                    p = e['n'].split()
                    if len(p) >= 2 and re.fullmatch(r'[가-힣]{2,4}', p[0]):
                        ea0 = choose([p[0]])
                        if ea0 == 'wait': stats['wait'] += 1; continue
                        if ea0 and ea0['lvl'] >= 2: e = dict(e, ar=p[0], n=' '.join(p[1:]), full=e['n'])
                if e.get('ar'):
                    ea = choose([e['ar']] + vterms)
                    if ea == 'wait': stats['wait'] += 1; continue
                    if ea and (not vanc or ea['lvl'] >= vanc['lvl'] or ea['term'] == e['ar']): anc = ea
                full = e.get('full') or e['n']
                prefix_split = e.get('ar') and full.startswith(e['ar']) and e.get('split') != 'dash'
                q = full if prefix_split else e['n']
                cands = []
                if anc:
                    kr = ask({'t': 'k', 'q': q, 'x': round(anc['lng'], 6), 'y': round(anc['lat'], 6), 'r': radius(anc), 'n': 8})
                    if kr is None: stats['wait'] += 1; continue
                    lim = 8 if anc['lvl'] <= 2 else 3
                    for c in (kr.get('r') or []):
                        if not foody(c) or not in_area(c, anc): continue
                        s_ = max(sim(e['n'], c['n']), sim(full, c['n']))
                        dd = dist((anc['lat'], anc['lng']), (c['y'], c['x']))
                        if s_ >= 0.995 or (s_ >= 0.97 and dd <= (12 if anc['lvl'] <= 2 else 5)) or (s_ >= 0.85 and dd <= lim): cands.append((s_, -dd, c, 'anchor'))
                else:
                    kr = ask({'t': 'k', 'q': q, 'n': 8})
                    if kr is None: stats['wait'] += 1; continue
                    ex = [c for c in (kr.get('r') or []) if foody(c) and max(sim(e['n'], c['n']), sim(full, c['n'])) >= 0.97]
                    main = [c for c in ex if '본점' in c['n']]
                    if len(nk(e['n'])) >= 4 and (len(ex) == 1 or len(main) == 1):
                        cands.append((0.97, 0, (ex if len(ex) == 1 else main)[0], 'global'))
                if cands:
                    cands.sort(key=lambda t: (-t[0], -t[1]))
                    s_, _, c, how = cands[0]
                    row = dict(n=e['n'], a=c['ra'] or c['a'], lat=c['y'], lng=c['x'], how='name:' + how, kid=c['id'], kn=c['n'], kc=c['c'], anc=anc and anc['term'])
                else:
                    stats['drop-name-unverified'] += 1
                    dropped.append({'ch': ch, 't': r['t'], 'n': e['n'], 'ar': e.get('ar', ''), 'anc': anc and anc['term'], 'lvl': anc and anc['lvl']})
                    continue
            if row.get('kid'):
                if row['kid'] in seen_kid: stats['dup-in-video'] += 1; continue
                seen_kid.add(row['kid'])
            row.update(x=e.get('x', ''), ar=e.get('ar', ''), s=e.get('s', 0), src=e['src'])
            stats[row['how']] += 1
            rows.append({'vid': r['id'], 't': r['t'], 'd': r['d'], **row})
        res += rows
    json.dump(res, open(f'res_{ch}.json', 'w'), ensure_ascii=False, indent=0)
    print(ch, len(res))
print(dict(stats))
json.dump(need, open('q_next.json', 'w'), ensure_ascii=False)
json.dump(dropped, open('dropped.json', 'w'), ensure_ascii=False, indent=0)
print('need', len(need), collections.Counter(q['t'] for q in need))
