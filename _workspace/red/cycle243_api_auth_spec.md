# cycle243 — API 인증 2단계 도입: nginx Basic Auth(Phase 1) + 백엔드 X-API-Key fail-closed(Phase 2)

작성: team-leader, 2026-09-03. 사용자 지시 "리포 private 전환했어. API 인증도 진행해줘". 메인 세션 실측(EC2 노출면) + 3렌즈 전수 조사
(surface 79라우트 · frontend · backend_surface) + 코드 재실측 후 확정.

> **현재 상태 = 인터넷의 누구나 이 계좌의 매매를 조작할 수 있다.** `curl http://3.38.228.74/api/trading/status` → 200(무인증). 같은 표면에
> `POST /api/trading/manual-sell`(임의 종목·수량 시장가 매도) · `POST /api/trading/stop`(13포지션 손절 정지) · `PUT /api/strategies/{id}/params`
> (손절%·max_positions 임의 설정, 화이트리스트 없음) 가 함께 열려 있다. 인증은 **코드베이스 전체에 0건**이다(Depends/Security/APIKeyHeader 부재).
> 리포 private 전환은 소스 노출만 닫았고 **런타임 표면은 그대로**다.

> **워킹트리 상태**: cycle242 미커밋 파일 다수(`src/engine/strategy_base.py` · 전략 4 · 테스트 2 신규 · 워크리스트 등). **git commit / push /
> stash / checkout / restore 금지** — 이 워크플로는 `_workspace/red/cycle243_api_auth_spec.md` **1개 파일만** 생성한다. cycle242 변경을 되돌리거나
> 함께 커밋하지 않는다. ⚠️ 이 제약은 §6 배포 절차의 전제이기도 하다 — **Phase 1 커밋에 `src/` 가 한 줄이라도 섞이면 백엔드가 재시작된다**(§0 ①).

> **8영역 무접촉**(risk.py · order_engine.py · realtime/ · auth/ · api/order.py · session.py · scanner.py · strategy_registry.py) +
> scheduler.py · boot_manager.py 무접촉. **EC2 접속·설정 변경 금지**(htpasswd 생성 · .env 편집 · 컨테이너 재시작은 메인 세션이 사용자 승인 하에 수행).

---

## 0. 결정 요약 (착수 질문 ①~⑩ + 추가 4)

