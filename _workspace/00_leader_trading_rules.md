# 매매 규칙 명세 — 팀장 작성

## 1. 시스템 개요
KIS OpenAPI 기반 국내주식 자동매매시스템. 다중 전략 아키텍처로 전략별 독립 자금 운용.
모의투자(VTS) 환경에서 1차 검증 후 실전 전환. **2026-05-08판 KIS API 명세에서 NXT(넥스트레이드 ATS) 주문/시세 정식 지원** → 매매 시간대를 KRX 단독에서 KRX+NXT 통합(08:00~20:00)으로 확장.

## 2. 전략 구성

### 전략 A: 상한가 모멘텀 (strategy_id: momentum)
전일종가 대비 급등 종목을 추적하여 +29% 돌파 시 매수, 다음 영업일 NXT 프리 시가에서 청산. **KRX 보드 한정**(상한가 +29%는 KRX 기준).

### 전략 B: 변동성 돌파 (strategy_id: volatility_breakout)
노이즈 비율 기반 동적 K값으로 보드별 시가 + 전일Range × K로 매수 목표가 설정, 돌파 시 매수. **NXT 프리 / KRX 메인 / NXT 애프터 모두 활성**(보드별 K값 분리 운용).

### 전략 C: 롱테일 변동성 돌파 (strategy_id: long_tail_volatility)
변동성 돌파 방식으로 조기 진입 + 당일 +29% 도달 시 익일 청산 모드 전환(롱테일 추구). **NXT 프리 / KRX 메인 / NXT 애프터 모두 활성**.

### 전략 D: 20일 신고가 스윙 (strategy_id: donchian_swing)
일봉 종가가 20일 신고가 돌파 + 60일 EMA 우상향 + 거래대금 1.5배 → 다음 영업일 09:05 시장가 매수. ATR(14)×2 트레일링 청산 / 하드 -7% / 시간 청산 없음 / 평균 5~15 영업일 보유. **KRX 메인만 활성**(추세추종은 일중 변동성 필요).

### 전략별 자금 비중
- 프론트엔드 Settings 페이지에서 비중 조절 (예: momentum 25 / VB 35 / LTV 25 / donchian 15)
- 총 자산을 비중에 따라 분배, 각 전략은 할당된 자금 내에서만 매매
- 전략 간 동일 종목 중복 매수 방지 (보유 OR 주문중 OR 당일매도 통합 가드)
- **매수 수량 1주 fallback (전략 잔여 자금 기준, 2026-05-11 P1 격상)**: `position_ratio × total_investment // current_price = 0`이라도 **전략 잔여 자금**이 1주 살 수 있으면 1주 매수. 4개 전략 동일 규칙.
  - **잔여 자금 = `state.total_investment` − (해당 전략 보유 포지션 `buy_price×qty` 합계 + 해당 전략 `pending_buys` 매수 예정 금액 합계)**
  - 보유/주문중은 `strategy_id`로 격리 — 다른 전략 포지션은 자기 전략 사용액에 포함하지 않음
  - 결함 차단: 기존 로직은 `state.total_investment >= current_price`(고정 총액)와 비교 → 동일 전략이 이미 다른 종목에 자금 90% 점유해도 1주 추가 매수 → **전략 한도 초과**. 2026-05-11 운영 사고로 노출
  - 구현: `StrategyBase._fallback_one_share(current_price)` 공통 헬퍼로 통합 — 4개 전략(`momentum`/`volatility_breakout`/`long_tail_volatility`/`donchian_swing`) 모두 동일 메서드 호출
  - race 가드: `pending_buys`는 `place_order` 응답 직후 동기 영역에서 즉시 등록 — 기존 매핑 등록 규약과 동일하게 합산 일관성 보장

### WebSocket 구독 가시성 (2026-05-12 G, 운영자 슬롯 추적)
- KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재 → 우리 측 도구 강화로 갈음
- **G1 SUBSCRIBE ACK 추적**: `KisWebSocket._subscriptions_acked` set 신규. 정상 응답(`rt_cd=="0"` + `msg1` 에 "SUBSCRIBE SUCCESS" 포함) 수신 시 add, `subscribe/unsubscribe/_is_rejection_response/connect 재연결` 시점에 discard/clear. `get_acked_tickers()` 헬퍼는 TICK_TR_ID 필터링한 set 반환
- **G2 진단 endpoint**: `GET /api/realtime/subscriptions` — `{ total, acked, fresh_60s, stale_60s, limit, tickers:{subscribed/acked/fresh/stale (모두 sorted)}, reconnect_count, ws_connected }`. KST 기준, ws_connected=False 도 200 응답. 인증 가드 없음
- **G3 status 확장**: `scanner.get_scan_status()` 에 `tick_coverage_total/acked/fresh/stale` 4개 키 추가. 기존 `subscribed_count` 보존. ScanMonitor 는 stale 카운트에 따라 색상 배지(0=기본 / 1~5=yellow / 6+=red). 한도 근접도 진행바(total/41, 80%+ amber) 노출

