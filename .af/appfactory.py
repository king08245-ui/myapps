#!/usr/bin/env python3
"""appfactory — 모바일 웹앱(PWA) 검수 + 스토어 에셋 도구.
  qa      APP_DIR [--flows F.py] [--slug S] [--store]   모바일 화면·접근성·PWA·오프라인·기능 검수
  icons   APP_DIR --glyph G --bg CSS [--fg C] [--svg F]  앱 아이콘 + Play 아이콘
  feature APP_DIR --name N --tagline T --glyph G --bg CSS [--fg C]   Play 그래픽 이미지 1024x500
  frames  APP_DIR --captions "a|b|c|d" [--bg CSS] [--fg C]  store/raw/*.png → 캡션 스토어 스크린샷
  qr      URL OUT.png
종료코드 1 = FAIL 있음. 결과: APP_DIR/qa/ (report.md, contact.png, 개별 스크린샷)
"""
import argparse, base64, functools, http.server, importlib.util, io, json, os, shutil, subprocess, sys, tempfile, threading
from pathlib import Path
from urllib.parse import urljoin, urlparse

AF_VERSION = "1.0"


def ensure_deps():
    for mod, pkg in (("playwright", "playwright"), ("PIL", "pillow"), ("segno", "segno")):
        try:
            __import__(mod)
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", pkg], check=True)


def chrome_path():
    for p in (os.environ.get("CHROME"), "/tmp/chromium"):
        if p and os.path.exists(p):
            return p
    d = Path.home() / ".cache" / "af-chromium"   # Playwright CDN이 막혀 있어 npm에 든 Chromium을 사용
    d.mkdir(parents=True, exist_ok=True)
    if not (d / "node_modules/@sparticuz/chromium").exists():
        subprocess.run(["npm", "i", "--silent", "--prefix", str(d), "@sparticuz/chromium"], check=True)
    js = 'import c from "@sparticuz/chromium"; console.log(await c.executablePath());'
    out = subprocess.run(["node", "--input-type=module", "-e", js], cwd=d, capture_output=True, text=True, check=True)
    return out.stdout.strip().splitlines()[-1]


ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"]
UA_AND = "Mozilla/5.0 (Linux; Android 15; SM-S931N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"
UA_IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
DEVICES = {
    "android-360": ({"width": 360, "height": 780}, 3, UA_AND),
    "iphone-390": ({"width": 390, "height": 844}, 3, UA_IOS),
    "small-320": ({"width": 320, "height": 640}, 2, UA_AND),
}
STORE_DEV = ({"width": 360, "height": 640}, 3, UA_AND)  # → 1080x1920 (9:16)


def ctx_kw(dev, scheme="light"):
    vp, dpr, ua = dev
    return dict(viewport=vp, device_scale_factor=dpr, user_agent=ua, is_mobile=True, has_touch=True,
                locale="ko-KR", timezone_id="Asia/Seoul", color_scheme=scheme)


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".webmanifest": "application/manifest+json", ".js": "text/javascript",
                      ".json": "application/json", ".svg": "image/svg+xml"}

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(app_dir, slug):
    root = Path(tempfile.mkdtemp(prefix="afroot-"))
    (root / "myapps").mkdir()
    os.symlink(Path(app_dir).resolve(), root / "myapps" / slug)  # GitHub Pages 하위경로(/myapps/<slug>/)와 같은 구조
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(root)))
    httpd.handle_error = lambda *a: None  # 브라우저가 끊은 연결 로그 숨김
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/myapps/{slug}/"


SCREENS = [f"{d}-{s}" for d in DEVICES for s in ("light", "dark")]