| # | 질문 | 결정 | 근거 |
|---|---|---|---|
| ① | Phase 1/2 파일 분리가 정말 "백엔드 무재시작"인가 | **보장된다 — 단 (a) Phase 1 커밋에 `src/**`·`requirements.txt` 가 0줄이고 (b) `docker-compose.prod.yml` 의 backend 블록과 **`.env` 를 둘 다 건드리지 않을 때만**.** ⚠️ **라운드 1 시정** — 종전 서술은 이미지 캐시 축만 따졌고 `.env` 축을 빠뜨렸다. backend 는 `env_file: .env` 라 **`.env` 에 한 줄만 추가해도 compose 가 서비스 config 를 다시 계산해 컨테이너를 재생성한다**(로컬 실측: `.env` 에 `API_AUTH_KEY=…` 추가 → `Container backend Recreated`, 컨테이너 ID 변경). 그래서 §6.1 P1-0 에서 `.env` 편집을 **삭제**하고 Phase 2 로 이월했다. 이것을 절차 규약(§6.1 커밋 파일 화이트리스트)과 정적 가드(D-8)로 이중 고정 | 루트 `.dockerignore` 가 `frontend/` · `_workspace/` · `docs/` · `*.md` · `supabase/` 를 제외하고, 루트 `Dockerfile` prod 스테이지는 `COPY requirements.txt .` 와 `COPY src/ ./src/` **둘뿐**이다. Phase 1 파일(`frontend/*` · `docker-compose*.yml` · `.gitignore` · `_workspace/*.md` · `tests/*`)은 어느 COPY 레이어의 입력도 아니므로 BuildKit 캐시가 전부 히트 → **동일 이미지 ID** → compose 가 backend 컨테이너를 재생성하지 않는다. compose 재생성 조건 = (이미지 ID 변경) ∨ (서비스 config 해시 변경) ∨ `--force-recreate` — deploy.yml:50 은 `up --build -d --remove-orphans` 로 셋 다 아니다. **그러므로 `docker-compose.prod.yml` 은 Phase 1 에서 `frontend:` 블록만 건드린다**(backend `ports` 변경은 config 해시를 바꿔 재시작 = Phase 2 로 이월) |
| ①-b | cycle232 D6("보유 시 장중 push 금지")가 Phase 1 에 적용되는가 | **적용되지 않는다.** D6 의 근거는 "재시작 1~5분 tick blind 손절 사각 + `_scan_loop` 5분 race" 이고, Phase 1 은 백엔드 프로세스를 재시작시키지 않는다 | 08-24 장중 재배포가 donchian `_breakout_high` 소실을 실측시킨 선례가 D6 의 근거인데 그건 **백엔드 재시작** 사건이다. Phase 1 은 frontend 컨테이너만 교체(대시보드 30~60초 단절, 매매 무영향)한다. **단 ① 의 전제가 깨지면 D6 가 즉시 되살아난다** — 그래서 배포 직후 `docker compose ps` 로 backend 의 `Up …` 경과시간이 유지됐는지 확인하는 것이 검증 항목이다(§6.2 V4) |
| ② | nginx 템플릿·envsubst·FILTER 설정 | 파일명은 **반드시** `frontend/nginx.conf.template` → `COPY nginx.conf.template /etc/nginx/templates/default.conf.template`, **기존 `COPY nginx.conf /etc/nginx/conf.d/default.conf` 줄 삭제 + `frontend/nginx.conf` 파일 자체 삭제**. `NGINX_ENVSUBST_FILTER=^API_AUTH_KEY$`(앵커 필수) | `nginx:alpine` 공식 엔트리포인트 기본값 = TEMPLATE_DIR `/etc/nginx/templates` · SUFFIX `.template` · OUTPUT_DIR `/etc/nginx/conf.d`. 즉 `default.conf.template` 만이 스톡 `default.conf` 를 **덮어쓴다** — 다른 이름이면 스톡 server 블록이 80 에 공존한다. 구 COPY 줄을 남기면 템플릿 렌더가 건너뛰어질 때 **인증 없는 구버전이 조용히 서빙되는 fail-open** 이 된다. 파일을 지우는 이유도 같다(드리프트 = 다음 사람이 되살릴 유혹). FILTER 는 스크립트가 `awk … name ~ filter` 로 **부분 일치** 평가하므로 앵커 없이 쓰면 `API_AUTH_KEY_OLD` 류까지 걸린다. FILTER 를 지정하는 진짜 이유는 `$host`/`$scheme` 보호가 아니라(그것들은 환경변수가 아니라서 애초에 치환 목록에 없다) **`.env` 에 같은 이름 변수가 생겼을 때의 프록시 헤더 오염 차단 + 다른 비밀이 설정 파일로 새는 것 차단** |
| ②-b | frontend 컨테이너에 비밀 주입 방식 | **`env_file: .env` 금지.** `environment: - API_AUTH_KEY=${API_AUTH_KEY}` 한 개만 | `env_file: .env` 는 KIS 키·OPENAI 키 등 33개 비밀을 nginx 컨테이너 환경에 넣는다. compose 는 프로젝트 디렉터리 `.env` 를 `${VAR}` 보간용으로 자동 로드하므로 env_file 없이도 해석된다(배포는 `cd ~/auto_stock` 에서 실행, 그 디렉터리에 .env 존재). 부수 효과로 ② 의 이름 충돌 위험 표면도 사라진다 |
| ③ | htpasswd 부재 시 처리 | **"기동 실패"가 아니다 — 증상은 세 갈래다**(라운드 1 실측 정정): 무자격 → **401**(정상과 동일) / 자격 + 파일 부재(ENOENT) → **403** / 자격 + 권한 거부(EACCES) → **500**. 방지책 = (a) 볼륨 소스를 **파일이 아니라 디렉터리**로 마운트(`./secrets:/etc/nginx/secrets:ro`, 파일은 `/etc/nginx/secrets/.htpasswd`) (b) **배포 전 선행 조건**을 절차서의 하드 게이트로 승격(§6.1 P1-0) (c) 배포 후 즉시 검증(§6.2 V1~V3) | `auth_basic_user_file` 은 설정 파싱 시점에 존재 검사를 하지 않고 **요청 시점**에 연다. bind mount 소스가 없으면 Docker 가 호스트에 빈 디렉터리를 만들어 마운트하므로 컨테이너는 정상 기동하고 `nginx -t` 도 통과한다. ⚠️ **무자격 요청은 파일이 정상일 때와 똑같이 401 이므로, 무자격 curl(V1)로는 이 결손을 원리적으로 탐지할 수 없다** — 검증은 반드시 `-u` 자격을 넣고 한다(§6.2 V1 정정). 그리고 500 은 "부재" 가 아니라 **권한 거부**의 신호다(nginx worker uid 101 vs 호스트 `ubuntu` uid 1000). deploy 는 새 컨테이너를 띄우기 전에 기존 것을 제거하므로 **자동 롤백이 없다**. 파일 대신 디렉터리를 마운트하면 최소한 `ls`/`test -f` 로 상태가 명확해지고 "파일이 디렉터리가 되는" 기괴한 상태가 안 생긴다. 완화 사실 = 프론트 500 이어도 **매매는 무영향**(엔진은 백엔드 in-process), 대시보드만 정지 = fail-closed 방향이므로 안전하지만 사용자 체감은 전면 장애다. CI 로 막을 수 없다(deploy.yml 은 허용 파일 목록 밖) |
| ④ | 백엔드 fail-closed vs fail-open | **fail-closed 확정.** `API_AUTH_KEY` 미설정·빈 문자열 → **모든 보호 경로 401** + 기동 시 CRITICAL 로그(변수명 명시, 값 미포함). 예외·비교 실패도 401 | (a) 매매 엔진은 in-process 라 API 잠김이 매매에 **영향 0**(대시보드만 멈춤) — 폭발 반경이 비대칭적으로 작다. (b) 반대편 fail-open 은 "키가 없으면 인증이 조용히 사라진다" = **이 사이클이 고치려는 결함의 정확한 재현**이고, 이 리포가 반복해서 데인 패턴이다(P0-1 유령 키 → 전략 2개 전 기간 체결 0 / KRX 오판 → full_universe 3,577→60 / 비중 단위 추론 변환 → 오염을 "균등분배"로 위장). 루트 CLAUDE.md 의 "조용히 흡수하지 말고 시끄럽게 거부" 독트린과 동일 방향. (c) fail-closed 의 유일한 실질 위험 = "키를 안 넣고 배포해 비상 시 manual-sell 이 막힌다" — 이것을 **구조적으로 불가능**하게 만든다: Phase 1 이 이미 `.env` 의 `API_AUTH_KEY` 를 envsubst 로 요구하므로, Phase 2 착수 전 `docker compose exec frontend grep X-API-Key /etc/nginx/conf.d/default.conf` 로 **키의 존재를 증명**한 뒤에만 Phase 2 를 푸시한다(§6.3 P2-0 = 하드 게이트). (d) healthcheck 폭발 반경 0 — 리포 전체에 `healthcheck:`/`HEALTHCHECK` 가 **0건**이고 deploy.yml 에도 curl 프로브가 없다 |
| ④-b | 401 vs 503 구분 / 사유 노출 | **응답은 401 단일** + 본문은 `ApiResponse` 봉투 고정 문구. 사유(`no_key_configured`/`missing_header`/`bad_key`/`cross_origin`)는 **로그에만** | 미설정 상태를 503 으로 구분하면 공격자에게 "이 박스는 키가 없다, 나중에 다시 오라"를 알려준다. 운영자 진단 채널은 기동 시 CRITICAL 로그 + `[api_auth_reject] reason=` 로 충분하다. 응답 본문은 `{"success": false, "data": null, "message": "unauthorized"}` — 라우트 응답 봉투 관례(`models/response.py::ApiResponse`)와 동형 |
| ⑤ | 미들웨어 등록 위치·순서 | **최외곽 = `src/main.py:308`(MetricsMiddleware 등록) 바로 뒤에 `app.add_middleware(ApiAuthMiddleware)`.** 실행 순서는 ServerError → **ApiAuth** → Metrics → CORS → Exception → router | Starlette 0.46.2 `add_middleware` 는 `user_middleware.insert(0, …)`, 스택은 `reversed()` 로 감싼다 ⇒ **마지막에 add 한 것이 가장 바깥**(소스 순서의 역, 직관과 반대라 반드시 명시). 최외곽이어야 하는 결정적 근거 = `MetricsMiddleware` 가 `_endpoint_metrics` 를 **정규화 없는 raw path** 로 키잉하는데(`main.py:48` `defaultdict(lambda: deque(maxlen=1024))`, `:57-59` 주석에도 명시) **키 개수 상한이 없다**. 인증을 안쪽에 두면 익명 `/api/<랜덤>` 폭주가 매매 프로세스 내 dict 를 무한 증식시키고 `GET /api/system/metrics` 가 그걸 되비춘다 = **인증 계층이 DoS 증폭기가 된다**. 부수 효과 2건은 무해하며 기록만 한다: 401 에 CORS 헤더 미부착(prod·dev 모두 same-origin이라 무의미) · preflight OPTIONS 가 인증에 도달(⑤-b) |
| ⑤-b | OPTIONS 예외를 두는가 | **두지 않는다.** OPTIONS 도 동일하게 인증 요구 | prod 에서 nginx `proxy_set_header` 는 **모든 메서드에 균일 적용**되므로 preflight 도 X-API-Key 를 달고 온다. dev 는 vite proxy 가 서버 측에서 같은 헤더를 주입한다(⑥). 즉 예외가 필요한 경로가 없고, 예외를 두면 "OPTIONS 로 시작하는 우회"라는 표면만 생긴다. 실무상 preflight 자체가 same-origin 구조에서 발생하지 않는다 |
| ⑤-c | 보호 범위 | **deny-by-default: `/health` 를 제외한 모든 경로.** `/api` 접두사 스코프 **기각** | `/api` 스코프는 `/docs`·`/redoc`·`/openapi.json` 을 못 덮는다 — `main.py:293-298` 이 `docs_url` 을 끄지 않아 **78개 엔드포인트 스키마가 통째로 열려 있다**(manual-sell·weights 요청 스키마 포함). 지금은 nginx 가 `/api/` 만 프록시해 SPA fallback 에 흡수되지만, SG 가 8000 을 열거나 nginx 규칙이 바뀌는 **한 번의 실수**로 노출된다. deny-by-default 는 앞으로 추가될 비-/api 라우트까지 자동 포함하는 유일한 형태다. `/health` 만 예외 = 관례적 liveness 프로브이고 현재 어떤 프로브도 없어 실사용은 EC2 호스트 수동 확인뿐(`kis_env` 노출은 수용) |
| ⑥ | 개발 환경(키 없이 로컬 실행) | **개발 예외·개발용 기본키 없음 — prod 와 동일한 단일 경로.** 키는 각자 `.env`(gitignore)에 넣고, dev 대시보드는 **vite proxy 가 서버 측에서 헤더를 주입**한다(`frontend/vite.config.ts` proxy `headers: { 'X-API-Key': process.env.API_AUTH_KEY ?? '' }`) + `docker-compose.yml` frontend 에 `API_AUTH_KEY=${API_AUTH_KEY}` 전달 | 커밋되는 개발용 기본키는 **공격자가 프로덕션에 가장 먼저 시도할 값**이다. `KIS_ENV != real` 류의 모드 분기 예외도 기각 — 운영이 vts 로 돌아가는 날 인증이 조용히 사라진다(비활성화=경로 변경 독트린). 키 없는 개발자는 401 을 보고 기동 로그의 CRITICAL(변수명 명시)로 **자가 진단**한다. dev 는 nginx 를 전혀 거치지 않으므로(프론트 `baseURL:'/api'` 상대경로 + vite proxy) Phase 1 은 dev 에 무영향이고, **Phase 2 만 dev 를 직격**한다 — 그래서 vite 주입이 Phase 2 에 동봉된다 |
| ⑦ | 기존 테스트 파급 최소화 | **`tests/conftest.py` 전역 autouse 픽스처 + 옵트아웃 마커 `real_api_auth`**(cycle202 `_neutralize_call_auction_gate` · cycle238 `_pin_pre_market_clock` 과 동형). 픽스처는 미들웨어 모듈의 **모듈 레벨 판정 함수 `authorize` 를 `lambda scope: ""` 로 monkeypatch** | 인증을 켜면 **40개 파일·수집 202케이스 중 201케이스가 401 로 전멸**하고 CI 전체 + coverage gate(`fail_under=60`)가 동반 실패한다(진입 경로 = `tests/contract/conftest.py:303` 의 `contract_env` 13파일 + 직접 `from src.main import app` 27파일). TestClient 는 27개 파일에서 각자 생성되므로 **기본 헤더 주입 방식은 27곳 수정**이 필요해 부적합. seam 은 한 곳이어야 한다. ⚠️ **프로덕션 코드에 `_TEST_BYPASS` 류 플래그를 두지 않는다** — 판정 함수 자체를 테스트가 갈아끼우는 형태여야 런타임에 우회 경로가 존재하지 않는다. 그래서 미들웨어는 `authorize` 를 **모듈 전역 이름으로 호출**해야 한다(메서드로 만들면 monkeypatch 가 안 먹는다 — 구현 계약, §2.3). 마커는 `pyproject.toml [tool.pytest.ini_options] markers` 에 **반드시 등록**(같은 파일 `filterwarnings = ["error"]` 때문에 미등록 마커는 즉시 스위트 실패) |
| ⑦-b | 픽스처가 만드는 사각 | 픽스처는 201 케이스를 인증에 **눈멀게** 만든다 → **배선 가드(B 그룹)** 로 보완: 최외곽 등록·Metrics 오염 차단·CORS 설정을 전용 테스트가 마커 하에 직접 검증 | 픽스처만 두면 "미들웨어 등록을 지웠는데 스위트가 전부 초록"이 성립한다. 이 사각은 반드시 명시적 가드로 닫는다 |
| ⑧ | 거부 로그 마커·cap | **`[api_auth_reject] reason=… method=… path=… ip=…`**(WARNING) — **cap 키는 `reason` 단독**(4종 고정), 카운트가 `1·10·100·1000·10000` 에 도달할 때만 발화(reason 당 ≤5행/일). 날짜 문자열 자기 리셋. `[api_auth_config]`(INFO, 기동 1회) · `[api_auth_key_missing]`(CRITICAL, 기동 1회, fail-closed 활성 시) | **cap 키에 raw path 를 넣으면 안 된다** — 인터넷 노출면이라 `/api/aaa`,`/api/aab`… 로 무제한 메모리 증가 벡터가 된다(`DailyEmitCap._emitted` 는 상한 없음). 그리고 `DailyEmitCap` 은 **스스로 날짜 롤오버를 하지 않는다**(외부 `reset_daily()` 호출자 = scheduler 일일 정산, 미들웨어엔 그 훅이 없다) → 요청 시점 날짜 키 자기 리셋을 직접 구현. 지수 임계는 "1행만"보다 **공격 볼륨**을 보여주면서도 유계다. 로그는 `logger.warning`(동기) — `write_log`(async, DB) 를 미들웨어에서 await 하면 인증 경로가 DB 에 결합된다. `_DbLogHandler` 가 INFO 컷으로 `system_logs` 까지 실어 나른다. **키 값·수신 헤더 값은 어떤 경로로도 로그에 남기지 않는다**(길이만). path 는 개행 제거 + 80자 절단(로그 인젝션 차단) |
| ⑨ | 운영 스크립트/문서 갱신 | §7 목록 — **포트에 따라 필요한 인증이 다르다**를 절차서에 못박는다: **:80 경유 = `-u <user>:<pass>`**(X-API-Key 는 nginx 가 주입) / **EC2 내부 :8000 직결 = `-H "X-API-Key: …"`**(nginx 미경유, basic auth 무의미) | 비상 매도 경로(`monday_0831_guide.md:37` manual-sell)가 :8000 직결이라 이 구분을 틀리면 **사고 당일 401 로 손이 묶인다** |
| ⑩ | TLS 부재 | **이번 범위 밖 — 한계로 명시 기록(L1) + 후속 F1 최우선 등재.** 동시에 **AWS SG 80 포트를 운영자 IP 로 제한**을 즉시 권고(사용자 콘솔 작업, 코드 범위 밖) | Basic Auth 자격과 X-API-Key 가 평문 HTTP 로 오간다. 경로상 관찰자는 자격을 그대로 획득한다. 인증 도입은 "익명 인터넷 전체 → 자격 보유자 + 경로 관찰자"로 공격면을 줄이는 것이지 없애는 것이 아니다 |
| ⑪ | **CORS 를 같은 사이클에서 닫는가** | **닫는다(Phase 2-C).** `allow_origins=["*"]` + `allow_credentials=True` → `allow_origins=<명시 목록>`(기본 빈 목록, `API_ALLOWED_ORIGINS` CSV). **라운드 1 추가** — `parse_allowed_origins` 가 `*` 항목을 **버리고** 기동 시 `[api_auth_wildcard_origin]` WARNING 을 남긴다(그 한 값이 CORS 전면 개방과 CSRF Origin 검사 무력화를 동시에 되살린다) | starlette 0.46.2 실측: `preflight_explicit_allow_origin = not allow_all_origins or allow_credentials` → True 이므로 **모든 오리진에 spec-valid 한 credentialed preflight 를 허가**한다. Phase 1 이 이걸 **악화**시킨다 — 운영자가 대시보드에 인증하면 브라우저가 Basic 자격을 캐시하고, 이후 방문하는 임의 사이트가 `credentials:'include'` 로 요청을 보낼 수 있으며 **nginx 의 X-API-Key 주입은 무차별**이라 출처를 구분하지 못한다. 수정 비용은 0 — prod·dev 모두 same-origin 이라(`client.ts:3` `baseURL:'/api'` 상대경로, `import.meta.env` 사용처 0건, dist 산출물에서 직접 확인) CORS 를 필요로 하는 소비자가 없다 |
| ⑫ | **CSRF — CORS 만으로 닫히지 않는다** | **상태변경 메서드(POST/PUT/PATCH/DELETE)에 Origin 검사 추가.** 규칙 = `Origin` 헤더 **부재 → 허용**(curl·ssh 스크립트 = 비상 경로, 절대 깨면 안 됨) / `Origin` 의 host:port == `Host` 헤더 → 허용 / `API_ALLOWED_ORIGINS` 등재 → 허용 / 그 외 → 401 `reason=cross_origin` | CORS 는 **simple request 를 막지 못한다** — 응답 읽기만 차단할 뿐 요청은 이미 실행된다. `POST /api/trading/stop` 은 본문이 없어 `Content-Type: text/plain` 인 simple request 로 성립하므로, CORS 를 아무리 조여도 브라우저 캐시된 Basic 자격 + nginx 주입 키로 **실행된다**. 표준 방어는 Origin 검사다. 자기 설정형(Host 매칭)이라 prod 는 설정 0으로 동작하고(Origin `http://3.38.228.74` vs Host `3.38.228.74` — nginx `proxy_set_header Host $http_host` 로 원 호스트를 **포트까지** 보존. ⚠️ 라운드 1 시정: 종전 `$host` 는 **포트를 떨어뜨려**(실측) SSH 터널 등 비-80 포트 접근의 상태변경을 전부 `cross_origin` 401 로 만들었다), dev 는 vite `changeOrigin: true` 가 Host 만 target 으로 바꾸고 브라우저 Origin 은 그대로 넘겨 **상태변경이 전부 401** 이 된다 — 라운드 1 에서 `vite.config.ts` proxy 가 `Origin: apiTarget` 도 함께 넣도록 시정해 **설정 없이** 동작하게 했다(`API_ALLOWED_ORIGINS` 는 폴백이지 전제가 아니다). GET 폴링만 통과해 "화면은 멀쩡한데 버튼만 죽는" 형태였다 |
| ⑬ | rate limiting | **이번 사이클 제외 — 후속 F8.** | nginx `limit_req` 는 싸지만 대시보드가 폴링을 18곳(최단 3초 `LogViewer.tsx:34`)에서 돌린다. 순진한 임계는 정상 사용자를 503 으로 끊는다. 임계 산정에 실측이 필요하므로 분리한다 |
| ⑭ | 키 규격·회전 | 32바이트 이상 URL-safe 랜덤(`python -c "import secrets;print(secrets.token_urlsafe(32))"`). 기동 시 길이 < 24 면 WARNING(값 미출력). **회전은 frontend·backend 동시 재시작 필요 → 장 종료 후에만** | `settings` 는 import 시점 싱글톤(`config.py:95`)이라 백엔드는 프로세스 재시작 없이는 새 키를 읽지 않고, nginx 는 컨테이너 시작 시 템플릿을 렌더한다. 회전 절차를 문서화하지 않으면 "키만 바꾸고 재시작 안 함" → Phase 2 fail-closed 로 대시보드 전면 401 |

