# 전체 코드리뷰 — 2026-06-27 (사이클 179 이후)

## 방법 / 범위
- **방법**: ultracode 워크플로 — 9 서브시스템 병렬 버그헌팅(recall) → 발견별 적대적 검증(refute-first) → 종합.
- **결과**: 후보 ~51건 → **검증 생존 39건** (CONFIRMED 27 + PLAUSIBLE 12) / REFUTED 다수.
- **범위**: 9개 서브시스템 전체 검증 완료(2차 resume 로 api/realtime/db/routes_engines/frontend 보강).
- **클린**: auth(토큰/OAuth) 코어 로직 + strategy_registry 자금배분 = 결함 0건.
- 라인 인용 포함 검증 메모는 워크플로 결과(`tasks/wni54reob.output`)에. 본 파일은 종합.

## ROOT CAUSE 클러스터 4개 (묶어서 시정하면 효율적)

**① 전략 인스턴스 상태 일일 미리셋** (strat-1/2/3/4/5) — `scheduler._reset_daily_state()`가 `strategy.state.*`만 비우고 전략 인스턴스 dict(`_targets`/`_open_confirmed`/`_prev_price`/`_limit_up_reached`/`_breakout_first_seen`/`_prev_prdy_rate`/`_partial_exit`)는 미정리 + 전략별 `_reset_daily_state()`는 **존재하나 호출처 0건(고아)**. 장수 싱글톤이라 영업일 가로질러 누적 → 재매수 종목 stale 오작동. **→ scheduler가 per-strategy `_reset_daily_state()` 호출 배선 + 각 전략이 자기 dict 전수 정리.**

**② WebSocket 다건(count>1) 메시지 silent drop** (rt-1/rt-2/rt-5) — `_handle_raw`(websocket.py:759)가 `count` 헤더를 버리고 payload 전체를 handler에 넘기고, `_handle_tick`/`_handle_execution`도 첫 레코드만 파싱. KIS 정본상 고빈도 시 단일 프레임에 N건 번들 → 2번째 이후 **시세·체결통보 소실**. 체결통보 소실은 포지션 수량 누락 = 손절 대상 오류(치명). **→ count 정수 파싱 후 레코드 단위 루프(필드폭 KIS 정본 확정).**

**③ manual_sell이 execute_sell 안전망 우회** (manualsell-1/2) — `routes/trading.py`의 수동 매도가 `place_order` 직접 호출 → `_selling` 가드/SellRejectionTracker/NXT 다운그레이드/시장가-거부 폴백 전부 우회 → 이중매도 race + NXT 청산 silent 실패. **→ manual_sell을 execute_sell 경로로 통일.**

**④ PARTIAL 상태 전이 불가** (trade-1 + order-3) — `update_trade_status`/`_update_trade_status_by_order_no`가 `.eq(status, PENDING)`만 매칭 → PARTIAL row의 COMPLETED 전이 영구 불가 → 실현손익 왜곡. **→ status 필터 `.in_([PENDING, PARTIAL])` 완화.**

---

## 요약 표

### HIGH (6)
| id | 서브시스템 | 판정 | 제목 |
|----|-----------|------|------|
| strat-1 | strategies | CONFIRMED | VB/LTV prepare() `_targets/_open_confirmed/_prev_price` 미리셋 → 전일 stale 타겟으로 매수 |
| rt-1 | realtime | CONFIRMED | 시세 다건 메시지 2번째 이후 silent drop → 최신 급변동가 누락(손절 지연) |
| rt-2 | realtime | CONFIRMED | **체결통보** 다건 2번째 이후 drop → `_filled_qty` 과소 → 포지션 수량 누락 |
| order-1 | order_risk | CONFIRMED | 매수 시장가 폴백 inner try 비-KisApiError 누수 → `pending_buys` 영구 잔존(당일 재진입 차단) |
| base-1 | api | CONFIRMED | 토큰만료 분류가 예수금부족(EGW00120 "만료") 거부를 토큰만료로 오인 → 토큰 재발급+주문 재전송 증폭 |
| stale-1 | scanner_stale | PLAUSIBLE | call-auction stale skip 이 NXT 애프터로 무한 지속 → 보유 종목 stale 탐지 비활성 |

