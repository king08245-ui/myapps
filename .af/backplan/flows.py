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


def ready(page):
    page.wait_for_selector("#view-today .hero, #view-today .empty, #view-today .goalsec, #view-today .today-head", timeout=10000)


def tab(page, name):
    page.click(f".tabs button[data-tab='{name}']")
    page.wait_for_selector(f"#view-{name}:not([hidden])", timeout=5000)


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


def make_goal(page, title="자격증 필기 합격", days=40, mids=(("기출 3회분 70점", 25), ("핵심 요약 1회독", 12)), tasks=2):
    """마법사로 목표 하나 만들기: 거꾸로 중간 목표(최종 → 아래로), 단계마다 할 일 tasks개"""
    page.locator("button", has_text=re.compile("목표 세우기")).first.click()
    page.fill("#wzTitle", title)
    page.fill("#wzDeadline", kst(days))
    page.click(".sheet-actions .btn.primary")
    for name, d in mids:
        page.fill("#wzMid", name)
        page.fill("#wzMidDate", kst(d))
        page.click(".ask button")
    page.click(".sheet-actions .btn.primary")
    n = page.locator(".sheet .addtask").count()
    for i in range(n):
        for j in range(tasks):
            box = page.locator(".sheet .addtask").nth(i)
            box.locator("input").fill(f"할 일 {i + 1}-{j + 1}")
            if j == 0:
                box.locator("button[aria-label='15분 늘리기']").click()   # 45분
            box.locator("button", has_text="할 일 추가").click()
    page.click(".sheet-actions .btn.primary")
    page.click(".sheet-actions .btn.primary")   # 완료
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
    page.click(".sheet-actions .btn.primary")
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
    page.click(".sheet-actions .btn.primary")
    boxes = page.locator(".sheet .addtask")
    assert boxes.count() == 3, f"단계 수(중간 2 + 최종 1)만큼 할 일 칸이 없음: {boxes.count()}"
    first_card = page.locator(".sheet .card").first.inner_text()
    assert "10km" in first_card, f"쪼개기는 지금에 가까운 단계부터여야 함: {first_card[:40]}"
    for i, (name, plus) in enumerate((("인터벌 400m×6", 2), ("장거리 8km", 4), ("대회 코스 답사", 0))):
        b = page.locator(".sheet .addtask").nth(i)
        b.locator("input").fill(name)
        for _ in range(plus):
            b.locator("button[aria-label='15분 늘리기']").click()
        b.locator("button", has_text="할 일 추가").click()
    li = page.locator(".sheet .card").nth(0).locator(".wz-list li").first.inner_text()
    assert "인터벌" in li and "1시간" in li, f"30분+15분×2 = 1시간이 표시되지 않음: {li}"
    shot("wizard-split")
    page.click(".sheet-actions .btn.primary")
    summary = page.inner_text(".sum")
    assert "끝나요" in summary, f"요약에 끝나는 날이 없음: {summary}"
    page.click(".sheet-actions .btn.primary")
    ready(page)
    assert page.locator(".hero h1").inner_text() == "하프 마라톤 완주", "만든 목표가 오늘 화면에 안 나옴"
    assert "예시 목표예요" not in page.inner_text("#view-today"), "내 목표를 만들었는데 예시가 남음"
    st = saved(page)
    assert len(st["goals"]) == 1 and not st["goals"][0].get("sample"), "손대지 않은 예시 목표가 지워지지 않음"
    steps = st["goals"][0]["steps"]
    assert [s["title"] for s in steps] == ["10km 1시간 안에", "15km 쉬지 않고 달리기", "하프 마라톤 완주"], f"단계 순서가 틀림: {[s['title'] for s in steps]}"
    assert steps[0]["tasks"][0]["blocks"] == 4 and steps[1]["tasks"][0]["blocks"] == 6, "15분 단위 시간이 저장되지 않음"
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
    ready(page)
    n = rows(page).count()
    for _ in range(10):
        loc = rows(page).locator(".chk[aria-pressed='false']")
        if not loc.count():
            break
        loc.first.click()
    assert rows(page).count() == n, f"오늘 몫을 다 하는 동안 목록 길이가 바뀜: {n} → {rows(page).count()}"
    text = page.inner_text("#view-today")
    assert "오늘 몫을 다 했어요" in text, "오늘 몫을 끝냈는데 안내가 없음"
    nxt = page.locator(".blk", has_text="미리 하기")
    assert nxt.count() == 1, "다음 칸 미리 하기가 없음"
    before = done_minutes(page)
    nxt.locator(".chk").click()
    assert done_minutes(page) == before + 15, "미리 한 칸이 끝낸 시간에 들어가지 않음"
    assert page.locator(".blk", has_text="미리 하기").count() == 1, "미리 한 뒤 그다음 칸이 안 나옴"
    shot("done-today")


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
    page.click("button:has-text('새 목표 세우기')")
    page.fill("#wzTitle", "둘째 목표")
    page.fill("#wzDeadline", kst(20))
    for _ in range(4):
        page.click(".sheet-actions .btn.primary")
    ready(page)
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
    node.locator(".addtask button[aria-label='15분 늘리기']").click()
    node.locator(".addtask button", has_text="할 일 추가").click()
    node = page.locator("#" + node_id)
    task = node.locator(".task").first
    assert task.locator("output").inner_text() == "45분", f"할 일 시간이 45분이 아님: {task.locator('output').inner_text()}"
    task.locator("button[aria-label$='15분 늘리기']").click()
    node = page.locator("#" + node_id)
    assert node.locator(".task output").first.inner_text() == "1시간", "15분 늘리기가 안 됨"
    assert node.locator(".task .sq i").count() == 4, "15분 칸 그림이 4칸이 아님"
    shot("plan")
    node.locator(".step-titlerow .icon-btn").click()
    assert page.is_visible("#sheet"), "지우기 전에 확인을 묻지 않음"
    page.click("#sheet .btn.primary")
    assert page.locator("#" + node_id).count() == 0, "확인 후에도 지워지지 않음"


