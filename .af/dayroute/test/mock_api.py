"""카카오 장소 검색·카카오모빌리티 길찾기·ODsay 대중교통을 흉내 내는 시험용 서버 (실제 응답 모양 그대로)
python3 mock_api.py PORT   →   /v2/local/search/keyword.json, /v1/directions, /v1/api/searchPubTransPathT, /__stats, /__reset"""
import json, math, sys, hashlib, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8790
STATS = {"kakao": 0, "navi": 0, "odsay": 0, "queries": []}
LOCK = threading.Lock()

# 이름으로 찾는 곳 (실제 좌표)
KNOWN = [
    ("공덕역 5호선", "교통,수송 > 지하철,전철 > 수도권5호선", 126.951592, 37.544018, "서울 마포구 마포대로 지하 92"),
    ("이태원역 6호선", "교통,수송 > 지하철,전철 > 수도권6호선", 126.994333861918, 37.5345252050511, "서울 용산구 이태원로 지하 177"),
    ("교보문고 광화문점", "문화,예술 > 도서 > 서점 > 대형서점", 126.97795, 37.57089, "서울 종로구 종로 1"),
    ("정독도서관", "사회,공공기관 > 도서관 > 공공도서관", 126.98322, 37.58149, "서울 종로구 북촌로5길 48"),
    ("유진식당", "음식점 > 한식 > 냉면", 126.98897, 37.57211, "서울 종로구 종로17길 52-1"),
    ("서울역", "교통,수송 > 기차,철도 > 기차역 > KTX정차역", 126.97061, 37.55467, "서울 용산구 한강대로 405"),
    ("대천IC", "교통,수송 > 도로시설 > IC > 고속도로IC", 126.575398785335, 36.3332494526298, "충남 보령시 주교면 관창리"),
    ("국립현대미술관 서울", "문화,예술 > 문화시설 > 미술관", 126.98015, 37.57863, "서울 종로구 삼청로 30"),
    ("여의도한강공원", "여행 > 공원 > 도시근린공원", 126.93425, 37.52834, "서울 영등포구 여의동로 330"),
]
CATS = [  # (검색어에 이 말이 있으면, 분류, 이름들)
    ("헬스", "스포츠,레저 > 스포츠시설 > 피트니스", ["바디라인 피트니스", "에이블짐", "스포애니", "짐박스"]),
    ("백반", "음식점 > 한식 > 백반,가정식", ["엄마손백반", "기사식당", "한솥밥집"]),
    ("국밥", "음식점 > 한식 > 국밥", ["옥천순대국", "할매국밥", "광장국밥", "청진동해장국"]),
    ("분식", "음식점 > 분식", ["김밥천국", "신전떡볶이", "명동분식"]),
    ("칼국수", "음식점 > 한식 > 국수 > 칼국수", ["명동교자", "바지락칼국수", "황생가칼국수"]),
    ("돈까스", "음식점 > 일식 > 돈까스,우동", ["정돈", "돈까스클럽"]),
    ("냉면", "음식점 > 한식 > 냉면", ["을지면옥", "평래옥"]),
    ("카페", "음식점 > 카페 > 커피전문점", ["스타벅스", "블루보틀", "카페 온화", "어니언"]),
    ("커피", "음식점 > 카페 > 커피전문점", ["스타벅스", "메가커피"]),
    ("미술관", "문화,예술 > 문화시설 > 미술관", ["서울시립미술관", "아트선재센터"]),
    ("박물관", "문화,예술 > 문화시설 > 박물관", ["국립민속박물관", "서울역사박물관"]),
    ("공원", "여행 > 공원 > 도시근린공원", ["효창공원", "경의선숲길", "서울숲"]),
    ("영화", "문화,예술 > 영화,영상 > 영화관", ["CGV 용산", "롯데시네마", "메가박스"]),
    ("사우나", "가정,생활 > 목욕,찜질 > 사우나,찜질방", ["드래곤힐스파", "해수사우나"]),
    ("서점", "문화,예술 > 도서 > 서점", ["영풍문고", "알라딘 중고서점"]),
]
MIXED_FOOD = [  # '맛집' 검색: 비싼 곳과 싼 곳이 섞여 나온다(가격대 거르기 시험용)
    ("한우명가", "음식점 > 한식 > 육류,고기 > 한우"), ("스시오마카세 진", "음식점 > 일식 > 초밥,롤 > 오마카세"),
    ("옥천순대국", "음식점 > 한식 > 국밥"), ("엄마손백반", "음식점 > 한식 > 백반,가정식"),
    ("그릴스테이크", "음식점 > 양식 > 스테이크,립"), ("명동분식", "음식점 > 분식"), ("평래옥", "음식점 > 한식 > 냉면"),
]


def h(s):
    return int(hashlib.md5(s.encode()).hexdigest(), 16)


def offset(x, y, meters, angle):
    dy = meters * math.cos(angle) / 111320
    dx = meters * math.sin(angle) / (111320 * math.cos(math.radians(y)))
    return x + dx, y + dy


