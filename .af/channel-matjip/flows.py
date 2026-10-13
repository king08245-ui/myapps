import json
import re


def ready(page):
    page.wait_for_function("document.getElementById('dbStat').textContent.length > 0", timeout=15000)


def slips(page):
    return page.locator("#results article.slip")


def to_results(page):
    page.evaluate("document.getElementById('resultTitle').closest('section').scrollIntoView({block: 'start'})")
    page.wait_for_timeout(200)


def km_values(page):
    """Distances of shops with an address point, in list order (rough '약…/…근처' pills are a separate group)."""
    vals = []
    for t in page.locator("#results .dist").all_inner_texts():
        if "약" in t or "근처" in t:
            continue
        m = re.findall(r"([\d.]+)\s*(km|m)\b", t)
        if m:
            num, unit = m[-1]
            vals.append(float(num) / (1000 if unit == "m" else 1))
    return vals


def area(page, term):
    page.click("#modeArea")
    page.fill("#q", term)
    page.click("#searchBtn")
    page.wait_for_function("!document.getElementById('resultNote').textContent.includes('찾는 중')", timeout=20000)


def menu(page, term):
    page.click("#modeMenu")
    page.fill("#q", term)
    page.click("#searchBtn")


def names(page):
    return page.evaluate("[...document.querySelectorAll('#results article.slip h3')].map(h => h.firstChild.textContent)")


def all_names(page):
    """Open every '더 보기' page, then return all shop names."""
    for _ in range(200):   # 10/14부터 가게 4,800여 곳 — '내 근처 전체'는 120번 넘게 눌러야 끝까지
        more = page.locator("#results button.more")
        if not more.count():
            break
        more.click()
    return names(page)


def count(page):
    m = re.match(r"(\d+)곳", page.inner_text("#resultNote"))
    return int(m.group(1)) if m else 0


def flow_area_search(page, shot):
    ready(page)
    page.get_by_role("button", name="종로3가", exact=True).click()
    n = slips(page).count()
    assert n > 0, "종로3가 검색 결과가 없음"
    note = page.inner_text("#resultNote")
    assert "곳" in note, "결과 개수 표시가 없음"
    assert "종로3가역에서 가까운 순" in note, f"찾은 동네 기준 정렬 안내가 없음: {note}"
    first = slips(page).first
    assert first.locator("a", has_text="네이버지도").count() == 1, "가게 카드에 네이버지도 링크가 없음"
    assert first.locator("a", has_text="영상").count() == 1, "가게 카드에 영상 링크가 없음"
    d = km_values(page)
    assert d == sorted(d), f"가까운 순 정렬이 아님: {d[:8]}"
    assert d and d[0] <= 0.5, f"종로3가 검색 첫 가게가 종로3가에서 멀다: {d[:3]}"
    page.wait_for_function("""() => { const t = document.getElementById('resultTitle').closest('section').getBoundingClientRect().top;
        return t > -10 && t < innerHeight * 0.5; }""", timeout=3000)   # 결과가 화면 아래에 숨지 않음
    to_results(page)
    shot("area")


def flow_area_words_stay_whole(page, shot):
    ready(page)
    area(page, "서울역")
    n = count(page)
    assert 0 < n < 100, f"서울역 검색이 서울 전체를 끌어옴({n}곳)"
    area(page, "시청")
    addr = page.inner_text("#results")
    assert "속초" not in addr, "시청 검색에 속초시 청학로가 섞임"
    area(page, "대구")
    assert "해운대구" not in page.inner_text("#results"), "대구 검색에 해운대구가 섞임"
    assert "대구에서 가까운 순" in page.inner_text("#resultNote"), "대구 검색이 대구 기준으로 정렬되지 않음"
    area(page, "명동")
    assert not any("동명동" in t for t in page.locator("#results .meta").all_inner_texts()), "명동 검색에 동명동이 섞임"
    area(page, "강남역")
    assert count(page) >= 5, "강남역 근처가 너무 적음(반경 넓히기 실패)"


def flow_menu_search(page, shot):
    ready(page)
    page.click("#modeMenu")
    assert page.inner_text("#regionLabel") == "어떤 메뉴?", "메뉴 모드로 바뀌지 않음"
    page.fill("#q", "순댓국")
    page.click("#searchBtn")
    n = slips(page).count()
    assert n >= 5, f"순댓국 결과가 너무 적음({n})"
    ns = " ".join(names(page))
    assert "순대" in ns or "순댓" in ns, "순대국 가게가 결과에 없음"
    to_results(page)
    shot("menu")
    menu(page, "간짜장")
    ns = all_names(page)
    assert ns, "간짜장 결과가 없음"
    # 예전 버그: 여러 가게가 나온 영상 제목의 '짜장면' 때문에 술맛여행놈 '홍두깨국수'가 걸림
    # (맛삼인 '홍두깨칼국수'는 짜장면도 파는 집을 혼자 다룬 영상이라 나와도 맞음)
    assert "홍두깨국수" not in ns and "신성식당" not in ns, "간짜장 검색에 관계없는 가게가 섞임(예전 버그)"


def flow_menu_noise_and_recall(page, shot):
    ready(page)
    menu(page, "해장국")
    ns = all_names(page)
    assert "국수포차" not in ns and "역전할머니맥주" not in ns, "해장국 검색에 술집이 섞임"
    menu(page, "순대국")
    ns = all_names(page)
    assert "재구네닭발" not in ns and not any("양꼬치" in x for x in ns), "순대국 검색에 관계없는 가게가 섞임"
    for term, least in (("회", 10), ("고기", 20), ("빵", 3), ("국밥", 20)):
        menu(page, term)
        assert count(page) >= least, f"'{term}' 결과가 너무 적음({count(page)}곳)"


