# 역산 15분 플래너 자동 검수 흐름 (Playwright sync API)
# 동기화 흐름은 시험 서버가 떠 있어야 함: node /home/claude/backplan-server/local.mjs --port=8791 --code=시험코드123
import json
import re
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KEY = "backplan:v1"
SYNC = "http://localhost:8791"
CODE = "시험코드123"


def kst(days=0):
    return (datetime.now(ZoneInfo("Asia/Seoul")) + timedelta(days=days)).strftime("%Y-%m-%d")


def wd_today():
    """오늘(KST) 요일: 0=일 … 6=토, 이름"""
    i = (datetime.now(ZoneInfo("Asia/Seoul")).weekday() + 1) % 7
    return i, "일월화수목금토"[i]


def pick_time(sel, minutes):
    """시간 드롭다운(15분 단위)에서 고르기 — 초점을 먼저 옮겨 실제로 누르는 것처럼"""
    sel.focus()
    sel.select_option(str(minutes))


def ready(page):
    page.wait_for_selector("#view-today .hero, #view-today .empty, #view-today .goalsec, #view-today .today-head", timeout=10000)


def tab(page, name, flow=False):
    page.click(f".tabs button[data-tab='{name}']")
    page.wait_for_selector(f"#view-{name}:not([hidden])", timeout=5000)
    if name == "plan":   # 역산 화면: 기본은 순서도 — 목록을 다루는 검수는 목록으로 바꿔서
        b = page.locator("#pvFlow" if flow else "#pvList")
        if b.count() and b.get_attribute("aria-pressed") != "true":
            b.click()


def saved(page):
    return page.evaluate(f"JSON.parse(localStorage.getItem('{KEY}') || 'null')")


def rows(page):
    return page.locator("#todayList .blk")


def done_minutes(page):
    t = page.locator(".hero .prog b.num").first.inner_text()
    h = re.search(r"(\d+)시간", t)
    m = re.search(r"(\d+)분", t)
    return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)


def fresh(page):
    """예시 없이 빈 상태로 시작"""
    page.evaluate(f"localStorage.setItem('{KEY}', JSON.stringify({{v: 2, goals: [], current: null, seen: true}}))")
    page.reload()
    ready(page)


def pick(page, text):
    opts = page.locator("#goalPick option").all_inner_texts()
    page.select_option("#goalPick", label=[o for o in opts if text in o][0])


def wz_next(page):
    page.click("#wzNext")


def make_goal(page, title="자격증 필기 합격", days=40, mids=(("기출 3회분 70점", 25), ("핵심 요약 1회독", 12)), tasks=2, cat=None, to_mk=None):
    """마법사(10/23 새 순서)로 단계 목표 하나: 목표·목표일 → 단계 → 거꾸로 중간 목표 → 요일별 시간 → 완료.
    그다음 역산 목록에서 단계마다(가까운 단계부터) '할 일 i-j'를 tasks개(첫 할 일 45분, 나머지 30분)"""
    page.locator("button:visible", has_text=re.compile("목표 세우기")).first.click()
    page.fill("#wzTitle", title)
    page.fill("#wzDeadline", kst(days))
    wz_next(page)
    page.click(".kindc[data-kind='steps']")
    for name, d in mids:
        page.fill("#wzMid", name)
        page.fill("#wzMidDate", kst(d))
        page.click(".ask button")
    wz_next(page)   # → 4 요일별 시간
    if cat:
        page.select_option("#wzCat", cat)
    if to_mk is False:
        page.uncheck("#wzToMk")
    wz_next(page)   # 완료
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    ready(page)
    if tasks:
        add_tasks(page, title, tasks)


def add_tasks(page, title, tasks):
    """역산 목록에서 단계마다 할 일 넣기(모든 목표 보기였으면 끝나고 되돌림)"""
    was_all = (saved(page) or {}).get("current") == "*"
    g = [x for x in saved(page)["goals"] if x["title"] == title][-1]
    order = sorted(g["steps"], key=lambda s: (1 if s.get("final") else 0, s["due"]))
    if was_all:
        pick(page, title)
    tab(page, "plan")
    for i, st in enumerate(order):
        for j in range(tasks):
            box = page.locator(f"#step-{st['id']} .addtask")
            box.locator("input").fill(f"할 일 {i + 1}-{j + 1}")
            if j == 0:
                pick_time(box.locator("select"), 45)
            box.locator("button", has_text="할 일 추가").click()
    page.click("#pvFlow")   # 역산 보기는 기본(순서도)으로 되돌려 둠
    tab(page, "today")
    if was_all:
        pick(page, "모든 목표")
    ready(page)


def quick_goal(page, title, days, kind="steps", n=10, all_days=False):
    """마법사로 빨리: 단계(중간 목표 없이) 또는 일별 n회"""
    page.locator("button:visible", has_text=re.compile("목표 세우기")).first.click()
    page.fill("#wzTitle", title)
    page.fill("#wzDeadline", kst(days))
    wz_next(page)
    page.click(f".kindc[data-kind='{kind}']")
    if kind != "steps":
        page.fill("#wzCount", str(n))
        if all_days:
            for wd in "토일":
                page.click(f".wdt button[aria-label='{wd}요일']")
    wz_next(page)   # → 4
    wz_next(page)   # 완료
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    ready(page)


def setup_goal(page, name, kind="steps", n=10):
    """설정 전 목표를 새 순서로 설정(목표 화면 카드의 '설정하기')"""
    tab(page, "goals")
    page.locator(".goal-item", has_text=name).locator("button", has_text="설정하기").click()
    wz_next(page)   # 1 목표일 확인
    page.click(f".kindc[data-kind='{kind}']")
    if kind != "steps":
        page.fill("#wzCount", str(n))
    wz_next(page)   # 3 → 4
    wz_next(page)   # 완료
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    ready(page)


