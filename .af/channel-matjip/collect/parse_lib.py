# 유튜브 설명란 → 가게 후보 뽑기 (채널 공통 도구)
import re

PROV = r'(?:서울(?:특별시)?|부산(?:광역시)?|대구(?:광역시)?|인천(?:광역시)?|광주(?:광역시)?|대전(?:광역시)?|울산(?:광역시)?|세종(?:특별자치시)?|경기(?:도)?|강원(?:특별자치도|도)?|충북|충청북도|충남|충청남도|전북(?:특별자치도)?|전라북도|전남|전라남도|경북|경상북도|경남|경상남도|제주(?:특별자치도|도)?)'
LEAD = r'^(?:[-•·*▶►✔︎✅☞👉📍📌🏠🏡🗺️🗺※>\s]|주소|위치|가게\s*위치|식당\s*위치|도로명|지번|address)*\s*[:：]?\s*'
RE_ADDR_PROV = re.compile(LEAD + r'(' + PROV + r'\s*[가-힣0-9]{1,8}(?:시|군|구)[\s\S]*?\d[\s\S]*)$')
RE_ADDR_PROV2 = re.compile(LEAD + r'(' + PROV + r'\s+[가-힣0-9]{1,10}(?:로|길|동|가|리|읍|면)\s*\d[\s\S]*)$')   # 세종 ○○로 12
RE_ADDR_SIGU = re.compile(LEAD + r'([가-힣]{1,5}(?:시|군|구)\s+(?:[가-힣]{1,5}(?:구|읍|면)\s+)?[가-힣0-9·.]{1,14}(?:로|길|동|가|리)\s*\d[\s\S]*)$')
RE_JIBUN = re.compile(r'^(?:\(?지번\)?\s*[:：]?\s*)?(?:' + PROV + r'\s*)?(?:[가-힣]{1,5}(?:시|군|구)\s*)?(?:[가-힣]{1,5}(?:구|읍|면)\s*)?[가-힣0-9]{1,10}(?:동|가|리|로)\d*(?:가)?\s*(?:산\s*)?\d+(?:-\d+)?(?:\s*\(?(?:지번|지명)\)?)?\s*$')
RE_TS = re.compile(r'(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])')
RE_PHONE = re.compile(r'(?:^|\D)(0\d{1,2}|0507|0505|010|070|1\d{3})[-.\s)]\s?\d{3,4}[-.\s]\d{4}(?:\D|$)')
RE_URL = re.compile(r'https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:com|co\.kr|kr|net|me|gl|ly|link)/\S*', re.I)
RE_META = re.compile(r'(영업\s*시간|영업|운영\s*시간|휴무|휴일|정기\s*휴|브레이크|라스트\s*오더|last\s*order|주차|출구|도보|전화|연락처|tel\b|☎|📞|⏰|🕐|🕑|💰|💵|가격|메뉴\s*[:：]|대표\s*메뉴|웨이팅|예약|배달|포장|재료\s*소진|매주|매달|월요일|화요일|수요일|목요일|금요일|토요일|일요일|평일|주말|공휴일|오전|오후|점심|저녁|^매일\s*(?:\d|오전|오후|영업|[(])|^\d{1,2}(:\d{2})?\s*[~-]|\d{1,2}:\d{2}\s*[~-]\s*\d{1,2}:\d{2}|\d{1,2}시(?:\s*\d{1,2}분)?\s*[~-]|[월화수목금토일]\s*[~-]\s*[월화수목금토일]|^[(（]|\d+,\d{3}\s*원|\d+\s*원\b|만원|천원)', re.I)
RE_MARK = re.compile(r'^[*\-=\[<【\s]*(식당\s*정보|가게\s*정보|맛집\s*정보|식당\s*목록|가게\s*목록|맛집\s*목록|식당\s*리스트|목록|목차|타임\s*라인|순서|챕터|chapters?|정보|위치|주소|장소|방문\s*식당|소개\s*식당|오늘의\s*식당|식당|가게|맛집\s*리스트|리스트|지도\s*모음집|주소\s*모음집)[*\-=\]>】\s:：]*$', re.I)
RE_PROSE_END = re.compile(r'(다|요|죠|네|니다|어요|아요|해요|세요|군요|구요|네요|ㅋ+|ㅎ+|ㅠ+|ㅜ+|[!?~…♡♥^]+|\.{2,}|\.)\s*\W*$')
RE_HASHLINE = re.compile(r'^#')
GENERIC = re.compile(r'(맛집|먹방|mukbang|korean\s*food|food|노포|핫플|추천|투어|리뷰|후기|구독|좋아요|알람|브금|music|track|bgm|채널|영상|촬영|협찬|광고|유료|제작\s*지원|오프닝|엔딩|인트로|아웃트로|마무리|요약|opening|ending|intro|outro|closing|사담|선정|감사|다음|예고|구글|google|지도|배경\s*음악|음악|naver|네이버|카카오|kakao|등록|검색|정보\s*없음|없음$)', re.I)

def norm_name(s):
    return re.sub(r'[\s·.\-_\'"‘’“”()\[\]]', '', (s or '')).lower()

def secs(m):
    h = int(m.group(1) or 0); mm = int(m.group(2)); ss = int(m.group(3))
    return h * 3600 + mm * 60 + ss

def strip_lead(s):
    s = s.strip()
    s = re.sub(r'^[\s\-•·*▶►✔︎✅☞👉📍📌🍴🔥⭐️★☆◆◇■□●○◎▷▶︎→>※#]+', '', s)
    s = re.sub(r'^(?:\d{1,2}\s*[.)．、:]\s*|\(\d{1,2}\)\s*|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]\s*|no\.?\s*\d+\s*|top\s*\d+\s*[.:]?\s*|best\s*\d+\s*[.:]?\s*|\d{1,2}\s*(?:위|등|번째|번)\s*[.):]?\s*)', '', s, flags=re.I)
    s = re.sub(r'^\d+차\s*[.:)]?\s*', '', s)
    return s.strip()

