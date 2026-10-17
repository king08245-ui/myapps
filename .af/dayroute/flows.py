# 하루동선 폰 화면 자동 검수 흐름 — 시험용 API(카카오·ODsay 흉내, test/mock_api.py)와 Worker 코드(local.mjs)가 떠 있어야 함
#   API: http://127.0.0.1:8788 (접속 코드 1234)   흉내 서버: http://127.0.0.1:8790
import json
import math
import os
import re
import subprocess
import urllib.request

API = "http://127.0.0.1:8788"
MOCK = "http://127.0.0.1:8790"
HERE = os.path.dirname(os.path.abspath(__file__))
PC_FAVS = "/home/claude/dayroute/src/favorites.json"   # PC판에서 가져온 실제 즐겨찾기 파일(가져오기 시험용, 공개하지 않음)
if not os.path.exists(PC_FAVS):   # 없으면 같은 모양으로 만든 시험용 파일(시험용 가짜 API로 짠 일정 2개)
    PC_FAVS = os.path.join(HERE, "test", "pc_favorites_sample.json")


def mock_stats(reset=False):
    with urllib.request.urlopen(MOCK + ("/__reset" if reset else "/__stats"), timeout=5) as r:
        return json.load(r)


def connect(page, code="1234"):
    """설정을 폰 저장소에 넣고 다시 열기 (처음 설정 화면을 건너뜀)"""
    page.evaluate("([s, c]) => { const d = JSON.parse(localStorage.getItem('dayroute:v1') || '{}'); d.server = s; d.code = c; localStorage.setItem('dayroute:v1', JSON.stringify(d)); }", [API, code])
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 연결됨')", timeout=10000)


def plan_now(page, text=None, transit=False):
    if text is not None:
        page.fill("#req", text)
    page.click("#mTransit" if transit else "#mCar")
    page.click("#go")
    page.wait_for_function("!document.getElementById('go').disabled", timeout=30000)
    err = page.evaluate("document.getElementById('status').classList.contains('err') ? document.getElementById('status').textContent : ''")
    return err


def stop_names(page):
    return page.evaluate("[...document.querySelectorAll('#timeline .stop:not(.start):not(.end) .card h3 a')].map(a => a.textContent)")


def stop_count(page):
    return page.locator("#timeline .stop:not(.start):not(.end)").count()


def flow_first_run_setup(page, shot):
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 설정 필요')", timeout=10000)
    assert page.is_visible("#setup"), "처음 열었는데 서버 설정 칸이 안 보임"
    assert "처음 한 번" in page.inner_text("#setupMsg"), "처음 설정 안내가 없음"
    page.fill("#srv", API)
    page.fill("#code", "틀린코드")       # 한글 코드도 보낼 수 있어야 함
    page.click("#setSave")
    page.wait_for_function("document.getElementById('setupMsg').textContent.includes('접속 코드가 맞지 않')", timeout=10000)
    page.fill("#code", "1234")
    page.click("#setSave")
    page.wait_for_function("document.getElementById('setup').hidden", timeout=10000)
    assert "서버 연결됨" in page.inner_text("#keys"), "맞는 코드인데 연결됨 표시가 없음"
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 연결됨')", timeout=10000)
    assert not page.is_visible("#setup"), "새로고침하자 설정을 다시 물어봄(저장 안 됨)"


def flow_make_plan_car(page, shot):
    connect(page)
    err = plan_now(page)
    assert not err, f"일정 짜기 실패: {err}"
    names = stop_names(page)
    assert len(names) == 4, f"헬스장·점심·전시·카페 4곳이 아님: {names}"
    assert not any("주차장" in n for n in names), f"'주차되는 헬스장'에 주차장이 뽑힘: {names}"
    assert "키워드로 해석한 요청" in page.inner_text("#parsed"), "해석한 요청 표시가 없음"
    summ = page.inner_text("#summary")
    assert re.search(r"10:00\s*–\s*\d\d:\d\d", summ), f"하루 일정 시각이 없음: {summ}"
    assert page.locator("#timeline .leg .pill", has_text="자가용").count() >= 1, "자가용 구간 표시가 없음"
    assert page.locator("#timeline .pill.no", has_text="주차 확인").count() >= 1, "자가용인데 '주차 확인' 표시가 없음"
    page.evaluate("document.getElementById('planArea').scrollIntoView({block: 'start'})")
    shot("plan")


def flow_transit_and_route_options(page, shot):
    connect(page)
    err = plan_now(page, transit=True)
    assert not err, f"대중교통 일정 실패: {err}"
    assert page.locator("#timeline .line", has_text="5호선").count() >= 1, "지하철 노선 표시가 없음"
    btn = page.locator("#timeline button", has_text="다른 경로").first
    btn.click()
    rows = page.locator("#timeline .opts li")
    assert rows.count() == 3, f"다른 경로 목록이 3줄이 아님: {rows.count()}"
    rows.nth(1).click()
    page.wait_for_function("!document.getElementById('go').disabled && document.querySelector('#timeline .opts li.cur')", timeout=30000)
    assert "472번" in page.inner_text("#timeline"), "버스 경로를 골랐는데 472번이 안 보임"
    assert page.locator("#timeline .opts li.cur").first.get_attribute("data-i") == "1", "고른 경로가 '지금 경로'로 표시되지 않음"
    page.evaluate("document.querySelector('#timeline .opts').scrollIntoView({block: 'center'})")
    shot("transit")


def flow_edit_stay_move_remove(page, shot):
    connect(page)
    assert not plan_now(page)
    first = page.locator("#timeline .stop:not(.start) .card").first
    before = first.inner_text()
    first.locator("button[aria-label='30분 늘리기']").click()
    page.wait_for_function("!document.getElementById('go').disabled", timeout=30000)
    v = page.locator("#timeline .stop:not(.start) .card").first.locator(".hrs input").input_value()
    assert v == "1.5", f"머무는 시간이 1.5시간이 아님: {v} (전: {before[:40]})"
    names = stop_names(page)
    page.locator("#timeline .stop:not(.start) .card").first.locator("button.more").click()
    page.locator("#timeline .stop:not(.start) .card").first.locator("button[aria-label='순서 뒤로']").click()
    page.wait_for_function("!document.getElementById('go').disabled", timeout=30000)
    after = stop_names(page)
    assert after[0] == names[1] and after[1] == names[0], f"순서 바꾸기가 안 됨: {names} → {after}"
    n = stop_count(page)
    page.locator("#timeline .stop:not(.start) .card").first.locator("button.more").click()
    page.locator("#timeline .stop:not(.start) .card").first.locator("button", has_text="빼기").click()
    page.wait_for_function(f"!document.getElementById('go').disabled && document.querySelectorAll('#timeline .stop:not(.start):not(.end)').length === {n - 1}", timeout=30000)
    assert stop_names(page)[0] == names[0], "빼기 뒤 남은 장소가 그대로가 아님"


