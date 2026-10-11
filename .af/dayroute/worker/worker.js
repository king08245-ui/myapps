// 하루동선 서버 (Cloudflare Worker) — PC판 server.js의 일정 짜기·경로 근처 찾기를 그대로 옮긴 것
// 폰 화면(https://king08245-ui.github.io/myapps/dayroute/)이 이 주소의 /api/plan, /api/nearby, /api/status를 부른다.
//
// Cloudflare 대시보드 → Workers → 이 Worker → 설정 → 변수 및 비밀(Variables and Secrets)에 넣을 것
//   KAKAO_REST_KEY  (비밀) 카카오 REST API 키 — 장소 검색 + 자동차 길찾기
//   ODSAY_API_KEY   (비밀) ODsay 키 — 대중교통 길찾기
//   KAKAO_JS_KEY    (비밀) 카카오 JavaScript 키 — 폰 화면의 지도 표시용(카카오에 등록한 도메인에서만 동작)
//   ACCESS_CODE     (비밀) 접속 코드 — 아무 단어나. 폰 앱 설정에 같은 값을 넣어야 일정 짜기가 됨(남이 키 사용량을 못 쓰게)
//   ANTHROPIC_API_KEY (비밀, 선택) 있으면 문장 해석을 AI가 함. 없으면 키워드로 해석
//   ODSAY_REFERER   (선택) ODsay 웹 키에 등록한 주소. 기본값 http://localhost:3000 (PC판에서 등록한 그 주소)
//   ALLOWED_ORIGINS (선택) 이 서버를 부를 수 있는 화면 주소, 쉼표로 구분. 기본값은 아래 DEFAULT_ORIGINS
//   SUBREQ_MAX      (선택) 한 번에 바깥 API를 부르는 최대 횟수. 무료 요금제는 50번이 한도라 기본 48

const VERSION = "2026-10-11b";
const DEFAULT_ORIGINS = ["https://king08245-ui.github.io", /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/];

/* 무료 요금제는 요청 한 번에 바깥 API 호출이 50번까지라, 셈을 하고 남은 몫은 이동 계산에 남겨 둔다 */
class Budget {
  constructor(max) { this.max = max; this.used = 0; this.cache = new Map(); this.short = false; }
  left() { return this.max - this.used; }
}

/* ---------- 활동 종류 ---------- */
const CAT = {
  gym:        { ko: "헬스장",   q: "헬스장",   min: 60 },
  lunch:      { ko: "점심",     q: "맛집",     min: 60, code: "FD6" },
  cafe:       { ko: "카페",     q: "카페",     min: 50, code: "CE7" },
  exhibition: { ko: "전시",     q: "미술관 박물관", min: 90 },
  park:       { ko: "공원 산책", q: "공원",     min: 60 },
  cinema:     { ko: "영화",     q: "영화관",   min: 130 },
  sauna:      { ko: "사우나",   q: "사우나",   min: 90 },
  dinner:     { ko: "저녁",     q: "맛집",     min: 90, code: "FD6" },
};
const KW = [
  ["gym", /헬스|운동|짐|PT|웨이트|필라테스/], ["lunch", /점심|브런치/], ["cafe", /카페|커피/],
  ["exhibition", /전시|박물관|미술관|갤러리|기념관/], ["park", /공원|산책|한강|숲길/],
  ["cinema", /영화|극장|시네마/], ["sauna", /사우나|찜질|목욕/], ["dinner", /저녁|갈비|술|다이닝/],
];

const GENERIC = /^(헬스장?|헬스클럽|운동|짐|PT|웨이트|필라테스|전시(회|관)?|박물관|미술관|갤러리|기념관|공원|산책|공원산책|숲길|영화(관)?|극장|시네마|사우나|찜질(방)?|목욕(탕)?|브런치)$/;
// 종류만 적은 말 중 뜻이 넓은 말은 찾기 좋은 말로 바꾼다. 나머지(필라테스·브런치·기념관…)는 적은 말 그대로 찾는다
const VAGUE = { 헬스: "헬스장", 운동: "헬스장", 짐: "헬스장", 전시: "미술관 박물관", 전시회: "미술관 박물관", 산책: "공원", 공원산책: "공원", 영화: "영화관", 찜질: "찜질방", 목욕: "목욕탕" };

