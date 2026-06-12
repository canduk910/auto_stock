# 사이클 119 Phase 1 진단 — donchian_swing stock_master 전환

## 사용자 결정 영구 영속
- **Q1=B** donchian 단독 (VCP는 사이클 120 별개)
- **Q2=D** 임시 완화 (사이클 118 효과 검증 *전* 안전 영역)
- **Q5=A** nxt_tradable=None (전체 — donchian MAIN 단독 + NXT 의존성 0)
- **Q6=B** domain-expert 자문 필수 (멀티데이 보유 영역 영향 평가)

## 결정적 발견

### 1. 현재 donchian `_scan_universe()` 영역 (사이클 119 시정 *전*)

**위치**: `src/engine/strategies/donchian_swing.py:405~454`

**현재 호출 영역**:
```python
async def _scan_universe(self) -> list[str]:
    from src.api.condition import fetch_stock_detail
    from src.db.system_logs import write_log
    from src.engine.scanner import KOSDAQ_150_TICKERS, KOSPI_200_TICKERS

    min_mcap = self.config.params["min_market_cap"]
    max_stocks = self.config.params["max_scan_stocks"]

    all_tickers = list(dict.fromkeys(list(KOSPI_200_TICKERS) + list(KOSDAQ_150_TICKERS)))
    logger.info("도치안 스윙 유니버스 후보(코스피200+코스닥150): %d종목", len(all_tickers))
    self._scan_stats["universe_candidates"] = len(all_tickers)

    filtered: list[str] = []
    for ticker in all_tickers:
        if len(filtered) >= max_stocks:
            break
        try:
            detail = await fetch_stock_detail(ticker)
            price = int(detail.get("stck_prpr", "0"))
            listed = int(detail.get("lstn_stcn", "0"))
            mcap = price * listed
            # 종목명 보강
            ...
            if mcap >= min_mcap:
                filtered.append(ticker)
        except Exception:
            continue
    ...
```

**KIS API 호출 영역**: `fetch_stock_detail` (`/uapi/domestic-stock/v1/quotations/inquire-price` FHKST01010100). 후보 350종목 × 1회 = **350 호출/일** (사이클 17 OPSP0002 backoff + LMS chain 위험 영역).

### 2. donchian 특수성 (VB/LTV/BFB와 차이)

| 영역 | VB/LTV/BFB (사이클 108) | donchian (현재) |
|------|------------------------|-----------------|
| 유니버스 | stock_master ~2,800종목 | KOSPI200 + KOSDAQ150 = ~350종목 고정 |
| 시총 컷 | KIS volume-rank API 응답 | `fetch_stock_detail` (개별 호출 350회) |
| nxt_tradable | True (NXT 갭상승 매수 영역) | None (MAIN 단독, 사이클 26 `DEFAULT_TRADABLE_BOARDS=("main",)`) |
| 보유 영역 | 일중 청산 (15:20 강제) | **멀티데이 보유** (5~15 영업일, `Position._MULTIDAY_STRATEGIES`) |
| 매수 timing | 시가 돌파 (09:00:05+) | 09:05~09:30 1회만 (갭 +3%↑ 스킵) |

### 3. 현재 donchian DEFAULT_PARAMS 영역

```python
DEFAULT_PARAMS = {
    "tradable_boards": ["main"],
    "exchange": "KRX",
    "donchian_period": 20,
    "long_ma_period": 60,
    "volume_period": 20,
    "volume_multiplier": 1.5,
    "atr_period": 14,
    "atr_trail_mult": 2.0,
    "min_market_cap": 300_000_000_000,    # 3,000억
    "min_trade_amount": 5_000_000_000,    # 50억
    "max_scan_stocks": 200,
    ...
}
```

**Q2=D 임시 완화 후보**:
- `min_market_cap`: 3,000억 → **500억** (사이클 118 효과 검증 *전*, 후보 풀 충분 확보)
- `min_trade_amount`: 50억 → **10억** (멀티데이 보유 → 유동성 보수적 요구)

### 4. 사이클 118 효과 검증 상태

| 영역 | 운영 현황 (2026-06-12 16:42 KST 시점) |
|------|--------------------------------------|
| 사이클 118 push 완료 | 16:30 KST (EC2 Deploy ✅) |
| stock_master 마지막 갱신 | **16:18 KST** (사이클 118 push 11분 *전*) |
| acml_tr_pbmn_present | **2.85%** (사이클 118 효과 미반영) |
| 다음 stock_master 자동 갱신 | 오늘 20:00 KST `_full_universe_load_task_loop` |
| 사용자 새로고침 | UI 종목마스터 메뉴 "지금 새로고침" 즉시 |
| 예상 acml_tr_pbmn_present | 99%+ (사이클 118 후 정상화) |

**리스크**: 사이클 119 시정 push 후, 다음 stock_master 갱신 *전* donchian `prepare()` 실행 시 `min_trade_amount=10억` 필터가 acml_tr_pbmn=0 영역으로 인해 후보 풀 0종목 발생 가능.

**완화 영역**: `list_by_filter()` 영역 graceful (raw miss = 통과, 사이클 65 Q6-1 09:00 race 답습) → acml_tr_pbmn=0 종목 graceful 통과 → 후보 풀 보존.

### 5. 사이클 32 R4 universe guard 영속 (영구 보장)

