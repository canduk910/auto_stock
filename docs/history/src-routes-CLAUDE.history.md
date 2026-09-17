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