### 렌즈 진단 전제 정정 (코드 재실측, 결론 불변)

1. **"htpasswd 파일이 없으면 nginx 가 기동 실패한다"(착수 컨텍스트)** → **틀렸다. 정상 기동한다.** ⚠️ **라운드 1 재정정** — 종전에 적어둔 "전면 500" 도 틀렸다(렌즈2 논증을 실측 없이 채택한 결과). 실측(nginx 1.31.5-alpine): 무자격 → **401**(정상과 동일) / 자격 + 파일 부재 → **403** / 자격 + 권한 거부 → **500**. 따라서 §6.2 V1 을 무자격 curl 로 두면 **어떤 결손도 탐지하지 못한다** — V1 을 `-u` 자격 요청으로 바꿔 403/500 을 실제로 보게 한다.
2. **"`/health` 가 유일한 비-/api 경로"(착수 컨텍스트)** → **아니다.** FastAPI 자동 문서 3종(`/docs`·`/redoc`·`/openapi.json`)이 살아 있다. 그래서 `/api` 접두사 스코프를 기각하고 deny-by-default 로 간다(⑤-c).
3. **"docker healthcheck 예외가 필요할 수 있다"(착수 컨텍스트)** → **불필요.** 리포 전체 grep 0건(compose 2종 · Dockerfile 2종 · deploy.yml). ci.yml 의 `--health-*` 는 임시 postgres 서비스 컨테이너용.
4. **"브라우저 fetch 가 basic auth 자격을 자동 동봉하는지 확인 필요"(착수 컨텍스트)** → **확인 완료·문제 없음.** 프로덕션 번들이 `axios.create({baseURL:'/api'})` 단일 클라이언트(21개 api 모듈 공유)이고 `import.meta.env` 사용처 0건이라 절대 URL 이 번들에 없다(dist 산출물 `baseURL:"/api"` 리터럴 확인). 문서 출처 == XHR 출처 → 자격 자동 동봉. `withCredentials` 불필요. SSE/WebSocket·raw fetch 0건. **Phase 1 은 프론트엔드 코드 변경 0**.
5. **"Phase 1 은 프론트 파일만이라 안전"** → 조건부다. `docker-compose.prod.yml` 의 **backend 블록**을 건드리면(예: `127.0.0.1:8000:8000`) config 해시가 바뀌어 백엔드가 재시작된다. 그 항목은 필요하지만 **Phase 2 로 이월**한다(①).
6. **"인증 미들웨어를 `BaseHTTPMiddleware` 로"** → **기각, 순수 ASGI 로 간다.** 이 리포는 anyio portal hang 으로 두 번 데였고(`test_cycle127_progress_routes.py`·`test_pnl_summary.py` 가 TestClient 회피를 명시), `stock_master` 4개 refresh 라우트가 `BackgroundTasks` fire-and-forget + 5초 폴링이다. `BaseHTTPMiddleware` 를 하나 더 쌓으면 매 요청 anyio task group + memory stream 이 추가된다. 순수 ASGI 는 거부 요청에서 `self.app` 을 아예 호출하지 않아 오버헤드도 0.

---

## 1. 확증된 사실 (3렌즈 + 재실측)

| 사실 | 근거 |
|---|---|
| 라우트 79개(= `/api` 78 + `/health`), 그중 **상태변경 32개**. 인증 코드 0건 | `src/main.py:311-327` 17 라우터 · grep `Depends(\|Security(\|APIKeyHeader\|X-API-Key` 무결과 · `src/config.py` 에 `api_auth_key` 부재 |
| **T0(자금 직접 이동)** — `POST /api/trading/manual-sell` 이 임의 종목·수량 **실 시장가 매도**를 낸다(바디 검증 0). `stop` 은 13포지션의 손절·트레일링을 정지시킨다(무한 하방). `restart` 는 공격자가 만드는 tick blind 창 | `routes/trading.py:101`(→ `place_order(side=SELL, price=0)`), `:95-97` 바디 `{ticker, quantity}` 뿐, `:28` stop, `:19` start, `:37` restart(stop→sleep(1)→start) |
| **T1 최대 레버** — `PUT /api/strategies/{id}/params` 는 화이트리스트 없이 `if key in strategy.config.params` 만으로 덮어쓰고 DB 영속 ⇒ 손절%·`atr_trail_mult`·`max_positions`·`position_ratio` 익명 설정 가능. cycle223 F2 가 recommendations apply 에만 `PARAM_RANGES` 를 넣은 **비대칭**이 여기 남아 있다 | `routes/strategies.py:168-181` vs `routes/recommendations.py:45` docstring |
| T1 매수 조종 14개(weights·auto-start·cash-usage-ratio·price-filter·trade-amount-filter·regime·integrations 7종) / **T2** quote-accounts POST·DELETE(KIS 앱키 주입·정상 계정 삭제) / **T3** stock_master refresh 4종이 KIS 20/s 한도를 매매 주문 경로와 공유(≈2,697종목×100ms≈13분) → 장중 주문 지연 유도 / **T4** 잔고·실현손익·전체 로그 익명 열람 | `strategies.py:103,202,224` · `system_integrations.py:123,173,227,270,367,432,490` · `kis_quote_accounts.py:52,123` · `stock_master.py:169,178,187,196` · `balance.py:19` · `history.py:42` · `logs.py:34,60` |
| `docker-compose.prod.yml` 이 backend 를 **0.0.0.0:8000** 에 게시 → AWS SG 가 유일한 방어막. Phase 1(frontend 컨테이너 한정)은 이 포트를 전혀 덮지 못한다 = **Phase 2 필요성의 직접 근거** | `docker-compose.prod.yml` backend `ports: "8000:8000"` |
| `/docs`·`/redoc`·`/openapi.json` 활성 — 78개 엔드포인트 스키마 공개 | `main.py:293-298` 에 `docs_url`/`redoc_url`/`openapi_url` 무지정 |
| CORS `*` + credentials 조합이 모든 오리진에 credentialed preflight 허가. 실제 응답은 `has_cookie` 게이트(cors.py:159) 때문에 브라우저가 **읽기만** 차단 — **요청은 이미 실행**됨(blind CSRF) | `main.py:300-306` · starlette 0.46.2 `cors.py:36,61,159` |
| Starlette `add_middleware` = `insert(0)`, 스택은 `reversed()` ⇒ **마지막 add 가 최외곽**. 현재 = Metrics(외) → CORS → router | `starlette/applications.py:131` |
| `MetricsMiddleware` 가 **raw path** 로 무제한 키를 만든다(`maxlen` 은 경로당 샘플 수만 제한) | `main.py:48,57-59` + 주석 "path templates 로 정규화하지 않고 raw path 사용" |
| **인증 켜면 40파일·201케이스 401 전멸** + coverage gate 동반 실패 | `tests/contract/conftest.py:303`(13파일) + 직접 import 27파일 · `ci.yml:68` 전체 스위트 · `pyproject.toml:74 fail_under=60` |
| 자체 `FastAPI()` 조립 6파일 + 라우트 함수 직접 await 7파일 = **영향 0**(미들웨어는 `src.main.app` 에만 붙는다) | 렌즈3 파일 목록 |
| `Settings` 는 pydantic-settings `BaseSettings` + `extra="ignore"` ⇒ `api_auth_key: str = ""` 한 줄로 `API_AUTH_KEY` 자동 매핑. `settings` 는 **import 시점 싱글톤** | `config.py:25,65,95` |
| `DailyEmitCap._emitted` 는 상한 없음 + `reset_daily()` 는 외부 호출자 의존(미들웨어엔 훅 없음) | `src/engine/daily_emit_cap.py` |
| `_DbLogHandler` 가 `src.*` 로거의 INFO 이상을 `system_logs` 로 실어 나름(500자 절단 + 500ms dedupe) | `main.py:161-202` |
| conftest autouse 선례 2건(파일명 제외형·마커 옵트아웃형) + `filterwarnings=["error"]` 로 미등록 마커 = 즉시 실패 | `tests/conftest.py:398,444` · `pyproject.toml` markers 블록 |
| `.dockerignore` 가 `frontend/`·`_workspace/`·`docs/`·`*.md`·`supabase/` 제외, 루트 Dockerfile prod 는 `COPY requirements.txt` + `COPY src/` 뿐 | `.dockerignore` · `Dockerfile:6,18` |
| 프론트 dist 가 `baseURL:"/api"` 상대경로 단일 클라이언트. axios 인터셉터 **없음**(→ 401 공통 처리 경로 부재, 후속 F4). `frontend/CLAUDE.md:20` 은 "인터셉터" 가 있다고 적어둔 **문서 드리프트** | `frontend/src/api/client.ts:3-9` · `frontend/dist/assets/client-*.js` · `frontend/CLAUDE.md:20` |

---

## 2. 시정 설계

### 2.1 Phase 1 — nginx Basic Auth (프론트엔드 자산만, 장중 배포 가능)

**신규 `frontend/nginx.conf.template`** (기존 `nginx.conf` 삭제):

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # cycle243 — 사이트 전체 Basic Auth. server 레벨에 두어 어떤 location 도 새지 않는다.
    auth_basic           "auto_stock";
    auth_basic_user_file /etc/nginx/secrets/.htpasswd;

    # API 리버스 프록시
    location /api/ {
        # 방어 심층화 — 상속으로도 걸리지만 명시한다(location 추가 시 누락 방지).
        auth_basic           "auto_stock";
        auth_basic_user_file /etc/nginx/secrets/.htpasswd;

        proxy_pass http://backend:8000;
        proxy_set_header Host $http_host;   # `$host` 는 포트를 떨어뜨린다(라운드 1 시정, §10 F5)
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # cycle243 — 백엔드 X-API-Key(Phase 2). 브라우저에는 노출되지 않는다.
        # proxy_set_header 는 클라이언트가 보낸 동명 헤더를 **치환**하므로 헤더 밀반입이 불가능하다.
        proxy_set_header X-API-Key "${API_AUTH_KEY}";
    }

    location / { try_files $uri $uri/ /index.html; add_header Cache-Control "no-cache, no-store, must-revalidate"; }
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ { expires 1y; add_header Cache-Control "public, immutable"; }
}
```

**`frontend/Dockerfile`** prod 스테이지: `COPY nginx.conf /etc/nginx/conf.d/default.conf` **삭제** → `COPY nginx.conf.template /etc/nginx/templates/default.conf.template`.

**`docker-compose.prod.yml`** — **`frontend:` 블록만** 변경(backend 블록 무접촉):
```yaml
  frontend:
    build: { context: ./frontend, target: prod }
    ports: ["80:80"]
    volumes:
      - ./secrets:/etc/nginx/secrets:ro     # .htpasswd — 호스트 선행 생성 필수(§6.1 P1-0)
    environment:
      - API_AUTH_KEY=${API_AUTH_KEY}        # env_file 금지(33개 비밀 주입 방지)
      - NGINX_ENVSUBST_FILTER=^API_AUTH_KEY$
      - TZ=Asia/Seoul
    depends_on: [backend]
    restart: unless-stopped
```

**`.gitignore`**: `secrets/` 추가. htpasswd 는 **git 에 절대 커밋 금지**.

### 2.2 Phase 2 — 백엔드 인증 (백엔드 재시작 → 15:30 이후)

**`src/config.py`** (2줄):
```python
    # cycle243 — API 인증. 미설정이면 fail-closed(모든 보호 경로 401) + 기동 시 CRITICAL.
    api_auth_key: str = ""
    # 교차 출처 허용 목록(CSV). 기본 빈 문자열 = same-origin 전용. dev 예: http://localhost:3000
    api_allowed_origins: str = ""
