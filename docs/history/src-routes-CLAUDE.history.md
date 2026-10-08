> 원본: `src/routes/CLAUDE.md` · 이관: 2026-09-17

정본은 [`src/routes/CLAUDE.md`](../../src/routes/CLAUDE.md). 이 파일은 거기서 걷어낸 원문을
**고치지 않고** 옮겨 둔 것이다(append-only). 사이클 축으로 찾으려면
[`docs/HARNESS_CHANGELOG.md`](../HARNESS_CHANGELOG.md) 로 간다.

절 제목은 **이관 시점의 정본 절 제목**이다. 항목 제목은 그 원문이 붙어 있던 엔드포인트다.

---

## 인증 — deny-by-default

### 2026-09-17 이관 — PUT /api/strategies/{id}/params 검증 강화 전후 — 사이클 278 시점 서술

```
* **인증은 실수 방어가 아니다** — 인증을 통과한 요청의 *값* 이 타당한지는 별개 문제다.
  **사이클 278 (2026-09-11)** 이후 `PUT /api/strategies/{id}/params` 는 카탈로그
  기반으로 키·자료형·범위·부호·불변식을 검사해 위반을 **422** 로 거부한다(종전에는
  미지 키를 조용히 버리고 범위 밖 손절값을 그대로 저장했다). 다만 **범위 안의 위험한
  값**(예: 손절 −15%)은 여전히 통과하고, 키는 단일 공유 키라 **누가 바꿨는지는 남지
  않는다** — 화면의 2단계 확인(identity 15키, cycle290 이 킬스위치 2키 추가)과 운영 기록이 그 자리를 메운다.
```

→ CHANGELOG: cycle278 · cycle290

## 엔드포인트 목록

### 2026-09-17 이관 — POST /api/trading/start — 종전 거부 창 10분

```
⚠️ **cycle283 D4 — 기동 거부 창 `20:00~21:30`**(`scheduler.TIME_SESSION_START_CUTOFF` ~ `TIME_SETTLEMENT`). 그 창에서는 `scheduler.start()` 가 즉시 거부하므로 이 라우트도 사실상 무동작이다(응답은 202 성격, 로그에 `장 종료 후 시작 시도 — 거부됨`). 종전 거부 창은 20:10~ 로 10분이었고 이제 90분이다
```

→ CHANGELOG: cycle283 D4

### 2026-09-17 이관 — POST /api/trading/manual-sell — cycle295 명세 좌표와 cycle287 잔여 처분 카드

```
🔴 **cycle295 (B) 컷 면제 경로**(§4-7 · §9-Q3 ②) — `place_order` 를 직접 부르므로 `execute_sell`·`_apply_clock`·`_route_exchange_by_clock` 을 **하나도 거치지 않는다** = `order_engine._market_rest_gate` 에 닿는 경로가 구조적으로 없다. **15:30~16:00 「완전 휴식」 구간에도 이 버튼은 주문을 낸다**(운영자 수동 조작은 막지 않기로 한 결정). D+1 판독에서 그 구간 주문이 1건 나오면 **이 라우트를 먼저 본다** — 게이트 고장으로 오진하지 않도록 그 구간엔 응답 message 에 면제 경고가 붙고 접수 로그에 `[market_rest_manual_exempt]` 가 찍힌다. ⚠️ 별건(cycle287 잔여) — 16:00~20:00 KRX 애프터에 누르면 44/41 변환도 KRX 라우팅도 없이 시장가가 나가 APBK3013 로 거부되고, 실패 경로에 `_selling.discard` 가 없어 stale `_selling` 이 남는다(처분 = §9-Q3 ③ `execute_sell` 위임, 별도 카드)
```

→ CHANGELOG: cycle295 · cycle287

### 2026-09-17 이관 — GET /api/trading/status — `tradable_boards` 필드 추가 사이클

```
**사이클 18 (2026-05-19) — `strategies[*].tradable_boards: list[str]`** 추가 (DEFAULT_TRADABLE_BOARDS 또는 params.tradable_boards). ScanMonitor "돌파 (대기)" 라벨 분기 근거
```

→ CHANGELOG: 사이클 18

### 2026-09-17 이관 — GET /api/balance — join 3필드·`sector` 필드 추가 사이클

```
J1(2026-05-11): 각 holding 에 `stock_master.get(ticker)` join → `nxt_tradable / krx_halted / excg_dvsn_cd` 3필드 노출(Optional, 캐시 miss/예외 시 None) **2026-08-04 — `sector` 필드 추가**: 위 loop 가 이미 조회한 `basics.raw` 를 `sector_naming.resolve_sector_name(ticker, basics_raw=...)` 에 주입해 **추가 DB 호출 0** 으로 섹터명 산출 (`bstp_kor_isnm` → `_kojiro_sector_key(master_raw)` → `미분류-{ticker}`). 대시보드 포지션 표 섹터 컬럼 소비.
```

→ CHANGELOG: J1 · 2026-08-04

### 2026-09-17 이관 — GET /api/history/pnl — 페어 3키 추가 사이클

```
**cycle276** 각 페어에 `buy_order_nos`/`sell_order_nos`(리스트 — 한 페어가 매수 주문 2건 이상인 실측 9건이 있어 **단수 금지**) + `pair_key`(= `strategy:ticker:첫 매수 order_no`, 빈 값이면 `None` = AI 자문 버튼 비활성) 3키 추가.
```

→ CHANGELOG: cycle276

### 2026-09-17 이관 — GET /api/llm-evaluations — 복합 키 도입 경위(B-2)와 `trade_date` 흡수 결함(B-3)

```
주문번호 단독 키로 접으면 오래된 날짜의 평가가 사라져 그 행은 버튼 비활성인데 상세는 200 을 주는 비대칭이 생긴다(cycle276 후속 B-2, 실 PG 재현)
(B-3: 종전엔 `to_date()` 가 `None` 으로 흡수해 **200 + 가장 최근 1행**이 나갔다)
```

→ CHANGELOG: cycle276 후속 B-2 · B-3

### 2026-09-17 이관 — GET /api/llm-evaluations/{order_no} — cycle266 직렬화 결함 서사와 B-3/B-4

```
`Decimal` 6필드는 여기서 `float` 로 사영(pydantic v2 가 `Decimal` 을 문자열로 내보내 프론트 `toFixed` 가 죽던 cycle266)
**422**(cycle276 후속 B-3 — db 호출 자체를 하지 않는다) — `except Exception: rows=[]` 형태의 fail-silent 금지(cycle266 이 3개월 은폐로 실증)
(B-4 개명 — KST 보장 없음)
```

→ CHANGELOG: cycle266 · cycle276 후속 B-3/B-4

### 2026-09-17 이관 — PUT /api/strategies/weights — 값 크기 기반 단위 추론 폐기

```
종전 `v / 100 if v > 1 else v` 값 크기 기반 단위 추론은 폐기(정수 `1`=1% 가 비율 `1.0`=100% 로 저장되던 결함).
```

→ CHANGELOG: 2026-08-18 비중 단위 계약

### 2026-09-17 이관 — GET /api/strategies/te — 도입 사이클과 검증 표기

```
**사이클 F (2026-08-02)** — 전략별 TE(트레이딩 예지치)/RR비율 최근 N개월(months×30일) 지표 (관찰 전용).
매매 8영역 diff 0 (read-only)
```

→ CHANGELOG: 사이클 F

### 2026-09-17 이관 — GET /api/strategies/params-schema — 재드리프트 시점 수치

```
재드리프트(99키 중 73키가 화면 밖이던 상태 — cycle278 이력, 숫자는 그 시점 값)가 그날부터 다시 시작된다(AST 가드 C35). 응답 `data` = `catalog_version` · `groups`(7) · `types`/`risks`/`units`(닫힌 어휘) · `params`(101, `ParamSpec` 전 필드 — `min_items`·`forbidden_choices` 포함: 화면이 빈 목록 저장을 사전 차단하고 금지 선택지를 비활성으로 그리는 근거) · `strategies[]`(`keys`/`params`/`defaults`/`deprecated_for_keys`) · `invariants.budget`(강제) + `invariants.order`(12건, 경고). `defaults` 는 클래스 `DEFAULT_PARAMS` **깊은 복사본**(응답 생성이 기본값·현재값을 변형하지 않는다). 현재값을 `GET /api/strategies`(staleTime 15s)에서 따로 가져오면 diff 미리보기가 낡은 기준값으로 계산되므로 한 응답에 함께 싣는다
```

→ CHANGELOG: cycle278 · cycle290

### 2026-09-17 이관 — PUT /api/strategies/{id}/params — 사이클 278 이전 무음 폐기

```
**사이클 278 (2026-09-11) 검증 강화** — 종전에는 `if key in strategy.config.params` 로 기존 키만 반영하고 **나머지를 조용히 버렸다**(오타·신규 키가 200 성공 응답을 받고 무시됨).
```

→ CHANGELOG: cycle278

### 2026-09-17 이관 — GET /api/logs · /api/logs/search — 파라미터 확장 사이클

```
**사이클 6(2026-05-17)** — 쿼리 파라미터 확장: `?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&level=ERROR&page=1&size=50`. 응답 `data` 는 `{items, total, total_pages}` dict. 기존 `?limit=50&level=ERROR` 하위 호환 보존(`limit` 단독은 `size` 흡수). 422: `from_date>to_date` / `page<1` / `size>200`. KST 강제 — 백엔드 `f"{date}T00:00:00+09:00"` ~ `T23:59:59.999999+09:00` 범위 비교 |
**사이클 6 통합(2026-05-20)** — `?q=...&level=INFO\|WARNING\|ERROR\|CRITICAL\|ALL&start=ISO&end=ISO&limit=1~1000`. `q` 는 `min_length=1` 필수 (빈 문자열 422). `level=ALL` 또는 None 은 무필터. ILIKE substring 매칭 (대소문자 무시) `message LIKE '%q%'`. 응답 `data` 는 `{logs:[{id,timestamp,log_level,message},...], total, has_more}` dict. `has_more=true` 면 limit 초과 — UI 가 "키워드 좁히기" 안내. 검색 시 페이징 비활성 (단일 응답) — `total>len(logs)` 시 키워드 추가 좁히기 또는 limit 상향
```

→ CHANGELOG: 사이클 6

### 2026-09-17 이관 — POST /api/recommendations/{id}/apply — J4 도입과 N1 Σ 사전 검증 도입 배경

```
**J4(2026-05-12)** — body 신규 옵션 `apply_weight: bool=False` 추가. true 면 `recommended_weight` 가 `strategy_config.weight` 로 반영(`save_weights`) + `applied_weight` 트래킹.
**N1(2026-08-18) — 증액 시 Σ 사전 검증**: `new_weight > 현재 weight` 이면 `타 전략 현재 weight 합 + new_weight > 1.0 + _WEIGHT_SUM_TOLERANCE` 일 때 `[weight_sum_violation]` WARNING + `success=false` 로 **거부**(params 적용 *전* early return — weight/params/status 어느 것도 저장 안 됨).
도입 배경 = Settings 가 Σ>1.01 이면 저장을 잠그므로, 무가드 증액이 **운영 DB 직접 UPDATE 외 복구 불가** 상태를 만들 수 있었다.
```