/* 키워드 해석: 목록에 없는 활동도 문구 그대로 검색어로 사용 (PC판과 같음, 종류만 적은 말은 근처에서 찾기) */
function ruleParse(text) {
  const parts = String(text || "").split(/[,，\n]|그리고|→/).map(s => s.trim()).filter(Boolean);
  const out = [];
  for (const raw of parts) {
    const sub = raw.split(/(?<=먹고|보고|가고|하고)\s+/).map(s => s.trim()).filter(Boolean);
    for (const part of sub) {
      let min = null;
      const h = part.match(/(\d+(?:\.\d+)?)\s*시간/), m = part.match(/(\d+)\s*분/);
      if (h || m) min = Math.round((h ? parseFloat(h[1]) * 60 : 0) + (m ? parseInt(m[1], 10) : 0));   // "1시간 30분" → 90분
      const needsParking = /주차/.test(part);
      const isReturn = /복귀|귀가|돌아(오|가)/.test(part);
      // 장소 이름이 적혀 있으면 그 이름으로 찾는다 ("광화문 교보문고", "A 근처 B")
      const clean = part.replace(/\d+(\.\d+)?\s*(시간|분)/g, "").replace(/주차(되는|가능한|가능|있는)?/g, "")
        .replace(/(책\s*)?사기|사러|구경하기|구경|먹기|먹고|먹으러|보기|보고|가고|하기|하고|가기|들르기|복귀|귀가|돌아오기|돌아가기|오후엔|오전엔|저녁엔|에서/g, " ")
        .replace(/\s+/g, " ").trim();
      let anchor = null, target = clean;
      const nm = clean.match(/^(.+?)\s*(근처|주변|앞|옆)\s+(.+)$/);
      if (nm) { anchor = nm[1].trim(); target = nm[3].trim(); }
      const near = !anchor && /근처|주변/.test(clean);
      let named = target.replace(/(\S)(점심|저녁|식사)(?=\s|$)/g, "$1").replace(/(^|\s)(점심|저녁|식사|밥|맛집|카페|커피|근처|주변)(?=\s|$)/g, " ").replace(/\s+/g, " ").trim();
      // "헬스장", "필라테스", "전시"처럼 종류만 적은 말은 가게 이름이 아니다 → 멀리서 이름으로 찾지 않고, 지금 있는 곳 근처에서
      // 그 말로 찾는다(뜻이 넓은 말만 VAGUE로 바꿈). '브런치'처럼 식사 종류를 적었으면 가격대 때문에 백반집으로 바꾸지 않는다
      const word = named.replace(/\s+/g, "");
      const kind = GENERIC.test(word) ? (VAGUE[word] || named) : "", kindLabel = kind && !VAGUE[word] ? named : "";
      if (kind) named = "";
      const catOf = c => (kindLabel && isMeal(c) ? "custom" : c);
      if (near && !isReturn) {
        // "근처 국밥집 점심" → 바로 앞 장소 가까이에서 찾기
        const hitN = KW.find(([, re]) => re.test(part));
        const cat = hitN ? catOf(hitN[0]) : "custom";
        const q = named.length >= 2 ? named : kind || (hitN ? CAT[hitN[0]].q : target.replace(/근처|주변/g, "").trim());
        out.push({ category: cat, label: clean, query: q || "맛집", nearPrev: true, minutes: min || (hitN ? CAT[hitN[0]].min : 60), needsParking });
        continue;
      }
      if (isReturn || named.length >= 2 || anchor) {
        const hitN = KW.find(([, re]) => re.test(part));
        const cat = hitN ? catOf(hitN[0]) : "custom";
        out.push({ category: cat, label: isReturn ? (named || clean) + " 복귀" : clean, query: (named.length >= 2 ? named : kind || target) || clean,
          anchor: anchor && !/^(근처|주변)$/.test(anchor) ? anchor : null, named: named.length >= 2, isReturn,
          minutes: isReturn ? 0 : (min || (hitN ? CAT[hitN[0]].min : 60)), needsParking });
        continue;
      }
      const hit = KW.find(([, re]) => re.test(part));
      if (hit) {
        out.push({ category: catOf(hit[0]), label: kindLabel || CAT[hit[0]].ko, query: kind || CAT[hit[0]].q, minutes: min || CAT[hit[0]].min, needsParking });
      } else {
        const q = part.replace(/\d+(\.\d+)?\s*(시간|분)/g, "").replace(/주차(되는|가능한|가능|있는)?/g, "")
          .replace(/(먹고|보고|가고|하고|오후엔|오전엔|저녁엔|에서|가기|하기)/g, "").trim();
        if (q.length >= 2) out.push({ category: "custom", label: q, query: q, minutes: min || 60, needsParking });
      }
    }
  }
  return out;
}

/* ---------- 식사 가격대 ----------
   카카오 API에는 가격 정보가 없어서, 카카오의 음식 분류(category_name)로 가격대를 추정한다. */
const CHEAP = /분식|김밥|국밥|해장국|국수|칼국수|백반|가정식|찌개|순대|도시락|설렁탕|곰탕|냉면|돈까스|돈가스|우동|라면|라멘|쌀국수|덮밥|햄버거|패스트푸드|중국요리|중식|짜장|제육|죽|떡볶이|수제비|감자탕|순두부|비빔밥|쌈밥|샌드위치|토스트|주먹밥|닭갈비|카레/;
const PRICEY = /한정식|오마카세|파인다이닝|스테이크|한우|코스요리|뷔페|호텔|참치회|장어|랍스터|대게|킹크랩|일식집|프렌치|와인|룸살롱|복어|회,/;
const CHEAP_QUERIES = ["백반", "국밥", "분식", "칼국수", "돈까스"];
const isMeal = c => c === "lunch" || c === "dinner";

