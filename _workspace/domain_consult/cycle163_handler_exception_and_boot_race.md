# 사이클 163 domain-expert 자문 — H0STCNI0 핸들러 예외 + 2차 _boot stock_master 0건 race

작성자: team-leader (트레이더 시각 자체 자문)
일자: 2026-06-18
범위: 의제 #5 (HIGH) + 의제 #6 (MEDIUM)

## 1. 운영 사고 진단 매트릭스

### 1.1 6/18 08:22~08:27 KST 정밀 로그 chain (Supabase MCP READ-ONLY 추적)

```
08:22:49.443  [boot_preissue] label=sub 사전 발급 완료
08:22:49.565  [boot_preissue] label=gold 사전 발급 완료
08:22:51.365  [cash_usage_ratio] net_asset=1289715 ratio=1.00 available=1289715
08:22:51.520  ERROR VB 유니버스 0종목 — stock_master 0건 (1차 prepare)
08:22:51.578  WARNING [vb_prepare_retry] cap=1/3 — 30초 대기
08:23:22.323  ERROR VB 유니버스 0종목 (재시도 1차)
08:23:22.402  WARNING [vb_prepare_retry] cap=2/3
08:23:52.949  ERROR VB 유니버스 0종목 (재시도 2차)
08:23:53.021  WARNING [vb_prepare_retry] cap=3/3
08:24:23.518  ERROR VB 유니버스 0종목 (재시도 3차 = 모두 실패)
08:24:24.004  ERROR LTV 유니버스 0종목 (재시도 hook 없음)
08:24:24.760  ERROR donchian 유니버스 0종목
08:24:25.268  ERROR BFB 유니버스 0종목
08:24:48.347  INFO DB 포지션 복구: 알테오젠 1주 @ 367000 (익일청산)
08:24:48.600  INFO 기동 완료
08:24:51.464  ERROR VB 0종목 (2차 _boot prepare 진입)  ← 본 의제 #5 핵심
08:24:51.539  WARNING [vb_prepare_retry] cap=1/3
08:25:22.013  ERROR VB 0종목 (2차 cap=2/3)
08:25:52.698  ERROR VB 0종목 (2차 cap=3/3)
08:26:23.307  ERROR VB 0종목 (모두 실패)
08:26:23.715  ERROR LTV 0종목
08:26:24.389  ERROR donchian 0종목
08:27:16.303  INFO [full_universe_load_summary] total=2768 fetched=0 skipped_ttl=2696
```

### 1.2 진짜 root cause — 사이클 158 hook의 본질적 한계

운영 추적이 드러내는 사실은 *2개*다.

**사실 (a) — `_full_universe_load_task_loop`은 거의 5분 소요**:
- 08:22:49 boot 시작 시 task 생성됨 → 즉시 1회 실행 분기 진입
- 08:27:16 emit `[full_universe_load_summary]` = **4분 27초 소요**
- `total=2768`이지만 `fetched=0 / skipped_ttl=2696` — 모든 ticker가 24h TTL fresh로 skip
- 즉 stock_master DB는 이미 적재 완료 상태였음 (`refreshed_at` 어제 적재 영속). KIS 호출은 `is_stale` 체크만 ticker별 약 0.1초씩 누적 = 4분.

**사실 (b) — `list_by_filter`는 raw.hts_avls 기준이라 0건 반환 정상**:
- 운영 DB 실측 (`raw.hts_avls ≥ 1000억` AND `raw.acml_tr_pbmn ≥ 500억`) = **0건**
- 사실 (a)와 무관 — stock_master는 이미 채워져 있고 raw.hts_avls 3,566 종목 보유
- 그러나 raw.acml_tr_pbmn은 253 종목만 (= 어제 16:10 KST basics refresh task의 흔적)
- 장 시작 *전* 08:22 시점은 당일 누적 거래대금이 아직 0이거나 미보강 → 거래대금 임계 통과 0건

즉 사이클 158 hook이 90초 (30s × 3회) 기다린 것은 **race 회피 효과 0** — 어차피 4분 27초까지 기다려도 raw.acml_tr_pbmn은 갱신되지 않는다 (basics refresh는 16:10 KST 1회/일).

### 1.3 결정적 해석 — 결함의 진짜 위치는 "필터 임계"가 아니라 "장 시작 전 후보 풀 정의"