```

**신규 `src/middleware/api_auth.py`**(+ 빈 `__init__.py`) — 동기·순수 ASGI, `await` 는 하위 앱/응답 전송뿐. DB·HTTP 호출 0.

### 2.3 구현 계약 (지키지 않으면 목적이 무너지는 항목)

1. **`authorize` 는 모듈 레벨 함수**이고 미들웨어 `__call__` 은 이를 **한정하지 않은 전역 이름으로 호출**한다(`reason = authorize(scope)`). 메서드(`self._authorize`)로 만들면 ⑦ 의 테스트 seam 이 성립하지 않는다. 반환값은 `str` — `""` 가 통과, 그 외는 거부 사유.
2. **`scope["type"] != "http"` 는 즉시 통과**(lifespan·websocket). 빠뜨리면 앱이 기동하지 않는다.
3. **빈 키 선분기**가 헤더 비교보다 **먼저**다. `compare_digest("", "")` 는 True 이므로, 미설정 상태에서 빈 헤더를 보내면 통과하는 구멍이 생긴다.
4. 비교는 `secrets.compare_digest(사용자헤더.encode(), 설정키.encode())`. 인코딩·비교에서 **어떤 예외가 나도 거부**(fail-closed)로 흡수.
5. 키는 **요청 시점에** `settings.api_auth_key` 를 읽는다. `__init__` 에서 캡처하면 monkeypatch 가 통하지 않는다.
6. **키 값·수신 헤더 값은 로그·응답·예외 메시지 어디에도 넣지 않는다.** 기동 로그는 `key_len=<정수>` 만.
7. 거부 응답 = `JSONResponse({"success": False, "data": None, "message": "unauthorized"}, status_code=401)`. `WWW-Authenticate` 를 붙이지 않는다(브라우저가 백엔드 다이얼로그를 띄우면 Phase 1 자격과 혼동된다).
8. Origin 검사는 **상태변경 메서드 한정**이고 **Origin 부재는 허용**이다. GET 에 적용하면 대시보드 폴링이 죽고, 부재를 거부하면 비상 curl 경로가 죽는다.
9. 로그 cap 은 `reason`(4종 고정) 키 + `dict[str,int]` 카운터 + 날짜 문자열 자기 리셋. **path 를 키에 넣지 않는다.**

### 2.4 마커·로그 서식

| 마커 | 레벨 | 시점 | 서식 |
|---|---|---|---|
| `[api_auth_config]` | INFO | 기동 1회(lifespan) | `enabled=true key_len=44 allowed_origins=0 protected=all_except_health` |
| `[api_auth_key_missing]` | **CRITICAL** | 기동 1회, 키 부재 시 | `API_AUTH_KEY 미설정 — /api 전 경로 401(fail-closed). .env 에 API_AUTH_KEY 를 설정하고 재시작하라` (값 미포함) |
| `[api_auth_key_weak]` | WARNING | 기동 1회, `len < 24` | `key_len=12 — 32바이트 이상 권장` |
| `[api_auth_wildcard_origin]` | WARNING | 기동 1회, `API_ALLOWED_ORIGINS` 에 `*` | 와일드카드 항목을 **무시했다**는 통지(라운드 1 시정, §10 F10) |
| `[api_auth_reject]` | WARNING | 거부 시, `reason` 당 count ∈ {1,10,100,1000,10000} | `reason=missing_header method=POST path=/api/trading/manual-sell ip=1.2.3.4 ip_src=xri count=10` — `ip` 는 `X-Real-IP` → `X-Forwarded-For` 마지막 → peer 폴백이고 `ip_src` 가 어느 축인지 남긴다(라운드 1 시정, §10 F8) |

`reason` 은 `no_key_configured` · `missing_header` · `bad_key` · `cross_origin` 4종 고정. `path` 는 개행 제거 후 80자 절단.

### 2.5 Phase 2 동봉 — CORS 잠금(⑪) · Origin 검사(⑫) · 포트 바인딩

- `src/main.py:300-306` → `allow_origins=_parse_csv(settings.api_allowed_origins)`(기본 `[]`), `allow_credentials=True` 유지, `allow_methods`/`allow_headers` 는 현행 유지.
- `docker-compose.prod.yml` backend `ports: - "127.0.0.1:8000:8000"` — SG 오설정 시에도 :8000 이 인터넷에 뜨지 않는다. **이 한 줄이 backend 컨테이너 재생성을 유발**하므로 Phase 2 전용이다.
- `frontend/vite.config.ts` proxy 에 `headers: { 'X-API-Key': process.env.API_AUTH_KEY ?? '', Origin: apiTarget }` · `docker-compose.yml` frontend 에 `API_AUTH_KEY=${API_AUTH_KEY}`(dev 대시보드 생존). **`Origin` 정규화가 라운드 1 추가분**이다 — 없으면 dev 의 상태변경이 전부 `cross_origin` 401 이다(§10 F6).
- `.env.example` 에 `API_AUTH_KEY=` · `API_ALLOWED_ORIGINS=` 플레이스홀더(빈 값) + 생성 명령 주석. `API_ALLOWED_ORIGINS` 는 **prod 에서 비워 두는 것이 정상**이고 dev 도 vite Origin 정규화 덕에 빈 값으로 동작한다.

---

## 3. Red 목록

### A. 미들웨어 단위 — `tests/unit/middleware/test_cycle243_api_auth.py` (전 케이스 `@pytest.mark.real_api_auth`)

| # | 검증 |
|---|---|
| A-1 | 키 설정 + 올바른 `X-API-Key` → 200 |
| A-2 | 키 설정 + 헤더 없음 → 401 ∧ 본문 `{"success": false, "message": "unauthorized"}` |
| A-3 | 키 설정 + 틀린 헤더 → 401 |
| A-4 | 헤더 대소문자 무관(`x-api-key`·`X-Api-Key`·`X-API-KEY`) 전부 인정 |
| A-5 | **키 미설정("") + 헤더 없음 → 401**(fail-closed 핵심) |
| A-6 | **키 미설정("") + 빈 문자열 헤더 → 401**(`compare_digest("","")==True` 함정 봉인) |
| A-7 | `/health` 는 무인증 200 |
| A-8 | `/openapi.json`·`/docs`·`/redoc` → 401(deny-by-default 스코프) |
| A-9 | `/api/...` GET·POST·PUT·DELETE 전부 401(헤더 없을 때) |
| A-10 | `OPTIONS /api/...` 헤더 없으면 401 / 있으면 통과(예외 없음 계약) |
| A-11 | `scope["type"]` 이 `lifespan`·`websocket` 이면 통과 — TestClient 컨텍스트 진입 자체가 성공 |
| A-12 | `Origin` 부재 + POST + 올바른 키 → 200(curl 비상 경로 보호) |
| A-13 | `Origin: http://testserver` == `Host: testserver` + POST → 200 |
| A-14 | `Origin: http://evil.example` ≠ Host + POST → 401 `reason=cross_origin` |
| A-15 | `Origin: http://evil.example` + **GET** → 200(상태변경 한정 계약) |
| A-16 | `API_ALLOWED_ORIGINS="http://localhost:3000"` 등재 오리진 + POST → 200 |
| A-17 | `authorize` 가 내부 예외를 던져도 401(fail-closed 흡수) — 인위적 예외 주입 |
| A-18 | 같은 reason 150회 거부 → `logger.warning` 3행(count 1·10·100) ∧ 카운터 dict 키 ≤ 4 |
| A-19 | path 에 `\n`·`\r` 포함 → 로그 메시지에 개행 없음 ∧ 80자 절단 |
| A-20 | 키 값과 수신 헤더 값이 로그 레코드·응답 본문 어디에도 등장하지 않음 |
| A-21 | 날짜 롤오버(내부 day 키 조작) → 카운터·cap 자기 리셋 |
| A-22 | `log_startup_state()` — 키 부재 CRITICAL(변수명 포함·값 미포함) / `len<24` WARNING / 정상 INFO |
| A-23 | 미들웨어가 `settings.api_auth_key` 를 **요청 시점** 참조(monkeypatch 후 즉시 반영) |
| **A-25** | (라운드 1) `API_ALLOWED_ORIGINS=*` 여도 교차 출처 POST 는 401 ∧ 기동 시 `[api_auth_wildcard_origin]` WARNING ∧ `allowed_origins=0` |
| **A-26** | (라운드 1) 거부 로그 `ip=` 가 `X-Real-IP` 값 ∧ `ip_src=xri` ∧ peer 주소 미노출 |
| **A-27** | (라운드 1) Origin `http://127.0.0.1:8080` + Host `127.0.0.1:8080` → 200 / Host `127.0.0.1`(=`$host` 형태) → 401 |
| **A-28** | (라운드 1) dev 형태(Origin==Host: `backend:8000` · `localhost:8001`) POST → 200 |

### B. 앱 배선 — `tests/contract/test_cycle243_auth_wiring.py` (`@pytest.mark.real_api_auth`)

| # | 검증 |
|---|---|
| B-1 | `app.user_middleware[0].cls is ApiAuthMiddleware`(최외곽) |
| B-2 | **401 요청이 `_endpoint_metrics` 키를 늘리지 않는다** — 무작위 `/api/<uuid>` 30회 401 후 dict 길이 불변(⑤ DoS 논거의 행위 검증) |
| B-3 | 인증 통과 요청은 종전대로 metrics 에 계상 |
| B-4 | `CORSMiddleware` 의 `allow_origins` 가 `["*"]` 아님 |
| B-5 | 라우터 78개 `/api` 경로 전수 — 헤더 없이 호출 시 **한 건도 200 이 아님**(파라미터라이즈, 라우트 추가 시 자동 커버) |

### C. 기존 스위트 보호 — `tests/conftest.py` + `tests/unit/test_cycle243_auth_fixture.py`

| # | 검증 |
|---|---|
| C-1 | 마커 없는 테스트에서 `TestClient(app).get("/api/trading/status")` 가 **200**(픽스처 작동 증명) |
| C-2 | 같은 호출을 `@pytest.mark.real_api_auth` 로 하면 401(옵트아웃 작동 증명) |
| C-3 | `pyproject.toml` markers 에 `real_api_auth` 등재(미등록이면 `filterwarnings=error` 로 스위트 사망) |

### D. 배포 자산 정적 가드 — `tests/unit/ast/test_cycle243_deploy_assets.py`

| # | 검증 |
|---|---|
| D-1 | `frontend/nginx.conf.template` 존재 ∧ `auth_basic` 이 **server 레벨과 `/api/` location 양쪽**에 |
| D-2 | 템플릿에 `proxy_set_header X-API-Key "${API_AUTH_KEY}";` 존재 |
| D-3 | `frontend/nginx.conf`(구 파일) **부재** |
| D-4 | `frontend/Dockerfile` 에 `COPY nginx.conf.template /etc/nginx/templates/default.conf.template` ∧ `conf.d/default.conf` COPY **부재** |
| D-5 | `docker-compose.prod.yml` frontend 에 `NGINX_ENVSUBST_FILTER=^API_AUTH_KEY$` ∧ `API_AUTH_KEY=${API_AUTH_KEY}` ∧ `./secrets:/etc/nginx/secrets:ro` ∧ **`env_file` 부재** |
| D-6 | `docker-compose.prod.yml` backend `ports` 가 `127.0.0.1:8000:8000`(Phase 2) |
| D-7 | `.gitignore` 에 `secrets/` ∧ git 추적 파일에 `.htpasswd` 부재 |
| D-8 | **Phase 1 무재시작 전제 고정** — `.dockerignore` 에 `frontend/` 존재 ∧ 루트 `Dockerfile` prod 스테이지의 `COPY` 대상이 `requirements.txt`·`src/` 뿐(회귀 시 ① 이 깨짐) |
| D-9 | `frontend/vite.config.ts` 에 `X-API-Key` 주입 존재 ∧ `docker-compose.yml` frontend 에 `API_AUTH_KEY` 전달 |
| D-10 | `src/middleware/api_auth.py` 에 `secrets.compare_digest` 사용 ∧ 키를 `==`/`!=` 로 비교하는 노드 0건(AST) |
| D-11 | `.env.example` 에 `API_AUTH_KEY` 키 존재 ∧ **값이 비어 있음**(개발용 기본키 커밋 차단) |
| **D-1-b** | (라운드 1) 템플릿에 `auth_basic off;` **0건** — 한 줄로 Basic Auth 와 백엔드 키 주입이 동시에 뚫린다 |
| **D-2-b** | (라운드 1) `proxy_set_header Host $http_host;` ∧ `$host` 0건 — `$host` 는 포트를 떨어뜨려 비-80 접근의 상태변경을 전부 401 로 만든다 |
| **D-5-c** | (라운드 1) backend `ports` 루프백 ⇔ Phase 2 가드 파일 존재 **동치** — Phase 1 커밋에 ports hunk 가 섞이면 CI FAIL |
| **D-9-b** | (라운드 1) vite proxy 가 `Origin: apiTarget` 도 주입 — 없으면 dev 상태변경 전면 401 |
| **D-11-b** | (라운드 1) `.env.example` 의 `API_ALLOWED_ORIGINS` 에 `*` 0건 |
| **D-13** | (라운드 1) `parse_allowed_origins("*") == []` ∧ `has_wildcard_origin` 판별 |
| **D-14** | (라운드 1) `_client_ip` 가 `X-Real-IP` → `X-Forwarded-For` 마지막 → peer 순 폴백 + 출처 태그 |

