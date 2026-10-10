# 스토어 스크린샷 전용 장면 (appfactory.py qa ... --flows store_flows.py --store)
# 각 장면은 화면 맨 위가 잘리지 않게, 부드러운 스크롤이 끝난 뒤 위치를 다시 맞춰서 찍는다.


def ready(page):
    page.wait_for_function("document.getElementById('dbStat').textContent.length > 0", timeout=15000)


def settle_on(page, js_el, offset=10):
    page.wait_for_timeout(900)   # 앱의 부드러운 스크롤이 끝날 때까지
    page.evaluate("([o]) => { const s = " + js_el + "; window.scrollTo(0, s.getBoundingClientRect().top + window.scrollY - o); }", [offset])
    page.wait_for_timeout(300)


RESULTS = "document.getElementById('resultTitle').closest('section')"


def flow_1_home(page, shot):
    ready(page)
    page.fill("#q", "종로3가")
    page.evaluate("window.scrollTo(0, 0)")
    shot("home")


def flow_2_area(page, shot):
    ready(page)
    page.fill("#q", "을지로")
    page.click("#searchBtn")
    settle_on(page, RESULTS)
    shot("area")


def flow_3_menu(page, shot):
    ready(page)
    page.click("#modeMenu")
    page.fill("#q", "순대국")
    page.click("#searchBtn")
    settle_on(page, RESULTS)
    shot("menu")


def flow_4_near(page, shot):
    ready(page)
    page.context.grant_permissions(["geolocation"])
    page.context.set_geolocation({"latitude": 37.5656, "longitude": 127.0176})   # 신당역 근처
    page.click("#gpsBtn")
    page.wait_for_function("document.getElementById('hereName').textContent === '현재 위치'", timeout=8000)
    page.click("#nearBtn")
    settle_on(page, RESULTS)
    shot("near")


def flow_5_map(page, shot):
    ready(page)
    page.fill("#q", "을지로")
    page.click("#searchBtn")
    page.wait_for_timeout(900)
    page.click("#viewBtn")
    page.wait_for_selector(".mapwrap svg circle.pin", timeout=8000)
    page.wait_for_timeout(400)
    page.locator(".mapwrap svg circle.pin").nth(3).dispatch_event("click")
    page.wait_for_selector(".mapwrap + div article.slip", timeout=4000)
    settle_on(page, "document.querySelector('a.gmap')", offset=8)
    shot("map")