장 시작 *전* (07:50 _boot ~ 09:00 KRX open) 시점의 매수 후보 풀은 본질적으로 *전일* 거래대금에 기반해야 한다. 하지만 현 코드는:

- `list_by_filter(min_trade_amount=...)` → `raw.acml_tr_pbmn` 비교 (사이클 108)
- 그런데 `raw.acml_tr_pbmn`은 *오늘 누적*도, *어제 종가 기준 누적*도 명확치 않은 영역
- 사이클 65 `_get_acml_tr_pbmn` 헬퍼는 *전일* 거래대금 의도였으나 raw 키 자체가 KIS FHKST01010100 응답이며 *호출 시점* 누적치

→ 실제로는 16:10 basics refresh task가 마지막 호출 시점 (어제 종가 + 그날 누적 거래대금) 으로 raw 동결 → 6/18 08:22 시점의 raw.acml_tr_pbmn은 *6/17 종가 누적 거래대금*. 그러므로 본래는 정상 동작했어야 함.

운영 실측 `mcap_1000eok_plus_raw=6` (hts_avls 기준 시총 1000억 이상이 단 6 종목) = 명백한 *데이터 손상* 시그널. KIS `inquire_stock_basics`의 hts_avls (백만원) 단위 환산이 어딘가에서 0배 또는 미입수. 사이클 116 단위 환산은 KRX `MKTCAP` (원) 영역만 다루므로 본 결함과 별개.

## 2. 의제 #5 (HIGH) — 시정 방향 결정

### 2.1 옵션 매트릭스

| 옵션 | 내용 | 위험 | 효과 |
|------|------|------|------|
| A | `_boot()` 영역 prepare 호출 *전* `stock_master.count_active()` 가드 + 0건 시 대기 | LOW | race 차단만 — 본 사고는 race 아님 (skipped_ttl=2696) → 효과 부분 |
| B | 5 전략 prepare 영역 사이클 158 자동 재시도 hook 통일 (LTV/donchian/BFB/VCP) | LOW | VB와 동일 hook → 동일 한계 (90초 부족) — 효과 부분 |
| C | A + B 통합 | LOW | 효과 부분 |
| D | sub-list 시그너처 변경 → master_raw 1순위 + raw 2순위 chain (사이클 153 패턴) | MEDIUM | hts_avls 손상 시점에도 master_raw.prdy_avls_scal (시총 억원) 활용 가능 → 429 종목 대비 raw 6 종목 → 회복 |
| **E** | **C + D 통합** | **MEDIUM** | **race 차단 + 데이터 손상 회복 영역 동시** |

### 2.2 권고 — 옵션 C로 우선 시정 + D는 사이클 164+ 인계

본 사이클 발주는 #5 + #6 통합. D는 `list_by_filter` 시그너처 변경 + 3 전략 호출 영역 동기화 → 별도 사이클이 안전하다.

**옵션 C 세부**:

#### 시정 1: `boot_manager.boot()` 영역 prepare *전* count 가드

```python
# boot_manager.py 영역
# 전략별 prepare 호출 전 stock_master 적재 대기 (사이클 163)
from src.db.stock_master import count_active
from asyncio import sleep as _asleep

BOOT_PREPARE_STOCK_MASTER_WAIT_SECS = 300  # 5분 cap (lifecycle race 차단)
BOOT_PREPARE_STOCK_MASTER_POLL_SECS = 10

waited = 0
while waited < BOOT_PREPARE_STOCK_MASTER_WAIT_SECS:
    try:
        cnt = await count_active()
    except Exception:
        cnt = 0
    if cnt > 0:
        if waited > 0:
            logger.info("[boot_prepare_wait] stock_master count=%d 영역 (waited=%ds)", cnt, waited)
        break
    await _asleep(BOOT_PREPARE_STOCK_MASTER_POLL_SECS)
    waited += BOOT_PREPARE_STOCK_MASTER_POLL_SECS
else:
    logger.warning(
        "[boot_prepare_wait_timeout] stock_master 0건 — %ds 대기 후 prepare 진행 (graceful)",
        BOOT_PREPARE_STOCK_MASTER_WAIT_SECS,
    )

for strategy in scheduler.registry.enabled():
    try:
        await strategy.prepare()
    except Exception:
        logger.exception("전략 prepare 실패: %s", strategy.strategy_id)
```

#### 시정 2: 5 전략 prepare 자동 재시도 hook 통일