→ CHANGELOG: J4 · N1

### 2026-09-17 이관 — POST /api/log-reports/run — upsert 전환으로 재실행이 파괴적이 된 경위

```
**cycle283 C9-b — 기본은 비파괴**. `insert_log_report` 가 upsert 로 바뀌면서(D6) 재실행이 처음으로 파괴적이 됐다: 21:30 정산은 `reset_request_metrics()` + `_reset_daily_state()` 를 돌린 뒤라 그 후 재실행하면 `api_metrics` 0 · `strategy_funnel` 0 으로 **그날 완성 리포트를 덮어쓴다**(종전 순수 INSERT 에서는 UNIQUE 충돌로 무해한 no-op). 그래서 완성 리포트(= `summary`·`model` 둘 다 채워진 행)가 있으면 `generate_daily_log_report` 를 **호출조차 하지 않고** `success=false`. 덮어쓰려면 `?force=1`. 1차 스냅샷만 있는 20:05~21:30 구간과 행 부재는 막지 않는다(20:10 실패일 수동 복구 경로 보존) |
`insert_log_report` 가 upsert 로 바뀌면서(D6) 재실행이 처음으로 파괴적이 됐다: 21:30 정산은 `reset_request_metrics()` + `_reset_daily_state()` 를 돌린 뒤라 그 후 재실행하면 `api_metrics` 0 · `strategy_funnel` 0 으로 **그날 완성 리포트를 덮어쓴다**(종전 순수 INSERT 에서는 UNIQUE 충돌로 무해한 no-op).
(20:10 실패일 수동 복구 경로 보존)
```

→ CHANGELOG: cycle283 C9-b · D6

### 2026-09-17 이관 — POST /api/log-reports/{YYYY-MM-DD}/external — 20:10 OpenAI 경로 병행 비교

```
**cycle249** — 20:20 KST 클라우드 루틴의 분석 결과 저장. **리포터 스코프의 유일한 쓰기 경로**(`src/middleware/api_auth.py::REPORTER_WRITE_PATH_RE`). 바디 `ExternalReportIn`: `provider`(1~40자) / `model`(1~80자) / `summary`(1~4000자) / `findings`(≤50개, 기존 `_validate_report` 로 category/severity 정규화 + title/detail/suggestion 길이 상한 — OpenAI 경로와 같은 정규화기) / `report_md`(선택, ≤200,000자). 범위 위반은 422. 날짜 형식 오류 → `success=False`. `src/db/log_reports.py::upsert_external_report` 가 `ext_*` 6컬럼에만 저장(기존 summary/findings/metrics/model 무접촉 — 20:10 OpenAI 경로와 병행 비교 기준선 보존) |
(기존 summary/findings/metrics/model 무접촉 — 20:10 OpenAI 경로와 병행 비교 기준선 보존)
```

→ CHANGELOG: cycle249

### 2026-09-17 이관 — GET /api/realtime/subscriptions — 필드별 추가 사이클

```
**사이클 18 (2026-05-19) — `last_tick_map: dict[ticker, ISO_KST\|null]`** 추가. **사이클 35 (2026-05-21) — `sessions[*].tickers_detail`** 추가 (cap 200, stale 우선 정렬, 종목당 `ticker/ticker_name/stale/last_tick/retries/last_resub`). **사이클 37 (2026-05-21) — `tickers_detail` 에 `last_cntg_hour` / `today_volume` 추가** (KIS `inquire_ccnl` 캐시 TTL 5분 + cap 20, 미스 → null).
```

→ CHANGELOG: 사이클 18 · 35 · 37

### 2026-09-17 이관 — POST /api/realtime/resubscribe — 단일 `TICK_TR_ID` 시절 서술

```
`_subscriptions` 보존 + `_send_subscribe(TICK_TR_ID, t, subscribe=True)` 만 호출(50ms sleep). 응답 `{resubscribed, tickers}` (sorted). WebSocket 끊김 시 400. F1 자동 재구독(재연결 60s 후)과 별개의 운영자 수동 트리거. 영구 로그 `[ws_manual_resubscribe] count=N tickers=[...]`
```

→ CHANGELOG: J2 · cycle293

### 2026-09-17 이관 — POST/GET /api/realtime/channel-probe — 포렌식 단계 표기와 `open_price` 추가 시점

```
**cycle253 (2026-09-05)** KRX 단독 채널 다크런치 프로브 — 포렌식 P1-7 B 1단계, 8영역 무접촉. body `{ticker(6자리 숫자), tr_id=H0STCNT0}`(허용 리터럴 집합 `{H0STCNT0, H0NXCNT0}`, **H0UNCNT0 는 422**). 409 사유 = `already_probing`·`already_tick_subscribed`·`held_or_pending_clear`·`in_desired_universe`(breakout∪스윙∪momentum)·`probe_cap`(3)·`subscribe_dropped`(구독 후 세션 미배정) / 400 = 메인 `_ws is None`. `kis_ws_pool.subscribe(tr_id, ticker, priority="LOW", bypass_limit=False 리터럴)`. 진입 시 전일 프로브 자동 축출(`action=evict`). 로그 `[krx_channel_probe] action=start` **logger 단독**(write_log 병행 금지 — cycle72 G-6 이중 INSERT). 기본 OFF — 호출 전까지 무동작 |
open_price(09-09 추가 — 채널별 시가 비교용, `ticker_prices[ticker]["open_price"]`)
```

→ CHANGELOG: cycle253

### 2026-09-17 이관 — GET/PUT /api/realtime/tick-channel-mode — cycle294 도입 → cycle295 철회 서술

```
| GET | `/api/realtime/tick-channel-mode` | realtime.py | **cycle293 (2026-09-14)** 시세 채널 리졸버 모드 조회 — `{mode(엔진 메모리 값), stored(DB 값), default, valid_modes, config_key}`. DB 조회 실패에도 200(메모리 값은 항상 보여야 한다, `stored=null`). **cycle294** — `switch_enabled`·`switch_offset_secs`·`switch_config_key` 3키 추가(전환 다이얼은 모드와 별개 축이다) + **적대 검증 시정**으로 `switch_windows`(그날 전환 허용 창) 1키 추가 — 운영자가 화면 없이 "오늘 전환이 몇 시로 잡혔는가" 를 확인하는 유일한 채널이다. ⚠️ **cycle295 (2026-09-16)** — 같이 들어왔던 `gap_hold_enabled`·`gap_config_key`·`nxt_gap_window` 3키는 갭 홀드 철회와 함께 **응답에서 사라졌다**. `switch_windows` 도 창 **3개 → 1개**(`pre_to_krx`)다 |
| PUT | `/api/realtime/tick-channel-mode` | realtime.py | **cycle293 — 🔴 장중 킬스위치.** body `{mode}` ∈ `off`/`observe`/`enforce_low`/`enforce`. **DB 저장 + 같은 요청에서 엔진 메모리까지 덮는다**(재시작·폴링 대기 없음 — cycle287 이 `param_catalog` 미등재로 장중에 못 껐던 실패를 반복하지 않는다. D6·D8 때문에 "다음 재시작에만 반영" 은 사실상 "영원히 못 끔" 이다). 어휘 밖 값 = **422**(조용한 흡수 없음, DB 도 안 간다). DB 쓰기 실패해도 메모리 반영은 시도하고 `persisted=false` + `message` 로 알린다. 폴링 백업 2곳(`scanner.subscribe_filtered_stocks` 5분 · `stale_watcher_core` 120초)이라 라우트를 못 써도 ≤2분. ⚠️ `off` 는 **이미 전용 채널에 올라간 구독을 되돌리지 않는다**(§3-C 장중 전환 금지) — 다음 `_boot`/재구독까지 그 채널에 남고, 그동안 매수 축 게이트는 그날 심긴 **코호트 스탬프**를 읽으므로 계속 닫혀 있다(cycle294 §6 — 술어가 채널 축에서 코호트 축으로 바뀌었고 **모드를 보지 않는다**). **cycle294 — 선택 필드 `switch_enabled: bool \| None` 추가.** 생략하면 현행 값 무접촉이라 모드만 바꾸는 기존 호출은 byte 동일하게 동작한다. `false` 면 **살아 있는 구독의 전환만** 멈춘다 — 종목은 첫 구독 채널에 머물고 `nxt_true` 는 NXT 종일이며 NXT 는 정규장·애프터에 체결을 실으므로 **blind 가 아니다**. 「채널이 문제」와 「전환이 문제」는 다른 결정이라 모드 enum 을 늘리지 않았다(사고 중에 쓸 카드가 `off` 하나뿐이면 운영자가 장중 146종목 대량 전환을 실행하게 된다). 🔴 **cycle295 (2026-09-16) — `gap_hold_enabled` 선택 필드는 폐기됐다.** cycle294 가 그 20분(15:40~16:00, KRX 에 연속 체결이 없고 NXT 애프터만 열려 있는 구간)의 손절 커버리지를 위해 넣었는데, 사용자 결정 「15:30~16:00 완전 휴식」으로 그 구간엔 **주문 자체를 내지 않으므로** 시세만 NXT 를 따라갈 이유가 사라졌다. ⚠️ 지금 그 키를 보내면 **422 가 아니라 조용히 무시**된다(pydantic `extra=ignore`) — 같은 요청의 `mode` 킬스위치까지 막히면 안 되기 때문이다. 즉 옛 런북대로 `{"mode":"enforce","gap_hold_enabled":true}` 를 보내면 `200`·`success:true`·`message:""` 를 받고 **아무 일도 일어나지 않는다**(응답에 그 키가 없는 것이 유일한 단서다). 신규 엔드포인트 0 이 계약이다
```

→ CHANGELOG: cycle293 · cycle294 · cycle295

### 2026-09-17 이관 — GET /api/market-regime/current — 레짐 매수 게이트 제거 시정 서사

```
🔴 **`buy_blocked` 는 항상 `false` 다** — 사이클 I(2026-08-03)가 레짐 매수 게이트를 제거했고, 레거시 `regime.buy_blocked` 프로퍼티(모드 무시)를 그대로 내보내던 표시 결함을 시정했다.
```

→ CHANGELOG: 사이클 I

### 2026-09-17 이관 — PUT /api/integrations/dkstock-regime — 「매수 가드 즉시 해제」 서술

```
비활성화 시 메모리 regime empty reset(매수 가드 즉시 해제). DB 갱신 실패는 500. 매크로 fetch 실패는 graceful — toggle 자체는 성공
```

→ CHANGELOG: 사이클 5 · 사이클 I

### 2026-09-17 이관 — GET /api/integrations/buy-block — 게이트 제거·E-2 통합 계획 서술