class Report:
    """같은 문제는 화면별로 반복하지 않고 한 줄로 묶음."""
    def __init__(self):
        self.rows = {}  # (level, msg) -> [areas]

    @property
    def items(self):
        return [(lv, areas, msg) for (lv, msg), areas in self.rows.items()]

    def add(self, level, area, msg):
        areas = self.rows.setdefault((level, msg), [])
        if area not in areas:
            areas.append(area)

    def count(self, level):
        return sum(1 for lv, _ in self.rows if lv == level)

    def has_fail(self, *areas):
        return any(lv == "FAIL" and (not areas or any(a.startswith(areas) for a in ar)) for lv, ar, _ in self.items)

    @staticmethod
    def label(areas):
        scr = [a for a in areas if a in SCREENS]
        rest = [a for a in areas if a not in SCREENS]
        if len(scr) == len(SCREENS):
            scr = ["모든 화면"]
        elif scr and all(a.endswith("-dark") for a in scr) and len(scr) == len(SCREENS) // 2:
            scr = ["다크모드 전체"]
        elif scr and all(a.endswith("-light") for a in scr) and len(scr) == len(SCREENS) // 2:
            scr = ["라이트모드 전체"]
        return ", ".join(scr + rest)

    def md(self):
        out = [f"# QA 결과: FAIL {self.count('FAIL')} · WARN {self.count('WARN')} · PASS {self.count('PASS')}", ""]
        for lv in ("FAIL", "WARN", "INFO", "PASS"):
            out += [f"- **{lv}** [{self.label(ar)}] {m}" for l, ar, m in self.items if l == lv]
        return "\n".join(out)


def watch(page, base, sink):
    host, bad = urlparse(base).netloc, set()

    def console(m):
        if m.type == "error" and not m.text.startswith("Failed to load resource"):  # HTTP 오류는 아래에서 경로와 함께 기록
            sink.append(f"콘솔 오류: {m.text[:200]}")

    def resp(r):
        u = urlparse(r.url)
        if u.netloc == host and r.status >= 400 and not u.path.endswith("/favicon.ico"):
            bad.add(u.path)
            sink.append(f"HTTP {r.status}: {u.path}")

    def failed(r):
        u = urlparse(r.url)
        if u.netloc == host and u.path not in bad and "ERR_ABORTED" not in (r.failure or ""):
            sink.append(f"요청 실패: {u.path} {r.failure or ''}")
    page.on("console", console)
    page.on("pageerror", lambda e: sink.append(f"JS 오류: {str(e)[:200]}"))
    page.on("dialog", lambda d: d.accept())
    page.on("response", resp)
    page.on("requestfailed", failed)