### WebSocket 시세 구독 우선순위 (2026-05-12 E1, donchian 조기 손절 사건 대응)
- **`MAX_SUBSCRIPTIONS = 41` (KIS 공식 한도)** — 기존 200은 과대 설정으로 한도 초과 자체를 차단하지 못해 41 초과분이 KIS 측에서 silently 거절될 수 있었음. 어제·오늘 donchian_swing 보유 종목 시세 무수신으로 ATR 트레일링이 작동 안 한 정황.
- **우선순위(HIGH → LOW)**:
  1. **보유 포지션** — `registry.all()` 순회 `state.positions.keys()` 합집합. **한도 무시 절대 보장** (`bypass_limit=True`). 손절·트레일링 감시는 KIS 한도보다 우선
  2. **익일청산 보류 대상** — `scheduler._pending_next_day_clear` set 의 ticker. **한도 무시 절대 보장**. 09:00 KRX 시장가 청산을 놓치면 위험
  3. **swing 후보** — `_collect_swing_tickers()` (donchian_swing 고정 유니버스)
  4. **모멘텀 스캔** — `scan_stocks()` 결과
  5. **VB/LTV 후보** — `_collect_breakout_tickers()`
- **drop 정책**: 잔여 슬롯(`MAX_SUBSCRIPTIONS - len(_subscriptions)`) 부족 시 후순위(swing → momentum → breakout)만 잘림. drop된 개수는 `[priority_drop] swing=X momentum=Y breakout=Z` INFO 로그 1행으로 노출.
- **중복 제거**: 같은 종목이 여러 그룹에 있으면 HIGH 순위로 1회만 subscribe. 후순위 그룹에서는 이미 구독된 종목 skip.
- **HIGH 단독 41 초과 시(이상 케이스)**: ERROR 로그 + `system_logs` 기록. 보유는 무조건 add (`bypass_limit=True`), 후순위는 0개. 운영자가 전략 비중을 줄여야 함.
- **구현 통합 지점**:
  - `src/realtime/websocket.py`: `MAX_SUBSCRIPTIONS = 41`. `subscribe(tr_id, tr_key, *, bypass_limit: bool = False)` 키워드 추가
  - `src/engine/scanner.py::subscribe_filtered_stocks(..., *, priority_groups: dict[str, list[str]] | None = None)` 키워드 추가 — 키: `positions / next_day_clear / swing / momentum / breakout`. `priority_groups=None` 이면 기존 평탄 처리(외부 호환)
  - `src/engine/scheduler.py`: `_build_priority_groups()` 헬퍼 신설, 4개 호출부(라인 254-258 / 285-291 / 307-310 / 1316-1338)가 dict 구성해 전달. 기존 `_collect_presubscribe_tickers` / `_build_subscription_source_counts` 보존
- **불변식**: HIGH 순위(보유 + 익일청산) 어떤 경우에도 drop 금지. 후순위 drop 발생 시 ERROR가 아닌 INFO (정상 운영 흐름)

### WebSocket 구독 거절 감지 (2026-05-12 E2 — 운영 가시성 + `_subscriptions` 정합성)
어제·오늘 운영 의심: KIS 한도 초과 등으로 일부 종목 구독이 거절되었으나 코드는 `msg1`의 `"ERROR"` 단일 키워드만 매칭 → 거절 사실 자체를 모른 채 `_subscriptions` set에 잔류했을 가능성. 거절 감지를 다층으로 강화해 정합성 회복 + 영구 로그로 다음 사례 추적성 확보.

- **위치**: `src/realtime/websocket.py::_handle_raw()` JSON 응답 분기 (현재 line 196-203)
- **거절 판정 조건 (하나라도 매칭)**:
  1. **rt_cd != "0"** (1순위 — KIS REST와 동일 규약). `body.get("rt_cd")` 가 None 이면 skip (Heartbeat 등 응답에는 rt_cd 없음)
  2. **msg1 키워드 (대소문자 무시, 기존 `"ERROR"` 확장)**: `ERROR / FAIL / REJECT / NOT ALLOWED / LIMIT / EXCEED / DUPLICATE / 한도 / 초과 / 이미 / 중복 / 허용되지 / 권한`
  3. msg_cd 화이트리스트는 이번 단계에서는 적용 안 함 — 거절 시 msg_cd 영구 로깅 누적되면 다음 단계에서 추가
- **거절 처리**:
  - `self._subscriptions.discard((tr_id, tr_key))` — 멱등 (이미 빠진 상태에서도 안전)
  - ERROR 로그: `"WebSocket 구독 거절: tr_id=%s, tr_key=%s, rt_cd=%s, msg_cd=%s, msg=%s"`
  - `write_log("ERROR", f"[ws_subscribe_reject] tr_id={tr_id} tr_key={tr_key} rt_cd={rt_cd} msg_cd={msg_cd} msg1={msg1}")` — Phase A1 `[kis_rejection]` 패턴 차용. fire-and-forget (비차단)
