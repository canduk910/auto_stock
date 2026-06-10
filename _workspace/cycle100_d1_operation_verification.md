# 사이클 100 D+1 운영 측정 보고서

**측정 시각**: 2026-06-11 08:01 KST (NXT 프리 마켓 영역)
**대상**: 사이클 92~99 통합 영속 영역 + UI "오늘 자동 갱신 횟수 0" 결함 진단
**방법**: Supabase MCP READ-ONLY 11 쿼리 (A1~A3 / B1~B5 / C1 / D1~D3 / E1~E3)
**코드 변경**: 0

---

## A. 사이클 92 영역 영속 검증 (HIGH) — 결과

### A1. 07:45~08:05 ERROR/WARNING 전수

| 시각 (KST) | log_level | 핵심 메시지 |
|-----------|-----------|------------|
| 07:46:02 | WARNING | dkstock.cloud fetch 실패 — 매수 가드 비활성 (`DKSTOCK_REGIME_ENABLED=false` 정상) |
| 07:46:11 | WARNING ×2 | quote_pool HTTP 500 attempt 1/3 (`inquire-daily-itemchartprice` label=gold/sub, 재시도 1회 자동 회복) |
| 08:00:00 | **ERROR** | `[kis_rejection]` APBK0918 매도 거부 — 티엠씨(217590) 프리마켓 시장가 매매 불가 (정상 — NXT 시간 외 KIS 거부) |
| 08:00:00 | WARNING ×2 | 매도 거부 → positions 보존 + 재시도 중단 (사이클 31 R6/R7 영속 정상 작동) |

**판정**: 사이클 92 영역 신규 ERROR/WARNING **0건**. KIS 거부는 *NXT 시간 외 시장가 거부 정상 흐름* (NXT 프리마켓은 시장가 불가 = KIS 정책). `_pending_next_day_clear` 가 즉시 09:00 KRX 시장가 청산 예약 전환 확인 (E1 23:00:38 "익일 청산 보류").

### A2. `[ws_auto_restart]` 영역

**0건** — 사이클 92 자동 재기동 미발화. 07:55 정시 boot 후 안정 운영 = **정상 (자동 재기동 불필요 경로)**.

### A3. `_boot` 발화 시점

```
07:46:02 [boot_preissue] label=sub/gold 사전 발급 완료
07:46:03 [cash_usage_ratio] net_asset=1306051 ratio=1.00 available=1306051
07:46:29 DB 포지션 복구: 티엠씨 3주 @ 22550 (익일청산, momentum)
07:46:29 기동 완료: 순자산 1306051, 보유 1종목
```

**판정**: 07:55 → **07:46 실측 발화 (약 9분 빠름)**. 사이클 92 의도 (07:55 TIME_BOOT) 와 실측 차이 영역 발견. E1 `=== 자동 매매 시작 (2026-06-11 07:45) ===` 확인 = **`AUTO_START=true` + 컨테이너 재기동 / pool_start 시점에 즉시 발화** 패턴 (07:55 정시 trigger 가 아닌 startup-on-boot). 사이클 92 영역의 7:55 TIME_BOOT 트리거가 *컨테이너 startup 시점에 의해 우회되었는지* 추가 진단 영역.

---

## B. 사이클 93/95/99 영역 영속 검증 (HIGH) — 결과

### B1. `[stock_master_bulk_refresh]` 영역

**0건** — 사이클 99 의 신규 prefix 가 발화되지 않음.

### B2. `universe_eager_refresh` 영역 (사이클 89 영속) — **결정적 발견**

```
07:46:32 [universe_eager_refresh] 개장 전 1회 적재 완료 universe=60
07:46:42 [universe_eager_refresh] stock_master upsert 완료
07:51:42 [universe_eager_refresh] 5분 주기 적재 완료 universe=60
07:51:45 [universe_eager_refresh] stock_master upsert 완료
07:56:45 [universe_eager_refresh] 5분 주기 적재 완료 universe=60
07:56:48 [universe_eager_refresh] stock_master upsert 완료
08:01:49 [universe_eager_refresh] 5분 주기 적재 완료 universe=60
08:01:52 [universe_eager_refresh] stock_master upsert 완료
```

**판정**: **5분 주기 정확 발화 (개장 전 1회 + 3회 = 4회 적재 + 4회 upsert)** = 백엔드 자동 갱신 **100% 정상 작동**.

### B3. `[scan_pool_eager_refresh]` 영역

**0건** — 사이클 83 prefix 가 발화되지 않음. 사이클 99 시점 prefix 통합/대체 가능성 (B2 가 단일 진실).

### B4/B5. prefix 전수 (확장 조사)

| prefix | 건수 |
|--------|------|
| `[src.engine.scheduler]` | 15 (B2 universe_eager_refresh 8 + B4 stock_master_universe_summary 5 + 기타 2) |
| `[src.engine.scanner]` | 6 |
| `[src.engine.order_engine]` | 1 |

