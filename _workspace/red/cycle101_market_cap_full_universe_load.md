# 사이클 101 Red 명세 — market_cap 페이징 + CTPF1002R 편입 + 매일 20:00 일괄 적재

**일자**: 2026-06-11 (Red 단계 — production 변경 0)
**선행**:
- `_workspace/cycle101_phase1_diagnosis.md` (Phase 1 진단 영속)
- `_workspace/cycle101_domain_consult.md` (domain-expert 자문 영속)
**사용자 결정 채택**: Q67=B / Q68=A / Q69=B / Q70=A (전부 영속)
**총 신규 테스트**: 17 케이스 (HIGH 6 + MEDIUM 6 + LOW 5) — 11 파일
**행위**: 매일 20:00:05 KOSPI + KOSDAQ market_cap 페이징 → ~2,800 ticker → CTPF1002R 편입 → stock_master 일괄 적재 (사이클 89 5분 주기 + fluctuation 영구 폐기)

---

## 명세 출처

| 영역 | 출처 |
|------|------|
| 매매 규칙 영속 | `_workspace/00_leader_trading_rules.md` (사이클 38/32/64/65/81 영속) |
| KIS 정본 (FHPST01740000) | `docs/kis/domestic-stock-ranking.md:6326-6500` + `chk_market_cap.py` main 호출 영역 |
| KIS 정본 (CTPF1002R) | `docs/kis/domestic-stock-info.md` + `chk_search_stock_info.py` 67 컬럼 COLUMN_MAPPING |
| 시점 결정 | Q67=B (20:00:05 자문 직후 + NXT 마감 동행) |
| fluctuation 폐기 | Q68=A (영구 폐기 — 사이클 89/97/99 60 ticker 영구 영속 영역 폐기) |
| 사이클 89 폐기 | Q69=B (5분 주기 영구 폐기 — 매일 20:00 단독) |
| domain-expert 자문 | Q70=A 채택 (사이클 101 자문 권고 영속) |

---

## KIS MCP 정본 인용 (사이클 98 G-DOC1 영속)

### A-1. market_cap (FHPST01740000) — 사이클 100 Phase 1 영속 재확인

`chk_market_cap.py` + `market_cap.py` main 호출 영역 100% 인용 (정본):

| 영역 | 정본 사실 |
|------|----------|
| TR_ID | `"FHPST01740000"` |
| URL | `/uapi/domestic-stock/v1/ranking/market-cap` |
| `fid_cond_mrkt_div_code` | **`"J"` 강제 (정본 ValueError 가드)** — NX 미지원 영구 확정 |
| `fid_cond_scr_div_code` | **`"20174"` 강제 (정본 ValueError 가드)** |
| `fid_input_iscd` | `"0000"` 전체 / `"0001"` 거래소 (KOSPI) / `"1001"` 코스닥 / `"2001"` 코스피200 |
| `fid_div_cls_code` | `"0"` 전체 / `"1"` 보통주 / `"2"` 우선주 |
| `fid_trgt_cls_code` / `fid_trgt_exls_cls_code` | `"0"` 강제 |
| `fid_input_price_1/2` / `fid_vol_cnt` | `""` 영역 = 전체 |
| **페이징** | **`tr_cont == "M"` → 재귀 호출 + `"N"` 영속** (정본 L107~120 영역 영속) |
| 응답 키 | `mksc_shrn_iscd` (유가증권 단축 종목코드) — 11 컬럼 |
| `ka.smart_sleep()` | 페이징 간 sleep (정본 L109) |

**KIS 156 API 중 유일 `tr_cont="M"` 페이징 지원 확정** (사이클 100 Phase 1 영속).
fluctuation (사이클 98/99 영속) / volume_rank (사이클 96 영속) 와 본질 차이.

### A-2. search_stock_info (CTPF1002R) — 사이클 81 영속

| 영역 | 정본 사실 |
|------|----------|
| TR_ID | `"CTPF1002R"` |
| URL | `/uapi/domestic-stock/v1/quotations/search-stock-info` |
| 파라미터 | `PRDT_TYPE_CD="300"` + `PDNO=<6자리>` |
| 응답 영역 | dict 단일 객체 (list 아님) |
| 컬럼 수 | **67 컬럼** (chk_search_stock_info.py COLUMN_MAPPING 정본) |
| 사이클 81 영속 | `bfdy_clpr` (전일종가) — 가격 필터 정본 키 |