- **호출자 시그널 전달 없음** — `subscribe()` 동기 시그니처 유지. 거절은 비동기 응답으로 처리되며 다음 5분 `_scan_loop` 사이클에서 E1 우선순위 큐로 자연 재시도. **재시도 큐 구현 금지(E2 범위 밖)**
- **정상 응답 흐름(`SUBSCRIBE SUCCESS` AES iv/key 저장) 불변** — 거절 분기에서 조기 return 만 한다
- **불변식**:
  - rt_cd 누락 응답 (Heartbeat PINGPONG / 비-JSON 캐럿 구분 실시간 데이터) → 거절 처리 안 함, `_subscriptions` 영향 없음
  - 같은 `(tr_id, tr_key)` 에 대해 거절 응답 2회 → discard 멱등 안전
  - E1 우선순위 큐 / `MAX_SUBSCRIPTIONS=41` / `bypass_limit` 분기 — 영향 없음

### 거래소 라우팅 (전략별 `exchange` 파라미터)
| 값 | 의미 | 비고 |
|---|---|---|
| `KRX` | 한국거래소 단일 | 기본값. 모의(VTS) 지원 |
| `NXT` | 넥스트레이드 ATS 단일 | 실전 한정 |
| `SOR` | Smart Order Routing | KIS가 KRX/NXT 자동 분배. 실전 한정 |

`place_order`/`cancel_order` body에 `EXCG_ID_DVSN_CD`로 전송. 모의는 SOR/NXT 시도 시 KIS가 거절하므로 KRX만 사용.

### 보드(매매 시간대) 화이트리스트
각 전략 `tradable_boards` 파라미터로 매매 가능 보드를 결정:

| Board | 시간 | 전략 매핑 (기본값) |
|---|---|---|
| `pre_nxt` | NXT 프리 08:00~09:00 | VB / LTV |
| `krx_open` | KRX 동시호가 08:30~09:00 | momentum |
| `main` | KRX+NXT 메인 09:00~15:20 | momentum / VB / LTV / donchian_swing |
| `krx_after` | KRX 시간외 단일가 15:30~18:00 | (현재 미사용) |
| `post_nxt` | NXT 애프터 15:30~20:00 | VB / LTV |

**RiskManager 보드 가드**: `on_tick` 매수 신호 평가 전 `session_tracker.is_tradable(strategy_id, params)`로 활성 보드 ∩ tradable_boards 체크 — 비활성 보드에서는 신호 평가 자체 skip.

---

## 3. 전략 A: 상한가 모멘텀 상세

### 종목 선정
- 09:30 이후 등락률 순위 API로 5분 주기 필터링
- 1차 필터: 전일종가 대비 등락률 +15% 이상 상승 종목
- 2차 필터: 시가총액 1,000억 원 이상 AND 당일 거래대금 200억 원 이상
- ETF/ETN 제외 (KODEX, TIGER, 인버스, 레버리지 등 + RISE/KoAct/PLUS/TIMEFOLIO/WOORI/FOCUS 키워드)
- 최대 40개 종목으로 제한

### 매수 규칙
- **진입 조건**: 전일종가 대비 현재가가 +29.0% 이상 도달 (29% 미만 → 29% 이상 돌파 순간만)
- **제외**: 이미 상한가(+30%)에 도달한 종목은 매수 대상에서 제외
- **주문 방식**: 시장가 매수
- **투자 비중**: 할당 자금의 25% (1종목당) — 자금 부족 시 1주 fallback 동작
- **중복 방지**: 동일 종목이 이미 보유 중이거나 미체결 매수 주문이 있으면 매수 금지
- **매매 보드**: KRX_OPEN + MAIN만 (NXT 보드 비활성 — 상한가 기준이 KRX이므로 NXT 단독 +29% 의미 약함)
- **거래소 라우팅**: 기본 KRX (SOR로 변경 시 KIS가 NXT/KRX 자동 분배)

### 당일 손절
- **조건**: 매수 체결가 대비 현재가가 -7.5% 이하 도달
- **주문**: 즉시 시장가 전량 매도
- **주의**: 기준은 반드시 "매수 체결가"이지 시가가 아님

### 익일 청산 (다음 영업일 NXT 프리 08:00 → NXT 거래가능 여부로 분기)
다음 영업일 보유 종목에 대해 **NXT 거래가능 여부**로 청산 시점을 분기한다 (2026-05-11 P1(B) → 2026-05-11 P1(C) 격상).

#### 분기 기준 — KIS CTPF1002R 사전 조회 (Primary) + 시가 수신 (Fallback)
KIS MCP 4질의 결과(2026-05-11) **CTPF1002R(주식기본조회) 응답의 두 필드로 종목별 NXT 등록 여부를 사전 조회 가능**함이 확정됨:
- `cptt_trad_tr_psbl_yn` — NXT 거래종목여부 (Y/N)
- `nxt_tr_stop_yn` — NXT 거래정지여부 (Y/N)
- **파생값**: `nxt_tradable = (cptt_trad_tr_psbl_yn == "Y") AND (nxt_tr_stop_yn == "N")`