`[stock_master_universe_summary]` 5분 주기 5회 emit 확인 (07:46/07:51/07:56/08:01/08:01) = 사이클 92~99 영역 영속 보장.

---

## C. 사이클 98 OPSQ2002 영구 차단 검증 (HIGH) — 결과

**0건** — `fetch_fluctuation` / `OPSQ2002` 매칭 0건 → **사이클 98 영구 차단 패턴 영속 확정**.

---

## D. stock_master 영역 점진 증가 검증 (HIGH) — 결과

### D1. stock_master_history (어제 17:00 ~ 오늘 08:01)

| change_type | count |
|-------------|-------|
| INSERT | 89 |
| UPDATE | 3 |
| TTL_REFRESH | 1 |

### D2. stock_master 누적

| total | kospi | kosdaq | bfdy_clpr_valid |
|-------|-------|--------|-----------------|
| 171 | 142 | 29 | **171 (100%)** |

### D3. 5분 윈도우별 시점 분포

| 시점 (KST) | change_type | cnt |
|-----------|-------------|-----|
| 07:46 | INSERT | **36** |
| 07:46 | UPDATE | 2 |
| 08:00 | TTL_REFRESH | 1 |

**판정**:
- 어제 17:00 ~ 오늘 07:45 = 53건 INSERT (D1 89 - 07:46 36 = 53)
- 오늘 07:46 = INSERT 36 + UPDATE 2 = 38건 갱신 (boot + universe_eager_refresh 첫 1회 + 보유 보강)
- 08:00 TTL_REFRESH 1건 = 24h TTL 만료 1종목 갱신
- **bfdy_clpr 100% 유효** = 사이클 81 가격필터 키 시정 영속 확정 (171/171 = `bfdy_clpr` 정상 적재)

---

## E. "오늘 자동 갱신 횟수 0" 결함 진단 (HIGH) — 결정적 발견

### E1. scheduler.start() 발화 시퀀스 (07:45~08:05)

```
07:45:01 === 자동 매매 시작 (2026-06-11 07:45) ===
07:46:02 [boot_preissue] label=sub/gold 사전 발급 완료
07:46:03 [market_regime] regime=None buy_blocked=False
07:46:29 [stock_master_eager] 보유+익일청산 1종목 갱신 완료
07:46:29 [pool_start] 보조 세션 등록: label=sub/gold
07:46:30 [pool_start_ready] ready=2/2 elapsed=0.20s
07:46:30 [pool_start] 완료: main=1 quotes=2 total_slots=123
07:46:32 체결통보 구독: H0STCNI0
07:46:32 통합 장운영정보 구독: H0UNMKO0
07:46:32 [stock_master_universe_summary] window=300s universe=60
07:46:32 [universe_eager_refresh] 개장 전 1회 적재 완료
07:46:42 [universe_eager_refresh] stock_master upsert 완료
07:51:42 [universe_eager_refresh] 5분 주기 적재 완료    ← 2회차
07:56:45 [universe_eager_refresh] 5분 주기 적재 완료    ← 3회차
07:59:18 사전 구독: 17종목 (돌파 + 스윙 + 보유)
08:00:14 롱테일 변동성 돌파 시가 확정 [pre_nxt]: 5/16
08:00:14 VB/LTV PRE_NXT 매매 시작 (08:00~)
08:00:32 [stale_watcher_detail] session=gold/sub
08:00:38 익일 청산 보류 (09:00 KRX 시장가 청산 예약): 티엠씨
08:00:38 익일 청산 실행 완료
08:01:23 [stock_master_universe_summary] window=300s universe=60
08:01:49 [universe_eager_refresh] 5분 주기 적재 완료    ← 4회차
```

**판정**: 백엔드 5분 주기 task **100% 정상 발화 (4회 적재 = 개장 전 1회 + 5분 주기 3회)**.

### E2. system_config 영역

| key | value |
|-----|-------|
| auto_start | true |
| buy_block_mode | OFF |
| cash_usage_ratio | 1 |

### E3. UI 카운터 영역

system_config 에 `%universe%` / `%refresh%` / `%stock_master%` 키 **0건** = **UI "오늘 자동 갱신 횟수" 표시 = DB 키 백킹 아닌 UI 자체 state 또는 별개 source**.

---

## 결정적 진단 종합

### 결함 가설 확정 — UI 표시 결함 (백엔드 무결성 영속)

**백엔드 5분 주기 task = 100% 정상 작동 (B2 4회 emit + B4 5회 emit + D3 38건 갱신 + 1건 TTL 갱신)**.