```
**사이클 I (2026-08-03) — 매수 게이트 제거**: mode/blocked 는 이제 매매에 영향 없는 **표시 전용**(risk.py/scheduler 게이트 폐지, 레짐 관찰 전용). 운영 DB `buy_block_mode=OFF` 권장(정직 표시). blocked=임계 OR 평가 결과(참고) / reasons=발동 사유 UI 표시.
**사이클 D (2026-07-31)**: `data_available`=매크로 데이터 실유입 여부(`regime.has_regime_data`) / `guard_inert`=`mode != "OFF" and not data_available`(가드 설정됐으나 데이터 없어 무력 = false sense of protection). 프론트 red 무력 배너(`buy-block-guard-inert`) 근거. **사이클 E-1 (2026-07-31, 관찰 전용)**: `etf_kospi_stage`/`etf_kosdaq_stage`(int\|null, KODEX200/코스닥150 고지로 스테이지) + `etf_defensive`(bool\|null, 신선 지수 방어 OR) + `etf_enabled`(bool, `etf_regime_enabled` 다크런치 토글). 소스=`get_current_etf_signal()`(재계산 X). **E-1 은 관찰 노출만 — 매수 가드 미연동**(block 통합은 E-2) |
**사이클 E-1 (2026-07-31, 관찰 전용)**: `etf_kospi_stage`/`etf_kosdaq_stage`(int\|null, KODEX200/코스닥150 고지로 스테이지) + `etf_defensive`(bool\|null, 신선 지수 방어 OR) + `etf_enabled`(bool, `etf_regime_enabled` 다크런치 토글). 소스=`get_current_etf_signal()`(재계산 X). **E-1 은 관찰 노출만 — 매수 가드 미연동**(block 통합은 E-2) |
**E-1 은 관찰 노출만 — 매수 가드 미연동**(block 통합은 E-2)
```

→ CHANGELOG: 사이클 I · D · E-1

### 2026-09-17 이관 — PUT /api/integrations/buy-block — 「다음 매수 신호부터 즉시 반영」

```
다음 매수 신호부터 즉시 반영
```

→ CHANGELOG: 사이클 8 · 사이클 11 · 사이클 I

### 2026-09-17 이관 — POST /api/strategy-funnel/snapshot — 최종 단계 단독 캡처 시절

```
**사이클 171 (2026-06-22)** — 종전 최종 단계 (`step_no=99`) 단독 → `scheduler.capture_funnel_snapshots(registry, is_provisional=False)` 공통 헬퍼 위임 (09:30 자동 hook 과 동일 단계별 + step_no=99 전체 캡처).
```

→ CHANGELOG: 사이클 171

### 2026-09-17 이관 — POST /api/stock-master/refresh-universe — Lock → fire-and-forget 전환 경위

```
**사이클 90 (2026-06-09)** — universe 즉시 trigger 수동 발화 + asyncio.Lock 동시 호출 차단 (409 Conflict). **사이클 110 (2026-06-11) 시정**: 사이클 101 (Q68=A+Q69=B) `fetch_top_500_universe` + `_universe_eager_refresh_loop` 폐기 시점에 import 동행 시정 누락 silent 결함 (사이클 101~108 8 사이클 동안 발견 0건). `from src.engine.scanner import _full_universe_load_once` 단일 호출. **사이클 127 (2026-06-13) — fire-and-forget 전환**: `FastAPI BackgroundTasks` 사용 (response 전송 *후* schedule, axios 디폴트 timeout silent 결함 영구 차단). asyncio.Lock 폐기 → `refresh_progress.is_running("universe")` state 기반 가드.
```

→ CHANGELOG: 사이클 90 · 110 · 127

### 2026-09-17 이관 — POST /api/stock-master/basics/refresh — KRX 폴백 하드코딩 결함 시정

```
**사이클 126 (2026-06-13)** — KIS CTPF1002R + FHKST01010100 매스 보강 즉시 trigger. KRX 1차 폴백에서 `nxt_tradable=False`/`krx_halted=False`/`admin_item=False` 하드코딩 결함 시정 (매매 hot path lazy 호출에만 의존하던 영역 일일 1회 매스 갱신 의무). 2,697 종목 × ~100ms ≈ 13분 소요. 자동 task = scheduler `TIME_STOCK_MASTER_BASICS_REFRESH=16:10 KST` + start() 직후 1회. **사이클 127 — fire-and-forget BackgroundTasks 전환**.
```

→ CHANGELOG: 사이클 126 · 127

### 2026-09-17 이관 — POST /api/stock-master/daily/refresh · master/refresh · refresh-progress — 도입 사이클

```
**사이클 126** — KIS FHKST03010100 일봉 즉시 적재 trigger. ⚠️ **cycle283** — 이 라우트는 `run_periodic_task_loop` 를 타지 않아 신선도 마커를 건드리지 않는다(부작용 0). 다만 `_drop_today_bars` 필터는 그대로 통과하므로 **20:00 KST 이전 실행은 오늘 봉을 쓰지 않는다**(`force` 는 멱등 skip 만 우회). `_stock_master_daily_load_once()` 호출 (사이클 122 일봉 자동 task 와 동일 함수). **사이클 127 — fire-and-forget BackgroundTasks 전환**. 응답 `{status: "started", task_key: "daily"}`. 200/409 |
⚠️ **cycle283** — 이 라우트는 `run_periodic_task_loop` 를 타지 않아 신선도 마커를 건드리지 않는다(부작용 0). 다만 `_drop_today_bars` 필터는 그대로 통과하므로 **20:00 KST 이전 실행은 오늘 봉을 쓰지 않는다**(`force` 는 멱등 skip 만 우회). `_stock_master_daily_load_once()` 호출 (사이클 122 일봉 자동 task 와 동일 함수). **사이클 127 — fire-and-forget BackgroundTasks 전환**. 응답 `{status: "started", task_key: "daily"}`. 200/409 |
`_stock_master_daily_load_once()` 호출 (사이클 122 일봉 자동 task 와 동일 함수). **사이클 127 — fire-and-forget BackgroundTasks 전환**. 응답 `{status: "started", task_key: "daily"}`. 200/409 |
**사이클 129 (2026-06-14)** — KIS 공식 일일 마스터 파일 (`kospi_code.mst` / `kosdaq_code.mst`) 다운로드 + cp949 파싱 + `master_raw` 배치 upsert 즉시 trigger. KOSPI 70 컬럼 + KOSDAQ 64 컬럼 (KOSDAQ 전용 `invt_alrm_yn` 투자주의환기 / 벤처기업 / KOSDAQ150 3건) 매스 적재. 자동 task = scheduler `TIME_STOCK_MASTER_MASTER_LOAD=16:30 KST` + start() 직후 1회. **fire-and-forget BackgroundTasks** (사이클 127 패턴).
**사이클 127 (2026-06-13)** — 작업 진행 상태 통합 조회 (5초 폴링 endpoint). **사이클 129 — 4 작업 확장 (universe/basics/daily/master)**. 응답 `{universe, basics, daily, master}` 각 10 키 `{status: idle\|running\|completed\|failed, total, processed, updated, skipped, failed, started_at, finished_at, elapsed_ms, error_message}`. RefreshProgressBanner 가 `refetchInterval: running 5_000 / 그 외 60_000` 으로 동적 폴링. process-local in-memory state (uvicorn 단일 워커 의무)
```

→ CHANGELOG: 사이클 126 · 127 · 129 · cycle283

### 2026-09-17 이관 — GET /api/stock-master/list — jsonb 문자열 비교 0건 결함과 Supabase 문법

