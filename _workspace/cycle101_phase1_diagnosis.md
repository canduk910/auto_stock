# 사이클 101 Phase 1 진단 — market_cap 페이징 + CTPF1002R 편입

**일자**: 2026-06-11 (Phase 1 READ-ONLY, 코드 변경 0)
**범위**: A KIS MCP 정본 정밀 재검증 / B 매일 20:00 적재 시점 정합 / C domain-expert 자문 의제 / D 시정 청사진 / Q67~Q70 사용자 결정 의제

---

## A. KIS MCP 정본 정밀 재검증 (사이클 98 G-DOC1 영구 가드 영속)

### A-1. `market_cap` (FHPST01740000) — 사이클 100 Phase 1 영속 재확인

`mcp__kis-code-assistant__read_source_code` 정본 (`market_cap.py` + `chk_market_cap.py`) 100% 인용.

| 영역 | 정본 사실 (재인용 의무) |
|------|----------------------|
| TR_ID | `"FHPST01740000"` |
| URL | `/uapi/domestic-stock/v1/ranking/market-cap` |
| `fid_cond_mrkt_div_code` | **`"J"` 강제 (정본 ValueError 가드)** — **NX 미지원 영구 확정** |
| `fid_cond_scr_div_code` | **`"20174"` 강제 (정본 ValueError 가드)** |
| `fid_div_cls_code` | `"0"` 전체 / `"1"` 보통주 / `"2"` 우선주 |
| `fid_input_iscd` | `"0000"` 전체 / `"0001"` 거래소 (KOSPI) / `"1001"` 코스닥 / `"2001"` 코스피200 |
| `fid_trgt_cls_code` / `fid_trgt_exls_cls_code` | `"0"` 강제 |
| `fid_input_price_1/2` / `fid_vol_cnt` | `""` 영역 = 전체 |
| **페이징** | **`tr_cont == "M"` → 재귀 호출 + `"N"` 영속** (정본 L107~120 영역 영속) |
| 응답 키 | `mksc_shrn_iscd` (유가증권 단축 종목코드) — 11 컬럼 |
| ka.smart_sleep() | 페이징 간 sleep (정본 L109) |

**결정적 발견 영속 (사이클 100 Phase 1 영속)**: KIS 156 API 중 **유일하게 `tr_cont="M"` 페이징 지원 확정** API. `fluctuation` (사이클 98/99 영속 비반환) / `volume_rank` (사이클 96 영속 비반환) 와 본질 차이.

**chk_market_cap.py 정본 파라미터 예시 (인용 의무)**:
- `fid_input_price_2="1000000"` (~ 가격 영역)
- `fid_input_price_1="50000"` (가격 ~ 영역)
- `fid_vol_cnt="1000"` (거래량 ~ 영역)

→ **운영 시정 시 정본 그대로 인용 의무**: 비어둠 (`""`) = 전체 영역 (정본 docstring 영속).

### A-2. `search_stock_info` (CTPF1002R) — 사이클 81 영속 + NXT 영역 영속

| 영역 | 정본 사실 |
|------|----------|
| TR_ID | `"CTPF1002R"` |
| URL | `/uapi/domestic-stock/v1/quotations/search-stock-info` |
| 파라미터 | `PRDT_TYPE_CD="300"` (주식/ETF/ETN/ELW) + `PDNO=<6자리>` |
| 응답 영역 | dict 단일 객체 (list 아님 → 정본 `if not isinstance(output_data, list): output_data = [output_data]` 영속) |
| 컬럼 수 | **67 컬럼** (chk_search_stock_info.py COLUMN_MAPPING 정본 인용) |
| 페이징 | `tr_cont == "M"` → 재귀 (max_depth=10 영속) — **단일 종목 호출 = 페이징 비활성** |
| 사이클 81 영속 | `bfdy_clpr` (전일종가) — 가격 필터 정본 키 |
| NXT 영역 | `cptt_trad_tr_psbl_yn` (NXT 거래종목여부 Y/N) + `nxt_tr_stop_yn` (NXT 거래정지여부 Y/N) |
| 시장 분류 | `excg_dvsn_cd` (사이클 95 `_classify_market` 영속) + `kospi200_item_yn` + `scts_mket_lstg_dt`(KOSPI 상장일) + `kosdaq_mket_lstg_dt` |
| 거래정지/관리 | `tr_stop_yn` (거래정지) + `admn_item_yn` (관리종목) — 사이클 100 Phase 1 D-3 영속 |