`_evaluate_universe_guard` (`src/engine/stale_universe_guard.py`) = 보유/익일청산 절대 보호 영역 영구 영속. 사이클 119 `_scan_universe()` 영역 시정으로 후보 풀 -90~95% 폭축 시에도 **이미 보유 중 종목** = stale watcher 절대 보호 + 매도/익일청산/15:20 강제청산 hot path 영역 영구 영속 무관.

### 6. 사이클 49 VCP Pullback 영속 (영역 무관)

사이클 49 VCP 시정 = `vcp_breakout.py::_check_pullback_sequence` 영역 한정 (ATR threshold ZigZag + state machine). donchian 영역 무관 영구 확정.

### 7. 사이클 119 시정 영역 (사이클 108 답습 패턴)

**(1) DEFAULT_PARAMS 영역**:
- `min_market_cap`: 300_000_000_000 → **50_000_000_000** (Q2=D 임시 완화, 500억)
- `min_trade_amount`: 5_000_000_000 → **1_000_000_000** (Q2=D 임시 완화, 10억)
- `exclude_tickers`: `[]` 신규 추가 (사이클 108 답습)
- `nxt_tradable`: `None` 신규 추가 (Q5=A 전체, donchian MAIN 단독)

**(2) `_scan_universe()` 영역**:
- KIS `fetch_stock_detail` 호출 350회 → `stock_master.list_by_filter()` 1회 호출
- KOSPI200/KOSDAQ150 고정 유니버스 제거 (사이클 108 답습)
- ticker 6자리 필터링 영속 + ETF 키워드 제외 영속 + ticker_names 보강 영속
- funnel 카운터 영속 (`universe_candidates` + `universe_filtered` + `last_run_at`)
- graceful 영역 (`list_by_filter()` raise 시 빈 list 반환 + `_scan_stats["universe_candidates"]=0`)

**(3) 회귀 가드 영역 (사이클 108 답습)**:
- HIGH 4: list_by_filter 호출 정합 + 4 필터 적용 + funnel 카운터 + graceful
- MEDIUM 2: 멀티데이 보유 영역 보호 (사이클 32 R4 영속) + 신호 빈도 영향
- AST 1: KIS API 호출 직접 사용 0 (사이클 108 답습)
- xfail 의미 전환 (KOSPI200/KOSDAQ150 고정 유니버스 폐기 계약 영구 보존)

## 영속 의무 매트릭스

- **사이클 17 KIS LMS chain**: KIS API 호출 100% 절감으로 영역 영구 보호 강화
- **사이클 29 005935 사고**: scanner 단계 영역 무관
- **사이클 32 R4 universe guard**: 보유/익일청산 절대 보호 영속
- **사이클 38 명문화**: scanner 단계 매수 진입 전 후보 풀 영역 한정, 매도/익일청산 hot path 무관
- **사이클 49 VCP Pullback**: 영역 무관 영구 확정
- **사이클 81 G-AST1**: stock_master.raw 영역 (bfdy_clpr/hts_avls 덮어쓰기 금지)
- **사이클 88 G-REJECT**: 재구독 영역 영구 보존
- **사이클 89 ETF 키워드 제외 + 한글 친숙 용어**: ETF_KEYWORDS 영속
- **사이클 100 인계 (Plan Phase B)**: donchian/VCP stock_master 베이스 전환 영역 (MEDIUM 위험)
- **사이클 108 답습 패턴**: VB/LTV/BFB 동일 패턴 답습
- **사이클 110 silent 결함 시정**: source 키 영속
- **사이클 112 KRX 인프라**: 영역 무관
- **사이클 115 Q3=C 폴백**: 영역 무관
- **사이클 116 MKTCAP 환산**: 영역 무관
- **사이클 117 basDd 재시도 + source 키**: 영역 무관
- **사이클 118 ACC_TRDVAL 매핑**: 사이클 119 의존성 (Phase 2 자문 의제)
- **CLAUDE.md "절대 깨지 말 것" 8 영역 영속**

## 매매 안전성

scanner 단계 매수 진입 전 후보 풀 영역 한정 (사이클 38 명문화 영속). donchian 멀티데이 보유 영역은 사이클 32 R4 + 익일 청산 안전망 영속 보호. Q2=D 임시 완화로 신호 빈도 보존.

## domain-expert 자문 의제 (Phase 2)

- A1. 멀티데이 보유 영역 영향: donchian 후보 풀 -90~95% 폭축 시 신규 진입 빈도 감소 위험
- A2. Q2=D 임시 완화 임계 (500억 / 10억) 영역 적정성 + 정밀화 (vs 1,000억/20억)
- A3. 매매 신호 영향 평가 (donchian 신호 빈도 추정)
- A4. 사이클 32 R4 universe guard 영속 + 사이클 49 VCP 영속 무관성 확인
- A5. 사이클 38 명문화 영속 (scanner 단계 매수 진입 전 영역)
- A6. 사이클 118 효과 검증 후 사이클 121+ DEFAULT 임계 복원 영역 권고
- A7. 사이클 119 push 시점 (사이클 118 stock_master 갱신 *전*) 안전성

## 운영 효과 예상 (push + EC2 자동 배포 후)

- KIS API 호출 100% 절감 (350 호출/일 → 0 호출/일, KIS LMS chain 안전 영역 강화)
- stock_master ~2,800 종목 영역 활용 (사이클 108 답습)
- 신호 빈도 ±5~15% 이내 (Q2=D 임시 완화 효과)
- 운영자 통제 영역 (`exclude_tickers` 인자 활용, Plan Phase C UI 호환)