프론트 vitest·Playwright 는 nginx 를 경유하지 않아 **깨지지 않지만 Phase 1 을 지켜주지도 않는다** — D 그룹이 유일한 자동 가드이고, 실제 nginx 기동 검증은 §6.2 수동 curl 뿐이다(L4).

---

## 4. 뮤테이션 목록 (전부 최소 1개 Red 가 FAIL 해야 한다)

| # | 뮤테이션 | 기대 FAIL |
|---|---|---|
| M-1 | `app.add_middleware(ApiAuthMiddleware)` 삭제 | B-1, B-5, A-2 |
| M-2 | 등록을 CORS 앞줄(안쪽)로 이동 | B-1, B-2 |
| M-3 | fail-closed → fail-open (`if not key: return await self.app(...)`) | A-5, A-6 |
| M-4 | `compare_digest` → `==` | D-10 |
| M-5 | 보호 범위를 `/api` 접두사로 축소 | A-8 |
| M-6 | `/docs` 를 예외 목록에 추가 | A-8 |
| M-7 | OPTIONS 무조건 통과 | A-10 |
| M-8 | Origin 검사 제거 | A-14 |
| M-9 | Origin 검사를 GET 에도 적용 | A-15 |
| M-10 | Origin 부재를 거부로 변경 | A-12 |
| M-11 | 빈 키 선분기 삭제(`compare_digest` 로 직행) | A-6 |
| M-12 | 로그 cap 키를 `(reason, path)` 로 변경 | A-18 |
| M-13 | 거부 로그에 수신 헤더 값 포함 | A-20 |
| M-14 | `scope["type"]` 게이트 제거 | A-11(TestClient 진입 실패) |
| M-15 | 키를 `__init__` 에서 캡처 | A-23 |
| M-16 | nginx 템플릿에서 `auth_basic` 삭제(server 또는 location) | D-1 |
| M-17 | Dockerfile 구 `COPY nginx.conf` 부활 | D-4 |
| M-18 | `NGINX_ENVSUBST_FILTER` 제거 | D-5 |
| M-19 | frontend 에 `env_file: .env` 추가 | D-5 |
| M-20 | `.env.example` 에 실제처럼 보이는 기본키 기입 | D-11 |
| M-21 | `authorize` 를 `self._authorize` 메서드로 변경 | C-1(픽스처 무효화 → 201케이스 401) |

**인증 우회 시도(공격자 시나리오) 전용**: (a) `X-API-Key` 를 클라이언트가 직접 보내 nginx 주입을 밀어내려는 시도 → `proxy_set_header` 치환으로 무효(§2.1 주석 + 수동 검증 V7) (b) 경로에 `/API/`·`//api/` 대소문자·중복 슬래시 변형 → deny-by-default 라 어차피 보호(A-8/B-5 로 커버) (c) OPTIONS 선행 → M-7 (d) Origin 없이 POST → 설계상 허용이나 **키가 없으면 어차피 401**(A-2 가 선행 방어).

---

## 5. 알려진 한계 (반드시 기록)

| # | 한계 | 성격 |
|---|---|---|
| **L1** | **TLS 부재** — Basic Auth 자격과 X-API-Key 가 평문 HTTP 로 오간다. 경로상 관찰자는 자격을 그대로 획득한다. 이번 사이클은 "익명 인터넷 전체 → 자격 보유자 + 경로 관찰자"로 줄일 뿐 없애지 않는다 | 범위 밖 · 후속 F1 최우선 |
| **L2** | **단일 공유 키·단일 계정** — 주체 식별, 부분 권한(읽기 전용 뷰), 감사 추적이 없다. manual-sell 을 누가 실행했는지 사후 확인 불가 | 설계 수용 · 후속 F7 |
| **L3** | Phase 1 만으로는 backend :8000 이 무방비(SG 가 유일 방어) — Phase 2 의 `127.0.0.1` 바인딩이 닫는다. **두 Phase 사이 기간이 위험 창** | 절차로 관리(§6.4) |
| **L4** | Phase 1 회귀 가드는 **텍스트 수준(D 그룹)뿐** — nginx 실기동·auth 동작을 검증하는 자동 테스트가 리포에 없다(vitest 는 jsdom+MSW, Playwright 는 vite dev server + `page.route` 모킹, 둘 다 nginx 미경유). 실검증은 배포 후 수동 curl | 명시 |
| **L5** | htpasswd 결손 = 기동 실패가 아니다. **무자격 401(정상과 구별 불가) / 자격+부재 403 / 자격+권한거부 500** 3갈래(실측). 자동 롤백 없음. 매매는 무영향(대시보드만) | 절차로 관리(§6.1 P1-0 · §6.2 V1 은 반드시 `-u`) |
| **L6** | 키 회전에 **frontend·backend 동시 재시작** 필요 → 장중 회전 불가 | 문서화(⑭) |
| **L7** | rate limiting 없음 — Basic Auth 무차별 대입 방어 없음 | 후속 F8 |
| **L8** | 인증은 **실수 방어가 아니다** — `PUT /api/strategies/{id}/params` 는 인증 후에도 화이트리스트 없이 손절 파라미터를 받는다(cycle223 F2 비대칭 잔존) | 후속 F3 |
| **L9** | 인증 통과자가 `/api/<랜덤>` 을 호출하면 `_endpoint_metrics` raw path 오염은 여전(최외곽 배치가 막는 것은 **익명** 폭주뿐) | 후속 F6 |
| **L10** | 대시보드에 401 공통 처리(axios 인터셉터)가 없어 자격 만료·키 교체 시 재인증 유도 없이 폴링만 조용히 실패한다(폴링 18곳, 최단 3초) | 후속 F4 |
| **L11** | (라운드 1) htpasswd 해시가 **apr1(MD5)** — 파일이 유출되면 오프라인 대입에 약하다. `openssl passwd -6`(SHA-512 crypt) 은 musl 에서도 동작하지만 이번엔 nginx 네이티브 지원이 확실한 apr1 을 유지했다. **L1(TLS 부재)이 살아 있는 동안은 해시보다 평문 자격이 먼저 새므로 우선순위가 낮다** — F1(HTTPS) 이후 재검토 | 후속 F1 종속 |
| **L12** | (라운드 1) `ip=` 는 프록시 1단(우리 nginx)만 신뢰한다. EC2 루프백 `:8000` 직결 호출자는 `X-Real-IP` 를 스스로 정할 수 있다(로컬 접근뿐이라 수용, `ip_src` 태그로 구분 가능) | 명시 |

---

## 6. 배포 절차서 초안

> 실행 주체 = **메인 세션 + 사용자 승인**. 이 워크플로(team-leader)는 EC2 에 접속하지 않고 커밋·푸시하지 않는다.

### 6.1 Phase 1 — 선행 조건 + 커밋 파일 화이트리스트

**P1-0 (EC2 선행, 배포 전 필수)**

> ⚠️ **`.env` 를 건드리지 않는다.** backend 가 `env_file: .env` 라 한 줄만 추가해도 compose 가
> backend 컨테이너를 **재생성**한다(실측) = Phase 1 무재시작 전제 붕괴 + 장중 tick blind.
> `API_AUTH_KEY` 추가는 **Phase 2(§6.3 P2-0, 15:30 이후)** 로 이월했다. Phase 1 동안
> `${API_AUTH_KEY}` 는 빈 문자열로 보간되어 `proxy_set_header X-API-Key "";` 로 렌더되고,
> 그러면 nginx 는 그 헤더를 아예 보내지 않는다 — Phase 1 백엔드는 아직 무인증이라 무해하다.
> (반대로 compose 의 `- API_AUTH_KEY=${API_AUTH_KEY}` 줄 자체를 지우면 변수가 **정의조차**
> 안 돼 envsubst 가 치환을 건너뛰고 nginx 가 `[emerg] unknown "api_auth_key" variable` 로
> **기동 실패**한다. 실측 확인 — 그 줄은 필수다.)

```bash
cd ~/auto_stock
# 권한: nginx worker 는 컨테이너 안 uid 101(nginx), 호스트 파일은 ubuntu(uid 1000) 소유다.
# 600/700 으로 두면 worker 가 열지도 traverse 하지도 못해 **자격 요청이 전부 500** 이 된다
# (실측 — `.token_cache` root 소유 사고와 동일 계열). 파일 내용은 apr1 해시뿐이고 호스트
# 접근은 이미 SSH 로 제한되므로 755/644 가 옳다.
mkdir -p secrets && chmod 755 secrets

# htpasswd 바이너리가 없으므로 openssl apr1 사용.
# 비밀번호를 **명령줄 인자로 주지 않는다** — argv 는 같은 호스트의 다른 사용자에게
# `ps aux` 로 보이고 셸 히스토리에도 남는다. `read -s` + `-stdin` 으로 넘긴다.
read -r -p 'basic auth user: ' AUTH_USER
read -r -s -p 'basic auth password: ' AUTH_PASS; echo
printf '%s:%s\n' "$AUTH_USER" "$(printf '%s' "$AUTH_PASS" | openssl passwd -apr1 -stdin)" \
  > secrets/.htpasswd
unset AUTH_PASS
chmod 644 secrets/.htpasswd

# 검증 (값은 출력하지 않는다)
test -s secrets/.htpasswd && echo "htpasswd OK: $(wc -l < secrets/.htpasswd) line(s)"
stat -c '%a %U' secrets secrets/.htpasswd   # → `755 ubuntu` / `644 ubuntu`
```

**P1-1 커밋 파일 화이트리스트 (`src/**` 와 `requirements.txt` 0줄 — ① 의 전제)**
```
frontend/nginx.conf.template      (신규)
frontend/nginx.conf               (삭제)
frontend/Dockerfile               (COPY 1줄 교체)
docker-compose.prod.yml           (frontend 블록만 — backend 블록 무접촉)
.gitignore                        (secrets/)
tests/unit/ast/test_cycle243_deploy_assets.py   (D-1~D-5, D-7~D-8 부분)
문서: README.md · frontend/CLAUDE.md · _workspace/00_URGENT_WORKLIST.md
```
> ⚠️ **`docker-compose.prod.yml` 한 파일에 Phase 1(frontend 블록)과 Phase 2(backend `ports`
> → `127.0.0.1`)가 함께 들어 있다.** git 은 파일 단위이고 이 실행 환경엔 `git add -p` 가
> 없으므로, Phase 1 커밋 전에 **backend `ports` 를 종전 값 `"8000:8000"` 으로 되돌린 뒤**
> 커밋하고, Phase 2 커밋에서 다시 `127.0.0.1:8000:8000` 으로 바꾼다. 이 짝짓기는 가드
> `test_cycle243_deploy_assets.py::test_compose_backend_ports_when_committed_then_paired_with_phase2_guard`
> (D-5-c)가 CI 에서 강제한다 — 루프백 바인딩이 Phase 2 가드 파일 없이 커밋되면 FAIL 한다.

**P1-1b 푸시 직전 하드 게이트** (전부 통과해야 push)
```bash
git diff --cached --name-only            # → P1-1 화이트리스트와 **정확히 일치**
git diff --cached --stat -- src/ requirements.txt   # → 출력 없음(0줄)
git diff --cached -- docker-compose.prod.yml | grep -E '^[+-][^+-]' | grep 8000
#   → 출력 없음(backend ports hunk 가 섞이지 않았음)
git status --porcelain -- .env           # → 출력 없음(.env 무편집)
```

**P1-2** `git push origin main` → CI success → Deploy 자동 실행.

### 6.2 Phase 1 배포 검증 (순서대로, 전부 통과해야 종료)

> ⚠️ **V1 은 반드시 자격을 넣고 한다.** 무자격 요청은 htpasswd 가 정상이든 부재든 **똑같이
> 401** 이라(실측) 결손을 원리적으로 탐지하지 못한다. 판별자는 **자격을 넣은 요청의 상태
> 코드**다: 200=정상 / **403=파일 부재** / **500=권한 거부**(P1-0 의 chmod 를 다시 본다).