**stock_master 정본 매핑 (사이클 101 청사진)**:
- `nxt_tradable = (cptt_trad_tr_psbl_yn == "Y") AND (nxt_tr_stop_yn != "Y")` — 사이클 13 Phase G `_strategy_exchange_async` 정합
- `krx_halted = (tr_stop_yn == "Y")` — 사이클 100 Phase 1 D-3 후보
- `admin_item = (admn_item_yn == "Y")` — 사이클 100 Phase 1 D-3 후보

### A-3. 사이클 98 G-DOC1 영구 가드 영속 의무

- 본 진단 = `chk_market_cap.py` + `chk_search_stock_info.py` main 호출 영역 정본 100% 인용 (영역 A-1 + A-2)
- 정본 파라미터 예시 그대로 인용 (가공 0)
- KIS API 비공식 fork / docstring 거짓 안내 영역 차단 (사이클 98 영속)

---

## B. 매일 20:00 일괄 적재 시점 정합 검증

### B-1. scheduler 시간 상수 매트릭스 (현황)

| 상수 | 시각 | 동작 |
|------|------|------|
| `TIME_NXT_POST_BUY_STOP` | 19:50 | `buy_disabled = True` (NXT 신규 매수 중단) |
| `TIME_NXT_POST_CLOSE` | **20:00** | `unsubscribe_all()` 발화 (자문과 동시) |
| `TIME_RECOMMENDATION` | **20:00** | AI 자문 `generate_recommendations()` (~3분, OpenAI) + `auto_apply_recommendations()` 직후 |
| `TIME_SETTLEMENT` | 20:10 | `_settle()` → `generate_daily_log_report()` → `purge_old_logs()` → `_reset_daily_state()` |

**현재 호출 chain (run_daily L645~L698)**:
```
20:00 await _wait_until(TIME_NXT_POST_CLOSE)
     → unsubscribe_all() (WS 시세 전수 해제)
     → generate_recommendations() (OpenAI, ~3분)
     → auto_apply_recommendations() (사이클 23 P3-1)
20:10 await _wait_until(TIME_SETTLEMENT)
     → _settle() (정산)
     → generate_daily_log_report() (OpenAI, ~60s)
```

### B-2. race 위험 검증 (HIGH 결과 = race 위험 0)

- `generate_recommendations` 및 `recommendation_engine` 모듈 `stock_master` **직접 참조 0건 확정** (grep 결과)
- `log_analysis_engine` 모듈 `stock_master` **직접 참조 0건 확정**
- AI 자문 user_payload 영역 = `recommendation_metrics` (trade_history) + `market_regime` (dkstock.cloud) + peer_metrics — stock_master 영역 race 위험 영속 **0**

### B-3. Rate Limit 영역 (HIGH 의제)

| 영역 | 모의 (5건/초) | 실전 (20건/초) | 50ms sleep 영속 (사이클 83) |
|------|--------------|--------------|---------------------------|
| ~2,800 ticker × CTPF1002R | ~560초 (9분) | ~140초 (2분) | 강제 차단 영속 |
| 사이클 89 영속 (60 ticker × 5분) | ~12초/주기 | ~3초/주기 | 사이클 83 답습 |
| 사이클 101 신규 (~2,800 × 1회/일) | **2분 ~ 9분 소요** | — | 50ms sleep 영속 의무 |

### B-4. 적재 시점 옵션 분석

| 옵션 | 시각 | 영향 | 위험 |
|------|------|------|------|
| 1 | **19:55** (자문 *전*) | 자문 영역과 순차 보장 | 19:50 매수 중단 *후* 5분 → 사이클 89 5분 주기와 동시 충돌 위험 |
| 2 | **20:00:05** (자문 직후) | NXT 종료 동행 | `unsubscribe_all()` 직후 즉시 적재 = WS race 0 + 자문 동시 OpenAI 호출 = REST 부담 분산 가능 |
| 3 | **20:08** (정산 *전*) | 자문 + 자동 적용 *후* | 정산 영역 (20:10) 과 2분 마진만 = 2,800 × 모의 9분 = **정산 지연 위험 HIGH** |
| 4 | `TIME_NXT_POST_CLOSE` 동행 | 가장 자연스러운 영역 | 자문 OpenAI + REST KIS 동시 = race 0 (서로 다른 API), 옵션 2 와 사실상 동일 |