def dist_m(x1, y1, x2, y2):
    R = 6371000
    p1, p2 = math.radians(y1), math.radians(y2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(x2 - x1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def doc(name, cat, x, y, addr, d=None):
    return {"place_name": name, "category_name": cat, "x": f"{x:.6f}", "y": f"{y:.6f}", "road_address_name": addr,
            "address_name": addr, "phone": "02-000-0000", "place_url": f"http://place.map.kakao.com/{h(name) % 10**8}",
            "distance": "" if d is None else str(int(d))}


def name_hit(query, k):
    """검색어의 낱말이 모두 이름이나 분류에 들어 있으면 맞는 곳 (카카오처럼 '광화문 교보문고' → 교보문고 광화문점)"""
    words = [w for w in query.split() if w]
    hay = (k[0] + k[1]).replace(" ", "")
    return bool(words) and all(w in hay for w in words)


def keyword(q):
    query = q.get("query", [""])[0]
    size = int(q.get("size", ["5"])[0])
    code = q.get("category_group_code", [""])[0]
    with LOCK:
        STATS["kakao"] += 1
        STATS["queries"].append(query)
    if "없는" in query:
        return []
    if "x" not in q:   # 전국: 이름으로
        hits = [k for k in KNOWN if name_hit(query, k)]
        if not hits and len(query) >= 2:
            hv = h(query)
            hits = [(query.split()[-1] if len(query.split()) > 1 else query, "여행 > 관광,명소", 126.95 + (hv % 1000) / 10000, 37.53 + (hv // 1000 % 600) / 10000, "서울 어딘가 " + str(hv % 99))]
        return [doc(*k) for k in hits[:size]]
    x, y = float(q["x"][0]), float(q["y"][0])
    radius = int(q.get("radius", ["3000"])[0])
    out = []
    # 이름이 맞는 실제 장소가 반경 안이면 (정확도순이면 맨 앞, 이름이 맞으면 가짜 지점은 만들지 않음)
    known = []
    for k in KNOWN:
        if name_hit(query, k):
            d = dist_m(x, y, k[2], k[3])
            if d <= radius:
                known.append(doc(*k, d=d))
    if known and q.get("sort", ["distance"])[0] == "accuracy":
        return known[:size]
    out += known
    if code == "FD6" and not any(w in query for w, _, _ in CATS):
        names = MIXED_FOOD
    else:
        hit = next((c for c in CATS if c[0] in query), None)
        if hit:
            names = [(n, hit[1]) for n in hit[2]]
        elif code == "CE7":
            names = [(n, "음식점 > 카페 > 커피전문점") for n in ["스타벅스", "메가커피", "카페 온화"]]
        else:
            names = [(f"{query} {i + 1}호점", "여행 > 관광,명소") for i in range(3)]
    # 반경이 넓을수록 더 많이 나온다 (좁은 반경에서 없을 때 넓혀 찾는 동작 시험용)
    n = 1 if radius <= 500 else 2 if radius <= 1000 else 4 if radius <= 3000 else 6
    if "드문" in query:
        n = 0 if radius < 2000 else 1
    for i in range(min(n, len(names) * 2)):
        nm, cat = names[i % len(names)]
        d = radius * (0.25 + 0.6 * ((h(query + str(i)) % 100) / 100))
        px, py = offset(x, y, d, (h(nm + str(i)) % 360) * math.pi / 180)
        label = nm if i < len(names) else f"{nm} {i // len(names) + 1}호점"
        out.append(doc(label, cat, px, py, f"서울 테스트구 시험로 {h(label) % 300}", d=dist_m(x, y, px, py)))
    if not code and radius >= 1000 and "주차" not in query:
        px, py = offset(x, y, radius * 0.2, 0.5)
        out.append(doc(f"{query} 공영주차장", "교통,수송 > 교통시설 > 주차장", px, py, "서울 테스트구 주차로 1", d=dist_m(x, y, px, py)))
    if "서점" in query and not code:   # 실제 카카오처럼 이름에 검색어가 든 다른 종류 가게가 가장 가까이 섞여 나옴(교보문고 안 안경점 등)
        px, py = offset(x, y, min(radius * 0.05, 60), 1.0)
        out.append(doc("서점옆 안경원", "가정,생활 > 안경,렌즈", px, py, "서울 테스트구 안경로 1", d=dist_m(x, y, px, py)))
    out.sort(key=lambda d_: float(d_["distance"] or 0))
    return out[:size]


def directions(q):
    with LOCK:
        STATS["navi"] += 1
    ox, oy = map(float, q["origin"][0].split(","))
    dx, dy = map(float, q["destination"][0].split(","))
    d = dist_m(ox, oy, dx, dy) * 1.3
    if d < 60:
        return {"routes": [{"result_code": 104, "result_msg": "출발지와 도착지가 5 m 이내로 설정된 경우 경로를 탐색할 수 없음"}]}
    roads, names = [], ["마포대로", "세종대로", "율곡로"]
    for r in range(3):
        v = []
        for i in range(12):
            t = (r * 12 + i) / 35
            v += [ox + (dx - ox) * t + 0.001 * math.sin(t * 9), oy + (dy - oy) * t]
        roads.append({"name": names[r], "distance": int(d / 3), "duration": int(d / 3 / 8), "vertexes": v})
    return {"routes": [{"result_code": 0, "summary": {"distance": int(d), "duration": int(d / 8.5),
            "fare": {"taxi": 4800 + int(d / 131) * 100, "toll": 2500 if d > 30000 else 0}},
            "sections": [{"roads": roads}]}]}


def odsay(q):
    with LOCK:
        STATS["odsay"] += 1
    if q.get("apiKey", [""])[0] != "test":
        return {"error": [{"code": "500", "message": "[ApiKeyAuthFailed] ApiKey authentication failed."}]}
    sx, sy, ex, ey = (float(q[k][0]) for k in ("SX", "SY", "EX", "EY"))
    d = dist_m(sx, sy, ex, ey)
    if d < 700:
        return {"error": [{"code": "-98", "message": "출, 도착지가 700m이내입니다."}]}
    kind = q.get("SearchPathType", ["0"])[0]

    def stations(n):
        return {"stations": [{"x": f"{sx + (ex - sx) * i / (n - 1):.6f}", "y": f"{sy + (ey - sy) * i / (n - 1):.6f}", "stationName": f"정류장{i}"} for i in range(n)]}
    ride = max(5, int(d / 400))
    subway = {"info": {"totalTime": ride + 11, "totalDistance": int(d * 1.2), "payment": 1400}, "subPath": [
        {"trafficType": 3, "sectionTime": 6}, {"trafficType": 1, "sectionTime": ride, "stationCount": max(2, int(d / 1200)),
         "lane": [{"name": "수도권 5호선", "subwayCode": 5}], "startName": "공덕", "endName": "광화문",
         "startX": sx, "startY": sy, "endX": ex, "endY": ey, "passStopList": stations(5)}, {"trafficType": 3, "sectionTime": 5}]}
    bus = {"info": {"totalTime": ride + 16, "totalDistance": int(d * 1.3), "payment": 1500}, "subPath": [
        {"trafficType": 3, "sectionTime": 4}, {"trafficType": 2, "sectionTime": ride + 6, "stationCount": max(3, int(d / 500)),
         "lane": [{"busNo": "472", "type": 11}, {"busNo": "261", "type": 11}, {"busNo": "7016", "type": 12}],
         "startName": "공덕역", "endName": "세종문화회관", "startX": sx, "startY": sy, "endX": ex, "endY": ey, "passStopList": stations(7)},
        {"trafficType": 3, "sectionTime": 6}]}
    mixed = {"info": {"totalTime": ride + 14, "totalDistance": int(d * 1.25), "payment": 1500}, "subPath": [
        {"trafficType": 3, "sectionTime": 3}, {"trafficType": 2, "sectionTime": 8, "stationCount": 4, "lane": [{"busNo": "604", "type": 11}],
         "startName": "출발 정류장", "endName": "환승 정류장", "startX": sx, "startY": sy, "endX": (sx + ex) / 2, "endY": (sy + ey) / 2},
        {"trafficType": 1, "sectionTime": ride - 3, "stationCount": 3, "lane": [{"name": "수도권 3호선", "subwayCode": 3}],
         "startName": "환승역", "endName": "도착역", "startX": (sx + ex) / 2, "startY": (sy + ey) / 2, "endX": ex, "endY": ey},
        {"trafficType": 3, "sectionTime": 4}]}
    paths = [subway] if kind == "1" else [bus] if kind == "2" else [subway, bus, mixed]
    if d > 50000 and kind == "0":
        paths.append({"info": {"totalTime": int(d / 1500) + 20, "totalDistance": int(d), "payment": 23700}, "subPath": [
            {"trafficType": 3, "sectionTime": 10}, {"trafficType": 4, "sectionTime": int(d / 1500), "stationCount": 2,
             "lane": [{"name": "KTX"}], "startName": "서울역", "endName": "대천역", "startX": sx, "startY": sy, "endX": ex, "endY": ey},
            {"trafficType": 3, "sectionTime": 10}]})
    return {"result": {"path": paths}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/v2/local/search/keyword.json":
            if self.headers.get("Authorization") != "KakaoAK test":
                return self.send({"errorType": "AccessDeniedError", "message": "wrong appKey"}, 401)
            return self.send({"documents": keyword(q), "meta": {}})
        if u.path == "/v1/directions":
            return self.send(directions(q))
        if u.path == "/v1/api/searchPubTransPathT":
            return self.send(odsay(q))
        if u.path == "/__stats":
            with LOCK:
                return self.send(STATS)
        if u.path == "/__reset":
            with LOCK:
                STATS.update({"kakao": 0, "navi": 0, "odsay": 0, "queries": []})
            return self.send({"ok": True})
        self.send({"error": "not found"}, 404)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