# ---------- 동기화 시험 서버 ----------
def srv(path, body=None):
    req = urllib.request.Request(SYNC + path, data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET")
    return urllib.request.urlopen(req, timeout=5).read().decode()


def srv_reset():
    srv("/__reset")


def srv_dump():
    d = json.loads(srv("/__dump"))
    return {k: json.loads(v) for k, v in d.items()}


def mk_snapshot(at=None, goals=None, ndays=30):
    """목표까지가 보내는 모양의 스냅숏 (오늘부터 매일 하루 분량)"""
    goals = goals if goals is not None else [
        {"id": "g3", "short": "한국사", "cat": "자격증", "title": "한국사 심화 2급", "start": kst(-10), "due": kst(120), "status": "진행 중", "memo": "기본서 하루 2쪽",
         "steps": [{"sid": "s-a", "t": "원서접수", "due": kst(20), "done": False}, {"sid": "s-b", "t": "기본서 1회독", "due": kst(80), "done": False}, {"sid": "s-c", "t": "기출 8회분", "due": kst(110), "done": False}],
         "metrics": [{"mid": "m-a", "name": "기본서 읽기", "unit": "쪽", "kind": "total", "days": 5, "start": 0, "target": 400}]},
        {"id": "g7", "short": "기타", "cat": "배우기", "title": "기타 솔로 따라치기", "start": kst(-10), "due": kst(200), "status": "계획", "memo": "",
         "steps": [{"sid": "s-g1", "t": "솔로 1구간", "due": kst(40), "done": False}, {"sid": "s-g2", "t": "전체 이어 치기", "due": kst(190), "done": False}],
         "metrics": [{"mid": "m-g", "name": "주간 연습 시간 (주 3회, 20분씩)", "unit": "분", "kind": "level", "days": 3, "start": 60, "target": 60}]},
        {"id": "g1", "short": "여행", "cat": "여행", "title": "유럽 여행", "start": kst(-10), "due": kst(600), "status": "보류", "memo": "", "steps": [], "metrics": []},
    ]
    days = []
    for i in range(ndays):
        d = kst(i)
        days.append({"d": d, "g": "g3", "m": "m-a", "k": 0, "text": "기본서 2쪽", "amt": 2, "unit": "쪽", "min": None, "kind": "amt"})
        if i % 2 == 0:
            days.append({"d": d, "g": "g7", "m": "m-g", "k": 0, "text": "연습 시간 20분", "amt": 20, "unit": "분", "min": 20, "kind": "session"})
    return {"at": at or datetime.utcnow().isoformat() + "Z", "from": kst(0), "to": kst(ndays - 1), "url": "https://claude.ai/artifact/TEST", "goals": goals, "days": days}


def srv_put_mk(snap):
    srv("/__put", {"key": "mk", "value": snap})


def connect(page, code=CODE, server=SYNC):
    tab(page, "goals")
    page.fill("#syncServer", server)
    page.fill("#syncCode", code)
    page.click("#syncConnect")
    page.wait_for_function("(() => { const s = document.getElementById('syncState'); const m = document.querySelector('#syncCard [role=alert]:not([hidden])'); return (s && /맞춤|⚠/.test(s.textContent)) || (m && m.textContent.trim()); })()", timeout=10000)


def quiet(page, top=False):
    """스크린샷 전에: 맞추는 중이면 끝날 때까지 기다리고, 알림 문구는 늦게 떠도 안 보이게, top이면 맨 위로"""
    try:
        page.wait_for_function("typeof state === 'undefined' || !state.sync || !state.sync.server || (state.sync.sig === localSig() && !syncing)", timeout=8000)
    except Exception:
        pass
    page.add_style_tag(content="#toast{display:none!important}")
    if top:
        page.evaluate("document.activeElement && document.activeElement.blur(); scrollTo(0, 0)")
        page.wait_for_timeout(400)
        page.evaluate("scrollTo(0, 0)")


def wait_synced(page, timeout=12000):
    """올리지 않은 변경이 없고 맞추는 중도 아닐 때까지"""
    page.wait_for_timeout(100)
    page.wait_for_function("typeof state !== 'undefined' && state.sync.sig === localSig() && !syncing", timeout=timeout)


# ---------- 기본 흐름 ----------
def flow_first_open_shows_example(page, shot):
    ready(page)
    assert "예시 목표예요" in page.inner_text("#view-today"), "처음 열었는데 예시 안내가 없음"
    assert page.locator(".hero h1").inner_text() == "토익 850점 받기"
    assert re.search(r"D-\d+", page.inner_text(".hero .dday")), "D-day가 없음"
    assert page.locator(".mosaic i").count() > 30, "진행 모자이크가 안 그려짐"
    assert page.locator(".mosaic i.d").count() >= 3, "끝낸 칸이 칠해지지 않음"
    assert rows(page).count() >= 2, "오늘의 15분 목록이 비어 있음"
    assert rows(page).locator(".chk[aria-pressed='true']").count() >= 1 and rows(page).locator(".chk[aria-pressed='false']").count() >= 1, "끝낸 칸과 남은 칸이 함께 보여야 함"
    assert "null" not in page.inner_text("main"), "화면에 null 글자가 보임"
    shot("today")


def flow_wizard_backward_planning(page, shot):
    ready(page)
    page.locator("button", has_text="내 목표 세우기").click()
    page.fill("#wzTitle", "하프 마라톤 완주")
    page.fill("#wzDeadline", kst(60))
    assert page.inner_text("#wzDday") == "D-60", f"목표일 옆 D-day가 안 보임: {page.inner_text('#wzDday')}"
    wz_next(page)
    assert page.locator(".kindc").count() == 3 and "어떻게 나눌까요" in page.inner_text("#sheetTitle"), "2단계에서 단계·일별·운동을 고르게 하지 않음"
    page.click(".kindc[data-kind='steps']")
    q = page.inner_text(".ask .q")
    assert "하프 마라톤 완주" in q and "바로 전에" in q, f"거꾸로 묻는 질문이 아님: {q}"
    page.fill("#wzMid", "15km 쉬지 않고 달리기")
    page.fill("#wzMidDate", kst(45))
    page.click(".ask button")
    q2 = page.inner_text(".ask .q")
    assert "15km 쉬지 않고 달리기" in q2, f"다음 질문이 방금 넣은 중간 목표를 기준으로 하지 않음: {q2}"
    page.fill("#wzMid", "10km 1시간 안에")
    page.fill("#wzMidDate", kst(25))
    page.click(".ask button")
    items = page.locator(".wz-list li").all_inner_texts()
    assert "하프 마라톤" in items[0] and "15km" in items[1] and "10km" in items[2], f"최종 목표가 맨 위, 거꾸로 쌓여야 함: {items}"
    shot("wizard-backward")
    wz_next(page)
    summary = page.inner_text(".sum")
    assert "구간마다 나오는 단계" in summary and "10km 1시간 안에" in summary and "15km" in summary, f"4단계에 구간마다 나오는 단계가 없음: {summary}"
    assert page.locator(".avail select").count() == 7, "4단계에 요일별 시간 드롭다운이 없음"
    shot("wizard-split")
    wz_next(page)
    ready(page)
    assert page.locator(".hero h1").inner_text() == "하프 마라톤 완주", "만든 목표가 오늘 화면에 안 나옴"
    assert "예시 목표예요" not in page.inner_text("#view-today"), "내 목표를 만들었는데 예시가 남음"
    st = saved(page)
    assert len(st["goals"]) == 1 and not st["goals"][0].get("sample"), "손대지 않은 예시 목표가 지워지지 않음"
    steps = st["goals"][0]["steps"]
    assert [s["title"] for s in steps] == ["10km 1시간 안에", "15km 쉬지 않고 달리기", "하프 마라톤 완주"], f"단계 순서가 틀림: {[s['title'] for s in steps]}"
    assert st["goals"][0].get("plan", {}).get("kind") == "steps" and st["goals"][0]["plan"]["at"] == kst(0), f"새 순서 설정(단계)이 저장되지 않음: {st['goals'][0].get('plan')}"
    assert rows(page).filter(has_text="10km 1시간 안에").count() >= 1, "만든 날부터 지금 단계가 오늘 화면에 나오지 않음"
    page.reload()
    ready(page)
    assert page.locator(".hero h1").inner_text() == "하프 마라톤 완주", "새로고침 후 목표가 사라짐"


def flow_check_block_updates_and_persists(page, shot):
    ready(page)
    before = done_minutes(page)
    n_rows = rows(page).count()
    rows(page).locator(".chk[aria-pressed='false']").first.click()
    assert done_minutes(page) == before + 15, f"체크했는데 끝낸 시간이 15분 늘지 않음: {before} → {done_minutes(page)}"
    assert rows(page).count() == n_rows, "체크했더니 오늘 목록 길이가 바뀜(흔들림)"
    page.reload()
    ready(page)
    assert done_minutes(page) == before + 15, "새로고침 후 체크가 사라짐"
    rows(page).locator(".chk[aria-pressed='true']").last.click()
    assert done_minutes(page) == before, "체크를 되돌려도 끝낸 시간이 그대로"


def flow_check_keeps_order_and_tapped_block(page, shot):
    """같은 할 일의 2번째 칸을 먼저 눌러도 그 칸이 체크되고, 목록 순서가 그대로(보류 4)"""
    ready(page)
    page.evaluate(f"""() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); const g = s.goals[0];
        g.avail = [240, 240, 240, 240, 240, 240, 240]; g.log = []; localStorage.setItem('{KEY}', JSON.stringify(s)); }}""")
    page.reload()
    ready(page)
    texts = rows(page).all_inner_texts()
    same = [i for i, t in enumerate(texts) if texts[0].split("\n")[0] in t]
    assert len(same) >= 2, f"같은 할 일 칸이 두 개 이상 있어야 함: {texts[:4]}"
    second = rows(page).nth(same[1])
    label = second.locator(".t2").inner_text()
    second.locator(".chk").click()
    texts2 = rows(page).all_inner_texts()
    assert [t.split("\n")[0] for t in texts2] == [t.split("\n")[0] for t in texts], "체크했더니 목록 순서가 바뀜"
    assert rows(page).nth(same[1]).locator(".chk").get_attribute("aria-pressed") == "true", f"누른 칸({label})이 체크되지 않음"
    assert rows(page).nth(same[0]).locator(".chk").get_attribute("aria-pressed") == "false", "누르지 않은 앞 칸이 대신 체크됨"
    page.reload()
    ready(page)
    assert rows(page).nth(same[1]).locator(".chk").get_attribute("aria-pressed") == "true", "새로고침 후 누른 칸 체크가 다른 칸으로 옮겨감"


def flow_today_quota_then_next_up(page, shot):
    """오늘 몫(그 요일에 고른 시간)을 다 하면 '＋ 15분 더'로 다음 할 일을 오늘로 당겨 더 함(10/21: 미리 하기 → 15분 더)"""
    ready(page)
    n = rows(page).count()
    wi, _ = wd_today()
    quota = saved(page)["goals"][0]["avail"][wi] // 15
    assert n == quota, f"오늘 칸 수가 오늘 요일에 고른 시간({quota}칸)과 다름: {n}"
    for _ in range(20):
        loc = rows(page).locator(".chk[aria-pressed='false']")
        if not loc.count():
            break
        loc.first.click()
    assert rows(page).count() == n, f"오늘 몫을 다 하는 동안 목록 길이가 바뀜: {n} → {rows(page).count()}"
    text = page.inner_text("#view-today")
    assert "오늘 몫을 다 했어요" in text, "오늘 몫을 끝냈는데 안내가 없음"
    assert page.locator(".blk", has_text="미리 하기").count() == 0, "없앤 '미리 하기' 칸이 남음"
    more = page.locator("#view-today button", has_text="15분 더")
    assert more.count() == 1, "오늘 몫을 다 했는데 '＋ 15분 더'가 없음"
    before = done_minutes(page)
    more.click()
    assert rows(page).count() == n + 1, f"'＋ 15분 더'를 눌러도 칸이 안 늘어남: {rows(page).count()}"
    new = rows(page).locator(".chk[aria-pressed='false']")
    assert new.count() == 1 and "원래" in rows(page).filter(has=page.locator(".chk[aria-pressed='false']")).inner_text(), "다음 할 일을 당겨 오지 않음"
    new.click()
    assert done_minutes(page) == before + 15, "더 한 15분이 끝낸 시간에 들어가지 않음"
    assert rows(page).count() == n + 1, "더 한 칸을 체크했더니 목록 길이가 바뀜"
    assert page.locator("#view-today button", has_text="15분 더").count() == 1, "더 한 뒤 다시 '＋ 15분 더'가 없음"
    page.reload()
    ready(page)
    assert rows(page).count() == n + 1 and rows(page).locator(".chk[aria-pressed='false']").count() == 0, "새로고침했더니 더 한 칸이 사라짐"
    shot("done-today", store=False)   # 스토어 화면은 8장까지


def flow_focus_timer(page, shot):
    page.clock.install()
    page.reload()
    ready(page)
    before = done_minutes(page)
    rows(page).locator(".play").first.click()
    card = page.locator("#timerCard")
    assert card.is_visible(), "타이머가 안 보임"
    assert page.inner_text("#timerLeft") in ("15:00", "14:59"), f"15분부터 시작하지 않음: {page.inner_text('#timerLeft')}"
    page.click("#timerCard button:has-text('잠시 멈춤')")
    assert "잠시 멈춤" in card.inner_text(), "멈춤 상태가 안 보임"
    page.click("#timerCard button:has-text('계속')")
    page.reload()   # 앱을 닫았다 열어도 타이머가 이어져야 함
    ready(page)
    assert page.locator("#timerCard").is_visible(), "다시 열었더니 타이머가 사라짐"
    shot("timer")
    page.clock.fast_forward("15:05")
    page.wait_for_function("document.getElementById('timerCard')?.classList.contains('end')", timeout=5000)
    assert "끝냈나요" in page.inner_text("#timerCard"), "15분이 지나도 끝 안내가 없음"
    page.click("#timerCard button:has-text('끝냄')")
    assert done_minutes(page) == before + 15, "타이머로 끝낸 칸이 체크되지 않음"
    assert page.locator("#timerCard").count() == 0, "끝낸 뒤에도 타이머가 남음"


def flow_timer_other_goal_and_deleted_task(page, shot):
    """다른 목표를 보는 중에도 타이머 카드가 보이고, 지운 할 일의 타이머는 울리지 않고 사라짐(보류 9)"""
    page.clock.install()
    fresh(page)
    make_goal(page, title="첫 목표", mids=(), tasks=1)
    rows(page).locator(".play").first.click()
    tab(page, "goals")
    tab(page, "goals")
    quick_goal(page, "둘째 목표", 20)
    assert "둘째 목표" in page.locator(".hero h1").inner_text()
    assert page.locator("#timerCard").is_visible(), "다른 목표를 보는 중 타이머 카드가 사라짐"
    assert "첫 목표" in page.inner_text("#timerCard"), "타이머 카드에 어느 목표인지 안 보임"
    pick(page, "첫 목표")
    tab(page, "plan")
    page.locator(".task .icon-btn").first.click()
    page.click("#sheet .btn.primary")
    tab(page, "today")
    page.clock.fast_forward("16:00")
    page.wait_for_timeout(500)
    assert page.locator("#timerCard").count() == 0, "지운 할 일의 타이머가 남음"
    assert saved(page).get("timer") is None, "지운 할 일의 타이머가 저장소에 남음"


def flow_plan_reverse_chain_edit(page, shot):
    ready(page)
    tab(page, "plan")
    nodes = page.locator(".chain .node[id^='step-']")
    assert "최종 목표" in nodes.first.inner_text(), "역산 화면 맨 위가 최종 목표가 아님"
    assert "지금" in page.locator(".chain .node.now").inner_text(), "맨 아래에 '지금'이 없음"
    count = nodes.count()
    page.locator(".insert").first.click()   # 최종 목표 바로 전에 추가
    assert page.locator(".chain .node[id^='step-']").count() == count + 1, "중간 목표가 추가되지 않음"
    title = page.locator(".step-title:focus")
    node_id = title.evaluate("el => el.closest('.node').id")
    title.fill("마지막 점검 주간")
    title.press("Enter")
    page.locator("h2.view-title").click()
    node = page.locator("#" + node_id)
    assert node.locator("textarea.step-title").input_value() == "마지막 점검 주간", "새 중간 목표 이름이 바뀌지 않음"
    assert any(s["title"] == "마지막 점검 주간" for s in saved(page)["goals"][0]["steps"]), "새 중간 목표 이름이 저장되지 않음"
    inp = node.locator(".addtask input")
    inp.fill("모의고사 오답만 다시")
    pick_time(node.locator(".addtask select"), 45)
    node.locator(".addtask button", has_text="할 일 추가").click()
    node = page.locator("#" + node_id)
    task = node.locator(".task").first
    assert task.locator("select").input_value() == "45", f"할 일 시간이 45분이 아님: {task.locator('select').input_value()}"
    assert task.locator("button[aria-label$='15분 늘리기']").count() == 0, "시간 고르기가 아직 −/+ 버튼임"
    pick_time(task.locator("select"), 60)
    node = page.locator("#" + node_id)
    sel = node.locator(".task select").first
    assert sel.input_value() == "60" and sel.evaluate("el => el.selectedOptions[0].textContent") == "1시간", "드롭다운으로 1시간을 골라도 안 바뀜"
    assert node.locator(".task .sq i").count() == 4, "15분 칸 그림이 4칸이 아님"
    shot("plan", store=False)   # 스토어에는 순서도 화면을 넣음
    node.locator(".step-titlerow .icon-btn").click()
    assert page.is_visible("#sheet"), "지우기 전에 확인을 묻지 않음"
    page.click("#sheet .btn.primary")
    assert page.locator("#" + node_id).count() == 0, "확인 후에도 지워지지 않음"


def flow_flowchart_view_and_date_edit(page, shot):
    """역산 순서도: 맨 위 최종 목표, 아래 오늘, 단계마다 15분 할 일 가지 · 상자를 누르면 날짜 바꾸기 · 보기 선택 기억"""
    ready(page)
    tab(page, "plan", flow=True)
    assert page.get_attribute("#pvFlow", "aria-pressed") == "true", "순서도 버튼이 눌린 상태가 아님"
    boxes = page.locator(".flow .fbox")
    assert "최종" in boxes.first.inner_text(), "순서도 맨 위가 최종 목표가 아님"
    assert page.locator(".flow .fbox.today").count() == 1, "순서도에 '오늘'이 없음"
    assert page.locator(".flow .fchip").count() >= 3, "단계의 15분 할 일 가지가 안 보임"
    assert page.locator(".flow .fchip .sq i.d").count() >= 1, "끝낸 15분 칸이 칠해지지 않음"
    assert page.locator(".flow .fgap .days").count() >= 2, "단계 사이 날 수가 없음"
    assert page.locator(".flow .fbox.next").count() == 1, "다음 단계 표시가 없음"
    assert "null" not in page.inner_text("#view-plan"), "화면에 null 글자가 보임"
    w = page.evaluate("document.querySelector('.flow').scrollWidth - document.querySelector('.flow').clientWidth")
    assert w <= 1, f"순서도가 옆으로 넘침: {w}px"
    quiet(page, top=True)
    shot("flow")
    g = saved(page)["goals"][0]
    mids = sorted([s for s in g["steps"] if not s.get("final")], key=lambda s: s["due"])
    target = mids[-1]
    page.locator(".flow .fbox", has_text=target["title"]).first.click()
    page.wait_for_selector("#dsDate", timeout=3000)
    page.fill("#dsDate", kst(40))
    page.click("#dsOk")
    page.wait_for_timeout(100)
    g = saved(page)["goals"][0]
    assert any(s["title"] == target["title"] and s["due"] == kst(40) for s in g["steps"]), "순서도에서 바꾼 단계 날짜가 저장되지 않음"
    page.locator(".flow .fbox.goal").click()
    page.fill("#dsDate", kst(100))
    page.click("#dsOk")
    page.wait_for_timeout(100)
    g = saved(page)["goals"][0]
    assert g["deadline"] == kst(100), "순서도에서 마감을 바꿨는데 저장되지 않음"
    assert (page.text_content("#toast") or "").startswith("마감을 옮기고 중간 목표"), f"중간 목표도 옮겼다는 안내가 없음: {page.text_content('#toast')}"
    assert max(s["due"] for s in g["steps"] if not s.get("final")) > kst(40), "마감을 늦췄는데 중간 목표가 같이 옮겨지지 않음"
    page.click("#pvList")
    page.reload()
    ready(page)
    page.click(".tabs button[data-tab='plan']")
    assert page.locator(".chain").count() == 1 and page.get_attribute("#pvList", "aria-pressed") == "true", "목록 보기를 골랐는데 다시 열면 순서도로 돌아감"


def flow_goal_card_change_deadline(page, shot):
    """목표 화면의 '마감 바꾸기'로 언제든 목표 날짜를 바꿈"""
    ready(page)
    tab(page, "goals")
    page.locator(".goal-item button", has_text="마감 바꾸기").first.click()
    page.wait_for_selector("#dsDate", timeout=3000)
    assert page.evaluate("document.activeElement && document.activeElement.id") == "dsDate", "마감 바꾸기 창에서 날짜 칸에 초점이 없음"
    page.fill("#dsDate", kst(0))
    page.click("#dsOk")
    assert page.is_visible("#sheet"), "오늘 날짜를 마감으로 받아 버림"
    page.fill("#dsDate", kst(90))
    page.press("#dsDate", "Enter")
    page.wait_for_timeout(100)
    assert saved(page)["goals"][0]["deadline"] == kst(90), "목표 화면에서 바꾼 마감이 저장되지 않음"
    assert re.search(r"D-90", page.inner_text("#view-goals")), "목표 카드의 D-day가 바뀌지 않음"


def flow_rename_then_tap_stepper(page, shot):
    """이름을 고친 직후 고른 시간(드롭다운)이 씹히지 않음(보류 5)"""
    ready(page)
    tab(page, "plan")
    task = page.locator(".task").first
    tid = task.evaluate("el => el.closest('.node').id")
    before = int(task.locator("select").input_value())
    name = task.locator("input.tt")
    name.click()
    name.fill("이름 바꾼 할 일")
    pick_time(task.locator("select"), before + 15)   # 입력칸이 포커스를 잃으며 change → 바로 시간 고르기
    node = page.locator("#" + tid)
    t2 = node.locator(".task").first
    assert t2.locator("input.tt").input_value() == "이름 바꾼 할 일", "고친 이름이 사라짐"
    assert t2.locator("select").input_value() == str(before + 15), f"이름을 고친 직후 고른 시간이 무시됨: {before}"
    step = page.locator(".chain .node[id^='step-'] textarea.step-title").nth(1)
    sid = step.evaluate("el => el.closest('.node').id")
    step.fill("단계 이름도 바꿈")
    pick_time(page.locator(f"#{sid} .addtask select"), 45)
    assert page.locator(f"#{sid} .addtask select").input_value() == "45", "단계 이름을 고친 직후 고른 시간이 무시됨"


def flow_dates_resort_and_even_split(page, shot):
    fresh(page)
    make_goal(page)
    tab(page, "plan")
    dates = page.locator(".chain .date-in")
    first_mid = page.locator(".chain .node[id^='step-']").nth(1)
    first_mid.locator(".date-in").fill(kst(5))          # 위쪽 중간 목표를 더 이른 날짜로 → 순서가 다시 맞춰져야 함
    first_mid.locator(".date-in").dispatch_event("change")
    vals = [dates.nth(i).input_value() for i in range(dates.count())]
    assert vals == sorted(vals, reverse=True), f"날짜를 고친 뒤 순서가 맞지 않음(위가 늦은 날): {vals}"
    page.click("button:has-text('할 일 양에 맞춰 날짜 나누기')")
    vals = [page.locator(".chain .date-in").nth(i).input_value() for i in range(page.locator(".chain .date-in").count())]
    assert vals[0] == kst(40), f"최종 목표 날짜가 바뀜: {vals[0]}"
    assert vals == sorted(vals, reverse=True) and len(set(vals)) == len(vals), f"나눈 날짜가 순서대로가 아님: {vals}"
    assert all(kst(1) <= v <= kst(40) for v in vals), f"오늘~마감 밖의 날짜: {vals}"


def flow_deadline_change_is_reversible(page, shot):
    """최종 마감을 앞당겼다 되돌리면 중간 목표 날짜도 원래대로, 지난 날짜는 받지 않음(보류 1)"""
    fresh(page)
    make_goal(page, days=60, mids=(("중간 A", 40), ("중간 B", 20)), tasks=1)
    tab(page, "plan")
    orig = [s["due"] for s in saved(page)["goals"][0]["steps"]]
    fin = page.locator(".chain .node.goal .date-in")
    fin.fill(kst(30))
    fin.dispatch_event("change")
    mid = [s["due"] for s in saved(page)["goals"][0]["steps"]]
    assert all(d <= kst(30) for d in mid), f"마감을 앞당겼는데 중간 목표가 마감 뒤에 남음: {mid}"
    assert len(set(mid)) == len(mid), f"앞당기면서 중간 목표가 한 날짜로 뭉침: {mid}"
    fin = page.locator(".chain .node.goal .date-in")
    fin.fill(kst(60))
    fin.dispatch_event("change")
    back = [s["due"] for s in saved(page)["goals"][0]["steps"]]
    def days_of(s):
        return (datetime.strptime(s, "%Y-%m-%d") - datetime.strptime(kst(0), "%Y-%m-%d")).days
    assert all(abs(days_of(a) - days_of(b)) <= 1 for a, b in zip(orig, back)), f"되돌렸는데 중간 목표 날짜가 돌아오지 않음: {orig} → {back}"
    fin = page.locator(".chain .node.goal .date-in")
    fin.fill(kst(-2))
    fin.dispatch_event("change")
    assert saved(page)["goals"][0]["deadline"] == kst(60), "지난 날짜를 마감으로 받아들임"
    m = page.locator(".chain .node[id^='step-']").nth(1).locator(".date-in")
    m.fill(kst(-3))
    m.dispatch_event("change")
    assert all(s["due"] >= kst(0) for s in saved(page)["goals"][0]["steps"]), "중간 목표에 지난 날짜가 들어감"


def flow_even_dates_skips_done_steps(page, shot):
    """'할 일 양에 맞춰 날짜 나누기'는 끝낸 단계를 건드리지 않음(보류 8)"""
    fresh(page)
    make_goal(page, days=50, mids=(("앞 단계", 10), ("뒤 단계", 30)), tasks=1)
    tab(page, "plan")
    first_step = [s for s in saved(page)["goals"][0]["steps"] if not s.get("final")][0]
    page.locator(f"#step-{first_step['id']} button", has_text="끝냄").click()
    page.click("button:has-text('할 일 양에 맞춰 날짜 나누기')")
    after = [s for s in saved(page)["goals"][0]["steps"] if s["id"] == first_step["id"]][0]
    assert after["due"] == first_step["due"], f"끝낸 단계 날짜가 바뀜: {first_step['due']} → {after['due']}"
    assert after.get("done"), "끝냄 표시가 저장되지 않음"


def flow_insert_before_tomorrow_no_false_shortage(page, shot):
    """내일이 마감인 단계 바로 전에 넣어도 거짓 '모자람'이 나오지 않음(보류 10)"""
    fresh(page)
    make_goal(page, title="내일 마감", days=1, mids=(), tasks=1)
    tab(page, "plan")
    page.locator(".insert").first.click()
    page.locator("h2.view-title").click()
    assert page.locator(".node.goal .chip.no").count() == 0, f"최종 목표에 거짓 모자람 표시: {page.inner_text('.node.goal')[:120]}"
    st = saved(page)["goals"][0]
    assert all(s["due"] >= kst(0) for s in st["steps"]), "새 중간 목표가 지난 날짜에 들어감"


def flow_shortage_and_no_time_alerts(page, shot):
    fresh(page)
    make_goal(page, days=10, mids=(("빠듯한 단계", 3),), tasks=3)
    tab(page, "sched")
    for wd in "월화수목금토일":
        pick_time(page.locator(f"select[aria-label='{wd}요일 시간']"), 0)
    assert page.locator(".avail select").evaluate_all("els => els.every(e => e.selectedOptions[0].textContent === '쉼')"), "0분을 골랐는데 '쉼'으로 안 보임"
    assert "쓸 수 있는 시간을 정하면" in page.inner_text("#view-sched"), "쓸 수 있는 시간이 0인데 안내가 없음"
    tab(page, "today")
    assert "쓸 수 있는 시간이 없어요" in page.inner_text("#view-today"), "오늘 화면에 시간이 없다는 경고가 없음"
    tab(page, "sched")
    pick_time(page.locator("select[aria-label='월요일 시간']"), 15)
    tab(page, "today")
    text = page.inner_text("#view-today")
    assert "모자라요" in text or "늦어요" in text, f"시간이 모자란데 경고가 없음: {text[:200]}"
    assert "더 필요해요" in text, f"마감을 넘길 때 '하루 평균 ○분 더 필요' 안내가 없음(보류 11): {text[:300]}"
    tab(page, "plan")
    assert page.locator(".chip.no").count() >= 1, "역산 화면에 모자람 표시가 없음"


def flow_schedule_view(page, shot):
    ready(page)
    tab(page, "sched")
    assert page.locator(".day.is-today").count() == 1, "오늘 날짜가 강조되지 않음"
    assert page.locator(".mile").count() >= 1, "중간 목표 마감 표시가 없음"
    text = page.inner_text("#view-sched")
    assert "에 다 끝나요" in text, "언제 다 끝나는지 안내가 없음"
    before = text
    mon = page.locator("select[aria-label='월요일 시간']")
    vals = mon.evaluate("el => [...el.options].map(o => +o.value)")
    cur = int(mon.input_value())
    assert vals[0] == 0 and 720 in vals and all(v % 15 == 0 for v in vals), f"요일 시간 드롭다운 값이 이상함: {vals[:6]}…"
    pick_time(mon, vals[vals.index(cur) + 1])
    assert page.inner_text("#view-sched") != before, "요일별 시간을 바꿔도 일정이 그대로"
    shot("schedule")


def flow_claude_copy_paste(page, shot):
    fresh(page)
    make_goal(page, title="정보처리기사 필기", days=30, mids=(), tasks=1)
    tab(page, "plan")
    page.click("button:has-text('Claude에게 나눠 달라기')")
    prompt = page.input_value("#cPrompt")
    assert "정보처리기사 필기" in prompt and kst(30) in prompt and '"milestones"' in prompt, "부탁 글에 목표·마감·답 모양이 없음"
    page.fill("#cAnswer", "이렇게 나눠 봤어요\n```json\n{\"milestones\":[{\"title\":\"1과목 개념 정리\",\"due\":\"" + kst(10) + "\",\"tasks\":[{\"title\":\"요구사항 확인 단원\",\"minutes\":40},{\"title\":\"화면 설계 단원\",\"minutes\":30}]},"
              "null,{\"title\":\"기출 3회 풀기\",\"due\":\"" + kst(22) + "\",\"tasks\":[\"2023년 1회\", null, {\"title\":\"2023년 2회\",\"minutes\":\"1시간 30분\"}]},"
              "{\"title\":\"정보처리기사 필기\",\"due\":\"" + kst(30) + "\",\"tasks\":[{\"title\":\"오답 노트 훑기\",\"minutes\":\"45분\"}]}]}\n```\n바꾸고 싶은 곳은 {단계 이름}으로 말씀해 주세요")
    page.click("#sheet .sheet-actions .btn.primary")
    assert "바꿀까요" in page.inner_text("#sheet"), "손으로 적은 계획이 있는데 바꾸기 전에 묻지 않음(보류 2)"
    page.click("#sheet .btn:has-text('취소')")
    assert page.input_value("#cAnswer").startswith("이렇게 나눠 봤어요"), "취소했더니 붙여넣은 답이 사라짐"
    page.click("#sheet .sheet-actions .btn.primary")
    page.click("#sheet .btn.primary:has-text('바꾸기')")
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    st = saved(page)["goals"][0]
    titles = [s["title"] for s in st["steps"]]
    assert titles == ["1과목 개념 정리", "기출 3회 풀기", "정보처리기사 필기"], f"Claude 답대로 채워지지 않음: {titles}"
    assert [k["blocks"] for k in st["steps"][0]["tasks"]] == [3, 2], "분이 15분 칸으로 바뀌지 않음(40분 → 3칸)"
    assert [k["title"] for k in st["steps"][1]["tasks"]] == ["2023년 1회", "2023년 2회"], f"글자만 있는 할 일·null이 제대로 처리되지 않음: {st['steps'][1]['tasks']}"
    assert [k["blocks"] for k in st["steps"][1]["tasks"]] == [2, 6], "글자 할 일은 30분, '1시간 30분'은 6칸이어야 함"
    assert st["steps"][2]["tasks"][0]["title"] == "오답 노트 훑기", "마지막 항목이 최종 목표의 할 일로 들어가지 않음"
    page.click("button:has-text('Claude에게 나눠 달라기')")
    page.fill("#cAnswer", "죄송해요, 다시 해 볼게요")
    page.click("#sheet .sheet-actions .btn.primary")
    assert "찾지 못했어요" in page.inner_text("#sheet"), "엉뚱한 답을 붙여넣었을 때 안내가 없음"
    page.fill("#cAnswer", '{"milestones":[null, 3, {"tasks":[]}]}')
    page.click("#sheet .sheet-actions .btn.primary")
    msg = page.inner_text("#sheet [role=alert]")
    assert re.search(r"[가-힣]", msg) and "TypeError" not in msg, f"깨진 답에 한국어 안내가 아님: {msg}"


def flow_backup_roundtrip(page, shot):
    ready(page)
    tab(page, "goals")
    with page.expect_download() as dl:
        page.click("#exportBtn")
    path = dl.value.path()
    data = json.load(open(path, encoding="utf-8"))
    assert data["app"] == KEY and len(data["data"]["goals"]) == 1, "백업 파일 내용이 맞지 않음"
    assert "sync" not in data["data"], "백업에 동기화 접속 코드가 들어감"
    fresh(page)
    tab(page, "goals")
    page.set_input_files("#importFile", path)
    page.wait_for_selector("#sheet:not([hidden])", timeout=5000)   # 가져오기 전에 확인을 물어야 함
    page.click("#sheet .btn.primary")
    tab(page, "today")
    assert page.locator(".hero h1").inner_text() == "토익 850점 받기", "백업에서 목표를 되살리지 못함"


def flow_broken_backup_and_storage_do_not_blank(page, shot):
    """모양이 틀린 백업·저장본이어도 화면이 비지 않음(보류 3)"""
    import tempfile
    ready(page)
    bad = {"app": KEY, "at": "2026-10-01T00:00:00Z", "data": {"goals": [
        {"id": "ok1", "title": "멀쩡한 목표", "deadline": kst(30), "steps": [{"id": "s1", "title": "단계", "due": kst(10), "tasks": [{"id": "t1", "title": "할 일", "blocks": "3"}, None, 5]}], "log": [{"d": kst(0), "t": "t1"}, "x"]},
        {"id": "bad1", "title": None, "deadline": "언젠가"}, 7, None,
        {"id": "bad2", "title": "단계 모양이 틀림", "deadline": kst(40), "steps": "abc", "avail": "x", "log": {"a": 1}}]}}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(bad, f, ensure_ascii=False)
    f.close()
    tab(page, "goals")
    page.set_input_files("#importFile", f.name)
    page.wait_for_selector("#sheet:not([hidden])", timeout=5000)
    assert "깨진 목표" in page.inner_text("#sheet"), "깨진 목표를 빼겠다는 안내가 없음"
    page.click("#sheet .btn.primary")
    for name in ("today", "plan", "sched", "goals"):
        tab(page, name)
        assert page.locator(f"#view-{name}").inner_text().strip(), f"{name} 화면이 빔"
    assert len(saved(page)["goals"]) == 2, f"멀쩡한 목표 2개만 남아야 함: {[g['title'] for g in saved(page)['goals']]}"
    page.evaluate(f"localStorage.setItem('{KEY}', JSON.stringify({{v: 2, goals: [{{id: 'z', title: '저장본', deadline: '{kst(20)}', steps: [{{title: 3}}, null], log: 5, timer: 'x'}}, 'nope'], current: 5, timer: {{goalId: 'z'}}, sync: 7}}))")
    page.reload()
    ready(page)
    assert "저장본" in page.inner_text("#view-today"), "깨진 저장본을 고쳐 읽지 못함"


def flow_multiple_goals_switch_and_delete(page, shot):
    fresh(page)
    make_goal(page, title="첫 번째 목표", mids=())
    tab(page, "goals")
    quick_goal(page, "두 번째 목표", 20)
    opts = page.locator("#goalPick option").all_inner_texts()
    assert len(opts) == 3 and opts[0].startswith("모든 목표") and "두 번째 목표" in page.locator(".hero h1").inner_text(), f"새 목표로 바뀌지 않음: {opts}"
    pick(page, "첫 번째")
    assert page.locator(".hero h1").inner_text() == "첫 번째 목표", "목표 고르기가 안 됨"
    pick(page, "모든 목표")
    assert page.locator(".goalsec").count() >= 1, "모든 목표 보기에 목표별 묶음이 없음"
    tab(page, "plan")
    assert page.locator(".chooser button").count() == 2, "모든 목표일 때 역산 화면에서 목표를 고르게 하지 않음"
    page.locator(".chooser button", has_text="첫 번째 목표").click()
    assert page.locator(".flow .fbox.goal").count() == 1 and "첫 번째 목표" in page.locator(".flow .fbox.goal").inner_text(), "고른 목표의 역산(순서도)이 안 나옴"
    page.click("#pvList")
    assert page.locator(".chain .node.goal").count() == 1, "고른 목표의 역산 목록이 안 나옴"
    tab(page, "goals")
    page.locator(".goal-item", has_text="두 번째 목표").locator("button", has_text="지우기").click()
    page.click("#sheet .btn.primary")
    assert page.locator(".goal-item").count() == 1, "목표가 지워지지 않음"
    page.reload()
    ready(page)
    assert page.locator("#goalPick option").count() == 1, "새로고침 후 지운 목표가 돌아옴"


def flow_edited_sample_asks_before_delete(page, shot):
    """고쳐 쓴 예시는 새 목표를 만들 때 묻고, '남겨 두기'면 내 목표로 남음(보류 6)"""
    ready(page)
    rows(page).locator(".chk[aria-pressed='false']").first.click()   # 예시를 써 봄
    page.locator("button", has_text="내 목표 세우기").click()
    page.fill("#wzTitle", "새 목표")
    page.fill("#wzDeadline", kst(30))
    wz_next(page)
    page.click(".kindc[data-kind='steps']")
    wz_next(page)
    wz_next(page)
    page.wait_for_selector("#sheet:not([hidden])", timeout=5000)
    assert "예시 목표를 고쳐 쓰셨네요" in page.inner_text("#sheet"), "고쳐 쓴 예시를 묻지 않고 지움"
    page.click("#sheet button:has-text('남겨 두기')")
    st = saved(page)
    assert [g["title"] for g in st["goals"]] == ["토익 850점 받기", "새 목표"], f"예시가 남지 않음: {[g['title'] for g in st['goals']]}"
    assert not any(g.get("sample") for g in st["goals"]), "남긴 예시에 '예시' 표시가 남음"


def flow_empty_states(page, shot):
    fresh(page)
    assert "아직 목표가 없어요" in page.inner_text("#view-today"), "목표가 없을 때 안내가 없음"
    tab(page, "plan")
    assert page.locator("#view-plan button", has_text="목표 세우기").count() == 1
    tab(page, "sched")
    assert page.locator("#view-sched button", has_text="목표 세우기").count() == 1
    tab(page, "today")
    make_goal(page, title="할 일 없는 목표", mids=(), tasks=0)
    # 10/21부터: 할 일이 없어도 그 요일에 고른 시간만큼 15분 칸이 생기고, 나누는 길을 알려 줌
    wi, _ = wd_today()
    quota = saved(page)["goals"][0]["avail"][wi] // 15
    r = rows(page)
    assert r.count() == quota and r.filter(has_text="할 일 없는 목표").count() == quota, f"할 일이 없는 목표에 요일 시간만큼 15분 칸이 없음({quota}칸): {page.inner_text('#view-today')[:300]}"
    assert "할 일을 적으면 15분 칸이 그 할 일로 채워지고" in page.inner_text("#view-today"), "할 일이 없을 때 나누는 안내가 없음"
    assert page.locator("#view-today .dfoot button", has_text="15분 할 일 적기").count() == 1, "할 일 적기 버튼이 없음"


def flow_long_text_and_big_numbers(page, shot):
    page.set_viewport_size({"width": 320, "height": 640})
    fresh(page)
    long = "아주아주긴목표이름입니다" * 6
    make_goal(page, title=long, days=200, mids=(("중간" * 30, 100),), tasks=1)
    page.evaluate(f"""() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); const g = s.goals[0];
        for (let i = 0; i < 40; i++) g.steps[0].tasks.push({{id: 'big' + i, title: '긴 할 일 '.repeat(8) + i, blocks: 32}});
        localStorage.setItem('{KEY}', JSON.stringify(s)); }}""")
    page.reload()
    ready(page)
    for name in ("today", "plan", "sched", "goals"):
        tab(page, name)
        ok = page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
        assert ok, f"{name} 화면에 가로 스크롤이 생김"
    tab(page, "plan")
    box = page.evaluate("""() => { const t = document.querySelector('.task'), sq = t.querySelector('.sq'), c = t.closest('.step');
        return {sq: sq.getBoundingClientRect().width, task: t.getBoundingClientRect().right, card: c.getBoundingClientRect().right,
                title: (() => { const a = document.querySelector('textarea.step-title'); return a.scrollHeight <= a.clientHeight + 2; })()}; }""")
    assert box["sq"] > 20, f"320px에서 15분 칸 그림 폭이 0(보류 12): {box}"
    assert box["task"] <= box["card"] + 1, f"320px에서 할 일 줄이 카드를 넘침: {box}"
    assert box["title"], "320px에서 단계 이름이 잘림(줄바꿈 안 됨)"
    tab(page, "today")
    assert "30분" in page.get_attribute(".mosaic", "aria-label"), "칸이 아주 많을 때 모자이크를 30분 단위로 줄이지 않음"
    hs = rows(page).evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().height))")
    assert hs and max(hs) <= 50, f"320px·긴 이름에서 15분 칸이 높아짐: {hs[:6]}"


