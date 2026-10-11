# 청산 AI 섀도 기록 — 설계 메모 (2026-10-11)

- 사용자 결정(2026-10-11 원문): 「2. (나) - 히스토리도 남겨두자.」 — (나) = 멀티데이 보유분 일 1회 섀도 기록만(backend 밖 · 확정 일봉 · 반사실 = AI 가 청산이라 한 다음 날 시가 매도 vs 실제 청산가)
- 근거 = `_workspace/analysis/llm_gate_eval_20261011/result.md` §5(형태 C 만 허용 · A 손절 유예 기각 · B 청산 앞당김 보류)
- 이 메모는 **설계만** 한다. 코드 0줄. 매매 행위 0 — 기록만 하고 어떤 청산 경로에도 들어가지 않는다
- 작성 = domain-expert. 채택 여부는 team-leader·사용자가 정한다
- 🟥 표시 = 사용자 결정 필요 · 🟧 표시 = 사람이 EC2 에서 해야 하는 일

---

## 0. 요지

| 항목 | 권고 |
|---|---|
| 자리 | **새 워커 컨테이너 `llm_worker`**(src 밖 `llm_worker/`, 자기 배포 축 `llm`). 지금은 청산 섀도 작업 **하나만** 담는다. 이름은 15장 1단계 계획의 이름을 그대로 써서, 나중에 매수평가 큐가 같은 컨테이너·같은 비밀 파일·같은 축으로 들어올 수 있게 한다 |
| 대상 | G1(`/api/balance/exit-lines`)에 보이는 보유 중 **전략 허용 목록 5개**(`donchian_swing`·`kojiro`·`vcp_breakout`·`bull_flag_breakout`·`etf_trend`) ∧ 매수일 ≤ 입력 봉 날짜 |
| 시각 | **거래일 아침 08:15 KST 1회**(재시도 08:35·08:55). 전일 봉이 확정된 뒤다(부팅 07:45 → `daily_bar_finalize` 가 보유 종목을 먼저 덮는다). 09:00 시가 전에 끝난다 |
| 입력 | 확정 일봉(`stock_master_daily`, D−1 까지) + G1 보유 스냅샷(손절선·목표가·진입 ATR·무장·최고가) + G0 전략 파라미터 |
| 출력 | `{"action":"hold"|"exit","exit_score":1~100,"rationale","key_risks","invalidations"}`. 「모르면 보유」 — 현 청산 규칙이 기본값이다 |
| 저장 | 새 표 `exit_ai_evaluations`(평가 1행 = 포지션 × 입력 봉 날짜) + `exit_ai_runs`(하루 1행 — 「대상 없음」 과 「워커가 안 돌았다」 를 가른다). migration 050, 가산형. **영구 보존**(DELETE 권한 자체를 주지 않는다) |
| 반사실 | 포지션 단위. 첫 `exit` 날의 다음 거래일 시가(−0.15% 미끄러짐) vs 그 뒤 실제 매도 평균가. 비교 대상은 0 이 아니라 **무작위 날짜 청산**이다 |
| 화면 | 1단계 **없음**. 실험 기간 동안 보유 화면에 AI 의견을 띄우지 않는다(사람이 보고 손으로 팔면 실험이 오염된다) |
| 끄기 | `docker compose stop llm_worker` 한 줄(매매 영향 0). 상시 스위치는 compose 환경 `EXIT_AI_MODE=off`(워커만 재생성) |
| 비용 | 보유 ~10건 × 21거래일 ≈ 월 210회. `gpt-6-luna` 실측 단가로 **월 $0.2 안팎**, 비싼 쪽 모델이어도 월 $1.5 안팎 |
| 판정 시점 | 신호가 있는 포지션 30개에서 중간 판정(대략 2~3개월), 100개 또는 2027-06 에서 최종 판정 |

---

## 1. 어디서 도는가

### 1.1 선택지

| 안 | 내용 | 장점 | 대가 |
|---|---|---|---|
| (a) `journal_worker` 에 작업 추가 | 15초 회전 루프에 「하루 1회 청산 평가」 를 끼운다 | 컨테이너가 늘지 않는다. compose 를 안 고치면 첫 배포가 `journal` 축 선택 배포(backend 무접촉)로 끝난다 | ① 격리 계약이 깨진다 — 읽는 환경변수가 둘뿐이라는 규약(`test_jw_isolation.py` I2)에 OpenAI 키가 들어간다 ② 동시 실행 금지 규약이라 LLM 10건 × 10초 ≈ 2분 동안 거래일지 회전이 멈춘다(08:15 = NXT 프리장 실매매 구간의 기록이 밀린다) ③ 「일어난 일을 받아 적는」 워커가 「새 판단을 만드는」 일을 하게 된다. 청산 평가 쪽 실패(모델 오류·메모리)가 거래일지까지 같이 죽인다 ④ `mem_limit: 160m` 안에 openai SDK 를 더 넣어야 한다 |
| **(b) 새 `llm_worker` 컨테이너 — 권고** | `llm_worker/`(패키지 `lw`)에 청산 섀도 작업 하나만. 15장 1단계 계획의 이름과 자리를 쓴다 | 격리가 깨끗하다(거래일지와 운명을 같이하지 않는다). 비밀값(OpenAI 키)이 이 컨테이너 하나에만 있다. 나중 매수평가 큐(cycle279)가 **새 컨테이너·새 축·새 비밀 파일 없이** 들어올 수 있다 | 첫 배포 1회가 **full**(compose 본체·`tools/deploy/` 를 고치므로 backend 재시작) — 장외 창에서만. 파일 수가 (a) 보다 많다 |
| (c) 클라우드 루틴(schedule) | 평일 아침 Claude 루틴이 리포터 키로 읽고 결과를 POST | EC2 자원 0 | 결과를 쓰려면 backend 에 쓰기 경로(새 POST)가 생긴다 = `src/` 변경 · 리포터 스코프 확장. 루틴 실행 시각이 흔들리면 09:00 전 완료 보장이 없다. 운영 DB 확정 봉을 직접 못 읽는다 |

**권고 = (b).** 이유 한 줄: 「판단을 새로 만드는 일」 과 「외부 API 비밀값」 을 거래일지 관찰자에게 얹으면 두 기능이 함께 죽고 함께 위험해진다. (a) 의 유일한 이점(첫 배포가 backend 무접촉)은 장외 창 full 배포 1회로 갚을 수 있는 크기다.

🟥 **결정 D-1** — (b) 새 `llm_worker` 컨테이너(권고) / (a) `journal_worker` 확장.
🟥 **결정 D-2** — 이름: `llm_worker`(권고 — 15장 1단계와 합칠 자리를 미리 연다) / `exit_ai_worker`(청산 섀도 전용, 매수평가 분리는 나중에 다시 정한다). 어느 쪽이든 **이번에 매수평가 큐는 만들지 않는다**(cycle279 미착수 상태 그대로).