**Primary 판별**: `stock_master` 테이블(24h TTL 캐시) → `inquire_stock_basics(ticker)` (CTPF1002R)
- Lazy: 매수 진입/익일 청산 직전 조회 → miss/stale 시 KIS 호출 후 upsert
- Eager(향후): 07:50 _boot()에서 후보 일괄 갱신 (1차에서는 Lazy만)

**Fallback**: stock_master 조회 실패 또는 미보강 종목 → 기존 WebSocket 시가 수신 휴리스틱 유지
- `ticker_prices[ticker]["open_price"] > 0` (또는 `_resolve_open_price` 폴링) → NXT 거래 가능 추정
- 시가 미수신 → NXT 거래 불가 추정

#### (a) NXT 거래 가능 (`nxt_tradable=True` + 시가 수신) — 08:00 NXT 프리 지정가 청산
- 매수 체결가 대비 +10% 이상 갭상승 → 고점 -2% 트레일링 스탑 (기존 동작 유지)
- 갭상승 미달 → **지정가 매도** (직전가 -1호가, KRX 호가단위 적용)
  - `ORD_DVSN = "00"`(지정가), `EXCG_ID_DVSN_CD = "NXT"`
  - 호가단위: `src/engine/util/tick_size.py::step_down(current, steps=1)` — KRX 표준 7구간 (1/5/10/50/100/500/1000원)
  - **시장가 미사용 사유**: NXT 프리 시간대 시장가는 KIS 에서 거부될 수 있음

#### (b) NXT 거래 불가 (`nxt_tradable=False` OR 시가 미수신) — 09:00 KRX 메인 시가 확정 후 시장가 청산
- 08:00 시점에는 **청산 보류** (`_pending_next_day_clear` set 에 등록)
- **NXT 등록 사전 판별이 False면 30s 안정화도 거치지 않고 즉시 보류** (불필요한 NXT 주문 시도 0)
- 09:00 KRX 메인 시가 확정(`_confirm_breakout_open_prices(board="main")`) 직후
  `_drain_pending_next_day_clear()` 가 시장가로 일괄 정리
- 정규장 시간대이므로 시장가 OK

#### 거래소 라우팅 사전 다운그레이드
- `OrderEngine._strategy_exchange(strategy_id, ticker=...)` — ticker 인자 추가
- 전략 `exchange`가 NXT/SOR 이지만 `stock_master.get(ticker).nxt_tradable=False`이면 **KRX 강제 다운그레이드**
- `system_logs`에 `[nxt_downgrade]` prefix 1행 (strategy/ticker/원래 exchange/적용 exchange)

#### 사후 보강
- 매도 거부 시(KIS `APBK0918` + "장운영시간이 아닙니다" 등) `is_market_closed_rejection()` 가드로
  **메모리 `state.positions` 및 DB `positions` 보존** (재시도하지 않고 다음 거래 가능 시각에 자연 재트리거)
- 거부 발생 직후 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강 → 같은 종목 재 NXT 호출 방지
- **시가 미수신 시 `high_since_buy` 폴백 + 갭률 0% 즉시 청산 경로는 제거** (전일 고가 혼입으로 좀비 포지션 위험)
- **시장가 호가 불가 거부(`is_market_order_disallowed`, APBK1943 "시장가호가불가" 등) Phase C, 2026-05-11**: 시장가 매도 경로(`limit_price=0`)에서 `step_down(현재가, 5)` 지정가 1회 폴백. 폴백 실패 시 메모리/DB positions 보존, cooldown 등록 안 함(청산 의무) → 다음 사이클 재트리거. 2026-05-11 계양전기(012200) 09:00:21 매도 ×3 + 수동 매도 ×2 실패 사고 대응

### 트레일링 스탑 상세
- NXT 프리 시가 이후 고점을 실시간 추적
- 현재가가 고점 대비 -2% 이하로 떨어지면 시장가 매도 트리거
- 수식: `(고점 - 현재가) / 고점 * 100 >= 2.0` 이면 매도

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 25%
- 일일 최대 손실 한도: 할당 자금의 5% → 도달 시 당일 매매 중단
- 동시 보유 종목 수: 최대 4종목

---

## 4. 전략 B: 변동성 돌파 상세

### 핵심 개념
- **노이즈 비율** = 1 - |Close - Open| / (High - Low)
- **동적 K값** = 최근 20일 평균 노이즈 비율
- **보드별 매수 목표가** = 보드 시가 + (전일 Range × K값 × 보드별 K 곱)

### 보드별 시가/타겟 분리 (Phase 5 Q1=C)
보드마다 시가가 다르므로 별도로 추적:
- `_targets[ticker]["boards"]["main"]` ← KRX 09:00 시가 + (전일Range × K × `k_value_krx_main`)
- `_targets[ticker]["boards"]["pre_nxt"]` ← NXT 프리 첫 거래 시가 + (전일Range × K × `k_value_nxt_pre`)
- `_targets[ticker]["boards"]["post_nxt"]` ← NXT 애프터 첫 거래 시가 + (전일Range × K × `k_value_nxt_post`)
- 보드별 K 곱 기본값 1.0. NXT는 거래대금이 KRX의 ~10%로 변동성 큼 → 1.2~1.5로 보수 운용 권장

