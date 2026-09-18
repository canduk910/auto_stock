# macro-lite — 운영 진단 가이드

매크로 대시보드(경기사이클·투자체제 · 장단기 금리차 · 하이일드 스프레드 · 환율 · 원자재) 전용
API 컨테이너를 운영자가 직접 켜고 점검하는 절차. `docs/backtest-monitoring.md` 와 같은 결로
쉬운 말로 적는다.

> 코드 정본:
> - vendor 패키지: `macro/macro_lite/`(원본 = stock-manager `packaging/macro_lite/`, 무수정 — `macro/README.md`)
> - 진입점: `macro/main.py` · 이미지: `macro/Dockerfile`
> - compose: `docker-compose.prod.yml`/`docker-compose.yml` 의 `macro` 서비스
> - nginx 프록시: `frontend/nginx.conf.template` · `frontend/nginx.tls.conf.template` 의 `location /api/macro/`
> - 배포 분류: `tools/deploy/compose_up_changed.sh` (`MACRO_RE='^macro/'`)

---

## 0. 이 컨테이너가 무엇인가 — 그리고 매매와 무관하다는 사실

`macro` 컨테이너는 5개 화면(경기사이클/투자체제 · 금리차 · 하이일드 스프레드 · 환율 · 원자재)에
데이터를 주는 **읽기 전용 조회 API** 다. yfinance·FRED 에서 시세를 받아와 캐시하고 판정 결과를
보여줄 뿐, 실제 매매 판단에는 **연결돼 있지 않다**.

- 매매가 실제로 보는 매크로 레짐은 여전히 `dkstock.cloud`(`src/engine/market_regime.py` ·
  `src/services/dkstock_client.py`)다. 이 컨테이너는 그 경로를 대체하지 않는다.
- `macro` 컨테이너가 죽어 있어도 매매 엔진·주문·손절·익일청산은 전부 정상 동작한다.
  대시보드의 「매크로」 메뉴 한 화면만 못 뜬다(502).
- 인증도 별도다 — `macro` 프로세스 자체에는 `X-API-Key` 같은 미들웨어가 없다
  (`macro/main.py` 의 `AUTH_DEPENDENCY=None`). 보호는 nginx Basic Auth 한 겹뿐이고,
  compose 는 이 컨테이너의 포트를 호스트에 게시하지 않는다(`ports:` 없음) — 외부에서
  직접 두드릴 방법이 없다.

---

## 1. EC2 최초 설치 절차

🔴 **`macro-cache` 디렉터리는 사람이 먼저 만든다.** compose 가 먼저 만들면 root:root 소유가
되어 컨테이너 안의 non-root 유저(`macro`, uid 1000)가 쓰기 거부당한다 — `.token_cache` 가
겪었던 사고와 같은 계열이다(`macro/Dockerfile` 주석 참조).

```bash
# EC2, ~/auto_stock/ 에서
mkdir -p ~/auto_stock/macro-cache
```

EC2 운영 계정(`ubuntu`)은 관례상 uid 1000 이고 컨테이너 유저도 uid 1000 으로 고정했으므로
위 `mkdir` 만으로 소유권이 이미 맞는다 — `secrets/`·`.htpasswd` 처럼 별도 `chmod` 가
필요 없다. 혹시 다른 uid 환경이라면(우분투가 아니거나 계정을 나중에 바꾼 경우):

```bash
# 컨테이너 uid(1000)와 호스트 소유자가 다를 때만
sudo chown -R 1000:1000 ~/auto_stock/macro-cache
```

그 다음은 평소 배포와 동일하다 — `git push` → GitHub Actions 가 `tools/deploy/compose_up_changed.sh`
를 호출하고, `macro/` 변경은 `mode=macro`(또는 backend 변경이 섞이면 `mode=full`)로 분류돼
`macro` 컨테이너가 뜬다. 최초 1회는 이미지가 없으므로 반드시 `full`(또는 수동
`docker compose -f docker-compose.prod.yml up --build -d`)로 배포해야 한다.

---

## 2. seed 적재 (하이일드 누적 시계열, 1회·멱등)

FRED 는 2026-04 부터 ICE BofA OAS 시리즈를 **최근 3년치만** 제공한다. 하이일드 스프레드 화면의
백분위 baseline(하워드 막스 5단계)은 컨테이너 안에 누적되는 10년 시계열에 의존하므로, 배포
직후 seed 를 한 번 적재해야 화면이 "최근 3년" 이 아니라 "10년" 기준으로 판정한다.