def flow_new_day_keeps_progress(page, shot):
    page.clock.install(time=datetime.now(ZoneInfo("Asia/Seoul")).replace(hour=21, minute=0, second=0, microsecond=0))
    page.reload()
    ready(page)
    rows(page).locator(".chk[aria-pressed='false']").first.click()
    total = done_minutes(page)
    page.clock.fast_forward("05:00:00")   # 다음 날 새벽 2시
    page.reload()
    ready(page)
    assert done_minutes(page) == total, "날짜가 바뀌었더니 끝낸 시간이 달라짐"
    assert rows(page).locator(".chk[aria-pressed='true']").count() == 0, "어제 끝낸 칸이 오늘 목록에 끝냄으로 남음"
    assert rows(page).count() >= 1, "다음 날 오늘 목록이 비어 있음"


def flow_overdue_step_alert(page, shot):
    ready(page)
    page.evaluate(f"""() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); const g = s.goals[0];
        const d = new Date(Date.now() - 3 * 864e5).toLocaleDateString('sv-SE', {{timeZone: 'Asia/Seoul'}}); g.steps[0].due = d;
        localStorage.setItem('{KEY}', JSON.stringify(s)); }}""")
    page.reload()
    ready(page)
    text = page.inner_text("#view-today")
    assert "마감" in text and "지났는데" in text, f"마감이 지난 중간 목표 경고가 없음: {text[:200]}"
    page.locator(".alert button", has_text="날짜 고치기").first.click()
    page.wait_for_selector("#dsDate", timeout=3000)
    page.fill("#dsDate", kst(5))
    page.click("#dsOk")
    page.wait_for_timeout(100)
    assert "지났는데" not in page.inner_text("#view-today"), "날짜를 고쳤는데 마감 지남 경고가 남음"