### 종목군
- 코스피 + 코스닥 전체에서 거래대금/시총 조건 필터
- 조건: 시가총액 1,000억 원 이상 AND **전일** 거래대금 200억 원 이상 (Settings에서 변경 가능)
  - 거래대금은 거래량순위 API 응답의 `prdy_vol × (stck_prpr - prdy_vrss)`로 산출 → 시간 의존 제거
- ETF/ETN 제외
- 최대 100종목

### 데이터 준비 (07:50 부트 시점)
- 각 종목의 최근 22일 일봉 데이터(시/고/저/종) 조회 (KIS FHKST03010100, 100일 응답)
- candles[0]이 오늘이면 candles[1]을 "전일"로 사용 (장 시작 전 빈/부분봉 방어)
- 종목별 K값 계산 + 전일 Range로 `target_offset_base` 산출
- `prev_range == 0` 또는 `target_offset_base == 0` 종목은 skip
- 전일 종가를 `scanner.ticker_prev_close`에 사전 등록

### 시가 확정 + 매수 규칙
- 보드 진입 시점에 `_confirm_breakout_open_prices(board=...)` 호출 → 보드별 시가 확정 + Target 계산
- **진입 조건**: 현재가 >= 활성 보드의 Target_Price 돌파 순간 (이전 틱 < target AND 현재 틱 >= target). 보드별 `_prev_price[ticker][board]` 분리
- **주문 방식**: 시장가 매수
- **투자 비중**: 할당 자금의 10% (1종목당) — 자금 부족 시 1주 fallback
- **동시 보유**: 최대 10종목
- **매매 보드**: PRE_NXT + MAIN + POST_NXT (Q3=A 야간 매매 활성)
- **거래소 라우팅**: 기본 KRX. SOR 권장(NXT/KRX 자동 분배)

### 손절
- **조건**: 매수 체결가 대비 -3%
- **주문**: 즉시 시장가 전량 매도

### 강제 청산 — 보드별 분리
- **15:20 KRX 메인 매수 중단 + 강제 청산**: `tradable_boards`에 POST_NXT가 **없는** 전략의 종목만 청산. POST_NXT 활성 전략은 19:50까지 보유 유지
- **19:50 NXT 애프터 매수 중단**: 모든 활성 전략 `buy_disabled = True`
- **20:00 NXT 애프터 종료**: 보유 종목은 다음 영업일까지 자동 이월(VB는 오버나잇 거부 원칙이지만 POST_NXT 활성 운영 시 익일 청산은 별도 검토 필요)

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 10%
- 일일 최대 손실 한도: 할당 자금의 5%

---

## 5. 전략 C: 롱테일 변동성 돌파 상세

VB와 진입 로직 동일 + 상한가 도달 시 익일 청산 모드로 전환해 긴 꼬리(롱테일) 추구.

### VB 대비 차이
- 추가 진입 필터: 전일대비 ≥ `min_prdy_rate`(기본 5%)
- 연속상한가 종목 제외 (`exclude_consecutive_limit`, 기본 2일 — 전일 기준 N일 연속 +25%↑면 후보 제외)
- 상한가 도달(+29%) 시 → 익일 청산 모드 전환(`_limit_up_reached` set)
- **2단계 청산**:
  - 당일 모드(상한가 미도달): 손절 -3%, 15:20 강제 청산 보류 가능(POST_NXT 활성 시 19:50까지)
  - 상한가 모드: 손절 -5%, 다음 영업일 NXT 프리 시가에서 갭상승 +10% → 트레일링 -2% / 그 외 즉시 매도
- 보드별 K값 분리는 VB와 동일

### 매매 보드 / 거래소 라우팅
VB와 동일.

---

## 6. 전략 D: 20일 신고가 스윙 (donchian_swing) 상세

### 개념
멀티데이 추세추종(터틀 스타일). 한 번 추세 잡힌 종목은 끝까지 따라간다는 클래식 추세 전략.

### 종목군
- **코스피200 + 코스닥150 고정 유니버스** (`scanner.KOSPI_200_TICKERS` + `KOSDAQ_150_TICKERS` 합집합) — 거래량순위 API 미사용(추세추종 부적합)
- 시가총액 컷만 사후 적용 (`min_market_cap`, 기본 3,000억)
- 거래대금 컷은 prepare()의 `volume_multiplier`(기본 1.5×)에서 일원화

### 진입 조건 (07:50 prepare)
1. 어제 종가가 최근 20일 신고가 돌파 (`donchian_period`)
2. 어제 종가가 60일 EMA 위 + EMA 우상향 (`long_ma_period`)
3. 어제 거래대금 ≥ 20일 평균 × `volume_multiplier`(1.5)
4. ATR(14) 산출