LAYOUT_JS = r"""() => {
 const vw = document.documentElement.clientWidth, out = {vw, sw: document.documentElement.scrollWidth, small: [], noname: [], smallInputs: [], wide: [], lowc: [], midc: [], noalt: 0, text: document.body.innerText.trim().length};
 const vis = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity !== 0; };
 const desc = el => { const t = (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || '').trim().replace(/\s+/g,' ').slice(0, 18);
   const c = typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/)[0] : ''; return el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + c + (t ? ` "${t}"` : ''); };
 const inScroller = el => { for (let n = el.parentElement; n && n !== document.body; n = n.parentElement) { const o = getComputedStyle(n).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') return true; } return false; };
 document.querySelectorAll('button, a[href], input:not([type=hidden]), select, textarea, [role=button], summary').forEach(el => {
   if (!vis(el)) return;
   let r = el.getBoundingClientRect();
   const lab = el.closest('label'); if ((el.type === 'checkbox' || el.type === 'radio') && lab) r = lab.getBoundingClientRect();
   const inlineLink = el.tagName === 'A' && getComputedStyle(el).display === 'inline';
   if (!inlineLink && Math.min(r.width, r.height) < 40) out.small.push(desc(el) + ` ${Math.round(r.width)}x${Math.round(r.height)}`);
   const name = (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || el.value || el.placeholder || '').trim();
   if (!name && !(el.labels && el.labels.length) && !el.getAttribute('aria-labelledby')) out.noname.push(desc(el));
   if (/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) && !/checkbox|radio|range|color/.test(el.type) && parseFloat(getComputedStyle(el).fontSize) < 16) out.smallInputs.push(desc(el) + ' ' + getComputedStyle(el).fontSize);
 });
 document.querySelectorAll('body *').forEach(el => { if (out.wide.length > 7) return; const r = el.getBoundingClientRect();
   if (r.right > vw + 1 && vis(el) && getComputedStyle(el).position !== 'fixed' && !inScroller(el)) out.wide.push(desc(el) + ` right=${Math.round(r.right)}`); });
 out.noalt = [...document.images].filter(i => !i.hasAttribute('alt')).length;
 const parse = c => { const m = /rgba?\(([^)]+)\)/.exec(c); if (!m) return null; const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
 const over = (t, b) => { const a = t.a + b.a * (1 - t.a); return a ? {r: (t.r*t.a + b.r*b.a*(1-t.a))/a, g: (t.g*t.a + b.g*b.a*(1-t.a))/a, b: (t.b*t.a + b.b*b.a*(1-t.a))/a, a} : t; };
 const lum = c => { const f = v => (v /= 255) <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); return 0.2126*f(c.r) + 0.7152*f(c.g) + 0.0722*f(c.b); };
 const dark = matchMedia('(prefers-color-scheme: dark)').matches;
 const bgOf = el => { const layers = []; for (let n = el; n; n = n.parentElement) { const s = getComputedStyle(n); if (s.backgroundImage !== 'none') return null; const c = parse(s.backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
   let b = dark ? {r:18,g:18,b:18,a:1} : {r:255,g:255,b:255,a:1}; for (let i = layers.length - 1; i >= 0; i--) b = over(layers[i], b); return b; };
 const seen = new Set(), tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
 while (tw.nextNode()) { const el = tw.currentNode.parentElement; if (!el || seen.has(el) || !tw.currentNode.textContent.trim()) continue; seen.add(el);
   if (!vis(el) || el.closest('[disabled],[aria-disabled=true],[hidden]')) continue;
   const s = getComputedStyle(el), bg = bgOf(el); if (!bg) continue; const fg = over(parse(s.color), bg);
   const L1 = lum(fg), L2 = lum(bg), ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05);
   const large = parseFloat(s.fontSize) >= 24 || (parseFloat(s.fontSize) >= 18.6 && +s.fontWeight >= 700);
   const d = desc(el) + ` ${ratio.toFixed(2)}:1`;
   if (ratio < 3) out.lowc.push(d); else if (!large && ratio < 4.5) out.midc.push(d); }
 return out; }"""


def layout_checks(page, rep, label):
    r = page.evaluate(LAYOUT_JS)
    if r["sw"] > r["vw"] + 1:
        rep.add("FAIL", label, f"가로 스크롤 발생 (문서 폭 {r['sw']}px > 화면 {r['vw']}px) 원인 후보: {'; '.join(r['wide'][:4])}")
    elif r["wide"]:
        rep.add("WARN", label, "화면 밖으로 나간 요소: " + "; ".join(r["wide"][:4]))
    if r["noname"]:
        rep.add("FAIL", label, "이름 없는 버튼/입력(스크린리더·사용성): " + "; ".join(r["noname"][:5]))
    if r["lowc"]:
        rep.add("FAIL", label, "글자 대비 3:1 미만(읽기 어려움): " + "; ".join(r["lowc"][:5]))
    if r["midc"]:
        rep.add("WARN", label, "글자 대비 4.5:1 미만: " + "; ".join(r["midc"][:4]))
    if r["small"]:
        rep.add("WARN", label, "터치 영역 40px 미만: " + "; ".join(r["small"][:5]))
    if r["smallInputs"]:
        rep.add("WARN", label, "입력칸 글자 16px 미만(아이폰 자동 확대): " + "; ".join(r["smallInputs"][:3]))
    if r["noalt"]:
        rep.add("WARN", label, f"alt 없는 이미지 {r['noalt']}개")
    if r["text"] == 0:
        rep.add("FAIL", label, "화면에 글자가 하나도 없음(렌더링 실패 의심)")


