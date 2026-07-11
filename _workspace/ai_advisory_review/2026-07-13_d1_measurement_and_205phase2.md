# 월요일(2026-07-13) D+1 실측 + 사이클 205 phase-2 설계

> 배경: 사이클 203(iscd 과차단 제거)·204(투자주의/투자유의 해제)·205-1(list_by_filter DB-side 필터)·
> **206(stock_master_daily 유니버스 한정 + 용량 퍼지 261→54MB)** 이 2026-07-11(토) 배포됨 →
> **월요일 07:50 _boot / 16:00 daily load 부터 실반영**. phase-2 + flag_retracement 는 D+1 실측 후 진행(사용자 결정).

## 1. D+1 실측 체크리스트 (월요일 장중/장후, Supabase MCP READ-ONLY)

| # | 항목 | 측정 방법 | 기대 |
|---|------|----------|------|
| 1 | **유니버스 확대** (203+204) | `strategy_funnel_snapshots` step3(1단계 진입 차단 통과) 종목수, 5전략 | VCP 63→175(실측)·BFB step3 확대. 이전 대비 급증 |
| 2 | **투자주의 매수 유입** (204) | 후보/체결에 mrkt_warn=01 종목(에스엘·삼성카드 등) 등장 여부 | 급등 시 후보 편입 |
| 3 | **list_by_filter 결정론성** (205-1) | BFB step1 일별 변동 (이전 42~143 요동) | 결정론적 안정화 |
| 4 | **WebSocket 41슬롯** ⚠️ | `[priority_drop]` INFO/WARNING 빈도 (system_logs) | 유니버스 확대로 LOW 구독 드롭 급증 여부 = phase-2 max_scan_stocks 상향 가부 판단 |
| 5 | **prepare wall-clock** ⚠️ | VCP/donchian prepare 소요(로그 timestamp), 09:00 창 내 완료 | 창 초과 없음 = phase-2 상향 가부 |
| 6 | ERROR/WARNING 이상 | system_logs 급증 여부 | 무이상 |
| 7 | **daily_load 유니버스 한정** (206) ⚠️ | 월요일 16:00 `[stock_master_daily_load_begin] candidates=N` = **~856(3576 아님)** + stock_master_daily 행수 재증가 없음(112K 유지) | 유니버스만 적재 = 용량 재적재 방지 확인 |
| 8 | **총 DB 용량** | `pg_database_size` | 209MB 유지 or 감소(7/16 WARNING 소멸 시 ~155MB) |

**4·5가 여유 있으면 phase-2 max_scan_stocks 상향 GO. 슬롯 드롭 상시화 or prepare 창 초과면 상향 보류/단계 축소.**
**7 이 3576 이면 206 배포 미반영 = 재점검.**

## 2. 사이클 205 phase-2 설계 (D+1 후)

### 핵심 발견 (205-1이 드러냄)
top-100 자격 종목 중 **88개가 ETF**(KODEX/TIGER — 시총·거래대금 커서 자격 통과) → ETF 필터가 limit **후** Python-side라 88 제거 → BFB 실질 12 → 가격필터 후 11. **ETF 상위 슬롯 잠식 = BFB 유니버스 축소 진짜 원인.**

### phase-2 = ETF DB-side 제외 + max_scan_stocks 상향 (병행)
1. **ETF를 limit *전* 제외** (핵심):
   - 현재 ETF 식별 = `scanner.ETF_KEYWORDS` name 매칭 (Python-side, list_by_filter *후*).
   - 선행 조사 필요: ETF DB 신호 존재 여부 — `excg_dvsn_cd` / master_raw 상품구분 / 별도 컬럼. 없으면 (a) stock_master ETF 플래그 컬럼 신설(master 적재 시) 또는 (b) list_by_filter가 ETF 제외 후 limit(name 기반이면 fetch 확대 필요).
   - 목표: limit 슬롯을 실질 종목이 채우도록.
2. **max_scan_stocks 상향** (domain 권고, D+1 슬롯 여유 시): BFB 100→300 / VB·LTV 100→250 / donchian 200→350 / VCP 200→330. `_workspace/00_leader_trading_rules.md` 동기화 의무.
3. **정렬** (`sort_by` 훅, 205-1에서 이미 인프라): 돌파류 전량이면 정렬 무관 / 스윙류 거래대금 DESC.
4. 회귀: return_stage_counts(3쿼리) + 5전략 prepare 반환 형식 + 매매 안전성 8영역 diff 0. limit 500+ 시 PostgREST 1000 cap 재점검(사이클 175).

### 대안 (슬롯 부족 시)
- max_scan_stocks 상향 대신 ETF 제외만 → 실질 종목 yield ↑ (슬롯 부담 최소).
- 가격필터(현 max 50만) / 거래대금 필터 강화로 후보 축소 병행.

## 3. 사이클 207 — BFB flag_retracement 완화 (독립, 205와 무관)
BFB flag_retracement 완화 (0.382→? domain 자문 + `tools/measure_bfb_pole_flag.py` 또는 사이클 203 DB 오프라인 스윕 실측). 폴 급등폭 대비 조정폭 현실화(폴 +10%→조정 ≤3.82% 거의 불가능). 사이클 198 은 flag_lookback_min 3→2 만 완화, retracement 미완화. flag_volume_ratio(0.60) 안전장치 불변.

## 4. 재개 순서 (월요일 D+1 후)
1. **D+1 실측** (§1 체크리스트 8항목) — 특히 #4 WebSocket 슬롯 · #5 prepare 시간 · #7 daily_load 856.
2. **205 phase-2** (§2) — ETF DB-side 제외 + max_scan_stocks 상향 (슬롯/시간 여유 확인 후).
3. **207 flag_retracement** (§3) — 독립, domain + 실측.
- 배포는 NXT 애프터(15:30+) 또는 익일 07:50 _boot 전. push 후 CI 확인 의무.
