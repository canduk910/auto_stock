# 사이클 220 — kojiro 브레이크이븐 플로어 이식 (다크런치) · Red 기록

작성: tdd-engineer (2026-08-18) · 구현: backend-dev (kojiro.py 단독)
자문: `_workspace/domain_consult/kojiro_exit_loss_review.md` (Q2 1순위 = 청산 브레이크이븐 플로어, 최고 EV)
선례: donchian P1 (`breakeven_promote_atr=1.5` 라이브) · BFB/VCP 사이클 C (`0.0` 다크런치)

## 동기부여 (실측)

08-18 kojiro 9왕복 중 샹들리에 청산 3건(영원무역 등)이 전부 +1.5N 승격선을 넘긴 뒤
전량 반납 — 이익보호 장치 전무. 영원무역(111770):

    매수 86,800 · 고점 95,000(+9.4%) · ATR 4,736
      1.5N 승격선 = 86,800 + 1.5×4,736 = 93,904  ← 고점이 넘김
      샹들리에선 = 95,000 − 2.5×4,736 = 83,160    ← 완전 왕복 시 반납
      실제 청산 83,000 (−4.4%)

브레이크이븐 플로어: 고점이 1.5N 넘긴 순간 `_stop_floor` 를 매수가로 승격 → 완전
왕복 시 86,800(±0%) 부근 청산. **VCP/BFB 는 boolean 래치(`_breakeven_latched`)를 썼지만
kojiro 는 기존 `_stop_floor` tighten-only 래칫을 그대로 승격**(ATR 팽창해도 buy 유지) —
별도 래치 set 불필요.

## 구현 명세 (backend-dev — kojiro.py 단독, 정확 삽입 위치 3곳 + 미러 1곳)

### ① DEFAULT_PARAMS (다크 = byte-identical)
`kojiro.py:154` `hard_stop_pct` 근처에 신설:
```python
"breakeven_promote_atr": 0.0,   # 다크런치 — 0=분기 미진입, DB 토글로 1.5 활성 (BFB 사이클 C 선례)
```
PARAM_RANGES/INT_PARAMS **미편입** (청산 정체성 상수).

### ② check_exit_signal §2 — 삽입 위치 = 현 `kojiro.py:867` (`self._stop_floor[ticker] = eff`) **직후**, `kojiro.py:870` (`if eff > 0 and current_price <= eff`) **직전**
```python
be_mult = float(params.get("breakeven_promote_atr", 0) or 0)
if be_mult > 0 and atr > 0 and pos.buy_price > 0 and \
   pos.high_since_buy >= pos.buy_price + be_mult * atr:
    promoted = max(eff, pos.buy_price)
    if promoted != eff:
        logger.info(
            "[kojiro_breakeven_promote] %s 고점(%d) ≥ 매수가(%d)+%.1f×ATR(%.1f) → 손절선 %d→%d",
            ticker, pos.high_since_buy, pos.buy_price, be_mult, atr, eff, promoted,
        )
    eff = promoted
    self._stop_floor[ticker] = eff   # 기존 tighten-only 래칫에 영속 (ATR 팽창해도 유지)
```
ATR 소스 = 위에서 이미 계산한 `atr = self._effective_atr(ticker)` (live). kojiro 는 `_entry_atr` 미도입 = 단일 메커니즘 독트린.

### ③ recompute_held_atr 재시작 재도출 — 삽입 위치 = 현 `kojiro.py:726-729` floor 래칫 블록 (`if base > 0: self._stop_floor[ticker] = max(...)`) **직후**
동일 승격 로직(`be_mult>0` 게이트). H-1 `_apply_high_since_buy_from_candles`(현 :684-696)가 **먼저** 고점을 복구하므로 이 블록 시점 `pos.high_since_buy` 는 복구값. `atr` 은 이 블록의 `atr_val` 사용.

### ④ _position_stop_price read-only 미러 — 현 `kojiro.py:984` (`return max(pct_line, atr_line, trail_line)`)
```python
be_mult = float(params.get("breakeven_promote_atr", 0) or 0)
be_line = int(pos.buy_price) if (
    be_mult > 0 and atr > 0 and pos.high_since_buy >= pos.buy_price + be_mult * atr
) else 0
return max(pct_line, atr_line, trail_line, be_line)
```
⚠️ `_stop_floor` **무변조** (이 메서드는 매수 게이트 read-only 추정기 — 청산 규약을 부작용으로 바꾸면 안 됨. 독트린 ":961 쓰기만 하고 갱신하지 않는다" 유지).

