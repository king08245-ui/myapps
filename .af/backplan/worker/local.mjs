// 역산 플래너 동기화 서버 시험 실행기 — Worker 코드를 이 컴퓨터에서 KV 대신 메모리(선택: 파일)로 돌린다.
//   node local.mjs --port=8791 --code=시험코드123 [--file=kv.json] [--nocode] [--nokv]
import http from "node:http";
import fs from "node:fs";
import worker from "./worker.js";

const args = Object.fromEntries(process.argv.slice(2).map(a => { const [k, ...v] = a.replace(/^--/, "").split("="); return [k, v.join("=") || "1"]; }));
const PORT = Number(args.port || 8791);
const FILE = args.file || null;

class MemKV {
  constructor() { this.m = new Map(); if (FILE && fs.existsSync(FILE)) for (const [k, v] of Object.entries(JSON.parse(fs.readFileSync(FILE, "utf8")))) this.m.set(k, v); }
  async get(key, type) { const v = this.m.get(key); if (v == null) return null; return type === "json" ? JSON.parse(v) : v; }
  async put(key, value) { this.m.set(key, String(value)); if (FILE) fs.writeFileSync(FILE, JSON.stringify(Object.fromEntries(this.m))); }
  async delete(key) { this.m.delete(key); if (FILE) fs.writeFileSync(FILE, JSON.stringify(Object.fromEntries(this.m))); }
}
const kv = new MemKV();
const env = { ACCESS_CODE: args.nocode ? undefined : (args.code || "시험코드123"), BP: args.nokv ? undefined : kv };

http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url, "http://localhost");
    if (u.pathname === "/__reset") { kv.m.clear(); if (FILE) fs.writeFileSync(FILE, "{}"); res.writeHead(200, { "access-control-allow-origin": "*" }); res.end("ok"); return; }
    if (u.pathname === "/__dump") { res.writeHead(200, { "content-type": "application/json", "access-control-allow-origin": "*" }); res.end(JSON.stringify(Object.fromEntries(kv.m))); return; }
    if (u.pathname === "/__put") {   // 시험용: 키 하나를 바로 넣기 (POST body = {key, value})
      const chunks = []; for await (const c of req) chunks.push(c);
      const { key, value } = JSON.parse(Buffer.concat(chunks).toString() || "{}");
      await kv.put(key, typeof value === "string" ? value : JSON.stringify(value));
      res.writeHead(200, { "access-control-allow-origin": "*" }); res.end("ok"); return;
    }
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const hasBody = !["GET", "HEAD"].includes(req.method);
    const headers = { ...req.headers }; delete headers["content-length"];
    const r = await worker.fetch(new Request(`http://localhost:${PORT}${u.pathname}${u.search}`,
      { method: req.method, headers, body: hasBody && chunks.length ? Buffer.concat(chunks) : undefined }), env);
    res.writeHead(r.status, Object.fromEntries(r.headers));
    res.end(Buffer.from(await r.arrayBuffer()));
  } catch (e) {
    res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    res.end("시험 서버 오류: " + e.message);
  }
}).listen(PORT, () => console.log(`역산 플래너 동기화 시험 서버 → http://localhost:${PORT} (코드 ${env.ACCESS_CODE ? "있음" : "없음"}, KV ${env.BP ? "메모리" : "없음"})`));