def flow_replace_place(page, shot):
    connect(page)
    assert not plan_now(page)
    old = stop_names(page)[0]
    page.locator("#timeline .stop:not(.start) .card").first.locator("button", has_text="바꾸기").click()
    assert page.is_visible("#searchbar"), "바꾸기를 눌렀는데 검색 칸이 안 보임"
    assert "바꾸기" in page.inner_text("#target"), "무엇을 바꾸는지 표시가 없음"
    page.wait_for_selector("#results li .use", timeout=15000)
    pick = page.locator("#results li .rname").nth(1).inner_text()
    page.locator("#results li .use").nth(1).click()
    page.wait_for_function("!document.getElementById('go').disabled", timeout=30000)
    page.wait_for_timeout(300)
    assert stop_names(page)[0] == pick, f"고른 곳({pick})으로 바뀌지 않음: {stop_names(page)[0]}"
    card = page.locator("#timeline .stop:not(.start) .card").first
    assert card.locator(".pill.ok", has_text="직접 고름").count() == 1, "'직접 고름' 표시가 없음"
    assert not page.is_visible("#searchbar"), "고른 뒤에도 검색 칸이 남아 있음"
    shot("replaced")
    card.locator("button.more").click()
    card.locator("button", has_text="자동 추천으로").click()
    page.wait_for_function("!document.getElementById('go').disabled", timeout=30000)
    assert stop_names(page)[0] == old, f"자동 추천으로 돌아가지 않음: {stop_names(page)[0]} (원래 {old})"


def flow_add_place(page, shot):
    connect(page)
    assert not plan_now(page)
    n = stop_count(page)
    page.locator("#timeline .addbtn").first.click()
    assert page.is_visible("#searchbar"), "추가를 눌렀는데 검색 칸이 안 보임"
    page.fill("#q", "서점")
    page.click("#qgo")
    page.wait_for_selector("#results li .use", timeout=15000)
    page.locator("#results li .use").first.click()
    page.wait_for_function(f"!document.getElementById('go').disabled && document.querySelectorAll('#timeline .stop:not(.start):not(.end)').length === {n + 1}", timeout=30000)
    first_label = page.locator("#timeline .stop:not(.start) .card").first.locator(".pill").first.inner_text()
    assert first_label == "서점", f"출발 다음에 서점이 들어가지 않음: {first_label}"


def flow_leg_mode_select(page, shot):
    connect(page)
    assert not plan_now(page)
    page.locator("#timeline select.lmode").first.select_option("walk")
    page.wait_for_function("!document.getElementById('go').disabled", timeout=30000)
    first_leg = page.locator("#timeline li.leg:not(.addrow)").first.inner_text()
    assert "도보" in first_leg, f"첫 구간을 도보로 바꿨는데 그대로: {first_leg[:60]}"
    assert page.locator("#timeline select.lmode").first.input_value() == "walk", "고른 이동수단이 유지되지 않음"


def flow_favorites_save_load_delete(page, shot):
    connect(page)
    assert not plan_now(page)
    page.fill("#favName", "토요일 코스")
    page.click("#favSave")
    assert page.locator("#favList .fav", has_text="토요일 코스").count() == 1, "즐겨찾기 목록에 안 보임"
    page.fill("#req", "사우나, 영화, 저녁")
    assert not plan_now(page)
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 연결됨')", timeout=10000)
    row = page.locator("#favList .fav", has_text="토요일 코스")
    assert row.count() == 1, "새로고침 후 즐겨찾기가 사라짐"
    row.locator("button", has_text="불러오기").click()
    assert page.input_value("#req").startswith("주차되는 헬스장"), "불러온 즐겨찾기의 요청 문장이 아님"
    assert stop_count(page) == 4, "불러온 즐겨찾기의 장소 수가 다름"
    page.wait_for_timeout(900)   # 불러온 뒤 시간표로 부드럽게 스크롤하는 중에 누르지 않게
    d = row.locator("button.x")
    d.click()
    assert d.inner_text() == "한 번 더", "삭제 확인 단계가 없음(실수로 지울 수 있음)"
    page.wait_for_timeout(700)   # '한 번 더'를 보고 다시 누름(연달아 두 번 눌린 것은 확인으로 치지 않음)
    d.click()
    assert page.locator("#favList .fav", has_text="토요일 코스").count() == 0, "두 번 눌렀는데 지워지지 않음"


def flow_import_pc_favorites(page, shot):
    connect(page)
    page.set_input_files("#importFile", PC_FAVS)   # 확인 창은 검수 도구가 자동으로 '예'를 누름
    page.wait_for_function("document.querySelectorAll('#favList .fav').length === 2", timeout=5000)
    assert "2개를 가져왔어요" in page.inner_text("#status"), "가져오기 결과 안내가 없음"
    page.locator("#favList .fav").nth(0).locator("button", has_text="불러오기").click()
    assert stop_count(page) >= 4, "PC판 즐겨찾기를 열었는데 시간표가 안 나옴"
    assert page.locator("#timeline li.leg .pill", has_text="자가용").count() >= 1, "PC판 경로(자가용 구간)가 안 보임"
    page.reload()
    page.wait_for_function("document.querySelectorAll('#favList .fav').length === 2", timeout=10000)


def flow_backup_roundtrip(page, shot):
    connect(page)
    assert not plan_now(page)
    page.fill("#favName", "백업 시험")
    page.click("#favSave")
    with page.expect_download() as dl:
        page.click("#exportBtn")
    path = dl.value.path()
    data = json.load(open(path, encoding="utf-8"))
    assert data.get("app") == "dayroute:v1" and len(data["data"]["favs"]) == 1, "백업 파일 내용이 맞지 않음"
    assert "1234" not in open(path, encoding="utf-8").read(), "백업 파일에 접속 코드가 들어감"
    page.evaluate("localStorage.clear()")
    page.reload()
    page.set_input_files("#importFile", path)
    page.wait_for_function("document.querySelectorAll('#favList .fav').length === 1", timeout=5000)
    assert page.locator("#favList .fav", has_text="백업 시험").count() == 1, "백업에서 즐겨찾기를 되살리지 못함"