### 불변 (FREEZE / 도메인 금기)
§1 백스톱(−8%) · §3 스테이지3 · **§4 샹들리에 trail_atr=2.5(조임 금기, domain)** · 진입 로직 전체 · `_reset_daily_state` 미접촉(_stop_floor 밤샘 보존). 8영역 무접촉.

## Red 산출물

파일: `tests/unit/engine/strategies/test_cycle220_kojiro_breakeven_floor.py` (21 케이스)

실행: `python -m pytest tests/unit/engine/strategies/test_cycle220_kojiro_breakeven_floor.py -q`
→ **8 failed, 13 passed** (RED 확정 — 구현 후 21 전량 PASS 기대)

### RED 드라이버 8 (현 코드 부재 → FAIL → 구현 후 PASS)
| 테스트 | 검증 | 현재 실패값 → 기대값 |
|--------|------|---------------------|
| test_default_param_is_dark | DEFAULT 키 존재 = 0.0 | `None` → `0.0` |
| test_promotion_fires_and_locks_at_buy | 승격 발화 + floor=buy + 로그 1회 + buy 이하 STOP_LOSS | `_stop_floor` 77,328 → 86,800 |
| test_promotion_tighten_only_no_fire_above_buy | 승격 후 buy 위 미발화 + floor=buy | `_stop_floor` 77,328 → 86,800 |
| test_ratchet_tighten_only_survives_atr_expansion | ATR 2배 팽창해도 floor=buy 유지 | 77,328 → 86,800 |
| test_fat_tail_floor_fixed_at_buy_chandelier_separate | 플로어 buy 고정(트레일 아님) | 77,328 → 86,800 |
| test_chandelier_trails_above_floor_no_fat_tail_cut | 샹들리에가 플로어 위 트레일(절단 안 됨) | 77,328 → 86,800 |
| test_restart_rederivation_promotes_floor_when_enabled | recompute → floor 재도출 buy | 77,328 → 86,800 |
| test_risk_cap_mirror_promotes_when_condition_met | `_position_stop_price`≥buy → open_risk 0 | 82,064 → 86,800 |

### GUARD 13 (현재 PASS — 구현 후 유지)
다크(mult=0) byte-identical(2) · 미도달 미승격 · 재시작 다크 재도출 · 리스크캡 미러 다크 · `_position_stop_price` read-only AST · §1 백스톱 · §3 스테이지3 · §4 trail_atr=2.5 상수 · check_buy_signal FREEZE AST · `_reset_daily_state` override 금지 AST · check_exit `_open_risk` 미참조 AST · PARAM_RANGES/INT_PARAMS 제외

## 테스트 설계 노트

- **exit 테스트**: `_hold(high, atr)` — `_candidates[ticker]["atr"]` live 세팅. §3 격리 = `_held_stage3` 빈 dict. freeze_time 불필요(check_exit_signal 시간 게이트 없음).
- **재시작(recompute) 테스트**: TR 매일 4,736 일정한 flat 85봉 합성 → Wilder ewm(1/20)이 **정확히 4,736 수렴**(결정론, floor 77,328 재현 확인). `pos.high_since_buy=97,000` 초기 세팅 + 봉 high 91,000(하회) → 복구가 97,000 유지 → 승격 조건 충족. `_RecomputeDeps` 로 DB 일봉/update_high/write_log/_fetch_sector 격리.
- **핵심 수치**: BUY 86,800 · ATR 4,736 · N15=93,904(정확 정수) · ATR_FLOOR 77,328 · PCT_BACKSTOP 79,856(−8.0% 정확) · 샹들리에@high95k=83,160.

## 기존 회귀 (baseline)

kojiro 스위트 9파일 **204 PASS** (mult=0 기본이라 구현 후에도 무영향 기대). 신규 파일은 기존 파일 무변경.

## backend-dev 인계 체크리스트

1. 삽입 4곳(위 ①②③④) + 로그 포맷 그대로.
2. `atr`/`atr_val` 소스 = 각 컨텍스트의 기존 변수 재사용(신규 fetch 금지).
3. `_position_stop_price` 에서 `_stop_floor` 쓰기 금지(read-only 미러).
4. 8영역 + 진입 로직 diff 0 확인.
5. Green 확인: 위 파일 21/21 PASS + kojiro 스위트 204 PASS 회귀 0.