**결정적 발견**: **옵션 2 (20:00:05) = 사이클 89 5분 주기 task `_universe_eager_refresh_task` 와 충돌 가능성** 영역 검토 필요. 사이클 89 task = 09:00~20:00 5분 주기 = 20:00 시점 동시 호출 race.

---

## C. domain-expert 자문 의제 5건 (Q62=B 영역 분리 영속)

| 의제 | 영역 | 자문 영역 |
|------|------|---------|
| 1 (HIGH) | 전체 KRX ~2,800 ticker 적재 시 매매 영향 | 사이클 99 60 ticker 영구 영속 vs 사이클 101 ~2,800 영역. 후보 풀 폭증 = 6 전략 신호 발화 빈도 영향. 사이클 38 명문화 (매수 진입 전용) 영속 보장 |
| 2 (HIGH) | 적재 시점 결정 | 19:55 vs 20:00:05 vs 20:08. AI 자문 + 정산 race + 사이클 89 5분 주기 task 충돌 |
| 3 (HIGH) | Rate Limit / KIS LMS chain 위험 | ~2,800 × CTPF1002R = 2~9분. 사이클 17 OPSP0002 backoff + 사이클 18 dedupe + 사이클 76 collector 영속 보장 |
| 4 (MEDIUM) | 사이클 99 60 ticker 영구 영속 영역 처리 | market_cap 도입 = fluctuation 폐기 vs 영속. 사이클 89 영속 (universe_eager_refresh 5분 주기) 영역 정합 |
| 5 (MEDIUM) | 사이클 95 unknown 합집합 영역 관계 | market_cap = KOSPI/KOSDAQ 명시 분리 = unknown 0 보장. 사이클 95 영역 영속 vs 폐기 |

---

## D. 시정 청사진 (사용자 결정 후 결정)

### D-1. 신규 함수 영역 (사이클 100 D-1 답습)

```python
# src/engine/scanner.py (또는 신규 모듈 stock_master_loader.py)
async def _fetch_market_cap_page(
    market: str,  # "kospi" (0001) / "kosdaq" (1001)
    max_pages: int = 100,  # 안전 한도 (페이지 당 30 × 100 = 3,000 ticker)
) -> list[dict]:
    """KIS market_cap (FHPST01740000) tr_cont='M' 재귀 페이징 누적.

    정본 인용 (사이클 98 G-DOC1 영속):
        chk_market_cap.py L60~70 main 호출 영역
        smart_sleep() 페이징 간 정본 영속

    Returns:
        accumulated output (dict list, 시가총액 정렬 desc)
    """
    ...

async def _full_universe_load_once() -> int:
    """매일 20:00 일괄 적재 — KOSPI + KOSDAQ 전체 페이징 + CTPF1002R upsert.

    Returns:
        upsert 종목 수 (~2,800 기대)
    """
    kospi_ticks = await _fetch_market_cap_page("kospi")
    kosdaq_ticks = await _fetch_market_cap_page("kosdaq")
    all_tickers = [r["mksc_shrn_iscd"] for r in kospi_ticks + kosdaq_ticks]
    # CTPF1002R 67 컬럼 → stock_master upsert
    for ticker in all_tickers:
        try:
            basics = await inquire_stock_basics(ticker)
            stock_master.upsert_one(ticker, **basics)
        except Exception:
            continue  # graceful
        await asyncio.sleep(0.05)  # 사이클 83 영속 (Rate Limit 보호)
    return len(all_tickers)
```

### D-2. scheduler 통합 영역 (사용자 결정 Q67 후 결정)

```python
# 옵션 2 (20:00:05) 예시
TIME_FULL_UNIVERSE_LOAD = time(20, 0, 5)  # 사이클 101 신규

# run_daily L645 영역 직후
await self._wait_until(TIME_FULL_UNIVERSE_LOAD)
try:
    n = await _full_universe_load_once()
    logger.info("[full_universe_load] 적재 완료 ticker=%d", n)
except Exception:
    logger.exception("[full_universe_load] 실패 graceful")
```

### D-3. 폐기/영속 결정 (사용자 결정 Q68/Q69 후 결정)

| 영역 | 위치 | Q68/Q69 후 결정 |
|------|------|---------------|
| `_fetch_fluctuation` | `scanner.py:1472` (사이클 97) | 폐기 (Q68=A) / 영속 (Q68=B/C) |
| `fetch_top_500_universe` | `scanner.py:1575` (사이클 89) | 폐기 (Q69=B) / 영속 (Q69=A/C) |
| `_universe_eager_refresh_loop` | `scheduler.py:2591` (사이클 89) | 폐기 (Q69=B) / 영속 (Q69=A/C) |
| `_FLUCTUATION_URL` / `_FLUCTUATION_TR_ID` | scanner.py 모듈 전역 | Q68=A 시 폐기 |