### MEDIUM (13)
| id | 서브시스템 | 판정 | 제목 |
|----|-----------|------|------|
| rt-5 | realtime | CONFIRMED | `_handle_raw`가 다건도 미분할 전달 — 분할 책임이 미처리 handler에만(②의 근본) |
| trade-1 | db | CONFIRMED | `update_trade_status` PENDING-only → PARTIAL→COMPLETED 전이 영구 불가(실현손익 왜곡) |
| manualsell-1 | routes_engines | CONFIRMED | 수동 매도가 `_selling`/SellRejectionTracker 우회 → 이중 매도 race |
| manualsell-2 | routes_engines | CONFIRMED | 수동 매도가 NXT 다운그레이드/시장가-거부 폴백/수량검증 없이 시장가 발사 |
| regime-1 | routes_engines | CONFIRMED | 매크로 레짐 `buffett_ratio`가 잘못된 키(`params.pbr_max`)에서 파싱 → 자문 입력 오염 |
| sched-2 | scheduler | CONFIRMED | 09:30 이후 재시작 시 복구한 익일청산큐 drain 누락 |
| sched-4 | scheduler | CONFIRMED | `stop()`이 진행 중 `start()` 남은 phase(강제청산/정산/일일초기화) 연쇄 실행 |
| strat-2 | strategies | CONFIRMED | LTV `_limit_up_reached` 미정리 → 재매수 종목 15:20 강제청산 누락 + 손절 -5% 오적용 |
| strat-3 | strategies | CONFIRMED | BFB `_reset_daily_state()` 고아 → `_breakout_first_seen` 전일 잔존 → retention 가드 우회 |
| strat-4 | strategies | CONFIRMED | Momentum `_prev_prdy_rate` 미리셋 → 익일 첫틱 갭상승 시 즉시 매수 |
| strat-5 | strategies | CONFIRMED | BFB `_partial_exit` 미정리 → 재진입 종목 measured-move 익절 영구 억제 |
| stale-2 | scanner_stale | CONFIRMED | 2-pass 슬롯 계산이 메인 세션 count(풀 union 아님) → 보조 세션 시 잘못된 잔여슬롯/drop |
| order-2 | order_risk | PLAUSIBLE | 체결통보 중복 dedup 부재 → `_filled_qty` 이중 누적 + phantom 포지션(KIS replay 가정) |

### LOW (20)
| id | 서브시스템 | 판정 | 제목 |
|----|-----------|------|------|
| rt-3 | realtime | CONFIRMED | 체결통보 짧은 payload 시 logging 없는 silent return(가시성 부재) |
| order-6 | order_risk | CONFIRMED | `_compute_next_market_open_kst` 주말 미스킵 → 금/주말 NXT TTL 오차 |
| sched-6 | scheduler | CONFIRMED | boot PENDING→COMPLETED 일괄 갱신이 미체결 BUY도 덮음 + 동기 DB(to_thread 위반) |
| strat-6 | strategies | CONFIRMED | donchian `breakout_fail_n_days` 캘린더일 기준 → 주말 포함 조기 STOP_LOSS |
| stale-3 | scanner_stale | CONFIRMED | `_last_scan_time` naive `datetime.now()`(KST 강제 위반) |
| stale-4 | scanner_stale | CONFIRMED | `_apply_price_filter` 60s TTL 캐시 우회 → scan당 DB read(최대 4×) |
| smdaily-1 | db | CONFIRMED | `get_recent_daily_normalized` 신선도 게이트가 prepare마다 별도 `max_bas_dd` SELECT(universe×N) |
| funnel-1 | db | CONFIRMED | `insert_snapshot` UPSERT가 새 uuid id 포함 → conflict 시 PK id churn(관찰성, 무해) |
| emit-summary-1 | routes_engines | CONFIRMED | backtest INSERT 실패 자문이 폴 루프 24h timeout까지 공회전(idle) |
| aggregate-1 | routes_engines | CONFIRMED | 일일 로그분석 `by_status`가 PARTIAL 누락 집계 |
| recs-kst-1 | frontend | CONFIRMED | Recommendations `formatDateTime`가 `Asia/Seoul` 누락 → 브라우저 로컬타임 렌더 |
| order-3 | order_risk | PLAUSIBLE | 부분체결 PARTIAL `affected==0` race 미처리(self-heal로 종단 치유) |
| order-4 | order_risk | PLAUSIBLE | 손절 잔여 재주문 동기 `_strategy_exchange`(NXT 다운그레이드 미적용) — 기본 KRX라 미발화 |
| order-5 | order_risk | PLAUSIBLE | sell_rejection 게이트가 FORCE_CLEAR/익일청산도 차단 — 09:00 5초 마진/익일 안전망 완화 |
| rt-4 | realtime | PLAUSIBLE | pool.subscribe가 OPSP backoff skip된 구독을 성공 추적 — backoff=KIS 활성이라 무해 |
| api/order-1 | api | PLAUSIBLE | `place_order` 응답 직접 인덱싱 → 비표준 응답 시 KeyError(481 cleanup+폴백으로 완화) |
| balance-1 | api | PLAUSIBLE | `is_market_order_disallowed`↔`is_market_closed_rejection` 상호배타 코드 미강제(현 호출순서로 안전) |
| stock-master-1 | db | PLAUSIBLE | `is_stale()`↔`_to_kst()` tz-naive 해석 불일치(UTC vs KST) — 쓰기 전부 tz-aware라 미발화 |
| stale-5 | scanner_stale | PLAUSIBLE | `is_call_auction_now` naive fallback(now=None) — 현재 호출자 없음, latent |
| funnel-fragment-key-1 | frontend | PLAUSIBLE | StrategyFunnel keyless Fragment → React key 경고(cosmetic, 자식 상태소실 REFUTE됨) |

