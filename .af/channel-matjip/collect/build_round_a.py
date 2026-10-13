# Round A: 주소 → 좌표, 영상 제목/첫 줄의 지역 이름 → 좌표 (카카오에 물어볼 목록)
import json, re
from parse_lib import addr_core
from extract import REGION_WORD
CH = ['soulmatzip', 'mukbang3man', 'higaengs']
STOP = set('맛집 맛집투어 투어 노포 베스트 Best BEST 시장 시장투어 먹자골목 골목 서울 한국 국내 전국 동네 우리동네 시청자 시청자추천 추천 길거리 길거리음식 외곽 외곽맛집 신도시 구도심 원도심 번화가 가성비 해장 혼밥 혼술 먹거리 먹거리투어 위주 몰아보기 모아보기 종류별 아침 점심 저녁 조식 아침식사 현지인 현지 로컬 학식 구내식당 푸드코트 빵지순례 빵집 디저트 카페 짬뽕투어 짜장면 대학교 대학가 여행 여행지 명소 당일치기 코스 데이트 핫플 근방 주변 근처 일대 이야기'.split())
def anchor_terms(title, raw):
    terms = []
    for m in re.finditer(r'([가-힣A-Za-z0-9]{2,12})\s*(?:에|으로|로)\s*(?:왔|다녀왔|가봤|갔)', raw[:400]):
        terms.append(m.group(1))
    toks = [re.sub(r'(에서|으로|에는|에|의)$', '', t) for t in re.findall(r'[가-힣A-Za-z0-9]+', re.sub(r'\(.*?\)|\[.*?\]', ' ', title))]
    if toks and re.fullmatch(r'[가-힣]{2,5}', toks[0]) and toks[0] not in STOP: terms.append(toks[0])   # 제목 첫 단어는 대개 지역
    for t in toks:
        m = re.match(r'^([가-힣]{2,4})(시장|역|동|먹자골목)$', t)
        if m and m.group(1) not in STOP: terms.append(m.group(1))
    for i, t in enumerate(toks):
        t2 = re.sub(r'(맛집투어|맛집|투어|시장투어)$', '', t)
        if len(t2) < 2 or t2 in STOP or re.fullmatch(r'\d+|[A-Za-z]+', t2): continue
        if REGION_WORD.match(t2) or re.search(r'(시|군|구|동|역|읍|면|리|도|가)$', t2) or (i + 1 < len(toks) and re.match(r'(맛집|시장|먹자|투어|역)', toks[i + 1])):
            terms.append(t2)
    out = []
    for t in terms:
        t = re.sub(r'(에서|으로|에|의)$', '', t)
        if t not in out and t not in STOP and len(t) >= 2: out.append(t)
    out = out[:5]
    BIG = r'(서울|부산|대구|인천|광주|대전|울산|경기|강원|충북|충남|전북|전남|경북|경남|제주|충청북도|충청남도|전라북도|전라남도|경상북도|경상남도|강원도|경기도)'
    for m in re.finditer(BIG + r'(?:특별시|광역시|도)?\s+([가-힣]{1,4}(?:구|군|시))(?![가-힣])', title):
        tt = m.group(1) + ' ' + m.group(2)
        if tt not in out: out.insert(0, tt)
    for m in ('서울', '부산', '대구', '인천', '광주', '대전', '울산', '제주'):
        if m in title and m not in out: out.append(m)
    return out

if __name__ == '__main__':
    Q = []; seen = set()
    raws = {}
    for ch in CH:
        for v in json.load(open(f'raw/{ch}.json'))['videos']: raws[v[0]] = v[3]
    for ch in CH:
        d = json.load(open(f'cand_{ch}.json'))
        for r in d['videos']:
            need_anchor = False
            for e in r['e']:
                if e['a']:
                    for q in {addr_core(e['a']), e['a']}:
                        if q and ('a', q) not in seen: seen.add(('a', q)); Q.append({'t': 'a', 'q': q})
                else: need_anchor = True
            if need_anchor:
                r['anchors'] = anchor_terms(r['t'], raws.get(r['id'], ''))
                for t in r['anchors']:
                    if ('a', t) not in seen: seen.add(('a', t)); Q.append({'t': 'a', 'q': t})
                    if ('k', t) not in seen: seen.add(('k', t)); Q.append({'t': 'k', 'q': t})
        json.dump(d, open(f'cand_{ch}.json', 'w'), ensure_ascii=False, indent=0)
    json.dump(Q, open('qa.json', 'w'), ensure_ascii=False)
    import collections
    print(len(Q), collections.Counter(q['t'] for q in Q))
    d = json.load(open('cand_higaengs.json'))
    for r in d['videos'][:12]: print(r['t'][:40], '→', r.get('anchors'))

