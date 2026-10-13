# 새 채널·새 영상 반영 도구 (10/14 채널 4개 추가 때 쓴 것)

데이터는 공개 영상 설명란에서 뽑고, 위치는 카카오로 확인한다. 유튜브·카카오는 클라우드 작업 공간에서 바로 못 열어서
LEE PC의 Claude 데스크톱 앱 브라우저(내장 브라우저)를 거친다.

1. **영상 목록·설명란** — 내장 브라우저로 `https://www.youtube.com/@채널/videos`를 열고, 페이지 안에서
   `/youtubei/v1/browse`(이어 받기)로 영상 목록, `/youtubei/v1/player`로 설명란(`videoDetails.shortDescription`)과
   올린 날(`microformat.playerMicroformatRenderer.publishDate`)을 받는다(채널 4개 1,746편 약 15분).
   결과를 `JSON.stringify` 해서 돌려주면 큰 결과는 작업 공간에 파일로 저장된다 → `raw/<핸들>.json` {title, videos:[[id,제목,날짜,설명]]}.
2. **가게 후보** — `python3 extract.py <핸들>` → `cand_<핸들>.json`.
   주소 줄 앞의 이름, 번호 목록(1. ○○), 타임라인(00:50 ○○)을 읽는다. 목록 앞의 지역 낱말(수원 ○○, ○○ - 성수역)은 `ar`로.
3. **카카오 확인** — 하루동선 페이지(king08245-ui.github.io, 카카오 JS 키 등록 도메인)를 내장 브라우저로 열고
   `/api/status`의 jsKey로 지도 SDK(`libraries=services`)를 올려 주소 검색·장소 검색을 돌린다(키는 화면·기록에 남기지 않음).
   질의 목록은 `resolve2.py`가 `q_next.json`으로 만들고 `push_round.sh <글자>`가 작업 브랜치 `matjip-work`의 `w/q<글자>.json`으로 올린다 →
   브라우저가 raw.githubusercontent.com에서 받아 실행 → 결과를 11만 자 조각으로 돌려받아 `assemble.py r<글자>.json <조각 수>`.
   `need 0`이 될 때까지 반복(지역 이름 → 그 지역 안 같은 이름 가게 순으로 2~3번).
4. **맞추는 규칙(resolve2.py)** — 설명란 주소가 있으면 그 주소 좌표, 200m 안에 이름이 비슷한 음식점이 있으면 그 점.
   이름만 있으면 영상 제목·첫 줄의 지역(예: '강원도 횡성' → 횡성군) 반경 20km(역·동 단위면 8km) 안에서 이름이 같거나 거의 같은
   음식점만(멀수록 더 엄격). 못 찾은 이름(해외 영상·폐업·상품명·구내식당 등)은 넣지 않는다.
5. **합치기** — `python3 build_places.py` → `places_new.json`(기존 가게에도 카카오 가게 종류를 8번째 칸으로).

못 한 것: '서울 사는 남자'는 가게 목록이 네이버 지도 모음집(naver.me) 안에만 있는데, 내장 브라우저가 map.naver.com을
안전 제한으로 열지 않아 설명란에 이름이 적힌 6곳만 넣었다.
