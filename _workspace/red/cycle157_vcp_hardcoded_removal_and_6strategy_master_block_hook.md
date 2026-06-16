# 사이클 157 Red — VCP hardcoded list 폐기 + 6 전략 _is_master_blocked_for_entry hook 통합 + FUNNEL_STAGES +1단계

## 사용자 결정 영속

- Q1+Q2+Q3 통합 = 10시 이후 배포 의도 (구축만, commit/push 절대 금지)
- Q2 옵션 A = 6 전략 전수 hook (momentum 포함, momentum 은 funnel 미적재)
- Q3 = FUNNEL_STAGES +1단계 (5 전략, momentum 제외)

## 의제 매트릭스

### Q1 — VCP hardcoded list 폐기

`src/engine/strategies/vcp_breakout.py:722~760` `_scan_universe()`:
- KOSPI_200_TICKERS + KOSDAQ_150_TICKERS hardcoded import 폐기
- `fetch_stock_detail` 124 KIS 호출/일 → 0
- `stock_master.list_by_filter(is_kospi200=True, is_kosdaq150=True, ...)` 전환 (사이클 153 donchian 답습)

### Q2 — 6 전략 _is_master_blocked_for_entry hook 통합 (옵션 A)

`src/engine/scanner.py::_is_master_blocked_for_entry(master_raw, raw)` 13건 진입 차단:
- 사이클 129 (master_raw 7건): trht_yn / sltr_yn / mang_issu_yn / ssts_hot_yn / stange_runup_yn / mrkt_alrm_cls_code / invt_alrm_yn
- 사이클 155 (raw FHKST01010100 6건): mrkt_warn_cls_code / invt_caful_yn / short_over_yn / sltr_yn / iscd_stat_cls_code / temp_stop_yn

#### 적용 전략

| 전략 | hook 위치 | funnel 적재 |
|------|----------|-------------|
| VB | `_scan_universe()` 결과 직후, `_apply_price_filter_in_prepare()` 직전 | 신규 step 적재 |
| LTV | 동일 | 신규 step 적재 |
| donchian | `_scan_universe()` 결과 직후 (시총 컷 통과 직후) | 신규 step 적재 |
| BFB | `_scan_universe()` 결과 직후 | 신규 step 적재 |
| VCP | `_scan_universe()` 결과 직후 (Q1 전환 후) | 신규 step 적재 |
| momentum | `scan_stocks()` 내부 mcap+trade_amount 통과 *후*, filtered.append 전 | funnel 미적재 (사이클 132 영속) |

#### 헬퍼 패턴 (5 전략 = VB/LTV/donchian/BFB/VCP 공통)

```python
async def _apply_master_block_filter_in_prepare(
    self, tickers: list[str]
) -> tuple[list[str], list[dict]]:
    """1단계 진입 차단 13건 hook (사이클 157 Q2).

    Returns:
        (survived, excluded) — excluded = [{ticker, name, reason}] (사이클 41 답습)
    """
    from src.db import stock_master as _sm_mod
    from src.engine import scanner as _scanner_mod

    # 사이클 32 R4 — 보유/익일청산 절대 보호
    protected: set[str] = set()
    try:
        protected = _scanner_mod._collect_protected_tickers_for_scanner()
    except Exception:
        logger.debug("[master_block_filter] protected_tickers 조회 실패 graceful", exc_info=True)

    survived: list[str] = []
    excluded: list[dict] = []
    for ticker in tickers:
        if ticker in protected:
            survived.append(ticker)
            continue
        try:
            basics = await _sm_mod.get(ticker)
            master_raw = (basics.master_raw if basics and basics.master_raw else None) or {}
            raw = (basics.raw if basics and basics.raw else None) or {}
        except Exception:
            survived.append(ticker)  # graceful 통과
            continue
        blocked, reason = _scanner_mod._is_master_blocked_for_entry(master_raw, raw)
        if blocked:
            name = ""
            try:
                name = _scanner_mod.ticker_names.get(ticker, "")
            except Exception:
                pass
            excluded.append({"ticker": ticker, "name": name, "reason": reason})
            continue
        survived.append(ticker)
    return survived, excluded
```

#### momentum 패턴 (scan_stocks 내부)

`src/engine/scanner.py::scan_stocks()` 영역, `mcap_ok + trade_ok + 상한가 제외` 통과 *후*, `filtered.append(ticker)` 직전:

```python
# 사이클 157 Q2 — 1단계 진입 차단 hook (momentum funnel 미적재 사이클 132 영속)
try:
    basics = await _stock_master_get_safe(ticker)
    master_raw = (basics.master_raw if basics and basics.master_raw else None) or {}
    raw_block = (basics.raw if basics and basics.raw else None) or {}
    blocked, _reason = _is_master_blocked_for_entry(master_raw, raw_block)
    if blocked:
        continue
except Exception:
    pass  # graceful 통과
```