def flow_last_plan_restored(page, shot):
    connect(page)
    assert not plan_now(page, "박물관 2시간, 점심, 카페, 저녁")
    names = stop_names(page)
    page.reload()
    page.wait_for_selector("#timeline .stop .card h3 a", timeout=8000)
    assert stop_names(page) == names, "다시 열었을 때 지난번 일정이 사라짐"
    assert "지난번에 짠 일정" in page.inner_text("#status"), "지난번 일정이라는 안내가 없음"
    assert page.input_value("#req") == "박물관 2시간, 점심, 카페, 저녁", "입력한 요청 문장이 유지되지 않음"


def flow_current_location_origin(page, shot):
    connect(page)
    page.context.grant_permissions(["geolocation"])
    page.context.set_geolocation({"latitude": 37.5443, "longitude": 126.9516})
    page.click("#hereBtn")
    page.wait_for_function("document.getElementById('from').value === '현재 위치'", timeout=8000)
    assert not plan_now(page)
    start = page.locator("#timeline .stop.start .card").inner_text()
    assert "현재 위치" in start, f"현재 위치에서 출발하지 않음: {start}"


def flow_errors_and_misses(page, shot):
    connect(page)
    err = plan_now(page, "1시간")
    assert "활동을 찾지 못했어요" in err, f"알아들을 수 없는 요청 안내가 없음: {err}"
    err = plan_now(page, "없는가게이름 1시간, 카페")
    assert not err, f"없는 가게가 섞인 요청이 통째로 실패함: {err}"
    miss = page.locator("#timeline .card", has_text="찾지 못함")
    assert miss.count() == 1, "못 찾은 곳 카드가 없음"
    assert miss.locator("button", has_text="바꾸기").count() == 1, "못 찾은 곳에 바꾸기 버튼이 없음"
    page.evaluate("([s]) => { const d = JSON.parse(localStorage.getItem('dayroute:v1')); d.server = s; localStorage.setItem('dayroute:v1', JSON.stringify(d)); }", ["http://127.0.0.1:9"])
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('연결되지 않음')", timeout=15000)
    assert page.is_visible("#setup") and "연결하지 못했어요" in page.inner_text("#setupMsg"), "서버에 못 붙을 때 안내가 없음"
    assert stop_count(page) >= 1, "서버가 안 될 때 지난 일정까지 사라짐"


def flow_demo_without_server(page, shot):
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 설정 필요')", timeout=10000)
    page.click("#demoBtn")
    page.wait_for_selector("#timeline .stop .card h3 a", timeout=5000)
    assert stop_count(page) == 4, "예시 일정이 안 나옴"
    page.locator("#timeline .stop:not(.start) .card").first.locator("button", has_text="바꾸기").click()
    assert "예시 일정" in page.inner_text("#status"), "예시 일정에서 바꾸기를 누를 때 안내가 없음"


def flow_image_export(page, shot):
    connect(page)
    assert not plan_now(page)
    with page.expect_download() as dl:
        page.click("#imgSave")
    assert dl.value.suggested_filename.endswith(".png"), f"이미지 파일이 아님: {dl.value.suggested_filename}"


def flow_api_call_budget(page, shot):
    connect(page)
    mock_stats(reset=True)
    err = plan_now(page, "점심, 저녁, 점심, 저녁, 점심, 저녁, 점심, 저녁, 점심, 저녁")
    assert not err, f"식사 10번 요청이 실패함: {err}"
    st = mock_stats()
    calls = st["kakao"] + st["navi"] + st["odsay"]
    assert calls <= 48, f"한 번에 바깥 API를 {calls}번 불러 무료 한도(50)를 넘을 수 있음"
    assert page.locator("#timeline li.leg:not(.addrow)").count() >= 5, "이동 계산이 빠짐"


def flow_small_screen_layout(page, shot):
    page.set_viewport_size({"width": 320, "height": 640})
    connect(page)
    assert not plan_now(page, transit=True)
    page.locator("#timeline button", has_text="다른 경로").first.click()
    ok = page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    assert ok, "작은 화면에서 가로 스크롤이 생김"


def flow_korean_access_code(page, shot):
    """접속 코드를 한글로 정해도(예: 하루동선) 연결·일정 짜기가 돼야 함 — 시험 서버 8789는 코드가 '하루동선'"""
    page.evaluate("() => { localStorage.setItem('dayroute:v1', JSON.stringify({server: 'http://127.0.0.1:8789', code: '하루동선'})); }")
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 연결됨')", timeout=10000)
    assert not plan_now(page), "한글 접속 코드로 일정 짜기가 안 됨"
    assert stop_count(page) == 4


# ---------- 독립 검수(10/11)·실제 키 시험에서 나온 문제의 재발 방지 ----------
def idle(page, t=30000):
    page.wait_for_function("!document.getElementById('go').disabled", timeout=t)
    page.wait_for_timeout(150)


def card(page, n):
    return page.locator("#timeline .stop:not(.start):not(.end) .card").nth(n)


def more(page, n, label):
    c = card(page, n)
    c.locator("button.more").click()
    c.locator("button", has_text=label).click()


def status(page):
    return page.evaluate("(() => { const s = document.getElementById('status'); return (s.classList.contains('err') ? 'ERR: ' : '') + s.textContent; })()")


def saved(page):
    return page.evaluate("JSON.parse(localStorage.getItem('dayroute:v1') || '{}')")


def fav_stops(page):
    plan = saved(page)["favs"][0]["state"]["plan"]
    return [i["place"]["name"] for i in plan["items"] if i["type"] == "stop"]


def flow_favorite_is_a_snapshot(page, shot):
    """즐겨찾기는 저장한 순간의 복사본: 저장 뒤 화면에서 고쳐도, 불러와서 고쳐도 저장본은 그대로"""
    connect(page)
    assert not plan_now(page)
    names = stop_names(page)
    page.fill("#favName", "토요일")
    page.click("#favSave")
    more(page, 1, "빼기")
    idle(page)
    assert stop_count(page) == len(names) - 1, "빼기가 안 됨"
    assert fav_stops(page) == names, "저장한 뒤 화면에서 고쳤더니 즐겨찾기도 바뀜"
    page.locator("#favList .fav").first.locator("button", has_text="불러오기").click()
    page.wait_for_timeout(900)
    assert stop_names(page) == names, f"불러온 즐겨찾기가 저장한 일정과 다름: {stop_names(page)}"
    acts = page.inner_text("#parsed").count("→") + 1
    assert acts == len(names), f"불러온 뒤 해석 줄({acts}곳)과 시간표({len(names)}곳)가 다름"
    card(page, len(names) - 1).locator("button[aria-label='30분 늘리기']").click()   # 마지막 곳 고치기 — 오류 없이 돼야 함
    idle(page)
    assert not status(page).startswith("ERR"), f"불러온 즐겨찾기를 고치다 오류: {status(page)}"
    card(page, 0).locator("button", has_text="바꾸기").click()
    page.wait_for_selector("#results li .use", timeout=15000)
    page.locator("#results li .use").nth(1).click()
    idle(page)
    assert fav_stops(page) == names, "불러와서 고쳤더니 즐겨찾기 저장본이 바뀜"