def flow_channel_toggle_persists(page, shot):
    ready(page)
    page.get_by_role("button", name="을지로", exact=True).click()
    before = page.inner_text("#resultNote")
    chip = page.locator("#channels button", has_text="술맛여행놈")
    chip.click()
    assert chip.get_attribute("aria-pressed") == "false", "채널이 꺼지지 않음"
    after = page.inner_text("#resultNote")
    assert after != before, "채널을 꺼도 결과가 그대로임"
    page.reload()
    ready(page)
    assert page.locator("#channels button", has_text="술맛여행놈").get_attribute("aria-pressed") == "false", "새로고침 후 채널 설정이 사라짐"
    page.locator("#channels button", has_text="술맛여행놈").click()


def flow_channels_all_off_message(page, shot):
    ready(page)
    page.get_by_role("button", name="을지로", exact=True).click()
    for b in page.locator("#channels button").all():
        b.click()
    assert "채널이 모두 꺼져" in page.inner_text("#results"), "채널을 다 끈 상태 안내가 없음"
    # switching the search mode clears the old search, so toggling a channel must not bring the old area back
    page.click("#modeMenu")
    page.locator("#channels button").first.click()
    assert page.inner_text("#resultTitle") == "결과", "메뉴로 바꾼 뒤 채널을 누르자 예전 동네 검색이 다시 나옴"


def flow_preset_location_sorts(page, shot):
    ready(page)
    page.locator("#herePresets button", has_text="강남역").click()
    assert page.inner_text("#hereName") == "강남역", "위치가 강남역으로 바뀌지 않음"
    page.click("#modeMenu")
    page.fill("#q", "냉면")
    page.click("#searchBtn")
    d = km_values(page)
    assert len(d) > 2 and d == sorted(d), f"강남역 기준 가까운 순이 아님: {d[:8]}"
    page.reload()
    ready(page)
    assert page.inner_text("#hereName") == "강남역", "새로고침 후 위치가 사라짐"
    page.locator("#herePresets button", has_text="위치 끄기").click()
    page.reload()
    ready(page)
    assert page.inner_text("#hereName") == "아직 정하지 않았어요", "위치 끄기가 새로고침 후 유지되지 않음"


def flow_gps_near_me(page, shot):
    ready(page)
    page.context.grant_permissions(["geolocation"])
    page.context.set_geolocation({"latitude": 37.5704, "longitude": 126.9921})
    page.click("#gpsBtn")
    page.wait_for_function("document.getElementById('hereName').textContent === '현재 위치'", timeout=8000)
    page.click("#nearBtn")
    assert "현재 위치" in page.inner_text("#resultTitle"), "내 근처 결과 제목이 없음"
    n = slips(page).count()
    assert n > 0, "현재 위치 근처 가게가 없음(종로3가 기준)"
    d = km_values(page)
    assert d and d == sorted(d), f"내 근처 목록이 가까운 순이 아님: {d[:8]}"
    # rough points must not sit inside the close bands (500m·1km·3km) — their distance is only the neighbourhood's
    bad = page.evaluate("""() => { let g = '', bad = 0;
        for (const n of document.querySelectorAll('#results h2.group, #results article.slip')) {
          if (n.tagName === 'H2') { g = n.textContent; continue; }
          const t = n.querySelector('.dist')?.textContent || '';
          if (/(500m|1km|3km) 이내/.test(g) && /약|근처/.test(t)) bad++;
        } return bad; }""")
    assert bad == 0, f"대략 위치 가게 {bad}곳이 가까운 거리 묶음(…이내)에 섞임"
    to_results(page)
    shot("near-me")
    # near-me list follows channel switches
    n0 = page.locator("#resultNote").inner_text()
    page.locator("#channels button").first.click()
    assert page.locator("#resultNote").inner_text() != n0, "내 근처 목록이 채널 끄기를 따르지 않음"
    assert "현재 위치 근처 전체" in page.inner_text("#resultTitle"), "채널을 끄자 내 근처 목록이 사라짐"
    page.locator("#channels button").first.click()
    # picking a preset while looking at near-me updates the list and its title
    page.locator("#herePresets button", has_text="서울역").click()
    assert page.inner_text("#resultTitle") == "서울역 근처 전체", f"위치를 바꿔도 제목이 그대로: {page.inner_text('#resultTitle')}"


def flow_near_me_has_no_distance_limit(page, shot):
    """'내 근처 전체 보기'는 3km 제한 없이 위치를 아는 가게 전부를 가까운 순으로(대략 위치 가게도 거리 순서에 맞게)"""
    ready(page)
    page.locator("#herePresets button", has_text="공덕역").click()
    page.click("#nearBtn")
    note = page.inner_text("#resultNote")
    total = count(page)
    assert total >= 1000 and "거리 제한 없음" in note, f"거리 제한 없이 전부 나오지 않음: {note}"
    groups = page.locator("#results h2.group").all_inner_texts()
    all_names(page)
    groups = page.locator("#results h2.group").all_inner_texts()
    labels = [g.split(" · ")[0] for g in groups]
    order = ["500m 이내", "1km 이내", "3km 이내", "대략 위치", "10km 이내", "50km 이내", "50km 밖"]
    idx = [next(i for i, o in enumerate(order) if o in lab) for lab in labels]
    assert idx == sorted(idx) and len(set(labels)) == len(labels), f"거리 묶음 순서가 뒤섞임: {labels}"
    assert any("50km 밖" in lab for lab in labels), f"50km 밖 가게(부산·제주 등)가 안 나옴: {labels}"
    assert slips(page).count() == total, f"'더 보기'를 다 열었는데 개수가 다름: {slips(page).count()} / {total}"
    d = km_values(page)
    assert max(d) > 100, f"멀리 있는 가게가 안 나옴(최대 {max(d)}km)"
    # 지도로 보기: 처음엔 가까운 곳을 비추고, '전체'를 누르면 먼 가게까지 보임
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    near_pins = page.locator(".mapwrap svg circle.pin").count()
    page.click(".mapctl button.wide")
    page.wait_for_timeout(200)
    all_pins = page.locator(".mapwrap svg circle.pin").count()
    assert all_pins > near_pins and all_pins >= 1000, f"지도 '전체'에 먼 가게가 안 나옴: 처음 {near_pins} → 전체 {all_pins}"