### 1.2 (b) 의 격리 규약 — `journal_worker` 선례를 그대로 따른다

- `src` import 0 · `KIS_` 변수 0 · 메인 `.env` 0 · 체결통보·WebSocket 0 · KIS REST 0.
- 읽는 환경변수 = `LLM_DATABASE_URL`·`OPENAI_API_KEY`(둘 다 `secrets/llm_worker.env`) · `API_REPORTER_KEY`(compose `environment:`) · `EXIT_AI_MODE`·`EXIT_AI_MODEL`·`TZ`(compose `environment:`, 비밀 아님). 이 목록 밖 변수를 읽으면 테스트가 붉어진다(I2 동형).
- HTTP 허용 경로 = G0 `GET /api/trading/status?include=system,holdings,strategies` · G1 `GET /api/balance/exit-lines` 둘뿐(화이트리스트 `lw/config.py`). 리포터 키는 GET 전체가 열려 있지만 코드가 둘만 부른다.
- 동시 요청 0 — LLM 호출도 한 건씩 순차. 하루 한 번이라 속도는 문제가 아니다.
- DB = 자동커밋 단문만. 트랜잭션 금지(배포 때 도는 `ALTER TABLE trade_history` 뒤에 줄을 세우지 않는다).
- 이미지 = non-root(`llm`, uid 1000) · 코드 root 소유 · `.dockerignore` 로 tests·ops 제외.
- 볼륨 = **없음**(로그 파일도 읽지 않는다 — 필요한 것은 G1 과 DB 에 다 있다).
- `ports:` 없음.

### 1.3 배포 축

- `tools/deploy/compose_up_changed.sh` 에 `LLM_RE='^llm_worker/'` 한 줄 + 분류 블록 `if` 하나(서비스 `llm_worker`). 축 순서 = `frontend` · `macro` · `journal` · `llm`.
- 이 변경과 compose 블록 추가는 `BACKEND_RE`(`tools/deploy/`·`docker-compose.prod.yml`)라 **첫 배포는 full** 이다. 그 뒤 워커 코드만 고치는 배포는 `llm` 선택 배포(backend 무접촉)다.
- 서비스는 `docker-compose.prod.yml` **본체**에 둔다(오버레이에만 두면 `--remove-orphans` 가 지운다 — 15.7).
- 첫 배포 창 = 장외(15:30~16:00 · 21:35~익일 07:45 · 주말). 지금 보유 10건이 있으므로 09:00~15:30 push 금지(D6). 20:00~21:35 도 금지(D8).

### 1.4 메모리·디스크 (2026-10-11 EC2 실측, 읽기만)

| 항목 | 값 |
|---|---|
| 메모리 | 총 1,835MB · 사용 811 · **available 1,024MB** · 스왑 4GB 중 162MB 사용 |
| 컨테이너 | backend 94MB · macro 35MB · journal_worker 25MB / 160MB · frontend 5MB |
| 디스크 `/` | 19G 중 15G 사용(**82%**, 남은 3.4G) |

- 권고 상한 = `mem_limit: 192m` · `cpus: 0.25` · 로그 `10m × 3`. 상한은 **첫 배포에 넣는다**(나중에 고치면 그 배포도 full).
- 런타임 여유는 충분하다. 위험은 빌드다(09-18 동시 빌드 OOM 사고). `COMPOSE_PARALLEL_LIMIT=1` 이 이미 걸려 있어 첫 full 배포는 backend → llm_worker 를 차례로 빌드한다. 배포 직전 `free -m`·`df -h` 확인(메모리 규약).
- 디스크 82% 는 새 이미지(약 200~300MB)를 받을 수는 있지만 여유가 크지 않다. 🟧 첫 배포 전 `docker image prune` 으로 매달린 이미지를 정리할지 운영자가 판단한다.

### 1.5 DB 역할 — `llm_worker` 전용 (`llm_worker/ops/role.sql`, 마이그레이션 아님)

`journal_worker/ops/role.sql` 과 같은 꼴.

| 표 | 권한 | 왜 |
|---|---|---|
| `stock_master_daily` | SELECT | 확정 일봉·`updated_at`(잠정 판정)·다음 날 시가 |
| `trade_history` | SELECT | 실제 매도 체결가·수량·시각 |
| `trade_journal_orders` | SELECT | 매도 사유(`reason_code`) — 「AI 보유 → 손절」 집계 |
| `exit_ai_evaluations` · `exit_ai_runs` | SELECT · INSERT · UPDATE (**DELETE 없음**) | 기록·사후 채움. 사용자 「히스토리도 남겨두자」 를 권한으로 박는다 |
| 시퀀스 2개 | USAGE | BIGSERIAL |
| 그 밖(`positions`·`system_config`·`strategy_config`·`kis_quote_accounts`·`llm_buy_evaluations` …) | 0 | 보유 목록은 G1 로만 읽는다 |

고정값 = `statement_timeout=5s` · `lock_timeout=1s` · `idle_in_transaction_session_timeout=5s`. 풀 `min_size=1, max_size=2`.

`positions` 를 열지 않는 이유: 손절선·무장·진입 ATR 은 엔진 메모리에만 있고 G1 이 유일한 창이다(15.8). DB `positions` 로는 그 칸을 못 채우고, 권한만 넓어진다.

---

## 2. 입력

### 2.1 대상 — 어떤 보유를 평가하나

**판정 규칙(사전 등록)**: G1 의 각 item 중 아래를 모두 만족하는 것.

1. `strategy_id ∈ EXIT_AI_STRATEGIES = {donchian_swing, kojiro, vcp_breakout, bull_flag_breakout, etf_trend}`
2. `buy_date ≤ bar_date`(입력 마지막 확정 봉 날짜) — 즉 **최소 한 번 장 마감을 넘긴 보유**
3. `quantity > 0`

명부 칸으로 판정하지 않는 이유 — `close_at_1520` 은 「당일 청산 전략」 표식이 아니다. `donchian_swing`·`etf_trend` 는 `close_at_1520=True` 인데 멀티데이다(15:20 에 「그날 끝낼 종목만」 돌려준다 — `strategies/CLAUDE.md` 「멀티데이 보유 전략」). 반대로 `bull_flag_breakout` 은 `Position._MULTIDAY_STRATEGIES` 에 없지만 `max_hold_days`(5영업일) 동안 들고 간다. 그래서 **명시 허용 목록**을 둔다. 워커는 `src` 를 import 할 수 없으므로 목록은 워커 상수이고, 정합은 backend 쪽 테스트가 잡는다(9장 C2 — `tests/unit/` 에서 워커 상수 파일을 읽어 `STRATEGY_MANIFEST` 의 id 와 대조).

