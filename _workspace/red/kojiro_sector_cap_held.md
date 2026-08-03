# RED — kojiro 섹터 캡 "전일 보유 미집계" (`_position_sectors` 영속 맵, 채택안 A)

- 자문: `_workspace/domain_consult/kojiro_sector_cap_held_counting.md` (§채택안 A + §후속 검증 8 시나리오)
- 테스트 파일: `tests/unit/engine/strategies/test_kojiro_sector_cap_held.py` (11 케이스)
- production `kojiro.py` **무접촉** (Red 전용). backend-dev Green 인계 대기.

## 결함 요약

`check_buy_signal` 섹터 캡 카운트(`kojiro.py:708~709`)가 동일섹터 보유 집계를 `_candidates` 에만
의존 → held 가 ATR 밴드/유니버스 이탈로 `_candidates` 에서 부재하면 `same=0` → 캡이 막으려던
"한 섹터 N종목 집중 → 테마 붕괴 시 ±30% 동시 락아웃"을 무력하게 허용.

## 채택 설계 (안 A) — Green 이 만족해야 할 계약

- 신규 `KojiroStrategy._position_sectors: dict[str, str]` (`__init__` 에 `{}`, `_candidates` 와이프 독립).
- stamp 3지점:
  1. `recompute_held_atr` (657 인근, 이미 `_fetch_sector` 호출) — 보유 정본 소스(밴드/유니버스 이탈 무관).
  2. `check_buy_signal` **BUY 반환 직전** (739 인근) — 당일 매수분 영속화.
  3. `on_position_closed` (810~811) — `pop(ticker, None)`.
- 카운트 폴백(708~709): `sect = (self._candidates.get(t) or {}).get("sector") or self._position_sectors.get(t)`.
- fail-open 가드(704 cap=0 / 706 후보 미분류) **불변**.
- `_reset_daily_state` override **추가 금지** (base no-op 상속 → 멀티데이 held 섹터 밤샘 보존).

## RED 실행 결과 (`pytest -q`, 0.90s — 전 케이스 <1s)

`6 failed, 5 passed`

### RED 6 (미구현 필드/로직 참조 — Green 후 GREEN 전환)

| 케이스 | 실패 원인 (현행) |
|--------|------------------|
| `test_prev_day_held_out_of_candidates_counts_toward_sector_cap` **[핵심]** | `same=0` (held `_candidates` 부재) → `Signal.BUY` (기대 NONE) |
| `test_position_sectors_survives_candidates_wipe` | `_candidates` 와이프 후 `same=0` → BUY (기대 NONE) |
| `test_recompute_held_atr_stamps_position_sector` | `_candidates[t].sector=="바이오"`(recompute 실행 확인) 되나 `_position_sectors` 미stamp |
| `test_on_position_closed_pops_position_sector` | on_position_closed 가 `_held_stage3`/`_stop_floor` 만 pop → `_position_sectors` 잔존 |
| `test_buy_signal_stamps_position_sector` | BUY 반환 경로가 `_position_sectors` 미stamp |
| `test_buy_stamp_persists_across_candidates_wipe_for_next_candidate` | 당일 매수분 와이프 후 미집계 → 2번째 후보 BUY (기대 NONE, cap=1) |

### 봉인/fail-open 가드 5 (현행·Green 후 모두 GREEN)

| 케이스 | 봉인 대상 |
|--------|-----------|
| `test_unclassified_held_not_counted_failopen` | held 미분류(독립키) 미집계 → 후보 통과 (위양성 차단) |
| `test_reset_daily_state_does_not_wipe_position_sectors` | base no-op → 정산 후 섹터 보존 |
| `test_kojiro_has_no_reset_daily_state_override` | **AST**: kojiro `_reset_daily_state` override 추가 영구 차단 |
| `test_check_exit_signal_has_no_position_sectors_token` | **AST**: 청산 경로 섹터 상태 무주입 (매수 게이트 전용) |
| `test_position_sectors_isolated_to_kojiro` | 8 안전영역(risk/order_engine/scheduler/session/registry/api.order/realtime×3/auth.token) `_position_sectors` 참조 0건 |

## 합성 방식

순수 메모리 상태 주입(KIS respx 불요) — `freezegun` 은 매수창 09:05~09:30(2026-05-08 09:10) 재현에만.
recompute 케이스만 `get_recent_daily_normalized`/`enrich`/`get_master_raw` 를 monkeypatch(85 dummy candles + 1행 enriched + KRX 바이오 플래그).