VB와 동일한 hook (cap 3회 + 30초 sleep) 을 LTV/donchian/BFB/VCP에 추가. 단 `_scan_universe()` 호출 *직후* 0건이면 재시도, 1건 이상이면 break.

각 전략 `prepare()` 본체 구조:
```python
tickers = await self._scan_universe()
for retry_attempt in range(3):
    if tickers:
        break
    logger.warning(
        "[<sid>_prepare_retry] stock_master 0건 — 30초 후 재시도 (cap=%d/3)",
        retry_attempt + 1,
    )
    await asyncio.sleep(30)
    stats = _empty_scan_stats()
    self._scan_stats = stats
    self._reset_funnel_steps()
    tickers = await self._scan_universe()
```

### 2.3 영속 의무 매트릭스 (사이클 163 영구 확인)

- 사이클 32 R4 보유/익일청산 절대 보호 — 본 시정 영향 0 (prepare 영역 한정)
- 사이클 38 명문화 — scanner 매수 진입 전 한정, hot path 무관
- 사이클 51 boot_manager 패턴 — 본체 영역 위임 보존
- 사이클 88 G-REJECT graceful — count_active 예외 시 cnt=0 폴백
- 사이클 106 lifecycle race 차단 — `_full_universe_load_task_loop` start() 즉시 1회 영속
- 사이클 134 task_loop_helper — stagger (0/240/480/720) 영속 (변경 0)
- 사이클 158 VB hook 영속 — 다른 4 전략 동일 패턴 답습

## 3. 의제 #6 (MEDIUM) — H0STCNI0 핸들러 예외 원인 진단

### 3.1 KIS 정본 검증 (KIS MCP `ccnl_notice`)

H0STCNI0 메시지 26 컬럼:
```
CUST_ID, ACNT_NO, ODER_NO, OODER_NO, SELN_BYOV_CLS, RCTF_CLS,
ODER_KIND, ODER_COND, STCK_SHRN_ISCD, CNTG_QTY, CNTG_UNPR,
STCK_CNTG_HOUR, RFUS_YN, CNTG_YN, ACPT_YN, BRNC_NO, ODER_QTY,
ACNT_NAME, ORD_COND_PRC, ORD_EXG_GB, POPUP_YN, FILLER, CRDT_CLS,
CRDT_LOAN_DATE, CNTG_ISNM40, ODER_PRC
```

`tr_key=` 빈 영역은 정상 — H0STCNI0은 HTS ID 단위 push이고 payload 첫 필드는 종목코드/계좌가 아닌 `CUST_ID(HTS_ID)`. `encrypted=True` = AES-256-CBC 영역. 핸들러 예외는 메시지 디코딩이 아닌 **콜백 (`_on_execution`) 내부 예외**.

### 3.2 6/17 12:43:09 KST 핸들러 예외 흐름 정밀 추적

```
12:43:09.413  INFO 롱테일 매수 신호 [main]: 알지노믹스(476830) 109900 >= 109795, K=0.6190
12:43:09.633  INFO BUY 주문 완료: 476830 1주 @ 0 (주문번호 0001521700)
12:43:09.641  INFO 매수 체결 → 포지션 등록: 알지노믹스(476830) 1주 @ 110000 (전략: LTV)
12:43:09.724  INFO 매수 주문 접수: 476830 1주 @ 109900 (주문번호 0001521700, 전략 LTV)
12:43:09.876  ERROR [callback_exception] handler=_on_execution ticker=476830 order_no=0001521700
12:43:09.880  ERROR WebSocket 메시지 핸들러 예외: tr_id=H0STCNI0 tr_key= encrypted=True
```

**해석**:
- `12:43:09.633` REST 응답 `place_order` 도착
- `12:43:09.641` (REST + 8ms) — 체결통보 진입 = `_handle_buy_fill` 시작 → 포지션 등록 완료
- `12:43:09.724` (포지션 등록 + 83ms) — `execute_buy` 측의 `insert_trade(PENDING)` 완료
- `12:43:09.876` (포지션 등록 + 235ms) — `_handle_buy_fill` 내부 어디선가 예외

이 순서는 `_handle_buy_fill` line 970 ~ 1043 (전량 체결 분기, ordered_qty==total_filled==1) 에서 예외 발생을 가리킨다.

### 3.3 가능 원인 후보