| 전략 | 넣나 | 이유 |
|---|---|---|
| `donchian_swing` · `kojiro` · `vcp_breakout` | 넣는다 | 멀티데이 추세 보유. 보유 기간이 길어 「언제 내릴까」 판단의 틈이 있다 |
| `bull_flag_breakout` | 넣는다 | 최대 5영업일 보유. 표본의 큰 몫(09월 왕복 17건 중 15건이 멀티데이) |
| `etf_trend` | 넣는다(층 분리) | 멀티데이. 지금은 섀도라 보유 0 — 실매수로 바뀌면 자동으로 들어온다. 분석은 전략 층으로 가른다 |
| `volatility_breakout` | 뺀다 | 15:20 전량 청산. 아침 평가 시점에 보유가 없다 |
| `momentum` · `long_tail_volatility` | 뺀다 | 넘긴 보유는 다음 날 09:00 KRX 시장가 청산(또는 갭 트레일링)이 기계적으로 정해져 있다. AI 의 「다음 날 시가 매도」 가 실제 행동과 거의 같아 반사실 차이가 0 에 몰린다 — 표본만 희석한다. **근거 문서 §5.3 은 「LTV 상한가 익일 보유」 를 대상에 넣었는데, 이 메모는 이 이유로 뺀다** |
| `ndx2x_riskoff` | 뺀다 | 손절 없는 레짐 보유(미국 지수 규칙). 종목 일봉만 보는 AI 의견은 그 규칙과 다른 질문이다 |

🟥 **결정 D-3** — 대상 목록 5개(권고) / 근거 문서대로 LTV 상한가 익일 보유까지(6개).

### 2.2 보유 목록 출처 — G1 (권고) vs DB `positions`

| | G1 `/api/balance/exit-lines` | DB `positions` |
|---|---|---|
| 손절선 `stop_price`·`stop_source` | 있음 | 없음 |
| 목표가·진입 ATR·donchian 무장(`kk_armed`·`kk_arm_price`)·`high_since_buy` | 있음 | 없음(일부만) |
| 매수 주문번호 `order_no`·`buy_date`·`quantity`·`buy_price` | 있음 | 있음 |
| 가용 시간 | 엔진 부팅(07:45) ~ 21:30 정산(`_reset_daily_state` 가 메모리 보유를 비운다) | 항상 |
| 권한 | 리포터 키 GET(이미 있음) | 새 GRANT 필요 |

**권고 = G1.** 08:15 는 부팅 뒤라 G1 이 살아 있다. G1 이 `running=false` 이거나 실패하면 그날은 평가하지 않고 `exit_ai_runs` 에 이유를 적는다(DB 로 대체하지 않는다 — 손절선 없이 평가하면 행마다 입력이 달라져 표본이 갈린다).

G0 에서는 전략별 `params` 만 쓴다(BFB `max_hold_days`, donchian `kk_time_exit_bars`·`kk_time_exit_min_r`, kojiro 샹들리에 배수 등 — 남은 보유 기한 계산용).

### 2.3 확정 일봉

- 출처 = `stock_master_daily`(KIS 일봉, 시장 `J` = KRX). 60봉 읽고 프롬프트에는 최근 30봉(매수평가와 같은 깊이).
- **확정 판정** = 입력 마지막 봉(`bar_date`)의 `updated_at ≥ 오늘 06:00 KST`(`daily_bar_finalize` 의 헤드 판정과 같은 규칙). 그 전 봉은 `updated_at ≥ (bas_dd+1일) 06:00`.
- 아직 잠정이면 그 종목은 08:35·08:55 재시도. 끝까지 잠정이면 `result=skipped reason=provisional_bar` 행을 남기고 **LLM 을 부르지 않는다**(잠정 종가는 19:59 애프터 체결가라 정규장 종가와 다르다 — cycle386).
- `bar_date` = `069500`(KODEX 200)의 `max(bas_dd) < 오늘` — 휴장일 달력 대신 쓴다(`daily_bar_finalize` 와 같은 방식). 종목의 마지막 봉이 `bar_date` 와 다르면(거래정지 등) `skipped reason=stale_bar`.
- 오늘 봉은 절대 읽지 않는다(`bas_dd < 오늘` 조건을 SQL 에 박는다 — 미래 정보 차단).

### 2.4 포지션 맥락 (프롬프트 칸)

| 칸 | 출처 |
|---|---|
| `strategy_id` · 전략 청산 구조 설명(고정 문구) | 워커 상수 — `strategies/CLAUDE.md` 카탈로그에서 옮긴다 |
| `buy_price_won` · `buy_date` · `bars_held`(매수일 포함 보유 봉 수, `069500` 봉으로 센다) | G1 + DB |
| `close_won`(bar_date 종가) · `unrealized_pct` | DB + G1 |
| `mfe_pct` · `mae_pct`(매수 뒤 확정 봉 고가·저가 기준) | DB |
| `stop_price_won` · `stop_source` · `stop_dist_pct`(종가 대비) · `stop_dist_atr` | G1 |
| `target_price_won`(있으면) · `entry_atr` · `kk_armed` · `kk_arm_price` | G1 |
| `time_exit_bars_left`(BFB·donchian 만) | G0 params + `bars_held` |
| 지표(EMA 5/20/60 · RSI14 · MACD · ATR14 · HV20 · 20일 채널 위치 · 연속 양/음봉) | 일봉 → `lw/features.py` |

종목명은 **넣지 않는다**(입력 오염 차단 — 매수평가는 `sanitize_text` 로 거른다. 여기서는 아예 뺀다).

---

## 3. 언제

### 3.1 선택지

| 안 | 시각 | 장점 | 대가 |
|---|---|---|---|
| **A. 다음 거래일 아침 — 권고** | D 일 08:15(재시도 08:35·08:55), 입력 = D−1 확정 봉 | 입력이 확정값이라 재현된다. 「밤사이 판단 → 시가에 집행」 이라는 반사실 문장과 시점이 정확히 맞는다(`act_date` = 실행 당일 = D) | 08:00~09:00 은 NXT 프리장 실매매 구간이다. 다만 워커가 backend 에 하는 일은 G0·G1 각 1회(G1 은 5초 캐시)뿐이고, 무거운 일(LLM)은 backend 밖이다 |
| B. 전날 밤 20:30 적재 직후 | D−1 일 20:40, 입력 = D−1 잠정 봉 | 판단이 하룻밤 일찍 나온다 | 종가·고가·저가가 잠정(애프터 혼입)이다. 기록된 입력 스냅샷이 다음 날 아침의 확정값과 달라 재현이 깨진다. 20:00~21:35 는 자문·스냅샷·적재·정산이 몰린 창이다. G1 은 21:30 에 비워진다 |
| C. 장 마감 직후 15:40 | D−1 일 15:40, 입력 = 정규장 종가 | 확정에 가장 빠르다 | DB 에 15:30 정규장 종가가 없다(20:30 적재 전). 워커는 KIS 를 부를 수 없다 → 성립하지 않는다 |