def flow_failed_edit_changes_nothing(page, shot):
    """신호가 끊겨 고치기가 실패하면 일정·상태는 그대로 — 다시 눌렀을 때 그 한 곳만 빠져야 함"""
    connect(page)
    assert not plan_now(page)
    names = stop_names(page)
    page.context.set_offline(True)
    more(page, 1, "빼기")
    idle(page)
    assert status(page).startswith("ERR"), "신호 없이 고쳤는데 오류 안내가 없음"
    assert stop_names(page) == names, "실패했는데 시간표가 바뀜"
    assert page.evaluate("plan.acts.length") == len(names), "실패했는데 활동 목록이 바뀜(다음 고치기가 엉뚱하게 됨)"
    page.context.set_offline(False)
    page.wait_for_timeout(300)
    more(page, 1, "빼기")
    idle(page)
    after = stop_names(page)
    assert after == names[:1] + names[2:], f"다시 빼기를 눌렀더니 엉뚱한 곳이 빠짐: {names} → {after}"


def flow_twelve_limit_add(page, shot):
    """12곳 일정에서 '여기에 추가' → 바로 안내하고 일정은 그대로, 그 뒤 고치기도 정상"""
    connect(page)
    txt = ", ".join(["정독도서관", "교보문고 광화문점", "국립현대미술관 서울", "서울역", "카페", "공원", "서점", "박물관", "미술관", "영화", "사우나", "카페"])
    assert not plan_now(page, txt)
    assert stop_count(page) == 12, f"12곳 일정이 아님: {stop_count(page)}"
    page.locator("#timeline .addbtn").first.click()
    assert "12곳까지" in status(page), f"12곳에서 추가할 때 안내가 없음: {status(page)}"
    assert not page.is_visible("#searchbar"), "더할 수 없는데 검색 칸이 열림"
    names = stop_names(page)
    more(page, 5, "빼기")
    idle(page)
    after = stop_names(page)
    assert after == names[:5] + names[6:], f"6번째를 뺐는데 결과가 다름: {names} → {after}"


def flow_double_tap_counts_once(page, shot):
    """계산이 늦을 때(1.5초) '빼기'를 두 번 눌러도 한 곳만 · ★저장 두 번은 하나만 · 삭제를 연달아 두 번은 지우지 않음"""
    connect(page)
    assert not plan_now(page)
    names = stop_names(page)
    page.evaluate("""() => { const f = window.fetch;
        window.fetch = (u, o) => String(u).includes('/api/plan') ? new Promise(r => setTimeout(r, 1500)).then(() => f(u, o)) : f(u, o); }""")
    c = card(page, 1)
    c.locator("button.more").click()
    rm = c.locator("button", has_text="빼기")
    rm.click()
    page.wait_for_timeout(120)
    rm.dispatch_event("click")   # 손가락이 한 번 더 닿은 상황(화면 잠금과 상관없이 버튼 동작 자체를 확인)
    page.wait_for_timeout(2000)
    idle(page)
    assert stop_names(page) == names[:1] + names[2:], f"두 번 눌렀더니 두 곳이 빠짐: {names} → {stop_names(page)}"
    page.fill("#favName", "중복 시험")
    page.click("#favSave")
    page.click("#favSave")
    assert page.locator("#favList .fav", has_text="중복 시험").count() == 1, "★저장을 두 번 눌렀더니 같은 즐겨찾기가 두 개"
    d = page.locator("#favList .fav", has_text="중복 시험").locator("button.x")
    d.click()
    page.wait_for_timeout(100)
    d.click()
    assert page.locator("#favList .fav", has_text="중복 시험").count() == 1, "삭제를 연달아 두 번 눌렀더니 확인 없이 지워짐"


def flow_kind_words_search_what_was_written(page, shot):
    """'필라테스·브런치·기념관'은 헬스장·백반집·미술관이 아니라 적은 말로 근처에서 찾음 · '1시간 30분'은 90분"""
    connect(page)
    mock_stats(reset=True)
    assert not plan_now(page, "필라테스 1시간, 브런치, 기념관")
    qs = mock_stats()["queries"]
    for w in ("필라테스", "브런치", "기념관"):
        assert any(w in q for q in qs), f"'{w}'로 찾지 않음: {qs}"
    assert not any(q in ("헬스장", "백반", "미술관 박물관") for q in qs), f"적은 말 대신 다른 말로 찾음: {qs}"
    labels = page.evaluate("[...document.querySelectorAll('#timeline .stop:not(.start) .meta .pill:first-child')].map(x => x.textContent)")
    assert labels[:3] == ["필라테스", "브런치", "기념관"], f"시간표의 활동 이름이 적은 말과 다름: {labels}"
    assert not plan_now(page, "전시 1시간 30분, 카페")
    v = card(page, 0).locator(".hrs input").input_value()
    assert v == "1.5", f"'1시간 30분'이 1.5시간이 아님: {v}"


def flow_reconnects_when_signal_returns(page, shot):
    """열 때 서버에 못 붙었어도 신호가 돌아오면 설정을 다시 넣지 않고 일정 짜기가 됨 · 오프라인으로 열면 설정 칸을 들이밀지 않음"""
    connect(page)
    assert not plan_now(page)
    page.route("**/api/status", lambda r: r.abort())
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('연결되지 않음')", timeout=15000)
    page.unroute("**/api/status")
    err = plan_now(page)
    assert not err, f"신호가 돌아왔는데 일정 짜기가 안 됨: {err}"
    assert "서버 연결됨" in page.inner_text("#keys"), "다시 연결됐다는 표시가 없음"
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
    page.context.set_offline(True)
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('인터넷 연결 없음')", timeout=15000)
    assert not page.is_visible("#setup"), "신호가 없을 뿐인데 서버 설정 칸이 열림"
    assert stop_count(page) >= 1, "오프라인으로 열었더니 지난 일정이 안 보임"
    page.context.set_offline(False)
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 연결됨')", timeout=15000)


