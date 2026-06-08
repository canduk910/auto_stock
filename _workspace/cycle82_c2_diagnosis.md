# 사이클 82 — C-2 정밀 진단 결과

**진단 의무**: `_scan_loop` 후보 풀 raw 보강 영역 확장 (HIGH, 사이클 81 영역 1 시정 후 인계)
**진단 방식**: 옵션 A 채택 (코드 변경 0, READ-ONLY)
**진단 일시**: 2026-06-08 (일, 비영업일)

---

## 진위 판정

**결론**: **부분적 진짜 결함 ○** — 단, 결함의 본질은 "raw 보강 영역 확장 필요" 가 아니라
**"stock_master eager refresh 영역의 후보 풀 미커버"** 로 재정의되어야 함.

분해:
- 가설 A (raw 보강 영역 확장 = HIGH): **거짓 알람 ×** — `_scan_loop` 진입점 4 사이트 전수 `subscribe_filtered_stocks` 단일 경로, 사이클 81 시정 (`prdy_clpr` → `bfdy_clpr`) 효과는 *진입한 ticker 한정* 정확히 도달.
- 가설 B (stock_master 적재 영역 협소 = MEDIUM): **진짜 결함 ○** — stock_master 총 14건만 적재 (보유+익일청산 위주). `_apply_price_filter` 가 graceful 통과로 동작 → 후보 풀의 ~90% 이상이 가격필터 우회 가능성.

---

## 근거 (READ-ONLY 데이터)

### 1. stock_master.raw 키 분포 (Supabase 운영 실측 2026-06-08)

| 측정 항목 | 값 | 해석 |
|----------|---|------|
| total_rows | **14** | 운영 전체 stock_master 매우 협소 |
| raw_not_null | 14 | 100% raw 적재 |
| has_bfdy_clpr_key | **13** | 사이클 81 시정 키 정합 (1건 = 042700 NULL — 사이클 20 부분 적재) |
| has_prdy_clpr_key | **0** | 사이클 64 키 0건 = 사이클 81 시정 의도 정확 |
| has_acml_tr_pbmn_key | **0** | CTPF1002R 응답에 없음 = 사이클 81 폴백 폐기 정확 |
| bfdy_clpr_valid_nonzero | 13 | 13/14건 유효값 |

전체 67 키 (CTPF1002R 응답) 분포 = `bfdy_clpr` / `thdt_clpr` / `lstg_stqt` 등 13 occurrences 균일. 사이클 81 도메인 자문 (CTPF1002R 정본 키 `bfdy_clpr`) 운영 검증 완료.

### 2. stock_master 적재 ticker 전수 (refreshed_at DESC)

```
005930 삼성전자          bfdy=329000  2026-06-08 10:24 (당일 갱신)
240810 원익IPS           bfdy=97900   2026-06-05 08:00
028260 삼성물산          bfdy=485500  2026-06-04 11:15
064400 LG씨엔에스        bfdy=113800  2026-06-01 08:19
001820 삼화콘덴서        bfdy=102000  2026-05-26
000250 삼천당제약        bfdy=355000  2026-05-22
090360 로보스타          bfdy=70300   2026-05-21
066570 LG전자            bfdy=181000  2026-05-21
042700 (이름 없음)       bfdy=NULL    2026-05-20 (부분 적재)
017670 SK텔레콤          bfdy=100500  2026-05-19
... (전체 14건)
```

**핵심 관찰**:
- 보유/익일청산 위주 (`_eager_refresh_stock_master_for_held_positions` 트리거)
- 사이클 81 영역 1 보고 ticker **402340 (SK스퀘어) 미적재** = `_apply_price_filter` 에서 graceful 통과 경로 진입 (`prdy_clpr <= 0`)
- 후보 풀 (momentum scan = 영업일 평균 30~50 ticker) 의 ~90% 이상이 stock_master 미적재 → 가격필터 *전면 graceful*

### 3. `_scan_loop` 진입 chain (정적 grep)

`scheduler.py` 진입 사이트 4건 전수 (`grep "subscribe_filtered_stocks"`):
- L521 (scheduler 부팅 직후 통합 구독)
- L562 (보드 전환 직후 재구독)
- L582 (09:30 모멘텀 첫 스캔 직후)
- L2008 (`_scan_loop` 5분 주기 본체)

모두 단일 함수 `scanner.subscribe_filtered_stocks` 호출 → `_apply_price_filter` → `_apply_trade_amount_filter` 순차 hook (사이클 65 Q3). **단일 데이터 경로 = 가설 A 거짓 알람 확정**.

### 4. `ticker_market_info` 갱신 사이트 전수 (정적 grep)

`scanner.py:600` 단일 사이트 (`scan_stocks` 본체 모멘텀 등락률 순위 API 응답 = `fetch_rising_stocks` 결과) — 키 = `market_cap` / `trade_amount` / `trade_amount_raw` (사이클 65 신규).

**관찰**: VB / LTV / BFB / VCP / donchian / swing 전략의 후보 풀 (각 전략 `prepare()` 진입점) 진입 시 `ticker_market_info` 직접 갱신 0건. 사이클 81 영역 2 (가격필터) 는 `stock_master.raw.bfdy_clpr` 단독 의존 → 모멘텀 외 5 전략 후보 풀에 `ticker_market_info` 미반영도 가격필터 동작에 영향 없음.

