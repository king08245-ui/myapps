# 셰프이원일(@셰프이원일) 가게를 places.json 8번째 채널로 붙인다 (10/18)
# 입력: sel.json(영상·초·이름·지역·메모·카카오 id), kdet.json(카카오 장소 결과), videos.json(영상 제목·날짜)
# 사용: python3 chef_build.py  → channel-matjip/places.json 을 고쳐 씀(이미 셰프이원일이 있으면 그 줄들을 새로 만듦)
import json, re, os
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '../../../../channel-matjip/places.json')
CH = '셰프이원일'

sel = json.load(open(os.path.join(HERE, 'sel.json')))
det = {r[0]: r for r in json.load(open(os.path.join(HERE, 'kdet.json')))}   # id → [id, 이름, 분류, 도로명, 지번, x, y]
vids = json.load(open(os.path.join(HERE, 'videos.json')))

# 지역 메모 고침(영상에서 들은 지역이 지금 위치와 다르거나 물음표가 붙은 것)
AR = {'노독일처': '마포', '이화만두': '광진구 능동', '하하 공덕점': '공덕', '홍보각': '역삼동', '이원일식탁': '반포동 서래마을',
      '풍년집': '역삼동', '양각도': '일산', '성천막국수': '양재동', '원가든 능이버섯백숙 본점': '일산', '섬진강다슬기수제비': '광주',
      '홍루원': '판교 성남', '가나돈까스의집': '논현동', '순대실록 대학로본점': '대학로', '부자피자': '이태원',
      '수하동': '', '마마교자관': '안산 원곡동 다문화음식거리', '원조선창집': '강화 선원면', '톤쇼우 광안점': '부산 광안리'}
MEMO = {'원가든 능이버섯백숙 본점': '능이버섯 백숙'}

def kind(cat, name):
    p = [t.strip() for t in cat.split('>') if t.strip()]
    if not p: return ''
    last = p[-1]
    sq = lambda s: re.sub(r'\s', '', s)
    if len(p) >= 2 and len(sq(last)) >= 3 and sq(name).startswith(sq(last)):   # 끝말이 상호(체인 이름, 예: 순대실록)면 한 칸 앞
        last = p[-2]
    if last in ('음식점', '가정,생활', '식품판매'): return ''
    return last.replace(',', '·')

def dong(jibun):
    if not jibun.startswith('서울'): return ''
    for t in jibun.split()[2:]:
        if re.fullmatch(r'[가-힣]+\d*(동|가)\d*(가)?', t): return t
    return ''

d = json.load(open(OUT))
# 다시 돌려도 같은 결과: 이전에 넣은 셰프이원일 줄·영상은 지움
if CH in d['channels']:
    keep_v = [i for i, v in enumerate(d['videos']) if v[3] != CH]
    remap = {old: new for new, old in enumerate(keep_v)}
    d['places'] = [p[:4] + [remap[p[4]]] + p[5:] for p in d['places'] if p[4] in remap]
    d['videos'] = [d['videos'][i] for i in keep_v]
else:
    d['channels'].append(CH)

vidx = {}
rows = []
for e in sel:
    k = det[e['k']]
    name = e['n']
    a = k[3] or k[4]
    ar = AR.get(name, e['ar']).replace('?', '').strip()
    dn = dong(k[4])
    if dn and dn not in ar and name not in AR: ar = (ar + ' ' + dn).strip()
    if e['vid'] not in vidx:
        vidx[e['vid']] = len(d['videos'])
        v = vids[e['vid']]
        d['videos'].append([v[0], v[1], v[2], CH])
    g = [round(k[6], 6), round(k[5], 6), 1]
    rows.append([name, MEMO.get(name, e['x']), a, ar, vidx[e['vid']], int(e['s']), g, kind(k[2], name)])

# 같은 카카오 가게가 두 번이면 하나만(먼저 나온 영상)
seen = set(); uniq = []
for e, r in zip(sel, rows):
    if e['k'] in seen: continue
    seen.add(e['k']); uniq.append(r)
d['places'] += uniq
tmp = OUT + '.tmp'                       # 다 쓴 뒤 바꿔 끼움(쓰는 중에 앱·검수가 반쯤 쓴 파일을 읽지 않게)
json.dump(d, open(tmp, 'w'), ensure_ascii=False, separators=(',', ':'))
os.replace(tmp, OUT)
print('channels', d['channels'])
print('셰프이원일 가게', len(uniq), '영상', len(vidx), '전체 가게 줄', len(d['places']), '영상', len(d['videos']), 'bytes', os.path.getsize(OUT))