### 매수 규칙
- **시점**: 다음 영업일 09:05 ~ 09:30 사이 시장가 (1종목당 1회만)
- **갭 스킵**: 시가 갭상승 +3% 이상이면 진입 스킵 (`gap_skip_threshold`, 추격 매수 회피)
- **투자 비중**: 할당 자금의 20% (1종목당)
- **동시 보유**: 최대 5종목
- **매매 보드**: MAIN만 (KRX 메인 한정)
- **거래소 라우팅**: 기본 KRX

### 청산
- **하드 손절**: 매수가 대비 -7%
- **ATR×2 Chandelier 트레일링**: `high_since_buy − ATR(14) × 2` 이하로 떨어지면 매도
- **시간 청산 없음**: 15:20 강제 청산 제외 (`check_force_clear()` 빈 리스트)
- 평균 5~15 영업일 보유 → DB `positions` 영속화로 일자 넘어 유지

#### high_since_buy 일봉 폴백 (E3, 2026-05-12)
- **`recompute_held_atr()` 직후 또는 함께 `high_since_buy` 일봉 보정** — 매수일 다음 영업일~전영업일까지의 KIS 일봉 high max로 복구. 시세 미수신 누적으로 chandelier 트레일링 손절선이 매수가 부근에 동결되는 결함 차단 (2026-05-12 이마트 사례)
- 대상: **donchian_swing 보유 포지션만** (chandelier 트레일링 사용 전략). 헬퍼는 일반화하되 호출은 donchian만 — 다른 전략 확장은 별도 단계
- 보정 조건: `pos.buy_date < today_kst` 인 보유 포지션만. 매수일 당일/미래일은 skip (당일은 `buy_price`가 진실, 미래일은 비정상 → WARNING)
- 보정값: `max(pos.high_since_buy, max(eligible_daily_highs))` — 일봉 응답 후 매수일 < bsop_date < today 범위 필터 → 일별 `stck_hgpr` max
- DB 영속화: 보정값이 기존 high_since_buy 초과 시 `update_high(ticker, new_high)` (또는 `save_position`)로 UPDATE + `system_logs` `[high_since_buy_recover]` prefix 1행
- 안전 가드: 종목별 sequential await (Rate Limit), 일봉 fetch 예외/빈 응답 → 해당 종목 skip + 다른 종목 영향 없음
- `risk.py:72` 실시간 시세 기반 `high_since_buy` 갱신은 그대로 유지 — 이건 boot 시점 1회 복구만

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 20%
- 일일 최대 손실 한도: 할당 자금의 8%

---

## 7. 공통 규칙

### 부분 체결 처리
- 시장가 주문도 호가 잔량 부족 시 부분 체결 가능
- 부분 체결 시: trade_history에 PARTIAL 상태로 기록, 체결된 수량만 반영
- 미체결 잔량: 30초 대기 후 미체결이면 잔여 주문 취소
- 손절 시 부분 체결: 체결된 부분은 손절 완료로 처리, 잔여는 재주문

### 체결 기반 포지션 관리
- **체결통보 WebSocket 구독 필수**: 시세(H0UNCNT0 KRX+NXT 통합) 외에 체결통보(실전: H0STCNI0, 모의: H0STCNI9)를 반드시 구독해야 함
- 통합 시세 `H0UNCNT0`로 KRX/NXT 거래가 같은 콜백으로 흘러옴 — 거래소 식별은 체결통보 `ODER_KIND` 필드에서
- **장운영정보 H0UNMKO0 구독** (실전 한정): 대표 종목(`005930`) 1개로 보드 전환 코드(`MKOP_CLS_CODE`) 실시간 수신
- 주문 접수 시 pending_buys에 등록 (중복 주문 차단)
- **체결통보 수신 시** 포지션 등록/제거 (주문 직후가 아님 — 체결 확인 전 포지션 등록하면 안 됨)
- 주문번호 매핑(`_order_qty`/`_order_strategy`/`_order_ticker`) 등록은 `place_order` 응답 직후 동기 영역에서. `await insert_trade` 진입 전 (시장가 즉시체결 race 방지)
- 체결통보 선행 race 가드: `_completed_orders` set + UPDATE 0건 보정 INSERT
- 기동 시: KIS 주문체결내역 API + DB trade_history.strategy로 포지션/미체결 복구
- 매수일자(buy_date) 기반 익일 청산 판정 (시간 기준이 아님)

### 매수 안전장치
- **종목코드 형식 비대칭**: 진입은 6자리 숫자만(`isdigit`) — ETF·신주인수권 차단. 사후처리(체결통보·잔고 sync)는 6자리 영숫자(`isalnum`) 허용
- **매수가능 캐시**: 60초 TTL — KIS `get_buyable()` 호출을 매 틱 → 분당 1회로 축소
- **잔고부족 매수 락**: 900초 — `is_insufficient_cash` 응답 또는 `max_buy_quantity≤0` 시 다음 잔고 sync까지 매수 차단
- **per-ticker low_funds cooldown**: 900초 — `calc_buy_quantity()<=0`인 종목 매 틱 반복 호출 차단
- **매도 잔고부족 즉시 break**: `is_insufficient_quantity` 응답 시 3회 재시도 생략 + 메모리·DB positions 정리