/* 검색어가 종류 이름이면(서점·카페·공원) 카카오가 그 종류로 분류한 곳을 앞으로 — 카카오 키워드 검색은 이름에 그 말이
   들어간 곳도 섞어 주므로('서점' → 교보문고 안 안경점·문구점·물류센터) 순서만 바꾼다(빼지는 않음) */
function kindFirst(list, query) {
  const q = String(query || "").replace(/\s+/g, "");
  if (q.length < 2) return list;
  const hit = c => String(c.category || "").replace(/\s+/g, "").split(">").some(s => s.includes(q));
  const a = list.filter(hit);
  return a.length && a.length < list.length ? a.concat(list.filter(c => !hit(c))) : list;
}

/* ---------- 이동 ---------- */
function km(a, b) {
  const R = 6371, r = Math.PI / 180, dl = (b.y - a.y) * r, dn = (b.x - a.x) * r;
  const s = Math.sin(dl / 2) ** 2 + Math.cos(a.y * r) * Math.cos(b.y * r) * Math.sin(dn / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}
const LL = p => [Number(p.y), Number(p.x)]; // [위도, 경도]
function walkLeg(a, b) {
  const d = km(a, b);
  return { mode: "walk", min: Math.max(3, Math.round(d * 1.3 / 4.5 * 60)), km: d, segs: [{ kind: "walk", path: [LL(a), LL(b)] }] };
}
function thin(path, max = 250) { // 지도에 그릴 점 개수 줄이기
  if (path.length <= max) return path;
  const step = Math.ceil(path.length / max);
  return path.filter((_, i) => i % step === 0 || i === path.length - 1);
}
function parsePath(p, a, b) {
  const steps = [], segs = [];
  let cur = LL(a);
  for (const sp of p.subPath || []) {
    if (sp.trafficType === 3) { if (sp.sectionTime) steps.push({ type: "walk", min: sp.sectionTime }); continue; }
    const lanes = sp.lane || [], lane = lanes[0] || {};
    const isBus = sp.trafficType === 2;
    const st = {
      type: sp.trafficType === 1 ? "subway" : sp.trafficType === 4 ? "train" : "bus",
      name: sp.trafficType === 1 ? lane.name : sp.trafficType === 4 ? (lane.name || "열차") : sp.trafficType >= 5 ? (lane.name || { 5: "고속버스", 6: "시외버스", 7: "항공" }[sp.trafficType]) : (lane.busNo ? lane.busNo + "번" : "버스"),
      // 같은 정류장 사이를 다니는 다른 버스들
      also: isBus ? lanes.slice(1).map(l => l.busNo).filter(Boolean).slice(0, 6) : [],
      subwayCode: lane.subwayCode, busType: lane.type,
      from: sp.startName, to: sp.endName, stops: sp.stationCount, min: sp.sectionTime,
    };
    steps.push(st);
    const stations = ((sp.passStopList || {}).stations || []).map(x => [Number(x.y), Number(x.x)]);
    const line = stations.length ? stations : [[Number(sp.startY), Number(sp.startX)], [Number(sp.endY), Number(sp.endX)]].filter(q => q.every(Number.isFinite));
    if (line.length) {
      segs.push({ kind: "walk", path: [cur, line[0]] });
      segs.push({ kind: st.type, subwayCode: st.subwayCode, busType: st.busType, path: line });
      cur = line[line.length - 1];
    }
  }
  segs.push({ kind: "walk", path: [cur, LL(b)] });
  return { mode: "transit", min: p.info.totalTime, km: (p.info.totalDistance || 0) / 1000, fare: p.info.payment, steps, segs };
}

/* ---------- 키·호출 예산을 쓰는 부분: 요청마다 새로 만든다(동시에 온 요청끼리 섞이지 않게) ---------- */
function api(env) {
  const KAKAO = env.KAKAO_REST_KEY || "", ODSAY = env.ODSAY_API_KEY || "", ANTHROPIC = env.ANTHROPIC_API_KEY || "";
  const ODSAY_REFERER = env.ODSAY_REFERER || "http://localhost:3000";
  const KAKAO_BASE = env.KAKAO_BASE || "https://dapi.kakao.com", NAVI_BASE = env.NAVI_BASE || "https://apis-navi.kakaomobility.com";
  const ODSAY_BASE = env.ODSAY_BASE || "https://api.odsay.com", ANTHROPIC_BASE = env.ANTHROPIC_BASE || "https://api.anthropic.com";
  const B = new Budget(Number(env.SUBREQ_MAX) || 48);

  /* 선택: Claude API로 요청 해석 (ANTHROPIC_API_KEY가 있을 때만) */
  async function aiParse(text) {
    const prompt = `한국어 하루 일정 요청을 활동 목록으로 바꿔줘.
각 활동: {"category": gym|lunch|cafe|exhibition|park|cinema|sauna|dinner|custom, "label": 짧은 한국어 이름, "query": 카카오맵에서 검색할 검색어, "minutes": 머무는 분, "needsParking": 주차 조건이면 true}
시간이 없으면 기본값: gym 60, lunch 60, cafe 50, exhibition 90, park 60, cinema 130, sauna 90, dinner 90, custom 60.
요청 순서대로. JSON 배열만 답해.

요청: ${String(text).slice(0, 500)}`;
    B.used++;
    const r = await fetch(ANTHROPIC_BASE + "/v1/messages", {
      method: "POST",
      headers: { "x-api-key": ANTHROPIC, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({ model: "claude-haiku-4-5-20251001", max_tokens: 600, messages: [{ role: "user", content: prompt }] }),
    });
    if (!r.ok) throw new Error("Claude API " + r.status);
    const j = await r.json();
    const t = (j.content || []).map(c => c.text || "").join("");
    const arr = JSON.parse(t.slice(t.indexOf("["), t.lastIndexOf("]") + 1));
    return arr.filter(a => a && a.query).map(a => ({
      category: CAT[a.category] ? a.category : "custom",
      label: String(a.label || a.query), query: String(a.query),
      minutes: Math.min(300, Math.max(10, Number(a.minutes) || 60)), needsParking: !!a.needsParking,
    }));
  }

  /* ---------- 카카오 장소 검색 ----------
     reserve: 뒤에 남은 이동 계산 몫. 그만큼은 남기고, 모자라면 검색을 건너뛴다(빈 결과 → '찾지 못함' 카드 → 폰에서 다시 고르기) */
  async function kakaoSearch(query, near, opts = {}, reserve = 0) {
    const u = new URL(KAKAO_BASE + "/v2/local/search/keyword.json");
    u.searchParams.set("query", query);
    u.searchParams.set("size", String(opts.size || 5));
    if (near) {
      u.searchParams.set("x", near.x); u.searchParams.set("y", near.y);
      u.searchParams.set("radius", String(opts.radius || 3000)); u.searchParams.set("sort", opts.sort || "distance");
    }
    if (opts.code) u.searchParams.set("category_group_code", opts.code);
    const key = u.toString();
    if (B.cache.has(key)) return B.cache.get(key);
    if (B.left() <= reserve) { B.short = true; return []; }
    B.used++;
    const r = await fetch(u, { headers: { Authorization: "KakaoAK " + KAKAO } });
    if (!r.ok) throw new Error(`카카오 장소 검색 실패 (${r.status}) — Cloudflare 설정의 KAKAO_REST_KEY를 확인하세요`);
    const j = await r.json();
    const out = (j.documents || []).map(d => ({
      name: d.place_name, x: d.x, y: d.y, address: d.road_address_name || d.address_name,
      category: d.category_name, phone: d.phone, url: d.place_url, dist: Number(d.distance || 0),
    }));
    B.cache.set(key, out);
    return out;
  }

  async function mealCandidates(a, here, budget, reserve) {
    if (budget === "any") return null; // 가격 상관없음 → 기본 검색 사용
    const code = "FD6";
    const seen = new Map();
    const add = list => list.forEach(p => { if (!seen.has(p.name)) seen.set(p.name, p); });
    add(await kakaoSearch(a.query, here, { code, radius: 500, size: 15 }, reserve));
    if (![...seen.values()].some(p => !PRICEY.test(p.category || ""))) add(await kakaoSearch(a.query, here, { code, radius: 1000, size: 15 }, reserve));
    if (![...seen.values()].some(p => !PRICEY.test(p.category || ""))) add(await kakaoSearch(a.query, here, { code, radius: 3000, size: 15 }, reserve));
    let pool = [...seen.values()].filter(p => !PRICEY.test(p.category || ""));
    if (budget === "cheap") {
      let ok = pool.filter(p => CHEAP.test(p.category || "") || CHEAP.test(p.name));
      for (const q of CHEAP_QUERIES) {
        if (ok.length >= 3) break;
        add(await kakaoSearch(q, here, { code, radius: 1500, size: 15 }, reserve));
        pool = [...seen.values()].filter(p => !PRICEY.test(p.category || ""));
        ok = pool.filter(p => CHEAP.test(p.category || "") || CHEAP.test(p.name));
      }
      pool = ok.length ? ok : pool;
    }
    if (!pool.length) {
      for (const q of CHEAP_QUERIES.slice(0, 2)) add(await kakaoSearch(q, here, { code, radius: 3000, size: 15 }, reserve));
      pool = [...seen.values()].filter(p => !PRICEY.test(p.category || ""));
    }
    return pool.sort((x, y) => x.dist - y.dist);
  }

  async function carLeg(a, b) {
    const u = new URL(NAVI_BASE + "/v1/directions");
    u.searchParams.set("origin", `${a.x},${a.y}`);
    u.searchParams.set("destination", `${b.x},${b.y}`);
    u.searchParams.set("priority", "TIME");
    B.used++;
    const r = await fetch(u, { headers: { Authorization: "KakaoAK " + KAKAO } });
    if (!r.ok) throw new Error(`자동차 길찾기 실패 (${r.status}) — 카카오모빌리티 길찾기 API가 앱에 연결됐는지 확인하세요`);
    const j = await r.json();
    const route = (j.routes || [])[0];
    if (!route || route.result_code !== 0 || !route.summary) return walkLeg(a, b); // 너무 가까우면 경로 없음 → 도보
    const s = route.summary;
    const roadsAll = (route.sections || []).flatMap(sec => sec.roads || []);
    const mainRoads = [...new Set(roadsAll.map(rd => rd.name).filter(Boolean))].slice(0, 3);
    const path = [LL(a)];
    for (const rd of roadsAll) { const v = rd.vertexes || []; for (let i = 0; i + 1 < v.length; i += 2) path.push([v[i + 1], v[i]]); }
    path.push(LL(b));
    return { mode: "car", min: Math.round(s.duration / 60) + 5, km: s.distance / 1000, taxi: s.fare && s.fare.taxi, toll: s.fare && s.fare.toll, via: mainRoads, segs: [{ kind: "car", path: thin(path) }] };
  }
  async function transitLeg(a, b, opt = {}) {
    if (km(a, b) < 0.75) return walkLeg(a, b); // ODsay는 700m 이내 경로를 주지 않음
    const u = new URL(ODSAY_BASE + "/v1/api/searchPubTransPathT");
    u.searchParams.set("SX", a.x); u.searchParams.set("SY", a.y);
    u.searchParams.set("EX", b.x); u.searchParams.set("EY", b.y);
    u.searchParams.set("apiKey", ODSAY);
    if (opt.type) u.searchParams.set("SearchPathType", String(opt.type)); // 1 지하철, 2 버스
    // 웹(URI) 키는 등록한 주소를 Referer로 보내야 인증됨
    B.used++;
    const r = await fetch(u, { headers: { Referer: ODSAY_REFERER } });
    const j = await r.json().catch(() => ({}));
    if (j.error) {
      const msg = Array.isArray(j.error) ? j.error[0]?.message : j.error.msg || j.error.message;
      if (/700m/.test(String(msg))) return walkLeg(a, b);
      throw new Error("대중교통 길찾기 실패 — " + (msg || "Cloudflare 설정의 ODSAY_API_KEY를 확인하세요"));
    }
    const paths = ((j.result && j.result.path) || []).slice(0, 6);
    if (!paths.length) return walkLeg(a, b);
    // 고른 경로 번호가 있으면 그것, 기차를 고르면 열차 구간이 있는 경로, 아니면 가장 좋은 경로
    let k = Number.isInteger(opt.pick) && paths[opt.pick] ? opt.pick : 0;
    if (!Number.isInteger(opt.pick) && opt.train) { const t = paths.findIndex(x => (x.subPath || []).some(sp => sp.trafficType === 4)); if (t >= 0) k = t; }
    const all = paths.map(x => parsePath(x, a, b));
    const leg = all[k];
    // 다른 경로들 (지도에 회색선으로 보여주고 고를 수 있게)
    leg.options = all.map((o, i) => ({ i, min: o.min, fare: o.fare, names: o.steps.filter(s => s.type !== "walk").map(s => s.name + (s.also && s.also.length ? "·" + s.also.join("·") : "")), segs: o.segs.filter(sg => sg.kind !== "walk") }));
    leg.pick = k;
    return leg;
  }

  /* ---------- 일정 짜기 ----------
     picks: { 활동번호: 장소 } — 사용자가 지도에서 직접 고른 장소는 검색 대신 그대로 사용 */
  async function makePlan({ text, origin, originLL, originPlace, start, mode, budget = "cheap", acts: givenActs, picks = {}, legModes = {}, legPaths = {}, reuse = [] }) {
    if (!KAKAO) throw new Error("서버에 KAKAO_REST_KEY가 없어요 (Cloudflare 설정 → 변수 및 비밀)");
    if (mode === "transit" && !ODSAY) throw new Error("서버에 ODSAY_API_KEY가 없어요 (대중교통은 ODsay 키가 필요해요)");
    picks = picks || {}; legModes = legModes || {}; legPaths = legPaths || {};

    // 폰이 보낸 활동 목록(고친 코스)은 모양을 다시 맞춘다 — 머무는 시간이 글자로 와도 시각 계산이 깨지지 않게
    let acts = Array.isArray(givenActs) && givenActs.length ? givenActs.filter(a => a && a.query).map(a => ({
      category: CAT[a.category] ? a.category : "custom", label: String(a.label || a.query).slice(0, 60), query: String(a.query).slice(0, 80),
      minutes: Math.min(720, Math.max(0, Math.round(Number(a.minutes) || 0))), named: !!a.named, isReturn: !!a.isReturn, nearPrev: !!a.nearPrev,
      anchor: a.anchor ? String(a.anchor).slice(0, 60) : null, needsParking: !!a.needsParking,
    })) : null, source = "kept";
    if (!acts && ANTHROPIC) { try { acts = await aiParse(text); source = "ai"; } catch (e) { console.warn("AI 해석 실패:", e.message); } }
    if (!acts || !acts.length) { acts = ruleParse(text); source = "rule"; }
    if (!acts.length) throw new Error("요청에서 활동을 찾지 못했어요. 예: 헬스장 1시간, 점심, 카페");
    if (acts.length > 12) throw new Error("한 번에 12곳까지 짤 수 있어요. 일정을 나눠 주세요.");

    // 고칠 때는 앞서 계산한 구간과 출발지를 다시 쓴다(바뀐 곳 앞뒤만 새로 계산) — 요청당 바깥 호출 50번·CPU 10ms 한도와
    // ODsay 무료 하루 횟수를 아낀다. 구간 열쇠 = 이동수단 + 고른 경로 + 두 곳 좌표
    const prevLegs = new Map();
    for (const L of Array.isArray(reuse) ? reuse.slice(0, 13) : []) {
      if (L && typeof L.key === "string" && L.key.length < 200 && typeof L.mode === "string" && Number.isFinite(L.min) && L.min >= 0 && L.min < 1440 && Array.isArray(L.segs)) prevLegs.set(L.key, L);
    }
    const inKorea = q => q && Number.isFinite(+q.x) && Number.isFinite(+q.y) && Math.abs(+q.y - 36) < 6 && Math.abs(+q.x - 128) < 6;
    // 폰의 '현재 위치'로 출발하면 좌표를 그대로 쓴다
    const ll = inKorea(originLL) ? originLL : null;
    const prevO = !ll && originPlace && originPlace.q === origin && inKorea(originPlace) ? originPlace : null;
    const o = ll ? { name: String(origin || "현재 위치").slice(0, 40), x: String(+ll.x), y: String(+ll.y), address: "", category: "", url: "" }
      : prevO ? { name: String(prevO.name || origin).slice(0, 60), x: String(+prevO.x), y: String(+prevO.y), address: String(prevO.address || "").slice(0, 120), category: String(prevO.category || "").slice(0, 120), url: String(prevO.url || "").slice(0, 200) }
      : (await kakaoSearch(origin, null, { size: 1 }))[0];
    if (!o) throw new Error(`출발지 '${origin}'을(를) 찾지 못했어요`);
    const [h, m] = String(start || "10:00").split(":").map(Number);
    let t = h * 60 + m;
    let here = { ...o };
    const items = [{ type: "start", t, place: here }];
    const used = new Set(Object.values(picks).map(p => p && p.name));
    let moving = 0;

    for (let i = 0; i < acts.length; i++) {
      const a = acts[i];
      const reserve = acts.length - i;   // 이번 구간 포함, 남은 이동 계산 몫
      let p = picks[i] && picks[i].x ? picks[i] : null, alts = [];
      if (!p && (a.named || a.isReturn || a.anchor)) {
        let base = null;
        if (a.anchor) base = (await kakaoSearch(a.anchor, null, { size: 1 }, reserve))[0] || here;
        const mealLike = isMeal(a.category) || /국밥|식당|냉면|국수|밥|면|집$/.test(a.query);
        const words = String(a.query).split(/\s+/).filter(Boolean);
        const tries = [a.query, ...(words.length > 1 ? [words.slice(1).join(" "), words.slice(0, -1).join(" "), ...[...words].sort((x, y) => y.length - x.length)] : [])];
        let found = [];
        for (const qq of [...new Set(tries)]) {
          if (qq.length < 2) continue;
          const ok = c => /주차/.test(a.query) || !/주차장/.test(c.category || "");
          if (base) {
            for (const rad of mealLike ? [500, 1000, 2000] : [1000, 2000]) {
              found = (await kakaoSearch(qq, base, { radius: rad, size: 5 }, reserve)).filter(ok);
              if (found.length) break;
            }
          } else {
            // 지금 있는 곳 20km 안에서 먼저, 없으면 전국
            found = (await kakaoSearch(qq, here, { radius: 20000, size: 5, sort: "accuracy" }, reserve)).filter(ok);
            if (!found.length) found = (await kakaoSearch(qq, null, { size: 5 }, reserve)).filter(ok);
          }
          if (found.length) break;
        }
        found = found.filter(c => !used.has(c.name) || a.isReturn);
        if (found.length) { p = found[0]; alts = found.slice(1, 3).map(c => c.name); }
        else if (a.named || a.isReturn) { items.push({ type: "miss", t, label: a.label, act: i }); continue; }
      }
      if (!p && a.nearPrev) {
        const meal = isMeal(a.category) || /국밥|식당|냉면|국수|밥|면|집$/.test(a.query);
        let found = [];
        for (const rad of meal ? [500, 1000, 2000] : [700, 1500, 3000]) {
          found = (await kakaoSearch(a.query, here, { radius: rad, size: 15, code: meal ? "FD6" : CAT[a.category]?.code }, reserve))
            .filter(c => !used.has(c.name) && !/주차장/.test(c.category || ""));
          if (meal && budget !== "any") found = found.filter(c => !PRICEY.test(c.category || ""));
          if (found.length) break;
        }
        if (!found.length) { items.push({ type: "miss", t, label: a.label, act: i }); continue; }
        found = kindFirst(found, a.query);
        p = found[0]; alts = found.slice(1, 3).map(c => c.name);
      }
      if (!p) {
        let cands = isMeal(a.category) ? await mealCandidates(a, here, budget, reserve) : null;
        if (!cands || !cands.length) cands = await kakaoSearch(a.query, here, { code: CAT[a.category]?.code, radius: 3000 }, reserve);
        if (!cands.length) cands = await kakaoSearch(a.query, here, { code: CAT[a.category]?.code, radius: 8000 }, reserve);
        cands = cands.filter(c => !used.has(c.name) && (/주차/.test(a.query) || !/주차장/.test(c.category || "")));   // '주차되는 헬스장'은 주차장이 아니라 헬스장
        cands = kindFirst(cands, a.query);
        if (!cands.length) { items.push({ type: "miss", t, label: a.label, act: i }); continue; }
        p = cands[0]; alts = cands.slice(1, 3).map(c => c.name);
      }
      used.add(p.name);
      // 구간별로 고른 이동수단이 있으면 그것으로, 없으면 기본 수단 (500m 안은 걸어서)
      const lm = legModes[i];
      if (lm && lm !== "car" && lm !== "walk" && !ODSAY) throw new Error("서버에 ODSAY_API_KEY가 없어서 버스·지하철·기차 구간을 계산할 수 없어요");
      const key = `${lm || "auto-" + mode}|${legPaths[i] ?? ""}|${(+here.x).toFixed(5)},${(+here.y).toFixed(5)}>${(+p.x).toFixed(5)},${(+p.y).toFixed(5)}`;
      const leg = prevLegs.get(key) || (lm === "walk" ? walkLeg(here, p)
        : lm === "car" ? await carLeg(here, p)
        : lm === "bus" ? await transitLeg(here, p, { type: 2, pick: legPaths[i] })
        : lm === "subway" ? await transitLeg(here, p, { type: 1, pick: legPaths[i] })
        : lm === "train" ? await transitLeg(here, p, { train: true, pick: legPaths[i] })
        : km(here, p) < 0.5 ? walkLeg(here, p) : mode === "car" ? await carLeg(here, p) : await transitLeg(here, p, { pick: legPaths[i] }));
      leg.key = key;
      leg.chosen = lm || "";
      items.push({ type: "leg", t, leg, act: i });
      t += leg.min; moving += leg.min;
      items.push({ type: "stop", t, place: p, label: a.label, act: i, meal: isMeal(a.category), picked: !!(picks[i] && !picks[i].keep), ret: !!a.isReturn, stay: a.minutes, needsParking: a.needsParking || mode === "car", alts });
      t += a.minutes;
      here = p;
    }
    items.push({ type: "end", t, place: here });
    return { source, acts, items, moving, start: h * 60 + m, end: t, mode, budget, picks, legModes, legPaths, short: B.short, originQuery: ll ? null : origin };
  }

  /* ---------- 경로 근처 장소 찾기 ----------
     앞 장소(prev)와 다음 장소(next) 사이에서, 들렀다 가도 덜 돌아가는 순서로 정렬 */
  async function nearby({ query, budget = "cheap", prev, next, meal }) {
    if (!KAKAO) throw new Error("서버에 KAKAO_REST_KEY가 없어요 (Cloudflare 설정 → 변수 및 비밀)");
    if (!query || !prev) throw new Error("검색어와 기준 위치가 필요해요");
    const pts = [prev];
    if (next) pts.push({ x: (Number(prev.x) + Number(next.x)) / 2, y: (Number(prev.y) + Number(next.y)) / 2 }, next);
    const seen = new Map();
    for (const pt of pts) {
      const list = await kakaoSearch(query, pt, { code: meal ? "FD6" : undefined, radius: 1200, size: 15 });
      list.forEach(p => { if (!seen.has(p.name + p.x)) seen.set(p.name + p.x, p); });
    }
    let out = [...seen.values()].filter(p => /주차/.test(query) || !/주차장/.test(p.category || ""));
    if (meal && budget !== "any") {
      out = out.filter(p => !PRICEY.test(p.category || ""));
      if (budget === "cheap") {
        const ok = out.filter(p => CHEAP.test(p.category || "") || CHEAP.test(p.name));
        out = ok.map(p => ({ ...p, cheap: true })).concat(out.filter(p => !ok.includes(p)).map(p => ({ ...p, cheap: false })));
      }
    }
    const base = next ? km(prev, next) : 0;
    out.forEach(p => { p.detourKm = next ? km(prev, p) + km(p, next) - base : km(prev, p); });
    out.sort((x, y) => (budget === "cheap" && meal ? (y.cheap - x.cheap) : 0) || x.detourKm - y.detourKm);
    if (!meal) out = kindFirst(out, query);
    return { results: out.slice(0, 15) };
  }

  return { makePlan, nearby };
}

/* ---------- 서버 ---------- */
function allowedOrigin(origin, env) {
  if (!origin) return null;
  const list = env.ALLOWED_ORIGINS ? String(env.ALLOWED_ORIGINS).split(",").map(s => s.trim()).filter(Boolean) : DEFAULT_ORIGINS;
  return list.some(o => o === "*" || (o instanceof RegExp ? o.test(origin) : o.replace(/\/$/, "") === origin)) ? origin : null;
}
function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json; charset=utf-8", ...cors } });
}
function sameCode(a, b) {   // 접속 코드 비교 (글자 수가 달라도 시간 차이가 덜 나게)
  a = String(a || ""); b = String(b || "");
  let d = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) d |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return d === 0;
}

