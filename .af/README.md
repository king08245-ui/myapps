# .af — 앱 원본 보관함

점(.)으로 시작하는 이 폴더는 GitHub Pages에 공개되지 않고 소스만 보관됩니다.
다음 작업 때 Claude가 여기서 기획서(SPEC.md)·자동 검수 흐름(flows.py)·검수 도구(appfactory.py)를 꺼내 이어서 고칩니다.

- `apps.json` — 배포된 앱 목록(주소, 마지막 수정일, 스토어 상태)
- `<앱>/SPEC.md` — 무엇을 만들었고 무엇을 정했는지
- `<앱>/flows.py` — 기능별 자동 검수 시나리오 (`python3 .af/appfactory.py qa <앱 폴더> --flows .af/<앱>/flows.py`)