def flow_rename_then_tap_stepper(page, shot):
    """이름을 고친 직후 누른 −/+가 씹히지 않음(보류 5)"""
    ready(page)
    tab(page, "plan")
    task = page.locator(".task").first
    tid = task.evaluate("el => el.closest('.node').id")
    before = task.locator("output").inner_text()
    name = task.locator("input.tt")
    name.click()
    name.fill("이름 바꾼 할 일")
    task.locator("button[aria-label$='15분 늘리기']").click()   # 입력칸이 포커스를 잃으며 change → 바로 + 클릭
    node = page.locator("#" + tid)
    t2 = node.locator(".task").first
    assert t2.locator("input.tt").input_value() == "이름 바꾼 할 일", "고친 이름이 사라짐"
    assert t2.locator("output").inner_text() != before, f"이름을 고친 직후 누른 +가 무시됨: {before}"
    step = page.locator(".chain .node[id^='step-'] textarea.step-title").nth(1)
    sid = step.evaluate("el => el.closest('.node').id")
    step.fill("단계 이름도 바꿈")
    page.locator(f"#{sid} .addtask button[aria-label='15분 늘리기']").click()
    assert page.locator(f"#{sid} .addtask output").inner_text() == "45분", "단계 이름을 고친 직후 누른 +가 무시됨"


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
        for _ in range(12):
            b = page.locator(f".avail .a:has(.wdn:text-is('{wd}')) button[aria-label='{wd}요일 15분 줄이기']")
            if "쉼" in page.locator(f".avail .a:has(.wdn:text-is('{wd}')) output").inner_text():
                break
            b.click()
    assert "쓸 수 있는 시간을 정하면" in page.inner_text("#view-sched"), "쓸 수 있는 시간이 0인데 안내가 없음"
    tab(page, "today")
    assert "쓸 수 있는 시간이 없어요" in page.inner_text("#view-today"), "오늘 화면에 시간이 없다는 경고가 없음"
    tab(page, "sched")
    page.locator(".avail .a:has(.wdn:text-is('월')) button[aria-label='월요일 15분 늘리기']").click()
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
    page.locator(".avail .a:has(.wdn:text-is('월')) button[aria-label='월요일 15분 늘리기']").click()
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
    page.click("button:has-text('새 목표 세우기')")
    page.fill("#wzTitle", "두 번째 목표")
    page.fill("#wzDeadline", kst(20))
    for _ in range(4):
        page.click(".sheet-actions .btn.primary")
    ready(page)
    opts = page.locator("#goalPick option").all_inner_texts()
    assert len(opts) == 3 and opts[0].startswith("모든 목표") and "두 번째 목표" in page.locator(".hero h1").inner_text(), f"새 목표로 바뀌지 않음: {opts}"
    pick(page, "첫 번째")
    assert page.locator(".hero h1").inner_text() == "첫 번째 목표", "목표 고르기가 안 됨"
    pick(page, "모든 목표")
    assert page.locator(".goalsec").count() >= 1, "모든 목표 보기에 목표별 묶음이 없음"
    tab(page, "plan")
    assert page.locator(".chooser button").count() == 2, "모든 목표일 때 역산 화면에서 목표를 고르게 하지 않음"
    page.locator(".chooser button", has_text="첫 번째 목표").click()
    assert page.locator(".chain .node.goal").count() == 1, "고른 목표의 역산이 안 나옴"
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
    for _ in range(4):
        page.click(".sheet-actions .btn.primary")
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
    assert "할 일이 아직 없어요" in page.inner_text("#view-today"), "할 일이 없을 때 안내가 없음"


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
    assert not page.locator("#view-plan").is_hidden(), "날짜 고치기를 눌렀는데 역산 화면으로 가지 않음"


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
    page.wait_for_selector("#wzMid", timeout=3000)
    page.fill("#wzMid", "초고 절반")
    page.fill("#wzMidDate", kst(45))
    page.click(".ask button")
    page.reload()
    page.wait_for_selector("#sheet:not([hidden])", timeout=5000)
    assert "2 / 4" in page.inner_text("#panel"), "다시 열었을 때 만들던 단계로 돌아오지 않음"
    items = page.locator(".wz-list li").all_inner_texts()
    assert "책 원고 1권 쓰기" in items[0] and "초고 절반" in items[1], f"만들던 내용이 사라짐: {items}"
    page.keyboard.press("Escape")
    assert "버릴까요" in page.inner_text("#panel"), "Esc로 확인 없이 버림"
    page.click("#panel button:has-text('계속 만들기')")
    assert "2 / 4" in page.inner_text("#panel"), "'계속 만들기'로 돌아오지 않음"
    page.click(".sheet-actions .btn.primary")
    focused = page.evaluate("document.activeElement && document.activeElement.id")
    assert focused and focused.startswith("wz-add-"), f"3단계 첫 초점이 할 일 입력칸이 아님: {focused}"
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
    assert "#server" not in page.url, "설정 링크가 주소창에 남음"
    page.wait_for_function("document.activeElement && document.activeElement.id === 'syncCode'", timeout=3000)


def flow_linked_plan_is_readonly_with_tasks(page, shot):
    srv_reset()
    srv_put_mk(mk_snapshot())
    ready(page)
    connect(page)
    pick(page, "한국사")
    tab(page, "plan")
    assert page.locator(".linknote").count() == 1, "목표까지에서 가져온 계획이라는 안내가 없음"
    assert page.locator(".insert").count() == 0, "목표까지 계획에 중간 목표 추가 버튼이 보임"
    assert page.locator("textarea.step-title, .chain input.date-in").count() == 0, "목표까지 단계 이름·날짜를 폰에서 고칠 수 있게 됨"
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
    page.locator(".daily li", has_text="기본서 읽기").locator("button[aria-label$='15분 늘리기']").click()
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


def flow_sync_merges_other_device(page, shot):
    srv_reset()
    srv_put_mk(mk_snapshot())
    ready(page)
    connect(page)
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