def is_addr(l):
    l = l.strip()
    if len(l) > 90 or len(l) < 6: return None
    for rx in (RE_ADDR_PROV, RE_ADDR_PROV2, RE_ADDR_SIGU):
        m = rx.match(l)
        if m:
            a = m.group(1).strip()
            if not re.search(r'(로|길|동|가|리|번지|읍|면)\s*\d|\d+\s*(번지|-\d)', a):  # needs a house number
                return None
            if re.search(r'(니다|어요|아요|해요|세요|습니다|네요|었|았|에\s*가면|근처에|다녀왔|있는|입니다)', a):  # a sentence, not an address
                return None
            return a
    return None

def is_jibun(l):
    l = l.strip()
    return bool(RE_JIBUN.match(l)) and len(l) <= 40

def clean_addr(a):
    a = re.sub(r'\s*[(（](?:도로명|지번|지명|구주소|신주소)[)）]\s*', ' ', a)
    a = re.sub(r'\s+', ' ', a).strip(' ,')
    return a

def addr_core(a):
    """주소에서 번지까지만 (층·호·건물 이름 빼기)"""
    t = re.sub(r'\(.*?\)', ' ', a)
    t = re.sub(r'(로|길)\s+(\d+(?:번|가)?길)(?=\s|$)', r'\1\2', t).split()
    for i in range(len(t) - 1, 0, -1):
        if re.fullmatch(r'(?:산)?\d+(?:-\d+)?(?:번지)?', t[i]) and re.search(r'(로|길|가|동|리|읍|면)$', t[i - 1]):
            return ' '.join(t[:i + 1]).replace('번지', '')
    return ' '.join(t)

def addr_tail(a):
    """주소 뒤에 붙은 가게 이름 후보: '서울 중구 창경궁로 67-13 꾸왁칼국수 1층' → '꾸왁칼국수'"""
    core = addr_core(a)
    rest = a[len(core):] if a.startswith(core) else ''
    rest = re.sub(r'\(.*?\)', ' ', rest)
    rest = re.sub(r'(지하\s*)?\d+\s*층|\d+\s*호|\d+F|B\d|1st|상가|건물|빌딩|내$', ' ', rest, flags=re.I)
    rest = re.sub(r'[,]', ' ', rest).strip()
    return rest if 2 <= len(rest) <= 20 else ''

def is_meta(l):
    s = l.strip()
    if not s: return True
    if RE_URL.fullmatch(s) or s.startswith('http'): return True
    if RE_HASHLINE.match(s): return True
    if RE_PHONE.search(s): return True
    if RE_META.search(s) and not re.search(r'[가-힣]{2,}(식당|집|관|옥|정|당|루|각|원|점)$', s): return True
    if re.fullmatch(r'[\d\s:~\-.,/()]+', s): return True
    if re.search(r'(역|정류장)\s*\d*\s*번?\s*출구|에서\s*\d+\s*m|\d+\s*m\s*$|\d+\s*km', s): return True
    return False

def is_prose(l):
    s = l.strip()
    if len(s) > 28: return True
    if s.count(' ') >= 5: return True
    if RE_PROSE_END.search(s) and len(s) > 7: return True
    return False

def split_name(raw):
    """'수정분식(칼국수)' → ('수정분식', '칼국수')"""
    s = strip_lead(raw)
    s = re.sub(r'\(?\b(0\d{1,2}|0507|0505|010|070)[-.\s)]\s?\d{3,4}[-.\s]\d{4}\b\)?', ' ', s)
    s = RE_TS.sub(' ', s).strip(' -–—:|/')
    s = re.sub(r'\s*[-–—:|]\s*$', '', s)
    x = ''
    m = re.match(r'^(.{2,30}?)\s*[(（\[]([^)）\]]{1,24})[)）\]]\s*$', s)
    if m: s, x = m.group(1).strip(), m.group(2).strip()
    s = s.strip(' \'"‘’“”「」『』<>《》')
    m = re.match(r'^[\'"‘’“”「『<《]?(.{2,30}?)[\'"‘’“”」』>》]\s*(.*)$', s)
    if m and m.group(2): s, x = m.group(1), (x + ' ' + m.group(2)).strip()
    return s.strip(), x

def name_ok(n, boiler=(), strict=True):
    if not n or len(n) < 2 or len(n) > 30: return False
    if n in boiler: return False
    if re.fullmatch(r'[\d\s\W]+', n): return False
    if GENERIC.search(n) and not re.search(r'(식당|(?<!맛)집|관|옥|점|당|루|각|분식|국수|냉면|국밥|반점|횟집|갈비|곱창|족발|보쌈|치킨|통닭|빵|베이커리|카페|커피|김밥|떡볶이|순대|만두|짬뽕|짜장|돈까스|돈가스|라멘|우동|소바|스시|초밥|회관|수산|정육|포차|주점|호프|막걸리)', n): return False
    if re.fullmatch(PROV, n) or (re.fullmatch(r'(?:' + PROV + r'\s*)?(?:[가-힣]{1,6}(시|군|구|역|읍|면' + ('|동' if strict else '') + r')|[가-힣]{1,5}\d가)(\s*맛집)?', n) and not re.search(r'(식당|집|옥|관|국수|냉면|분식)', n.replace('맛집', ''))): return False
    if is_addr(n) or is_jibun(n): return False
    return True