def flow_step_without_tasks_still_shows_today(page, shot):
    """할 일 없이 중간 목표만 있는 목표(오늘 마감)도 오늘·일정·순서도에 보이고, 거기서 바로 할 일을 적고 끝냄을 누름"""
    fresh(page)
    make_goal(page, title="한식조리기능사", days=40, mids=(("필기 합격", 20), ("필기 원서 접수", 0)), tasks=0)
    st = saved(page)["goals"][0]
    s_today = [s for s in st["steps"] if s["title"] == "필기 원서 접수"][0]
    s_next = [s for s in st["steps"] if s["title"] == "필기 합격"][0]
    assert s_today["due"] == kst(0), f"오늘 마감 중간 목표가 안 만들어짐: {s_today}"
    mr = page.locator("#view-today .mrow")
    assert mr.count() == 1 and "오늘 마감" in mr.inner_text() and "필기 원서 접수" in mr.inner_text(), f"오늘 마감 중간 목표가 오늘 화면에 없음: {page.inner_text('#view-today')[:300]}"
    assert "15분 할 일이 없어요" in mr.inner_text(), "할 일이 없다는 안내가 없음"
    # 일정: 오늘 주황 상자 안에 마감 표시
    tab(page, "sched")
    today_box = page.locator(".day.is-today")
    assert today_box.count() == 1, "할 일 없이 오늘 마감만 있는데 오늘 상자가 없음"
    assert today_box.locator(".mile", has_text="필기 원서 접수").count() == 1, f"오늘 마감 표시가 오늘 상자 밖에 있음: {page.inner_text('#view-sched')[:300]}"
    assert "15분 ×" in today_box.inner_text() and "필기 원서 접수" in today_box.inner_text(), f"일정 오늘 상자에 요일별 시간만큼 지금 단계가 안 나옴: {today_box.inner_text()}"
    assert today_box.locator("button", has_text="15분 할 일 적기").count() == 1, "일정의 마감 표시에서 할 일을 적으러 갈 수 없음"
    quiet(page, top=True)
    shot("notask-sched", store=False)
    # 순서도: 할 일 없는 단계(오늘·앞으로)에 '＋ 15분 할 일 적기' 가지
    tab(page, "plan", flow=True)
    adds = page.locator(".flow .fchip.add")
    assert adds.count() == 2, f"할 일 없는 단계 2개에 '할 일 적기' 가지가 없음: {adds.count()}"
    page.locator(".flow .frow", has_text="필기 합격").locator(".fchip.add").click()
    assert page.locator("#pvList").get_attribute("aria-pressed") == "true", "할 일 적기를 눌렀는데 목록으로 안 바뀜"
    focused = page.evaluate("document.activeElement && document.activeElement.id")
    assert focused == "add-" + s_next["id"], f"그 단계의 할 일 칸에 커서가 안 감: {focused}"
    page.keyboard.type("필기 기출 1회")
    page.keyboard.press("Enter")
    # 모든 목표 보기: 다른 목표가 있어도 오늘 마감이 묶음으로 보임
    tab(page, "goals")
    make_goal(page, title="토익 시험", days=30, mids=(), tasks=1)
    pick(page, "모든 목표")
    sec = page.locator(".goalsec", has_text="한식조리기능사")
    assert sec.count() == 1 and sec.locator(".mrow").count() == 1, f"모든 목표 보기에서 오늘 마감 중간 목표가 빠짐: {page.inner_text('#view-today')[:400]}"
    quiet(page, top=True)
    shot("notask-today", store=False)
    sec.locator(".mrow button", has_text="할 일 적기").click()
    focused = page.evaluate("document.activeElement && document.activeElement.id")
    assert focused == "add-" + s_today["id"], f"오늘 화면 '할 일 적기'가 그 단계 칸으로 안 감: {focused}"
    page.keyboard.type("원서 사진 준비")
    page.keyboard.press("Enter")
    tab(page, "today")
    assert rows(page).filter(has_text="원서 사진 준비").count() >= 1, "할 일을 적었는데 오늘 15분 칸이 안 생김"
    mr = page.locator("#view-today .mrow")
    assert mr.count() == 1 and mr.locator("button", has_text="할 일 적기").count() == 0, "할 일을 적었는데 '할 일 없음'이 남음"
    # 끝냄 → 다음 단계 칸이 오늘부터 놓임(끝낸 단계가 다음 단계를 막지 않음)
    mr.locator("button", has_text="끝냄").click()
    assert page.locator("#view-today .mrow").count() == 0, "끝냄을 눌렀는데 오늘 마감 줄이 남음"
    after = [s for s in saved(page)["goals"][0]["steps"] if s["id"] == s_today["id"]][0]
    assert after.get("done"), "오늘 화면 끝냄이 저장되지 않음"
    assert rows(page).filter(has_text="필기 기출 1회").count() >= 1, f"앞 단계를 끝냈는데 다음 단계 칸이 오늘 안 놓임: {rows(page).all_inner_texts()}"


def flow_goals_without_tasks_get_daily_15(page, shot):
    """15분 할 일이 없는 목표도 오늘 화면에 단계 이름 15분 칸이 생겨 체크·타이머·'15분 더'가 되고, 새로고침해도 남음(10/20·10/21 LEE 요청)"""
    page.clock.install()
    fresh(page)
    make_goal(page, title="한식요리자격증", days=30, mids=(("필기 공부", 10),), tasks=0)
    tab(page, "goals")
    make_goal(page, title="토익 시험", days=30, mids=(("단어장 1회독", 8),), tasks=1)
    tab(page, "goals")   # 목표 카드에서 요일별 시간 → '매일 15분'
    page.click("button[aria-label='한식요리자격증 요일별 시간']")
    page.locator("#sheet button", has_text="매일 15분").click()
    assert [g for g in saved(page)["goals"] if g["title"] == "한식요리자격증"][0]["avail"] == [15] * 7, "요일별 시간 '매일 15분'이 저장되지 않음"
    page.locator("#sheet button", has_text="닫기").click()
    tab(page, "today")
    pick(page, "모든 목표")
    assert page.locator("#view-today .notask").count() == 0, "할 일 없는 목표를 '오늘 화면에 안 나오는 목표'로 따로 빼 둠"
    sec = page.locator(".goalsec", has_text="한식요리자격증")
    assert sec.count() == 1, f"할 일 없는 목표가 모든 목표 오늘 화면에 없음: {page.inner_text('#view-today')[:400]}"
    d = sec.locator(".blk.daily")
    assert d.count() == 1 and "필기 공부" in d.inner_text() and "지금 단계 · 15분" in d.inner_text(), f"지금 단계 이름으로 15분 칸이 안 생김: {sec.inner_text()}"
    assert "0/1" in sec.locator(".gh").inner_text(), f"목표 묶음 머리에 0/1이 아님: {sec.locator('.gh').inner_text()}"
    head = page.inner_text("#view-today .today-head")
    d.locator(".chk").click()
    assert d.locator(".chk").get_attribute("aria-pressed") == "true", "단계 이름 15분 칸을 눌러도 체크가 안 됨"
    assert page.inner_text("#view-today .today-head") != head, "단계 이름 15분을 체크해도 오늘 합계가 그대로"
    g0 = [g for g in saved(page)["goals"] if g["title"] == "한식요리자격증"][0]
    assert len(g0.get("dlog", [])) == 1 and g0["dlog"][0]["d"] == kst(0), f"단계 이름 15분 체크가 저장되지 않음: {g0.get('dlog')}"
    quiet(page, top=True)
    shot("daily-15")
    more = sec.locator(".dfoot button", has_text="15분 더")
    assert more.count() == 1, "단계 이름 15분을 다 했는데 '＋ 15분 더'가 없음"
    more.click()
    d = page.locator(".goalsec", has_text="한식요리자격증").locator(".blk.daily")
    assert d.count() == 2 and d.nth(1).locator(".chk").get_attribute("aria-pressed") == "false", "'＋ 15분 더'로 칸이 하나 더 생기지 않음"
    page.reload()
    ready(page)
    d = page.locator(".goalsec", has_text="한식요리자격증").locator(".blk.daily")
    assert d.count() == 2 and d.first.locator(".chk").get_attribute("aria-pressed") == "true", "새로고침했더니 단계 이름 15분 칸·체크가 사라짐"
    # 타이머로 둘째 칸 끝내기
    d.nth(1).locator(".play").click()
    assert "필기 공부" in page.inner_text("#timerCard"), "단계 이름 15분 타이머 카드에 단계 이름이 없음"
    page.clock.fast_forward("15:05")
    page.wait_for_function("document.getElementById('timerCard')?.classList.contains('end')", timeout=5000)
    page.click("#timerCard button:has-text('끝냄')")
    g0 = [g for g in saved(page)["goals"] if g["title"] == "한식요리자격증"][0]
    assert sorted(e["k"] for e in g0["dlog"]) == [1, 2], f"타이머로 끝낸 단계 이름 15분이 기록되지 않음: {g0['dlog']}"
    # 다시 누르면 체크 취소
    d = page.locator(".goalsec", has_text="한식요리자격증").locator(".blk.daily")
    d.nth(1).locator(".chk").click()
    g0 = [g for g in saved(page)["goals"] if g["title"] == "한식요리자격증"][0]
    assert len(g0["dlog"]) == 1, f"단계 이름 15분 체크 취소가 안 됨: {g0['dlog']}"
    # 목표 하나 볼 때: 이번 달 횟수 + 단계별로 나누는 길
    page.locator(".goalsec .gh", has_text="한식요리자격증").click()
    assert "이번 달 15분 칸 1번" in page.inner_text(".hero"), f"목표 화면에 15분 칸 횟수가 없음: {page.inner_text('.hero')}"
    s1 = [s for s in g0["steps"] if s["title"] == "필기 공부"][0]
    page.locator("#view-today .dfoot button", has_text="15분 할 일 적기").click()
    assert page.evaluate("document.activeElement && document.activeElement.id") == "add-" + s1["id"], "할 일 적기가 지금 단계 칸으로 안 감"
    # 지금 단계 할 일을 비운 목표도 단계 이름으로 단계 이름 15분
    page.evaluate(f"""() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); const g = s.goals[1];
        g.steps.find(x => x.title === '단어장 1회독').tasks = []; localStorage.setItem('{KEY}', JSON.stringify(s)); }}""")
    page.reload()
    ready(page)
    pick(page, "토익 시험")
    wi, _ = wd_today()
    quota = [g for g in saved(page)["goals"] if g["title"] == "토익 시험"][0]["avail"][wi] // 15
    dd = rows(page).filter(has_text="지금 단계 · 15분")
    assert dd.count() == quota and dd.filter(has_text="단어장 1회독").count() == quota, f"할 일을 비운 단계에 요일 시간만큼({quota}칸) 단계 이름 칸이 없음: {page.inner_text('#view-today')[:300]}"
    tab(page, "goals")
    assert "15분 칸 1번" in page.locator(".goal-item", has_text="한식요리자격증").inner_text(), "목표 목록에 15분 칸 횟수가 없음"


def flow_no_block_today_pulls_next_block(page, shot):
    """오늘 요일을 '쉼'으로 고르면 그 목표는 오늘 쉬고, '＋ 15분 하기'를 누르면 다음 칸을 오늘로 당겨 와 체크하면 진도에 들어감"""
    fresh(page)
    make_goal(page, title="자격증 필기 합격", days=40, mids=(("핵심 요약 1회독", 20),), tasks=2)
    _, wn = wd_today()
    tab(page, "sched")
    pick_time(page.locator(f"select[aria-label='{wn}요일 시간']"), 0)
    tab(page, "today")
    text = page.inner_text("#view-today")
    assert rows(page).count() == 0 and f"오늘({wn}요일)은 이 목표를 쉬는 날이에요" in text, f"쉼으로 고른 요일인데 칸이 나오거나 안내가 없음: {text[:300]}"
    page.locator("#view-today button", has_text="15분 하기").click()
    r = rows(page)
    assert r.count() == 1 and "원래" in r.inner_text(), f"'＋ 15분 하기'로 다음 칸이 안 당겨짐: {page.inner_text('#view-today')[:300]}"
    before = done_minutes(page)
    r.locator(".chk").click()
    assert done_minutes(page) == before + 15, "당겨 온 칸을 체크했는데 끝낸 시간에 안 들어감"
    st = saved(page)["goals"][0]
    assert len(st["log"]) == 1 and not st.get("dlog"), f"당겨 온 칸은 할 일 기록(log)으로 남아야 함: log={st['log']} dlog={st.get('dlog')}"
    text = page.inner_text("#view-today")
    assert "오늘 몫을 다 했어요" in text and page.locator("#view-today button", has_text="15분 더").count() == 1, f"당겨 온 칸을 끝낸 뒤 '＋ 15분 더'가 없음: {text[:300]}"


