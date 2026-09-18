# cycle303 — macro_lite 이식 (1단계: macro API 컨테이너 + `/macro` 메뉴)

> 사용자 승인 2026-09-18 ("B로 가자" · "환율, 원자재, 경기사이클-투자체제 모두 포함" · "착수하자").
> **매매 행위 변화 0.** `src/engine/market_regime.py` · `src/services/dkstock_client.py` 무접촉.
> 이 사이클이 끝나도 매매는 여전히 dkstock.cloud 를 본다(전환은 3단계, 별도 승인).

원본(읽기 전용) = `/Users/koscom/Projects/stock-manager/packaging/macro_lite/` — **원본을 수정하지 않는다.**

---

## 1. 배치 — `macro/` 하나로 봉인

```
macro/                         # ← 새 최상위 디렉터리. 매매 이미지와 완전 분리
├── Dockerfile                 # 자체 이미지 (pandas/numpy/yfinance)
├── requirements.txt           # 원본 packaging/macro_lite/requirements.txt 그대로
├── main.py                    # FastAPI 진입점 (패키지는 router 만 준다)
├── pytest.ini                 # 원본 backend/pytest.ini (pythonpath = .)
├── macro_lite/                # 원본 backend/macro_lite/ 무수정 vendor
├── data/                      # 원본 backend/data/ (seed 2개)
└── tests/                     # 원본 backend/tests/ vendor
```

**팀 리드 지시(루트 `macro_lite/` + 루트 `data/`)에서 벗어난 유일한 항목이다.** 사유 셋:
1. `oas_history_store.SEED_PATH_DEFAULT` 가 요구하는 "`macro_lite` 와 `data` 가 같은 상위" 를 `macro/` 가 그대로 만족한다.
2. Docker 빌드 컨텍스트가 `./macro` 로 닫혀 매매 리포 전체가 macro 이미지 빌드에 실려 가지 않는다.
3. 배포 분류 정규식이 `^macro/` 단일 앵커가 된다(루트에 두면 `macro_lite/`·`data/` 두 축 + 루트 `data/` 라는 모호한 이름이 생긴다).

되돌리기는 `git mv` 한 번 + 정규식 한 줄이다.

## 2. 백엔드 계약

- 진입점 `macro/main.py` — `from macro_lite.router import router` 를 `include_router`. `router` 가 `prefix="/api/macro"` 를 이미 갖는다. `docs_url=None, redoc_url=None, openapi_url=None`(내부 전용). `GET /health` 1개 추가(compose healthcheck·진단용, 라우터 밖).
- `AUTH_DEPENDENCY = None` **그대로.** 우리 `ApiAuthMiddleware` 는 이 프로세스에 없고, 컨테이너 포트도 열지 않는다. 보호는 nginx Basic Auth 가 한다.
- `MACRO_LITE_CACHE_DIR=/var/lib/macro-lite` — **영속 bind mount 필수**(tmpfs 금지, 도메인 제약 3). 호스트 `./macro-cache`.
- `FRED_API_KEY` 선택. `env_file: .env` **금지**(비밀 33개를 macro 컨테이너에 밀어 넣는다) — `environment` 로 이 한 키만 전달.

### 도메인 제약 (원본과 결과가 갈리는 금기)
- 투자 로직·**캐시 TTL 변경 금지**(VIX 10분 · 환율/원자재 10분 · 금리차/사이클 1h · 하이일드 24h · FRED stale 7일).
- `credit_spread` **partial_failure 폐기 로직**(읽기측·쓰기측 2단) 유지.
- regime 판정은 **무상태** — `previous_regime` 미전달, **이력 저장소 추가 금지**.
- `credit_direction` 이 거의 항상 `"stable"` 인 것은 **원본 특성**. 버그로 고치지 않는다.
- `events.py` 침체 회색 alpha 0.15 상위 / 약세장 붉은색 alpha 0.10 — 색·레이어 순서 변경 금지.

## 3. compose

`docker-compose.prod.yml` **본체**에 `macro` 서비스(오버레이에 두면 `--remove-orphans` 가 지운다).
**`ports:` 없음** — compose 내부 네트워크 전용. `docker-compose.yml`(dev)에도 같은 서비스 + 루프백 포트 `127.0.0.1:8010:8000`(호스트 `npm run dev` 경로용).

## 4. nginx — 두 템플릿 **모두**

`frontend/nginx.conf.template`(80) · `frontend/nginx.tls.conf.template`(443) 양쪽에 `location /api/macro/` 를
`location /api/` **앞**에 둔다(prefix 최장일치라 순서 무관하지만 가독성 계약).

🔴 **upstream 은 변수 + resolver 로 지연 해석한다.**
```
resolver 127.0.0.11 valid=10s ipv6=off;
set $macro_upstream http://macro:8000;
proxy_pass $macro_upstream$request_uri;
```
리터럴 `proxy_pass http://macro:8000;` 은 nginx 가 **기동 시점에** 이름을 풀지 못하면 **기동 자체를 거부**한다 —
macro 컨테이너가 죽어 있거나 아직 안 뜬 순간에 대시보드가 통째로 내려간다. 변수 형식은 요청 시점 해석이라 502 로 끝난다.
`$request_uri` 는 변수 형식에서 URI 가 자동 전달되지 않기 때문에 필수다.

- `auth_basic` 2줄 명시(상속되지만 방어 심층화 — 기존 `/api/` 와 동일 규약).
- 🔴 `auth_basic off;` **절대 금지**(AST 가드 D-1-b).
- 치환 구문(달러+중괄호)을 새로 쓰지 않는다(cycle246 키 평문 유출 경로).
- `proxy_read_timeout 60s;` — 콜드 캐시 1회 갱신이 yfinance 27건이라 기본 60s 로는 빠듯하다.