### 5. 운영 효과 측정 (2026-06-08 일요일 12h 영역, 영업일 9시간 포함)

| Prefix | 24h 발화 건수 | 해석 |
|--------|--------------|------|
| `[price_filter_scanner_skip]` | **0건** | 사이클 81 push 미반영 (일요일 미배포) **또는** stock_master 영역 협소 영향 |
| `[price_filter_scanner_daily_summary]` | 1건 (20:10:05) | `min=3000 max=500000 daily_skip=0 reasons={below_min:0, above_max:0}` |
| `[universe_excluded]` | 4건 (09:35) | 사이클 32 R4 universe guard 정상 발화 |
| `[trade_amount_filter_scanner_skip]` | 0건 | 디폴트 0 (비활성) 영속 |

운영 부피 측정: 영업일 09:30 첫 스캔 = `급등종목 스캔: 2종목 통과 (전체 12종목)` — 본 사이클 영업일 후보 풀 부피 매우 협소 (12 ticker), `_apply_price_filter` 진입 ticker 자체 2~14건 영역. **사이클 81 시정의 영업일 효과 측정은 후보 풀 부피 회복 후 별도 측정 필요**.

---

## 진단 결론

### A. 가설 A (raw 보강 영역 확장 HIGH) = **거짓 알람 종결**

`_scan_loop` 진입점 4 사이트 단일 `subscribe_filtered_stocks` 경로 + `_apply_price_filter` 가 `stock_master.get(ticker)` 비동기 단일 진입 — 사이클 81 시정 (`bfdy_clpr` 키) 효과가 *진입한 ticker 한정* 정확히 도달. **사이클 82 영역 확장 시정 불필요**. C-2 카드 종결.

### B. 가설 B (stock_master 적재 영역 협소 MEDIUM) = **신규 카드 #82-A 발의**

**진짜 결함 영역 재정의**: `_apply_price_filter` 가 `prdy_clpr <= 0` (= stock_master 미적재 또는 raw NULL) 시 **graceful 통과** 로 동작 (`survivors.append(ticker); continue` L173-175). stock_master 운영 적재 14건만 → 후보 풀 ~90% 가 graceful 통과 → 가격필터 운영 효과 부분 상실.

**옵션 (사이클 83 발주 의제)**:
- 옵션 1 (**MEDIUM 권고**): `_scan_loop` 시점 후보 풀 ticker 에 대해 `stock_master.upsert_from_kis(ticker)` eager refresh 호출 추가 (`_eager_refresh_stock_master_for_held_positions` 패턴 답습 — 보유/익일청산 외 후보 풀로 영역 확장). KIS Rate Limit 20/s × 5 분 = 6,000 호출 마진 충분. TTL 24h.
- 옵션 2 (**LOW**): graceful 통과 영역 가시화만 (사이클 81 후속 카드 #C-5) — `[price_filter_scanner_pass_no_data] ticker=... reason=stock_master_miss` INFO emit + 일일 집계. 시정 없이 운영 측정 1~2주 후 옵션 1 발주 여부 재검토.
- 옵션 3 (**보류**): stock_master eager refresh 영역 확장 = 사이클 32 R4 universe guard `inquire_ccnl` 영역과 통합 (호출 사이트 절약) — refactor-expert 자문 의제.

### C. 사이클 81 영역 1 SK스퀘어 사고 재해석

- 사이클 81 시정 (`bfdy_clpr` 키) = **정확** (key 누락 영구 차단)
- 그러나 stock_master 에 402340 미적재 시 graceful 통과 → R6 안전망 (사이클 31) 단독 의존 → 동일 패턴 재발 가능
- **옵션 B 권고** = R6 안전망 + 가격필터 정상 동작 = 2중 안전망 보장

### D. 후속 카드 사이클 83+ 의제

| 카드 | 위급도 | 영역 | 진행 |
|-----|--------|------|------|
| **#82-A** | MEDIUM | stock_master eager refresh 후보 풀 확장 (옵션 1 또는 2) | domain-expert 자문 후 발주 |
| #C-4 | LOW | `[risk_silent_skip]` DailyEmitCap 폭주 검증 (사이클 81 인계) | 영업일 운영 1주 후 |
| #C-5 | LOW | `[price_filter_scanner_pass_no_data]` emit (옵션 2와 동일) | #82-A 옵션 1 채택 시 자동 종결 |
| #16 | MEDIUM | 후보 풀 폭축 회고 (Q6-3 2026-06-13 이후) | 2주 운영 후 |
| 사이클 78 후속 | LOW | `[swing_rest_poll_summary]` 실증 측정 (2026-06-09 화요일 09:30~15:20) | 영업일 측정 |

---

## 진단 산출 요약

- **코드 변경 0** (READ-ONLY 의무 준수)
- **Supabase MCP READ-ONLY 5 쿼리** (운영 데이터 무영향)
- **사이클 81 영역 1 시정 정확성 운영 검증 완료**
- **C-2 카드 자체는 거짓 알람 종결** + **신규 #82-A (MEDIUM) 인계** = stock_master 적재 영역 협소 = 가격필터 graceful 통과 영역 ~90%
- 사이클 83+ domain-expert 자문 의제 = "stock_master eager refresh 후보 풀 영역 확장" (옵션 1 KIS 호출 부담 vs 옵션 2 가시화만)