| # | 위치 | 가능성 | 근거 |
|---|------|------|------|
| A | line 987 `update_trade_status(price=price)` → Supabase 예외 | LOW | INFO 로그가 거기까지 emit 되지 않음 |
| B | line 991~ `affected==0` 분기 진입 → `insert_trade(COMPLETED)` UniqueViolation | MEDIUM | 12:43:09.641 (체결통보) > 12:43:09.724 (PENDING INSERT) 영역 — race 정합 |
| C | line 1012 except 분기 → `_update_trade_status_by_order_no` 내부 예외 | LOW | 함수 자체는 try/except 으로 보호됨 |
| **D** | **line 1032 `save_position` → Supabase HTTP/2 ConnectionTerminated 또는 timeout** | **HIGH** | 사이클 134 task_loop_helper 도입 사유 = 동시 발화로 Supabase HTTP/2 폭주. 6/17 12:43 시점은 자동 매매 중간 → DB 부하 정합 |

### 3.4 결정적 진단 — 시그니처는 별 의미 없고, callback 내부 raise 영구 영속이 본질

사이클 88 G-REJECT-1 영구 영속 의무에 따라 `_on_execution` 콜백 예외는 **`raise` 영속** → `_handle_raw` 외부로 전파 → `_receive_loop`로 → WebSocket 재연결 자연 발화. 이 정책은 의도이며 변경 금지.

운영 사고 시점 결과는:
- 6/17 12:43:09 핸들러 예외 1회 → `_receive_loop` 예외 → WS 재연결 시도
- 매수 자체는 KIS 측에서 정상 체결 완료 (알지노믹스 1주 @ 110000)
- 포지션 메모리 등록도 정상 (line 969 INFO 발화 완료)
- 누락된 것: `save_position` DB INSERT, `_update_trade_status` COMPLETED 갱신 중 일부

→ 결함의 영향은 trade_history `price` 정합 일부 손상 + DB positions 미동기화 가능성. 그러나 알지노믹스가 EC2 재기동 후 `_boot()` 영역에서 `load_db_positions` 영역 복구되지 않은 흔적이 6/18 08:24:48 운영 로그에 있다 ("DB 포지션 복구: 알테오젠 1주 @ 367000 (익일청산, 전략 volatility_breakout)" — 알지노믹스 부재). 즉 6/17 12:43 callback 예외로 알지노믹스 positions DB row 실종.

### 3.5 시정 방향 — 가시화 강화 + DB 부하 graceful

`_handle_buy_fill` 영역 전량 체결 분기를 try/except 3 영역 분리:

1. `update_trade_status` (PENDING → COMPLETED 갱신)
2. `insert_trade` (race 보정 COMPLETED INSERT)
3. `save_position` (positions DB INSERT)

각 영역 예외는 `[buy_fill_db_error] step=<X> ticker=... order_no=... err=...` ERROR + system_logs INSERT (가시화). 메모리 positions 등록은 이미 완료이므로 callback raise하지 않고 **graceful 완료** — `_pending_buy_orders`/`_order_strategy` 등 매핑 정리는 보존. 다음 `_sync_positions_from_balance()` (15분 주기) 가 DB 정합 회복.

단, 사이클 88 G-REJECT-1 영속 의무 (callback raise → 재연결) 영역은 **다른 callback 영역에는 적용 영속**. `_handle_buy_fill` 영역만 graceful 전환 — DB INSERT race는 재연결로 해결되지 않기 때문.

### 3.6 사이클 161 (BUY price 정합) 영역과의 인과

사이클 161 시정은 `update_trade_status(price=price)` 인자 명시 = `_handle_buy_fill` line 987~990 영역. 본 사고 (6/17 12:43)는 사이클 161 *배포 직전* 시점 (사이클 161 commit 시각 미확정, 사이클 162는 6/18 작성). 6/17 BUY 3 종목 (-100/-100/-500원 차이)은 사이클 161 시정 *전* 운영 결함의 흔적 = 본 사고와 동일 패턴이지만 **원인은 다름**:

- 6/17 결함 #4 = `price=` 인자 누락 → trade_history.price 미갱신 → 33,400원 vs HTS 33,350원 -50원
- 6/17 12:43 callback 예외 = save_position 또는 update DB 영역 예외 → positions DB 미동기화