### 스케줄 — KRX/NXT 통합 운영 (08:00~20:00)

| 시각 | 동작 |
|------|------|
| 07:45 | 자동 매매 시작 (`AUTO_START` + DB 재확인. 주말+공휴일 KIS chk-holiday로 자동 건너뜀) |
| 07:50 | 프로세스 기동, OAuth 토큰 갱신, DB 포지션/설정 복구, 전략별 자금 분배, 전략 prepare(일봉/K값/전일종가/도치안 단계별 통계) |
| 07:55 | WebSocket 연결, **체결통보(H0STCNI0/9) 구독** + **통합 장운영정보(H0UNMKO0/005930) 구독** + 사전 구독(돌파+스윙+보유 합집합) |
| 08:00 | NXT 프리 진입 — 익일 청산 백그라운드(30초 안정화 후 NXT 시가 청산) + 돌파 시가 확정(`board="pre_nxt"`) + VB/LTV PRE_NXT 매매 시작 |
| 09:00:05 | KRX 메인 시가 확정 — VB/LTV `board="main"` 별도 시가 + KRX 09:00 시가 + (전일Range × `k_value_krx_main`) Target_Price 계산 → MAIN 매매 진입 |
| 09:05~09:30 | donchian_swing 진입창 — 시장가 1주문/종목, 갭 +3%↑ 스킵 |
| 09:30 | 모멘텀 종목 스캔 시작. 5분 주기 `_scan_loop` 시작(돌파+스윙+보유 합집합 재구독) |
| 15:20 | KRX 메인 신규 매수 중단 + KRX 메인 강제 청산(`_force_clear_main_only`) — POST_NXT 활성 전략 종목은 보유 유지 |
| 15:30 | KRX 메인 마감 → NXT 애프터 전환. VB/LTV는 POST_NXT에서 매매 계속 |
| 19:50 | NXT 애프터 신규 매수 중단 + 전략수정 AI자문 생성(OpenAI → `parameter_recommendations`) |
| 20:00 | NXT 애프터 종료, WebSocket 구독 해제 |
| 20:10 | 전략별 + 합산 일일 정산, daily_performance 기록, 일일 로그 분석 리포트 생성(OpenAI → `daily_log_reports`), 프로세스 Sleep |

### 야간 매매(POST_NXT 15:30~20:00) 운용 원칙 — Q3=A 활성
- 사용자 부재 시간대 사고 위험 인지 — Settings 상단 amber 경고 배너 노출
- 손절·트레일링은 실시간 작동
- NXT 거래대금 KRX 대비 ~10%로 변동성 큼 → 보드별 K 곱(`k_value_nxt_post`) 1.2~1.5 보수 운용 권장
- 비활성화 원하면 Settings 페이지에서 해당 전략의 `tradable_boards`에서 POST_NXT 해제

### API Rate Limit 대응
- 초당 20건 제한 준수
- 일괄 매도(손절 동시 발생) 시 asyncio.Semaphore로 큐잉
- 주문이 지연되더라도 순차 실행 보장

### 환경 설정
- .env의 `KIS_ENV`로 실전/모의 전환 (인증 정보 자동 매핑)
- 모든 TR_ID는 `settings.get_tr_id()`로 환경별 자동 변환
- **모의(VTS)는 KRX만 지원** — SOR/NXT는 실전 한정. 모의에서 NXT/SOR 시도 시 KIS가 거절
- 실전 전환 시 반드시 팀장 승인 필요

### 전략별 잔고/실적 관리
- trade_history: strategy 컬럼으로 전략별 거래내역 분리
- daily_performance: (date, strategy) 복합PK로 전략별 + 합산 실적 기록
- 정산 시각 변경 영향: total_asset 계산 시점이 16:10 → 20:10로 이동, 종가가 NXT 20:00 마지막 체결가가 됨

### 시간 상수 (`src/engine/scheduler.py`)
| 상수 | 값 | 의미 |
|---|---|---|
| `TIME_AUTO_START` | 07:45 | 자동 매매 시작 |
| `TIME_BOOT` | 07:50 | 프로세스 부트 |
| `TIME_PRESUBSCRIBE` | 07:55 | 사전 구독 |
| `TIME_PRE_NXT_OPEN` | 08:00 | NXT 프리 진입 (익일 청산 + VB/LTV PRE_NXT) |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | KRX 메인 시가 확정 |
| `TIME_SCAN_START` | 09:30 | 모멘텀 스캔 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | KRX 메인 매수 중단 + 강제 청산 |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감 → NXT 애프터 전환 |
| `TIME_NXT_POST_BUY_STOP` | 19:50 | NXT 애프터 매수 중단 |
| `TIME_RECOMMENDATION` | 19:50 | AI자문 생성 |
| `TIME_NXT_POST_CLOSE` | 20:00 | NXT 애프터 종료, unsubscribe |
| `TIME_SETTLEMENT` | 20:10 | 정산 + 일일 로그 분석 |
| `NEXT_DAY_STABILIZE_SECS` | 30 | 익일 청산 NXT 프리 시가 안정화 |
| `SESSION_TICK_INTERVAL` | 30 | SessionTracker 보드 전환 감시 주기 |