def flow_wizard_typed_task_not_lost(page, shot):
    """새 마법사: 방식을 고르지 않으면 넘어가지 않고, 4단계에서 구간·요일을 보여 주며, '쉼'만 고르면 완료되지 않음"""
    fresh(page)
    page.locator("button:visible", has_text=re.compile("목표 세우기")).first.click()
    page.fill("#wzTitle", "한식 실기")
    page.fill("#wzDeadline", kst(30))
    wz_next(page)
    wz_next(page)   # 방식을 안 고르고 다음
    assert page.locator(".kindc").count() == 3, "방식을 안 골랐는데 넘어감"
    page.click(".kindc[data-kind='steps']")
    page.fill("#wzMid", "재료 손질 연습")
    page.fill("#wzMidDate", kst(10))
    page.click(".ask button")
    wz_next(page)
    sm = page.inner_text(".sum")
    assert "재료 손질 연습" in sm and "한식 실기" in sm, f"4단계에 구간마다 나오는 단계가 없음: {sm}"
    for wd in "월화수목금토일":
        pick_time(page.locator(f"#sheet select[aria-label='{wd}요일 시간']"), 0)
    wz_next(page)
    assert page.is_visible("#sheet"), "요일별 시간이 모두 쉼인데 완료됨"
    pick_time(page.locator("#sheet select[aria-label='월요일 시간']"), 30)
    wz_next(page)
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    st = saved(page)["goals"][0]
    assert st["plan"]["kind"] == "steps" and st["avail"][1] == 30 and sum(st["avail"]) == 30, f"4단계에서 고른 요일별 시간이 저장되지 않음: {st['avail']}"


def flow_wizard_draft_survives_reload(page, shot):
    """Claude 앱에 다녀오는 사이 앱이 닫혀도 만들던 목표가 이어짐 · 그만둘 때는 확인(보류 7)"""
    ready(page)
    page.locator("button", has_text="내 목표 세우기").click()
    page.fill("#wzTitle", "책 원고 1권 쓰기")
    page.reload()   # 1단계에서 적던 것도 남아야 함
    page.wait_for_selector("#sheet:not([hidden])", timeout=5000)
    assert page.input_value("#wzTitle") == "책 원고 1권 쓰기", "1단계에서 적던 목표가 사라짐"
    page.fill("#wzDeadline", kst(90))
    page.press("#wzDeadline", "Enter")   # Enter로 다음
    page.click(".kindc[data-kind='steps']")
    page.wait_for_selector("#wzMid", timeout=3000)
    page.fill("#wzMid", "초고 절반")
    page.fill("#wzMidDate", kst(45))
    page.click(".ask button")
    page.reload()
    page.wait_for_selector("#sheet:not([hidden])", timeout=5000)
    assert "3 / 4" in page.inner_text("#panel"), "다시 열었을 때 만들던 단계로 돌아오지 않음"
    items = page.locator(".wz-list li").all_inner_texts()
    assert "책 원고 1권 쓰기" in items[0] and "초고 절반" in items[1], f"만들던 내용이 사라짐: {items}"
    page.keyboard.press("Escape")
    assert "버릴까요" in page.inner_text("#panel"), "Esc로 확인 없이 버림"
    page.click("#panel button:has-text('계속 만들기')")
    assert "3 / 4" in page.inner_text("#panel"), "'계속 만들기'로 돌아오지 않음"
    wz_next(page)
    assert "4 / 4" in page.inner_text("#panel"), "4단계로 넘어가지 않음"
    page.click("#panel button:has-text('그만두기')")
    page.click("#panel button:has-text('버리기')")
    page.reload()
    ready(page)
    assert page.locator("#sheet").is_hidden(), "그만둔 목표 만들기가 다시 열림"
    assert saved(page).get("draft") is None, "그만뒀는데 만들던 내용이 저장소에 남음"


def flow_accessibility_basics(page, shot):
    """백업 가져오기는 Tab으로 가는 버튼, 입력칸 이름, 창을 닫으면 초점 복귀, 날짜 하한(보류 13)"""
    ready(page)
    tab(page, "goals")
    tag = page.evaluate("document.getElementById('importBtn').tagName")
    assert tag == "BUTTON", "백업 가져오기가 버튼이 아님(Tab으로 갈 수 없음)"
    btn = page.locator(".goal-item button", has_text="지우기").first
    btn.focus()
    btn.click()
    page.click("#sheet .btn:has-text('취소')")
    page.wait_for_timeout(100)
    assert page.evaluate("document.activeElement && document.activeElement.textContent.trim()") == "지우기", "확인 창을 닫았는데 초점이 원래 버튼으로 돌아오지 않음"
    tab(page, "today")
    page.locator("button", has_text="내 목표 세우기").click()
    assert page.get_attribute("#wzDeadline", "min") == kst(1), "마감 달력의 첫 날이 내일이 아님"
    page.fill("#wzTitle", "접근성 목표")
    page.fill("#wzDeadline", kst(30))
    page.press("#wzTitle", "Enter")
    page.press("#wzDeadline", "Enter")
    page.click(".kindc[data-kind='steps']")
    page.wait_for_selector("#wzMid", timeout=3000)
    assert page.get_attribute("#wzMid", "aria-label"), "중간 목표 입력칸에 이름이 없음"
    assert page.get_attribute("#wzMidDate", "min") == kst(0), "중간 목표 날짜에 지난 날짜를 고를 수 있음"
    h = page.evaluate("document.getElementById('wzMid').getBoundingClientRect().height")
    assert h >= 44, f"중간 목표 입력칸 높이가 44px보다 작음: {h}"


# ---------- 목표까지 연동 ----------
def flow_sync_connect_imports_mokpyo_goals(page, shot):
    srv_reset()
    srv_put_mk(mk_snapshot())
    ready(page)
    connect(page)
    assert "맞춤" in page.inner_text("#syncState"), f"연결 뒤 상태가 이상함: {page.inner_text('#syncState')}"
    st = saved(page)
    linked = [g for g in st["goals"] if g.get("src")]
    assert sorted(g["src"] for g in linked) == ["g3", "g7"], f"진행 중·계획 목표만 들어와야 함(보류는 빼고): {[g.get('src') for g in linked]}"
    assert not any(g.get("sample") for g in st["goals"]), "목표까지 목표가 들어왔는데 손대지 않은 예시가 남음"
    assert st["current"] == "*", "처음 받으면 모든 목표 보기여야 함"
    g3 = [g for g in linked if g["src"] == "g3"][0]
    assert [s.get("src") for s in g3["steps"] if not s.get("final")] == ["s-a", "s-b", "s-c"], "목표까지 단계가 그대로 들어오지 않음"
    tab(page, "today")
    assert page.locator(".goalsec").count() == 0 and "설정 전 목표 2개" in page.inner_text("#preBox"), f"설정 전 목표가 오늘 화면에 나오거나 따로 알려 주지 않음: {page.inner_text('#view-today')[:300]}"
    page.locator("#preBox button[aria-label='한국사 심화 2급 설정하기']").click()
    wz_next(page)
    page.click(".kindc[data-kind='steps']")
    wz_next(page)
    wz_next(page)
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    setup_goal(page, "기타 솔로")
    pick(page, "모든 목표")
    assert page.locator(".goalsec").count() == 2, "모든 목표 오늘 화면에 목표별 묶음이 2개가 아님"
    assert page.locator(".blk", has_text="기본서 2쪽").count() == 1, "목표까지 하루 분량(기본서 2쪽)이 오늘 타일로 안 나옴"
    assert page.locator(".blk", has_text="연습 시간 20분").count() == 2, "20분짜리 하루 분량이 15분 칸 2개로 나뉘지 않음"
    quiet(page)
    shot("sync-today-all")
    page.locator(".blk", has_text="기본서 2쪽").locator(".chk").click()
    wait_synced(page)
    page.wait_for_timeout(300)
    d = srv_dump()["data"]
    p = d["progress"]["goals"]["g3"]
    ym = kst(0)[:7]
    assert p["credits"]["m-a"][ym] == 2, f"체크한 하루 분량이 실적으로 올라가지 않음: {p}"
    assert p["minutes"][ym] == 15, f"15분 기록이 올라가지 않음: {p}"
    assert "목표까지와 맞춤" in page.inner_text("#view-today"), "오늘 화면에 맞춘 시각이 안 보임"


def flow_sync_wrong_code_and_unreachable(page, shot):
    srv_reset()
    ready(page)
    connect(page, code="틀린코드")
    msg = page.inner_text("#syncCard [role=alert]")
    assert "접속 코드가 맞지 않아요" in msg, f"틀린 코드 안내가 없음: {msg}"
    assert not saved(page)["sync"]["code"], "틀린 코드를 저장함"
    page.fill("#syncServer", "http://localhost:9")
    page.fill("#syncCode", CODE)
    page.click("#syncConnect")
    page.wait_for_function("(() => { const m = document.querySelector('#syncCard [role=alert]:not([hidden])'); return m && /연결하지 못했어요/.test(m.textContent); })()", timeout=20000)
    assert not saved(page)["sync"]["server"], "연결되지 않는 서버를 저장함"


def flow_sync_settings_link_prefills_server(page, shot):
    srv_reset()
    page.goto(page.url.split("#")[0] + "#server=" + urllib.request.quote(SYNC, safe=""))
    page.wait_for_selector("#syncCard", timeout=5000)
    assert page.input_value("#syncServer") == SYNC, "설정 링크로 열었는데 서버 주소가 안 채워짐"
    assert "#server=" in page.url, "주소창에서 서버 주소가 사라짐 — 이 주소를 다른 기기로 보내면 빈칸이 됨"
    page.wait_for_function("document.activeElement && document.activeElement.id === 'syncCode'", timeout=3000)
    # 코드까지 든 링크로 열어도 주소창에는 코드가 남지 않아야 함
    page.goto(page.url.split("#")[0] + "#server=" + urllib.request.quote(SYNC, safe="") + "&code=" + urllib.request.quote(CODE, safe=""))
    page.wait_for_function("typeof state !== 'undefined' && state.sync.code", timeout=5000)
    assert "code" not in page.url, f"접속 코드가 주소창에 남음: {page.url}"
    assert "#server=" in page.url, "코드 링크로 연 뒤 서버 주소가 주소창에서 사라짐"


def flow_share_link_sets_up_another_device(page, shot):
    """폰에서 연결한 뒤 '다른 기기 연결 링크' → 컴퓨터에서 열면 서버 칸이 채워지고 코드만 넣으면 같은 계획"""
    srv_reset()
    srv_put_mk(mk_snapshot())
    ready(page)
    connect(page)
    assert "#server=" in page.url and "code" not in page.url, f"연결 뒤 주소창 상태가 이상함: {page.url}"
    card = page.locator("#syncCard")
    assert "서버 localhost:8791" in card.inner_text(), "연결된 서버 주소가 카드에 안 보임"
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.click("#syncShareBtn")
    page.wait_for_function("(() => { const t = document.getElementById('toast'); const s = document.getElementById('sheet'); return (t && !t.hidden && /복사/.test(t.textContent)) || (s && !s.hidden); })()", timeout=3000)
    link = page.evaluate("navigator.clipboard.readText().catch(() => '')") or page.input_value("#panel input")
    assert link.endswith("#server=" + urllib.request.quote(SYNC, safe="")), f"연결 링크가 이상함: {link}"
    assert "code" not in link, "연결 링크에 접속 코드가 들어감"
    # 새 기기(저장 내용 없음)에서 링크 열기
    ctx2 = page.context.browser.new_context(viewport={"width": 390, "height": 844})
    p2 = ctx2.new_page()
    errs = []
    p2.on("pageerror", lambda e: errs.append(str(e)))
    p2.goto(link)
    p2.wait_for_selector("#syncCard", timeout=5000)
    assert p2.input_value("#syncServer") == SYNC, "다른 기기에서 링크를 열었는데 서버 칸이 비어 있음"
    p2.fill("#syncCode", CODE)
    p2.click("#syncConnect")
    p2.wait_for_function("(() => { const s = document.getElementById('syncState'); return s && /맞춤/.test(s.textContent); })()", timeout=10000)
    st2 = json.loads(p2.evaluate(f"localStorage.getItem('{KEY}')"))
    assert sorted(g.get("src") for g in st2["goals"] if g.get("src")) == ["g3", "g7"], "다른 기기에서 목표까지 목표가 안 들어옴"
    assert not errs, f"다른 기기 화면에서 JS 오류: {errs}"
    ctx2.close()
    # 연동을 끊으면 주소창의 서버 주소도 지움(다시 열었을 때 옛 서버가 되살아나지 않게)
    tab(page, "goals")
    page.locator("#syncCard button", has_text="연동 끊기").click()
    page.click("#sheet .btn.primary")
    page.wait_for_timeout(200)
    assert "#server" not in page.url, "연동을 끊었는데 주소창에 서버 주소가 남음"
    page.reload()
    ready(page)
    assert not saved(page)["sync"]["server"], "연동을 끊고 새로 열었는데 서버가 되살아남"


def flow_linked_plan_is_readonly_with_tasks(page, shot):
    srv_reset()
    srv_put_mk(mk_snapshot())
    ready(page)
    connect(page)
    pick(page, "한국사")
    tab(page, "plan")
    assert page.locator(".linknote").count() == 1, "목표까지에서 가져온 계획이라는 안내가 없음"
    assert page.locator(".insert").count() == 0, "목표까지 계획에 중간 목표 추가 버튼이 보임"
    assert page.locator("textarea.step-title").count() == 0, "목표까지 단계 이름을 폰에서 고칠 수 있게 됨"
    assert page.locator(".chain input.date-in").count() >= 2, "목표까지 목표의 날짜를 폰에서 바꿀 칸이 없음"
    assert page.locator(".daily li", has_text="기본서 읽기").count() == 1, "하루 분량 시간 정하기가 없음"
    quiet(page, top=True)
    shot("linked-plan")
    node = page.locator(".chain .node", has_text="원서접수").first
    node.locator("button", has_text="끝냄").click()
    node = page.locator(".chain .node", has_text="원서접수").first
    assert node.locator("button[aria-pressed='true']").count() == 1, "단계 끝냄 표시가 안 됨"
    n2 = page.locator(".chain .node", has_text="기본서 1회독").first
    n2.locator(".addtask input").fill("1단원 정리")
    n2.locator(".addtask button", has_text="할 일 추가").click()
    pick_time(page.locator(".daily li", has_text="기본서 읽기").locator("select"), 30)
    setup_goal(page, "한국사")
    tab(page, "today")
    assert page.locator(".blk", has_text="기본서 2쪽").count() == 2, "하루 분량을 30분으로 늘렸는데 15분 칸이 2개가 아님"
    wait_synced(page)
    page.wait_for_timeout(300)
    d = srv_dump()["data"]
    assert d["progress"]["goals"]["g3"]["steps"] == ["s-a"], f"끝낸 단계가 진행으로 올라가지 않음: {d['progress']['goals']['g3']}"
    g3 = [g for g in d["data"]["goals"] if g.get("src") == "g3"][0]
    assert any(k["title"] == "1단원 정리" for s in g3["steps"] for k in s["tasks"]), "폰에서 더한 15분 할 일이 서버에 없음"