def contact_sheet(paths, out_png):
    from PIL import Image, ImageDraw, ImageFont
    if not paths:
        return
    try:
        font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 22)
    except OSError:
        font = ImageFont.load_default()
    thumbs = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        w = 300
        im = im.resize((w, int(im.height * w / im.width)))
        stem = Path(p).stem
        thumbs.append((stem if len(stem) <= 24 else stem[:23] + "…", im))
    cols = 6 if len(thumbs) >= 6 else len(thumbs)
    rows = (len(thumbs) + cols - 1) // cols
    th = max(t[1].height for t in thumbs)
    sheet = Image.new("RGB", (cols * 316 + 16, rows * (th + 48) + 16), (40, 40, 48))
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(thumbs):
        x, y = 16 + (i % cols) * 316, 16 + (i // cols) * (th + 48)
        d.text((x, y), name, fill=(230, 230, 240), font=font)
        sheet.paste(im, (x, y + 32))
    sheet.save(out_png)


def pwa_checks(pw, url, httpd, out, rep):
    from PIL import Image
    prof = tempfile.mkdtemp(prefix="afprof-")
    ctx = pw.chromium.launch_persistent_context(prof, executable_path=chrome_path(), args=ARGS, headless=True, **ctx_kw(DEVICES["android-360"]))
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    errs = []
    watch(page, url, errs)
    page.goto(url, wait_until="load")
    href = page.evaluate("document.querySelector('link[rel=manifest]')?.href || ''")
    if not href:
        rep.add("FAIL", "PWA", "manifest 링크 없음 (<link rel=manifest>)")
    else:
        res = page.request.get(href)
        try:
            m = json.loads(res.text())
        except Exception:
            m = None
            rep.add("FAIL", "PWA", f"manifest를 읽을 수 없음 (HTTP {res.status})")
        if m:
            if not (m.get("name") or m.get("short_name")):
                rep.add("FAIL", "PWA", "manifest에 name/short_name 없음")
            if len(m.get("short_name", "")) > 12:
                rep.add("WARN", "PWA", f"short_name이 깁니다({len(m['short_name'])}자) → 홈 화면에서 잘림")
            if m.get("display") not in ("standalone", "fullscreen", "minimal-ui"):
                rep.add("FAIL", "PWA", "display가 standalone/fullscreen/minimal-ui 가 아님")
            for k in ("start_url", "scope", "id", "theme_color", "background_color", "lang"):
                if k not in m:
                    rep.add("FAIL" if k == "start_url" else "WARN", "PWA", f"manifest에 {k} 없음")
            sizes, maskable = set(), False
            for ic in m.get("icons", []):
                u = urljoin(href, ic.get("src", ""))
                r = page.request.get(u)
                if r.status != 200:
                    rep.add("FAIL", "PWA", f"아이콘 파일 없음: {ic.get('src')}")
                    continue
                try:
                    w, h = Image.open(io.BytesIO(r.body())).size
                except Exception:
                    rep.add("FAIL", "PWA", f"아이콘 이미지 손상: {ic.get('src')}")
                    continue
                decl = ic.get("sizes", "")
                if decl and decl != f"{w}x{h}":
                    rep.add("FAIL", "PWA", f"아이콘 크기 불일치: {ic.get('src')} 선언 {decl} / 실제 {w}x{h}")
                sizes.add(f"{w}x{h}")
                maskable |= "maskable" in ic.get("purpose", "")
            for need in ("192x192", "512x512"):
                if need not in sizes:
                    rep.add("FAIL", "PWA", f"{need} 아이콘 없음")
            if not maskable:
                rep.add("WARN", "PWA", "maskable 아이콘 없음 (안드로이드 아이콘이 작게/흰 테두리로 보임)")
    ok = page.evaluate("""async () => { if (!('serviceWorker' in navigator)) return false;
        return await Promise.race([navigator.serviceWorker.ready.then(() => true), new Promise(r => setTimeout(() => r(false), 8000))]); }""")
    if not ok:
        rep.add("FAIL", "PWA", "서비스워커 등록 실패 (오프라인·설치 불가)")
    else:
        page.reload(wait_until="load")
        page.wait_for_timeout(800)
        if not page.evaluate("!!navigator.serviceWorker.controller"):
            rep.add("FAIL", "PWA", "서비스워커가 페이지를 제어하지 않음")
    try:
        cdp = ctx.new_cdp_session(page)
        ie = [e["errorId"] for e in cdp.send("Page.getInstallabilityErrors").get("installabilityErrors", [])]
        ie = [e for e in ie if e not in ("in-incognito",)]
        if ie:  # 헤드리스에선 오류를 놓치기도 하므로 '없음'을 통과 근거로 쓰지 않음
            rep.add("FAIL", "PWA", "Chrome 설치 불가 사유: " + ", ".join(ie))
    except Exception as e:
        rep.add("INFO", "PWA", f"설치 가능성 API 확인 불가: {e}")
    title = page.title()
    httpd.shutdown(); httpd.server_close()  # 서버를 실제로 꺼서 진짜 오프라인 상태로 다시 열기
    try:
        page.reload(wait_until="load", timeout=8000)
        alive = page.evaluate("document.body.innerText.trim().length") > 0 and page.title() == title
    except Exception:
        alive = False
    try:
        page.screenshot(path=str(out / "offline.png"), timeout=5000)
    except Exception:
        pass
    rep.add("PASS" if alive else "FAIL", "오프라인", "서버가 꺼진 상태에서도 열림" if alive else "오프라인에서 열리지 않음")
    for e in errs:
        if "ERR_CONNECTION_REFUSED" not in e and "요청 실패" not in e:
            rep.add("FAIL", "PWA", e)
    if not rep.has_fail("PWA", "오프라인"):
        rep.add("PASS", "PWA", "설치 조건 충족 (manifest·아이콘 크기·서비스워커 제어)")
    ctx.close()


def load_flows(path):
    spec = importlib.util.spec_from_file_location("flows", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fns = [f for n, f in vars(mod).items() if n.startswith("flow_") and callable(f)]
    return sorted(fns, key=lambda f: f.__code__.co_firstlineno)


def run_flows(browser, url, flows, out, rep, store_dir=None):
    from PIL import Image
    n = 0
    for fn in flows:
        ctx = browser.new_context(**ctx_kw(STORE_DEV if store_dir else DEVICES["iphone-390"]))
        page = ctx.new_page()
        errs = []
        watch(page, url, errs)
        page.goto(url, wait_until="load")
        page.wait_for_timeout(300)

        def shot(name, store=True):
            nonlocal n
            page.wait_for_timeout(250)
            if store_dir is not None:
                if store:
                    n += 1
                    p = store_dir / f"{n:02d}-{name}.png"
                    page.screenshot(path=str(p))
                    Image.open(p).convert("RGB").save(p)
            else:
                page.screenshot(path=str(out / f"flow-{fn.__name__[5:]}-{name}.png"))
        try:
            fn(page, shot)
            if not store_dir:
                rep.add("PASS", "기능", fn.__name__[5:])
        except Exception as e:
            page.screenshot(path=str(out / f"FAIL-{fn.__name__}.png"))
            rep.add("FAIL", "기능", f"{fn.__name__[5:]}: {type(e).__name__}: {str(e)[:300]}")
        if not store_dir:
            for e in errs:
                rep.add("FAIL", f"기능 {fn.__name__[5:]}", e)
        ctx.close()


def cmd_qa(a):
    from playwright.sync_api import sync_playwright
    app = Path(a.app_dir).resolve()
    slug = a.slug or app.name
    out = app / "qa"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir()
    rep = Report()
    if not (app / "index.html").exists():
        sys.exit("index.html 없음")
    httpd, url = serve(app, slug)
    shots = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome_path(), args=ARGS, headless=True)
        for dname, dev in DEVICES.items():
            for scheme in ("light", "dark"):
                label = f"{dname}-{scheme}"
                ctx = browser.new_context(**ctx_kw(dev, scheme))
                page = ctx.new_page()
                errs, ext = [], set()
                watch(page, url, errs)
                page.on("request", lambda r: urlparse(r.url).netloc not in (urlparse(url).netloc, "") and ext.add(urlparse(r.url).netloc))
                page.goto(url, wait_until="load")
                page.wait_for_timeout(600)
                p = out / f"{label}.png"
                page.screenshot(path=str(p))
                shots.append(p)
                if dname == "iphone-390" and scheme == "light":
                    page.screenshot(path=str(out / "full-page.png"), full_page=True)
                layout_checks(page, rep, label)
                for e in errs:
                    rep.add("FAIL", label, e)
                if ext:
                    rep.add("INFO", "외부 리소스", "오프라인에선 빠짐: " + ", ".join(sorted(ext)))
                ctx.close()
        if a.flows:
            flows = load_flows(a.flows)
            run_flows(browser, url, flows, out, rep)
            if a.store:
                sd = app / "store" / "raw"
                shutil.rmtree(sd, ignore_errors=True)
                sd.mkdir(parents=True)
                run_flows(browser, url, flows, out, rep, store_dir=sd)
                rep.add("INFO", "스토어", f"스토어용 원본 스크린샷 {len(list(sd.glob('*.png')))}장 → store/raw/ (1080x1920)")
        elif a.store:
            sd = app / "store" / "raw"
            sd.mkdir(parents=True, exist_ok=True)
            ctx = browser.new_context(**ctx_kw(STORE_DEV))
            page = ctx.new_page()
            page.goto(url, wait_until="load")
            page.wait_for_timeout(500)
            page.screenshot(path=str(sd / "01-home.png"))
            ctx.close()
        browser.close()
        pwa_checks(pw, url, httpd, out, rep)
    if not rep.has_fail("android", "iphone", "small"):
        rep.add("PASS", "화면", "3개 기기 × 라이트/다크: 가로 스크롤·대비·버튼 이름·JS 오류 이상 없음")
    extra = sorted(out.glob("flow-*.png"))[:12] + sorted(out.glob("FAIL-*.png")) + [p for p in [out / "offline.png"] if p.exists()]
    contact_sheet(shots + extra, out / "contact.png")
    (out / "report.md").write_text(rep.md(), encoding="utf-8")
    print(rep.md())
    print(f"\n스크린샷 모음: {out / 'contact.png'}")
    sys.exit(1 if rep.count("FAIL") else 0)


def render(html, w, h, path, rgb=False):
    from playwright.sync_api import sync_playwright
    from PIL import Image
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chrome_path(), args=ARGS, headless=True)
        pg = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        pg.set_content(html, wait_until="load")
        pg.wait_for_timeout(200)
        pg.screenshot(path=str(path))
        b.close()
    im = Image.open(path)
    (im.convert("RGB") if rgb else im.convert("RGBA")).save(path)