def flow_keeps_other_apps_offline_copy(page, shot):
    """같은 주소(king08245-ui.github.io)의 다른 앱(채널 맛집수첩) 저장본을 지우지 않아야 함 — 이 앱의 옛 저장본만 지움"""
    page.evaluate("""async () => { await caches.open('channel-matjip-v9'); await caches.open('dayroute-v0');
        for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister(); }""")
    page.reload()
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
    page.wait_for_timeout(300)
    keys = page.evaluate("caches.keys()")
    assert "channel-matjip-v9" in keys, f"채널 맛집수첩의 오프라인 저장본을 지움: {keys}"
    assert "dayroute-v0" not in keys, f"이 앱의 옛 저장본이 남음: {keys}"


def flow_draft_survives_reopen(page, shot):
    """지난 일정이 있어도, 그 뒤 새로 적던 요청·출발지·시각·이동수단은 다시 열었을 때 그대로"""
    connect(page)
    assert not plan_now(page, "카페, 공원")
    page.fill("#req", "광화문 교보문고 2시간, 근처 국밥집 점심")
    page.fill("#from", "서울역")
    page.fill("#start", "13:30")
    page.click("#mTransit")
    page.click("h1")   # 칸을 벗어나면 저장
    page.wait_for_timeout(200)
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 연결됨')", timeout=10000)
    assert page.input_value("#req").startswith("광화문 교보문고"), f"새로 적던 요청이 지난 일정 것으로 돌아감: {page.input_value('#req')}"
    assert page.input_value("#from") == "서울역" and page.input_value("#start") == "13:30", "출발지·시각이 돌아감"
    assert page.get_attribute("#mTransit", "aria-pressed") == "true", "이동수단이 돌아감"
    assert stop_count(page) == 2, "지난 일정(시간표)은 그대로 보여야 함"


def flow_demo_then_real_plan(page, shot):
    """서버가 연결된 채로 '예시 일정 보기'를 눌러도, 그다음 '일정 짜기'와 고치기가 정상"""
    connect(page)
    page.click("#setBtn")
    page.click("#demoBtn")
    page.wait_for_selector("#timeline .stop .card h3 a", timeout=5000)
    err = plan_now(page, "카페, 공원")
    assert not err, f"예시를 본 뒤 일정 짜기가 막힘: {err}"
    assert stop_count(page) == 2, "새 일정이 안 나옴"
    card(page, 0).locator("button[aria-label='30분 늘리기']").click()
    idle(page)
    assert not status(page).startswith("ERR"), f"예시를 본 뒤 고치기가 막힘: {status(page)}"


def flow_wrong_code_is_slow(page, shot):
    """접속 코드를 마구 넣어 보며 맞히지 못하게: 틀린 코드는 1초 가까이 늦게, 맞는 코드는 바로"""
    t = page.evaluate("""async ([api]) => { const go = async c => { const t0 = performance.now();
        await fetch(api + '/api/status', {headers: {'x-access-code': c}}); return performance.now() - t0; };
        return [await go('0000'), await go('1234')]; }""", [API])
    assert t[0] >= 900, f"틀린 코드에 바로 답함({t[0]:.0f}ms) — 마구 맞혀 볼 수 있음"
    assert t[1] < 600, f"맞는 코드인데 늦음({t[1]:.0f}ms)"


def flow_busy_server_message(page, shot):
    """계산이 서버 한도로 끊겨도(응답 없이 연결이 끊김) '서버 주소를 확인하세요'가 아니라 '다시 눌러 주세요'"""
    connect(page)
    assert not plan_now(page)
    page.route("**/api/plan", lambda r: r.abort())
    err = plan_now(page, "카페, 공원")
    assert "한 번 더" in err, f"서버는 살아 있는데 주소를 확인하라고 함: {err}"
    page.unroute("**/api/plan")


def flow_edits_reuse_routes(page, shot):
    """고칠 때는 바뀐 곳 앞뒤 구간만 새로 계산(무료 한도·ODsay 하루 횟수 아낌): 머무는 시간만 바꾸면 바깥 호출 0번"""
    connect(page)
    assert not plan_now(page, transit=True)
    mock_stats(reset=True)
    card(page, 0).locator("button[aria-label='30분 늘리기']").click()
    idle(page)
    st = mock_stats()
    assert st["kakao"] + st["navi"] + st["odsay"] == 0, f"머무는 시간만 바꿨는데 바깥 API를 다시 부름: 카카오 {st['kakao']} · 길찾기 {st['navi']} · ODsay {st['odsay']}"
    card(page, 0).locator("button", has_text="바꾸기").click()
    page.wait_for_selector("#results li .use", timeout=15000)
    mock_stats(reset=True)
    page.locator("#results li .use").nth(1).click()
    idle(page)
    st = mock_stats()
    assert st["odsay"] <= 2, f"한 곳을 바꿨는데 대중교통 길찾기를 {st['odsay']}번 부름(앞뒤 2구간이면 충분)"


def flow_add_asks_what_to_find(page, shot):
    """'여기에 추가'는 '못 찾았어요'가 아니라 무엇을 찾을지 묻고, '서점'은 이름만 비슷한 안경원보다 서점이 먼저"""
    connect(page)
    assert not plan_now(page)
    page.locator("#timeline .addbtn").first.click()
    hint = page.inner_text("#results")
    assert "무엇을 찾을지" in hint and "찾지 못했어요" not in hint, f"찾기 전인데 안내가 이상함: {hint}"
    page.fill("#q", "서점")
    page.click("#qgo")
    page.wait_for_selector("#results li .use", timeout=15000)
    first = page.locator("#results li .rmeta").first.inner_text()
    assert "안경" not in first, f"'서점' 검색 맨 위에 안경원이 나옴: {first}"
    assert "주차장" not in page.inner_text("#results"), "장소 추가 검색에 주차장이 섞임"
    assert not plan_now(page, "서점 1시간, 카페")
    assert stop_names(page)[0] != "서점옆 안경원", f"'서점' 일정에 안경원이 뽑힘: {stop_names(page)}"


def flow_last_stop_cannot_be_removed(page, shot):
    """한 곳짜리 일정에서 빼기 → 요청 문장으로 다시 짜지 말고 안내만"""
    connect(page)
    assert not plan_now(page, "카페")
    more(page, 0, "빼기")
    assert "마지막 한 곳" in status(page), f"마지막 곳을 빼려 할 때 안내가 없음: {status(page)}"
    assert stop_count(page) == 1


