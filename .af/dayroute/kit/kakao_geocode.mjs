// 채널 맛집수첩 가게 주소를 카카오 주소 검색으로 다시 찍는다 (이 PC에서 실행, 인터넷 필요)
// 키는 ../dayroute-app/.env 의 KAKAO_REST_KEY를 읽기만 하고 화면·파일 어디에도 적지 않는다.
// 결과: kakao_geo.json  {주소: [위도, 경도, 정밀도] 또는 null}  정밀도 1=건물 번지까지, 2=도로·동까지, 3=지역만
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
const envFile = path.resolve(here, "../dayroute-app/.env");
const key = (fs.readFileSync(envFile, "utf8").match(/^\s*KAKAO_REST_KEY\s*=\s*(.+?)\s*$/m) || [])[1]?.replace(/^["']|["']$/g, "");
if (!key) { console.log("KAKAO_REST_KEY를 .env에서 찾지 못했어요"); process.exit(1); }
const addrs = JSON.parse(fs.readFileSync(path.join(here, "addrs.json"), "utf8"));
const LVL = { ROAD_ADDR: 1, REGION_ADDR: 1, ROAD: 2, REGION: 3 };
function clean(a) {   // 층·호·건물 이름·괄호를 빼고 번지까지만
  const t = a.replace(/\(.*?\)/g, " ").replace(/(로|길)\s+(\d+(?:번|가)?길)(?=\s|$)/g, "$1$2").split(/\s+/).filter(Boolean);
  for (let i = t.length - 1; i > 0; i--) if (/^\d+(-\d+)?$/.test(t[i]) && /(로|길|가|동|리)$/.test(t[i - 1])) return t.slice(0, i + 1).join(" ");
  return t.join(" ");
}
async function find(q) {
  const u = "https://dapi.kakao.com/v2/local/search/address.json?size=1&query=" + encodeURIComponent(q);
  for (const wait of [0, 1000, 3000]) {
    await new Promise(r => setTimeout(r, wait));
    try {
      const r = await fetch(u, { headers: { Authorization: "KakaoAK " + key } });
      if (r.status === 401 || r.status === 403) throw Object.assign(new Error("키 오류 " + r.status), { fatal: true });
      if (!r.ok) continue;
      return (await r.json()).documents || [];
    } catch (e) { if (e.fatal) throw e; }
  }
  return null;   // 세 번 다 실패
}
const out = {};
let n = 0, ok = 0, fail = 0;
for (const a of addrs) {
  let hit = null;
  for (const q of [...new Set([clean(a), a])]) {
    const docs = await find(q);
    if (docs === null) { fail++; break; }
    if (docs.length) { const d = docs[0]; hit = [+(+d.y).toFixed(6), +(+d.x).toFixed(6), LVL[d.address_type] || 3]; break; }
  }
  out[a] = hit; if (hit) ok++;
  if (++n % 100 === 0) console.log(`${n} / ${addrs.length} (찾음 ${ok})`);
  await new Promise(r => setTimeout(r, 60));
}
fs.writeFileSync(path.join(here, "kakao_geo.json"), JSON.stringify(out));
console.log(`끝: ${ok}곳 찾음 / ${addrs.length}곳, 실패 ${fail} → kakao_geo.json`);