| V | 명령 | 기대 |
|---|---|---|
| V1 | `curl -s -o /dev/null -w '%{http_code}\n' -u '<USER>:<PASS>' http://3.38.228.74/` | **200**. 403 = htpasswd **부재** / 500 = **권한 거부**(755·644 확인) → 즉시 P1-0 재확인 |
| V2 | `curl -s -o /dev/null -w '%{http_code}\n' http://3.38.228.74/api/trading/status` | **401**(무자격 차단 — 이 사이클의 목적 자체) |
| V3 | `curl -s -o /dev/null -w '%{http_code}\n' -u '<USER>:<PASS>' http://3.38.228.74/api/trading/status` | **200** |
| V4 | EC2: `docker compose -f docker-compose.prod.yml ps` | **backend 의 `Up …` 경과시간이 배포 전과 연속**(재시작 없음 = ① 확증) / frontend 는 방금 뜬 상태 |
| V5 | EC2: `docker compose -f docker-compose.prod.yml exec frontend grep -c 'proxy_set_header X-API-Key' /etc/nginx/conf.d/default.conf` | **1**(템플릿 렌더 성공). ⚠️ 종전 `grep -c 'X-API-Key'` 는 템플릿 **주석 2줄**까지 세어 실제 값이 **3** 이었다(정상 배포를 실패로 오판) |
| V6 | EC2: `docker compose ... exec frontend grep -cE '^[[:space:]]*proxy_set_header X-API-Key "[^"]{32,}";' /etc/nginx/conf.d/default.conf` | Phase 1 에서는 **0**(키를 아직 안 넣었다 — 정상). Phase 2 배포 후 **1**. ⚠️ 종전 `grep 'X-API-Key' \| wc -c > 60` 은 **빈 키로 렌더돼도 217** 을 반환해(주석 때문) 공허했다. **값 자체는 출력하지 않는다** |
| V7 | `curl -s -o /dev/null -w '%{http_code}\n' -u '<USER>:<PASS>' -H 'X-API-Key: attacker' http://3.38.228.74/api/trading/status` | **200**(Phase 1 시점) — Phase 2 이후 다시 실행해 **200 유지**면 `proxy_set_header` 치환 확증(공격자 키가 무시됨. 실측으로 확인된 성질) |
| V8 | 브라우저로 `http://3.38.228.74/` | 다이얼로그 → 로그인 후 대시보드 정상(폴링 포함) |
| V9 | EC2: 매매 로그 이상 없음(`[boot]` 재발생 없음, 포지션 수 불변) | 백엔드 무재시작 재확인 |

### 6.3 Phase 2 — 선행 게이트 + 배포

**P2-0 하드 게이트 (EC2 에서 `.env` 에 키를 넣고, 넣었음을 직접 증명한다)**

```bash
cd ~/auto_stock
# 키 생성·주입 — 값을 히스토리·argv 에 남기지 않는다.
grep -q '^API_AUTH_KEY=' .env || \
  python3 -c "import secrets;print('API_AUTH_KEY='+secrets.token_urlsafe(32))" >> .env
# 게이트: 32자 이상 실키가 정확히 1줄 (값은 출력하지 않는다)
grep -c '^API_AUTH_KEY=.\{32,\}$' .env    # → 1
```
> 이 `grep` 이 **1** 이 아니면 Phase 2 푸시 **금지**다 — fail-closed 라 대시보드가 전면 401 이 된다.
> ⚠️ **라운드 2 정정**: 그 상태의 최단 복구는 `git revert` 가 아니라 **EC2 에서 `.env` 에 키
> 한 줄을 넣고 `docker compose -f docker-compose.prod.yml up -d`**(수십 초)다 — `.env` 변경이
> 곧 backend·frontend 재생성이고 그 재생성이 키 반영이다(§10.1 F1 실측의 대칭 결과).
> `git revert` 후 재배포(CI+Deploy 5~10분 왕복)는 **기능 자체를 되돌릴 때**의 경로이지 사고
> 당일 1차 조치가 아니다. 종전 단정은 운영자를 긴 경로로 몰았다(§10.5 R2-3).
> ⚠️ 종전 게이트(§6.2 V6 의 `grep 'X-API-Key' | wc -c > 60`)는 **공허했다** — 템플릿 주석 2줄이
> 같은 문자열을 포함해 키가 빈 문자열로 렌더돼도 217바이트를 반환했다(실측). 호스트 `.env`
> 를 직접 재는 위 형태가 정본이고, 배포 후 확인은 정정된 V6 가 맡는다.
> ⚠️ 이 `.env` 편집은 그 자체로 backend 컨테이너를 재생성시킨다 — Phase 2 는 어차피 재시작
> 창(15:30 이후)이므로 여기서만 허용된다.

**P2-1 배포 창**: 보유 포지션이 있으면 **15:30 이후**(cycle232 D6 — 백엔드 재시작 1~5분 tick blind). 보유 0이면 장중도 가능하나 권고하지 않음.

**P2-2 커밋 파일**
```
src/config.py                        (2 필드)
src/middleware/__init__.py           (신규, 빈 파일)
src/middleware/api_auth.py           (신규)
src/main.py                          (add_middleware 1줄 + CORS allow_origins + lifespan 기동 로그 1줄)
docker-compose.prod.yml              (backend ports → 127.0.0.1:8000:8000)
docker-compose.yml                   (dev frontend 에 API_AUTH_KEY 전달)
frontend/vite.config.ts              (proxy headers 주입)
.env.example                         (API_AUTH_KEY= / API_ALLOWED_ORIGINS= 빈 값)
tests/conftest.py                    (env 기본값 + autouse 픽스처)
pyproject.toml                       (markers 에 real_api_auth)
tests/unit/middleware/… · tests/contract/… · tests/unit/ast/…   (A/B/C/D)
문서: CLAUDE.md · src/routes/CLAUDE.md · README.md · _workspace/monday_0831_guide.md · _workspace/00_URGENT_WORKLIST.md · docs/HARNESS_CHANGELOG.md
```

**P2-3 배포 검증**

| V | 명령(EC2 내부 실행) | 기대 |
|---|---|---|
| W1 | `curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/api/trading/status` | **401** |
| W2 | `KEY=$(grep '^API_AUTH_KEY=' .env \| cut -d= -f2-); CFG=$(mktemp); printf 'header = "X-API-Key: %s"\n' "$KEY" > "$CFG"; curl -s -o /dev/null -w '%{http_code}\n' --config "$CFG" localhost:8000/api/trading/status; rm -f "$CFG"` | **200**. ⚠️ `-H "X-API-Key: $KEY"` 형태는 키가 **argv 에 실려** `ps` 로 노출되고 히스토리에도 남는다 — curl config 파일 경유가 정본 |
| W3 | `curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/openapi.json` | **401** |
| W4 | `curl -s localhost:8000/health` | `{"status":"ok",...}` |
| W5 | `docker compose -f docker-compose.prod.yml ps` | backend 포트가 **`127.0.0.1:8000->8000/tcp`** |
| W6 | 외부: `curl -s -o /dev/null -w '%{http_code}\n' -u '<USER>:<PASS>' http://3.38.228.74/api/trading/status` | **200**(nginx 주입 확증) |
| W7 | `system_logs` 에 `[api_auth_config] enabled=true` 1행 ∧ `[api_auth_key_missing]` **0건** | 기동 정상 |
| W8 | 부팅 후 포지션 수·`[boot]` 마커 정상, 손절 감시 재가동 | 매매 정상 |

**롤백**: Phase 2 는 `.env` 에서 키를 지우면 **더 나빠진다**(fail-closed → 전면 401).
- **1차 조치(수십 초)** = 키 결손이면 `.env` 에 키를 넣고 `docker compose -f docker-compose.prod.yml up -d`. `.env` 변경이 컨테이너 재생성을 유발하고 그것이 곧 반영이다. 장중이면 재생성 = 1~5분 tick blind 를 감수하는 교환임을 명시한다.
- **기능 철회** = `git revert` 후 재배포(CI+Deploy 5~10분). 인증 자체를 되돌리기로 결정했을 때만.
- 비상 매도 절차서(`_workspace/monday_0831_guide.md`)의 401 분기가 이 순서를 그대로 담는다(§10.5 R2-3, 가드 D-17).

### 6.4 두 Phase 사이의 위험 창(L3) 관리
Phase 1 배포 후 Phase 2 전까지 backend :8000 은 SG 에만 의존한다. **Phase 1 당일 장 종료 직후 Phase 2 를 배포**하는 것을 기본으로 하고, 지연될 경우 사용자에게 **AWS SG 8000 인바운드 부재를 콘솔에서 재확인**하도록 요청한다.

---

## 7. 정본 문서·운영 스크립트 갱신 목록

> **상태(라운드 2, 2026-09-03)**: `README.md` · `_workspace/monday_0831_guide.md` · 루트 `CLAUDE.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md` · `docs/architecture.md` **갱신 완료**(§10.2 F7).
> ⚠️ **라운드 1 의 이 상태란은 `_workspace/00_URGENT_WORKLIST.md` 에 대해 false green 이었다** — 그 파일의 라운드 1 diff 는 curl 자격 치환 5줄(`-u "<USER>:<PASS>"`)뿐이고 §7 이 약속한 "신규 항목(cycle243 배포·후속 F1~F8) 등재" 가 없었다(`grep -n cycle243` = 1건, `HTTPS|TLS` = 0건). **라운드 2 에서 실제 등재**했다(§10.5 R2-1, 가드 D-16).
> **상태(사이클 종료, team-leader, 2026-09-03)**: 잔여 2건 **완료** — `docs/HARNESS_CHANGELOG.md` verbatim 1행 prepend + 루트 `CLAUDE.md` 하네스 표 1행 추가(가장 오래된 cycle226 행 제거, **15행 유지**). §7 표의 9개 파일 전부 갱신 완료다. 전체 스위트 실측 = 백엔드 **6,240 PASS**(10 skipped · 328 xfailed · 13 xpassed, 134s) · 프론트 **469 PASS**(68 파일). cycle243 표적 **77 PASS**. `python tools/test_impact/build_index.py` 재생성(backend modules 132 · tests 899). ⚠️ **커밋·푸시·EC2 접속은 미수행**(사용자 지시 대기) — 워킹트리에 **cycle242 미커밋 파일이 그대로 보존**돼 있다(`src/engine/strategy_base.py` · 전략 4 · 테스트 2 · 워크리스트). 배포 절차서는 §6 + 사이클 보고 `deploy_runbook`.

| 파일 | 내용 |
|---|---|
| `README.md:153` | `http://localhost:8000/docs` → 인증 필요 명시 + 로컬 실행 시 `API_AUTH_KEY` 필수 + 키 생성 명령 |
| `_workspace/monday_0831_guide.md:33,37` | **:8000 직결이므로 `-H "X-API-Key: …"` 필수**(basic auth 무의미). 비상 매도 커맨드 갱신 |
| `_workspace/00_URGENT_WORKLIST.md:664,667` | **:80 경유이므로 `-u <user>:<pass>`**. 신규 항목(cycle243 배포·후속 F1~F8) 등재 |
| 루트 `CLAUDE.md` | 환경 변수 절에 `API_AUTH_KEY`·`API_ALLOWED_ORIGINS` · 배포 절에 "Phase 1 은 백엔드 무재시작이라 D6 미적용, 단 `src/` 0줄 조건" · 핵심 안전 규칙에 "인증 fail-closed 는 조용히 끄지 않는다" · 하네스 표 1행 |
| `src/routes/CLAUDE.md` | 전 라우트가 `/api` 접두사 무관하게 인증 대상(`/health` 만 예외)이라는 계약 |
| `frontend/CLAUDE.md` | nginx 템플릿 전환 · Basic Auth · **문서 드리프트 시정**(`client.ts` 에 인터셉터가 있다는 :20 서술은 사실이 아니다) |
| `.env.example` | `API_AUTH_KEY=` / `API_ALLOWED_ORIGINS=` (빈 값 + 생성 명령 주석) |
| `docs/HARNESS_CHANGELOG.md` | cycle243 verbatim |
| `docs/architecture.md` | 요청 흐름도에 nginx auth_basic → X-API-Key 주입 → 미들웨어 단계 추가 |

---

## 8. 후속 (워크리스트 등재)