def flow_mokpyo_update_keeps_phone_tasks(page, shot):
    srv_reset()
    srv_put_mk(mk_snapshot(at="2026-10-01T00:00:00Z"))
    ready(page)
    connect(page)
    pick(page, "한국사")
    tab(page, "plan")
    n2 = page.locator(".chain .node", has_text="기본서 1회독").first
    n2.locator(".addtask input").fill("1단원 정리")
    n2.locator(".addtask button", has_text="할 일 추가").click()
    n3 = page.locator(".chain .node", has_text="기출 8회분").first
    n3.locator(".addtask input").fill("기출 1회")
    n3.locator(".addtask button", has_text="할 일 추가").click()
    snap = mk_snapshot(at="2026-10-02T00:00:00Z")
    g3 = snap["goals"][0]
    g3["steps"][1]["t"] = "기본서 1회독 (개정판)"          # 이름 바꿈
    g3["steps"][0]["done"] = True                          # 목표까지에서 완료
    g3["steps"] = [s for s in g3["steps"] if s["sid"] != "s-c"] + [{"sid": "s-d", "t": "모의고사", "due": kst(100), "done": False}]   # 기출 단계 지움(할 일 있음) + 새 단계
    snap["goals"] = [g3]                                   # 기타 목표는 목표까지에서 지움
    srv_put_mk(snap)
    tab(page, "goals")
    page.click("#syncNowBtn")
    page.wait_for_function(f"JSON.parse(localStorage.getItem('{KEY}')).mk.at === '2026-10-02T00:00:00Z'", timeout=8000)
    st = saved(page)
    g = [x for x in st["goals"] if x.get("src") == "g3"][0]
    by = {s.get("src"): s for s in g["steps"]}
    assert by["s-b"]["title"] == "기본서 1회독 (개정판)" and by["s-b"]["tasks"][0]["title"] == "1단원 정리", "단계 이름이 바뀌면서 폰 할 일이 사라짐"
    assert by["s-a"].get("mkDone"), "목표까지에서 완료한 단계가 폰에 완료로 안 보임"
    assert by["s-c"].get("gone") and by["s-c"]["tasks"], "목표까지에서 지운 단계의 폰 할 일이 사라짐(빠짐 표시로 남아야 함)"
    assert "s-d" in by, "목표까지에 새로 생긴 단계가 안 들어옴"
    g7 = [x for x in st["goals"] if x.get("src") == "g7"][0]
    assert g7.get("gone"), "목표까지에서 지운 목표가 빠짐 표시가 안 됨"
    tab(page, "today")
    assert "기타 솔로" not in page.inner_text("#view-today"), "빠진 목표가 오늘 화면에 남음"


def flow_linked_date_edit_roundtrip(page, shot):
    """목표까지 목표의 날짜를 폰에서 바꾸면 진행에 실려 가고, 반영된 스냅숏이 오면 표시가 사라짐 · 목표까지가 따로 바꾸면 목표까지를 따름"""
    srv_reset()
    srv_put_mk(mk_snapshot(at="2026-10-01T00:00:00Z"))
    ready(page)
    connect(page)
    pick(page, "한국사")
    tab(page, "plan", flow=True)
    new_due = kst(150)
    page.locator(".flow .fbox.goal").click()
    page.wait_for_selector("#dsDate", timeout=3000)
    page.fill("#dsDate", new_due)
    page.click("#dsOk")
    page.locator(".flow .fbox", has_text="원서접수").first.click()
    page.fill("#dsDate", kst(25))
    page.click("#dsOk")
    assert page.locator(".flow .fbox.pend").count() == 2, "바꾼 날짜 표시가 안 보임"
    wait_synced(page)
    page.wait_for_timeout(300)
    ed = srv_dump()["data"]["progress"]["goals"]["g3"].get("edits")
    assert ed == {"due": new_due, "steps": {"s-a": kst(25)}}, f"바꾼 날짜가 진행에 제대로 안 실림: {ed}"

    def g3():
        return [x for x in saved(page)["goals"] if x.get("src") == "g3"][0]

    assert g3()["mkEdit"]["due"] == {"from": kst(120), "to": new_due}, f"바꾼 값 기록이 이상함: {g3().get('mkEdit')}"

    def push(snap, at):
        snap["at"] = at
        srv_put_mk(snap)
        tab(page, "goals")
        page.click("#syncNowBtn")
        page.wait_for_function(f"JSON.parse(localStorage.getItem('{KEY}')).mk.at === '{at}'", timeout=8000)
        page.wait_for_timeout(100)

    push(mk_snapshot(), "2026-10-02T00:00:00Z")   # 목표까지가 아직 반영 전(옛 날짜 그대로)
    g = g3()
    assert g.get("mkDue") == new_due and g["mkEdit"]["due"]["to"] == new_due, f"목표까지 반영 전인데 내가 바꾼 마감이 사라짐: {g.get('mkDue')} {g.get('mkEdit')}"
    assert [s for s in g["steps"] if s.get("src") == "s-a"][0]["due"] == kst(25), "목표까지 반영 전인데 바꾼 단계 날짜가 되돌아감"
    snap = mk_snapshot()
    snap["goals"][0]["due"] = new_due
    snap["goals"][0]["steps"][0]["due"] = kst(25)
    push(snap, "2026-10-03T00:00:00Z")            # 목표까지가 반영함
    assert "mkEdit" not in g3(), f"목표까지가 반영했는데 바꾼 값 표시가 남음: {g3().get('mkEdit')}"
    tab(page, "plan", flow=True)
    page.locator(".flow .fbox.goal").click()
    page.fill("#dsDate", kst(160))
    page.click("#dsOk")
    snap = mk_snapshot()
    snap["goals"][0]["due"] = kst(170)
    snap["goals"][0]["steps"][0]["due"] = kst(25)
    push(snap, "2026-10-04T00:00:00Z")            # 목표까지에서 따로 다른 날로 바꿈
    g = g3()
    assert g.get("mkDue") == kst(170) and "mkEdit" not in g, f"목표까지에서 따로 바꾼 날짜를 따르지 않음: {g.get('mkDue')} {g.get('mkEdit')}"
    assert "목표까지를 따랐어요" in (page.text_content("#toast") or ""), f"목표까지를 따랐다는 알림이 없음: {page.text_content('#toast')}"


def flow_new_goal_goes_to_mokpyo(page, shot):
    """연결된 기기에서 새 목표를 세우며 '목표까지에도 넣기' → 진행에 실려 가고, 목표까지가 pid를 붙여 돌려주면 연동 목표로 바뀜(할 일 유지·중복 없음)"""
    srv_reset()
    srv_put_mk(mk_snapshot(at="2026-10-01T00:00:00Z"))
    ready(page)
    connect(page)
    make_goal(page, title="독서 모임 발표", days=40, mids=(("발표 자료 초안", 20),), tasks=1, cat="배우기")
    g = [x for x in saved(page)["goals"] if x["title"] == "독서 모임 발표"][0]
    assert g.get("toMk") is True and g.get("cat") == "배우기", f"목표까지에도 넣기·분야가 저장되지 않음: {g.get('toMk')} {g.get('cat')}"
    wait_synced(page)
    page.wait_for_timeout(300)
    ng = srv_dump()["data"]["progress"].get("newGoals") or []
    assert len(ng) == 1 and ng[0]["pid"] == g["id"] and ng[0]["title"] == "독서 모임 발표" and ng[0]["cat"] == "배우기" and ng[0]["due"] == kst(40), f"새 목표가 진행에 안 실림: {ng}"
    assert [s["t"] for s in ng[0]["steps"]] == ["발표 자료 초안"], f"새 목표의 단계가 안 실림: {ng[0]['steps']}"
    snap = mk_snapshot()
    snap["goals"].append({"id": "g9", "pid": g["id"], "short": "발표", "cat": "배우기", "title": "독서 모임 발표", "start": kst(0), "due": kst(40), "status": "계획", "memo": "",
                          "steps": [{"sid": "s-n1", "pid": ng[0]["steps"][0]["pid"], "t": "발표 자료 초안", "due": kst(20), "done": False}], "metrics": []})
    snap["at"] = "2026-10-02T00:00:00Z"
    srv_put_mk(snap)
    tab(page, "goals")
    page.click("#syncNowBtn")
    page.wait_for_function(f"JSON.parse(localStorage.getItem('{KEY}')).mk.at === '2026-10-02T00:00:00Z'", timeout=8000)
    page.wait_for_timeout(100)
    same = [x for x in saved(page)["goals"] if x["title"] == "독서 모임 발표"]
    assert len(same) == 1, f"목표까지에 들어간 새 목표가 폰에서 {len(same)}개가 됨"
    x = same[0]
    assert x["id"] == g["id"] and x.get("src") == "g9" and not x.get("toMk"), f"폰 목표가 연동 목표로 안 바뀜: {x.get('src')} {x.get('toMk')}"
    s1 = [s for s in x["steps"] if s["title"] == "발표 자료 초안"][0]
    assert s1.get("src") == "s-n1" and s1["tasks"], "단계가 목표까지 단계와 이어지지 않았거나 15분 할 일이 사라짐"
    assert "목표까지에 들어갔어요" in (page.text_content("#toast") or ""), f"새 목표가 들어갔다는 알림이 없음: {page.text_content('#toast')}"
    wait_synced(page)
    page.wait_for_timeout(300)
    assert not srv_dump()["data"]["progress"].get("newGoals"), "연동된 뒤에도 새 목표로 또 보냄"


def flow_phone_goal_card_send_to_mokpyo(page, shot):
    """예전에 만든 폰 목표도 목표 화면에서 '목표까지에도 넣기'로 보낼 수 있고, 보내지 않기로 되돌릴 수 있음"""
    srv_reset()
    srv_put_mk(mk_snapshot())
    ready(page)
    make_goal(page, title="수영 1km", days=60, mids=(("자유형 200m", 30),), tasks=1)
    connect(page)
    card = page.locator(".goal-item", has_text="수영 1km")
    card.locator("button", has_text="목표까지에도 넣기").click()
    page.select_option("#tmCat", "건강")
    page.click("#tmOk")
    g = [x for x in saved(page)["goals"] if x["title"] == "수영 1km"][0]
    assert g.get("toMk") is True and g.get("cat") == "건강", "목표 화면에서 목표까지로 보내기가 저장되지 않음"
    card = page.locator(".goal-item", has_text="수영 1km")
    card.locator("button", has_text="보내지 않기").click()
    g = [x for x in saved(page)["goals"] if x["title"] == "수영 1km"][0]
    assert g.get("toMk") is False, "보내지 않기가 안 됨"


def flow_old_saved_data_still_loads(page, shot):
    """이번 업데이트 전 저장본(새 칸 없음)도 그대로 열리고 기록이 남음"""
    old = {"v": 2, "seen": True, "current": None, "goals": [{"id": "old1", "title": "예전 목표", "deadline": kst(30), "createdAt": kst(-5), "avail": [60] * 7,
           "steps": [{"id": "st1", "title": "예전 단계", "due": kst(10), "tasks": [{"id": "t1", "title": "예전 할 일", "blocks": 2}]},
                     {"id": "fin", "title": "예전 목표", "due": kst(30), "final": True, "tasks": []}],
           "log": [{"id": "l1", "d": kst(-1), "t": "t1", "k": 1}], "ilog": [], "ed": 1}], "del": {}, "imin": {}}
    page.evaluate(f"localStorage.setItem('{KEY}', JSON.stringify({json.dumps(old, ensure_ascii=False)}))")
    page.reload()
    ready(page)
    st = saved(page)
    assert len(st["goals"]) == 1 and st["goals"][0]["title"] == "예전 목표", "예전 저장본의 목표가 사라짐"
    assert st["goals"][0]["log"] == [{"id": "l1", "d": kst(-1), "t": "t1", "k": 1}], "예전 끝낸 기록이 사라지거나 바뀜"
    tab(page, "plan", flow=True)
    assert page.locator(".flow .fbox", has_text="예전 단계").count() == 1, "예전 목표가 순서도에 안 보임"
    assert page.locator(".flow .fchip .sq i.d").count() == 1, "예전 끝낸 칸이 순서도에 안 칠해짐"


def flow_sync_merges_other_device(page, shot):
    srv_reset()
    srv_put_mk(mk_snapshot())
    ready(page)
    connect(page)
    setup_goal(page, "한국사")
    setup_goal(page, "기타 솔로")
    pick(page, "모든 목표")
    tab(page, "today")
    page.locator(".blk", has_text="기본서 2쪽").locator(".chk").click()
    wait_synced(page)
    page.wait_for_timeout(300)
    d = srv_dump()["data"]
    other = json.loads(json.dumps(d["data"]))
    g7 = [g for g in other["goals"] if g.get("src") == "g7"][0]
    g7["ilog"].append({"id": "other1", "d": kst(0), "i": kst(0) + "|m-g", "k": 1, "n": 2, "m": "m-g", "a": 0, "s": 1})
    g7["ed"] = 1
    srv("/__put", {"key": "data", "value": {"rev": d["rev"] + 1, "at": "2026-10-11T00:00:00Z", "device": "PC-test", "data": other, "progress": d["progress"]}})
    page.locator(".blk", has_text="연습 시간 20분").nth(1).locator(".chk").click()   # 이 기기에서도 변경
    page.wait_for_function(f"(() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); return s.sync.rev >= {d['rev'] + 2}; }})()", timeout=10000)
    page.wait_for_timeout(500)
    st = saved(page)
    g7l = [g for g in st["goals"] if g.get("src") == "g7"][0]
    ks = sorted(e["k"] for e in g7l["ilog"])
    assert ks == [1, 2], f"다른 기기의 체크와 이 기기의 체크가 합쳐지지 않음: {g7l['ilog']}"
    g3l = [g for g in st["goals"] if g.get("src") == "g3"][0]
    assert len(g3l["ilog"]) == 1, "이 기기의 앞선 체크가 사라짐"
    tab(page, "today")
    assert page.locator(".blk", has_text="연습 시간 20분").locator(".chk[aria-pressed='true']").count() == 2, "합친 체크가 화면에 안 보임"


