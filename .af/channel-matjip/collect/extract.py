# 채널별 설명란 → 가게 후보 (candidates/<채널>.json)
import json, re, sys, collections
from parse_lib import *

def boilerplate(videos):
    cnt = collections.Counter()
    for v in videos:
        cnt.update(set(l.strip() for l in v[3].split('\n') if l.strip()))
    n = len(videos)
    return {l for l, c in cnt.items() if c >= max(4, n * 0.08)}

REGION_WORD = re.compile(r'^(서울|부산|대구|인천|광주|대전|울산|세종|제주|수원|성남|고양|용인|부천|안산|안양|남양주|화성|평택|의정부|시흥|파주|김포|광명|군포|하남|오산|이천|양주|구리|안성|포천|의왕|여주|동두천|과천|가평|양평|연천|춘천|원주|강릉|동해|태백|속초|삼척|홍천|횡성|영월|평창|정선|철원|화천|양구|인제|고성|양양|청주|충주|제천|보은|옥천|영동|증평|진천|괴산|음성|단양|천안|공주|보령|아산|서산|논산|계룡|당진|금산|부여|서천|청양|홍성|예산|태안|전주|군산|익산|정읍|남원|김제|완주|진안|무주|장수|임실|순창|고창|부안|목포|여수|순천|나주|광양|담양|곡성|구례|고흥|보성|화순|장흥|강진|해남|영암|무안|함평|영광|장성|완도|진도|신안|포항|경주|김천|안동|구미|영주|영천|상주|문경|경산|군위|의성|청송|영양|영덕|청도|고령|성주|칠곡|예천|봉화|울진|울릉|창원|마산|진주|통영|사천|김해|밀양|거제|양산|의령|함안|창녕|남해|하동|산청|함양|거창|합천|서귀포|부평|일산|분당|송도|판교|동탄|평촌|산본|중동|영등포|강남|강북|강서|강동|마포|용산|종로|중구|성북|성동|동대문|서대문|은평|노원|도봉|광진|관악|동작|서초|송파|양천|구로|금천|중랑)(시|군|구|도)?$')