| # | 항목 | 우선도 |
|---|---|---|
| **F1** | **HTTPS 도입**(Caddy 자동 인증서 또는 ALB+ACM) — L1 해소. 도메인 필요 여부 사용자 결정 | **최우선** |
| **F2** | AWS SG 80 인바운드를 운영자 IP 로 제한(사용자 콘솔, 코드 범위 밖) — 즉시 가능한 최대 효과 | **즉시 권고** |
| **F3** | `PUT /api/strategies/{id}/params` 파라미터 화이트리스트(cycle223 F2 비대칭 해소, L8) | 높음 |
| **F4** | axios 401 인터셉터 — 재인증 안내/리로드(L10) | 중 |
| **F5** | 키 회전 절차 문서화·스크립트화(⑭·L6) | 중 |
| **F6** | `_endpoint_metrics` raw path 키 상한 또는 라우트 템플릿 정규화(L9) | 중 |
| **F7** | 감사 로그 — 상태변경 엔드포인트 호출자·시각·페이로드 요약 기록(L2) | 중 |
| **F8** | nginx `limit_req` — 폴링 실측(18곳, 최단 3초) 기반 임계 산정 후 도입(L7) | 낮음 |
| **F9** | `/docs`·`/redoc` 를 운영에서 완전 비활성(`docs_url=None`)할지 결정 — 현재는 인증으로 보호만 함 | 낮음 |

---

## 9. 실행 순서 (하네스)

1. **tdd-engineer** — §3 Red(A 23 · B 5 · C 3 · D 11 = 42 케이스) 작성. `pyproject.toml` 마커 등재를 **Red 와 같은 커밋**에 넣지 않으면 스위트 전체가 죽는다(`filterwarnings=error`).
2. **backend-dev** — §2.2~2.5 Green. §2.3 구현 계약 9항을 체크리스트로 확인.
3. **frontend-dev** — §2.1 nginx 템플릿·Dockerfile·compose(Phase 1) + vite proxy 헤더(Phase 2).
4. **tester** — §4 뮤테이션 21종 실증 + 전체 스위트(`python -m pytest -q -p no:cacheprovider`) + `cd frontend && npm test`. **201케이스가 초록으로 돌아왔는지**가 ⑦ 의 합격선.
5. **team-leader** — §6 절차서 확정 후 사용자에게 배포 승인 요청(Phase 1 장중 가능 / Phase 2 15:30 이후).

---

## 10. 적대적 검증 라운드 1 — 확증 결함과 시정 (backend-dev + tdd-engineer, 2026-09-03)

3렌즈 리뷰가 32건을 제출했고 중복을 접으면 **13개 축**이다. 전부 재현·실측으로 확증한 뒤
시정했다. 실측은 로컬 docker(compose v5.1.1 · `nginx:alpine` 1.31.5)에서 수행했고, 리포의
실제 `frontend/nginx.conf.template` 을 그대로 렌더해 검증했다.

### 10.1 확증 (실측 근거)

| # | 확증 내용 | 실측 |
|---|---|---|
| **F1** (HIGH) | **Phase 1 은 무재시작이 아니었다** — P1-0 의 `.env` 편집만으로 backend 가 재생성된다 | 최소 compose(backend `env_file: .env`)로 `up -d` → `.env` 에 `API_AUTH_KEY=…` **한 줄 추가** → `up -d` 출력 `Container backend Recreated`, 컨테이너 ID `8d1b6a959bf6` → `9d85f888cbc9`. 같은 실험에서 `environment: - X=${X}` 만 쓰는 frontend 도 재생성됨(`1d07` → `dbfd`) = **Phase 2 에서 키가 nginx 에 전파된다는 근거이기도 하다** |
| **F2** (HIGH) | **P1-0 의 권한 지시가 전면 500 을 만든다** — worker uid 101 vs 호스트 uid 1000 | 같은 컨테이너·같은 템플릿에서 파일 모드만 바꿔 4연속 측정: `644`+dir `755` → 자격 **200** / `chown 1000:1000`+`600` → 자격 **500** / 파일 644 + dir `700` → **500** / dir 755 + 644 복구 → **200**. `id nginx` → `uid=101` |
| **F3** (HIGH) | **Phase 2 하드 게이트 V6 가 공허** — 빈 키로 렌더돼도 통과, V5 기댓값도 오답 | 실키 렌더: `grep -c 'X-API-Key'` = **3**(문서 기대 1), `grep \| wc -c` = **261**. 빈 키 렌더: `grep -c` = **3**, `wc -c` = **217**(> 60 = 통과). 원인 = 템플릿 주석 2줄이 같은 문자열 포함. 대체식 `grep -cE '^[[:space:]]*proxy_set_header X-API-Key "[^"]{32,}";'` = 실키 **1** / 빈 키 **0** |
| **F4** (MEDIUM) | **htpasswd 결손 증상이 문서와 다르고, V1 은 그것을 탐지할 수 없다** | 무자격 → **401**(정상과 동일) / 자격+부재 → **403** / 자격+권한거부 → **500**. 즉 무자격 curl(V1)은 결손 여부와 무관하게 401 |
| **F5** (MEDIUM) | **`$host` 가 포트를 떨어뜨려 비-80 접근의 상태변경이 전부 401** | 클라이언트 `Host: 127.0.0.1:18109` → 업스트림 수신 `HOST=[127.0.0.1]`. `$http_host` 로 바꾼 대조군은 `HOST=[127.0.0.1:18113]` |
| **F6** (MEDIUM) | **dev 상태변경이 전부 `cross_origin` 401** | `authorize()` 직접 구동: Origin `http://localhost:3000` + Host `backend:8000` → `cross_origin`. GET 은 통과 = "화면은 멀쩡한데 버튼만 죽는" 형태 |
| **F7** (MEDIUM) | **§7 정본 문서·운영 스크립트 미갱신** — 비상 매도 curl 이 Phase 2 후 401 | `git status` 상 `monday_0831_guide.md`·`00_URGENT_WORKLIST.md`·`README.md`·`src/routes/CLAUDE.md`·`frontend/CLAUDE.md`·`docs/architecture.md` 전부 무변경이었다 |
| **F8** (MEDIUM) | **`ip=` 가 프로덕션에서 상수** — 잘못된 귀인 | Phase 2 는 backend 를 `127.0.0.1:8000` 에 묶어 전 요청이 nginx 경유 + uvicorn 에 `--proxy-headers` 없음 ⇒ `scope["client"]` = nginx 컨테이너 IP 고정. 템플릿은 이미 `X-Real-IP`/`X-Forwarded-For` 를 넣고 있었는데 미들웨어가 읽지 않았다 |
| **F9** (MEDIUM) | **Phase 1/2 파일 분리가 강제되지 않음** — `docker-compose.prod.yml` 한 파일에 두 Phase 가 섞여 있고 D-5-b 는 `ports` 를 안 본다 | 워킹트리에 Phase 2 값(`127.0.0.1:8000:8000`)이 이미 들어간 상태에서 Phase 1 가드가 초록이었다 |
| **F10** (MEDIUM) | **`API_ALLOWED_ORIGINS=*` 한 줄로 결정 ⑪ 이 원복** | `parse_allowed_origins("*")` → `['*']` → starlette `allow_all_origins=True`. 값 검증·기동 경고·회귀 가드 전무 |
| **F11** (MEDIUM) | **배포 명령이 비밀을 argv·히스토리에 남긴다** | `openssl passwd -apr1 '<PASSWORD>'`(argv) · W2 의 `-H "X-API-Key: $(…)"`(argv) |
| **F12** (MEDIUM) | **D-9 vite 가드가 주석만으로 충족** | 파일 내 `X-API-Key` 2회·`API_AUTH_KEY` 3회 중 코드는 각 1회. 실제 주입 줄을 지워도 초록 |
| **F13** (HIGH) | **D-1 정규식이 `auth_basic off;` 를 통과** — 그 파일이 스스로 위협으로 적어둔 우회를 못 잡음 | 템플릿에 `location = /api/bypass { auth_basic off; … }` 한 블록 주입 → nginx 정상 기동 + **무자격 200** |

### 10.2 시정

| # | 무엇을 | 어디를 |
|---|---|---|
| F1 | Phase 1 절차에서 **`.env` 편집 삭제** → Phase 2 P2-0 으로 이월. Phase 1 은 빈 키로 렌더(`X-API-Key ""` = 헤더 미전달)되고 그때 백엔드는 아직 무인증이라 무해 | 명세 §0-① · §6.1 P1-0 · §6.3 P2-0 · `docker-compose.prod.yml` 주석 · 루트 `CLAUDE.md` 배포 절 |
| F2 | `chmod 700/600` → **`chmod 755 secrets` + `chmod 644 secrets/.htpasswd`** + 사유(uid 101 vs 1000) 명시 | 명세 §6.1 P1-0 · 템플릿 주석 · compose 주석 · `CLAUDE.md` |
| F3 | V5/V6 를 **지시문 한 줄**로 좁히고(`proxy_set_header X-API-Key "…32자 이상…"`), 하드 게이트 P2-0 을 **호스트 `.env` 직접 측정**으로 교체 | 명세 §6.2 V5·V6 · §6.3 P2-0 |
| F4 | 증상 3갈래로 통일 + **V1 을 `-u` 자격 요청으로 전환**(무자격 V1 은 탐지 불가) | 명세 §0-③·렌즈 정정 1·L5·§6.2 · 템플릿·compose 주석 · `CLAUDE.md` |
| F5 | `proxy_set_header Host $host` → **`$http_host`** | `frontend/nginx.conf.template` + 가드 D-2-b + 행위 회귀 A-27 |
| F6 | vite proxy 가 `Origin: apiTarget` 도 주입 — dev 가 **설정 없이** 동작 | `frontend/vite.config.ts` + 가드 D-9-b + 행위 회귀 A-28 |
| F7 | 운영 문서 6종 갱신(포트별 인증 차이 명시) | `_workspace/monday_0831_guide.md`(비상 매도 curl 을 curl config 파일 경유로) · `_workspace/00_URGENT_WORKLIST.md` · `README.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md`(인터셉터 드리프트 동반 시정) · `docs/architecture.md`(요청 인증 흐름도 신설) |
| F8 | `_client_ip` 를 `X-Real-IP` → `X-Forwarded-For` **마지막** 항목 → peer 순 폴백 + **`ip_src` 출처 태그** 병기 | `src/middleware/api_auth.py` + 가드 D-14 + 행위 회귀 A-26 |
| F9 | D-5-b 를 **ports 를 뺀 backend 전 형태 고정**으로 강화 + 신규 **D-5-c** 가 "루프백 ports ⇔ Phase 2 가드 파일" 을 동치로 묶어 CI 에서 강제 + 푸시 직전 하드 게이트 **P1-1b** | `tests/unit/ast/test_cycle243_deploy_assets.py` · 명세 §6.1 |
| F10 | `parse_allowed_origins` 가 `*` 를 **버리고**, 기동 시 `[api_auth_wildcard_origin]` WARNING | `src/middleware/api_auth.py` + 가드 D-13 · D-11-b + 행위 회귀 A-25 |
| F11 | `openssl passwd -apr1 -stdin` + `read -s`, W2 는 **curl config 파일** 경유 | 명세 §6.1 P1-0 · §6.3 W2 · `monday_0831_guide.md` |
| F12 | D-9 가 **주석을 걷어낸 코드**에서 검사하고 값이 `process.env.API_AUTH_KEY` 인지까지 확인 | `tests/unit/ast/test_cycle243_phase2_assets.py` |
| F13 | D-1 을 **realm 문자열까지** 요구하도록 강화 + 신규 **D-1-b** 가 `auth_basic off;` 0건 강제 | `tests/unit/ast/test_cycle243_deploy_assets.py` · 템플릿 주석 |

### 10.3 뮤테이션 실증 (전부 검출)

| 뮤테이션 | FAIL 한 가드 |
|---|---|
| 템플릿에 `location = /api/bypass { auth_basic off; }` 주입 | D-1-b |
| `Host $http_host` → `$host` 환원 | D-2-b (+ A-27 이 행위로) |
| backend `ports` 를 `8000:8000` 로 되돌림(Phase 2 가드 파일 존재 상태) | D-5-c |
| backend `environment` 에 `EXTRA=1` 추가 | D-5-b |
| `parse_allowed_origins` 의 `*` 필터 제거 | D-13 + A-25 |
| `_client_ip` 를 `scope["client"]` 단독으로 환원 | D-14 + A-26 |
| vite 에서 `Origin: apiTarget` 삭제 | D-9-b |
| vite `X-API-Key` 를 빈 상수로 치환 | D-9 |

### 10.3-b 스위트 결과 (라운드 1 종료 시점)