**권고 = A.** 사용자 조건 「확정 일봉」 을 그대로 지키는 유일한 시점이다.

### 3.2 아침 실행 순서 (한 번의 실행 = 하루)

1. 07:45 엔진 부팅 → `daily_bar_finalize` 가 ①`069500` ②DB `positions` 보유 종목 ③나머지 순으로 전일 봉을 확정(부팅 예산 90초). 보유 종목이 앞줄이라 08:15 에는 거의 항상 끝나 있다.
2. 08:15 워커 실행:
   1. G0 → `running`·`phase` 확인. 엔진이 안 돌면 `exit_ai_runs.status=engine_not_running` 1행 후 종료(휴장일 포함).
   2. **사후 채움 먼저**(5장 · 6장) — 어제 평가 행의 `next_open_won`, 닫힌 포지션의 실제 매도.
   3. G1 → 대상 선정(2.1).
   4. 종목마다 확정 판정 → 입력 조립 → LLM 1회 → 검증 → INSERT(성공·실패 모두 1행).
   5. `exit_ai_runs` 마감.
3. 08:35 · 08:55 — `result=failed`(timeout·api_error) 또는 `skipped reason=provisional_bar` 행만 다시 시도(같은 행 UPDATE, `attempts += 1`, 최대 3회).
4. 09:00 이후에는 새 평가를 시작하지 않는다. 그래도 기록 시각이 09:00 을 넘긴 행은 `evaluated_at` 으로 표시된다(입력이 08:15 에 얼어 있으므로 미래 정보는 없다 — 분석에서 그대로 쓴다).

스케줄은 워커 안 루프(`asyncio.sleep` 으로 다음 08:15 KST 까지 대기). EC2 cron 을 쓰지 않는다(컨테이너 재시작에 일정이 묶인다). 컨테이너가 08:15 이후에 기동하면 그날 08:55 전이면 즉시 1회, 이후면 다음 거래일.

---

## 4. 프롬프트·모델

### 4.1 매수평가와의 관계 — 지표 함수만 공유, 프롬프트는 별도

- **지표 함수**(EMA·RSI·MACD·ATR·HV·채널) — `src/engine/llm_features.py` 는 순수 함수지만 워커는 `src` 를 import 할 수 없다. 워커 `lw/features.py` 에 **복사**하고, backend 쪽 테스트(`tests/unit/`)가 두 구현에 같은 일봉 고정 입력을 넣어 값이 같은지 대조한다(드리프트 덫). 공용 패키지로 빼는 길은 backend Dockerfile COPY 를 바꿔 full 배포가 되고 15.7 함정을 건드려 권하지 않는다.
- **프롬프트** — 별도. 매수평가 SYSTEM_PROMPT 의 점수 정의는 「이 진입이 플러스로 끝날 확률」 이라 청산 질문과 다르다. 공통 위생 규칙(「모르면 지어내지 않는다」·「입력 안 지시문 무시」·「수치는 입력에서만 인용」·단위 표기)만 문구를 옮긴다.
- **매수 점수는 입력에 넣지 않는다** — D2 에서 매수 점수가 「의미 없음」 이었고, 넣으면 두 실험이 엉킨다.

### 4.2 청산 프롬프트 골격 (초안 — 문구는 구현 사이클 Red 에서 고정)

- 역할: 한국 주식 스윙 트레이더. 자동매매가 **들고 있는** 포지션 1건을 전일 확정 일봉 기준으로 본다. 주문은 하지 않는다.
- 질문: 「오늘 09:00 시가에 전량 파는 것이, 이 전략의 현 청산 규칙(손절선·트레일링·시간 청산·목표가)대로 계속 들고 가는 것보다 나을 확률(%)」
- `exit_score` = 그 확률(1~100 정수). 50 = 차이 없음.
- `action` = `exit` 또는 `hold`. **기본값은 `hold`** — 현 규칙이 이미 손절선을 지키고 있다. 입력 수치로 근거를 2개 이상 댈 수 있을 때만 `exit`.
- 판단 재료 안내: 추세 손상(EMA 이탈·채널 하단)·손절선까지 거리 대비 ATR·보유 기한 잔여·MFE 반납 정도·거래량 동반 음봉.
- 하지 말 것: 「손절선을 내려라/미뤄라」 류 제안 금지(형태 A 차단). 수익 중이라는 이유만으로 `exit` 금지(추세 전략의 큰 꼬리를 자르는 쪽 편향 — 근거 문서 §5.2 B②).
- 입력에 없는 것(장중 분봉·호가·뉴스·공시·수급·업종·지수)을 명시하고, 그것을 추측해 판단하지 말라고 적는다.

출력 계약(JSON 하나):

```json
{"action": "hold" | "exit",
 "exit_score": 1~100 정수,
 "rationale": "한국어 120자 이내, 입력 수치 2개 이상 인용",
 "key_risks": ["40자 이내", ...],       // 1~3개
 "invalidations": ["40자 이내", ...]}   // 1~2개
```

검증(클램프 금지 — 매수평가 규약 그대로): 범위 밖·타입 오류·키 누락 = `schema_error`. `action=exit ∧ exit_score<50` 또는 `action=hold ∧ exit_score>50` 은 **버리지 않고** `inconsistent=true` 로 기록(주 지표는 `action`, 보조 지표는 `exit_score` 순위라 둘 다 필요하다).

실패 어휘(`reason`) = 매수평가 10종에서 그대로 쓸 수 있는 것 + 청산 전용 둘: `timeout`·`api_error`·`parse_error`·`schema_error`·`no_bars`·`no_key`·`cap_exceeded`·`disabled_model`·`payload_error`·`truncated` + **`provisional_bar`·`stale_bar`**(`skipped`).

### 4.3 모델 설정

- 워커 자체 설정 `EXIT_AI_MODEL`(compose `environment:`, 비밀 아님). 기본값 = 지금 매수평가 기본값과 같은 `gpt-6-luna`.
- **매수평가 설정 키를 따라가지 않는다.** cycle445 가 매수평가 모델 위치를 정리 중인데, 그 값이 바뀔 때 청산 실험의 모델이 조용히 같이 바뀌면 한 실험 안에 모델이 섞인다(D2 에서 한 `prompt_version` 키에 두 모델이 섞인 다섯 키를 확인했다 — 같은 실수). 실험 기간 동안 모델은 고정이고, 바꾸면 새 층이 시작된다.
- `prompt_version` = `exit-v1-{model}-{sha8(SYSTEM 문구 + 전략 설명 + 출력 계약)}` — **모델명을 키에 넣는다**(cycle445 D7 과 같은 방향).
- `max_completion_tokens = 2000`(추론 모델 출력 한도 소진 함정 — 매수평가 09-11 실측), `response_format=json_object`, 호출 타임아웃 30초, SDK 재시도 0(`max_retries=0`) — 재시도는 08:35·08:55 패스가 한다.