def extract(v, ch, boiler):
    vid, title, date, raw = v
    lines = [l.strip() for l in raw.split('\n')]
    lines = [l for l in lines if l and l not in boiler]
    out = []          # entries
    ts = []           # (sec, name, x)
    for l in lines:
        m = RE_TS.search(l)
        if not m: continue
        txt = (l[:m.start()] + ' ' + l[m.end():]).strip()
        if RE_TS.search(txt): txt = RE_TS.sub(' ', txt).strip()   # "1. 수정분식 00:54" or "00:54 수정분식"
        n, x = split_name(txt)
        if n: ts.append((secs(m), n, x))
    used = set()
    last_addr_i = -10; last_name_i = -10
    for i, l in enumerate(lines):
        a = is_addr(l)
        if not a: continue
        a = clean_addr(a)
        # same shop as the previous address? (no new name line in between)
        if out and out[-1].get('ai') is not None and last_name_i < out[-1]['ai'] and i - out[-1]['ai'] <= 4:
            between = lines[out[-1]['ai'] + 1:i]
            if all(is_meta(b) or is_jibun(b) or is_addr(b) or RE_MARK.match(b) for b in between):
                if re.search(r'(로|길)\s*\d', a) and not re.search(r'(로|길)\s*\d', out[-1]['a']): out[-1]['a'] = a
                out[-1]['ai'] = i
                continue
        name, x, j = '', '', i - 1
        while j >= 0 and i - j <= 8:
            b = lines[j]
            if is_addr(b) or (j in used): break
            if is_meta(b) or is_jibun(b) or RE_MARK.match(b) or RE_URL.search(b) and len(RE_URL.sub('', b).strip()) < 2: j -= 1; continue
            n, xx = split_name(b)
            if not is_prose(b) and name_ok(n, boiler, strict=False): name, x = n, xx; used.add(j); last_name_i = j; break
            break
        if not name:
            t = addr_tail(a)
            n, xx = split_name(t) if t else ('', '')
            if n and name_ok(n, boiler): name, x = n, xx
        out.append({'n': name, 'x': x, 'a': a, 'src': 'addr', 'ai': i})
        last_addr_i = i
    # numbered list items / list block items without address
    in_list = False
    for i, l in enumerate(lines):
        if i in used: continue
        if RE_MARK.match(l):
            in_list = bool(re.search(r'목록|리스트|목차', l)); continue
        numbered = re.match(r'^\s*(?:\d{1,2}\s*[.)．]|[①-⑮]|\(\d{1,2}\))\s*\S', l)
        if not (numbered or in_list): continue
        if is_addr(l) or is_jibun(l) or is_meta(l) or RE_URL.search(l) and len(RE_URL.sub('', l).strip()) < 3: continue
        if RE_TS.search(l):  # timeline line, handled as ts
            continue
        if is_prose(l):
            in_list = False if not numbered else in_list
            continue
        n, x = split_name(l)
        if not name_ok(n, boiler): continue
        if any(norm_name(e['n']) == norm_name(n) for e in out): continue
        out.append({'n': n, 'x': x, 'a': '', 'src': 'list'})
    # timeline names (only when no list/address names, or names not yet present)
    names = [norm_name(e['n']) for e in out if e['n']]
    ts_entries = []
    for s, n, x in ts:
        if not name_ok(n, boiler) or is_prose(n): continue
        k = norm_name(n)
        hit = next((e for e in out if e['n'] and (norm_name(e['n']) == k or (len(k) >= 2 and (k in norm_name(e['n']) or norm_name(e['n']) in k)))), None)
        if hit:
            if not hit.get('s'): hit['s'] = s
            continue
        ts_entries.append({'n': n, 'x': x, 'a': '', 'src': 'ts', 's': s})
    if not out: out += ts_entries          # 목록·주소가 없을 때만 타임라인 이름을 후보로
    for e in out: e.pop('ai', None); e.setdefault('s', 0)
    # ranking items like "수원 중평떡볶이", "문정역 서울콩비지", "폴앤폴리나 - 여의도": split the place part
    AREA_END = re.compile(r'(역|동|시장|시장내|거리|골목|먹자골목|구|시|군|읍|면|가|로|길|터미널|대학교|대|공원|타운|센터|몰)$')
    for e in out:
        if not e['n']: continue
        e['full'] = e['n']
        if e['src'] in ('list', 'ts'):
            parts = re.split(r'\s+[-–—/]\s+|\s*[-–—]\s*(?=[가-힣A-Za-z])(?<=[가-힣A-Za-z]\s[-–—])', e['n'])
            parts = [p.strip() for p in re.split(r'\s[-–—]\s|\s[-–—]|[-–—]\s', e['n']) if p.strip()]
            if len(parts) == 2:
                a, b = parts
                isA = lambda s: bool(REGION_WORD.match(s.split()[0]) or re.search(r'(역|[가-힣]{1,4}동|시장|시장내|거리|골목|터미널|대학교|공원)$', s))
                if isA(b) and not isA(a): e['n'], e['ar'], e['split'] = a, b.replace('시장내', '시장'), 'dash'
                elif isA(a) and not isA(b): e['n'], e['ar'], e['split'] = b, a.replace('시장내', '시장'), 'dash'
            p = e['n'].split()
            if len(p) >= 2 and (REGION_WORD.match(p[0]) or (len(p[0]) >= 3 and re.search(r'(역|동)$', p[0]))) and not e.get('ar') \
                    and not (re.fullmatch(r'[가-힣A-Za-z0-9]{0,6}(본점|직영점|본관|별관|\d호점)', ' '.join(p[1:])) or (re.fullmatch(r'[가-힣]{2,3}점', ' '.join(p[1:])) and not ' '.join(p[1:]).endswith('반점'))):
                e['ar'] = p[0]; e['n'] = ' '.join(p[1:]); e['split'] = 'prefix'
    return out

if __name__ == '__main__':
    ch = sys.argv[1]
    d = json.load(open(f'raw/{ch}.json'))
    B = boilerplate(d['videos'])
    res = []
    for v in d['videos']:
        res.append({'id': v[0], 't': v[1], 'd': v[2], 'e': extract(v, ch, B)})
    json.dump({'title': d['title'], 'videos': res}, open(f'cand_{ch}.json', 'w'), ensure_ascii=False, indent=0)
    c = collections.Counter(e['src'] for r in res for e in r['e'])
    print(ch, 'videos', len(res), 'with entries', sum(1 for r in res if r['e']), dict(c), 'noname-addr', sum(1 for r in res for e in r['e'] if not e['n']))