---

## 권장 시정 순서 (TDD 사이클 단위; HIGH safety 우선)
1. **strat-1 (HIGH)** — VB/LTV prepare() 일괄 리셋. 절대규칙("돌파 = 이전틱<기준가 AND 현재틱>=기준가") 위반.
2. **rt 클러스터 ②(HIGH, rt-1/rt-2/rt-5)** — 다건 count 분할. **체결통보 누락 = 포지션 미등록 = 손절 불가(CLAUDE.md 금기).** KIS 정본 필드폭(H0STCNT0 45 / H0STCNI0 26) 확정 후 레코드 루프. **domain-expert + KIS MCP 동반.**
3. **order-1 (HIGH)** — 매수 폴백 except 분리 + finally cleanup.
4. **base-1 (HIGH)** — 토큰만료 분류를 msg_cd 화이트리스트로. EGW00120 충돌 차단(토큰 한도 고갈 방지). **인계 "inquire-balance 5xx halt"와 인증 chain 인접.**
5. **stale-1 (HIGH/PLAUSIBLE)** — call-auction 코드 분기에 시간창 게이트. KIS push 가정 domain-expert 확인 후.
6. **클러스터 ①(strat-2/3/4/5, MEDIUM)** — per-strategy `_reset_daily_state` 배선 1 hook으로 다수 해소.
7. **클러스터 ④(trade-1 + order-3, MEDIUM/LOW)** — status 필터 `.in_([PENDING,PARTIAL])`.
8. **sched-2 + sched-4 (MEDIUM)** — mid-day drain hook + phase 간 `_running` 가드.
9. **클러스터 ③(manualsell-1/2, MEDIUM)** — manual_sell을 execute_sell로 통일.
10. **regime-1, stale-2 (MEDIUM)** — 자문 키 정합 + 풀 union 슬롯.
11. **LOW 묶음** — KST/주말/tz(order-6/stale-3/stale-5/stock-master-1/recs-kst-1), sched-6 to_thread, stale-4 캐시, strat-6 영업일, aggregate-1/by_status, funnel-1/smdaily-1, rt-3 가시화, emit-summary-1, order-4/5/rt-4/api·order-1/balance-1/funnel-fragment-key-1.

---

# 상세 — 신규 검증분 (api/realtime/db/routes_engines/frontend)

## HIGH

### rt-1 / rt-2 / rt-5 — WebSocket 다건(count>1) 메시지 silent drop (클러스터 ②)
- **위치**: `src/realtime/websocket.py:759`(rt-5, 근본) · `handler.py:107`(rt-1 시세) · `handler.py:151`(rt-2 체결통보) · CONFIRMED
- **시나리오**: `_handle_raw`가 `raw.split("|",3)`의 `count`(parts[2])를 버리고 payload 전체를 handler로 전달. `_handle_tick`/`_handle_execution`은 `payload.split("^")` 후 첫 레코드(fields[0..9]/[0..18])만 파싱. **KIS 공식 샘플(chk_ccnl_krx.py / chk_ccnl_notice.py)이 다건 번들(`0|H0STCNT0|004|rec1^rec2^...`)을 명시** — 고빈도 시 단일 프레임 N건. 시세(rt-1)는 첫(오래된)가만 채택 → 급락 최신가 누락 → 손절/트레일링 한 틱 지연. **체결통보(rt-2)는 누적이라 치명** — 2번째 체결 CNTG_QTY 누락 → `_filled_qty` 과소 → 포지션 수량 과소 등록/잔여취소 오발동/실잔고 불일치 → 손절 대상 수량 오류.
- **시정**: `count` 정수 파싱 → `_handle_raw` 또는 handler에서 레코드 폭(45/26)×count 슬라이싱 루프. count≠1 가시화 로그.