* cycle243 표적 **74 PASS**(`deploy_assets` 11 · `phase2_assets` 11 · `middleware` 55 중 해당분 · `contract` · `fixture`).
* 프론트엔드 **469 PASS**(68 파일) · `tsc -p tsconfig.node.json --noEmit` 통과(vite 설정 타입).
* 백엔드 전체 **6,235 PASS / 2 FAIL**(10 skipped · 329 xfailed · 12 xpassed, 11분).
  * 실패 2건 = `tests/unit/engine/test_boot_manager_extraction.py::test_boot_calls_preissue_before_token_and_load_config`
    · `test_boot_manager_buy_date_date_object.py::test_boot_recovers_position_with_date_object_buy_date`.
    스택은 `src/db/pg.py:128 AttributeError: 'NoneType' object has no attribute 'acquire'`
    (= 커넥션 풀이 None 인 상태로 boot 경로 진입) + `inquire-balance` 네트워크 재시도.
  * **cycle243 변경과 무관하다는 근거**: (a) 두 파일 단독 실행 **5 PASS** (b) `tests/unit/engine`
    전체 **3,675 PASS / 0 FAIL** (c) `tests/contract` + 해당 2파일 **186 PASS** (d) `tests/integration`
    + 해당 2파일 **272 PASS** (e) **이번에 추가·수정한 파일 전부**(`tests/unit/ast` ·
    `tests/unit/middleware` · 픽스처 테스트) + 해당 2파일 **646 PASS**. 즉 어떤 조합으로도
    재현되지 않고, 라운드 1 의 `src/` 변경은 `src/middleware/api_auth.py` 3개 함수뿐이라
    DB 풀·boot 경로에 접점이 없다. 전체 실행 순서에서만 나타나는 **선행 오염**으로 보이며
    (테스트 수도 종전 6,225 + 신규 12 = 6,237 로 정확히 일치), team-leader 에게 별건으로 인계한다.

### 10.4 라운드 1 이후에도 남는 것

* **L1(TLS 부재)** 은 그대로다. 이 라운드의 어떤 시정도 평문 경로 관찰자를 막지 못한다 — 후속 F1.
* **L4(nginx 실기동 자동 가드 부재)** 도 그대로다. 이번 실측은 전부 **일회성 수동 검증**이고
  리포에 남는 것은 텍스트·AST 가드뿐이다. `auth_basic off` 같은 우회는 D-1-b 가 텍스트로만 막는다.
* **L10(401 인터셉터 부재)** 는 F6 의 실패를 조용하게 만드는 증폭 요인이었다 — 후속 F4 유지.
* **`API_ALLOWED_ORIGINS` 가 두 통제를 겸한다** — CORS 허가 목록과 CSRF Origin 허용 목록이
  같은 변수 하나다(두 곳이 갈리면 "CORS 는 막는데 CSRF 는 통과" 가 되므로 의도된 공유였다).
  라운드 1 은 와일드카드만 닫았고, "특정 오리진에 CSRF 예외만 주고 credentialed 응답 읽기는
  막는" 세분화는 못 한다. 실사용 소비자가 0이라 지금은 무해 — 필요해지면 분리한다.
* **`ip=` 는 프록시 하나를 신뢰한다** — `X-Real-IP`/`X-Forwarded-For` 는 우리 nginx 가
  `proxy_set_header` 로 치환하므로 :80 경유 요청에서는 위조가 불가능하지만, EC2 루프백
  `:8000` 직결에서는 호출자가 값을 정할 수 있다(로컬 접근뿐이라 수용). `ip_src` 태그가
  그 구분을 남긴다.
* **`ports` 축의 정적 가드 불가능성**: D-6(Phase 2)이 요구하는 값과 Phase 1 의 값이 상반되므로
  단일 정적 단언으로는 양립할 수 없다. D-5-c 의 **짝짓기**가 대안이고, 그마저도
  "Phase 2 가드 파일이 같은 커밋에 있는가" 라는 간접 신호에 의존한다(P1-1b 육안 게이트 동반 이유).

---

## 10.5 적대적 검증 라운드 2 — 확증 결함과 시정 (backend-dev + tdd-engineer, 2026-09-03)

라운드 2 는 **라운드 1 이 "시정 완료" 로 선언한 항목의 실제 상태**를 diff·grep 으로 되짚었다.
3건이 MEDIUM 으로 확증됐고 전부 "본문 어딘가에는 적었지만 운영자가 실제로 손대는 자리에는
반영되지 않은" 형태였다 — 그래서 시정과 함께 **텍스트 회귀 가드 3건(D-15~D-17)** 을 신설했다.

### 10.5.1 확증 (실측 근거)

| # | 확증 내용 | 실측 |
|---|---|---|
| **R2-1** (MEDIUM) | **F7 미종결 — 워크리스트 등재 없음, 그런데 §7 상태란은 "갱신 완료"(false green)** | `git diff _workspace/00_URGENT_WORKLIST.md` = **5 insertions / 2 deletions**, 내용 전부 `-u "<USER>:<PASS>"` 치환. `grep -n cycle243` → **771행 1건**(curl 주석). `grep -nE "HTTPS|TLS"` → cycle243 관련 **0건**. 루트 `CLAUDE.md` 는 이 파일을 "다른 작업을 시작하기 전에 먼저 읽는다" 로 지정 ⇒ 최대 잔여 위험(L1 TLS 부재 · 후속 F2 SG 80 제한)이 **아카이브될 Red 문서에만** 존재. 나머지 6종(README·monday_0831_guide·CLAUDE.md·routes/CLAUDE.md·frontend/CLAUDE.md·architecture.md)은 실제로 정확히 갱신됨을 확인(frontend/CLAUDE.md 의 인터셉터 드리프트 시정은 `frontend/src/api/client.ts` 전문 확인으로 사실 검증 — 인터셉터 0건) |
| **R2-2** (MEDIUM) | **F11 미종결 — 상시 추적되는 유일한 htpasswd 레시피에 argv 형태 잔존** | `grep -rn "openssl passwd"` 전수 4곳: `.gitignore:43` = `printf '%s:%s\n' "<USER>" "$(openssl passwd -apr1 '<PASSWORD>')"` **argv 잔존** / 명세 §6.1:341 = `-stdin`(시정형) / §10.1 F11 = argv 를 결함으로 확증 / §10.2 F11 = `-stdin` + `read -s` 로 시정 선언. 루트 `CLAUDE.md:225` 는 권한(755/644)만 적고 생성 명령이 없어 **`.gitignore` 가 유일 잔존 경로** ⇒ 키 회전(F5) 시점에 운영자가 복사할 확률이 가장 높은 줄 |
| **R2-3** (MEDIUM) | **비상 절차서의 401 분기에 복구 조치가 없고, 안심 문구가 그 문서 자신의 전제와 모순** | `monday_0831_guide.md:52-56` = 진단(`grep -c '^API_AUTH_KEY=…'`)만 지시하고 "매매 엔진 자체는 정상이므로 15:20 자동 청산 경로는 살아 있다" 로 종료 — **다음 조치 문장 없음**. 그런데 이 가이드가 존재하는 이유가 그 자동 청산의 실패(APBK0400, 같은 파일 :26 "자동 대기 금지")다. 게다가 명세 §6.3:410 은 "롤백은 `git revert` 후 재배포뿐" 이라 단정 — 실제 최단 복구는 `.env` 키 한 줄 + `docker compose … up -d`(수십 초)이고, 그 경로의 실재는 §10.1 F1 실측(`.env` 변경 → `Container backend Recreated`)과 본 라운드 probe(`.env` 의 키가 컨테이너에 `KEY_LEN=44` 로 전달)로 확인됨 ⇒ 사고 당일 운영자를 5~10분 CI+Deploy 왕복으로 몰아넣는 지시 |

### 10.5.2 시정

| # | 무엇을 | 어디를 |
|---|---|---|
| R2-1 | 워크리스트에 **`## 🔐 cycle243 · API 인증` 절 신설** — 배포 전 노출 실측(무인증 200) · Phase 1/2 표(창·선행 조건·Phase 1 무재시작 전제) · 포트별 인증 차이 · L3 위험 창 · **남는 위험(L1 TLS 최우선 · L2/L4/L7/L8/L10)** · **후속 F1~F9 표**. 명세 §7 상태란의 false green 도 정정(라운드 1 이 무엇을 못 했는지 명시) | `_workspace/00_URGENT_WORKLIST.md`(§ 신설) · 명세 §7 |
| R2-2 | `.gitignore` 레시피를 **`read -s` + `printf '%s' "$AUTH_PASS" \| openssl passwd -apr1 -stdin`** 로 교체 + `unset AUTH_PASS` + 755/644 권한 사유(uid 101 vs 1000, §10.1 F2) 병기 | `.gitignore` |
| R2-3 | 401 분기를 **진단 → 복구 2단계**로 재작성: ①`grep -c` 가 1 이면 호출 쪽 원인(포트별 인증 혼동) 분기, 0 이면 ②`.env` 키 주입 + `docker compose -f docker-compose.prod.yml up -d`(수십 초). **재생성 = 장중 1~5분 tick blind(cycle232 D6)** 라는 교환 명시. 모순 안심 문구 삭제하고 "자동 청산은 폴백으로만 취급" 으로 교체. 명세 §6.3 의 롤백 단정도 **1차 조치 / 기능 철회** 2층으로 정정 | `_workspace/monday_0831_guide.md` · 명세 §6.3(P2-0 주석 · 롤백 문단) |

### 10.5.3 신설 회귀 가드 — `tests/unit/ast/test_cycle243_ops_docs.py`

배포 자산이 아니라 **운영 문서**를 보므로 D 그룹과 파일을 나눴다(Phase 1/2 커밋 화이트리스트와
무관하게 항상 커밋된다).

| 가드 | 무엇을 고정 |
|---|---|
| **D-15** | `git grep "openssl passwd"`(추적 파일, `tests/` 제외)의 **모든** 히트가 `-stdin` 이고 `openssl passwd` 뒤 인용 리터럴 인자가 0 — argv 비밀 레시피의 부활을 파일 무관하게 차단 |
| **D-16** | 워크리스트에 `## … cycle243 …` 절이 존재 ∧ 그 절 본문에 `TLS` · `HTTPS` · `보안그룹` · `Phase 2` ∧ 후속 `F1`~`F5` 등재 — §7 "갱신 완료" 의 근거가 실재하도록 |
| **D-17** | 비상 가이드의 `401 이 오면` 블록에 `>> .env` ∧ `docker-compose.prod.yml up -d` ∧ `tick blind` 가 있고, 공백을 접은 전문에 `15:20 자동 청산 경로는 살아 있다` 가 **0건** — 진단만 하고 끝나는 형태와 모순 안심 문구의 부활을 동시에 차단 |

### 10.5.4 뮤테이션 실증

| 뮤테이션 | FAIL 한 가드 |
|---|---|
| `.gitignore` 레시피를 `openssl passwd -apr1 '<PASSWORD>'`(argv) 로 환원 | D-15 |
| `.gitignore` 레시피에서 `-stdin` 만 제거(파이프 유지) | D-15 |
| 워크리스트의 cycle243 절 삭제 | D-16 |
| 워크리스트 cycle243 절에서 후속 표(F1~F9)만 삭제 | D-16 |
| 401 분기의 복구 명령 블록 삭제(진단만 남김) | D-17 |
| 401 분기에 "15:20 자동 청산 경로는 살아 있다" 재삽입 | D-17 |

### 10.5.5 라운드 2 이후에도 남는 것

* **L1(TLS 부재)** 그대로 — 이 라운드는 그 위험을 *표준 문서에 등재*했을 뿐 해소하지 않았다(F1).
* `README.md:162` 의 `curl -H "X-API-Key: $API_AUTH_KEY"` 는 **argv 노출이 맞지만 유지**했다 —
  로컬 dev(localhost·단일 사용자 머신) 대상이고, 여기에 mktemp curl-config 3줄을 넣으면
  quickstart 가독성이 손해다. 공유 호스트에서는 `monday_0831_guide.md` 의 curl config 형태를
  쓴다. **의식적 수용이지 누락이 아니다**(D-15 는 `openssl passwd` 축만 본다).
* **D-15~D-17 은 텍스트 가드다** — 문구가 살아 있는지만 보고 절차가 실제로 동작하는지는
  못 본다(L4 와 같은 한계). 복구 명령의 실검증은 Phase 2 배포 당일 수동 1회.