**결론**: 사이클 161은 결함 #4 시정 영역 그대로 영속. 본 사이클 163은 **3 영역 try/except 분리 + 가시화 강화**로 callback 예외 후속 영향 차단.

## 4. 시정 영역 사양 (TDD Red)

### 4.1 의제 #5 시정

#### A. `src/db/stock_master.py::count_active()` 신규 (count="exact")

```python
async def count_active() -> int:
    """stock_master 활성 row 카운트 (사이클 163, _boot prepare 가드용).

    사이클 128 count="exact" 패턴 답습 (PostgREST 1000행 silent cap 회피).
    """
    def _query():
        return (
            supabase.table("stock_master")
            .select("ticker", count="exact")
            .limit(0)
            .execute()
        )
    try:
        result = await asyncio.to_thread(_query)
        return result.count or 0
    except Exception as exc:
        logger.warning("[stock_master_count_active_failed] err=%r", exc)
        return 0
```

#### B. `src/engine/boot_manager.py` prepare 가드 hook

위 §2.2 시정 1 영역 그대로.

#### C. 4 전략 (LTV/donchian/BFB/VCP) prepare 자동 재시도 hook

위 §2.2 시정 2 영역 그대로.

### 4.2 의제 #6 시정

#### `src/engine/order_engine.py::_handle_buy_fill` 전량 체결 분기 3 영역 try/except 분리

```python
if total_filled >= ordered_qty:
    # 사이클 163 — 3 영역 try/except 분리 + 가시화 강화
    # 사이클 88 G-REJECT-1 영속 부분 예외 (DB INSERT race는 재연결로 해결 안 됨)
    try:
        affected = await update_trade_status(
            ticker, TradeType.BUY, TradeStatus.COMPLETED,
            strategy=strategy_id, price=price,
        )
    except Exception as exc:
        logger.error(
            "[buy_fill_db_error] step=update_trade_status ticker=%s order_no=%s err=%r",
            ticker, order_no, exc,
        )
        affected = 0

    if affected == 0:
        self._completed_orders.add(order_no)
        from src.engine.scanner import ticker_names as _tn
        try:
            await insert_trade(TradeRecord(
                ticker=ticker,
                ticker_name=_tn.get(ticker, ""),
                trade_type=TradeType.BUY,
                price=price,
                quantity=total_filled,
                profit_loss=0,
                status=TradeStatus.COMPLETED,
                strategy=strategy_id,
                order_no=order_no,
            ))
            logger.warning(
                "체결통보 선행 race — COMPLETED 직접 INSERT: 매수 %s (주문번호: %s)",
                t(ticker), order_no,
            )
        except Exception as exc:
            logger.warning(
                "[buy_fill_correction_unique_violation] ticker=%s order_no=%s strategy_attempted=%s err=%r → strategy 무관 강제 COMPLETED UPDATE",
                ticker, order_no, strategy_id, exc,
            )
            try:
                forced_affected = await _update_trade_status_by_order_no(
                    order_no, TradeType.BUY, TradeStatus.COMPLETED,
                    price=price,
                )
                if forced_affected == 0:
                    logger.error(
                        "[buy_fill_correction_forced_update_zero] ticker=%s order_no=%s",
                        ticker, order_no,
                    )
            except Exception as exc2:
                logger.error(
                    "[buy_fill_db_error] step=forced_update ticker=%s order_no=%s err=%r",
                    ticker, order_no, exc2,
                )

    try:
        from src.db.positions import save_position
        from src.engine.scanner import ticker_names
        await save_position(
            ticker=ticker, ticker_name=ticker_names.get(ticker, ""),
            buy_price=price, quantity=total_filled, order_no=order_no,
            strategy_id=strategy_id, buy_date=state.positions[ticker].buy_date,
        )
    except Exception as exc:
        logger.error(
            "[buy_fill_db_error] step=save_position ticker=%s order_no=%s err=%r — 메모리 등록 영역 영속, 15분 sync 회복 기대",
            ticker, order_no, exc,
        )

    self._filled_qty.pop(order_no, None)
    self._order_qty.pop(order_no, None)
    self._order_strategy.pop(order_no, None)
    self._order_ticker.pop(order_no, None)
    state.cached_buyable_at = 0.0
    logger.info("매수 전량 체결: %s %d주 @ %d (전략: %s)", t(ticker), total_filled, price, strategy_id)
```