### base-1 — 토큰만료 오분류로 토큰 재발급+주문 재전송 증폭
- **위치**: `src/api/base.py:560` (quote 경로 866 동일 복제) · CONFIRMED · correctness
- **시나리오**: `_request` 토큰 분기가 `"token" in msg1.lower() or "만료" in msg1` 순수 substring 매칭. 프로젝트가 **EGW00120("기간이 만료된 code")을 예수금부족 변형으로 활용**(error-codes.md:38, is_insufficient_cash 화이트리스트). 매수(TTTC0012U)/매수가능조회(TTTC8908R) 예수금부족 거부 → msg1 "만료" → 토큰 분기 True → `token_manager.issue()`(분당1개 한도, ≤61초 블록) + attempt<3이면 동일 주문 body `continue` 재전송. 결과: **약 122초 지연 + 불필요 토큰 2회 재발급(인증 chain 사고 위험) + 동일 매수 2회 추가 재전송(중복 체결 위험)**. '권리만료'/'청약기간 만료' 등도 동일 오분류.
- **시정**: 토큰만료를 msg_cd 화이트리스트(EGW00121~00126 등)로. is_insufficient_cash/is_market_closed_rejection이면 토큰 분기 배제. "만료" substring 매칭 폐기.

## MEDIUM

### trade-1 — PARTIAL row의 COMPLETED 전이 영구 불가 (클러스터 ④)
- **위치**: `src/db/trade_history.py:187`(+L93) · CONFIRMED · correctness
- **시나리오**: 분할체결로 PARTIAL row 기록 후 잔량 누적체결 → `update_trade_status(COMPLETED)` 호출하나 `.eq(status, PENDING)`라 PARTIAL 미매칭 → affected==0 → 보정 INSERT → (ticker,order_no,trade_type) UNIQUE(migration 029) 위반 → 폴백 `_update_trade_status_by_order_no`도 PENDING-only → 또 0건 → `[*_correction_forced_update_zero]` ERROR만 + row가 PARTIAL 영구 잔존. `_sync_orders_to_db`도 dedup키로 skip. 정산이 부분체결분만 반영 → 일일 실현손익 왜곡. (`_lookup_strategy_from_trade_history`는 `.in_([PENDING,PARTIAL])`라 작성자가 PARTIAL 인지했으면서 두 전이 함수만 PENDING-only로 남긴 비대칭.)
- **시정**: `_update_trade_status_by_order_no` status 필터 `.in_([PENDING,PARTIAL])`(order_no 단일키라 안전) 또는 COMPLETED 전이 강제 UPDATE는 status 필터 제거.

### manualsell-1 — 수동 매도가 _selling/SellRejectionTracker 우회 → 이중매도 race (클러스터 ③)
- **위치**: `src/routes/trading.py:143`(place_order 후 `_selling.add`) · CONFIRMED · safety
- **시나리오**: 자동 손절/익일청산 in-flight(`_selling.add`된) 종목에 운영자 manual-sell → `execute_sell` 진입가드(`ticker in _selling`/`is_blocked`) 우회 + `place_order` 직접 발사 후에야 `_selling.add` → 동일 수량 이중 매도 → over-sell APBK 거부 또는 음수 포지션/손익오류. NXT 차단 TTL 종목도 무조건 재발사 → 거부 폭주. `_selling.add`가 place_order 후라 더블클릭도 race.
- **시정**: manual_sell도 `_selling`/`is_blocked` 사전 가드, 가능하면 `execute_sell` 위임으로 단일 게이트.

### manualsell-2 — 수동 매도가 NXT 다운그레이드/시장가-거부 폴백/수량검증 없이 발사 (클러스터 ③)
- **위치**: `src/routes/trading.py:128` · CONFIRMED · correctness
- **시나리오**: `place_order(시장가, exchange=params.exchange)` 직접 호출 → (1) `_strategy_exchange_async` NXT→KRX 다운그레이드 미적용(전략 exchange=NXT/SOR 설정 시 NXT 미거래 종목에 NXT 주문) (2) NXT 세션 시장가 거부(APBK1943/3013)에 step_down 지정가 폴백 없음 → 청산 silent 실패 (3) `ManualSellRequest`에 quantity 제약 없음(UI는 가드하나 직접 API는 무방비).
- **시정**: `_strategy_exchange_async` 사용 + 시장가 거부 폴백(execute_sell 재사용) + quantity>0/보유이내 검증(422).