### 위험 요약 (실전 전환 전 검토)
1. **VTS 검증 불가** — SOR/NXT는 실전 한정. 카나리 운영 어려움
2. **NXT 거래대금 ~10%** — 시가 흔들림이 매매 신호 노이즈로 작용 가능
3. **야간 매매 모니터링 부재** — 사용자 부재 시간대 사고 위험. POST_NXT는 명시 토글로만 활성
4. **정산 시각 이동 영향** — daily_performance 'date' 의미, EC2 자동 재시작 정책, 익일 부팅 시각 모두 영향
5. **종목 적격성** — NXT 거래 가능 종목이 KRX 전 종목인지 일부인지 명세 미기재. 운영 데이터로 검증 필요

### AI자문 고도화 (Phase J4, 2026-05-12)

기존 19:50 AI자문은 `recommended_params` 화이트리스트 키만 권고했으나, **전략별 자산배정(weight)** 과 **로직/파라미터 추가·삭제** 같은 구조적 변경은 권고 채널이 없었다. J4 에서 두 채널을 신설하되 **자동 적용은 절대 없음** — 모두 운영자 수동 검토 후 명시적 apply.

**DB 스키마 확장 (`parameter_recommendations`)**:
- `recommended_weight NUMERIC` — AI 추천 전략 weight (0.0~1.0). null = 변경 권고 없음
- `code_review_notes TEXT` — 로직/파라미터 추가·삭제 자유 텍스트 자문. 최대 2000자. 자동 적용 없음
- `applied_weight NUMERIC` — 사용자가 apply 시점에 실제 적용한 weight (트래킹용)

**recommendation_engine 컨텍스트 확장**:
- `current_weight` (자기 전략 weight) + `peer_weights` (다른 enabled 전략 weight dict) + `peer_metrics` (다른 전략 최근 성과 dict) 를 user_payload 에 추가
- 프롬프트에 명시: ① 다른 전략 weight + 성과 종합해 자기 비중 변경 권고 (0.0~1.0). 합계 1.0 근접은 **운영자가 apply 시점에 책임** ② 화이트리스트 외 신규 파라미터 도입 또는 폐기 제안을 자유 텍스트로 (최대 2000자, 코드 자동 변경 없음)

**검증 헬퍼 (`_validate_recommendations` 확장)**:
- `recommended_weight`: float 캐스트 + `0.0 <= x <= 1.0` 범위 검증. 범위 외면 None 으로 무시 + WARNING 로그
- `code_review_notes`: str 캐스트 + `len(text) > 2000` 이면 2000자로 잘라냄. 비-str 이면 None

**apply 흐름 (`POST /api/recommendations/{id}/apply`)**:
- body 신규 옵션: `apply_weight: bool = False`
  - True 일 때 `recommended_weight == None` 이면 400 (`"적용할 weight 가 없습니다"`)
  - True + 유효한 weight 면 `strategy_config.weight` 갱신 (`save_weights({strategy_id: recommended_weight})`) + `registry.update_weights()` 메모리 반영 + DB `parameter_recommendations.applied_weight` 갱신
  - **`allocate_funds()` 즉시 재호출 금지** — 다음 `_boot()` (다음 영업일 07:50) 에서 자연 반영
- 기존 `apply_keys` 와 `apply_weight` 동시 가능 — 둘 다 처리
- 응답 데이터에 `applied_weight: float | null` 포함

**프론트엔드 (`Recommendations.tsx`)**:
- **자산 배정 카드** (recommended_weight 가 null 아닐 때만): 현재 weight → 추천 weight + 변경량(%p) + "weight 적용" 체크박스. 체크 시 apply body 에 `apply_weight: true` 포함. 적용 후 `applied_weight` 표시 + amber 안내 "다음 영업일부터 반영"
- **로직/파라미터 자문 카드** (code_review_notes 가 null 아닐 때만): 자유 텍스트 (whitespace-pre-wrap, max-height + overflow-y-auto). "검토 완료" 토글은 클라이언트 상태(localStorage 선택)
- 기존 params 적용 카드는 그대로 유지 — 변경 없음

**안전 불변식**:
- weights 자동 적용 절대 금지 — `apply_weight=true` 명시 시에만
- code_review_notes 텍스트 기반 코드 자동 변경 절대 금지 — 정보 표시만
- `allocate_funds()` 시그니처 그대로, 즉시 재호출 안 함 (다음 _boot 반영)
- 기존 `apply_keys` 흐름 + J1~J3 + I1~I3 + 다른 Phase 영향 없음
