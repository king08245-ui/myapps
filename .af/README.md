# .af — 앱 원본 보관함

점(.)으로 시작하는 이 폴더는 GitHub Pages에 공개되지 않고 소스만 보관됩니다.
다음 작업 때 Claude가 여기서 기획서(SPEC.md)·자동 검수 흐름(flows.py)·검수 도구(appfactory.py)를 꺼내 이어서 고칩니다.

- `apps.json` — 배포된 앱 목록(주소, 마지막 수정일, 스토어 상태)
- `<앱>/SPEC.md` — 무엇을 만들었고 무엇을 정했는지
- `<앱>/flows.py` — 기능별 자동 검수 시나리오 (`python3 .af/appfactory.py qa <앱 폴더> --flows .af/<앱>/flows.py`)
- `<앱>/store/*.md` — 플레이스토어 등록 문구·Play Console 답변·테스터 안내(스토어 키트가 있는 앱만)
- `dayroute/` — 하루동선 서버(Cloudflare Worker) 소스 `worker/worker.js`, PC 시험 실행기 `worker/local.mjs`, 검수용 가짜 API `test/mock_api.py`.
  검수 전에 `python3 test/mock_api.py 8790` 와 `node worker/local.mjs --port=8788 --env=../test/test.env --public=none`(8789는 test-ko.env)를 띄워야 함. 실제 키(.env)는 여기에 두지 않음.
  카카오 지도 SDK 흉내 `test/kakao_stub.js`(즐겨찾기 장소 찾기 검수용), PC판 즐겨찾기 모양의 시험 파일 `test/pc_favorites_sample.json`.
- `backplan/` — 역산 15분 플래너. 동기화 서버(Cloudflare Worker + KV) 소스 `worker/worker.js`, 시험 실행기 `worker/local.mjs`(메모리 KV).
  검수 전에 `node .af/backplan/worker/local.mjs --port=8791 --code=시험코드123`을 띄워야 연동 흐름이 돈다. 목표까지 아티팩트와는 claude.ai 사용자 지정 연결 '역산플래너'(`/mcp`)로 맞춤.