```
**사이클 84** 페이징 list (refreshed_at DESC). limit ∈ [1,1000], offset ≥ 0. **사이클 128 (2026-06-13)** 4 필터 query param 신규 + 응답 envelope: `market` (KOSPI/KOSDAQ/None) / `min_market_cap` (억원 단위, `_eok_to_won` 헬퍼 환산 후 시총 비교) / `min_trade_amount` (억원 단위, 원 환산 후 거래대금 비교) / `name_substr` (대소문자 무시 substring). 응답 schema 변경 `list[dict]` → `{items, total, limit, offset}` envelope (`total` = `count="exact"` 정확). 422: 범위 외. **사이클 168 (2026-06-20)** — `min_market_cap` / `min_trade_amount` 필터 0건 silent 결함 시정. raw.hts_avls / raw.acml_tr_pbmn 가 운영 DB 에 jsonb *문자열* 로 저장되어 종전 jsonb numeric gte 가 항상 false (number > string 정렬) → 어떤 임계든 0건. migration 039 생성 컬럼 `hts_avls_eok`(억원) / `acml_tr_pbmn_won`(원) STORED + 인덱스로 전환. `list_paged_by_filter` `.gte("hts_avls_eok", min_market_cap//100_000_000)` / `.gte("acml_tr_pbmn_won", min_trade_amount)`. market/name 필터는 정상이라 영향 0 |
**사이클 128 (2026-06-13)** 4 필터 query param 신규 + 응답 envelope: `market` (KOSPI/KOSDAQ/None) / `min_market_cap` (억원 단위, `_eok_to_won` 헬퍼 환산 후 시총 비교) / `min_trade_amount` (억원 단위, 원 환산 후 거래대금 비교) / `name_substr` (대소문자 무시 substring). 응답 schema 변경 `list[dict]` → `{items, total, limit, offset}` envelope (`total` = `count="exact"` 정확). 422: 범위 외. **사이클 168 (2026-06-20)** — `min_market_cap` / `min_trade_amount` 필터 0건 silent 결함 시정. raw.hts_avls / raw.acml_tr_pbmn 가 운영 DB 에 jsonb *문자열* 로 저장되어 종전 jsonb numeric gte 가 항상 false (number > string 정렬) → 어떤 임계든 0건. migration 039 생성 컬럼 `hts_avls_eok`(억원) / `acml_tr_pbmn_won`(원) STORED + 인덱스로 전환. `list_paged_by_filter` `.gte("hts_avls_eok", min_market_cap//100_000_000)` / `.gte("acml_tr_pbmn_won", min_trade_amount)`. market/name 필터는 정상이라 영향 0 |
(`total` = `count="exact"` 정확). 422: 범위 외. **사이클 168 (2026-06-20)** — `min_market_cap` / `min_trade_amount` 필터 0건 silent 결함 시정. raw.hts_avls / raw.acml_tr_pbmn 가 운영 DB 에 jsonb *문자열* 로 저장되어 종전 jsonb numeric gte 가 항상 false (number > string 정렬) → 어떤 임계든 0건. migration 039 생성 컬럼 `hts_avls_eok`(억원) / `acml_tr_pbmn_won`(원) STORED + 인덱스로 전환. `list_paged_by_filter` `.gte("hts_avls_eok", min_market_cap//100_000_000)` / `.gte("acml_tr_pbmn_won", min_trade_amount)`. market/name 필터는 정상이라 영향 0 |
**사이클 168 (2026-06-20)** — `min_market_cap` / `min_trade_amount` 필터 0건 silent 결함 시정. raw.hts_avls / raw.acml_tr_pbmn 가 운영 DB 에 jsonb *문자열* 로 저장되어 종전 jsonb numeric gte 가 항상 false (number > string 정렬) → 어떤 임계든 0건. migration 039 생성 컬럼 `hts_avls_eok`(억원) / `acml_tr_pbmn_won`(원) STORED + 인덱스로 전환. `list_paged_by_filter` `.gte("hts_avls_eok", min_market_cap//100_000_000)` / `.gte("acml_tr_pbmn_won", min_trade_amount)`. market/name 필터는 정상이라 영향 0
```

→ CHANGELOG: 사이클 84 · 128 · 168

### 2026-09-17 이관 — GET /api/stock-master/{ticker}/history — 스키마 재설계와 프론트 회귀 시정

```
**사이클 84** — ticker 별 변경 이력 (changed_at DESC). `stock_master_history` 조회 (`list_history` = `select("*")` pass-through). **사이클 150 (migration 036)** 스키마 재설계: `(ticker, seq)` PK. `id`/`before_raw`/`after_raw` 제거 → `seq INT`(0=최신본 / 1=직전본) + `raw JSONB` 신설 (92K→7,146 row 용량 절감). `change_type` = INSERT/UPDATE/DELETE 3종 (trigger `OLD.raw IS DISTINCT FROM NEW.raw` 조건, 'TTL_REFRESH' 미발화). 현재 응답 schema `[{ticker, seq, change_type, raw, changed_at}]`. **사이클 169 (2026-06-20)** — 프론트 UI 변경이력 탭이 사이클 150 신 스키마에 미동기화(`item.before_raw`/`after_raw` 참조)되어 빈 화면이던 회귀 시정 (백엔드 변경 0, 프론트 단독) |
(`list_history` = `select("*")` pass-through). **사이클 150 (migration 036)** 스키마 재설계: `(ticker, seq)` PK. `id`/`before_raw`/`after_raw` 제거 → `seq INT`(0=최신본 / 1=직전본) + `raw JSONB` 신설 (92K→7,146 row 용량 절감). `change_type` = INSERT/UPDATE/DELETE 3종 (trigger `OLD.raw IS DISTINCT FROM NEW.raw` 조건, 'TTL_REFRESH' 미발화). 현재 응답 schema `[{ticker, seq, change_type, raw, changed_at}]`. **사이클 169 (2026-06-20)** — 프론트 UI 변경이력 탭이 사이클 150 신 스키마에 미동기화(`item.before_raw`/`after_raw` 참조)되어 빈 화면이던 회귀 시정 (백엔드 변경 0, 프론트 단독) |
**사이클 150 (migration 036)** 스키마 재설계: `(ticker, seq)` PK. `id`/`before_raw`/`after_raw` 제거 → `seq INT`(0=최신본 / 1=직전본) + `raw JSONB` 신설 (92K→7,146 row 용량 절감).
**사이클 169 (2026-06-20)** — 프론트 UI 변경이력 탭이 사이클 150 신 스키마에 미동기화(`item.before_raw`/`after_raw` 참조)되어 빈 화면이던 회귀 시정 (백엔드 변경 0, 프론트 단독)
```

→ CHANGELOG: 사이클 84 · 150 · 169

### 2026-09-17 이관 — GET /api/stock-master/{ticker}/daily — `Decimal` 문자열 직렬화 결함 서사

```
**사이클 266 (2026-09-07) 결함 시정** — `change_rate`/`prtt_rate`(`NUMERIC(8,4)`)가 asyncpg `Decimal` → pydantic v2 JSON 모드에서 **문자열**로 직렬화되어(운영 실측 `"0.0000"`) 프론트 `.toFixed(2)` 가 `TypeError` 로 죽던 것을 `_daily_row_for_json(row)` 가 **새 dict 로 사영**하며 시정(`Decimal` → `float()`, **필드명 열거 금지** = 값 타입으로만 판정, `raw` 키는 **재귀 변환 금지**(사이클 81 G-AST1 영속), 비-`Decimal`·`float()` 실패는 **필드 단위 fail-open** = 원값 유지).
(종전 `except Exception: rows=[]` 로 진짜 DB 장애를 404 로 은폐하던 것을 제거). ⚠️ **F-1 (알려진 한계, 미해소)** — `src/db/stock_master_daily.py::get_recent_daily` 가 **자신이** 예외를 삼켜 `[]` 를 반환하므로(280~287행) 이 500 은 오늘 **실질 도달 불가**이고 진짜 DB 장애는 여전히 404 로 도착한다. 근본 시정은 그 db 모듈인데 6 전략 `prepare()` + 터틀 사이징 ATR + `get_donchian_high` + 수정주가 락 게이트(`_row_has_lock`) + `market_regime.compute_etf_stage_signal` 이 공유 ⇒ 매매 행위 변경 = **사용자 승인 + `domain-consult` 선행** 대상(`_workspace/00_URGENT_WORKLIST.md` 등재). 그래서 404 `detail` 문구가 "서버 조회 실패도 같은 404 로 보일 수 있으니 로그의 `stock_master_daily` 를 확인하라"는 단서를 지고 있다
```

→ CHANGELOG: 사이클 124 · 266

## market_state.py / market_ops.py — 장운영상태 화면

### 2026-09-17 이관 — GET /api/market-ops — cycle285 적대 검증이 잡은 오분류 2건

```
**cycle285 적대 검증 시정**: 종전에는 모든 상태를 무조건 `holiday` 로 덮어 20:20 클라우드 루틴이 실제로 성공(`done`)했거나 재기동으로 `running` 인 행까지 "휴장일" 로 보였다.
**cycle285 적대 검증 시정**: 종전에는 "행이 존재하고 정산 시각이 지났다" 만으로 `overwritten` 을 단정해 스냅샷이 그날 아예 안 돌았어도 21:31 부터 영원히 "완료" 로 보였다.
```

→ CHANGELOG: cycle285

## backtest.py — `/api/backtest/*`

### 2026-09-17 이관 — GET /api/backtest/mcp/health — Phase 표기

```
Phase 1 산출 — 실행/조회 엔드포인트는 미구현
```

→ CHANGELOG: —

## market_state.py / market_ops.py — 장운영상태 화면

### 2026-09-25 cycle363 — `/api/market-ops` 행의 「마커 영구 결측 4작업」 서술 교체

정본 원문(행 일부 두 곳):

— 마커가 영구 결측인 4작업(`full_universe_load`·`evening_funnel_capture`·`stock_master_daily_purge`·`quote_token_refresh`)은 시각이 지나도 `failed` 가 아니라 `unknown` 이다.

그러지 않으면 boot 즉시실행이 매일 남기는 07:5x 증거가 저녁 예정 실행을 하루 종일 거짓 "완료" 로 보이게 한다.

경위: cycle363 이 `full_universe_load` 에 영업일 슬롯 게이트를 붙이면서 그 task 도 성공 마커를 남긴다.
그래서 「마커가 영구 결측인 4작업」은 3작업(`evening_funnel_capture`·`stock_master_daily_purge`·
`quote_token_refresh`)이 됐다. 다만 이 화면의 9행(전체 유니버스 적재)은 여전히 진행률만 읽는다
(`marker_iso=None`) — 화면 행위는 불변이고 서술만 낡았다. 같은 게이트 때문에 부팅 즉시 실행이 평상시
아침에는 돌지 않으므로 「매일 남기는 07:5x 증거」의 「매일」도 걷었다. 원문의 「4작업은 시각이 지나도
`failed` 가 아니라 `unknown`」은 `full_universe_load`(진행률 판정 — `not_fired`/`failed` 가능)와
`evening_funnel_capture`(산출물 판정)에는 맞지 않아, 행마다 판정 소스를 적는 문장으로 바꿨다.

→ CHANGELOG: cycle363 행

## 엔드포인트 목록

### 2026-09-26 cycle364 S1 — `/api/strategy-funnel/snapshot` 행 · `/api/market-ops` 행의 행 순서와 저녁 funnel 증거 문장

정본 원문(`/api/strategy-funnel/snapshot` 행 전체):

| POST | `/api/strategy-funnel/snapshot` | strategy_funnel.py | 수동 trigger — 각 전략 prepare 결과(`_funnel_steps`) snapshot 즉시 생성. `scheduler.capture_funnel_snapshots(registry, is_provisional=False)` 공통 헬퍼에 위임한다(09:30 자동 hook 과 동일 — 단계별 + `step_no=99` 전체 캡처). 운영자 "지금 각 단계 후보 보기" 니즈 충족. 응답 `{target_date, saved_count, count}` (saved_count = 저장 row 수). `is_provisional=True` 는 16:20 저녁 task 전용 |

정본 원문(`/api/market-ops` 행 중 행 순서 괄호와 저녁 funnel 증거 문장):

오늘 야간작업 현황(시각순 14행: basics 보강·purge·저녁 funnel·마스터·재무·토큰 재발급·매수중단·AI자문·유니버스·metrics 스냅샷·클라우드 루틴·일봉 적재·정산·로그분석).
`evening_funnel_capture` 의 산출물 카운트는 `strategy_funnel_snapshots` 의 `is_provisional=TRUE` 행만 센다 — 09:30 자동 캡처·스캐너 필터 훅(둘 다 `is_provisional=False`)이 16:20 저녁 캡처의 "성공" 으로 새지 않게 하기 위해서다. 그 카운트도 같은 evidence-time 게이트를 타서 `snapshot_at >= _funnel_evidence_floor(today)`(= `TIME_EVENING_FUNNEL_CAPTURE` − `_SCHEDULE_EVIDENCE_GRACE`, KST) 인 행만 센다 — 부팅 +600초(≈07:57) 잠정 쓰기가 저녁 캡처 "완료" 로 보이지 않게 하기 위해서이고, `funnel_last_at` 은 이 하한 없이 전체 기간 최댓값이다.

경위: 저녁 캡처가 21:00 다음 거래일 미리보기가 되면서 market-ops 저녁 증거가 `target_date = $1` → `target_date > $1` 로 바뀌었다
(evidence 키 `snapshot_rows_today` 는 계약이라 이름 유지, 뜻 = 오늘 19:00 이후에 쓴 다음 세션 잠정 행). 하한은 21:00 − 2시간 = 19:00.
행 순서에서 저녁 funnel 이 일봉 적재(20:30)와 정산(21:30) 사이로 옮겨졌다. 수동 캡처는 라벨 가드(카드3 (가))가 기준일이 다른 전략을 건너뛰고 message 로 알린다.

→ CHANGELOG: cycle364 S1 행

## 엔드포인트 목록

### 2026-09-27 cycle384 — `PUT /api/strategies/{id}/params` 행의 「매수를 멈추는 정당한 수단」 · 카탈로그 수

정본 원문(`PUT /api/strategies/{id}/params` 행 중 한 구절):

어느 쪽도 운영자가 의도한 것이 아니다. 매수를 멈추는 정당한 수단은 전략 비활성화다.

정본 원문(같은 행 · `GET /api/strategies/params-schema` 행 · 「인증」 절의 수):

- identity(리스크 정체성 상수 15키)는 **서버가 막지 않는다**
- 파라미터 카탈로그(`src/engine/param_catalog.py` 104키) 전체
- `params`(104, `ParamSpec` 전 필드
- (identity 15키)과 운영 기록이 그 자리를 메운다.

경위: 전략 비활성화는 보유분의 손절까지 멈춘다(루트 `CLAUDE.md` 금기). cycle384(사용자 결정 2026-09-27 「돈키언 신규매수 중지」)가 신규 매수 신호만 멈추는 `buy_paused` 를 두었으므로 정당한 수단을 그것으로 바꿨다. 같은 사이클이 카탈로그를 105키 · identity 18키(`CATALOG_VERSION="cycle384.1"`)로 늘렸다. identity 15키 표기는 cycle300(`daily_fetch_depth_mode`)·cycle382(`market_unit_mode`)가 identity 키를 더할 때 따라오지 못한 수였다.

→ CHANGELOG: cycle384 행

## 엔드포인트 목록

### 2026-09-27 cycle385 — `POST /api/trading/manual-sell` 행의 「stale `_selling` 이 남는다」

정본 원문(같은 행 「알려진 한계」 중 한 구절):

⚠️ **알려진 한계** — 16:00~20:00 KRX 애프터에 누르면 44/41 변환도 KRX 라우팅도 없이 시장가가 나가 APBK3013 로 거부되고, 실패 경로에 `_selling.discard` 가 없어 stale `_selling` 이 남는다.

경위: cycle385(분할 매도 허용)가 이 라우트의 `_selling.add` 를 `place_order` **앞**으로 옮겼다. 뒤에 두면 시장가가 REST 응답보다 먼저 체결될 때 주문 종료의 `_selling.discard` 가 먼저 돌고 그 뒤에 선 표식이 잔여 보유의 손절을 막는 좀비가 된다(보유 축 분리 전에는 포지션이 통째로 지워져 무해했던 순서다). 발사 실패로 표식을 되돌리는 것은 발사되지 않은 것이 확정된 실패뿐이다(부록 R3 K2 — `src/api/base.py::_request` 가 주문 POST 도 전송 오류·5xx 에 재시도해 앞 전송이 접수됐을 수 있다). 부록 R3 는 그 실패를 APBK0400(`is_sell_qty_exceeded`)으로 한정했고, 그러면 APBK3013·APBK0918 장운영외처럼 같은 요청의 앞 전송도 똑같이 거부됐을 거부까지 표식을 남겨 손절이 `selling_reconcile` 까지 멈췄다(3차 돈 렌즈 NO-GO). 부록 R4 D2(2026-09-28, 루트 규칙 「NXT 매도 거부 좀비 차단」 — 보존하면 stale `_selling` 좀비 — 을 따른 결정)가 판정을 `order_engine._sell_not_placed_reason` 으로 모아 장운영시간 외 · 시장가 불가 거부도 되돌리게 했다. 그래서 애프터 시장가 거부는 문구가 시장가 불가 키워드에 걸리면 표식을 되돌리고(`selling_released=market_order_disallowed`), 걸리지 않거나 EGW00201·전송 예외면 표식을 남기되 `[manual_sell_selling_kept]` WARNING 으로 드러나고, 열린 주문이 없으면 `selling_reconcile` 이 푼다 — 원문의 「조용히 남는 stale `_selling`」 과 다르다.

→ CHANGELOG: cycle385 행

---

## 2026-10-01 sync-docs 압축 — 정본에서 이관

출처 = `src/routes/CLAUDE.md`(이관 직전 HEAD `fe7b081e`). 절 제목은 이관 시점의 정본 절 제목이다.

### 인증 — deny-by-default — 엔드포인트 수 · fail-closed bullet · 「401 단일」

```
잡으면 78개 엔드포인트 스키마가 그대로 열린다)
* **fail-closed** — `API_AUTH_KEY` 미설정·빈 문자열이면 전부 401 이다(조용히 열지 않는다).
  매매 엔진은 in-process 라 API 가 잠겨도 매매 영향은 0이고, 대시보드만 멈춘다.
* **응답은 401 단일** + `{"success": false, "data": null, "message": "unauthorized"}`.
```

사유: 라우트 데코레이터는 2026-10-01 기준 94개라 「78개」 는 낡은 수다(수 없이 「스키마 전체」로 바꿨다). fail-closed bullet 은 루트 「핵심 안전 규칙」 API 인증 항목과 같은 문장이라 링크로 줄였다. `reporter_scope` 사유는 cycle249 부터 403(`message="forbidden"`)이라 「401 단일」 은 코드와 다르다(`src/middleware/api_auth.py` `_FORBIDDEN_BODY`).

### 엔드포인트 목록 — `POST /api/trading/start` — 응답 성격 표기

```
(응답은 202 성격, 로그에 `장 종료 후 시작 시도 — 거부됨`)
```

사유: 라우트는 `asyncio.create_task(start())` 뒤 즉시 200 `success=True` 를 돌려준다. 「결과를 기다리지 않는다」로 바꿨다.

### 엔드포인트 목록 — `POST /api/trading/restart` — 저녁 블록 서술 · 복구 ③ · immediate 시각

```
넷 다 `TIME_SETTLEMENT` 뒤에 있어 `start()` 가 거부되면 하나도 실행되지 않는다.
③ 리포트 `POST /api/log-reports/run`(21:30 이후 실행은 `api_metrics`/`strategy_funnel` 이 이미 0 이라 그 두 축은 복구되지 않는다 — **20:05 1차 스냅샷 행이 그날 metrics 의 유일한 생존본**이므로 덮어쓰지 않도록 `force` 없이 쓴다)
일봉 결손 자체는 다음 영업일 07:59 immediate 가 7일 증분으로 보정하지만
```

사유: 코드 대조(2026-10-01): 20:30 일봉 적재는 `TIME_SETTLEMENT`(21:30) 앞이다 — 넷의 공통점은 `start()` 가 띄우는 경로라는 것이다(`scheduler.py` 일봉 task 생성 · `_settle` · `generate_daily_log_report` · `purge_old_logs`). `_is_complete_report` 는 `metrics.snapshot_pass` 가 있는 1차 스냅샷 행을 완성본으로 보지 않으므로 `force` 없이도 재실행이 그 행을 덮어쓴다 — 「force 없이 쓰면 덮어쓰지 않는다」 는 코드와 다르고 같은 문서의 `/run` 행과도 어긋났다. immediate 실행 시각은 상수가 아니라 기동 + `initial_delay_secs=240`(`data_load_tasks.stock_master_daily_load_task_loop`)이다.

### 엔드포인트 목록 — `GET /api/balance` — 섹터 조회 · 청산선 필드 수

```
섹터명은 그 loop 가 이미 조회한 `basics.raw` 를 `sector_naming.resolve_sector_name(ticker, basics_raw=...)` 에 주입해 **추가 DB 호출 0** 으로 산출한다
**cycle339 — 청산선 4필드**(`strategy_id`/`stop_price`/`stop_source`/`target_price`/`target_source`)
```

사유: `resolve_sector_name` 은 `bstp_kor_isnm` 이 비면 `stock_master.get_master_raw` 를 1회 부른다 — 「추가 DB 호출 0」 이 아니라 `stock_master.get` 재조회 생략이다. 열거된 키는 5개(`strategy_id` + 청산선 4필드)다.

### 엔드포인트 목록 — `GET /api/history/pnl` — 실측 건수

```
(리스트 — 한 페어가 매수 주문 2건 이상인 실측 9건이 있어 **단수 금지**)
```

사유: 실측 건수는 시점 수치라 정본에서 뺐다. 규칙(단수 금지)은 남는다.

### 엔드포인트 목록 — `GET /api/performance/summary` — 증상 설명

```
`PerformanceCard` 의 `toLocaleString('ko-KR')` 이 `String` 에 자체 구현이 없어 `Object.prototype` 쪽으로 떨어져 **예외 없이 천단위 구분만 사라진다**(`10720000.00원`). 같은 dict 의 `total_profit_rate`·`avg_daily_profit_rate` 는 이미 `float` 라 한 카드 줄에서 한 칸만 어긋나 눈에 잘 띄지 않는다.
```

사유: 결함 메커니즘 서술을 한 문장으로 줄였다.

### 엔드포인트 목록 — `PUT /api/strategies/weights` — 날짜 꼬리 · 비중 0 가드 누락

```
**요청 바디 `weights` 단위 = 비율(0.0~1.0). 퍼센트(0~100) 금지** (2026-08-18 확정)
```

사유: 날짜 꼬리를 뺐다. 이 행은 cycle325 비중 0 가드(`[weight_zero_guard]` · `[weight_zero_probe_degraded]`)를 적지 않았다 — 정본 「전략 설정 쓰기 경로」 절에 보강했다.

### 엔드포인트 목록 — `PUT /api/realtime/tick-channel-mode` — 코호트 매수 게이트 · 다이얼 분리 근거

```
그동안 매수 축 게이트는 그날 심긴 **코호트 스탬프**를 읽으므로 계속 닫혀 있다(술어가 채널 축이 아니라 코호트 축이고 **모드를 보지 않는다**).
(재시작·폴링 대기 없음 — 킬스위치가 `param_catalog` 미등재라 장중에 못 껐던 실패를 반복하지 않는다. D6·D8 때문에 "다음 재시작에만 반영" 은 사실상 "영원히 못 끔" 이다)
「채널이 문제」와 「전환이 문제」는 다른 결정이라 모드 enum 을 늘리지 않았다(사고 중에 쓸 카드가 `off` 하나뿐이면 운영자가 장중 146종목 대량 전환을 실행하게 된다).
```

사유: cycle336(사용자 결정 2026-09-21)이 `risk.on_tick` 의 `if chan_buy_blocked: continue` 를 걷었다 — 코호트 판정은 계측기로만 남아 매수를 막지 않는다(`src/engine/risk.py` 매수 분기 주석). 다이얼 분리 근거는 `src/realtime/CLAUDE.md` 「시세 채널」 절에 같은 문장이 있어 링크로 줄였다.

### 엔드포인트 목록 — `GET /api/market-regime/current` — 조회 실패 기본값

```
`auto_regime_adjust`·`cash_usage_ratio`·`etf_regime_enabled` 조회 실패는 전부 graceful 기본값(`True`/`1.0`/`False`)
```

사유: `db.system_config.get_auto_regime_adjust` 는 예외를 내지 않고 판독 불가를 `False` 로 돌려준다(cycle316). 라우트의 `except: auto = True` 는 도달하지 않는다.

### 엔드포인트 목록 — `/api/integrations/dkstock-regime` — 출처 표기

```
외부 매크로 서버 활성 여부 조회
외부 매크로 서버 활성 토글
```

사유: 매크로 레짐의 출처는 cycle315 부터 우리 `macro` 컨테이너다(`src/services/macro_client.py`).

### 엔드포인트 목록 — `PUT /api/integrations/status-exit` — 순서의 이유

```
이유 = `pg.execute` 는 커넥션 획득에 상한이 없어 RDS 가 멈추면 `off` 가 30초 넘게 메모리에 닿지 못했다 — 사고 중에는 `off` 가 먼저다.
```

사유: `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절에 같은 근거가 있어 링크로 줄였다.

### 엔드포인트 목록 — `POST /api/stock-master/*` — 소요 시간 실측 · 근거

```
2,697 종목 × ~100ms ≈ 13분 소요.
(axios 디폴트 timeout silent 결함 영구 차단)
```

사유: 소요 시간은 시점 실측이다. 네 POST 의 공통 규약(fire-and-forget · 409 · `force` 기본 True)은 표 아래 한 단락으로 모았다.

### 엔드포인트 목록 — `POST /api/log-reports/run` — 완성 리포트 정의

```
완성 리포트(= `summary`·`model` 둘 다 채워진 행)
```

사유: 실제 판정은 `_is_complete_report` 4축이다(행 존재 · `metrics.snapshot_pass` 없음 · `summary` 가 비지 않고 `OPENAI_EMPTY_RESPONSE_SUMMARY` 도 아님 · `model` 있음).

### market_state.py / market_ops.py — 장운영상태 화면 — `GET /api/market-ops` — 판정 규칙의 근거 문장

```
— 안 돈 작업을 실패로 그리지 않는 것이지 이미 증명된 사실을 지우는 게 아니다.
(둘 다 "이미 없는 증거" 또는 "순수 시계 사실" 이라 휴장 승격 대상이 아니다)
— 그러지 않으면 boot 즉시실행이 남긴 07:5x 증거가 저녁 예정 실행을 하루 종일 거짓 "완료" 로 보이게 한다.
DB 조회는 단일 `fetchrow` 집계(≈3ms) + `system_config` 마커 일괄 조회(`get_task_last_success_bulk`) + `refresh_progress`(메모리) + `daily_log_reports` 1행 — 폴링 비용 무시 가능.
```

사유: 표 셀 하나(약 4KB)를 판정 규칙 목록으로 나누면서 근거 문장을 줄였다. 실측 지연(≈3ms)은 시점 수치다.

---

## 2026-10-02 sync-docs 압축 2차 — 정본에서 이관

출처 = `src/routes/CLAUDE.md`(1차 반영본). 절 제목은 이관 시점의 정본 절 제목이다. 정본에는 규칙·식별자·조건을 남기고, 아래 원문(경위·근거 서술·다른 정본과 겹치는 열거·화면 소비처 서술)만 옮겼다.

### 인증 — deny-by-default — 포트별 인증 · 실수 방어 bullet — 접근 예시·보완 수단

````
Basic Auth `-u <USER>:<PASS>`(X-API-Key 는 nginx 가 주입)
— 화면의 2단계 확인(identity 18키)과
  운영 기록이 메운다.
````

사유: curl 자격 표기는 사용 예시라 정본 규칙이 아니다. 「2단계 확인이 메운다」 는 화면 절차 설명이고 정본은 frontend 문서다.

### 엔드포인트 목록 — 숫자 열 사영 이유(행마다 반복)

````
`get_trades` 의 `SELECT t.*` 는 NUMERIC(`price`·`profit_loss`)을 `Decimal` 로 주고 pydantic v2 는 그것을 JSON **문자열**로 내보내, `TradeHistoryGrid` 가 그 열을 예외 없이 전 행 `-` 로 떨군다.
`Decimal` 6필드는 `float` 로 사영한다(문자열이면 프론트 `toFixed` 가 죽는다).
— 빠지면 `PerformanceCard` 의 `toLocaleString('ko-KR')` 이 예외 없이 천단위 구분만 잃는다(`10720000.00원`).
`change_rate`/`prtt_rate`(`NUMERIC(8,4)`)가 `Decimal` 문자열로 나가면 프론트 `.toFixed(2)` 가 `TypeError`.
— `except Exception: rows=[]` 식 fail-silent 금지.
````

사유: 같은 이유(NUMERIC → `Decimal` → JSON 문자열)를 행마다 다시 적었다. 표 머리 한 단락(「숫자 열 공통」)으로 모았다.

### 엔드포인트 목록 — `POST /api/trading/restart` — 경위·보정 경로

````
(정산 뒤 `run_daily` 가 익일 대기로 진입)
넷 다 `start()` 가 띄우는 경로라 거부되면 하나도 돌지 않는다.
일봉 결손은 다음 영업일 부팅의 immediate 실행(기동 + 240초, 7일 증분)이 메우지만 `_boot()` 의 prepare 보다 늦다 — `[daily_head_stale]` WARNING 이 알린다
````

사유: 일봉 결손의 자동 보정 경로는 `src/engine/CLAUDE.md` 「scheduler.py」 절 `TIME_SESSION_START_CUTOFF` 행과 루트 운영 가이드에 같은 내용이 있어 링크로 줄였다. 복구 3종은 정본에 그대로 남는다.

### 엔드포인트 목록 — `GET /api/trading/status` · `GET /api/balance` — 소비처·섹터 해석 순서

````
— ScanMonitor "돌파 (대기)" 라벨 분기 근거
섹터는 이미 읽은 `basics.raw` 를 `sector_naming.resolve_sector_name(ticker, basics_raw=...)` 에 넘겨 재조회를 생략한다(`bstp_kor_isnm` → 없으면 `get_master_raw` 1회 후 `_kojiro_sector_key` → `미분류-{ticker}`).
````

사유: 화면 소비처는 frontend 문서 몫이다. 섹터 해석 순서의 정본은 `src/engine/CLAUDE.md` 모듈 맵 `sector_naming.py` 항목이다.

### 엔드포인트 목록 — `GET /api/history/pnl` · `GET /api/llm-evaluations` — 필드 열거·상한 근거

````
`data.summary` = 슬라이스 전 closed 페어 집계: `realized_total_krw`(float) · `realized_rate_pct`(가중, round2) · `win_count`·`loss_count`·`even_count`(int) · `win_rate_pct`(round1) · `closed_count`(int). 분모 0 이면 비율은 0.0
(0개·초과 = 422, 손익 그리드 size 상한)
````

사유: 요약 필드는 `frontend/src/types/trading.ts` `TradePnLSummary` 로 가리킨다(반올림·분모 0 규칙은 정본에 남긴다). 200 의 출처는 경위다.

### 엔드포인트 목록 — `GET /api/strategies/params-schema` — data 필드 열거

````
`data` = `catalog_version` · `groups`(7) · `types`/`risks`/`units`(닫힌 어휘) · `params`(105, `ParamSpec` 전 필드 — `min_items`·`forbidden_choices` 포함) · `strategies[]`(`keys`/`params`/`defaults`/`deprecated_for_keys`) · `invariants.budget`(강제) + `invariants.order`(12건, 경고). `defaults` = `DEFAULT_PARAMS` **깊은 복사본**. 현재값을 함께 싣는 이유 = `GET /api/strategies`(staleTime 15s)와 따로 받으면 diff 미리보기 기준값이 낡는다
````

사유: 모양은 `frontend/src/types/strategy-params.ts` `ParamsSchemaData` 가 정본이라 가리키고, 개수·강제/경고 구분·이유 한 문장만 남겼다.

### 엔드포인트 목록 — `POST /api/log-reports/run` · `/external` — 정산 내부 호출·비교 서술

````
21:30 정산이 `reset_request_metrics()` + `_reset_daily_state()` 를 돌린 뒤 재실행하면 `api_metrics`·`strategy_funnel` 0 으로 **완성 리포트를 덮어쓰므로**(`insert_log_report` = upsert)
두 경로를 나란히 비교할 수 있다
````

사유: 정산이 무엇을 리셋하는지는 engine 정본 몫이다. 비교 가능성은 무접촉 규칙의 귀결이라 규칙만 남겼다.

### 엔드포인트 목록 — `/api/realtime/*` — 필드 열거·화면 소비처·구현 사유

````
`total/acked/fresh_60s/stale_60s/limit/tickers(subscribed/acked/fresh/stale, sorted)/reconnect_count/ws_connected/sessions[]`
UI 가 WS tick 시각과 KIS 체결시각을 비교해 "WS 구독 의심" 을 표시한다(5분+ 차이 amber). KIS 에 슬롯 조회 API 가 없어 우리 측 추적을 노출한다.
`get_market_op_state_summary()` 카운트·샘플 + `circuit_breaker` 휴리스틱(`{suspected,reasons,halt_ratio,halted,observed,representative_mkop_cls_code,halt_reasons_sample}`, CB 전용 필드가 없어 best-effort) + `details`(cap 200, `{ticker,vi_code,ovtm_vi_code,halt_yn,halt_reason,iscd_stat,mkop_cls_code,exch_code,received_at}`).
소스 `H0UNMKO0`. RealtimeHealth 5번째 카드
(프로브 중 그 종목이 매수돼 HIGH 로 승격되면 그 함수는 보조 세션 고아 튜플을 못 지우면서 라이브 라우팅을 pop 한다)
— 화면 없이 오늘 전환 시각을 보는 유일한 채널
**DB 저장 후 같은 요청에서 엔진 메모리까지 덮는다**(재시작·폴링 대기 없음).
폴링 백업 2곳(`scanner.subscribe_filtered_stocks` 5분 · `stale_watcher_core` 120초)이라 라우트를 못 써도 ≤2분.
`switch_enabled` 생략 = 현행 값 무접촉, `false` = 살아 있는 구독의 전환만 멈춘다. ⚠️ 선택 필드 밖의 키는 **422 가 아니라 조용히 무시**된다(pydantic `extra=ignore` — 같은 요청의 `mode` 킬스위치가 막히면 안 된다).
````

사유: 세션 집계 필드는 `src/realtime/CLAUDE.md` 「라우트 응답」 절, 장운영 응답 모양은 `frontend/src/types/market-operation.ts` `MarketOperationStatus`, 폴링 백업 2곳은 `src/engine/CLAUDE.md` `tick_channel_mode.py` 항목, `switch_enabled`·미지 필드 처리는 `src/realtime/CLAUDE.md` 「시세 채널」 절이 정본이라 링크로 줄였다. 화면 카드·배지 서술은 frontend 문서 몫이다.

### 엔드포인트 목록 — `/api/market-regime/*` · `/api/integrations/*` — 필드 열거·화면 소비처

````
`auto_regime_adjust` 는 db 게터가 판독 불가를 `False` 로 돌려준다
MarketRegimeCard ETF 스테이지 표시 근거
`{mode: 'OFF'\|'WARN'\|'SOFT'\|'HARD', thresholds:{vix_threshold, fg_high_threshold, fg_low_threshold, defensive_enabled}, blocked, reasons:[], soft_multiplier, data_available, guard_inert}`
`armed` 에는 전용 플래그가 없어 쏘지 않는 `fallback_only` 종목도 보인다.
🔴 **저장에 실패한 축은 고정된 채 남는다**(그 축의 다음 성공 PUT 이나 재시작까지 refresh 가 되돌리지 않는다).
실패 `message` = 「DB 저장에 실패했습니다 — 메모리에는 즉시 반영했고, 그 축을 고정했습니다(다음 성공 저장 또는 재시작까지 유지 — refresh 가 되돌리지 않습니다).」
`{accounts:[{id,label,app_key,app_secret_masked,kis_env,active,created_at,updated_at}]}`
````

사유: 응답 모양은 `frontend/src/types/integrations.ts` `BuyBlockState` · `frontend/src/types/kis-quote-accounts.ts` `KisQuoteAccount` 로 가리킨다. 고정 해제 조건과 이유는 `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절이 정본이다. 실패 message 원문은 `src/routes/system_integrations.py` 에 있다.

### 엔드포인트 목록 — `POST /api/strategy-funnel/snapshot` — message 꼬리 원문·자정 규칙

````
헬퍼의 라벨 가드가 메모리 목록 기준일이 오늘과 다른 전략(21:00 저녁 미리보기 · 준비 중 · 준비 실패)을 건너뛴다. `message` = 「<N>개 snapshot 저장」 + 꼬리 둘(응답 키 불변): ① 기준일이 다른 전략이 있으면 「 — 메모리 목록은 <as_of,…> 기준이라 오늘 날짜로 저장하지 않았다」 ② 건너뛴 전략이 있으면 「 (건너뜀: <sid>:<사유>, …)」 — 사유 = `in_progress` · `prepare_failed` · `as_of_mismatch` · `evening_preview_reject` · `no_meta`. 자정이 지나 저녁 목록의 기준일이 오늘이 돼도 저녁 미리보기는 확정 저장하지 않는다(`evening_preview_reject`).
````

사유: 판정 순서와 자정 규칙(`evening_preview_reject`)의 정본은 `src/engine/CLAUDE.md` 「캡처 라벨 가드 — `capture_skip_reason`」 절이다. message 원문은 `src/routes/strategy_funnel.py` 에 있다. 사유 5종 이름은 정본에 남긴다.

### 엔드포인트 목록 — `/api/stock-master/*` — 컬럼·필드 열거·트리거 정의·화면 주기

````
KOSPI 70 컬럼 + KOSDAQ 64 컬럼(KOSDAQ 전용 `invt_alrm_yn` 투자주의환기 / 벤처기업 / KOSDAQ150)
각 10키 `{status: idle\|running\|completed\|failed, total, processed, updated, skipped, failed, started_at, finished_at, elapsed_ms, error_message}`. RefreshProgressBanner `refetchInterval: running 5_000 / 그 외 60_000`.
집계 8키 `{count_all, bfdy_clpr_present, nxt_tradable_count, with_hts_avls, with_acml_tr_pbmn, total_daily_rows, last_daily_load_at, top_10_recent:[{ticker,name,refreshed_at}]}`
`stock_master_history` PK `(ticker, seq)` — `seq INT`(0=최신본 / 1=직전본) + `raw JSONB`. `[{ticker, seq, change_type, raw, changed_at}]`, `change_type` = INSERT/UPDATE/DELETE(trigger `OLD.raw IS DISTINCT FROM NEW.raw`, 'TTL_REFRESH' 미발화)
근본 시정 자리(그 db 모듈)는 전략 `prepare()`·터틀 ATR·`get_donchian_high`·수정주가 락 게이트·`compute_etf_stage_signal` 이 공유해 매매 행위 변경 = **사용자 승인 + `domain-consult` 선행** 대상이다(`_workspace/00_URGENT_WORKLIST.md` 등재).
````

사유: 마스터 컬럼은 `src/api/CLAUDE.md` 「kis_master.py」 절, 진행·집계 응답 모양은 `frontend/src/types/stock-master.ts` `RefreshProgress`·`StockMasterStats`, `stock_master_history` 표 정의는 `src/db/CLAUDE.md` 「DB 스키마」 절이 정본이다. F-1 의 공유 소비처 전체 목록은 워크리스트 항목이 갖고, 정본에는 「매매 행위 변경 = 승인 대상」 한 문장만 남겼다.

### 엔드포인트 목록 — `GET /api/stock-chart/candles` — 화면 진입·message 원문

````
종목 차트 모달(잔고·주문체결내역·매매손익 행 더블클릭)
(ASCII 숫자만 — `\d` 는 전각 숫자도 통과)
`data` = `CandleChart`(16필드, `src/models/candle_chart.py`). `message` = `"{일봉\|주봉\|월봉} {N:,}개"` · 부분 `"… — 일부 구간만({incomplete_reason})"` · 0봉 `"표시할 봉이 없습니다"`. 실패는 전부 **HTTP 200 + `success=false`, `data=null`**: 첫 창 `KisApiError` → `"KIS 조회 실패 [{msg_cd}] {msg1}"` + `[stock_chart_error] stage=first_window` / `ChartBusyError` → 「다른 차트 조회가 진행 중입니다 — 잠시 후 다시 시도하세요」(로그는 `period_chart` 의 `[stock_chart_busy]` 한 줄뿐) / 그 밖 → 「차트 조회 실패 — 서버 로그 [stock_chart_error] 확인」 + `stage=unexpected`(예외 문자열은 응답에 싣지 않는다).
````

사유: 화면 진입은 frontend 문서, 모델 경로는 `src/api/CLAUDE.md` 「period_chart.py」 절이 갖는다. message 원문은 `src/routes/stock_chart.py` 에 있어 정본에는 실패 분류(200 + `success=false` · 로그 마커)만 남겼다.

### 수동 매도 — `POST /api/trading/manual-sell` — 컷 면제 · 표식 · 되돌림 · 알려진 한계 — 구현 경로·근거 서술

````
- 🔴 **컷 면제 경로** — `place_order` 를 직접 불러 `execute_sell`·`_apply_clock`·`_route_exchange_by_clock` 을 거치지 않아
  `order_engine._market_rest_gate` 에 닿을 경로가 없다. **15:30~16:00 「완전 휴식」 구간에도 주문이 나간다**(운영자 수동
  조작은 막지 않기로 한 결정). 그 구간엔 응답 message 에 면제 경고가, 접수 로그에 `[market_rest_manual_exempt]` 가
  붙는다. D+1 판독에서 그 구간 주문이 나오면 **이 라우트를 먼저 본다**.
체결되면 `_handle_sell_fill` 이 그만큼만 빼고, 남은 보유는 손절·
이유 셋 =
  `qty_exceeded`(APBK0400 수량 초과) · `market_closed`(장운영시간 외) · `market_order_disallowed`(시장가 불가 — APBK1943 ·
  APBK3013 계열). 손절 잔여 재주문과 같은 판정이고 msg1 문구 기반이라, 문구가 키워드에 없으면 되돌리지 않는다.
표식이 선 주문은 손절 잔여 재주문(J-2)에서
  보유와 무관하게 남은 수량을 다시 낸다(운영자가 누른 수량의 대상은 추적 밖 주식일 수 있다). 표식이 `_selling` 해제를
  바꾸는 규칙(손님 주문 · 동결 표식)의 정본 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축」. `strategy_id` 로
  수동 주문을 추론하지 않는다 — 이 라우트는 보유 전략 id 를 적는다.
`[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다.` 는 걸린다(`src/api/balance.py`). KRX 애프터 거부 msg1
    원문은 아직 모른다(`src/engine/CLAUDE.md` 규칙 2)
분할 매도에서는 **다시 누르면 추가 매도**다
````

사유: 컷 면제 경고·마커는 `src/engine/CLAUDE.md` 「order_engine.py」 절, 「안 걸렸다」 판정과 J-2 재주문 효과는 같은 문서 「매도 체결 — 주문 축과 보유 축」 절이 정본이라 링크로 줄였다. 이유 이름 3종과 금기 문장은 정본에 남긴다.

### 전략 설정 쓰기 경로 — 비중 · 파라미터 · AI 자문 적용 — `PUT /api/strategies/weights` · `/params` — 이유 서술·중복 안내

````
`registry.update_weights` 가 `config.enabled = weight > 0` 을 자동 토글해 비중 0 = 그 전략 보유분의
  손절 정지이기 때문이다
(화면 비활성은 안내일 뿐 정본이 아니다)
매수를 멈추는
  정당한 수단은 `buy_paused` 다(`{"params":{"buy_paused":true}}` — 신규 매수 신호만 멈추고 청산은 그대로. 전략
  비활성화는 보유분의 손절까지 멈춘다).
- ⚠️ 미지 키·범위 밖 값을 보내는 운영자 `curl` 스크립트는 422 를 받는다.
````

사유: `config.enabled = weight > 0` 자동 토글과 「비활성화 = 손절 정지」 금기는 루트 `CLAUDE.md` 「핵심 안전 규칙」 이 정본이다. curl 안내는 422 코드 표가 이미 말한다.

### 장운영상태 화면 — `market_state.py` · `market_ops.py` — `GET /api/market-ops` 행 판정 — 조건의 근거·행 순서

````
— 아침 증거가 저녁 예정 실행을
  하루 종일 "완료" 로 보이게 하지 않는다.
「오늘 저녁(19:00
  이후)에 쓴 **다음 세션** 잠정 행」이다(키 이름은 계약이라 유지). `is_provisional=TRUE` 는 09:30 자동 캡처·스캐너 필터 훅
  (둘 다 `False`)을, 날짜 조건은 오늘 날짜 잠정 행(부팅 +600초 레거시 재준비)을 뺀다.
행 순서에서 저녁
  funnel 은 일봉 적재(20:30)와 정산(21:30) 사이다.
````

사유: 조건 자체(evidence-time 2시간 · `target_date > 오늘` ∧ `is_provisional=TRUE` ∧ 하한 19:00)는 정본에 남기고, 각 조건이 무엇을 빼려는지의 설명과 행 순서 서술만 옮겼다.


---

## 2026-10-02 sync-docs 압축 2차 검증 — 이관 사유 정정

출처 = 2차 검증 지적 7건. 위 「압축 2차 — 정본에서 이관」 절의 사유 가운데 사실과 다른 것을 정정하고, 정본에 되살린 것을 적는다(위 절은 고치지 않는다).

- **숫자 열 공통 단락** — 「`except Exception: rows=[]` 금지」 는 원래 `/api/llm-evaluations/{order_no}` · `/api/stock-master/{ticker}/daily` 두 라우트에 걸린 금기였다. 표 머리로 올리며 한정어가 빠져 표 전체 규칙처럼 읽혔고, graceful 로 명시한 관찰 라우트(`/api/portfolio/risk` — `src/routes/portfolio.py` 의 `except Exception: … strategies = []` · bundle · balance 청산선 · strategy-funnel · market-regime/current)와 충돌했다. 정본에 범위(`/api/llm-evaluations/*` · `/api/stock-master/{ticker}/daily`)와 예외(graceful 관찰 라우트)를 되살렸다.
- **증상 두 갈래** — 「프론트 숫자 포맷이 예외 없이 깨진다」 는 절반만 맞았다. history 그리드 `-`·`PerformanceCard` 천단위 상실은 조용히 깨지고, llm 단건 모달·stock-master 일봉 탭은 `toFixed` 의 `TypeError` 로 렌더가 무너진다. 정본에 두 갈래를 적었다.
- **수동 매도 알려진 한계 ②** — 「분할 매도에서는」 한정어가 빠져 무조건 문장이 됐다. 전량이 실제로 체결됐다면 재발사는 보유 0 이라 KIS 가 거부한다. 정본에 「보유보다 적은 수량을 판 경우(분할 매도)」 를 되살렸다.
- **llm 배치 상한 200** — 위 절 사유 「200 의 출처는 경위다」 는 틀렸다. `_MAX_ORDER_NOS = 200`(`src/routes/llm_evaluations.py`)은 `/api/history/pnl` `size` 상한과 함께 움직이는 결합 불변식이다(pnl 페이지만 키우면 그 페이지의 버튼 판정 배치가 422). 정본 배치 행에 되살렸다.
- **`/api/balance` 섹터 주입** — 위 절 사유 「섹터 해석 순서의 정본은 engine」 은 해석 순서에는 맞지만, 이 라우트가 `basics_raw=basics.raw` 를 주입해 재조회를 막는다는 라우트 쪽 사실(`src/routes/balance.py` 의 `resolve_sector_name` 호출)은 engine 문서에 없다. 정본 행에 주입 사실 한 구절을 되살렸다.
- **인증 절 보완 수단** — 위 절 사유 「2단계 확인은 화면 절차이고 정본은 frontend 문서다」 는 틀렸다. `frontend/CLAUDE.md` 에는 identity 배지 한 줄뿐이고 「2단계 확인」 서술이 없다. 남은 곳은 이 정본 「전략 설정 쓰기 경로」 의 identity 항목 하나다(앞으로의 압축에서 지우지 않는다). 인증 절에 「보완 = 화면의 2단계 확인(identity 18키) · 운영 기록」 한 구절과 그 항목 링크를 되살렸다.
- **응답 모양의 정본 방향** — `src/models/CLAUDE.md` 머리는 「응답 칸의 뜻은 routes 가 정본」 이라 하는데, 2차 압축은 응답 모양을 프론트 TS 사본에 맡겼다. TS 는 소비자 사본이라 어긋날 수 있다 — 실례로 `BuyBlockState` 에는 ETF 키가 없다. 정본 표 머리에 「응답 모양의 정본 = 백엔드 모델·생산 함수, TS 는 사본」 을 적고, TS 링크 옆에 백엔드 이름을 붙였다(`BuyBlockStatusResponse` · `KisQuoteAccount` · `_build_pnl_summary` · `_build_params_schema` · `get_market_op_state_summary()` · `refresh_progress.get_all_progress()` · `stock_master.get_stats()`). 같은 행의 「ETF 관찰 3키」 는 이름을 넷 나열하고 있었고 모델 docstring 도 「관찰 필드 4종」 이라 「4키」 로 고쳤다. `src/models/CLAUDE.md` 의 문장은 이 담당 범위 밖이라 손대지 않았다.
- **되살리지 않은 것** — funnel snapshot · stock-chart 의 `message` 원문. 응답 키는 불변이고 문구는 계약이 아니다. 원문은 소스(`src/routes/strategy_funnel.py` · `src/routes/stock_chart.py`)와 위 이관 절에 남아 있다.

---

## 엔드포인트 목록

### 2026-10-08 cycle411 2차 보완 F14 — 실비용 엔드포인트 행의 사이클 꼬리표·「보완」 표기 제거, B2·B4 문구 정정

정본 원문(실비용 관련 행, 걷어내기 전):

```
| GET | `/api/balance` | balance.py | 잔고(예수금 + 보유종목, 0수량 제외). … `sell_cost_rate`(수수료율+세율, ETF/ETN 은 수수료율만)·`cost_status="estimated"`(cycle411, 사용자 결정 10-08 §3 — `engine/cost_overlay.today_window_rates`, 서버 오늘 기준 30일 창, 표본 없으면 기본값. 화면이 평가금액에 곱한다) + `buy_fee_paid`/`buy_fee_status`(cycle411 보완 M1 — 엔진 open 페어(`db/trade_history.get_trade_pairs` 모듈 속성 경유)의 `buy_trade_ids` 체결 비용(정산→추정, 남은 수량 비율)을 더하고, 페어 없는 보유(수동 매수 등)는 매입금액 × 추정 수수료율·`estimated`) 상세 = … |
| GET | `/api/history?page=&size=&ticker=&strategy=` | history.py | … 체결 행마다 `fee`·`cost_status`(BUY·SELL 공통) + SELL 행 `tax`·`net_profit_loss`(= 그 행 `profit_loss − fee − tax`, cycle411 — 비용 조회 실패는 새 칸만 비우고 기존 응답 유지, `[cost_overlay_unavailable]`). **cycle411 보완 H2** — 배분(`cost_overlay.trade_costs`)은 이 페이지 트래이드가 아니라 그 날짜 범위의 **전체** COMPLETED+PARTIAL 체결(`trade_cost_db.get_trades_by_status`)로 하고, 페이지·전략 필터(`?strategy=`)는 배분 **뒤**에 거른다(한 페이지만 보면 그 날 정산 1행 전부를 떠안는 결함을 막는다). CANCELLED·PENDING 행은 배분 대상이 아니라 `fee`/`cost_status` 가 없다(None) |
| GET | `/api/history/pnl?page=&size=&strategy=&ticker=` | history.py | … + `buy_trade_ids`/`sell_trade_ids`(cycle411) + `partial_sell_trade_ids`(cycle411 보완 L2). … **cycle411(사용자 결정 10-08)** — 페어마다 `fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_bp`·`slippage_won`·`cost_status`(settled/estimated/mixed)·`allocated`(같은 날·종목 체결 2건 이상이 정산 1행을 나눠 받았을 때만 true) 를 `engine/cost_overlay.overlay_pairs` 로 덧붙인다. … **분할 매도 뒤(보완 L2)** 판 몫은 `partial_fee`·`partial_tax` 로 따로(총합 보존). `slippage_won`(보완 M4) = 그 페어 체결 행 중 `order_price` 가 하나도 없으면 `None`(있으면 덮인 행만 합산). summary 에 `fee_sum`·`tax_sum`·`realized_net_total_krw`·`realized_net_rate_pct`·`slippage_n`(closed 페어가 가리키는 체결 행 중 `order_price` 덮인 수) 추가 — **보완 M4** 비용 조회 실패 시 저 네 합계는 `0` 이 아니라 `None`(기존 칸은 그대로) |
| GET | `/api/performance/summary?strategy=total` | performance.py | … **cycle411** — `net_total_profit_rate`·`net_avg_daily_profit_rate`(순손익 기준, round 4 — gross 는 round 2 라 수수료·세금처럼 작은 차이가 같은 자리로 뭉개지는 것을 피한다). 🔴 **보완 H1** — `net_total_profit_rate` 는 30일 창이 아니라 **개시 이래** 전체(`_since_inception_net_rows`, `get_performance(days=36_500, …)` 로 전 기간을 읽어 재누적) 축이다 — 비용이 없으면 gross `cumulative_return_rate` 와 같다. 비용 조회 실패 = gross 값으로 폴백 |
| GET | `/api/performance/daily?days=30&strategy=total` | performance.py | … **cycle411** — 행마다 `daily_fee`·`daily_tax`·`daily_net_pnl`·`net_daily_profit_rate`·`net_cumulative_return_rate`·`cost_status`(settled/estimated/mixed). `strategy=` 를 주면 그 전략 체결의 비용만 합친다(**보완 H2** — 배분은 그 날짜 범위 전체 체결로 하고 전략 필터는 배분 뒤에 건다). 🔴 **보완 H1** — `net_cumulative_return_rate` 는 이 창이 아니라 개시 이래 전체로 재누적한 값에서 이 창의 날짜만 집는다(창 첫 행부터 다시 쌓지 않는다). 요율은 화면 범위가 아니라 서버 오늘 기준 30일 창(**보완 M2**, `cost_overlay.today_window_rates`). 비용 조회 실패 = `[cost_overlay_unavailable]` WARNING + 새 칸 전부 `None`(기존 칸 그대로) |
| GET | `/api/strategies/te?months=3` | strategies.py | … `data: TeRrMetrics[]`(7전략 · 19필드 + cycle411 net 8필드 + 보완 M5 `win_gross`/`loss_gross` 2필드, …). … 전략별 예외 격리. **cycle411(사용자 결정 10-08 Q2)** — `compute_te_rr` 호출 **전** `engine/cost_overlay.overlay_pairs(pairs)` 로 페어에 net 칸을 얹어 판정을 순손익 기준으로 만든다(실패해도 pairs 는 gross 그대로 — compute_te_rr 의 net→gross 폴백이 받는다) |
| GET | `/api/costs/today?strategy=` | costs.py | 오늘 체결 × (정산 or 추정 요율), 전략별 + total(cycle411 — OrderMonitor 용, `scheduler.py` 무접촉 경로). … `strategy=` 는 **배분 뒤에** 그 전략만 거른다(cycle411 보완 H2 — 배분 자체는 오늘 전체 COMPLETED+PARTIAL 로 한다). `fee_rate`/`tax_rate`/`rate_source` 는 오늘 하루가 아니라 서버 오늘 기준 30일 창(보완 M2). DB 예외 500 |
| GET | `/api/costs/daily?from=&to=` | costs.py | 날짜별 비용·슬리피지·`cost_status` 추이(cycle411) → … 요율은 `from`~`to` 화면 범위가 아니라 서버 오늘 기준 30일 창(보완 M2, `cost_overlay.today_window_rates`) · ETF 판정은 stock_master 구분 코드 우선(보완 M3, `cost_overlay.stock_master_etf_flags`). 날짜 형식·순서·366일 초과 = 422(`_parse_range` 재사용) · DB 예외 500 |
```

경위: 루트 `CLAUDE.md` 「문서 규약」을 cycle411 1차·2차 보완이 쌓은 `**cycle411**`·`**보완
Hx/Mx**` 태그가 어겼다(2차 통합 검증 F14). 더불어 `/api/performance/summary` 행의 「비용
조회 실패 = gross 값으로 폴백」과 `/api/strategies/te` 행의 「실패해도 pairs 는 gross
그대로」는 2차 보완 B2·B4 가 바꾼 실제 동작(둘 다 **실패 = net 전용 칸 `None`**, 세전 값을
세후 칸에 담지 않는다)과 더 이상 맞지 않아 같이 고쳤다. 각 행을 현재형으로 다시 쓰며
걷어냈다. 값의 출처 괄호(`cycle411, 사용자 결정 10-08 §3 …`)는 규약이 허용해 남긴 곳도
있다.

→ CHANGELOG: cycle411