# ---------- 즐겨찾기 장소 (10/17): 집·도서관·자주 가는 카페 ----------
HOME = {"name": "집", "x": "126.9562", "y": "37.5469", "address": "서울 마포구 마포대로 195", "category": "", "url": ""}
LIB = {"name": "마포중앙도서관", "x": "126.9087", "y": "37.5636", "address": "서울 마포구 성미산로 128",
       "category": "사회,공공기관 > 도서관 > 공공도서관", "url": "http://place.map.kakao.com/771"}
CAFE = {"name": "스타벅스 공덕역점", "x": "126.952", "y": "37.5431", "address": "서울 마포구 마포대로 92",
        "category": "음식점 > 카페 > 커피전문점 > 스타벅스", "url": "http://place.map.kakao.com/772"}
STUB = open(os.path.join(HERE, "test", "kakao_stub.js"), encoding="utf-8").read()
WORKER = os.path.join(HERE, "worker", "worker.js")


def places(page, *items):
    """즐겨찾기 장소를 폰 저장소에 바로 넣기 — items: (부를 이름, 장소). 다음 connect()의 새로고침부터 보임"""
    pl = [{"id": f"p{i}", "alias": a, "place": p, "savedAt": "2026-10-17T00:00:00Z"} for i, (a, p) in enumerate(items)]
    page.evaluate("(pl) => { const d = JSON.parse(localStorage.getItem('dayroute:v1') || '{}'); d.places = pl; localStorage.setItem('dayroute:v1', JSON.stringify(d)); }", pl)


def kakao_stub(page):
    """카카오 지도 SDK를 검수용 흉내(test/kakao_stub.js)로 — 서버 상태의 지도 키를 'test'로 바꿔 앱이 SDK를 부르게 함"""
    def status(route):
        r = route.fetch()
        d = r.json()
        d["jsKey"] = "test"
        route.fulfill(response=r, body=json.dumps(d))
    page.route("**/api/status", status)
    page.route("https://dapi.kakao.com/**", lambda r: r.fulfill(status=200, content_type="text/javascript; charset=utf-8", body=STUB))


def plan_bodies(page):
    """폰이 /api/plan으로 보낸 요청 내용을 모음"""
    got = []
    page.on("request", lambda r: got.append(json.loads(r.post_data)) if r.method == "POST" and r.url.endswith("/api/plan") else None)
    return got


def km(a, b):
    r = math.pi / 180
    ay, by, ax, bx = float(a["y"]), float(b["y"]), float(a["x"]), float(b["x"])
    s = math.sin((by - ay) * r / 2) ** 2 + math.cos(ay * r) * math.cos(by * r) * math.sin((bx - ax) * r / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(s))