🟥 **결정 D-4** — 모델: `gpt-6-luna`(권고 — 싸고 현 매수평가와 같다) / 다른 모델(cycle445 D8 에서 검토 중인 `gpt-6.1-sol` 등). 정하면 실험 끝까지 고정.

### 4.4 호출 수·비용

| 항목 | 값 |
|---|---|
| 지금 대상 보유 | 10건(2026-10-11 DB `positions`: donchian 2 · kojiro 6 · VCP 2) |
| 호출 | 하루 ≈ 보유 수(재시도 포함 최대 3배). 월 ≈ 200~250회 |
| 토큰 | 매수평가 실측 평균 입력 ≈ 2,800 · 출력 ≈ 600~1,000. 청산은 포지션 칸이 늘어 입력 ≈ 3,500 예상 |
| 비용 | `gpt-6-luna` 매수평가 실측 ≈ $0.0008/회 → **월 $0.2 안팎**. 비싼 모델(`gpt-5.6-luna` 급 ≈ $0.0064/회)이어도 월 $1.5 안팎 |
| 상한 | `EXIT_AI_DAILY_CAP = 40`회/일(초과분은 `failed reason=cap_exceeded` 행만) |

비용 추정은 매수평가와 같은 단가표 기준이고 청구서 대조 전이다.

### 4.5 OpenAI 키 전달

- 메인 `.env` 금지. **`~/auto_stock/secrets/llm_worker.env`**(git 밖, 권한 600·소유 ubuntu)에 `LLM_DATABASE_URL=` · `OPENAI_API_KEY=` 두 줄.
- 권고: **OpenAI 에서 이 워커 전용 프로젝트 키를 새로 발급**하고 월 사용 한도(예 $5)를 건다. 메인 키를 복사하면 사용량이 섞이고, 이 컨테이너가 뚫렸을 때 메인 AI 기능(20:00 자문·매수평가)까지 같은 키를 돌려야 한다.
- 🟧 compose `env_file` 이 가리키는 파일이 없으면 **compose 명령 전체가 실패**한다(journal_worker 선례 — `full`·`none` 배포의 `up` 이 아무것도 만들지 않는다). 그래서 **배포 전에** 사람이 만든다.
- 워커는 키를 로그에 남기지 않는다(테스트: 로그 출력·예외 메시지에 키 문자열 0).

🟥 **결정 D-5** — 키: 전용 프로젝트 키 + 월 한도(권고) / 메인 키 복사.

---

## 5. 이력 저장 — migration `050_exit_ai_evaluations.sql`

가산형(신규 테이블 2개 + 인덱스). `IF NOT EXISTS` 필수(deploy.yml 이 매 push 마다 전 마이그레이션을 재적용한다 — 043 주석). `pg_harness` 는 디렉터리를 glob 하므로 목록 수정은 필요 없다. 다음 번호가 050 인지는 구현 사이클 착수 때 다시 확인한다(049 가 마지막).

### 5.1 `exit_ai_evaluations` — 평가 1행 = 포지션 × 입력 봉 날짜

| 묶음 | 칸 | 뜻 |
|---|---|---|
| 키 | `id BIGSERIAL PK` · **UNIQUE `(bar_date, strategy_id, ticker, buy_date, buy_order_no)`** | 같은 봉으로 같은 포지션을 두 번 평가하지 않는다(재기동·휴장일 중복 방지). KIS 주문번호는 하루 단위로만 유일해 `buy_date` 가 키에 들어간다 |
| 날짜 | `bar_date DATE NOT NULL`(입력 마지막 확정 봉) · `act_date DATE NOT NULL`(반사실 매도일 = 실행 당일) | |
| 포지션 | `strategy_id` · `ticker` · `buy_date` · `buy_order_no TEXT NOT NULL DEFAULT ''` · `quantity` · `buy_price_won NUMERIC` · `bars_held INT` | G1 스냅샷 |
| 상태 스냅샷 | `close_won` · `unrealized_pct` · `high_since_buy_won` · `mfe_pct` · `mae_pct` · `stop_price_won` · `stop_source` · `stop_dist_pct` · `target_price_won` · `entry_atr NUMERIC` · `kk_armed BOOL` · `time_exit_bars_left INT` | 평가 순간의 규칙 상태. 「AI 가 무엇을 보고 그렇게 말했나」 |
| 결과 | `mode TEXT NOT NULL`(`shadow`) · `result TEXT NOT NULL`(`ok`·`failed`·`skipped`) · `reason TEXT` · `attempts INT NOT NULL DEFAULT 1` | |
| 판단 | `action TEXT`(`hold`·`exit`) · `exit_score INT` · `inconsistent BOOL` · `rationale TEXT` · `key_risks JSONB` · `invalidations JSONB` | |
| 모델 | `model TEXT` · `prompt_version TEXT` · `feature_version TEXT` · `tokens_in` · `tokens_out` · `cost_usd NUMERIC(12,6)` · `latency_ms INT` · `evaluated_at TIMESTAMPTZ` · `created_at TIMESTAMPTZ DEFAULT now()` | |
| 재현 | `input_payload JSONB`(프롬프트에 실은 데이터 그대로) · `raw_response TEXT` | 다른 모델로 오프라인 재채점·파서 재판독 |
| **사후 채움 ①** | `next_open_won NUMERIC` · `next_open_filled_at TIMESTAMPTZ` | `act_date` 시가(KRX). 그날 20:30 적재로 들어오고 시가는 확정 때 바뀌지 않는다 |
| **사후 채움 ②** | `outcome_status TEXT NOT NULL DEFAULT 'open'`(`open`·`closed`·`unknown`) · `exit_date DATE` · `exit_vwap_after_won NUMERIC`(`act_date` 09:00 이후 매도 체결의 수량가중 평균가) · `sold_qty_after INT` · `exit_reason TEXT`(마지막 매도의 `reason_code`) · `outcome_filled_at TIMESTAMPTZ` | 실제 결과. 같은 포지션의 행마다 채운다(분할 매도가 있으면 행마다 다르다) |

인덱스: `(act_date)` · `(strategy_id, ticker, buy_date)` · 부분 인덱스 `WHERE outcome_status = 'open'`(사후 채움 대상 탐색).

### 5.2 `exit_ai_runs` — 하루 1행