`_handle_buy_fill` 자체는 try/except 없이 종료 — callback 외부 예외 raise는 더 이상 발생 안 함. `_handle_sell_fill`는 사이클 147 영속 영역 그대로 보존 (별도 사이클 인계).

## 5. 회귀 가드 매트릭스

### 의제 #5 가드 (≥8 케이스)

- G-163-BOOT-1: `boot_manager.boot()` 영역 prepare 호출 *전* `count_active()` 호출 영속 (AST)
- G-163-BOOT-2: `count_active() == 0` 영역 → `asyncio.sleep(10)` 발화 (freezegun)
- G-163-BOOT-3: `count_active() > 0` 영역 → 즉시 prepare 진입 (대기 0)
- G-163-BOOT-4: 5분 cap 초과 → graceful WARNING + prepare 진행
- G-163-COUNT-1: `count_active()` 정상 응답 반환
- G-163-COUNT-2: `count_active()` 예외 → 0 폴백 graceful
- G-163-LTV-RETRY: LTV `prepare()` 0건 → 30초 sleep × 3회 재시도 (사이클 158 VB 패턴)
- G-163-DONCHIAN-RETRY: donchian 동일
- G-163-BFB-RETRY: BFB 동일
- G-163-VCP-RETRY: VCP 동일

### 의제 #6 가드 (≥6 케이스)

- G-163-BUYFILL-1: `update_trade_status` 예외 → `[buy_fill_db_error] step=update_trade_status` ERROR + callback raise 0건
- G-163-BUYFILL-2: `insert_trade` (race) 예외 → `[buy_fill_correction_unique_violation]` WARNING + forced UPDATE 시도
- G-163-BUYFILL-3: `forced_update` 예외 → `[buy_fill_db_error] step=forced_update` ERROR + callback raise 0건
- G-163-BUYFILL-4: `save_position` 예외 → `[buy_fill_db_error] step=save_position` ERROR + 메모리 positions 등록 영속
- G-163-BUYFILL-5: 정상 흐름 → 모든 INFO 발화 + 매핑 정리 영속 (회귀 보존)
- G-163-SAFETY-1: `_handle_sell_fill` 변경 0 (사이클 147 영속)
- G-163-SAFETY-2: `_handle_buy_fill` 외부 호출자 인터페이스 변경 0
- G-163-SAFETY-3: 사이클 88 G-REJECT-1 다른 callback 영역 변경 0 (`_on_tick` / `_on_board` raise 영속)

## 6. 영속 의무 매트릭스 (사이클 163 영구 확인)

- 사이클 17 KIS LMS chain — 영향 0 (DB 영역만)
- 사이클 30 trade_history 부분 UNIQUE 인덱스 — 영속 (영향 0)
- 사이클 32 R4 보유/익일청산 절대 보호 — 영속
- 사이클 38 명문화 — scanner 매수 진입 전 한정 영속
- 사이클 51 boot_manager 패턴 — wrapper 답습
- 사이클 88 G-REJECT-1 — `_on_tick` / `_on_board` raise 영속, `_handle_buy_fill`만 graceful 분리
- 사이클 102 G-REJECT-1 — 정책 유지 (callback exception 가시화)
- 사이클 106 lifecycle race 차단 — `_full_universe_load_task_loop` 영속
- 사이클 134 task_loop_helper stagger — 영속 변경 0
- 사이클 147 `_handle_sell_fill` strategy fallback + UniqueViolation 강제 UPDATE — 영속 변경 0
- 사이클 158 VB prepare 자동 재시도 — 4 전략 확장
- 사이클 161 _handle_buy_fill price 정합 — 영속 (price=price 인자 영속)
- 사이클 162 익일청산큐 DB + 동시호가 stale 회피 — 영속

## 7. 사이클 164+ 인계

- D 옵션 (master_raw 1순위 + raw 2순위 chain) 자문 + 사이클 153 패턴 답습
- 알지노믹스 (476830) 6/17 12:43 사고 후 positions DB 정합 검증 (Supabase MCP)
- raw.hts_avls 데이터 손상 (3,566 → 6 종목 시총 1000억 이상) 원인 추적 — 사이클 116 단위 환산 / 사이클 107 merge / 사이클 126 basics refresh 영역
- D+1 운영 측정: 6/18 16:10 KST basics refresh 후 raw.acml_tr_pbmn 갱신 → 6/19 _boot prepare 정상 발화 확인
