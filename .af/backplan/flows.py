# 역산 15분 플래너 자동 검수 흐름 (Playwright sync API)
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KEY = "backplan:v1"


def kst(days=0):
    return (datetime.now(ZoneInfo("Asia/Seoul")) + timedelta(days=days)).strftime("%Y-%m-%d")


def ready(page):
    page.wait_for_selector("#view-today .hero, #view-today .empty", timeout=10000)


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
    page.evaluate(f"localStorage.setItem('{KEY}', JSON.stringify({{v: 1, goals: [], current: null, seen: true}}))")
    page.reload()
    ready(page)


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


def flow_first_open_shows_example(page, shot):
    ready(page)
    assert "예시 목표예요" in page.inner_text("#view-today"), "처음 열었는데 예시 안내가 없음"
    assert page.locator(".hero h1").inner_text() == "토익 850점 받기"
    assert re.search(r"D-\d+", page.inner_text(".hero .dday")), "D-day가 없음"
    assert page.locator(".mosaic i").count() > 30, "진행 모자이크가 안 그려짐"
    assert page.locator(".mosaic i.d").count() >= 3, "끝낸 칸이 칠해지지 않음"
    assert rows(page).count() >= 2, "오늘의 15분 목록이 비어 있음"
    assert rows(page).locator(".chk[aria-pressed='true']").count() >= 1 and rows(page).locator(".chk[aria-pressed='false']").count() >= 1, "끝낸 칸과 남은 칸이 함께 보여야 함"
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
    assert len(st["goals"]) == 1 and not st["goals"][0].get("sample"), "예시 목표가 지워지지 않음"
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
    first_open = rows(page).locator(".chk[aria-pressed='false']").first
    first_open.click()
    assert done_minutes(page) == before + 15, f"체크했는데 끝낸 시간이 15분 늘지 않음: {before} → {done_minutes(page)}"
    assert rows(page).count() == n_rows, "체크했더니 오늘 목록 길이가 바뀜(흔들림)"
    page.reload()
    ready(page)
    assert done_minutes(page) == before + 15, "새로고침 후 체크가 사라짐"
    rows(page).locator(".chk[aria-pressed='true']").last.click()
    assert done_minutes(page) == before, "체크를 되돌려도 끝낸 시간이 그대로"


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
    title.fill("마지막 점검 주간")
    title.press("Enter")
    page.locator("h2.view-title").click()
    node = page.locator(".chain .node[id^='step-']", has=page.locator("input.step-title[value='마지막 점검 주간']"))
    assert node.count() == 1, "새 중간 목표 이름이 저장되지 않음"
    inp = node.locator(".addtask input")
    inp.fill("모의고사 오답만 다시")
    node.locator(".addtask button[aria-label='15분 늘리기']").click()
    node.locator(".addtask button", has_text="할 일 추가").click()
    node = page.locator(".chain .node[id^='step-']", has=page.locator("input.step-title[value='마지막 점검 주간']"))
    task = node.locator(".task").first
    assert task.locator("output").inner_text() == "45분", f"할 일 시간이 45분이 아님: {task.locator('output').inner_text()}"
    task.locator("button[aria-label$='15분 늘리기']").click()
    node = page.locator(".chain .node[id^='step-']", has=page.locator("input.step-title[value='마지막 점검 주간']"))
    assert node.locator(".task output").first.inner_text() == "1시간", "15분 늘리기가 안 됨"
    assert node.locator(".task .sq i").count() == 4, "15분 칸 그림이 4칸이 아님"
    shot("plan")
    node.locator(".step-titlerow .icon-btn").click()
    assert page.is_visible("#sheet"), "지우기 전에 확인을 묻지 않음"
    page.click("#sheet .btn.primary")
    assert page.locator("input.step-title[value='마지막 점검 주간']").count() == 0, "확인 후에도 지워지지 않음"


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
              "{\"title\":\"기출 3회 풀기\",\"due\":\"" + kst(22) + "\",\"tasks\":[{\"title\":\"2023년 1회\",\"minutes\":90}]},"
              "{\"title\":\"정보처리기사 필기\",\"due\":\"" + kst(30) + "\",\"tasks\":[{\"title\":\"오답 노트 훑기\",\"minutes\":\"45분\"}]}]}\n```\n바꾸고 싶은 곳은 {단계 이름}으로 말씀해 주세요")
    page.click("#sheet .sheet-actions .btn.primary")
    page.wait_for_selector("#sheet[hidden]", state="attached", timeout=5000)
    st = saved(page)["goals"][0]
    titles = [s["title"] for s in st["steps"]]
    assert titles == ["1과목 개념 정리", "기출 3회 풀기", "정보처리기사 필기"], f"Claude 답대로 채워지지 않음: {titles}"
    assert [k["blocks"] for k in st["steps"][0]["tasks"]] == [3, 2], "분이 15분 칸으로 바뀌지 않음(40분 → 3칸)"
    assert st["steps"][2]["tasks"][0]["title"] == "오답 노트 훑기", "마지막 항목이 최종 목표의 할 일로 들어가지 않음"
    page.click("button:has-text('Claude에게 나눠 달라기')")
    page.fill("#cAnswer", "죄송해요, 다시 해 볼게요")
    page.click("#sheet .sheet-actions .btn.primary")
    assert "찾지 못했어요" in page.inner_text("#sheet"), "엉뚱한 답을 붙여넣었을 때 안내가 없음"