export default {
  async fetch(request, env = {}) {
    const url = new URL(request.url);
    const origin = allowedOrigin(request.headers.get("origin"), env);
    const cors = origin ? { "access-control-allow-origin": origin, "vary": "origin" } : {};
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: { ...cors, "access-control-allow-methods": "GET, POST, OPTIONS",
        "access-control-allow-headers": "content-type, x-access-code", "access-control-max-age": "86400" } });
    }
    const needCode = !!env.ACCESS_CODE;
    let given = request.headers.get("x-access-code") || "";
    try { given = decodeURIComponent(given); } catch {}   // 폰 앱은 한글 코드도 되게 인코딩해서 보냄
    const codeOk = !needCode || sameCode(given, env.ACCESS_CODE);
    // 틀린 코드에는 1초 늦게 답한다 — 코드를 마구 넣어 보며 맞히기 어렵게 (기다리는 시간은 CPU 한도에 들어가지 않음)
    const slow = () => new Promise(r => setTimeout(r, 1000));

    if (url.pathname === "/api/status") {
      if (!codeOk) await slow();
      // 지도 키(JavaScript 키)는 화면에서 쓰는 값이라 보내도 됨 — 카카오에 등록한 도메인에서만 동작
      return json({ ok: true, version: VERSION, kakao: !!env.KAKAO_REST_KEY, odsay: !!env.ODSAY_API_KEY, ai: !!env.ANTHROPIC_API_KEY,
        jsKey: env.KAKAO_JS_KEY || "", needCode, codeOk, weakCode: needCode && codeOk && String(env.ACCESS_CODE).length < 6 }, 200, cors);
    }
    if (url.pathname === "/api/plan" || url.pathname === "/api/nearby") {
      if (request.method !== "POST") return json({ error: "POST로 불러 주세요" }, 405, cors);
      if (!codeOk) { await slow(); return json({ error: "접속 코드가 맞지 않아요. 앱 설정의 접속 코드를 확인하세요." }, 401, cors); }
      let input;
      try { input = JSON.parse(await request.text() || "{}"); } catch { return json({ error: "요청 형식이 잘못됐어요" }, 400, cors); }
      try {
        const A = api(env);
        const out = url.pathname === "/api/plan" ? await A.makePlan(input) : await A.nearby(input);
        return json(out, 200, cors);
      } catch (e) {
        return json({ error: e.message || String(e) }, 400, cors);
      }
    }
    if (url.pathname === "/" || url.pathname === "") {
      return new Response("하루동선 서버가 동작 중이에요. 폰 앱 설정에 이 주소를 넣으세요: " + url.origin + "\n",
        { headers: { "content-type": "text/plain; charset=utf-8", ...cors } });
    }
    return json({ error: "없는 주소예요" }, 404, cors);
  },
};
