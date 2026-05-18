# 사이클 13 — BFB/VCP ScanMonitor 가시화 + stale 회복 강화 (Red 명세)

직전 베이스라인: commit 21984c2 (사이클 11, 2026-05-18).

## 배경

(1) bull_flag_breakout(BFB) / vcp_breakout(VCP) 두 신규 전략(2026-05-15)이 백엔드에 등록되었지만 ScanMonitor UI 에 노출되지 않음. 운영자 가시성 결함.

(2) 사이클 9 에서 KIS 차단 회피 목적으로 `STALE_FORCE_REREGISTER_AFTER 3→10` 으로 늦췄으나, 10회 × 120s = **20분 stale 누적 후에야 강제 재등록** 발화 — 단발 silent inactive 회복이 너무 느림. 분당 추가 트래픽 ~20 req 수준이라 KIS 한도(18 req/s = 1080/분)의 2%로 무시 가능 → **5회 × 120s = 10분으로 단축**.

## 행위 (2 항목)

### 행위 1 — `STALE_FORCE_REREGISTER_AFTER` 10 → 5
- `src/engine/scheduler.py::STALE_FORCE_REREGISTER_AFTER == 5` (이전 10)
- `STALE_WATCHER_INTERVAL_SECS == 120` 보존 (사이클 9)
- `STALE_FRESHNESS_SECS == 60` 보존 (5/12 의도)
- 분당 강제 재등록 트래픽: 보조 5 × 40 종목 × 2 / (120s/60) = 200 → 1/5 임계 (200/5=40 미만)
- 사이클 9 회귀 가드 의미 갱신:
  - `tests/unit/engine/test_stale_watcher_thresholds.py` 케이스 수 보존 (7)
  - 임계값 가정 10 → 5 갱신
  - 6회째에 강제 재등록 발화 / 5회까지는 resend (이전 11/10 동일 패턴)

### 행위 2 — ScanMonitor BFB/VCP 카드 노출
- `frontend/src/components/ScanMonitor.tsx`:
  - `BREAKOUT_KEYS` 4종으로 확장 (`volatility_breakout` / `long_tail_volatility` / `bull_flag_breakout` / `vcp_breakout`)
  - `BREAKOUT_LABELS` 신규 라벨 2종 추가:
    - `bull_flag_breakout`: "눌림목 돌파"
    - `vcp_breakout`: "VCP 변동성 수축"
  - 전체 탭 BREAKOUT 카운트 행 4종 모두 노출
  - 전략 탭 진입 시 BFB/VCP 도 운영시간 안내 + 타겟 가격 테이블 노출 (기존 VB/LTV 분기 그대로 활용 — 두 전략 모두 MAIN only 단일 보드)

## 회귀 테스트 매핑

| 행위 | 파일 | 케이스 |
|------|------|--------|
| 1 | `tests/unit/engine/test_stale_watcher_thresholds.py` (의미 갱신) | 7 (보존) |
| 2 | `frontend/src/components/__tests__/ScanMonitor.bfb_vcp.test.tsx` (신규) | 3 |

## 안전 원칙

- 매매 코드 무수정: `order_engine.py` / `risk.py::on_tick()` / 전략 파일 변경 0
- 백엔드 응답 키 무변경: ScanMonitor 는 기존 `strategies[key].scanned_count` / `targets` / `params` 만 사용 (BFB/VCP 도 이미 `get_scan_stats()` 보유)
- 사이클 9 KIS 차단 회피 정책 보존: 트래픽 산정 식 유지, 새 임계도 분당 200 req 미만
- 사이클 11 `get_buy_block_state` 60s TTL 캐시 무영향 (Risk Manager 호출 경로 무변경)

## 베이스라인 보존 확인

- 백엔드 1269 passed (사이클 11 시점)
- 프론트엔드 +3 신규 케이스 추가 (BFB/VCP 카드 렌더링)
