// 역산 15분 플래너 동기화 서버 (Cloudflare Worker + KV)
//   폰 앱  https://king08245-ui.github.io/myapps/backplan/  ⇄  이 서버  ⇄  목표까지 아티팩트(claude.ai 연결 '역산플래너' → /mcp)
//
// Cloudflare 대시보드에서 할 것
//   1) 저장소 → KV → 이름공간 하나 만들기(예: backplan)
//   2) 이 Worker → 설정 → 바인딩 → KV 이름공간 추가: 변수 이름 BP, 위 이름공간
//   3) 설정 → 변수 및 비밀 → ACCESS_CODE (비밀) — 폰 앱과 목표까지에 같은 값을 넣는다
//   선택: ALLOWED_ORIGINS (쉼표로 구분, 폰 화면 주소)
//
// 저장 내용 (KV)
//   data : { rev, at, device, data: {goals, del, imin}, progress }  ← 폰이 올림
//   mk   : { at, recvAt, from, to, url, goals, days }                ← 목표까지가 올림

const VERSION = "2026-10-12a";
const DEFAULT_ORIGINS = ["https://king08245-ui.github.io", /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/];
const MAX_BODY = 4 * 1024 * 1024;
const PROTOCOLS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"];

const slow = () => new Promise(r => setTimeout(r, 1000));   // 틀린 접속 코드는 1초 늦게(마구 맞혀 보기 어렵게)

function originOk(origin, env) {
  if (!origin) return false;
  const extra = String(env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
  return [...DEFAULT_ORIGINS, ...extra].some(o => (o instanceof RegExp ? o.test(origin) : o === origin));
}
function corsFor(origin, env) {
  if (!originOk(origin, env)) return {};
  return {
    "access-control-allow-origin": origin, vary: "origin",
    "access-control-allow-headers": "content-type, x-access-code",
    "access-control-allow-methods": "GET, PUT, OPTIONS",
    "access-control-max-age": "86400",
  };
}
function json(obj, status = 200, headers = {}) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers } });
}
function sameCode(a, b) {
  a = String(a ?? ""); b = String(b ?? "");
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0;
}
function givenCode(request) {
  const raw = request.headers.get("x-access-code") || "";
  try { return decodeURIComponent(raw); } catch { return raw; }
}
async function readBody(request) {
  const len = Number(request.headers.get("content-length") || 0);
  if (len > MAX_BODY) throw Object.assign(new Error("보낸 내용이 너무 커요"), { status: 413 });
  const t = await request.text();
  if (t.length > MAX_BODY) throw Object.assign(new Error("보낸 내용이 너무 커요"), { status: 413 });
  try { return JSON.parse(t || "{}"); } catch { throw Object.assign(new Error("요청 형식이 잘못됐어요"), { status: 400 }); }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/mcp" || url.pathname === "/mcp/") return handleMcp(request, env);
    if (url.pathname.startsWith("/.well-known/")) return new Response("not found", { status: 404 });   // 인증 없는 MCP 서버
    const cors = corsFor(request.headers.get("origin") || "", env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    if (url.pathname === "/" || url.pathname === "") {
      return new Response("역산 15분 플래너 동기화 서버가 동작 중이에요. 폰 앱 설정에 이 주소를 넣으세요: " + url.origin + "\n",
        { headers: { "content-type": "text/plain; charset=utf-8", ...cors } });
    }
    try {
      if (!env.BP) return json({ error: "서버에 저장소(KV)가 연결되지 않았어요. Cloudflare에서 이 Worker에 KV 바인딩 BP를 추가해 주세요." }, 500, cors);
      const needCode = !!env.ACCESS_CODE;
      const codeOk = needCode && sameCode(givenCode(request), env.ACCESS_CODE);
      if (url.pathname === "/api/status") {
        if (!codeOk) await slow();
        const out = { ok: true, version: VERSION, needCode, codeOk, weakCode: codeOk && String(env.ACCESS_CODE).length < 6 };
        if (codeOk) {
          const [d, mk] = await Promise.all([env.BP.get("data", "json"), env.BP.get("mk", "json")]);
          Object.assign(out, { rev: d?.rev || 0, at: d?.at || null, mkAt: mk?.at || null });
        }
        return json(out, 200, cors);
      }
      if (url.pathname === "/api/sync") {
        if (!needCode) return json({ error: "서버에 ACCESS_CODE가 없어요. Cloudflare → 이 Worker → 설정 → 변수 및 비밀에 ACCESS_CODE를 비밀로 넣어 주세요." }, 503, cors);
        if (!codeOk) { await slow(); return json({ error: "접속 코드가 맞지 않아요. 앱 설정의 접속 코드를 확인하세요." }, 401, cors); }
        if (request.method === "GET") {
          const [d, mk] = await Promise.all([env.BP.get("data", "json"), env.BP.get("mk", "json")]);
          return json({ ok: true, version: VERSION, rev: d?.rev || 0, at: d?.at || null, device: d?.device || null, data: d?.data || null, mk: mk || null }, 200, cors);
        }
        if (request.method === "PUT") {
          const body = await readBody(request);
          if (!body || typeof body !== "object" || !body.data || !Array.isArray(body.data.goals)) return json({ error: "요청 형식이 잘못됐어요 (data.goals가 없어요)" }, 400, cors);
          const cur = await env.BP.get("data", "json");
          const rev = cur?.rev || 0;
          if ((body.baseRev | 0) !== rev) return json({ error: "conflict", rev }, 409, cors);
          const rec = { rev: rev + 1, at: new Date().toISOString(), device: String(body.device || "").slice(0, 60), data: body.data, progress: body.progress || null };
          await env.BP.put("data", JSON.stringify(rec));
          return json({ ok: true, rev: rec.rev, at: rec.at }, 200, cors);
        }
        return json({ error: "GET이나 PUT으로 불러 주세요" }, 405, cors);
      }
      return json({ error: "없는 주소예요" }, 404, cors);
    } catch (e) {
      return json({ error: e.message || String(e) }, e.status || 500, cors);
    }
  },
};