---

## 시정 영역 (Green 단계 backend-dev 인계)

### 1. `src/engine/scanner.py` 신규 영역

```python
# 사이클 101 — market_cap (FHPST01740000) KIS 156 API 중 유일 페이징 지원
_MARKET_CAP_URL = "/uapi/domestic-stock/v1/ranking/market-cap"
_MARKET_CAP_TR_ID = "FHPST01740000"
_MARKET_CAP_INPUT_ISCD: dict[str, str] = {
    "kospi": "0001",   # 거래소 (KOSPI) — KIS 정본
    "kosdaq": "1001",  # 코스닥        — KIS 정본
}

# 사이클 101 — 환경 분리 Rate Limit (domain-expert A3 영속)
_FULL_UNIVERSE_SLEEP_REAL = 0.050   # 실전 환경 50ms (Semaphore 20/s 일치)
_FULL_UNIVERSE_SLEEP_VTS = 0.200    # 모의 환경 200ms (Semaphore 5/s 일치)
_FULL_UNIVERSE_MAX_LOAD_SECONDS_REAL = 300  # 실전 5분
_FULL_UNIVERSE_MAX_LOAD_SECONDS_VTS = 600   # 모의 10분 (정산 race 차단)


async def _fetch_market_cap_page(market: str, max_pages: int = 100) -> list[dict]:
    """KIS market_cap (FHPST01740000) tr_cont="M" 페이징 누적.

    사이클 101 신규 — 사이클 99 60 ticker 영구 영속 본질 해결.
    KIS 156 API 중 유일 페이징 지원 (사이클 100 Phase 1 영속).

    정본 인용 (사이클 98 G-DOC1):
        chk_market_cap.py + market_cap.py main 호출 영역 정본 L107~120

    영속 의무:
        - tr_cont "M" → "N" 페이징 (정본 영속)
        - max_pages 무한 루프 차단 (사이클 91 답습)
        - 환경 분리 sleep (domain-expert A3)
        - graceful KIS error (사이클 88 G-REJECT 영속)
    """
    ...


async def _full_universe_load_once() -> dict:
    """KIS API 만으로 stock_master 전체 ~2,800 ticker 적재.

    Step 1: market_cap 페이징 (KOSPI 0001 + KOSDAQ 1001 분리)
    Step 2: 각 ticker → search_stock_info (CTPF1002R) 67 컬럼
    Step 3: stock_master upsert (사이클 84 history trigger 영속)

    환경 분리 (domain-expert A3 영속):
        - 실전: 50ms sleep + max_load_seconds=300
        - 모의: 200ms sleep + max_load_seconds=600 (정산 race 차단)

    영속 의무:
        - 사이클 32 R4 universe guard (보유/익일청산 절대 보호)
        - 사이클 38 명문화 (매수 진입 전용)
        - 사이클 84 history trigger
        - 사이클 88 G-REJECT graceful 영속
        - 사이클 98 G-DOC1 chk_market_cap.py + chk_search_stock_info.py 인용 영속

    Returns:
        {total, kospi, kosdaq, securities, etf, fetched, skipped_ttl,
         failed, elapsed_ms} dict
    """
    ...
```

### 2. `src/engine/scheduler.py` 신규 task

```python
TIME_FULL_UNIVERSE_LOAD = time(20, 0, 5)  # 사이클 101 — Q67=B 영속


async def _full_universe_load_task(self) -> None:
    """사이클 101 — 매일 20:00:05 1회 발화 (Q67=B 영속).

    영속 의무:
        - AI 자문 (20:00) 직후 영역
        - NXT 마감 (20:00) 동행 영역
        - 정산 (20:10) *전* 완료 의무 (max_load_seconds 가드 영속)
        - 사이클 79 G-AST2 lifecycle hook (stop()/run_daily.finally task_attrs)
        - 사이클 78 G-AST1 flush 호출 사이트 영속
    """
    ...
```