`run_date DATE PK` · `bar_date` · `started_at` · `finished_at` · `status`(`done`·`engine_not_running`·`g1_failed`·`no_targets`·`partial`) · `n_targets` · `n_ok` · `n_failed` · `n_skipped` · `n_next_open_filled` · `n_outcome_filled` · `model` · `prompt_version` · `note`.

왜 필요한가 — 평가 행이 0 인 날이 「대상이 없었다」 인지 「워커가 죽었다」 인지 표 하나로 가린다(「없음」 과 「모름」 을 섞지 않는다).

### 5.3 누가 언제 채우나

- **워커 자신**이 매일 아침 실행 첫 단계(3.2 ②)에서 채운다. 별도 일정 없음.
- `next_open_won` — `act_date < 오늘` 이고 비어 있는 행 → `stock_master_daily(ticker, bas_dd=act_date).open_price`. 그날 봉이 없으면(거래정지) 비워 두고 다음 날 재시도, 10거래일 넘게 없으면 `outcome_status=unknown`.
- 실제 결과 — `outcome_status='open'` 인 포지션(`strategy_id, ticker, buy_date, buy_order_no`)이 오늘 G1 에 없으면:
  - `trade_history` 에서 같은 `(strategy, ticker)` 의 `SELL` · `COMPLETED`/`PARTIAL` 체결을 매수 시각 뒤 ~ 다음 같은 `(strategy, ticker)` `BUY` 앞까지 모은다.
  - 누적 매도 수량 ≥ 마지막 평가 행의 `quantity` → 행마다 `act_date` 09:00 이후 체결로 `exit_vwap_after_won`·`sold_qty_after`, 마지막 체결로 `exit_date`·`exit_reason`(`trade_journal_orders.reason_code`) → `closed`.
  - 모자라면 `open` 유지, 10거래일 지나도 안 맞으면 `unknown`(수동 매도·장부 불일치 — 분석에서 뺀다).
- G1 이 실패한 날은 닫힘 판정을 하지 않는다(보유가 사라진 것과 조회 실패를 섞지 않는다).

### 5.4 보존

- **영구 보존**. 권한에 DELETE 를 주지 않고, retention 작업을 두지 않는다.
- 크기: 하루 10행 × 행당 약 8KB(입력 스냅샷·원문 포함) ≈ 월 2MB · 연 25MB. RDS 에서 문제 되지 않는다.
- 나중에 줄일 필요가 생기면 `input_payload`·`raw_response` 만 1년 뒤 비우는 쪽을 먼저 검토한다(판단·결과 칸은 지우지 않는다). 지금은 하지 않는다.

---

## 6. 반사실 측정 (사전 등록 초안)

> 첫 분석 전에 `prereg.frozen.md` + sha256 으로 얼린다(D2 와 같은 방식). 아래는 그 초안이다.

### 6.1 정의

- **분석 단위 = 포지션**(같은 포지션의 여러 날은 독립이 아니다).
- 모집단 P = `ok` 평가가 1행 이상이고 `outcome_status='closed'` 인 포지션.
- 신호 포지션 P_s = P 중 `action='exit'` 가 한 번이라도 나온 포지션. 첫 `exit` 행 = d*.
- 반사실 매도가 `cf = next_open_won(d*) × (1 − 0.0015)` — 09:00 시장가 미끄러짐을 0.15% 로 깎는다(실제 매도가는 실제 미끄러짐을 이미 품고 있어서, 안 깎으면 반사실 쪽이 공짜 이득을 얻는다). 민감도: 0% · 0.3%.
- 실제 = `exit_vwap_after_won(d*)`(d* 의 `act_date` 09:00 이후 매도 평균).
- **Δ_p = (cf − 실제) ÷ `buy_price_won` × 100**(%p, 진입가 대비). + = AI 대로 일찍 팔았으면 나았다. 매도 비용은 양쪽이 같아 뺀다.

### 6.2 지표

| 지표 | 무엇 | 왜 |
|---|---|---|
| **M1** 평균 Δ (P_s) | 포지션 부트스트랩 95% 신뢰구간 | 주 지표 |
| **M2** 무작위 날짜 대비 | P_s 의 각 포지션에서 평가일 하나를 무작위로 골라 같은 계산 → 10,000회 → 「무작위 ≥ 관측」 비율 = p | **D2 교훈** — 손실 구간에서는 「아무 날이나 일찍 판 것」 도 좋아 보인다. AI 가 이겨야 할 상대는 0 이 아니라 무작위 타이밍이다 |
| **M3** 순위 판별 (일 단위) | `exit_score` vs 라벨 y = 1[(실제 − next_open) ÷ buy < −0.25%](그날 팔았으면 나았다)의 AUC, 포지션 단위 군집 부트스트랩 | 임계와 무관한 판별력 |
| **M4** 꼬리 비용 | 실제 수익 ≥ +2R(또는 +15%)로 끝난 포지션에서 Δ 의 합 | 추세 전략은 큰 이익 몇 건으로 번다. AI 가 그 꼬리를 얼마나 자를지 |
| **M5** 보유 오류 | `STOP_LOSS` 로 끝난 포지션 중 마지막 평가가 `hold` 였던 비율 | 「놓친 경고」 |
| M6 층별(판정에 안 씀) | 전략별 · 모델별 · `prompt_version` 별 · donchian 은 cycle405 이후만 | |

### 6.3 판정 규칙 (초안)

1. |P_s| < 30 → **판단 불가**.
2. M1 상한 < 0 → **해로움**(AI 대로 팔면 손해).
3. M1 하한 > 0 ∧ M2 p < 0.05 ∧ M3 AUC 하한 > 0.5 → **유용**(그때 형태 B 재검토 안건으로 올린다 — 자동으로 아무것도 바뀌지 않는다).
4. M1 신뢰구간이 (−1.0%p, +1.0%p) 안 → **의미 없음**. 1.0%p 는 donchian 8%·kojiro 8% 손절 폭의 1/8 수준 = 실익 경계.
5. 그 밖 → **결론 유보**(표본 더).

### 6.4 표본과 기간 (운영 DB 읽기 전용 실측, 2026-10-11)

멀티데이 왕복(매수일 < 매도일) — 대상 4전략:

| 월 | kojiro | donchian | BFB | VCP | 합 |
|---|---:|---:|---:|---:|---:|
| 07 | 9 | 5 | — | — | 14 |
| 08 | 10 | 14 | — | — | 24 |
| 09 | 6 | 10 | 15 | — | 31 |
| 10(11일까지) | 0 | 0 | 2 | 1 | 3 |

