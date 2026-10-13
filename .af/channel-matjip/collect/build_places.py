# 기존 places.json + 새 채널 결과 → 새 places.json (가게 종류 8번째 칸 추가)
import json, re, sys, collections
sys.argv = ['x']
src = open('resolve2.py').read().split("stats = collections.Counter()")[0]
exec(src)                                  # sim, dist, foody, ask/C 등
OLD = '/home/claude/myapps/channel-matjip/places.json'
d = json.load(open(OLD))
def kind(kc):
    if not kc: return ''
    t = kc.split('>')[-1].strip()
    if t in ('음식점', '') : t = kc.split('>')[0].strip() if '>' in kc else ''
    if t in ('음식점', '가정,생활', '식품판매'): return ''
    return t.replace(',', '·')
# 1) 기존 가게: 이름+좌표로 카카오 분류 붙이기
nk_old = 0
for p in d['places']:
    while len(p) < 7: p.append(None)
    k = ''
    g = p[6]
    if g and g[2] == 1:
        r = C.get(kcache.key({'t': 'k', 'q': p[0], 'x': round(g[1], 6), 'y': round(g[0], 6), 'r': 300, 'n': 6}))
        if r:
            best = max(((sim(p[0], c['n']), c) for c in (r.get('r') or []) if foody(c) and dist((g[0], g[1]), (c['y'], c['x'])) <= 0.2), key=lambda t: t[0], default=(0, None))
            if best[0] >= 0.85: k = kind(best[1]['c'])
    p[:] = p[:7] + [k]
    if k: nk_old += 1
# 2) 새 채널
NAMES = {'mukbang3man': '맛삼인', 'soulmatzip': '쏘울맛집', 'higaengs': '하이갱스', 'seoul_namzaa': '서울 사는 남자'}
ORDER = ['mukbang3man', 'soulmatzip', 'higaengs', 'seoul_namzaa']
LABEL = re.compile(r'^(가게명|가게\s*이름|상호명?|식당명?|업체명|장소|방문\s*매장|매장명?|식당\s*이름)\s*[:：]\s*')
vidx = {}; drop = collections.Counter(); added = collections.Counter()
for ch in ORDER:
    rows = json.load(open(f'res_{ch}.json'))
    for r in rows:
        n = LABEL.sub('', r['n']).strip()
        n = re.sub(r'\s+', ' ', n)
        if re.search(r'폐업|이전(했|함|됨)?\s*$|으로\s*이전|로\s*이전', n): drop['폐업·이전'] += 1; continue
        n = re.sub(r'\s*\*.*$', '', n).strip()
        kc = r.get('kc') or ''
        if re.search(r'시장$', n) and not re.search(r'(식당|집|국밥|국수|분식|순대|떡|빵|칼국수|만두|김밥|횟집|수산|정육|반찬)', n) and (not kc or '시장' in kc or not foody({'c': kc, 'g': ''})):
            drop['시장 이름'] += 1; continue
        if not n or len(n) < 2: drop['이름 없음'] += 1; continue
        key = r['vid']
        if key not in vidx:
            vidx[key] = len(d['videos']); d['videos'].append([r['vid'], r['t'], r['d'], NAMES[ch]])
        g = [round(r['lat'], 6), round(r['lng'], 6), 1] if r.get('lat') else None
        a = re.sub(r'\s+', ' ', (r.get('a') or '')).strip()
        x = (r.get('x') or '').strip()
        if re.search(r'구글|google|검색|등록', x): x = ''
        d['places'].append([n, x, a, r.get('ar') or '', vidx[key], int(r.get('s') or 0), g, kind(kc)])
        added[ch] += 1
d['channels'] = d['channels'][:3] + [NAMES[c] for c in ORDER]
# 같은 영상 안 같은 이름 줄 하나로
seen = set(); out = []
for p in d['places']:
    k = (p[4], norm_name(p[0]))
    if k in seen: drop['같은 영상 중복'] += 1; continue
    seen.add(k); out.append(p)
d['places'] = out
json.dump(d, open('places_new.json', 'w'), ensure_ascii=False, separators=(',', ':'))
import os
print('old with kind', nk_old, 'added', dict(added), 'dropped', dict(drop))
print('channels', d['channels'], 'videos', len(d['videos']), 'places', len(d['places']), 'bytes', os.path.getsize('places_new.json'))