## 5. 배포 분류 — `tools/deploy/compose_up_changed.sh`

`MACRO_RE='^macro/'` 추가. 모드를 **서비스 목록**으로 일반화한다(backend 축은 불변).

| 변경 | MODE | 명령 |
|---|---|---|
| backend 입력 | `full` | `up --build -d --remove-orphans` |
| frontend 만 | `frontend` | `up --build -d --remove-orphans --no-deps frontend` |
| macro 만 | `macro` | `… --no-deps macro` |
| 둘 다 | `frontend+macro` | `… --no-deps frontend macro` |
| 그 외 | `none` | `up -d --remove-orphans` |

- 판정 불가(마커 없음·미지 SHA·diff 실패·직전 시도 실패)는 **전부 full** — 불변.
- ⚠️ `set -e` 아래에서 `[ -n "$X" ] && ARR+=(x)` 는 조건이 거짓일 때 라인 종료코드 1 로 **스크립트를 죽인다.** 반드시 `if … then … fi`.
- `--remove-orphans` 는 compose 파일에 **정의되지 않은** 서비스만 지운다 — 목록에서 빠진 backend 는 안전하다.

## 6. 프론트

- `frontend/src/macro/` — 원본 `frontend/macro/` 를 **`.jsx` → `.tsx` 변환**. 응답 타입은 `frontend/src/types/macro.ts`.
- API 래퍼는 **우리 `frontend/src/api/client.ts`**(axios, `baseURL:'/api'`, `withCredentials:true`). 패키지의 `api/client.js` 는 **버린다**.
  🔴 **`X-API-Key` 를 프론트에서 붙이지 않는다** — nginx 가 주입하고 클라이언트 헤더를 치환한다.
  ⚠️ 우리 client 는 `timeout: 10000` 이다. macro 콜드 캐시 응답은 그보다 길다 → macro 호출만 **요청별 `timeout: 60000` 오버라이드**.
- 타입 계약 2(패키지 제공자 조언): `MacroCycleSection` 의 `data.cycle || data` 폴백과 `regime?.regime` optional chaining 이
  응답 shape 계약 자체다 → 두 필드를 **optional** 로 둔다.
- 라우트 `/macro` + 나브 leaf **"매크로"**(전략 그룹과 설정 사이). 경로 총 **11개**가 된다.
- **5개 섹션 전부**: 경기사이클+투자체제 · 장단기 금리차 · 하이일드 스프레드 · 환율 · 원자재.

### 🔴 경기사이클 보존 목록 (사용자가 유용하게 보고 있는 화면 — 구조를 새로 설계하지 않는다)
1. **국면 4칸 가로 배열** — 회복기 → 확장기 → 과열기 → 수축기. 현재 국면 진한 색 + 확대, 나머지 흐림.
2. **체제 4칸 가로 배열** — 적극 매수 → 선별 매수 → 신중 → 방어. 같은 방식.
3. 두 줄이 **나란히** 보여 동시에 읽히는 배치.
4. 판단 근거 지표 카드(장단기 금리차 · 크레딧 스프레드 · VIX · 섹터 로테이션 · 달러).
5. **`DivergenceNote`** — 국면과 체제가 엇갈릴 때의 경고.
6. 체제 상세(공포탐욕 · 버핏지수 · VIX 수치와 등급 라벨).
7. 설명 툴팁 `InfoTooltip`("버핏지수(4단계) × 공포탐욕(5단계) = 20칸 매트릭스" 류 해설).

색·간격·타이포만 우리 화면(`frontend/src/pages/`)에 맞춘다.

## 7. 데이터 적재

- `macro/data/oas_history_seed.json`(HY 881행 · IG 880행, 2023-05-09~2026-09-16).
  적재는 **앱 기동 시 자동이 아니다** — `python -m macro_lite.seed` 1회(멱등).
  **컨테이너가 쓰는 `MACRO_LITE_CACHE_DIR` 와 같은 경로**에 적재해야 한다.
- `macro/data/macro_regime_history_seed.json`(147행)도 가져오되 **macro_lite 는 이 파일을 읽지 않는다** —
  2단계 값 비교용 참고 자료다. 판정 입력으로 연결하면 원본과 결과가 갈린다.
- 운영 런북 `docs/macro-lite.md` 에 EC2 절차를 적는다. ⚠️ **`macro-cache` 디렉터리는 EC2 에서 사람이 먼저 `mkdir`** —
  compose 가 먼저 만들면 root:root 가 되어 컨테이너가 못 쓴다(`.token_cache` 사고와 같은 계열).

## 8. 가드 (신규)

1. nginx **두 템플릿 모두** 에 `/api/macro` 프록시가 있다(한쪽만 → RED).
2. macro 서비스가 `docker-compose.prod.yml` **본체**에 있고 `ports:` 가 **없다**.
3. 루트 `requirements.txt` 에 `numpy`/`yfinance` 가 **없다**(매매 이미지 오염 방지).
   ⚠️ `pandas` 는 **이미 루트에 있다**(`pandas==2.2.3`) — 가드 대상에서 뺀다.
4. `src/` 에 macro 코드가 없다(`macro_lite` import 0건).
5. 배포 분류에 macro 축이 있다(텍스트 + 행위).
6. 프론트: 5개 섹션이 모두 렌더 · 경기사이클이 국면 4칸 · 체제 4칸 · divergence 를 갖는다.

## 9. 범위 밖 (이번 사이클에 하지 않는다)

`src/engine/market_regime.py` · `src/services/dkstock_client.py` 접촉 · dkstock.cloud 전환 ·
매매 판단에 macro 값 연결 · 8영역 · `scheduler.py` · `src/realtime/CLAUDE.md`.
