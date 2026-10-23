// 배포할 때마다 VERSION을 올리면 설치된 앱이 새 화면을 받습니다.
const VERSION = 'backplan-v8';
const SHELL = ['./', './index.html', './manifest.webmanifest', './privacy.html',
  './icons/icon-192.png', './icons/icon-512.png', './icons/maskable-512.png', './icons/apple-touch-icon.png'];
const FONT_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com'];
const WAIT_MS = 3000;   // 신호가 약할 때 새 화면을 기다리는 최대 시간 — 넘으면 저장해 둔 화면을 먼저 보여 줌

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL.map(u => new Request(u, {cache: 'reload'})))));
  self.skipWaiting();
});
// 같은 주소(king08245-ui.github.io)에 다른 앱도 저장본을 두므로, 지우는 건 이 앱의 옛 저장본뿐
const PREFIX = 'backplan-';
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith(PREFIX) && k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});

const put = (req, res) => { if (res && (res.ok || res.type === 'opaque')) { const copy = res.clone(); caches.open(VERSION).then(c => c.put(req, copy)); } return res; };
const later = (ms, v) => new Promise(r => setTimeout(() => r(v), ms));

self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  const u = new URL(r.url);
  if (u.origin === location.origin) {
    if (r.mode === 'navigate' || u.pathname.endsWith('/') || u.pathname.endsWith('.html')) {
      // 화면: 새것을 받아 쓰되, 3초 안에 안 오면 저장본을 먼저 보여 주고 새것은 뒤에서 저장(다음에 열 때 반영)
      const net = fetch(r).then(res => put(r, res));
      e.waitUntil(net.catch(() => {}));
      e.respondWith(caches.match(r, {ignoreSearch: true}).then(m => m || caches.match('./index.html')).then(saved => {
        if (!saved) return net;
        return Promise.race([net.then(res => res.ok ? res : saved, () => saved), later(WAIT_MS, saved)]);
      }));
    } else {
      // 아이콘 등: 저장본으로 바로 열고, 뒤에서 새것으로 갈아 둠
      e.respondWith(caches.match(r, {ignoreSearch: true}).then(m => {
        const net = fetch(r).then(res => put(r, res)).catch(() => m || Response.error());
        return m || net;
      }));
    }
  } else if (FONT_HOSTS.includes(u.hostname)) {
    e.respondWith(caches.match(r).then(m => m || fetch(r).then(res => put(r, res))));
  }
});