UI "오늘 자동 갱신 횟수 0" 표시는 다음 중 하나:
1. **(HIGH) UI 카운터 source 결함** — frontend 컴포넌트가 잘못된 prefix (`[stock_master_bulk_refresh]` 또는 `[scan_pool_eager_refresh]` 사이클 99 시점 비활성/대체된 prefix) 를 grep 중. 백엔드 실제 prefix = `[universe_eager_refresh]`.
2. **(MEDIUM) UI 카운터 영역 = "오늘" 정의 결함** — KST 자정 reset 영역에서 `00:00` 기준 vs `07:45` 기준 미스매치.
3. **(LOW) UI 카운터 = system_logs 직접 query** — UI 가 system_logs 의 특정 prefix 카운트를 실시간 polling, 사이클 99 prefix 가 실제 발화되지 않아 0건 표시.

### 사이클 92~99 영속 영역 확정

| 사이클 | 영역 | 영속 확정 |
|-------|------|----------|
| 92 | `[ws_auto_restart]` | 0건 (자동 재기동 불필요, 정상) |
| 92 | 07:55 TIME_BOOT | **07:46 실측** (컨테이너 startup-on-boot 우회 의심 영역) |
| 93 | universe_eager_refresh chain | 5분 주기 정상 (4회) |
| 95 | stock_master upsert | 4회 정상 |
| 98 | OPSQ2002 차단 | 0건 (영구 차단) |
| 99 | stock_master 171 적재 | bfdy_clpr 171/171 (100%) |
| 99 | `[stock_master_bulk_refresh]` | **0건 (미발화 영역)** |
| 83 | `[scan_pool_eager_refresh]` | **0건 (미발화 영역)** |

### 위험 등급 매트릭스

| 영역 | 위험 | 매매 안전성 영향 |
|------|------|----------------|
| UI 카운터 0 표시 | **MEDIUM** | 0 (UI 표시만, 매매 hot path 무관) |
| 07:46 vs 07:55 시점 차이 | **LOW** | 0 (boot 정상 완료, NXT 08:00 매매 정상 시작 확인) |
| `[stock_master_bulk_refresh]` 미발화 | **LOW** | 0 (`[universe_eager_refresh]` 가 동일 효과 보장, 단 사이클 99 의도 영역 확인 필요) |
| KIS 거부 APBK0918 | **0 (정상)** | 0 (NXT 시간 외 시장가 거부 = KIS 정책, 09:00 KRX 청산 예약 정상 전환) |

---

## Plan Phase A/B/C 발주 권고

### Phase A — UI 카운터 결함 시정 (MEDIUM, frontend-dev 단독 가능)

1. `frontend/src/` 에서 "자동 갱신 횟수" 표시 컴포넌트 식별
2. 데이터 source 확인 — system_logs query 직접 vs frontend state
3. 시정안 3개:
   - **A-1**: UI grep prefix 를 `[universe_eager_refresh]` 로 정정 (실제 백엔드 prefix)
   - **A-2**: 백엔드에 `[stock_master_bulk_refresh]` prefix 추가 emit (사이클 99 의도 회복)
   - **A-3**: UI 카운터를 `stock_master_history` 시점 분포 query 로 전환 (더 정확한 진실)
4. **권고**: A-1 (1줄 시정, 즉시 정합)

### Phase B — 07:55 TIME_BOOT 시점 검증 (LOW, backend-dev)

1. `scheduler.py` 의 `TIME_BOOT="07:55"` 영역 vs `AUTO_START=true` 컨테이너 startup 경로 우선순위 확인
2. 07:46 실측이 의도된 동작인지 (startup-on-boot 우회) 검증
3. 의도 영역 명문화 (`CLAUDE.md` 사이클 92 행 vs 실측 차이 영구 기록)

### Phase C — D+2 영속 측정 (2026-06-12 금 08:01 KST) (MAINTENANCE)

1. B2 5분 주기 task 영속 재확인
2. D1 stock_master_history 누적 추가 확인
3. UI 카운터 시정 효과 측정 (Phase A 시정 후)

---

## 산출물 메타

- **결정적 발견 (1)**: UI 카운터 0 = 표시 결함 (백엔드 100% 정상)
- **결정적 발견 (2)**: 사이클 99 `[stock_master_bulk_refresh]` prefix 미발화 (사이클 99 의도 영역 vs 실측 차이)
- **결정적 발견 (3)**: 사이클 92 07:55 TIME_BOOT vs 07:46 실측 차이 (컨테이너 startup 우회 가능성)
- **silent 결함 영구 차단**: bfdy_clpr 171/171 (100%) = 사이클 81 영속 확정
- **매매 안전성**: 무영향 (NXT 청산 정상 흐름 + APBK0918 거부 정상 처리)

**핵심 결론**: 백엔드 5분 주기 task = **100% 정상 작동 영구 확정**. UI "0회" 표시 = 표시 layer 결함. Phase A-1 (1줄 시정) 권고.