def flow_backup_roundtrip(page, shot):
    ready(page)
    tab(page, "goals")
    with page.expect_download() as dl:
        page.click("#exportBtn")
    path = dl.value.path()
    data = json.load(open(path, encoding="utf-8"))
    assert data["app"] == KEY and len(data["data"]["goals"]) == 1, "백업 파일 내용이 맞지 않음"
    fresh(page)
    tab(page, "goals")
    page.set_input_files("#importFile", path)
    page.wait_for_selector("#sheet:not([hidden])", timeout=5000)   # 가져오기 전에 확인을 물어야 함
    page.click("#sheet .btn.primary")
    tab(page, "today")
    assert page.locator(".hero h1").inner_text() == "토익 850점 받기", "백업에서 목표를 되살리지 못함"


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
    assert len(opts) == 2 and "두 번째 목표" in page.locator(".hero h1").inner_text(), f"새 목표로 바뀌지 않음: {opts}"
    page.select_option("#goalPick", label=[o for o in opts if "첫 번째" in o][0])
    assert page.locator(".hero h1").inner_text() == "첫 번째 목표", "목표 고르기가 안 됨"
    tab(page, "goals")
    page.locator(".goal-item", has_text="두 번째 목표").locator("button", has_text="지우기").click()
    page.click("#sheet .btn.primary")
    assert page.locator(".goal-item").count() == 1, "목표가 지워지지 않음"
    page.reload()
    ready(page)
    assert page.locator("#goalPick option").count() == 1, "새로고침 후 지운 목표가 돌아옴"


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
    """Claude 앱에 다녀오는 사이 앱이 닫혀도 만들던 목표가 이어짐 · '그만두기'를 누르면 버림"""
    ready(page)
    page.locator("button", has_text="내 목표 세우기").click()
    page.fill("#wzTitle", "책 원고 1권 쓰기")
    page.fill("#wzDeadline", kst(90))
    page.click(".sheet-actions .btn.primary")
    page.fill("#wzMid", "초고 절반")
    page.fill("#wzMidDate", kst(45))
    page.click(".ask button")
    page.reload()
    page.wait_for_selector("#sheet:not([hidden])", timeout=5000)
    assert "2 / 4" in page.inner_text("#panel"), "다시 열었을 때 만들던 단계로 돌아오지 않음"
    items = page.locator(".wz-list li").all_inner_texts()
    assert "책 원고 1권 쓰기" in items[0] and "초고 절반" in items[1], f"만들던 내용이 사라짐: {items}"
    page.click("#panel button:has-text('그만두기')")
    page.reload()
    ready(page)
    assert page.locator("#sheet").is_hidden(), "그만둔 목표 만들기가 다시 열림"
    assert saved(page).get("draft") is None, "그만뒀는데 만들던 내용이 저장소에 남음"