### 3. `src/engine/stock_master_metrics.py` 영역 확장

```python
async def record_full_universe_load_summary(stats: dict) -> None:
    """사이클 101 — 매일 일괄 적재 summary 영역 (사이클 74 패턴 답습)."""
    ...


async def flush_full_universe_load_collector() -> None:
    """사이클 101 — flush 호출 사이트 (사이클 78 G-AST1 영속).

    emit prefix:
        [full_universe_load_summary] total=N kospi=M kosdaq=K
        securities=L etf=J fetched=I skipped_ttl=H failed=G elapsed_ms=F
    """
    ...
```

### 4. 폐기 영역 (Q68=A + Q69=B 영속)

| 영역 | 위치 | 결정 |
|------|------|------|
| `_fetch_fluctuation` | `scanner.py:1472` (사이클 97) | Q68=A 영구 폐기 |
| `fetch_top_500_universe` | `scanner.py:1575` (사이클 89) | Q69=B 영구 폐기 (또는 `_full_universe_load_once` 로 통합) |
| `_universe_eager_refresh_loop` (scanner) | `scanner.py:1683` (사이클 89) | Q69=B 영구 폐기 |
| `_universe_eager_refresh_loop` (scheduler) | `scheduler.py:2591` (사이클 89) | Q69=B 영구 폐기 |
| `_universe_eager_refresh_task` | scheduler.py (사이클 89) | Q69=B 영구 cancel |
| `_FLUCTUATION_URL` | `scanner.py:1370` (사이클 97) | Q68=A 영구 폐기 |
| `_FLUCTUATION_TR_ID` | `scanner.py:1371` (사이클 97) | Q68=A 영구 폐기 |

---

## 회귀 가드 17 케이스 (HIGH 6 + MEDIUM 6 + LOW 5)

### HIGH 6 (시정 핵심 = market_cap + 시점 + 환경 분리 + 정본 인용)

| ID | 파일 | 검증 |
|----|------|------|
| **G-MC1** | `tests/unit/engine/scanner/test_cycle101_market_cap_pagination.py` | market_cap (FHPST01740000) tr_cont "M" → "N" 재귀 페이징 누적 (다중 페이지 mock, 정본 L107~120 영속) |
| **G-MC2** | `tests/unit/engine/scanner/test_cycle101_market_cap_input_iscd.py` | `_MARKET_CAP_INPUT_ISCD = {"kospi": "0001", "kosdaq": "1001"}` AST 정적 + KIS 정본 정합 |
| **G-CTPF1** | `tests/integration/test_cycle101_ctpf1002r_integration.py` | `_full_universe_load_once` chain — market_cap → CTPF1002R 67 컬럼 → stock_master upsert |
| **G-TIME1** | `tests/unit/engine/test_cycle101_time_full_universe_load.py` | `TIME_FULL_UNIVERSE_LOAD == time(20, 0, 5)` AST + Q67=B 영속 |
| **G-RATE1** | `tests/unit/engine/scanner/test_cycle101_rate_limit_env_split.py` | 환경 분리 — `KIS_ENV=real` 50ms / `KIS_ENV=vts` 200ms + max_load_seconds (300 real / 600 vts) freezegun |
| **G-DOC1** | `tests/unit/ast/test_cycle101_ast_chk_citation.py` | 사이클 98 G-DOC1 영속 — `_fetch_market_cap_page` + `_full_universe_load_once` docstring 영역 `chk_market_cap.py` + `chk_search_stock_info.py` 인용 의무 |

### MEDIUM 6 (lifecycle + 폐기 + 가시화)

