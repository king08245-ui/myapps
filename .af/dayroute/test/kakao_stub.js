// 검수용 카카오 지도 SDK 흉내 (https://dapi.kakao.com/v2/maps/sdk.js 대신 flows.py가 넣어 줌)
// 지도는 그리지 않고, 장소 찾기(Places·Geocoder)는 아래 정해 둔 답을 돌려준다. 부른 기록은 window.__kakaoCalls
(function () {
  function LatLng(lat, lng) { this.lat = +lat; this.lng = +lng; }
  LatLng.prototype.getLat = function () { return this.lat; };
  LatLng.prototype.getLng = function () { return this.lng; };
  function LatLngBounds() { this.n = 0; }
  LatLngBounds.prototype.extend = function () { this.n++; };
  LatLngBounds.prototype.isEmpty = function () { return !this.n; };
  function KMap(el, o) { this.c = (o && o.center) || new LatLng(37.5443, 126.9515); }
  KMap.prototype.addControl = function () {};
  KMap.prototype.setBounds = function () {};
  KMap.prototype.panTo = function (c) { this.c = c; };
  KMap.prototype.relayout = function () {};
  KMap.prototype.getCenter = function () { return this.c; };
  function Overlay(o) { this.o = o || {}; }
  Overlay.prototype.setMap = function () {};
  Overlay.prototype.getContent = function () { return this.o.content; };

  // [이름, 분류, 경도, 위도, 주소]
  var PLACES = [
    ["공덕래미안5차아파트", "부동산 > 주거시설 > 아파트", 126.9562, 37.5469, "서울 마포구 마포대로 195"],
    ["공덕래미안5차 공영주차장", "교통,수송 > 교통시설 > 주차장 > 공영주차장", 126.9564, 37.5468, "서울 마포구 마포대로 195"],
    ["마포중앙도서관", "사회,공공기관 > 도서관 > 공공도서관", 126.9087, 37.5636, "서울 마포구 성미산로 128"],
    ["스타벅스 공덕역점", "음식점 > 카페 > 커피전문점 > 스타벅스", 126.952, 37.5431, "서울 마포구 마포대로 92"],
    ["스타벅스 서울역점", "음식점 > 카페 > 커피전문점 > 스타벅스", 126.9714, 37.5559, "서울 중구 한강대로 405"],
    ["정독도서관", "사회,공공기관 > 도서관 > 공공도서관", 126.98322, 37.58149, "서울 종로구 북촌로5길 48"]
  ];
  // [도로명 주소, 건물 이름, 경도, 위도]
  var ADDR = [["서울 마포구 마포대로 195", "공덕래미안5차아파트", 126.9562, 37.5469]];
  var squash = function (s) { return String(s).replace(/\s+/g, ""); };
  window.__kakaoCalls = [];

  function Places() {}
  Places.prototype.keywordSearch = function (q, cb, opt) {
    window.__kakaoCalls.push({ fn: "keyword", q: q, radius: (opt && opt.radius) || 0, loc: !!(opt && opt.location) });
    var k = squash(q);
    var hits = PLACES.filter(function (p) { return squash(p[0]).indexOf(k) >= 0; }).map(function (p, i) {
      return { place_name: p[0], category_name: p[1], x: String(p[2]), y: String(p[3]), road_address_name: p[4], address_name: p[4], place_url: "http://place.map.kakao.com/77" + i };
    });
    setTimeout(function () { cb(hits, hits.length ? "OK" : "ZERO_RESULT"); }, 20);
  };
  function Geocoder() {}
  Geocoder.prototype.addressSearch = function (q, cb) {
    window.__kakaoCalls.push({ fn: "address", q: q });
    var k = squash(q).replace(/^서울(특별시)?/, "");
    var hits = ADDR.filter(function (a) { return squash(a[0]).indexOf(k) >= 0; }).map(function (a) {
      return { address_name: a[0], x: String(a[2]), y: String(a[3]), road_address: { address_name: a[0], building_name: a[1] }, address: { address_name: a[0] } };
    });
    setTimeout(function () { cb(hits, hits.length ? "OK" : "ZERO_RESULT"); }, 20);
  };
  Geocoder.prototype.coord2Address = function (x, y, cb) {
    window.__kakaoCalls.push({ fn: "coord2Address", x: x, y: y });
    setTimeout(function () { cb([{ road_address: { address_name: "서울 마포구 시험로 12" }, address: { address_name: "서울 마포구 시험동 1" } }], "OK"); }, 20);
  };

  window.kakao = { maps: {
    load: function (cb) { setTimeout(cb, 0); },
    LatLng: LatLng, LatLngBounds: LatLngBounds, Map: KMap, CustomOverlay: Overlay, Polyline: Overlay,
    ZoomControl: function () {}, ControlPosition: { RIGHT: "RIGHT" }, event: { addListener: function () {} },
    services: { Places: Places, Geocoder: Geocoder, Status: { OK: "OK", ZERO_RESULT: "ZERO_RESULT", ERROR: "ERROR" },
      SortBy: { ACCURACY: "accuracy", DISTANCE: "distance" } }
  } };
})();