# ---------- 10/21: 요일별 시간 드롭다운 · 마감 순 · 낮은 칸 ----------
def flow_weekday_time_dropdown_shows_or_rests(page, shot):
    """목표마다 월~일 시간을 드롭다운으로 고르면 그 요일 오늘 화면에 그만큼 15분 칸, '쉼'이면 그 목표는 오늘 쉼(10/21 LEE 요청)"""
    fresh(page)
    make_goal(page, title="한식요리자격증", days=30, mids=(("필기 공부", 10),), tasks=2)
    tab(page, "goals")
    make_goal(page, title="토익 시험", days=60, mids=(("단어장 1회독", 20),), tasks=2)
    wi, wn = wd_today()
    pick(page, "모든 목표")
    tab(page, "sched")
    wk = page.locator(".weekall .wkline")
    assert wk.count() == 2, "모든 목표 일정에 목표마다 요일별 시간 줄이 없음"
    assert "한식" in wk.first.inner_text(), f"요일별 시간 줄이 마감 가까운 순이 아님: {wk.first.inner_text()}"
    wk.first.click()
    assert page.locator("#sheet select.tsel").count() == 7, "요일별 시간 창에 월~일 드롭다운 7개가 없음"
    assert page.locator("#sheet button[aria-label*='15분 늘리기']").count() == 0, "요일별 시간이 아직 −/+ 버튼임"
    pick_time(page.locator(f"#sheet select[aria-label='{wn}요일 시간']"), 30)
    page.locator("#sheet button", has_text="닫기").click()
    page.click("button[aria-label='토익 시험 요일별 시간 바꾸기']")
    pick_time(page.locator(f"#sheet select[aria-label='{wn}요일 시간']"), 0)
    assert page.locator(f"#sheet select[aria-label='{wn}요일 시간']").evaluate("e => e.selectedOptions[0].textContent") == "쉼", "0분이 '쉼'으로 안 보임"
    page.locator("#sheet button", has_text="닫기").click()
    st = {g["title"]: g for g in saved(page)["goals"]}
    assert st["한식요리자격증"]["avail"][wi] == 30 and st["토익 시험"]["avail"][wi] == 0, "드롭다운으로 고른 요일 시간이 저장되지 않음"
    assert f"{wn} 쉼" in page.locator(".wkline", has_text="토익").locator(".wk").get_attribute("aria-label"), "요일별 시간 줄에 쉼이 안 보임"
    tab(page, "today")
    sec = page.locator(".goalsec", has_text="한식요리자격증")
    assert sec.locator(".blk").count() == 2, f"오늘 30분을 골랐는데 15분 칸이 2개가 아님: {sec.inner_text()}"
    assert page.locator(".goalsec", has_text="토익 시험").count() == 0, "오늘 쉼으로 고른 목표가 오늘 화면에 나옴"
    rest = page.locator("#view-today .rest", has_text="오늘 쉬는 목표")
    assert rest.count() == 1 and "토익" in rest.inner_text(), f"쉬는 목표 안내가 없음: {page.inner_text('#view-today')[-300:]}"
    # 목표 하나 볼 때: 위에 요일별 시간 한 줄, 쉬는 날 안내, 거기서 바로 바꾸기
    pick(page, "토익 시험")
    assert f"오늘({wn}요일)은 이 목표를 쉬는 날이에요" in page.inner_text("#view-today"), "목표 하나 볼 때 쉬는 날 안내가 없음"
    strip = page.locator(".hero .wk")
    assert strip.count() == 1 and f"{wn} 쉼" in strip.get_attribute("aria-label"), "오늘 화면 위에 요일별 시간 한 줄이 없음"
    page.locator(".hero button", has_text="요일별 시간").click()
    assert "토익 시험" in page.inner_text("#sheetTitle"), "오늘 화면에서 요일별 시간 창이 안 열림"
    pick_time(page.locator(f"#sheet select[aria-label='{wn}요일 시간']"), 15)
    page.locator("#sheet button", has_text="닫기").click()
    assert rows(page).count() == 1, f"오늘 15분으로 바꿨는데 칸이 1개가 아님: {rows(page).count()}"
    page.reload()
    ready(page)
    assert rows(page).count() == 1 and saved(page)["goals"][1]["avail"][wi] == 15, "새로고침했더니 고른 요일 시간이 사라짐"


def flow_today_sorted_by_dday(page, shot):
    """모든 목표 오늘 화면·목표 목록·목표 고르기가 마감 지난(D+) 목표 → D-day 적은 목표 순, D-day 배지는 크고 색으로 구분(10/21 LEE 요청)"""
    fresh(page)
    make_goal(page, title="느긋한 목표", days=90, mids=(), tasks=1)
    tab(page, "goals")
    make_goal(page, title="코앞 목표", days=5, mids=(), tasks=1)
    tab(page, "goals")
    make_goal(page, title="지난 목표", days=20, mids=(), tasks=1)
    # 마감이 이틀 지난 목표로(마감 바꾸기는 지난 날을 안 받으므로 저장소에서)
    page.evaluate(f"""() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); const g = s.goals.find(x => x.title === '지난 목표');
        const d = new Date(Date.now() - 2 * 864e5).toLocaleDateString('sv-SE', {{timeZone: 'Asia/Seoul'}}); g.deadline = d; g.steps.forEach(x => x.due = d);
        g.plan.at = new Date(Date.now() - 5 * 864e5).toLocaleDateString('sv-SE', {{timeZone: 'Asia/Seoul'}});
        s.goals.forEach(x => x.avail = [30, 30, 30, 30, 30, 30, 30]); s.current = '*'; localStorage.setItem('{KEY}', JSON.stringify(s)); }}""")
    page.reload()
    ready(page)
    heads = page.locator(".goalsec .gh b").all_inner_texts()
    assert heads == ["지난 목표", "코앞 목표", "느긋한 목표"], f"오늘 화면 순서가 마감 지난 → 가까운 순이 아님: {heads}"
    assert page.locator(".goalsec", has_text="지난 목표").locator(".blk.late").count() >= 1, "마감 지난 목표에 밀린 칸이 안 나옴"
    badges = page.locator(".goalsec .gh .dd")
    assert "over" in badges.nth(0).get_attribute("class") and badges.nth(0).inner_text().startswith("D+"), f"마감 지난 목표 배지가 D+·빨강이 아님: {badges.nth(0).inner_text()}"
    assert "soon" in badges.nth(1).get_attribute("class"), "7일 안 목표 배지가 주황이 아님"
    bg = [badges.nth(i).evaluate("e => getComputedStyle(e).backgroundColor") for i in range(3)]
    assert len(set(bg)) == 3, f"D-day 배지 색이 마감 정도에 따라 다르지 않음: {bg}"
    fs = badges.nth(0).evaluate("e => parseFloat(getComputedStyle(e).fontSize)")
    assert fs >= 15, f"D-day 배지 글자가 작음: {fs}px"
    assert "마감 가까운 순" in page.inner_text("#view-today"), "오늘 화면에 정렬 기준 안내가 없음"
    quiet(page, top=True)
    shot("today-sorted", store=False)
    opts = page.locator("#goalPick option").all_inner_texts()
    assert opts[1].startswith("지난 목표") and opts[2].startswith("코앞 목표"), f"목표 고르기 순서가 마감 순이 아님: {opts}"
    tab(page, "goals")
    names = [t.strip() for t in page.locator(".goal-item h3").all_inner_texts()]
    assert [n.split(" 단계")[0] for n in names] == ["지난 목표", "코앞 목표", "느긋한 목표"], f"목표 목록 순서가 마감 순이 아님: {names}"
    assert page.locator(".goal-item .gsub .dd.over").count() == 1, "목표 목록에 마감 지난 배지가 없음"
    pick(page, "코앞 목표")
    tab(page, "today")
    big = page.locator(".hero .dd.big")
    assert big.count() == 1 and big.evaluate("e => parseFloat(getComputedStyle(e).fontSize)") >= 20, "목표 화면 D-day가 크게 안 보임"
    assert big.inner_text() == "D-5", f"목표 화면 D-day가 틀림: {big.inner_text()}"


def flow_compact_tiles_fit_phone(page, shot):
    """오늘 화면 15분 칸 높이를 낮춰 폰 한 화면에 많이 보임 — 누르는 곳은 그대로 넉넉(10/21 LEE 요청)"""
    page.set_viewport_size({"width": 360, "height": 780})
    ready(page)
    page.evaluate(f"""() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); s.goals[0].avail = [180, 180, 180, 180, 180, 180, 180]; localStorage.setItem('{KEY}', JSON.stringify(s)); }}""")
    page.reload()
    ready(page)
    r = rows(page)
    assert r.count() == 12, f"오늘 3시간인데 칸이 12개가 아님: {r.count()}"
    hs = r.evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().height))")
    assert max(hs) <= 50, f"15분 칸이 너무 높음: {hs}"
    gap = page.evaluate("(() => { const a = document.querySelectorAll('#todayList .blk'); return a[1].getBoundingClientRect().top - a[0].getBoundingClientRect().bottom; })()")
    assert gap <= 6, f"칸 사이 간격이 큼: {gap}"
    todo = r.filter(has=page.locator(".chk[aria-pressed='false']")).first
    chk, play = todo.locator(".chk").bounding_box(), todo.locator(".play").bounding_box()
    assert chk["width"] >= 40 and chk["height"] >= 40, f"체크 버튼이 너무 작아짐: {chk}"
    assert play["width"] >= 44 and play["height"] >= 40, f"타이머 버튼이 너무 작아짐: {play}"
    span = page.evaluate("(() => { const a = document.querySelectorAll('#todayList .blk'); return a[a.length - 1].getBoundingClientRect().bottom - a[0].getBoundingClientRect().top; })()")
    assert span <= 12 * 50 + 11 * 6, f"12칸이 차지하는 높이가 큼: {span}"


def flow_pulled_rows_fill_time_and_stay_put(page, shot):
    """그 요일 시간보다 놓인 칸이 적으면 뒤 칸을 당겨 채우고(원래 날짜 표시), 당겨 온 칸을 체크해도 줄 순서가 그대로 · 일정 오늘 상자도 같은 양"""
    fresh(page)
    make_goal(page, title="긴 호흡 목표", days=60, mids=(), tasks=2)   # 45분+30분 = 5칸을 60일에 고르게 → 오늘 놓인 칸은 1개
    _, wn = wd_today()
    tab(page, "sched")
    pick_time(page.locator(f"select[aria-label='{wn}요일 시간']"), 60)
    tab(page, "today")
    r = rows(page)
    assert r.count() == 4, f"오늘 1시간을 골랐는데 칸이 4개가 아님: {r.count()}"
    xs = r.locator(".chk").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().left))")
    tops = r.evaluate_all("els => els.map(e => e.getBoundingClientRect().top)")
    assert len(set(xs)) == 1 and len({round(tops[i + 1] - tops[i]) for i in range(3)}) == 1, f"당겨 온 칸만 모양·간격이 다름: {xs} {tops}"
    notes = r.locator(".t2").all_inner_texts()
    assert sum("원래" in n for n in notes) == 3, f"뒤 칸을 당겨 온 표시가 없음: {notes}"
    titles = [t.split("\n")[0] for t in r.all_inner_texts()]
    r.nth(3).locator(".chk").click()
    r = rows(page)
    assert [t.split("\n")[0] for t in r.all_inner_texts()] == titles, f"당겨 온 칸을 체크했더니 줄 순서가 바뀜: {titles} → {r.all_inner_texts()}"
    assert r.nth(3).locator(".chk").get_attribute("aria-pressed") == "true", "누른 칸이 체크되지 않음"
    assert r.locator(".chk[aria-pressed='true']").count() == 1, "다른 칸까지 체크됨"
    tab(page, "sched")
    box = page.locator(".day.is-today")
    assert "15분 × 3" in box.inner_text(), f"일정 오늘 상자가 오늘 화면(남은 3칸)과 다름: {box.inner_text()}"
    tab(page, "plan", flow=True)
    chips = page.locator(".flow .frow", has=page.locator(".fbox.today")).locator(".fchip")
    assert chips.count() >= 1 and "할 일 1-1" in chips.first.inner_text(), "순서도 오늘 가지에 당겨 온 칸이 없음"


def flow_old_bare_goals_keep_daily_15(page, shot):
    """10/20까지의 저장본: 설정 전 목표는 오늘 화면에 안 나오고(설정 전 목록·일정·목표에 구분 표시) 설정하면 나옴 ·
    할 일 없이 기본 요일 시간이던 목표는 매일 15분으로 한 번만 옮김(10/23 LEE 요청 3번)"""
    D, L = [120, 60, 60, 60, 60, 60, 120], [0, 15, 15, 15, 15, 15, 0]

    def goal(i, title, avail, tasks=(), src=None):
        g = {"id": f"o{i}", "title": title, "deadline": kst(40 + i), "createdAt": kst(-9), "avail": avail, "ed": 1, "log": [], "ilog": [],
             "steps": [{"id": f"s{i}", "title": title, "due": kst(40 + i), "final": True, "tasks": [{"id": f"t{i}{j}", "title": t, "blocks": 4} for j, t in enumerate(tasks)]}]}
        if src:
            g["src"] = src
        return g
    old = {"v": 2, "seen": True, "current": "*", "goals": [goal(1, "할 일 없는 옛 목표", D), goal(2, "시간 고친 옛 목표", [30] * 7),
           goal(3, "할 일 있는 옛 목표", D, ("기출 1회",)), goal(4, "목표까지 옛 목표", L, src="g9")], "del": {}, "imin": {}}
    page.evaluate(f"localStorage.setItem('{KEY}', JSON.stringify({json.dumps(old, ensure_ascii=False)}))")
    page.reload()
    ready(page)
    av = page.evaluate("Object.fromEntries(state.goals.map(g => [g.title, g.avail]))")
    assert av["할 일 없는 옛 목표"] == [15] * 7 and av["목표까지 옛 목표"] == [15] * 7, f"할 일 없는 옛 목표가 매일 15분으로 안 옮겨짐: {av}"
    assert av["시간 고친 옛 목표"] == [30] * 7 and av["할 일 있는 옛 목표"] == D, f"직접 고친 시간·할 일 있는 목표의 요일 시간이 바뀜: {av}"
    assert page.locator(".goalsec").count() == 0 and "설정 전 목표 4개" in page.inner_text("#preBox"), f"설정 전 목표가 오늘 화면에 나오거나 설정 전 목록이 없음: {page.inner_text('#view-today')[:300]}"
    quiet(page, top=True)
    shot("today-pre", store=False)
    tab(page, "sched")
    assert page.locator(".day li.pre .tag.pre").count() >= 1, "일정에 설정 전 목표 표시가 없음"
    tab(page, "goals")
    assert page.locator(".goal-item.pre").count() == 4 and page.locator(".goal-item .tag.pre").count() == 4, "목표 카드에 설정 전 표시가 없음"
    tab(page, "today")
    page.locator("#preBox button[aria-label='할 일 없는 옛 목표 설정하기']").click()
    wz_next(page)
    page.click(".kindc[data-kind='steps']")
    wz_next(page)
    wz_next(page)
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    sec = page.locator(".goalsec", has_text="할 일 없는 옛 목표")
    assert sec.locator(".blk").count() == 1, f"설정한 옛 목표가 오늘 1칸(매일 15분)이 아님: {page.inner_text('#view-today')[:300]}"
    assert sec.locator(".blk.late").count() == 0, "설정하기 전 날들이 밀린 것으로 나옴"
    assert "설정 전 목표 3개" in page.inner_text("#preBox"), "설정한 목표가 설정 전 목록에 남음"
    # 옮긴 뒤 기본값과 같은 시간을 직접 골라도 다시 옮기지 않음(한 번만)
    page.locator(".goalsec .gh", has_text="할 일 없는 옛 목표").click()
    page.locator(".hero button", has_text="요일별 시간").click()
    wi, _ = wd_today()
    for i, wdn in enumerate("일월화수목금토"):
        pick_time(page.locator(f"#sheet select[aria-label='{wdn}요일 시간']"), D[i])
    page.locator("#sheet button", has_text="닫기").click()
    page.reload()
    ready(page)
    g1 = [g for g in saved(page)["goals"] if g["title"] == "할 일 없는 옛 목표"][0]
    assert g1["avail"] == D and g1.get("av") == 1, f"직접 고른 시간이 새로고침 뒤 매일 15분으로 되돌아감: {g1['avail']}"
    assert rows(page).count() == D[wi] // 15, f"직접 고른 시간만큼 칸이 안 나옴: {rows(page).count()}"