### regime-1 — 매크로 레짐 buffett_ratio 잘못된 키 파싱
- **위치**: `src/engine/market_regime.py:177` · CONFIRMED · correctness
- **시나리오**: `from_macro_cycle`이 `buffett_ratio`를 `regime.params.pbr_max`(PBR 상한 배분 파라미터)에서 읽음. 정본 키는 형제 레벨 `regime.buffett_level`(dkstock_client.py:300 docstring + fixture 확정). 결과: buffett_ratio가 항상 None이거나 PBR값으로 오염 → AI 자문 user_payload + market_regime_snapshots 감사기록에 틀린 버핏지수. `DKSTOCK_REGIME_ENABLED=true`(기본 false) 시 발화. 매수 가드엔 미사용(매매 직접 영향 0).
- **시정**: `regime_obj.get("buffett_level")`로 매핑.

## LOW (신규분 요약)
- **rt-3** (CONFIRMED): 체결통보 `len(fields)<15` 분기가 완전 무음 return(_handle_tick은 `_silent_drop_count` 가시화). 포지션 미등록 시 운영자 인지 수단 0. → WARNING+카운터.
- **smdaily-1** (CONFIRMED): `get_recent_daily_normalized` 신선도 게이트가 이미 메모리에 있는 `db_rows[0].bas_dd` 대신 `max_bas_dd` 별도 SELECT(VCP 348종목×prepare). 정확성 무해. → in-memory 판정.
- **funnel-1** (CONFIRMED): UPSERT payload에 새 uuid id → conflict 시 PK churn. FK/참조 없어 무해(관찰성). → payload에서 id 제거.
- **emit-summary-1** (CONFIRMED): backtest INSERT 실패 rec가 `summarized_rec_ids` 미등록 → 폴 루프 24h timeout까지 idle 공회전(KIS/DB write 0). → 실패 rec 종결 마킹.
- **aggregate-1** (CONFIRMED): 일일 로그분석 `by_status`가 PENDING/COMPLETED/CANCELLED만, PARTIAL 누락 → 상태분포 silent 불일치. → PARTIAL 카운터 추가.
- **recs-kst-1** (CONFIRMED): `Recommendations.formatDateTime`만 `timeZone:'Asia/Seoul'` 누락(다른 포매터 전부 강제) → TZ≠KST 시 9시간 어긋남. → 옵션 추가.
- **api/order-1** (PLAUSIBLE): `place_order` `data["output"]`/`output["ODNO"]` 직접 인덱싱 → 비표준 응답 KeyError. 481 cleanup+raise, handler 포착, 체결통보 폴백 chain으로 완화. → `.get()`+검증.
- **balance-1** (PLAUSIBLE): 상호배타 코드 미강제(현 execute_sell 호출순서로 우연 안전). → `and not is_market_closed_rejection(err)`.
- **stock-master-1** (PLAUSIBLE): `is_stale()` tz-naive→UTC vs `_to_kst()`→KST. 쓰기 전부 tz-aware(now_kst_iso)+TIMESTAMPTZ라 미발화. → 폴백 KST 통일.
- **rt-4** (PLAUSIBLE): pool이 OPSP backoff로 skip된 구독을 `_ticker_to_session` 성공 추적. backoff=KIS측 이미 활성+HIGH는 bypass라 무해, ≤300s 자가치유.
- **funnel-fragment-key-1** (PLAUSIBLE): keyless `<>` Fragment → React key 경고(cosmetic). 자식 상태소실 피해는 REFUTE(stateful 자식 0). → `<Fragment key>`.

> 기존 4 서브시스템(order_risk/scheduler/strategies/scanner_stale)의 20건 상세는 본 표 + `tasks/wni54reob.output` 참조. strat-1/order-1/stale-1/sched-2/sched-4/strat-2~6/stale-2~5/order-2~6 포함.

## 알려진 인계 항목과의 관계
- **"잔고 영속 500 fallback"(MEDIUM)** — base-1(토큰만료 오분류)이 인증 chain에서 인접(증폭 경로). sched-6(boot 동기차단)도 boot 영역 인접. 별개 유지하되 base-1 시정 시 함께 검토.