| ID | 파일 | 검증 |
|----|------|------|
| **G-AST1** | `tests/unit/ast/test_cycle101_ast_flush_required.py` | 사이클 78 G-AST1 영속 — `record_full_universe_load_summary` 정의 모듈의 대응 `flush_full_universe_load_collector` 호출 사이트 ≥1건 정적 |
| **G-AST2** | `tests/unit/ast/test_cycle101_ast_task_cancel.py` | 사이클 79 G-AST2 영속 — `_full_universe_load_task` cancel 목록 (`stop()` task_attrs 튜플 + `run_daily()` finally 블록) 양쪽 동행 |
| **G-EMIT1** | `tests/unit/engine/scanner/test_cycle101_emit_visibility.py` | `[full_universe_load_summary] total=N kospi=K kosdaq=L securities=M etf=J fetched=... ` 1행 emit |
| **G-PURGE1** | `tests/unit/ast/test_cycle101_fluctuation_purged.py` | `_fetch_fluctuation` + `_FLUCTUATION_URL` + `_FLUCTUATION_TR_ID` 영구 폐기 AST (정의 0건) — Q68=A 영속 |
| **G-PURGE2** | `tests/unit/ast/test_cycle101_universe_eager_refresh_purged.py` | `_universe_eager_refresh_loop` (scanner+scheduler) + `_universe_eager_refresh_task` 영구 폐기 AST (정의 0건) — Q69=B 영속 |
| **G-AGE1** | `tests/unit/engine/scanner/test_cycle101_stock_master_age_warning.py` | `[stock_master_age_warning] ticker=X loaded_at=Y age_days=Z` 7일 이상 WARNING (domain-expert A5 적시성 보강) |

### LOW 5 (영속 확인)

| ID | 파일 | 검증 |
|----|------|------|
| **G-PERSIST1** | `tests/unit/engine/test_cycle101_38_명문화_persistence.py` | 사이클 38 명문화 영속 — `tradable_boards` 매수 진입 전용 (~2,800 적재 = scanner 단계 한정, 매도/익일청산/15:20 강제청산 영향 0) |
| **G-PERSIST2** | `tests/unit/engine/test_cycle101_32_r4_persistence.py` | 사이클 32 R4 영속 — 보유/익일청산 종목 universe guard 절대 보호 (`_full_universe_load_once` 영향 0) |
| **G-PERSIST3** | `tests/unit/db/test_cycle101_84_history_trigger.py` | 사이클 84 history trigger 영속 — 90일 retention + ~2,800 universe = 252,000 row (5% 미만, 안전) |
| **G-PERSIST4** | `tests/unit/engine/scanner/test_cycle101_88_g_reject_persistence.py` | 사이클 88 G-REJECT 영속 — graceful 영속 (KIS rt_cd != "0" 시 continue) |
| **G-PERSIST5** | `tests/unit/engine/test_cycle101_kst_persistence.py` | KST 영속 (사이클 68) — `src/db/_kst.py` 헬퍼 (`now_kst_iso`, `KST`) 사용 의무 |

---

## xfail 의미 전환 (사이클 66 K-2 패턴 답습)

폐기 영역 = 기존 사이클 97/99/89 회귀 가드 xfail 마킹 (영속 보존, Green 단계 backend-dev 가 시정).

| 영역 | 파일 | 의미 전환 사유 |
|------|------|--------------|
| 사이클 97 fluctuation | `tests/unit/engine/scanner/test_cycle97_*.py` | Q68=A 영구 폐기 = 사이클 97 fluctuation 영역 자연 폐기 |
| 사이클 99 60 ticker | `tests/unit/ast/test_cycle99_default_arg_persistence.py` | Q68=A + market_cap = ~2,800 영역으로 흡수 = 60 ticker 영역 자연 폐기 |
| 사이클 99 KIS limit | `tests/unit/ast/test_cycle99_kis_limit_documentation.py` | Q68=A 폐기 + market_cap 페이징 지원 = "KIS 페이징 미지원" 명문화 영역 폐기 |
| 사이클 89 universe_eager | `tests/unit/engine/scanner/test_cycle89*.py` (해당 시) | Q69=B 5분 주기 영구 폐기 |

**Green 단계 backend-dev 인계**: 사이클 97/99 회귀 가드 = `@pytest.mark.xfail(strict=False, reason="사이클 101 Q68=A 영구 폐기")` 마킹.

---

## Red 실행 검증