`macro/data/oas_history_seed.json` 이 이미 이미지 안에 들어 있다(운영 데이터 추출본 —
HY(`BAMLH0A0HYM2`) 881행 · IG(`BAMLC0A0CM`) 880행, 2023-05-09 ~ 2026-09-16). 컨테이너
안에서 다음을 실행한다:

```bash
docker compose -f docker-compose.prod.yml exec macro python -m macro_lite.seed
```

컨테이너의 `MACRO_LITE_CACHE_DIR` 은 이미 compose `environment` 로 `/var/lib/macro-lite`
(= 호스트 `./macro-cache`)로 고정돼 있으므로 이 명령만으로 **앱이 실제로 쓰는 경로와 동일한
곳**에 적재된다(README 의 "적재 경로가 앱과 달라야 한다" 함정을 compose 설정이 이미 막는다 —
직접 임시 컨테이너를 띄워 실행할 때만 `MACRO_LITE_CACHE_DIR=/var/lib/macro-lite` 를 앞에
명시한다).

출력 예시(실측 값 — 재실행해도 `total` 불변):

```
seed: /app/data/oas_history_seed.json
  BAMLH0A0HYM2: added=881 removed=0 total=881 range=2023-05-09 ~ 2026-09-16
  BAMLC0A0CM: added=880 removed=0 total=880 range=2023-05-09 ~ 2026-09-16
```

**멱등이다** — 이미 있는 날짜는 덮어쓰지 않고, 두 번 실행해도 `total` 이 그대로다. 배포마다
매번 실행해도 안전하지만, 보통은 **최초 설치 시 1회**면 된다(이후는 매일 FRED 조회로 1일치씩
자연 누적된다).

### `macro_regime_history_seed.json` 은 macro_lite 가 읽지 않는다

`macro/data/macro_regime_history_seed.json`(147행, 원 프로젝트 `macro_regime_history`
테이블 추출본)도 이미지 안에 함께 들어 있지만, 이 컨테이너의 어떤 API 도 이 파일을 읽지 않는다.
체제 판정(`macro_lite.regime.determine_regime`)은 **무상태**이고 직전 체제를 전달받지 않는다.
이 파일은 2단계(dkstock.cloud 전환 검토 시 원 프로젝트 산출값과 로컬 산출값을 비교하는 용도)를
위한 참고 자료일 뿐이다 — 매매 판단에도, macro_lite 자신의 판정에도 연결하지 않는다.

---

## 3. `FRED_API_KEY` 등록

FRED 무키 CSV 경로(`fredgraph.csv`)가 운영 IP 에서 막히면(HTML 차단·timeout) JSON API 폴백이
유일한 신선 데이터 경로가 된다. 키가 없어도 7일 stale 캐시까지는 화면이 뜨지만, 등록을 권장한다.

1. https://fred.stlouisfed.org/docs/api/api_key.html 에서 발급
2. EC2 `~/auto_stock/.env` 에 `FRED_API_KEY=발급받은값` 추가

⚠️ **`.env` 를 편집하면 `env_file: .env` 인 backend 가 재생성된다**(compose 가 `.env` 값이
바뀌면 그 파일을 참조하는 서비스를 재시작 대상으로 본다 — `macro` 는 `env_file: .env` 를 쓰지
않지만 backend 는 쓴다). 그래서 `.env` 편집은 **반드시 장외 창**에서만 한다 —
**15:30~16:00 · 21:35~익일 07:45** 또는 주말·공휴일(루트 `CLAUDE.md` 「운영 가이드」 절과
동일 규약). 편집 후 반영은 수동으로 컨테이너를 올려야 한다(배포 스크립트는 `.env` 를 git 밖이라
보지 못한다):

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## 4. 캐시 영속성이 왜 필수인가

FRED 가 OAS 시리즈를 최근 3년치만 공개하기 때문에, 이 컨테이너가 스스로 쌓아 온 10년 누적
시계열(`macro:oas_history_persist:{series_id}` 키, `./macro-cache/cache.db`)이 **유일한
장기 시계열 원천**이다. 이 파일이 사라지면:

- 3년을 넘는 과거분은 **영구 재취득이 불가능**하다(FRED 자체가 더 이상 주지 않는다).
- 하이일드 스프레드 **차트**의 10년·5년 구간이 "최근 3년" 으로 **영구 퇴행**한다 — seed JSON 을
  다시 넣으면 seed 범위(2023-05-09~2026-09-16)까지는 복구되지만(멱등이라 안전), seed 자체를
  잃으면 그마저 안 된다.

🔴 **누적 시계열은 백분위·z점수 baseline 이 아니다** — `fetcher.py::_fetch_fred_oas` 의
`_compute_oas_stats(rows)` 가 누적 store 머지(`merge_and_persist`) **앞**에서 돌고, 그 `rows` 는
**그 호출이 방금 받아 온 신선 fetch 결과**다. 즉 화면의 백분위·5단계 심리는 **그날 FRED 가 돌려준
범위**(CSV 약 881행 / JSON 폴백 약 787행, 둘 다 약 3년)로 계산되고, 누적 store 와 seed 는
**차트 시계열 전용**이다. CSV 가 막혀 JSON 으로 넘어간 날은 그 창이 약 4개월 짧아져 백분위가
미세하게 달라진다 — 그래서 **CSV↔JSON 시도 순서를 바꾸지 않는다**(바꾸면 매일 짧은 창으로 판정한다).

**그래서 `./macro-cache` 는 반드시 영속 볼륨이어야 한다**(tmpfs·컨테이너 임시 레이어 금지 —
compose 가 이미 호스트 bind mount 로 고정해 뒀으므로 기본 설정을 바꾸지 않는 한 안전하다).
백업 권고 — 정기적으로 `./macro-cache/cache.db` 를 스냅샷하거나, `macro/data/oas_history_seed.json`
을 최신화해 둔다(재추출 절차는 원본 README 의 `scripts/export_oas_history.py` — stock-manager
쪽 리포에만 있다, 이 리포에는 vendor 하지 않았다).

---

## 5. 장애 복구

### FRED_API_KEY 교체 후 즉시 반영하고 싶을 때

`credit_spread` 응답은 두 겹으로 캐시된다 — 당일 1회 캐시(`macro:daily:credit_spread:{날짜}`)와
fetcher 24h 캐시(`macro:credit_spread_v8` + FRED stale 폴백 `macro:credit_spread_fred_{hy,ig}_stale`).
키 등록 직후 신선 데이터를 강제로 받고 싶으면 **둘 다** 비운다:

```bash
docker compose -f docker-compose.prod.yml exec macro python - <<'PY'
from macro_lite import cache
cache.delete_prefix("macro:credit_spread")
cache.delete_prefix("macro:daily:credit_spread:")
PY
```

🔴 **`macro:oas_history_persist:*` 는 절대 지우지 않는다** — 위 「캐시 영속성」 절의 10년
누적 시계열이다. `delete_prefix("macro:credit_spread")` 는 접두사가 달라 이 키를 건드리지
않으므로 위 명령 자체는 안전하다. 이 키를 직접 지우는 명령을 만들지 않는다.

### 누적 store(캐시 볼륨) 자체를 유실했을 때

`macro/data/oas_history_seed.json` 백업이 있으면 위 §2 seed 명령을 다시 실행한다(멱등이라
안전). 백업이 없으면 FRED 가 제공하는 최근 3년치부터 다시 쌓이며 baseline 이 3년으로
퇴행한다 — 복구 불가 항목이므로 §4 의 백업 권고를 평소에 지킨다.

---

## 6. 로컬에서 화면 띄우기

```bash
docker compose up --build  # macro 서비스 포함 — 개발: 프론트 :3000 · 백엔드 :8002 · macro :8010(루프백)
```

브라우저에서 `http://localhost:3000/macro` 를 연다(vite dev 프록시가 `/api/macro` 를
`http://macro:8000` — 컨테이너 밖에서 `npm run dev` 로 직접 띄웠다면 기본값
`http://localhost:8010` — 로 넘긴다, `frontend/vite.config.ts`).

macro API 만 단독으로 찔러 보려면(컨테이너 기동 후):

```bash
curl -s http://localhost:8010/health
curl -s http://localhost:8010/api/macro/yield-curve | jq
```

프로덕션에서는 nginx Basic Auth 뒤에서 `https://auto.dkstock.cloud/macro`(또는 사내 도메인)를
연다 — 별도 포트가 없으므로 사이트 URL 그대로 `/macro` 경로만 붙인다.