FONT = "'Noto Sans CJK KR','Apple SD Gothic Neo','Noto Color Emoji',sans-serif"  # style="..." 안에 들어가므로 작은따옴표


def glyph_html(a, px):
    if a.svg:
        data = base64.b64encode(Path(a.svg).read_bytes()).decode()
        return f'<img src="data:image/svg+xml;base64,{data}" style="width:{px}px;height:{px}px">'
    return f'<span style="font-size:{px}px;line-height:1;font-weight:800;color:{a.fg};font-family:{FONT}">{a.glyph}</span>'


def icon_html(a, size, ratio):
    return (f'<html><body style="margin:0;width:{size}px;height:{size}px;background:{a.bg};display:flex;'
            f'align-items:center;justify-content:center">{glyph_html(a, int(size * ratio))}</body></html>')


def cmd_icons(a):
    app = Path(a.app_dir)
    (app / "icons").mkdir(parents=True, exist_ok=True)
    (app / "store").mkdir(exist_ok=True)
    jobs = [("icons/icon-192.png", 192, .58), ("icons/icon-512.png", 512, .58), ("icons/maskable-512.png", 512, .46),
            ("icons/apple-touch-icon.png", 180, .58), ("store/play-icon-512.png", 512, .56)]
    for rel, s, r in jobs:
        render(icon_html(a, s, r), s, s, app / rel, rgb=rel.endswith("apple-touch-icon.png"))
        print("✓", rel)