```bash
# 신규 17 케이스 = production 코드 부재로 모두 fail 예상
python -m pytest -x \
  tests/unit/engine/scanner/test_cycle101_*.py \
  tests/unit/engine/test_cycle101_*.py \
  tests/unit/db/test_cycle101_*.py \
  tests/integration/test_cycle101_*.py \
  tests/unit/ast/test_cycle101_*.py
# 기대: 17 FAILED (Red 단계 의무)
```

---

## 영속 매트릭스 (사이클 101 시정 *전* / *후* 보장)

| 사이클 | 영역 | 영향 |
|--------|------|------|
| 17 | OPSP0002 backoff (WebSocket 영역) | 영향 0 (영역 분리) |
| 18 | 60s WARNING dedupe (REST 영역) | 영속 (~2,800 호출 중 5xx 흡수) |
| 29 | 005935 LMS chain 사고 패턴 | 영향 0 (K stale watcher 영역 무관) |
| 32 R4 | universe guard 보유/익일청산 절대 보호 | **영속 영구** (G-PERSIST2 영속) |
| 38 | `tradable_boards` 매수 진입 전용 명문화 | **영속 영구** (G-PERSIST1 영속) |
| 64/65 | scanner protected_tickers + 거래대금 필터 | 영향 0 (영역 분리) |
| 67 | stale_manager 분해 | 영향 0 (영역 분리) |
| 76 | api retry collector 5분 윈도우 | 영속 (KIS LMS chain 흡수) |
| 78/79 | flush 호출 사이트 + task cancel | **G-AST1/G-AST2 영속 의무** |
| 81 | bfdy_clpr 가격 필터 정본 키 | 정확도 회복 ~99%+ (24h TTL 안정화) |
| 83 | scan_pool eager refresh 5분 주기 | 영향 0 (영역 분리) |
| 84 | stock_master history 90일 retention | G-PERSIST3 영속 |
| 88 | G-REJECT graceful 매트릭스 | G-PERSIST4 영속 |
| 89 | universe_eager_refresh 5분 주기 | **Q69=B 영구 폐기** (G-PURGE2 영속) |
| 95 | `_classify_market` KOSPI/KOSDAQ 분리 | 헬퍼 모듈 영역 영속 (market_cap unknown=0 영속) |
| 97 | fluctuation API 도입 | **Q68=A 영구 폐기** (G-PURGE1 영속) |
| 98 | G-DOC1 (chk_*.py 정본 인용 의무) | **G-DOC1 영속 영구** |
| 99 | 60 ticker 영구 영속 | market_cap 페이징 ~2,800 흡수 |
| 100 | UI prefix 정정 + market 분기 | 영향 0 (영역 분리) |

---

## 운영 효과 예상 (Green + push 후 D+1 tester verify)

- `[full_universe_load_summary] total=2800 kospi=950 kosdaq=1650 securities=2600 etf=200 fetched=N skipped_ttl=M failed=K elapsed_ms=L` 매일 20:00:05 1행 emit
- `stock_master` 총 row 171 → ~2,800 (~16x) 확인
- SK스퀘어 (402340) `bfdy_clpr` valid 확인 (사이클 81 silent 결함 영속 회복 검증)
- `[price_filter_scanner_skip]` 0건/30일+ → 정상 영구 회복 발화
- `[risk_silent_skip]` (R6) 270건/일 → 0~5건/일 영속 감소
- 사이클 89 `_universe_eager_refresh_loop` 호출 0건 (Q69=B 영구 폐기 검증)
- 사이클 97 `_fetch_fluctuation` 호출 0건 (Q68=A 영구 폐기 검증)

---

## 후속 카드 인계 (사이클 102+)

- **Plan Phase A** (사이클 102+): VB/LTV/BFB prepare() = stock_master 베이스 전환 (~2,800 universe 활용)
- **Plan Phase B** (사이클 103+): donchian/VCP prepare() = stock_master 베이스 전환
- **반례 1 영역** (사이클 102+): 신규 IPO 종목 운영자 수동 적재 단발 호출 영역
- **#16** (MEDIUM, 2026-06-13 이후): 후보 풀 폭축 역설 risk 2주 회고
- **UI 종목마스터 등락률 컬럼** (사이클 102+): `bfdy_ctrt` (CTPF1002R 67 컬럼) UI 표시 영역 검토