/* ---------- MCP (Streamable HTTP, JSON 응답만) — claude.ai 사용자 지정 연결 '역산플래너' ---------- */
const TOOLS = [
  {
    name: "sync_goals",
    title: "목표까지 → 역산 플래너 맞추기",
    description: "목표까지(인생 목표 계획)의 목표·단계·앞으로의 평일 하루 분량을 역산 15분 플래너 폰 앱으로 보내고, 폰에서 끝낸 단계와 15분 기록·하루 분량 실적을 돌려받는다. code는 동기화 서버의 접속 코드(ACCESS_CODE).",
    inputSchema: {
      type: "object",
      properties: {
        code: { type: "string", description: "동기화 서버 접속 코드" },
        snapshot: { type: "object", description: "목표까지 스냅숏 {at, from, to, url, goals:[{id,short,cat,title,start,due,status,memo,steps:[{sid,t,due,done}],metrics:[{mid,name,unit,kind,days,start,target}]}], days:[{d,g,m,text,amt,unit,min,kind}]}" },
      },
      required: ["code", "snapshot"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: true, openWorldHint: false },
  },
  {
    name: "get_progress",
    title: "역산 플래너 진행 보기",
    description: "폰 앱이 마지막으로 올린 진행(끝낸 단계, 15분 기록, 하루 분량 실적)과 올린 시각을 읽는다. code는 동기화 서버의 접속 코드.",
    inputSchema: { type: "object", properties: { code: { type: "string", description: "동기화 서버 접속 코드" } }, required: ["code"], additionalProperties: false },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
];
const MCP_HEADERS = { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type, mcp-session-id, mcp-protocol-version, authorization", "access-control-allow-methods": "POST, GET, OPTIONS" };
const rpcOk = (id, result) => ({ jsonrpc: "2.0", id, result });
const rpcErr = (id, code, message) => ({ jsonrpc: "2.0", id: id ?? null, error: { code, message } });
const toolOk = obj => ({ content: [{ type: "text", text: JSON.stringify(obj) }], structuredContent: obj });
const toolErr = msg => ({ content: [{ type: "text", text: msg }], isError: true });

async function handleMcp(request, env) {
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: MCP_HEADERS });
  if (request.method !== "POST") return new Response("이 주소는 MCP(POST) 전용이에요.", { status: 405, headers: { allow: "POST", ...MCP_HEADERS } });
  let msg;
  try { msg = JSON.parse(await request.text()); } catch { return json(rpcErr(null, -32700, "Parse error"), 400, MCP_HEADERS); }
  const handle = async m => {
    if (!m || typeof m !== "object" || m.jsonrpc !== "2.0" || typeof m.method !== "string") {
      return m && m.id !== undefined ? rpcErr(m.id, -32600, "Invalid Request") : (m && (m.result !== undefined || m.error !== undefined) ? null : rpcErr(null, -32600, "Invalid Request"));
    }
    const isNote = m.id === undefined || m.id === null && m.method.startsWith("notifications/");
    try {
      switch (m.method) {
        case "initialize": {
          const want = m.params?.protocolVersion;
          return rpcOk(m.id, {
            protocolVersion: PROTOCOLS.includes(want) ? want : PROTOCOLS[1],
            capabilities: { tools: { listChanged: false } },
            serverInfo: { name: "backplan-sync", title: "역산플래너", version: VERSION },
            instructions: "역산 15분 플래너 폰 앱과 목표까지 계획을 맞추는 도구예요. 모든 도구에 동기화 서버 접속 코드(code)가 필요해요.",
          });
        }
        case "ping": return rpcOk(m.id, {});
        case "tools/list": return rpcOk(m.id, { tools: TOOLS });
        case "tools/call": return rpcOk(m.id, await callTool(m.params || {}, env));
        case "resources/list": return rpcOk(m.id, { resources: [] });
        case "prompts/list": return rpcOk(m.id, { prompts: [] });
        default:
          if (isNote || m.method.startsWith("notifications/")) return null;
          return rpcErr(m.id, -32601, "Method not found: " + m.method);
      }
    } catch (e) {
      return isNote ? null : rpcErr(m.id, e.rpcCode || -32603, e.message || String(e));
    }
  };
  if (Array.isArray(msg)) {
    const out = (await Promise.all(msg.map(handle))).filter(Boolean);
    return out.length ? json(out, 200, MCP_HEADERS) : new Response(null, { status: 202, headers: MCP_HEADERS });
  }
  const r = await handle(msg);
  return r ? json(r, 200, MCP_HEADERS) : new Response(null, { status: 202, headers: MCP_HEADERS });
}

async function callTool(params, env) {
  const name = params.name, args = params.arguments || {};
  if (!TOOLS.some(t => t.name === name)) throw Object.assign(new Error("Unknown tool: " + name), { rpcCode: -32602 });
  if (!env.BP) return toolErr("서버에 저장소(KV)가 연결되지 않았어요. Cloudflare에서 KV 바인딩 BP를 추가해 주세요.");
  if (!env.ACCESS_CODE) return toolErr("서버에 ACCESS_CODE가 없어요. Cloudflare에서 비밀 ACCESS_CODE를 넣어 주세요.");
  if (!sameCode(args.code, env.ACCESS_CODE)) { await slow(); return toolErr("접속 코드가 맞지 않아요. 역산 플래너 서버의 ACCESS_CODE와 같은 값을 넣어 주세요."); }
  const d = await env.BP.get("data", "json");
  const phone = d ? { rev: d.rev, at: d.at, device: d.device || "" } : null;
  if (name === "get_progress") {
    const mk = await env.BP.get("mk", "json");
    return toolOk({ ok: true, version: VERSION, phone, progress: d?.progress || null, mkAt: mk?.at || null });
  }
  // sync_goals
  const snap = args.snapshot;
  if (!snap || typeof snap !== "object" || !Array.isArray(snap.goals)) return toolErr("snapshot.goals가 없어요.");
  if (snap.goals.length > 300 || (Array.isArray(snap.days) && snap.days.length > 30000)) return toolErr("보낸 목표나 하루 분량이 너무 많아요.");
  const rec = { ...snap, days: Array.isArray(snap.days) ? snap.days : [], at: typeof snap.at === "string" ? snap.at : new Date().toISOString(), recvAt: new Date().toISOString() };
  const text = JSON.stringify(rec);
  if (text.length > MAX_BODY) return toolErr("보낸 내용이 너무 커요.");
  await env.BP.put("mk", text);
  return toolOk({ ok: true, version: VERSION, mkAt: rec.at, goals: rec.goals.length, days: rec.days.length, phone, progress: d?.progress || null });
}
