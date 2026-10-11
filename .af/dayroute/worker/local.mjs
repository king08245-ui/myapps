// 하루동선 시험 실행기 — 새 폰 화면(public/)과 Worker 코드(worker.js)를 이 컴퓨터에서 바로 돌린다.
//   node local.mjs                  → http://localhost:3000 (키는 ../dayroute-app/.env에서 읽음, 화면에 키를 보여 주지 않음)
//   node local.mjs --port=8788 --env=test.env --public=none   (검수용: API만)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import worker from "./worker.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, ...v] = a.replace(/^--/, "").split("="); return [k, v.join("=")]; }));
const PORT = Number(args.port || process.env.PORT || 3000);
const PUBLIC = args.public === "none" ? null : path.resolve(here, args.public || "public");
const ENVFILE = path.resolve(here, args.env || "../dayroute-app/.env");

const env = {};
if (fs.existsSync(ENVFILE)) {
  for (const line of fs.readFileSync(ENVFILE, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);
    if (m) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}
for (const k of Object.keys(process.env)) if (/^(KAKAO_|ODSAY_|ANTHROPIC_|ACCESS_CODE|ALLOWED_ORIGINS|SUBREQ_MAX|NAVI_BASE)/.test(k)) env[k] = process.env[k];

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json",
  ".webmanifest": "application/manifest+json", ".png": "image/png", ".svg": "image/svg+xml", ".css": "text/css" };

http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, "http://localhost");
    if (u.pathname.startsWith("/api/") || (!PUBLIC && u.pathname === "/")) {
      const chunks = [];
      for await (const c of req) chunks.push(c);
      const hasBody = !["GET", "HEAD"].includes(req.method);
      const headers = { ...req.headers };
      delete headers["content-length"];
      const r = await worker.fetch(new Request(`http://localhost:${PORT}${u.pathname}${u.search}`,
        { method: req.method, headers, body: hasBody && chunks.length ? Buffer.concat(chunks) : undefined }), env);
      res.writeHead(r.status, Object.fromEntries(r.headers));
      res.end(Buffer.from(await r.arrayBuffer()));
      return;
    }
    if (!PUBLIC) { res.writeHead(404); res.end("not found"); return; }
    let p = path.normalize(decodeURIComponent(u.pathname)).replace(/^([/\\])+/, "");
    if (!p || p.endsWith("/") || p.endsWith("\\")) p += "index.html";
    const file = path.join(PUBLIC, p);
    if (!file.startsWith(PUBLIC) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end("not found"); return; }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream", "cache-control": "no-store" });
    if (file.endsWith("index.html")) {   // 이 시험 서버가 API도 함께 준다는 표시 → 앱이 서버 주소 없이 바로 씀
      res.end(fs.readFileSync(file, "utf8").replace("<head>", '<head>\n<meta name="dayroute-local" content="1">'));
      return;
    }
    fs.createReadStream(file).pipe(res);
  } catch (e) {
    res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    res.end("시험 서버 오류: " + e.message);
  }
}).listen(PORT, () => {
  console.log(`하루동선 폰 화면 시험 → http://localhost:${PORT}`);
  console.log(`  카카오 키: ${env.KAKAO_REST_KEY ? "있음" : "없음"} · 지도 키: ${env.KAKAO_JS_KEY ? "있음" : "없음"} · ODsay 키: ${env.ODSAY_API_KEY ? "있음" : "없음"}`);
  console.log("  이 창을 닫으면 꺼집니다.");
});