### Q3 — FUNNEL_STAGES +1단계

| 전략 | 현재 stages | 신규 step 위치 |
|------|-------------|---------------|
| VB | 5단계 (사이클 143) | 2 직후 신규 step 3 "1단계 진입 차단 13건 통과" → 6단계 |
| LTV | 6단계 (사이클 143) | 2 직후 신규 step 3 → 7단계 |
| donchian | 8단계 (사이클 39) | 2 직후 신규 step 3 → 9단계 |
| BFB | 8단계 (사이클 39+47) | 2 직후 신규 step 3 → 9단계 |
| VCP | 8단계 (사이클 39+47) | 2 직후 신규 step 3 → 9단계 |
| momentum | (funnel 영구 제외) | hook 적용은 하되 funnel 기록 안 함 |

## 회귀 가드 (단일 파일 통합 ≥18 케이스)

`tests/unit/engine/strategies/test_cycle157_master_block_hook_and_vcp_listfilter.py`

### A 영역 — VCP hardcoded list 폐기 (Q1)

- G-157-VCP-1 (HIGH): `_scan_universe()` 가 `list_by_filter(is_kospi200=True, is_kosdaq150=True, ...)` 호출
- G-157-VCP-2: vcp_breakout.py 본체에 `KOSPI_200_TICKERS` / `KOSDAQ_150_TICKERS` import 0건
- G-157-VCP-3: vcp_breakout.py 본체에 `fetch_stock_detail` 호출 0건

### B 영역 — _is_master_blocked_for_entry hook 통합 (Q2, 5 전략 prepare-path + momentum scan_stocks)

- G-157-HOOK-VB / LTV / DONCHIAN / BFB / VCP: 각 전략 prepare() 호출 시 `_is_master_blocked_for_entry` 통합 발화
- G-157-HOOK-MOMENTUM: scan_stocks() 가 master block 통과 ticker 만 filtered 에 추가
- G-157-HOOK-PROTECTED (HIGH): 보유 종목 절대 보호 (사이클 32 R4) — `protected` 통과 보장
- G-157-HOOK-GRACEFUL: stock_master.get 예외 시 graceful 통과
- G-157-HOOK-EXCLUDED-FORMAT: excluded = [{ticker, name, reason}] 영속

### C 영역 — FUNNEL_STAGES +1단계 (Q3)

- G-157-FUNNEL-VB: VB_FUNNEL_STAGES len == 6 (5 + 1)
- G-157-FUNNEL-LTV: LTV_FUNNEL_STAGES len == 7 (6 + 1)
- G-157-FUNNEL-DONCHIAN: donchian FUNNEL_STAGES len == 9 (8 + 1)
- G-157-FUNNEL-BFB: BFB FUNNEL_STAGES len == 9 (8 + 1)
- G-157-FUNNEL-VCP: VCP FUNNEL_STAGES len == 9 (8 + 1)
- G-157-FUNNEL-MOMENTUM-EXCLUDED: momentum prepare() empty stub + funnel 미적재 (사이클 132 영속)

### D 영역 — AST + 안전성

- G-AST-157: `_is_master_blocked_for_entry` callsite ≥ 6건 (5 전략 prepare + 1 scan_stocks)
- G-157-SAFETY-1 (HIGH): src/engine/risk.py / src/engine/order_engine.py / src/realtime/ / src/auth/ 변경 0
- G-157-SAFETY-2: 사이클 38 명문화 — `_apply_master_block_filter_in_prepare` 가 check_exit_signal/매도/익일청산 영역 호출 0
- G-157-SAFETY-3: 사이클 81 G-AST1 — `_is_master_blocked_for_entry` 가 raw write 0건 (read-only)

## 영속 의무 매트릭스

- 사이클 17 KIS LMS chain (VCP fetch_stock_detail 폐기로 안전 마진 강화)
- 사이클 32 R4 보유/익일청산 절대 보호
- 사이클 38 명문화 (매수 진입 전 한정)
- 사이클 39/41/47/143 FUNNEL_STAGES + cap 200/20 + 한글 사유
- 사이클 81 G-AST1 raw read-only
- 사이클 108 list_by_filter 패턴
- 사이클 121 donchian 패턴
- 사이클 129 master_raw 7건 + 사이클 155 raw 6건 = 13건 차단
- 사이클 132 momentum funnel 제외 (hook 적용 하되 snapshot 미적재)
- 사이클 148/151 _apply_*_in_prepare 패턴
- 사이클 153/154 is_kospi200/is_kosdaq150 영속
- 사이클 155 _is_master_blocked_for_entry 13건 영속

## 절대 금지

- commit/push 절대 금지 (사용자 명시 10시 이후 배포)