def server_parse(samples):
    """서버(worker.js)의 ruleParse를 node로 돌린 결과"""
    src = open(WORKER, encoding="utf-8").read()
    code = src[src.index("const CAT = {"):src.index("/* ---------- 식사 가격대")]
    js = code + "\nconst isMeal = c => c === 'lunch' || c === 'dinner';\nprocess.stdout.write(JSON.stringify(JSON.parse(process.env.SAMPLES).map(ruleParse)));"
    out = subprocess.run(["node", "-e", js], env={**os.environ, "SAMPLES": json.dumps(samples, ensure_ascii=False)}, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def flow_place_add_by_search_then_start_there(page, shot):
    """'＋ 집·자주 가는 곳 저장' → 이름 '집' + '공덕래미안' 찾기 → 저장 → 출발지 칩 '집' → 저장한 좌표에서 출발(이름으로 다시 찾지 않음)"""
    kakao_stub(page)
    connect(page)
    page.wait_for_function("!!(window.kakao && kakao.maps && kakao.maps.services)", timeout=10000)
    bodies = plan_bodies(page)
    page.click("#placeChips .addchip")
    assert page.is_visible("#plAdd"), "장소 추가 칸이 안 열림"
    page.fill("#plAlias", "집")
    page.fill("#plQ", "공덕래미안")
    page.click("#plGo")
    page.wait_for_selector("#plResults li .use", timeout=8000)
    assert "공덕래미안5차아파트" in page.inner_text("#plResults"), f"찾은 곳이 안 보임: {page.inner_text('#plResults')}"
    assert "주차장" not in page.inner_text("#plResults"), "장소 찾기 결과에 공영주차장이 섞임"
    shot("place-search")
    page.locator("#plResults li .use").first.click()
    assert page.locator("#plList .place", has_text="집").count() == 1, "저장한 장소가 목록에 없음"
    assert "저장했어요" in page.inner_text("#plMsg"), f"저장 안내가 없음: {page.inner_text('#plMsg')}"
    assert not page.is_visible("#plAdd"), "저장했는데 추가 칸이 그대로 열려 있음"
    chip = page.locator("#placeChips button", has_text="집")
    chip.click()
    assert page.input_value("#from") == "집", "칩을 눌렀는데 출발지가 집이 아님"
    assert chip.get_attribute("aria-pressed") == "true", "고른 출발지 칩이 표시되지 않음"
    mock_stats(reset=True)
    assert not plan_now(page, "카페, 공원")
    start = page.locator("#timeline .stop.start .card").inner_text()
    assert "집" in start, f"집에서 출발하지 않음: {start}"
    o = bodies[-1].get("originLL") or {}
    assert abs(o.get("x", 0) - 126.9562) < 1e-6 and abs(o.get("y", 0) - 37.5469) < 1e-6, f"저장한 좌표로 보내지 않음: {o}"
    assert "집" not in mock_stats()["queries"], "출발지 '집'을 이름으로 다시 찾음(엉뚱한 '집'이라는 가게가 나올 수 있음)"
    page.evaluate("document.getElementById('placesPanel').scrollIntoView({block: 'start'})")
    shot("places-panel")
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 연결됨')", timeout=10000)
    assert page.locator("#plList .place", has_text="집").count() == 1, "새로고침하자 즐겨찾기 장소가 사라짐"


def flow_place_names_in_request(page, shot):
    """요청에 저장한 이름을 적으면 그곳으로: '도서관 2시간, 점심, 단골카페 1시간, 집' → 마포중앙도서관 → 식당 → 스타벅스 공덕역점 → 집(도착)"""
    places(page, ("집", HOME), ("도서관", LIB), ("단골카페", CAFE))
    connect(page)
    bodies = plan_bodies(page)
    assert "도서관 2시간, 집" in page.inner_text("#reqNote"), f"요청 칸 아래 안내가 없음: {page.inner_text('#reqNote')}"
    page.fill("#req", "도서관 2시간, 점심, 단골카페 1시간, 집")
    shot("places-form")
    mock_stats(reset=True)
    assert not plan_now(page, "도서관 2시간, 점심, 단골카페 1시간, 집")
    names = stop_names(page)
    assert len(names) == 4 and names[0] == "마포중앙도서관" and names[2] == "스타벅스 공덕역점" and names[3] == "집", f"저장한 곳으로 짜지 않음: {names}"
    assert "도착" in card(page, 3).locator("h3").inner_text(), "맨 끝 '집'이 도착(집으로 돌아오기)이 아님"
    pills = page.evaluate("[...document.querySelectorAll('#timeline .stop:not(.start) .pill.star')].map(x => x.textContent)")
    assert pills == ["★ 도서관", "★ 단골카페", "★ 집 복귀"], f"★ 표시가 다름: {pills}"
    assert card(page, 0).locator(".hrs input").input_value() == "2", "‘도서관 2시간’이 2시간이 아님"
    qs = mock_stats()["queries"]
    assert not [q for q in qs if "도서관" in q or "단골" in q or q == "집"], f"저장한 곳을 이름으로 다시 찾음: {qs}"
    assert "키워드로 해석한 요청" in page.inner_text("#parsed"), "해석한 요청 표시가 바뀜"
    b = bodies[-1]
    assert len(b.get("acts", [])) == 4 and b["picks"]["0"]["name"] == "마포중앙도서관", "활동 목록과 저장한 곳을 함께 보내지 않음"
    assert "주차 확인" not in card(page, 0).inner_text(), "늘 가는 곳에도 '주차 확인'이 붙음"
    page.evaluate("document.getElementById('planArea').scrollIntoView({block: 'start'})")
    shot("places-plan")
    card(page, 1).locator("button[aria-label='30분 늘리기']").click()
    idle(page)
    assert stop_names(page) == names, f"머무는 시간을 고쳤더니 저장한 곳이 바뀜: {stop_names(page)}"


def flow_place_home_words(page, shot):
    """'귀가'·'집으로 복귀'·'집에 가기'는 저장한 집으로 · '집에서 출발'·맨 앞 '집'은 출발지를 집으로 · 출발지에 '도서관'만 적어도 그 좌표"""
    places(page, ("집", HOME), ("도서관", LIB))
    connect(page)
    bodies = plan_bodies(page)
    for text in ("카페, 귀가", "카페, 집으로 복귀", "카페 1시간, 집에 가기"):
        err = plan_now(page, text)
        assert not err, f"'{text}' 실패: {err}"
        names = stop_names(page)
        assert names[-1] == "집" and len(names) == 2, f"'{text}' → 집으로 끝나지 않음: {names}"
    page.fill("#from", "서울역")
    assert not plan_now(page, "집에서 출발, 도서관 3시간, 집")
    assert page.input_value("#from") == "집", "‘집에서 출발’인데 출발지 칸이 집으로 안 바뀜"
    assert "집" in page.locator("#timeline .stop.start .card").inner_text(), "집에서 출발하지 않음"
    assert stop_names(page) == ["마포중앙도서관", "집"], f"집 → 도서관 → 집이 아님: {stop_names(page)}"
    page.fill("#from", "서울역")
    assert not plan_now(page, "집, 도서관, 집")
    assert page.input_value("#from") == "집" and stop_names(page) == ["마포중앙도서관", "집"], f"맨 앞 '집'을 출발로 보지 않음: {stop_names(page)}"
    page.fill("#from", "도서관")
    assert not plan_now(page, "카페")
    assert "도서관" in page.locator("#timeline .stop.start .card").inner_text()
    o = bodies[-1].get("originLL") or {}
    assert abs(o.get("x", 0) - 126.9087) < 1e-6, f"출발지 '도서관'을 저장한 좌표로 보내지 않음: {o}"


def flow_place_near_saved(page, shot):
    """'집 근처 카페 1시간' → 저장한 집 1.2km 안의 카페 (서버가 '집'이라는 이름의 가게를 찾아 그 근처로 가지 않게)"""
    places(page, ("집", HOME))
    connect(page)
    page.fill("#from", "서울역")
    assert not plan_now(page, "집 근처 카페 1시간, 공원")
    pl = page.evaluate("plan.items.filter(i => i.type === 'stop').map(i => i.place)")
    d = km(pl[0], HOME)
    assert d < 1.3, f"집 근처가 아닌 카페: {pl[0]['name']} ({d:.2f}km)"
    assert "카페" in card(page, 0).inner_text(), "카페가 아님"
    assert card(page, 0).locator(".hrs input").input_value() == "1"


def flow_place_save_from_card_and_use_in_edit(page, shot):
    """시간표 '⋯ → ☆ 장소 저장'으로 이름 붙여 저장 → ★ 표시 · 바꾸기·여기에 추가 검색의 칩으로 저장한 곳을 넣기"""
    places(page, ("도서관", LIB))
    connect(page)
    assert not plan_now(page, "카페, 공원")
    name0 = stop_names(page)[0]
    c = card(page, 0)
    c.locator("button.more").click()
    c.locator("button", has_text="☆ 장소 저장").click()
    inp = c.locator(".ren input")
    assert inp.input_value() == name0, f"기본 이름이 장소 이름이 아님: {inp.input_value()}"
    inp.fill("단골카페")
    c.locator(".ren button", has_text="저장").click()
    assert card(page, 0).locator(".pill.star", has_text="단골카페").count() == 1, "저장한 뒤 ★ 표시가 없음"
    assert page.locator("#plList .place", has_text="단골카페").count() == 1, "즐겨찾기 장소 목록에 없음"
    card(page, 1).locator("button", has_text="바꾸기").click()
    page.wait_for_selector("#tchips button", timeout=5000)
    shot("target-chips")
    page.locator("#tchips button", has_text="도서관").click()
    idle(page)
    assert stop_names(page)[1] == "마포중앙도서관", f"칩으로 바꾸지 못함: {stop_names(page)}"
    assert card(page, 1).locator(".pill.star").count() == 1, "바꾼 곳에 ★ 표시가 없음"
    n = stop_count(page)
    page.locator("#timeline .addbtn").first.click()
    page.locator("#tchips button", has_text="단골카페").click()
    page.wait_for_function(f"!document.getElementById('go').disabled && document.querySelectorAll('#timeline .stop:not(.start):not(.end)').length === {n + 1}", timeout=30000)
    assert stop_names(page)[0] == name0, f"칩으로 더한 곳이 맨 앞이 아님: {stop_names(page)}"


def flow_place_rename_delete_backup(page, shot):
    """이름 바꾸기(겹치면 안내, 요청에서도 새 이름으로) · 삭제는 '한 번 더'를 보고 다시 · 백업 파일에 장소도 들어가고 되살아남"""
    places(page, ("집", HOME), ("단골카페", CAFE))
    connect(page)
    r1 = page.locator("#plList .place").nth(1)
    r1.locator("button", has_text="이름").click()
    r1.locator(".ren input").fill("집")
    r1.locator(".ren button", has_text="저장").click()
    assert "이미 있어요" in page.inner_text("#plMsg"), "같은 이름으로 바꾸려 할 때 안내가 없음"
    r1.locator(".ren input").fill("카페")
    r1.locator(".ren button", has_text="저장").click()
    assert page.locator("#plList .place b").all_inner_texts() == ["집", "카페"], "이름이 바뀌지 않음"
    assert not plan_now(page, "카페 1시간, 집")
    assert stop_names(page) == ["스타벅스 공덕역점", "집"], f"새 이름 '카페'가 저장한 곳으로 가지 않음: {stop_names(page)}"
    with page.expect_download() as dl:
        page.click("#exportBtn")
    path = dl.value.path()
    data = json.load(open(path, encoding="utf-8"))
    assert [p["alias"] for p in data["data"].get("places", [])] == ["집", "카페"], "백업 파일에 즐겨찾기 장소가 없음"
    d = page.locator("#plList .place").nth(1).locator("button.x")
    d.click()
    assert d.inner_text() == "한 번 더", "삭제 확인 단계가 없음"
    page.wait_for_timeout(700)
    d.click()
    assert page.locator("#plList .place").count() == 1, "두 번 눌렀는데 지워지지 않음"
    page.set_input_files("#importFile", path)
    page.wait_for_function("document.querySelectorAll('#plList .place').length === 2", timeout=5000)
    assert "장소 2개" in page.inner_text("#status"), f"가져오기 안내가 없음: {page.inner_text('#status')}"


def flow_place_save_current_location(page, shot):
    """'📍 지금 있는 곳으로 저장': 이름이 없으면 먼저 묻고, 지금 좌표와 주소(카카오)로 저장"""
    kakao_stub(page)
    connect(page)
    page.context.grant_permissions(["geolocation"])
    page.context.set_geolocation({"latitude": 37.5512, "longitude": 126.9882})
    page.click("#plAddBtn")
    page.click("#plHere")
    assert "부를 이름" in page.inner_text("#plStat"), "이름 없이 저장하려 할 때 안내가 없음"
    page.fill("#plAlias", "회사")
    page.click("#plHere")
    page.wait_for_selector("#plList .place", timeout=10000)
    row = page.locator("#plList .place").first.inner_text()
    assert "회사" in row and "시험로 12" in row, f"지금 위치·주소로 저장되지 않음: {row}"
    p = saved(page)["places"][0]["place"]
    assert abs(float(p["x"]) - 126.9882) < 1e-6 and abs(float(p["y"]) - 37.5512) < 1e-6, f"좌표가 다름: {p}"


def flow_client_parser_matches_server(page, shot):
    """폰에 옮긴 요청 해석(ruleParse)이 서버(worker.js)와 똑같이 해석하는지 — 한쪽만 고치면 여기서 걸림"""
    samples = ["주차되는 헬스장 1시간, 점심, 오후엔 전시, 카페", "헬스 1시간, 점심, 한강공원 산책", "박물관 2시간, 점심, 카페, 저녁", "사우나, 영화, 저녁",
               "광화문 교보문고 2시간, 근처 국밥집 점심, 정독도서관, 이태원 복귀", "필라테스 1시간, 브런치, 기념관", "전시 1시간 30분, 카페",
               "서점 1시간, 카페", "책 사러 교보문고 가고 점심 먹고 카페", "헬스장 근처 점심", "집 근처 카페 1시간", "귀가", "집으로 복귀",
               "사우나 그리고 영화 → 저녁", "도서관에서 공부 3시간", "카페 2시간\n공원 산책", "PT 1시간, 갈비 저녁", "한강 산책 40분",
               "숲길, 영화관", "없는가게이름 1시간, 카페", "1시간", "점심 먹고  카페 가고 공원", "주차 가능한 갤러리 90분, 근처 칼국수"]
    want = server_parse(samples)
    got = page.evaluate("(S) => S.map(s => ruleParse(s))", samples)
    for s, a, b in zip(samples, want, got):
        assert a == b, f"'{s}' 해석이 다름\n서버: {a}\n폰: {b}"


def flow_places_small_screen(page, shot):
    """320px 화면: 출발지 칩·장소 목록·이름 바꾸기 칸·추가 칸이 가로로 넘치지 않음"""
    page.set_viewport_size({"width": 320, "height": 640})
    places(page, ("집", HOME), ("도서관", LIB), ("단골카페", CAFE), ("주말에가는큰도서관분관", {**LIB, "name": "서울특별시교육청 마포평생학습관 아현분관"}))
    connect(page)
    page.locator("#plList .place").nth(3).locator("button", has_text="이름").click()
    page.click("#plAddBtn")
    ok = page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    assert ok, "작은 화면에서 가로 스크롤이 생김"
    page.evaluate("document.querySelector('.placebar').scrollIntoView({block: 'start'})")
    shot("places-320")


def flow_no_places_server_parses(page, shot):
    """즐겨찾기 장소가 없거나 요청에 안 나오면 예전처럼 서버가 해석(활동 목록을 보내지 않음) · '집 복귀'를 못 찾으면 집 저장 안내"""
    connect(page)
    bodies = plan_bodies(page)
    assert not plan_now(page, "카페, 공원")
    assert "acts" not in bodies[-1], "즐겨찾기 장소가 없는데 폰에서 해석해 보냄"
    assert not plan_now(page, "카페, 집 복귀")
    miss = page.locator("#timeline .card", has_text="찾지 못함")
    assert miss.count() == 1 and miss.locator("button", has_text="집 저장").count() == 1, "집을 못 찾았을 때 저장 안내가 없음"
    miss.locator("button", has_text="집 저장").click()
    assert page.is_visible("#plAdd") and page.input_value("#plAlias") == "집", "집 저장 칸이 안 열림"
    places(page, ("도서관", LIB))
    page.reload()
    page.wait_for_function("document.getElementById('keys').textContent.includes('서버 연결됨')", timeout=10000)
    assert not plan_now(page, "카페, 공원")
    assert "acts" not in bodies[-1], "요청에 저장한 이름이 없는데 폰에서 해석해 보냄"