---

## Q67~Q70 사용자 결정 의제

### Q67 (HIGH) 적재 시점
- **A**: 19:55 (자문 *전*, 순차) — 사이클 89 5분 주기 task 충돌 위험
- **B**: 20:00:05 (자문 직후 동행) — WS unsubscribe 직후 race 0 + 자문/REST 서로 다른 API
- **C**: 20:08 (정산 *전*) — 정산 지연 위험 HIGH (모의 9분 소요 시 정산 미스)
- **권장 (Phase 1 영속)**: **B (20:00:05)** — race 0 + 동시 OpenAI/REST 부하 분산 + 사이클 89 task 동시 호출은 별도 가드 필요

### Q68 (HIGH) 사이클 99 fluctuation 영역 처리
- **A**: 영구 폐기 (market_cap 단독, 60 ticker 영역 폐기)
- **B**: 영속 + 병행 (5분 주기 fluctuation + 매일 20:00 market_cap)
- **C**: market_cap 1차 + fluctuation 2차 (graceful fallback)
- **권장 (Phase 1 영속)**: **A (영구 폐기)** — market_cap 페이징 = ~2,800 우월 영역 (60 ticker 영역 사실상 무용)

### Q69 (MEDIUM) 사이클 89 영속 (universe_eager_refresh 5분 주기) 처리
- **A**: 영속 (60 ticker 영구 영속 + 매일 20:00 매트릭스 결합)
- **B**: 폐기 (매일 20:00 단독 영역)
- **C**: 영속 + 병행 (2 source)
- **권장 (Phase 1 영속)**: **B (폐기)** — Q68=A 결정 시 사이클 89 영역 자연 폐기 (fluctuation 호출 영역과 chain 동행)

### Q70 (HIGH) domain-expert 자문 즉시 진행 여부
- **A**: Phase 1 진단 *후* + Q67~Q69 결정 *후* domain-expert 발주 (순차)
- **B**: Phase 1 진단 + Q67~Q69 결정 + domain-expert 자문 통합 단일 응답
- **C**: domain-expert 자문 생략 (사용자 결정 단독)
- **권장 (Phase 1 영속)**: **A** — 사이클 100 Phase 1 영역 영속 패턴 + 의제 5건 사전 정의 영역 영속

---

## 영속 영역 (사이클 101 시정 전 / 후 보장)

1. **사이클 81 영속**: `bfdy_clpr` 가격 필터 키 (CTPF1002R 67 컬럼 영역)
2. **사이클 13 Phase G 영속**: `_strategy_exchange_async` NXT 사전 차단 (nxt_tradable 정본)
3. **사이클 38 명문화 영속**: `tradable_boards` 매수 진입 전용 (~2,800 적재 = 후보 풀 확장이 매도/손절 영향 0)
4. **사이클 98 G-DOC1 영속**: KIS chk_*.py 정본 인용 의무 영속
5. **사이클 100 Phase 1 D-1 영속**: market_cap = KIS 156 중 유일 페이징 지원 영역
6. **사이클 17 OPSP0002 backoff + 사이클 18 dedupe + 사이클 76 collector 영속**: KIS LMS chain 차단
7. **사이클 83 50ms sleep 영속**: Rate Limit 20/s 보호
8. **사이클 95 _classify_market 영속**: KOSPI/KOSDAQ 명시 분리 영역 (Q68=A 시 market_cap 직접 호출로 unknown=0 영속)

---

## 진행 가이드 (사용자 결정 후)

1. **Q67~Q70 사용자 결정 수령**
2. **Q70=A 경우** → `domain-consult` 스킬 발주 (의제 5건)
3. **tdd-engineer Red 명세 작성** → `_workspace/red/cycle101_full_universe_load.md`
4. **backend-dev Green 구현** → `scanner.py` 신규 함수 + `scheduler.py` 신규 task
5. **tester 통합 검증** + 사이클 89 5분 주기 task 충돌 race 가드
6. **운영 측정 의무**: 익일 20:00 적재 후 `stock_master` 171 → ~2,800 (~16x) 확인 + `[full_universe_load]` 1행 emit