- 활발할 때 월 25~30개. 다섯 전략 `buy_paused` 가 10-13 재개 예정이라 그 뒤부터 쌓인다. 지금 보유 10건은 10-14 아침부터 바로 평가 대상이다.
- `exit` 신호 비율은 모른다. 40~60% 로 잡으면 P_s 는 월 10~15개 → **30개 중간 판정 ≈ 2~3개월(2026-12 ~ 2027-01)**.
- 「의미 없음」(±1%p) 을 가르려면 Δ 의 표준편차를 5%p 로 가정할 때 약 100개 → **6~9개월**. 최종 판정 = P_s 100개 또는 2027-06 중 먼저.
- 전략 비중·`buy_paused`·파라미터가 바뀌면 표본 구성이 바뀐다 — 층별로 본다. donchian 은 cycle405(깡토식 개조) 이후만 쓴다.

---

## 7. 화면

- **1단계 = 화면 없음.** 확인은 DB 조회와 `docker logs llm_worker` 로 한다.
- 🔴 **실험 기간에는 보유 화면(잔고·전략 패널·대시보드)에 AI 청산 의견을 띄우지 않는다.** 사람이 「AI 가 팔라는데」 를 보고 손으로 팔면 실제 청산가가 AI 영향을 받아 반사실이 성립하지 않는다(이미 판 포지션의 실제가 곧 AI 의견이 된다). 트레이더 관점에서도 매일 아침 「팔까?」 문장을 보면 규칙을 깨고 싶어진다.
- 2단계(선택): **닫힌 포지션의** 거래일지 카드에 한 줄 — 「AI 청산 의견: 10-14 보유 38 · 10-15 청산 64(근거…) → 시가 매도였다면 +1.2%p」. 회고 전용이라 오염이 없다. backend 가 새 표를 읽기만 하는 `src/db/exit_ai.py` + `journal_view` 칸 추가라 `src/` 변경(full 배포)이다.

🟥 **결정 D-6** — 화면: 1단계 없음 + 실험 중 보유 화면 노출 금지(권고) / 닫힌 포지션 거래일지 카드 한 줄까지 같이.

---

## 8. 비활성화·안전

### 8.1 끄는 법

| 방법 | 효과 | 반영 |
|---|---|---|
| `docker compose -f docker-compose.prod.yml stop llm_worker` | 완전 정지 | 즉시. backend 무접촉 |
| compose `environment: EXIT_AI_MODE=off` | 워커는 살아 있고 `exit_ai_runs.status=disabled` 만 쓴다 | `llm` 축 선택 배포(워커만 재생성) |
| `secrets/llm_worker.env` 에서 키 제거 + 워커 재생성 | 평가 행이 `no_key` 실패로 남는다 | 워커 재생성 |

DB `system_config` 스위치는 두지 않는다 — 그러려면 그 표에 SELECT 를 열어야 하는데, 워커가 매매 킬스위치 표를 읽을 이유를 만들지 않는다.

비활성화 심층 검증(루트 규칙) — 소비처 = 분석 스크립트와(2단계를 하면) 거래일지 카드뿐. 매매 경로 소비처는 **구조적으로 0** 이다(아래 8.2 의 가드). 끄면 그날부터 이력이 비는 것 외 영향이 없다.

### 8.2 매매 영향 0 을 보장하는 장치

1. **프로세스 분리** — backend 와 다른 컨테이너. 워커가 죽거나 메모리를 다 써도(`mem_limit`) backend 이벤트 루프와 무관.
2. **backend → 워커 의존 0** — backend 는 워커를 부르지 않고, 1단계에서는 새 표도 읽지 않는다.
3. **구조 가드(backend 쪽 테스트)** — `src/` 안에서 `exit_ai_evaluations`·`exit_ai_runs` 를 언급할 수 있는 파일을 `src/db/exit_ai.py`(2단계)·그 읽기 라우트로만 한정하고, **`src/engine/` 과 8영역에서는 0** 이어야 한다. 「매매에는 쓰지 않는다」 를 코드 규칙으로 박는다.
4. **backend 부하** — G0·G1 각 하루 1~3회(G1 은 5초 캐시). 일봉·체결 조회는 워커가 RDS 에 직접, 전용 역할 `statement_timeout=5s`·`lock_timeout=1s`·자동커밋.
5. **KIS 0** — 같은 앱키 접속으로 메인 체결통보가 끊길 길이 없다(격리 테스트).
6. **쓰기 권한 = 자기 표 둘뿐**. `trade_history` 를 바꿀 길이 없다.

### 8.3 비밀값

- OpenAI 키·DSN 은 `secrets/llm_worker.env` 에만. 메인 `.env` 를 마운트하지 않는다.
- 워커 코드·문서·테스트에 KIS 자격 변수 접두사·체결통보 TR 이름 0(I2 동형 문서 스캔).
- 로그·예외·DB(`raw_response`·`input_payload`)에 키·DSN 이 들어가지 않는 것을 테스트로 확인.
- 프롬프트에 계좌번호·종목명 없음.

### 8.4 깨지면 안 되는 안전 규칙과의 관계

- 손절 유예(형태 A)는 **어떤 단계에서도 만들지 않는다**(근거 문서 §5.2). 이 설계의 출력은 어떤 엔진 입력에도 연결되지 않는다.
- 15:20 일괄청산·익일청산·체결통보·NXT 좀비 차단 — 무접촉.
- 8영역·`scheduler.py` — 0줄.

---

## 9. 구현 사이클 분해