# ---------- 10/23: 새 순서(목표일 → 단계·일별·운동) · 밀린 것 · 완료 보관 ----------
def flow_daily_plan_start_date_and_sentence(page, shot):
    """일별: 전체 횟수 → 한 달 20일 기준 + 여유 20%로 목표일에서 거꾸로 시작일, 늦으면 '…에 시작될 예정입니다'와 시작 D-day(10/23 LEE 요청)"""
    fresh(page)
    page.locator("button:visible", has_text=re.compile("목표 세우기")).first.click()
    page.fill("#wzTitle", "영단어 40회")
    page.fill("#wzDeadline", kst(100))
    wz_next(page)
    page.click(".kindc[data-kind='daily']")
    page.fill("#wzCount", "40")
    sm = page.inner_text("#wzPlanSum")
    start = kst(100 - 72)
    m, d = int(start[5:7]), int(start[8:10])
    assert "한 달 20일(주 5일) 기준 40회는 2달" in sm and "2.4달(72일)" in sm, f"한 달 20일·여유 20% 계산 안내가 없음: {sm}"
    assert f"이 프로젝트의 실행은 {m}월 {d}일에 시작될 예정입니다." in sm and "시작 D-28" in sm, f"시작 예정 문구·시작 D-day가 없음: {sm}"
    shot("wizard-daily", store=False)
    wz_next(page)
    assert "1/40" in page.inner_text("#wzPlanSum"), "확인 단계에 1/40 회차 미리보기가 없음"
    wz_next(page)
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    p = saved(page)["goals"][0]["plan"]
    assert p["kind"] == "daily" and p["n"] == 40 and p["from"] == start and len(p["dates"]) == 40, f"일별 설정이 저장되지 않음: {p.get('from')} {len(p.get('dates', []))}"
    assert p["dates"][0] >= start and p["dates"][-1] <= kst(100), f"회차 날짜가 시작일~목표일 밖: {p['dates'][0]} ~ {p['dates'][-1]}"
    assert all(datetime.strptime(x, "%Y-%m-%d").weekday() < 5 for x in p["dates"]), "기본(월~금)이 아닌 요일에 회차가 놓임"
    assert len(set(p["dates"])) == 40, "여유가 있는데 하루에 두 회차가 놓임"
    text = page.inner_text("#view-today")
    assert f"이 프로젝트의 실행은 {m}월 {d}일에 시작될 예정입니다." in text and "아직 시작 전" in text and rows(page).count() == 0, f"시작 전 목표 안내가 오늘 화면에 없음: {text[:300]}"
    tab(page, "goals")
    assert "시작 D-28" in page.inner_text(".goal-item"), "목표 카드에 시작 D-day가 따로 안 보임"
    tab(page, "plan")
    assert page.locator(".sesl li").count() == 40 and page.locator(".sesl li").first.inner_text().startswith("1/40"), "역산 화면에 회차 목록(1/40 …)이 없음"
    tab(page, "today")
    page.locator("#view-today button", has_text="오늘부터 시작").first.click()
    assert saved(page)["goals"][0]["plan"]["from"] == kst(0), "오늘부터 시작이 안 됨"
    wi, _ = wd_today()
    if 1 <= wi <= 5:
        assert rows(page).count() == 1 and rows(page).first.inner_text().startswith("1/40"), f"오늘부터 시작했는데 1/40이 안 나옴: {page.inner_text('#view-today')[:300]}"


def flow_daily_backlog_listed_and_title_edit(page, shot):
    """일별: 어제·그전 못 한 회차가 오늘 회차와 함께 나오고(독려 문구), 끝낸 회차는 1/N을 두고 제목을 고쳐 남김(10/23 LEE 요청)"""
    fresh(page)
    quick_goal(page, "기출 10회", 9, kind="daily", n=10, all_days=True)
    page.evaluate(f"""() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); const p = s.goals[0].plan;
        const d = k => new Date(Date.now() + k * 864e5).toLocaleDateString('sv-SE', {{timeZone: 'Asia/Seoul'}});
        p.from = d(-2); p.at = d(-2); p.dates = p.dates.map((x, i) => d(i - 2)); localStorage.setItem('{KEY}', JSON.stringify(s)); }}""")
    page.reload()
    ready(page)
    r = rows(page)
    texts = r.all_inner_texts()
    assert r.count() == 3 and texts[0].startswith("1/10") and texts[2].startswith("3/10"), f"밀린 회차와 오늘 회차가 함께 나오지 않음: {texts}"
    assert "밀림" in texts[0] and "밀림" in texts[1] and "오늘 회차" in texts[2], f"밀린 회차 표시가 없음: {texts}"
    cheer = page.inner_text(".cheer")
    assert "어제 못 한 것 1개" in cheer and "그전에 밀린 것 1개" in cheer, f"어제·그전 못 한 것 독려 문구가 없음: {cheer}"
    assert "밀린 2" in page.inner_text("#view-today .today-head"), "오늘 머리에 밀린 개수가 없음"
    quiet(page, top=True)
    shot("today-backlog")
    r.first.locator(".chk").click()
    r = rows(page)
    assert r.count() == 3 and r.first.locator(".chk").get_attribute("aria-pressed") == "true", "밀린 회차를 체크하면 줄이 사라지거나 체크가 안 됨"
    assert "오늘 함" in r.first.inner_text(), f"밀린 회차를 오늘 한 표시가 없음: {r.first.inner_text()}"
    r.first.locator("button[aria-label='1/10 회차 제목 고치기']").click()
    page.fill("#sesTitle", "2019년 1회 기출")
    page.click("#sesOk")
    t0 = rows(page).first.inner_text()
    assert t0.startswith("1/10") and "2019년 1회 기출" in t0, f"끝낸 회차 제목이 안 바뀜: {t0}"
    page.reload()
    ready(page)
    g = saved(page)["goals"][0]
    e = [x for x in g["slog"] if x["k"] == 1][0]
    assert e.get("t") == "2019년 1회 기출" and e["d"] == kst(0), f"회차 기록·제목이 저장되지 않음: {g['slog']}"
    assert "2019년 1회 기출" in rows(page).first.inner_text(), "새로고침 뒤 고친 제목이 사라짐"
    tab(page, "plan")
    assert "2019년 1회 기출" in page.locator(".sesl li").first.inner_text() and "밀림" in page.locator(".sesl li").nth(1).inner_text(), "역산 회차 목록에 기록·밀림이 안 보임"


def flow_overdue_steps_goal_completes_to_archive(page, shot):
    """목표일이 지난(D+) 단계 목표는 밀린 칸만 나오고, 다 체크하면 완료 → 보관함 · 되돌리기(10/23 LEE 요청: 부가세 신고처럼 다 한 목표가 계속 나오던 것)"""
    fresh(page)
    make_goal(page, title="부가세 신고", days=10, mids=(), tasks=0)
    page.evaluate(f"""() => {{ const s = JSON.parse(localStorage.getItem('{KEY}')); const g = s.goals[0];
        const d = k => new Date(Date.now() + k * 864e5).toLocaleDateString('sv-SE', {{timeZone: 'Asia/Seoul'}});
        g.deadline = d(-2); g.steps.forEach(x => x.due = d(-2)); g.plan.at = d(-4); g.avail = [15, 15, 15, 15, 15, 15, 15];
        localStorage.setItem('{KEY}', JSON.stringify(s)); }}""")
    page.reload()
    ready(page)
    r = rows(page)
    assert r.count() == 3 and all("밀림" in x for x in r.all_inner_texts()), f"D+ 목표에 밀린 칸(3일 × 15분)만 나와야 함: {r.all_inner_texts()}"
    assert page.inner_text(".hero .dd.big") == "D+2", "D+ 배지가 없음"
    assert "밀린 것을 다 하면 완료 보관함으로" in page.inner_text("#view-today"), "밀린 것을 다 하면 완료된다는 안내가 없음"
    for _ in range(2):
        rows(page).locator(".chk[aria-pressed='false']").first.click()
    assert rows(page).count() == 3, "밀린 칸을 체크하는 동안 줄이 사라짐"
    rows(page).locator(".chk[aria-pressed='false']").first.click()   # 마지막 → 완료
    g = saved(page)["goals"][0]
    assert g.get("doneAt") == kst(0) and g.get("doneBy") == "check", f"밀린 것을 다 했는데 완료로 보관되지 않음: {g.get('doneAt')} {g.get('doneBy')}"
    assert "완료 보관함" in (page.text_content("#toast") or ""), "완료 보관함으로 옮겼다는 알림이 없음"
    assert "오늘 완료한 목표" in page.inner_text("#view-today") and rows(page).count() == 0, f"보관한 목표가 오늘 화면에 남거나 완료 안내가 없음: {page.inner_text('#view-today')[:300]}"
    tab(page, "goals")
    assert page.locator(".goal-item", has_text="부가세 신고").count() == 0, "보관한 목표가 목표 목록에 남음"
    arch = page.locator("#archive")
    assert arch.count() == 1 and "완료 보관함 1개" in arch.inner_text(), "완료 보관함이 없음"
    arch.locator("summary").click()
    assert "부가세 신고" in arch.inner_text(), "보관함에 다 한 목표가 없음"
    arch.locator("button", has_text="되돌리기").click()
    g = saved(page)["goals"][0]
    assert not g.get("doneAt") and g.get("reopen") == kst(0), "되돌리기가 안 됨"
    assert page.locator(".goal-item", has_text="부가세 신고").count() == 1, "되돌린 목표가 목록에 안 돌아옴"
    page.reload()
    ready(page)
    assert not saved(page)["goals"][0].get("doneAt"), "되돌린 목표가 새로고침하자 다시 보관됨"
    assert "목표일이 지났어요" in page.inner_text("#view-today"), "되돌린 D+ 목표에 안내가 없음"


def flow_daily_all_sessions_done_archives(page, shot):
    """일별: 오늘 회차를 다 하면 다음 회차를 미리 할 수 있고, 모든 회차를 끝내면 바로 완료 보관함으로"""
    fresh(page)
    quick_goal(page, "책 2권 읽기", 3, kind="daily", n=2, all_days=True)
    r = rows(page)
    assert r.count() == 1 and r.first.inner_text().startswith("1/2"), f"오늘 1/2 회차가 없음: {r.all_inner_texts()}"
    r.first.locator(".chk").click()
    assert "오늘 회차를 다 했어요" in page.inner_text("#view-today"), "오늘 회차를 다 했다는 안내가 없음"
    page.locator("#view-today button", has_text="다음 회차 미리 하기").click()
    r = rows(page)
    assert r.count() == 2 and "미리 하기" in r.nth(1).inner_text(), f"다음 회차를 오늘로 당기지 못함: {r.all_inner_texts()}"
    r.nth(1).locator(".chk").click()
    g = saved(page)["goals"][0]
    assert g.get("doneAt") == kst(0) and len(g["slog"]) == 2, f"모든 회차를 끝냈는데 보관함으로 안 감: {g.get('doneAt')} {g.get('slog')}"
    assert "완료 보관함" in (page.text_content("#toast") or ""), "완료 보관함으로 옮겼다는 알림이 없음"


def flow_ramp_exercise_curve(page, shot):
    """운동: 최종 목표·처음 가능치·횟수로 회차마다 양을 곡선으로 나눔(S자는 처음이 천천히), 제목에서 이름·목표를 짐작(10/23 LEE 요청)"""
    fresh(page)
    page.locator("button:visible", has_text=re.compile("목표 세우기")).first.click()
    page.fill("#wzTitle", "팔굽혀펴기 50개")
    page.fill("#wzDeadline", kst(19))
    wz_next(page)
    page.click(".kindc[data-kind='ramp']")
    assert page.input_value("#wzWhat") == "팔굽혀펴기" and page.input_value("#wzTarget") == "50" and page.input_value("#wzUnit") == "개", "제목에서 운동 이름·최종 목표·단위를 짐작하지 못함"
    page.fill("#wzStart", "10")
    page.fill("#wzCount", "20")
    for wd in "토일":
        page.click(f".wdt button[aria-label='{wd}요일']")
    sm = page.inner_text("#wzPlanSum")
    assert "1회 10개" in sm and "20회 50개" in sm, f"처음·마지막 회차 양이 안 맞음: {sm}"
    assert page.locator("#wzPlanSum svg.spark").count() == 1, "변화 곡선 그림이 없음"
    s5 = re.search(r"5회 (\d+)개", sm)
    page.click("button[data-curve='line']")
    l5 = re.search(r"5회 (\d+)개", page.inner_text("#wzPlanSum"))
    assert s5 and l5 and int(s5.group(1)) < int(l5.group(1)), f"S자 곡선이 처음에 천천히 늘지 않음: S {s5 and s5.group(1)} / 직선 {l5 and l5.group(1)}"
    page.click("button[data-curve='s']")
    shot("wizard-ramp", store=False)
    wz_next(page)
    wz_next(page)
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    p = saved(page)["goals"][0]["plan"]
    assert p["kind"] == "ramp" and p["a"] == 10 and p["b"] == 50 and p["unit"] == "개" and p["what"] == "팔굽혀펴기" and p["curve"] == "s", f"운동 설정이 저장되지 않음: {p}"
    r = rows(page)
    assert r.count() == 1 and "1/20" in r.first.inner_text() and "팔굽혀펴기 10개" in r.first.inner_text(), f"오늘 1회차 양이 안 나옴: {r.all_inner_texts()}"
    assert page.locator(".hero svg.spark").count() == 1, "목표 화면 위에 변화 곡선이 없음"
    tab(page, "plan")
    last = page.locator(".sesl li").last.inner_text()
    assert "20/20" in last and "팔굽혀펴기 50개" in last, f"마지막 회차가 최종 목표가 아님: {last}"


def flow_sync_old_device_keeps_new_fields(page, shot):
    """10/23 전 판(새 칸을 모르는 기기)이 올린 목표를 받아도 이 기기의 설정·회차 기록·완료 보관을 지킴"""
    srv_reset()
    fresh(page)
    connect(page)
    tab(page, "today")
    quick_goal(page, "책 5권", 6, kind="daily", n=5, all_days=True)
    rows(page).first.locator(".chk").click()
    tab(page, "goals")
    quick_goal(page, "끝낸 일", 30)
    tab(page, "goals")
    page.locator(".goal-item", has_text="끝낸 일").locator("button", has_text="목표 완료").click()
    page.click("#sheet .btn.primary")
    wait_synced(page)
    page.wait_for_timeout(300)
    d = srv_dump()["data"]
    old = json.loads(json.dumps(d["data"]))
    for g in old["goals"]:
        for k in ("plan", "slog", "doneAt", "doneBy", "reopen"):
            g.pop(k, None)
    srv("/__put", {"key": "data", "value": {"rev": d["rev"] + 1, "at": "2026-10-23T00:00:00Z", "device": "PC-옛판", "data": old, "progress": d["progress"]}})
    page.click("#syncNowBtn")
    page.wait_for_function(f"JSON.parse(localStorage.getItem('{KEY}')).sync.rev >= {d['rev'] + 1}", timeout=8000)
    page.wait_for_timeout(300)
    st = {g["title"]: g for g in saved(page)["goals"]}
    assert st["책 5권"].get("plan", {}).get("kind") == "daily" and len(st["책 5권"].get("slog", [])) == 1, f"옛 판이 올린 목표를 받으면서 설정·회차 기록이 사라짐: {st['책 5권'].get('plan')} {st['책 5권'].get('slog')}"
    assert st["끝낸 일"].get("doneAt") == kst(0), "옛 판이 올린 목표를 받으면서 완료 보관이 풀림"
    tab(page, "today")
    assert rows(page).count() >= 1 and rows(page).first.inner_text().startswith("1/5"), "옛 판 목표를 받은 뒤 오늘 회차가 사라짐"