def gu_label_boxes(page):
    return page.evaluate("""() => { const s = document.querySelector('.mapwrap svg').getBoundingClientRect();
        const box = e => { const r = e.getBoundingClientRect(); return {t: e.textContent, l: r.left - s.left, r: r.right - s.left, top: r.top - s.top, b: r.bottom - s.top}; };
        return {w: s.width, h: s.height, gu: [...document.querySelectorAll('.mapwrap svg .gulabel')].map(box),
                stn: [...document.querySelectorAll('.mapwrap svg .stnlabel')].map(box)}; }""")


def overlaps(a, b):
    return a["l"] < b["r"] - 1 and b["l"] < a["r"] - 1 and a["top"] < b["b"] - 1 and b["top"] < a["b"] - 1


def flow_map_shows_gu_names(page, shot):
    """지도에 서울 구 경계와 이름: 이웃한 구는 다른 바탕색, 서울을 볼 때 구 이름이 여럿, 확대해도 보이는 구의 이름이 화면 안에(역 이름과 안 겹침)"""
    ready(page)
    page.locator("#herePresets button", has_text="공덕역").click()
    page.click("#nearBtn")
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg .gulabel", timeout=8000)
    tint = page.evaluate("Object.fromEntries([...document.querySelectorAll('.mapwrap svg path.gu')].map(p => [p.dataset.n, p.getAttribute('class')]))")
    assert len(tint) == 25, f"서울 구 경계가 25개가 아님: {len(tint)}"
    for a, b in (("마포구", "용산구"), ("마포구", "서대문구"), ("용산구", "중구"), ("중구", "종로구"), ("강남구", "서초구"), ("마포구", "영등포구")):
        assert tint[a] != tint[b], f"맞닿은 {a}·{b}가 같은 바탕색: {tint[a]}"
    g = gu_label_boxes(page)
    names = [x["t"] for x in g["gu"]]
    assert "마포구" in names and "용산구" in names and len(names) >= 10, f"서울 지도에 구 이름이 모자람: {names}"
    page.evaluate("document.querySelector('.mapwrap').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    shot("map-gu-seoul", store=False)
    for term, expect in (("종로3가", ("종로구", "중구")), ("공덕역", ("마포구",))):
        area(page, term)
        page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
        g = gu_label_boxes(page)
        names = [x["t"] for x in g["gu"]]
        assert any(e in names for e in expect), f"{term} 근처를 확대한 지도에 구 이름이 없음: {names}"
        for x in g["gu"]:
            assert x["l"] >= -1 and x["top"] >= -1 and x["r"] <= g["w"] + 1 and x["b"] <= g["h"] + 1, f"구 이름이 지도 밖으로 잘림: {x}"
        bad = [(a["t"], b["t"]) for i, a in enumerate(g["gu"]) for b in g["gu"][i + 1:] + g["stn"] if overlaps(a, b)]
        assert not bad, f"구 이름이 다른 이름과 겹침: {bad}"
    page.click(".mapctl button[aria-label='확대']")
    page.click(".mapctl button[aria-label='확대']")
    g = gu_label_boxes(page)
    assert g["gu"], "많이 확대하자 구 이름이 모두 사라짐"
    page.evaluate("document.querySelector('.mapwrap').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    shot("map-gu-zoom", store=False)


def svg_boxes(page, sel):
    return page.evaluate("""(sel) => { const s = document.querySelector('.mapwrap svg').getBoundingClientRect();
        return [...document.querySelectorAll(sel)].map(e => { const r = e.getBoundingClientRect();
          return {t: e.textContent, l: r.left - s.left, r: r.right - s.left, top: r.top - s.top, b: r.bottom - s.top, w: s.width, h: s.height}; }); }""", sel)


def map_km(page):
    """지금 지도 폭(km): viewBox 폭 × 1.113"""
    return float(page.get_attribute(".mapwrap svg", "viewBox").split()[2]) * 1.1132


def flow_zoomed_in_shows_all_names(page, shot):
    """3km 안팎으로 확대하면 고르지 않아도 점 위에 가게 이름이 뜨고(겹치지 않게), 넓게 보면 사라짐"""
    ready(page)
    area(page, "종로3가")
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    for _ in range(4):
        if map_km(page) <= 3.5:
            break
        page.click(".mapctl button[aria-label='확대']")
    assert map_km(page) <= 3.6, f"확대가 안 됨: {map_km(page):.1f}km"
    labels = svg_boxes(page, ".mapwrap svg .plabel")
    assert len(labels) >= 5, f"{map_km(page):.1f}km 폭으로 확대했는데 가게 이름이 거의 없음: {len(labels)}개"
    titles = set(page.locator(".mapwrap svg circle.pin title").all_text_contents())
    for x in labels:
        base = x["t"].replace("✓ ", "")
        assert any(t == base or (base.endswith("…") and t.startswith(base[:-1])) for t in titles), f"지도에 없는 가게 이름: {x['t']}"
        assert x["l"] >= -1 and x["top"] >= -1 and x["r"] <= x["w"] + 1 and x["b"] <= x["h"] + 1, f"가게 이름이 지도 밖으로 잘림: {x}"
    gus = svg_boxes(page, ".mapwrap svg .gulabel")
    bad = [(a["t"], b["t"]) for i, a in enumerate(labels) for b in labels[i + 1:] + gus if overlaps(a, b)]
    assert not bad, f"가게 이름끼리(또는 구 이름과) 겹침: {bad[:3]}"
    page.evaluate("document.querySelector('.mapwrap').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    shot("map-names", store=False)
    # 고른 가게는 말풍선 하나로만(같은 이름이 두 번 뜨지 않게)
    pin = page.locator(".mapwrap svg circle.pin").first
    name = pin.locator("title").text_content()
    pin.dispatch_event("click")
    page.wait_for_selector(".mapwrap svg .sellabel", timeout=3000)
    dup = [x for x in svg_boxes(page, ".mapwrap svg .plabel") if x["t"].replace("✓ ", "") == name]
    assert not dup, f"고른 가게 이름이 말풍선과 이름표로 두 번 뜸: {name}"
    for _ in range(3):
        page.click(".mapctl button[aria-label='축소']")
    assert map_km(page) > 3.6 and page.locator(".mapwrap svg .plabel").count() == 0, f"넓게 봤는데 가게 이름이 남음({map_km(page):.1f}km)"


def slips_by_vk(page, vk):
    return page.evaluate("""(vk) => [...document.querySelectorAll('#results article.slip')].filter(a => a.dataset.vk === vk)
        .map(a => ({cls: a.className, text: a.innerText, pressed: a.querySelector('button.visit')?.getAttribute('aria-pressed')}))""", vk)


def flow_visited_shops_marked_gray(page, shot):
    """가 본 집 체크: 카드·지도 점이 회색, 새로고침해도 남고, 지도에서 바꿔도 확대가 그대로, 백업으로 옮기기"""
    import tempfile
    ready(page)
    area(page, "종로3가")
    first = slips(page).first
    name = first.locator("h3").evaluate("h => h.firstChild.textContent")
    vk = first.get_attribute("data-vk")
    first.locator("button.visit").click()
    marked = slips_by_vk(page, vk)
    assert marked and all("visited" in m["cls"] for m in marked), "가 봤어요를 눌렀는데 카드가 회색으로 안 바뀜"
    assert "✓ 가 봤어요" in marked[0]["text"] and marked[0]["pressed"] == "true", "가 본 집 표시가 카드에 없음"
    assert "가 본 집 1곳" in page.inner_text("#visitCount"), f"가 본 집 수가 안 보임: {page.inner_text('#visitCount')}"
    page.reload()
    ready(page)
    area(page, "종로3가")
    again = slips_by_vk(page, vk)
    assert again and "visited" in again[0]["cls"], "새로고침하자 가 본 집 표시가 사라짐"
    to_results(page)
    shot("visited", store=False)
    # 지도: 회색 점 + 범례, 지도에서 바꿔도 확대·위치 그대로
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    gray = page.locator(".mapwrap svg circle.pin.seen")
    assert gray.count() >= 1 and "(가 봤어요)" in gray.first.locator("title").text_content(), "가 본 집 점이 회색이 아님"
    assert page.locator(".maplegend span:not([hidden])", has_text="가 본 집").count() == 1, "지도 범례에 가 본 집이 없음"
    page.click(".mapctl button[aria-label='확대']")
    vb0 = page.get_attribute(".mapwrap svg", "viewBox")
    other = page.locator(".mapwrap svg circle.pin:not(.seen)").first
    other_name = other.locator("title").text_content()
    other.dispatch_event("click")
    page.wait_for_selector(".mapwrap + div article.slip", timeout=4000)
    page.locator(".mapwrap + div article.slip button.visit").click()
    assert page.get_attribute(".mapwrap svg", "viewBox") == vb0, "지도에서 가 봤어요를 누르자 확대·위치가 처음으로 돌아감"
    sel = page.locator(".mapwrap svg circle.pin.sel")
    assert "seen" in (sel.get_attribute("class") or ""), f"지도에서 체크한 가게({other_name}) 점이 회색이 안 됨"
    assert page.locator(".mapwrap + div article.slip.visited").count() == 1, "지도 아래 카드가 회색으로 안 바뀜"
    assert page.locator(".mapwrap svg .sellabel text").text_content().startswith("✓ "), "가 본 집 말풍선에 체크 표시가 없음"
    page.locator(".mapwrap + div article.slip button.visit").click()   # 다시 누르면 지움
    assert "seen" not in (page.locator(".mapwrap svg circle.pin.sel").get_attribute("class") or ""), "체크를 지웠는데 점이 회색으로 남음"
    # 백업 내보내기 → 지우고 → 가져오기
    with page.expect_download() as dl:
        page.click("#visitExport")
    path = dl.value.path()
    data = json.load(open(path, encoding="utf-8"))
    assert data["app"] == "channel-matjip" and vk in data["visited"] and data["names"].get(vk) == name, f"백업 파일 내용이 이상함: {data}"
    page.evaluate("localStorage.removeItem('cfn.visited')")
    page.reload()
    ready(page)
    assert "가 본 집 1곳" not in page.inner_text("#visitCount"), "지웠는데 가 본 집이 남음"
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(data, f, ensure_ascii=False)
    f.close()
    page.set_input_files("#visitImport", f.name)
    page.wait_for_function("document.getElementById('visitCount').textContent.includes('1곳 더함')", timeout=4000)
    page.set_input_files("#visitImport", f.name)   # 같은 파일을 또 가져와도 늘지 않음
    page.wait_for_function("document.getElementById('visitCount').textContent.includes('새로 더할 곳 없음')", timeout=4000)
    assert "가 본 집 1곳" in page.inner_text("#visitCount"), "백업을 가져왔는데 가 본 집이 돌아오지 않음"


def flow_map_pin_shows_name(page, shot):
    """지도에서 점을 누르면 그 가게 이름이 지도 위 말풍선으로 뜨고, 빈 곳을 누르면 사라짐"""
    ready(page)
    page.get_by_role("button", name="종로3가", exact=True).click()
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    assert page.locator(".mapwrap svg .sellabel").count() == 0, "아무것도 안 골랐는데 이름표가 있음"
    for pick in ("first", "last"):
        pin = getattr(page.locator(".mapwrap svg circle.pin"), pick)
        name = pin.locator("title").text_content()
        pin.dispatch_event("click")
        page.wait_for_selector(".mapwrap + div article.slip", timeout=4000)
        lab = page.locator(".mapwrap svg .sellabel text")
        assert lab.count() == 1, "점을 눌렀는데 지도에 가게 이름이 안 뜸"
        shown = lab.text_content()
        assert shown == name or (shown.endswith("…") and name.startswith(shown[:-1])), f"지도 이름표가 고른 가게와 다름: {shown} / {name}"
        card = page.locator(".mapwrap + div article.slip h3").evaluate("h => h.firstChild.textContent")
        assert card == name, f"아래 카드가 고른 가게와 다름: {card} / {name}"
        box = page.evaluate("""() => { const s = document.querySelector('.mapwrap svg').getBoundingClientRect(),
            r = document.querySelector('.mapwrap svg .sellabel rect').getBoundingClientRect();
            return [r.left - s.left, s.right - r.right, r.top - s.top, s.bottom - r.bottom]; }""")
        assert min(box) >= -1, f"이름표가 지도 밖으로 잘림: {box}"
    page.evaluate("document.querySelector('.mapwrap').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    shot("map-name", store=False)
    page.click(".mapctl button[aria-label='확대']")
    assert page.locator(".mapwrap svg .sellabel").count() == 1, "확대하자 이름표가 사라짐"
    page.locator(".mapwrap svg").click(position={"x": 30, "y": 30})
    assert page.locator(".mapwrap svg .sellabel").count() == 0, "빈 곳을 눌렀는데 이름표가 남음"


def flow_stale_gps_label(page, shot):
    page.evaluate("localStorage.setItem('cfn.origin', JSON.stringify({name: '현재 위치', lat: 37.55, lng: 126.97, gps: true}))")
    page.reload()
    ready(page)
    assert page.inner_text("#hereName") == "지난번 위치", "지난번 GPS 위치를 '현재 위치'라고 보여줌"


def flow_typed_location(page, shot):
    ready(page)
    page.fill("#hereInput", "합정역")
    page.click("#hereBtn")
    assert page.inner_text("#hereName") == "합정역", "합정역 입력이 위치로 설정되지 않음"
    page.fill("#hereInput", "망원동")
    page.click("#hereBtn")
    assert page.inner_text("#hereName") == "망원", "동 이름 입력이 위치로 설정되지 않음"
    page.fill("#hereInput", "없는장소이름123")
    page.click("#hereBtn")
    # 검수 환경은 외부 인터넷이 막혀 있으므로 '인터넷 연결' 안내가, 실제 폰에서는 '못 찾았어요'가 나와야 함
    page.wait_for_function("/못 찾았어요|인터넷/.test(document.getElementById('hereHint').textContent)", timeout=20000)


def flow_map_view(page, shot):
    ready(page)
    page.get_by_role("button", name="종로3가", exact=True).click()
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    pins = page.locator(".mapwrap svg circle.pin").count()
    assert pins > 0, "지도에 가게 점이 없음"
    assert page.locator("a.gmap").count() == 1, "구글지도에서 보기 버튼이 없음"
    page.locator(".mapwrap svg circle.pin").last.dispatch_event("click")
    page.wait_for_selector(".mapwrap + div article.slip", timeout=4000)
    page.evaluate("document.querySelector('.mapwrap').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    shot("map")
    page.click("#viewBtn")
    assert slips(page).count() > 0, "목록 보기로 돌아오지 않음"


def flow_rough_shop_map_links(page, shot):
    ready(page)
    area(page, "망원동")
    all_names(page)   # 가게가 많아져 주소 없는 가게(대략 위치 묶음)는 '더 보기' 뒤에 있음
    hrefs = page.evaluate("""[...document.querySelectorAll('#results article.slip')]
        .filter(a => !a.querySelector('.meta span')?.textContent.startsWith('📍'))
        .map(a => a.querySelector('a[href*="map.naver.com"]').href)""")
    assert hrefs, "주소 없는 가게가 없어 확인 불가(데이터 확인 필요)"
    bad = [h for h in hrefs if "%EB%A7%9D%EC%9B%90" not in h]   # '망원'
    assert not bad, f"주소 없는 가게의 지도 링크에 동네 이름이 빠짐: {bad[:2]}"


def flow_empty_and_more(page, shot):
    ready(page)
    page.fill("#q", "없는동네이름")
    page.click("#searchBtn")
    page.wait_for_function("!document.getElementById('resultNote').textContent.includes('찾는 중')", timeout=20000)
    t = page.inner_text("#results")
    assert "못 찾았어요" in t or "찾지 못했어요" in t, f"결과 없음 안내가 없음: {t[:80]}"
    assert "찾는 중" not in t, "장소 찾기가 끝났는데 '찾는 중'이 남아 있음"
    page.get_by_role("button", name="은평구", exact=True).click()
    more = page.locator("#results button.more")
    if more.count():
        n0 = slips(page).count()
        more.click()
        assert slips(page).count() > n0, "더 보기가 동작하지 않음"
    ok = page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1")
    assert ok, "결과 화면에서 가로 스크롤 발생"


# ---------- 2차 독립 검수에서 나온 문제의 재발 방지 ----------

def cards(page):
    """보이는 가게 카드: 이름, 주소(📍 줄), 거리 표시."""
    return page.evaluate("""[...document.querySelectorAll('#results article.slip')].map(a => ({
        n: a.querySelector('h3').firstChild.textContent,
        a: (a.querySelector('.meta span')?.textContent || '').replace('📍 ', ''),
        d: a.querySelector('.dist')?.textContent || ''}))""")


def km_of(text):
    m = re.findall(r"([\d.]+)\s*(km|m)\b", text)
    if not m:
        return None
    num, unit = m[-1]
    return float(num) / (1000 if unit == "m" else 1)


def flow_same_name_shops_stay_apart(page, shot):
    ready(page)                                   # 기본 위치: 공덕역
    menu(page, "분식")
    all_names(page)
    for c in cards(page):
        if c["a"].startswith("부산"):
            k = km_of(c["d"])
            assert k is None or k > 200, f"부산 가게가 공덕역 가까이 나옴(다른 가게 좌표와 합쳐짐): {c}"
    menu(page, "짬뽕")
    ns = all_names(page)
    assert ns.count("원성반점") >= 2, f"서울·강릉 원성반점이 한 카드로 합쳐짐: {ns.count('원성반점')}장"


def flow_fixed_coordinates(page, shot):
    ready(page)
    page.locator("#herePresets button", has_text="서울역").click()
    page.click("#nearBtn")
    all_names(page)
    cs = {c["n"]: c for c in cards(page)}
    k = km_of(cs.get("골목길", {}).get("d", "")) if "골목길" in cs else None
    assert k is None or k > 3.5, f"황학동 가게(골목길)가 서울역 가까이 나옴(틀린 좌표): {k}km"
    k = km_of(cs.get("무교동북어국집", {}).get("d", ""))
    assert k and 1.5 <= k <= 1.9, f"무교동북어국집 거리가 주소와 다름(서울역에서 약 1.7km여야 함): {k}"
    area(page, "종로3가")
    all_names(page)   # 종로3가 1km 안 가게가 40곳을 넘으면 우래옥은 '더 보기' 뒤에 있음
    cs = {c["n"]: c for c in cards(page)}
    k = km_of(cs.get("우래옥", {}).get("d", ""))
    assert k and 0.5 <= k <= 0.75, f"우래옥 거리가 주소와 다름(종로3가역에서 약 630m여야 함): {k}"


def flow_city_search_stays_in_city(page, shot):
    ready(page)
    for city, other in (("부산", ("강원", "경북", "속초")), ("속초", ("부산", "경북 포항"))):
        area(page, city)
        all_names(page)
        cs = cards(page)
        assert cs, f"{city} 결과가 없음"
        bad = [c for c in cs if c["a"].startswith(other)]
        assert not bad, f"{city} 검색에 다른 도시 가게가 섞임: {bad[:2]}"
        far = [c for c in cs if (km_of(c["d"]) or 0) > 60]
        assert not far, f"{city} 검색에 60km 넘는 가게가 섞임: {far[:2]}"


def flow_rough_point_uses_address(page, shot):
    ready(page)
    area(page, "속초")
    all_names(page)
    c = next((c for c in cards(page) if c["n"] == "어글리패티"), None)
    # 어글리패티는 '속초' 영상에 나온 고성 토성면 가게(속초에서 약 5km): 번지까지 정확한 좌표여도 속초 검색에 나와야 함
    assert c, "속초 검색에 어글리패티가 없음"
    k = km_of(c["d"])
    assert k is not None and k < 10, f"어글리패티가 주소(고성군 토성로 54) 대신 고성 중심 좌표를 씀: {c['d']}"


def gmap_href(page):
    a = page.locator("a.gmap")
    return a.get_attribute("href") if a.count() else None


def flow_gmap_route_sane(page, shot):
    from urllib.parse import unquote
    ready(page)
    page.locator("#herePresets button", has_text="위치 끄기").click()
    menu(page, "회")
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg", timeout=8000)
    assert gmap_href(page) is None, "기준 위치가 없는데 전국 가게로 구글지도 길찾기를 만듦"
    page.click("#viewBtn")                       # 목록으로
    page.locator("#herePresets button", has_text="공덕역").click()
    area(page, "제주")
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    h = unquote(gmap_href(page) or "")
    assert h, "제주 검색에 구글지도 버튼이 없음"
    assert "공덕역" not in h, "제주 가게 길찾기가 공덕역에서 출발함"
    page.click("#viewBtn")
    menu(page, "회")
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    h = unquote(gmap_href(page) or "")
    assert h and "공덕역" in h, "공덕역 기준 회 길찾기가 공덕역에서 출발하지 않음"
    for far in ("속초", "제주", "부산", "강릉"):
        assert far not in h, f"공덕역 근처 길찾기에 {far} 가게가 들어감"


def flow_map_pin_card_visible(page, shot):
    page.set_viewport_size({"width": 375, "height": 667})
    ready(page)
    area(page, "종로3가")
    to_results(page)                             # 결과 머리가 화면 맨 위 → '지도로 보기' → 지도 아래 카드는 화면 밖에서 시작
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    page.wait_for_timeout(200)
    page.locator(".mapwrap svg circle.pin").first.dispatch_event("click")
    page.wait_for_selector(".mapwrap + div article.slip", timeout=4000)
    page.wait_for_timeout(900)                   # 부드러운 스크롤
    r = page.evaluate("(() => { const r = document.querySelector('.mapwrap + div article.slip').getBoundingClientRect(); return [r.top, r.bottom, innerHeight]; })()")
    assert r[1] <= r[2] + 1 and r[0] >= -1, f"점을 눌러 뜬 가게 카드가 화면 밖에 있음: top={r[0]:.0f} bottom={r[1]:.0f} 화면={r[2]}"


def flow_hint_during_area_search(page, shot):
    ready(page)
    page.get_by_role("button", name="종로3가", exact=True).click()
    page.locator("#herePresets button", has_text="강남역").click()
    h = page.inner_text("#hereHint")
    assert "찾은 곳" in h and "종로3가" in h, f"동네 검색 중 위치를 바꿨을 때 안내가 실제 동작과 다름: {h}"
    menu(page, "냉면")
    assert "찾은 곳" not in page.inner_text("#hereHint"), "메뉴 검색인데 '찾은 곳 기준' 안내가 남음"


def flow_no_duplicate_cards(page, shot):
    ready(page)
    area(page, "성수동")
    ns = all_names(page)
    assert ns.count("행복식당") + ns.count("행복한식당") <= 1, "같은 주소의 행복식당/행복한식당이 두 장으로 나옴"
    area(page, "제주")
    ns = all_names(page)
    dup = [n for n in ns if "골목해장국" in n or n == "함덕골목"]
    assert len(dup) <= 1, f"같은 가게(함덕7길 6-14)가 여러 장으로 나옴: {dup}"


def flow_wider_radius_and_stations(page, shot):
    ready(page)
    area(page, "이태원")
    note = page.inner_text("#resultNote")
    if count(page) and "3km" in note:
        assert "넓힘" in note, f"반경을 3km로 넓혔다는 안내가 없음: {note}"
    area(page, "을지로4가")              # 인터넷 없이도 아는 역
    assert count(page) > 0, "을지로4가 검색 결과가 없음(역 목록에 없음)"
    assert "을지로4가역에서 가까운 순" in page.inner_text("#resultNote"), "을지로4가역 기준 정렬이 아님"


def flow_mode_switch_keeps_typed_word(page, shot):
    ready(page)
    page.fill("#q", "냉면")                 # 동네 모드에서 메뉴를 입력하고, 찾기 전에 '메뉴로'를 누름
    page.click("#modeMenu")
    assert page.input_value("#q") == "냉면", "메뉴로 바꾸자 입력한 글자가 지워짐"
    assert page.inner_text("#resultTitle") == "냉면 결과" and count(page) > 0, "바꾼 모드에서 입력한 메뉴를 찾지 않음"
    page.click("#modeArea")                 # 찾은 뒤 모드를 바꾸면 새 말을 넣도록 비움
    assert page.input_value("#q") == "", "검색이 끝난 말이 다른 모드로 넘어감"


def flow_map_buttons_before_outlines(page, shot):
    ready(page)
    # 지도 윤곽(map_seoul.json)이 늦게 오는 상황: 앱의 fetch를 감싸 그 파일만 붙잡아 둠
    # (서비스워커가 저장본으로 답하면 page.route로는 못 붙잡으므로 이렇게 함)
    page.evaluate("""() => { const f = window.fetch; const gate = new Promise(r => { window.__release = r; });
        window.fetch = (u, ...a) => String(u).includes('map_seoul') ? gate.then(() => f(u, ...a)) : f(u, ...a); }""")
    page.get_by_role("button", name="종로3가", exact=True).click()
    page.click("#viewBtn")
    # 지도 윤곽을 불러오기 전에 확대/축소/전체를 눌러도 오류가 없어야 함(오류는 검수 도구가 JS 오류로 잡음)
    page.evaluate("document.querySelectorAll('.mapctl button').forEach(b => b.click())")
    page.wait_for_timeout(300)
    page.evaluate("window.__release()")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    page.evaluate("document.querySelectorAll('.mapctl button').forEach(b => b.click())")
    page.wait_for_timeout(300)


def flow_keeps_other_apps_offline_copy(page, shot):
    """같은 주소(king08245-ui.github.io)의 다른 앱(하루동선) 저장본을 지우지 않아야 함 — 이 앱의 옛 저장본만 지움"""
    ready(page)
    page.evaluate("""async () => { await caches.open('dayroute-v9'); await caches.open('channel-matjip-v0');
        for (const r of await navigator.serviceWorker.getRegistrations()) await r.unregister(); }""")
    page.reload()
    ready(page)
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)   # 새로 깔린 서비스워커가 자리 잡을 때까지
    page.wait_for_timeout(300)
    keys = page.evaluate("caches.keys()")
    assert "dayroute-v9" in keys, f"하루동선의 오프라인 저장본을 지움: {keys}"
    assert "channel-matjip-v0" not in keys, f"이 앱의 옛 저장본이 남음: {keys}"


# ---------- 10/14 — 유튜브 채널 4개 추가(맛삼인·쏘울맛집·하이갱스·서울 사는 남자) ----------
NEW_CH = ["맛삼인", "쏘울맛집", "하이갱스", "서울 사는 남자"]


def chip_counts(page):
    out = {}
    for t in page.locator("#channels button").all_inner_texts():
        m = re.match(r"(.+?)\s+(\d+)$", t.strip())
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def flow_seven_channels_with_own_colors(page, shot):
    """채널 7개가 버튼으로 나오고, 새 채널마다 가게가 있고, 채널 색이 모두 다르다"""
    ready(page)
    c = chip_counts(page)
    assert len(c) == 7, f"채널이 7개가 아님: {list(c)}"
    for ch in ["백년해방", "술맛여행놈", "쇼리뷰"] + NEW_CH:
        assert c.get(ch, 0) > 0, f"{ch} 채널 가게가 없음: {c}"
    assert c["하이갱스"] >= 1000 and c["쏘울맛집"] >= 300 and c["맛삼인"] >= 200, f"새 채널 가게 수가 너무 적음: {c}"
    cols = page.evaluate("[...document.querySelectorAll('#channels .sw')].map(s => getComputedStyle(s).backgroundColor)")
    assert len(cols) == 7 and len(set(cols)) == 7, f"채널 색이 겹침: {cols}"
    stat = page.inner_text("#dbStat")
    assert re.search(r"가게 [\d,]+곳", stat), f"전체 가게 수 표시가 없음: {stat}"


def flow_new_channel_shops_found(page, shot):
    """새 채널 가게가 동네·메뉴 검색에 나오고, 카드에 채널 이름(글자)·가게 종류·영상 장면이 붙는다"""
    ready(page)
    area(page, "횡성")
    ns = all_names(page)
    assert "수지막국수" in ns, f"횡성 검색에 하이갱스 '수지막국수'가 없음: {ns[:10]}"
    card = page.locator("#results article.slip", has=page.locator("h3", has_text="수지막국수")).first
    t = card.inner_text()
    assert "하이갱스" in t, "카드에 채널 이름이 글자로 없음"
    assert "🍴" in t, "카드에 가게 종류(예: 국수)가 없음"
    href = card.locator("a", has_text="영상").get_attribute("href")
    assert "&t=" in href, f"하이갱스 타임라인 장면으로 가는 링크가 아님: {href}"
    # 채널 이름표는 글자색이 본문색(채널 색은 옆 점으로만) — 노란·연보라 채널 글자도 읽히게
    ink, tag = page.evaluate("""() => [getComputedStyle(document.body).color,
        getComputedStyle(document.querySelector('#results .tag.ch')).color]""")
    assert ink == tag, f"채널 이름표 글자가 본문색이 아님: {tag} / {ink}"
    to_results(page)
    shot("new-channel")
    menu(page, "고추장불고기")
    ns = all_names(page)
    assert any("정오네" in n for n in ns), f"메뉴 검색에 쏘울맛집 '정오네 고추장불고기'가 없음: {ns[:10]}"
    menu(page, "간짜장")
    ns = all_names(page)
    assert "우강반점" in ns, f"간짜장 검색에 맛삼인 '우강반점'(당진)이 없음: {ns[:12]}"


def flow_menu_uses_shop_kind(page, shot):
    """이름에 메뉴가 없는 가게도 가게 종류(카카오 분류)로 메뉴 검색에 걸린다"""
    ready(page)
    menu(page, "냉면")
    n_with = count(page)
    kinds = page.evaluate("""() => [...document.querySelectorAll('#results article.slip')].filter(a =>
        !/냉면/.test(a.querySelector('h3').firstChild.textContent) && /🍴[^\\n]*냉면/.test(a.innerText)).length""")
    assert kinds >= 1, "가게 이름에 '냉면'이 없는데 종류가 냉면인 가게가 하나도 없음"
    assert n_with >= 100, f"냉면 결과가 너무 적음({n_with})"


def flow_new_channel_toggle(page, shot):
    """하이갱스를 끄면 그 가게가 빠지고, 다시 켜면 돌아온다(새로고침 후에도 기억)"""
    ready(page)
    area(page, "횡성")
    assert "수지막국수" in all_names(page), "횡성 검색에 수지막국수가 없음"
    page.locator("#channels button", has_text="하이갱스").click()
    assert "수지막국수" not in all_names(page), "하이갱스를 꺼도 수지막국수가 남음"
    page.reload()
    ready(page)
    assert page.locator("#channels button", has_text="하이갱스").get_attribute("aria-pressed") == "false", "새로고침 후 하이갱스 끄기가 사라짐"
    page.locator("#channels button", has_text="하이갱스").click()
    area(page, "횡성")
    assert "수지막국수" in all_names(page), "하이갱스를 다시 켰는데 수지막국수가 안 돌아옴"


def flow_map_legend_fits_seven(page, shot):
    """지도 범례에 채널 7개가 들어가도 지도 폭을 넘지 않고, 지도 높이의 절반을 가리지 않는다"""
    ready(page)
    page.locator("#herePresets button", has_text="공덕역").click()
    page.click("#nearBtn")
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    r = page.evaluate("""() => { const w = document.querySelector('.mapwrap').getBoundingClientRect(), l = document.querySelector('.maplegend').getBoundingClientRect();
        return {mw: w.width, mh: w.height, lw: l.width, lh: l.height, ll: l.left - w.left, lr: w.right - l.right,
                n: document.querySelectorAll('.maplegend span:not([hidden])').length}; }""")
    assert r["n"] >= 7, f"범례에 채널이 다 안 나옴: {r}"
    assert r["ll"] >= 0 and r["lr"] >= 0, f"범례가 지도 밖으로 나감: {r}"
    assert r["lh"] <= r["mh"] * 0.35, f"범례가 지도를 너무 가림: {r}"
    shot("map-7ch", store=False)