| 사이클 | 내용 | 파일 | 테스트 | 배포 |
|---|---|---|---|---|
| **C1 표·역할** | migration 050(표 2개·인덱스) + `llm_worker/ops/role.sql` | `supabase/migrations/050_exit_ai_evaluations.sql` · `llm_worker/ops/role.sql` | `tests/integration/` 스키마·UNIQUE·DELETE 권한 없음 확인(역할 시험은 pg_harness 안에서 역할 생성 후 `DELETE` 거부 단언) | `none`(migration 만 — deploy.yml 이 적용) |
| **C2 워커 본체** | 패키지 `lw` — `config`(상수·허용 경로·허용 전략) · `http`(G0/G1) · `db`(자동커밋) · `features`(지표 복사) · `prompt`(프롬프트·출력 검증) · `exit_shadow`(대상 선정·평가·기록) · `outcome`(사후 채움) · `schedule`(08:15/08:35/08:55 KST 루프) · `__main__` + Dockerfile · requirements(asyncpg·httpx·openai) · README | `llm_worker/**` | 워커 자체 `llm_worker/tests/`: 격리(I1~I3 동형 — src import 0·환경변수 목록·KIS 접두사 0·키 로그 0) · 대상 선정(허용 목록·`buy_date ≤ bar_date`) · 미래 정보 차단(`bas_dd < 오늘`, 잠정 봉 skip) · 출력 검증(클램프 금지·`inconsistent`) · 사후 채움(분할 매도·같은 종목 재매수 경계·G1 실패 날 닫힘 판정 금지) · 일정(freezegun 창 안·밖) · 일일 상한. backend 쪽 `tests/unit/`: 지표 동등성(`llm_features` vs `lw/features`) · 허용 목록 ⊆ 명부 id · `src/engine/`·8영역의 `exit_ai_*` 언급 0 | 없음(컨테이너 정의 전) |
| **C3 배선** | compose 본체 블록(`mem_limit: 192m`·`cpus: 0.25`·로그 상한·`env_file`·`environment`·`restart: unless-stopped`·볼륨 없음·포트 없음) + `compose_up_changed.sh` `LLM_RE` 축 + 배포 가드 테스트 갱신(`test_cycle248_deploy_pipeline.py` 등) + `pyproject.toml` testpaths 에 `llm_worker/tests` + 문서(루트 CLAUDE.md Docker 절 · `docs/architecture.md` 15장 · README 「배포 전 호스트 준비」) | `docker-compose.prod.yml` · `tools/deploy/compose_up_changed.sh` · 문서 | 배포 파이프라인 가드 · `/sync-docs` | **full 1회**(backend 재시작) — 장외 창, 🟧 아래 사전 준비 완료 뒤 |
| **C4 첫 가동 실측** | 다음 거래일 08:15~09:00 — `exit_ai_runs` 1행·평가 행 수 = 대상 보유 수 · 칸에 값이 찍히는지(손절선·`bars_held`·`next_open` 다음 날) · 비용 | — | — | — |
| **C5 사전 등록 고정** | 6장 초안을 `prereg.frozen.md` + sha256 으로 얼린다(첫 분석 전) | `_workspace/analysis/exit_ai_shadow/` | — | — |
| C6(선택) | 닫힌 포지션 거래일지 카드 한 줄(D-6 에서 고르면) | `src/db/exit_ai.py` · `src/engine/journal_view.py` · 프론트 카드 | 단위 + 화면 | full |

규모(대략): C1 SQL 120줄 + 테스트 150줄 · C2 코드 900~1,200줄 + 테스트 1,000줄 안팎 · C3 100줄 + 문서. 세션 2~3개.

순서 제약:
1. C1 → 🟧 역할 생성·비밀 파일 → C2 → C3 배포. **비밀 파일이 없는 채로 C3 를 push 하면 compose 전체가 실패해 backend 도 올라오지 않는다**(journal_worker 선례).
2. C3 는 full 이므로 장외 창 + 사용자 승인(자율 구간이어도 compose·`tools/deploy/` 변경은 full 판정이라 창 규칙을 지킨다).
3. 매매 행위 변경이 없어 8영역 승인·`domain-consult` 선행 조건에는 해당하지 않는다. 다만 외부 서비스(OpenAI 새 키)·운영 DB 역할 생성은 「외부로 나가는 조치」·운영 조치라 사용자 승인 항목이다.

---

## 10. 반례 / 한계

- **표본이 느리다.** 판정까지 수개월. 그 사이 전략·파라미터·모델이 바뀌면 층이 갈린다.
- **기본값 `hold` 편향.** 「모르면 보유」 를 넣었으므로 `exit` 신호가 드물 수 있다(D2 의 70점 게이트처럼 신호 0 이면 M1 을 못 잰다). 첫 2주 실측에서 `exit` 비율이 5% 미만이면 프롬프트 문구를 바꾸기 전에 사용자에게 알린다(바꾸면 새 `prompt_version` 층).
- **시가 반사실의 낙관.** 실제로 09:00 시장가를 냈다면 시가보다 나쁘게 체결될 수 있다. 0.15% 깎기 + 민감도로 대응하지만, 얇은 종목은 더 나쁠 수 있다.
- **같은 날 기계적 청산과 겹침.** kojiro 스테이지3 `TREND_EXIT`(익일 아침)·종목상태 청산이 같은 날 시가 근처에서 나면 Δ≈0 이 섞인다. 분석에서 「act_date 09:05 이전 실제 매도」 를 뺀 민감도를 함께 본다.
- **일봉만 본다.** 장중 정보·뉴스·수급이 없다. 매수평가가 같은 조건에서 「의미 없음」 이었다는 점이 사전 기대를 낮춘다(근거 문서 §5.4 — 「C 는 사용자가 데이터를 원할 때만」). 이 실험의 값은 「AI 를 청산에 쓰지 않을 근거를 데이터로 남기는 것」 일 가능성이 높다.

## 11. 후속 검증 권고 (tdd-engineer / tester)

- tdd-engineer: 사후 채움의 경계 시리즈 — ① 분할 매도 2회 후 전량 ② 매도 뒤 같은 전략·종목 재매수(쿨다운 밖) ③ 수동 매도(전략 귀속 다름) ④ G1 일시 실패 날 ⑤ 거래정지로 `act_date` 봉 없음. 미래 정보 차단 — 08:15 시점 DB 에 오늘 봉(껍데기)이 있어도 읽지 않는지.
- tester: C4 첫 가동에서 `exit_ai_runs` 와 평가 행 수 대조, 다음 날 `next_open_won` 이 채워지는지, backend 응답 시간·메모리 변화 0 확인(08:15 전후 `docker stats`).

---

## 12. 결정·조치 목록

**🟥 사용자 결정**

| # | 결정 | 권고 |
|---|---|---|
| D-1 | 자리 | (b) 새 워커 컨테이너 |
| D-2 | 이름 | `llm_worker`(15장 1단계와 합칠 자리) — 이번에 매수평가 큐는 만들지 않는다 |
| D-3 | 대상 | 5전략(donchian·kojiro·VCP·BFB·etf_trend). LTV 상한가 익일 보유 제외 |
| D-4 | 모델 | `gpt-6-luna` 고정(실험 중 변경 = 새 층) |
| D-5 | OpenAI 키 | 전용 프로젝트 키 + 월 한도 |
| D-6 | 화면 | 1단계 없음 · 실험 중 보유 화면 노출 금지 |
| D-7 | C3 full 배포 창 | 장외(주말 권고) |

**🟧 사람이 EC2·외부에서 할 일(C3 배포 전)**

1. migration 050 적용 확인 뒤 `psql "$DATABASE_URL" -v llm_pw="$PW" -f llm_worker/ops/role.sql`(PW = `openssl rand -hex 24`).
2. `~/auto_stock/secrets/llm_worker.env` 생성(`LLM_DATABASE_URL` = 역할 `llm_worker` DSN · `OPENAI_API_KEY`), 권한 600.
3. (D-5 권고 시) OpenAI 콘솔에서 전용 프로젝트 키 발급 + 월 한도 설정.
4. 배포 직전 `free -m`·`df -h` 확인, 필요하면 `docker image prune`.