def cmd_feature(a):
    app = Path(a.app_dir)
    (app / "store").mkdir(parents=True, exist_ok=True)
    tile = f'<div style="width:200px;height:200px;border-radius:44px;background:rgba(255,255,255,.18);display:flex;align-items:center;justify-content:center;flex:none">{glyph_html(a, 120)}</div>'
    html = (f'<html><body style="margin:0;width:1024px;height:500px;background:{a.bg};display:flex;align-items:center;gap:56px;'
            f'padding:0 96px;box-sizing:border-box;font-family:{FONT};color:{a.fg}">{tile}<div>'
            f'<div style="font-size:68px;font-weight:800;letter-spacing:-1px;line-height:1.15">{a.name}</div>'
            f'<div style="font-size:32px;opacity:.92;margin-top:18px;line-height:1.4">{a.tagline}</div></div></body></html>')
    render(html, 1024, 500, app / "store/feature-graphic-1024x500.png", rgb=True)
    print("✓ store/feature-graphic-1024x500.png")


def cmd_frames(a):
    app = Path(a.app_dir)
    raws = sorted((app / "store/raw").glob("*.png"))
    caps = [c.strip() for c in a.captions.split("|")]
    od = app / "store/screens"
    shutil.rmtree(od, ignore_errors=True)
    od.mkdir(parents=True)
    for i, p in enumerate(raws):
        cap = caps[i] if i < len(caps) else ""
        data = base64.b64encode(p.read_bytes()).decode()
        html = (f'<html><body style="margin:0;width:1080px;height:1920px;background:{a.bg};font-family:{FONT};color:{a.fg};'
                f'display:flex;flex-direction:column;align-items:center;overflow:hidden">'
                f'<div style="height:400px;display:flex;align-items:center;justify-content:center;padding:0 90px;text-align:center;'
                f'font-size:76px;font-weight:800;line-height:1.25;letter-spacing:-1.5px;word-break:keep-all">{cap}</div>'
                f'<img src="data:image/png;base64,{data}" style="width:820px;border-radius:56px;'
                f'box-shadow:0 30px 80px rgba(0,0,0,.35);border:14px solid #111"></body></html>')
        render(html, 1080, 1920, od / f"{i + 1:02d}.png", rgb=True)
        print("✓", od / f"{i + 1:02d}.png")


def cmd_qr(a):
    import segno
    segno.make(a.url, error="m").save(a.out, scale=12, border=3)
    print("✓", a.out)


def main():
    ensure_deps()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    q = sp.add_parser("qa"); q.add_argument("app_dir"); q.add_argument("--flows"); q.add_argument("--slug"); q.add_argument("--store", action="store_true")
    for name in ("icons", "feature"):
        s = sp.add_parser(name); s.add_argument("app_dir"); s.add_argument("--glyph", default="★"); s.add_argument("--svg")
        s.add_argument("--bg", default="#2f6fec"); s.add_argument("--fg", default="#ffffff")
        s.add_argument("--name", default=""); s.add_argument("--tagline", default="")
    f = sp.add_parser("frames"); f.add_argument("app_dir"); f.add_argument("--captions", default=""); f.add_argument("--bg", default="#2f6fec"); f.add_argument("--fg", default="#ffffff")
    r = sp.add_parser("qr"); r.add_argument("url"); r.add_argument("out")
    a = ap.parse_args()
    {"qa": cmd_qa, "icons": cmd_icons, "feature": cmd_feature, "frames": cmd_frames, "qr": cmd_qr}[a.cmd](a)


if __name__ == "__main__":
    main()
