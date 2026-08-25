# 사이클 227 명세 — P0-1 Stage 0: acml_vol 실측 배관 + would_pass 관측 + P0-2 universe 가드 안전조건 시정

> 작성: team-leader (오케스트레이터), 2026-08-25
> 근거: `_workspace/00_URGENT_WORKLIST.md` P0-1·P0-2 + 도메인 자문 `_workspace/domain_consult/bfb_vcp_acml_vol_gate.md`
> 사용자 결정 (2026-08-25 확정):
> 1. **시정 방향 A-raw** — 실시간 누적거래량을 사이클 222-a `day_high` 선례로 흘린다. **8영역 수정 승인 = handler.py + risk.py 두 파일 한정.**
> 2. **Stage 0 관측 우선** — 게이트 행위 변경 0. 배관 + `would_pass` 관측 로그만. 1~2영업일 실측 후 게이트 전환은 별도 사이클.
> 3. **비중 현행 유지** (BFB 0.15 / VCP 0.10) — 다크런치 금지(Σ 정규화 위험 이전). 게이트 전환 사이클에서 재확인.
> 4. **P0-2 동반** — universe 가드 안전조건을 같은 배관으로 시정.

## 자문 핵심 (구현 구속력 있는 판정)

- **B(전일 확정치) 폐기** — 플래그/베이스는 수축 구간이라 전일 거래량 기준 게이트는 통과 확률 ~0 (결함 재생산).
- **폴백 sentinel 에 `0` 금지** — `0` 이 바로 P0 의 그 값. "미수신"과 "미달"을 타입 분리(None / -1) + 로그 마커 분리.
- **`len(fields) < 10` 가드 상향 금지** — `<15` 로 올리면 필드 10~14개 payload 가 통째 drop → 그 틱으로 돌던 손절·트레일링이 조용히 죽는다. `_parse_day_high` 선례대로 가드 유지 + `try/except → sentinel`.
- **`ticker_prices` 주입 절대 금지** — donchian `ext_pct` 커플링 (risk.py:409 주석 + 기존 가드).
- **관측 로그 폭주 금지** — P1-3(001450 이 2시간 로그 42% 점유) 교훈. cap 필수.
- **관측 판정 기준**: 주 3건↑ would_pass = 예상대로 → 게이트 전환 / 0건 = P1-3 래치 선행 필수 / 일 10건↑ = 스코프 불일치 등 재조사.
- ACML_VOL = `fields[13]` (KIS 정본 확인 완료, 46컬럼 3채널 동일). 분자·분모 스코프 불일치(H0UNCNT0 통합 vs 일봉 J)는 인지된 한계 — 정합화는 행위 변경이라 별도 사이클.

## 행위 목록 (Red → Green 단위)

### W1. handler.py — `_parse_acml_vol` + on_tick 전달 (8영역, 승인됨)

- `_parse_acml_vol(fields: list[str]) -> int`: `fields[13]` int 파싱. `len(fields) < 14` 또는 파싱 실패 → **`-1`** (sentinel — `0` 금지). 음수 값 응답도 `-1` 처리.
- `_handle_tick` 이 `await _on_tick(ticker, current_price, open_price, change_rate, day_high=day_high, acml_vol=acml_vol)` 전달.
- **기존 `len(fields) < 10` 가드 byte 불변** (상향 금지 — AST 가드로 봉인).
- 파싱 실패가 틱을 죽이지 않는다 (day_high 0 폴백 선례 — fail-open, 틱은 산다).

### W2. risk.py — on_tick 키워드 수용 + 관측 기록 (8영역, 승인됨)

- 시그니처: `*, day_high: int = 0, acml_vol: int = -1`.
- `acml_vol >= 0` 일 때만 `tick_volume.record_acml_vol(ticker, acml_vol)` 호출 (1 dict assign — `ticker_last_tick` 선례 비용).
- **`ticker_prices` 4키 불변** (`current_price`/`open_price`/`change_rate`/`prdy_ctrt`). `acml_vol` 키 대입 금지.
- 그 외 on_tick 행위 변경 0.

### W3. 신규 leaf 모듈 `src/engine/tick_volume.py` (8영역 미접촉)

- 모듈 전역 상태 + **날짜 키 자기 리셋** (`_emit_budget_clamp` DailyEmitCap 선례 — `_reset_daily_state` 훅 미의존, **scheduler.py diff 0 이 설계 목표**):
  - `record_acml_vol(ticker: str, value: int) -> None` — 저장 날짜(KST) != 오늘이면 전체 clear 후 기록. `value < 0` 무시.
  - `get_observed_acml_vol(ticker: str) -> int | None` — 저장 날짜 != 오늘이면 `None` (크로스데이 오염 차단). 미관측 `None` (**`0` sentinel 금지**).
  - `reset_for_test()` — 테스트 격리용.
- DB/HTTP/시계 외부 의존 최소 (KST date 만). `portfolio_risk.py` 순수 모듈 선례.

### W4. BFB would_pass 관측 훅 (`bull_flag_breakout.py` — 행위 변경 0)

- `check_buy_signal` 거래량 컷 평가 지점(retention 완주 직후, 기존 `:844` "거래량 컷" 블록 **직전**)에 관측 블록:
  - `observed = tick_volume.get_observed_acml_vol(ticker)` / `vol_threshold` 는 기존 식 그대로 계산.
  - `would_pass = observed is not None and observed >= vol_threshold`.
  - INFO 로그 (grep 정밀성 — P2-7 교훈, 로그 본문에 타 마커 문자열 포함 금지):
    - 관측 있음: `[bfb_vol_gate_observe] ticker=%s observed=%d threshold=%d would_pass=%s`
    - 미수신: `[bfb_vol_gate_observe] ticker=%s reason=no_observation threshold=%d` (미수신·미달 분리 — 자문 C. `logger.debug` 단독 금지, INFO 로 `system_logs` 도달)
  - **cap**: `(ticker, outcome)` 당 1회/일, outcome ∈ {pass, fail, no_obs} (최대 3행/종목/일). 날짜 키 자기 리셋.
  - cap 과 무관하게 `_scan_stats` 카운터 누적: `vol_gate_observe_pass` / `vol_gate_observe_fail` / `vol_gate_observe_no_obs` (총량은 API 로 관측).
  - 관측 블록 전체 try/except 흡수 — 실패 시 `[bfb_vol_gate_observe_failed]` WARNING 1행 (cycle225 교훈: debug 단독 금지) 후 기존 흐름 계속. **관측기 자기실패가 매수 평가를 죽이면 안 된다.**
- **기존 거래량 컷 4줄(`info_price`/`acml_vol`/`vol_threshold`/`if acml_vol < vol_threshold`) byte 불변** — Stage 0 보증. 여전히 `Signal.NONE`.

### W5. VCP 동일 관측 훅 (`vcp_breakout.py` — 행위 변경 0)

- 마커 `[vcp_vol_gate_observe]`, 나머지 W4 동일. VCP 는 edge-crossing 재트리거로 관측 이벤트 다발 가능 → cap 필수.
- would_pass 의미는 기존 게이트와 거울 정합: `vol_threshold <= 0` 이면 게이트가 통과시키므로 `would_pass=True` (outcome=pass).
- `_scan_stats` 카운터 동일 3키.

### W6. P0-2 — universe 가드 안전조건 시정 (`stale_universe_guard.py` + 필요 시 `quotation.py` — 둘 다 8영역 아님)

- 결함: `today_volume` = `inquire_ccnl`(FHKST01010300) output ~30행 `cntg_vol` 합 → 임계 10,000 을 사실상 항상 미달 → "스테일 6회 = 무조건 축출" 퇴화. 2026-08-25 BFB 후보 20/48 축출 실측.
- 시정 — 안전조건 소스를 **진짜 당일 누적**으로:
  1. **1순위**: `tick_volume.get_observed_acml_vol(ticker)` (마지막 관측 누적 — stale 종목이라도 stale 전 관측값이 "오늘 유의미하게 거래됐나"에 유효).
  2. **2순위 (REST 폴백)**: KIS MCP 정본으로 FHKST01010300 output row 에 `acml_vol` 존재 여부 확인 → 존재하면 `inquire_ccnl` 반환 dict 에 `acml_vol` 키 추가(첫 row 추출, **추가 KIS 호출 0**). 부재 확정 시 `/quotations/inquire-price`(FHKST01010100, 화이트리스트 기존재) 로 targets 한정 1회 조회 + 50ms sleep.
  3. **둘 다 부재** → **제외 보류** (기존 `ccnl is None → 보류` 패턴 정합. 잘못된 축출 = 매수 평가 상실이 잘못된 보류 = 슬롯 낭비보다 훨씬 비싸다. 슬롯 34% 사용 실측).
- `[universe_excluded]` 로그에 `acml_vol=%d vol_source=tick|rest` 병기 + 기존 `today_volume` 필드 유지(운영 grep 연속성).
- `UNIVERSE_LOW_VOLUME_THRESHOLD=10_000` 값 불변 (임계 재튜닝 아님 — 분자 정의 시정).
- 보유/익일청산 절대 보호·50ms sleep·`_reset_daily_state` 동행 clear 등 기존 계약 전부 불변.
- 대량 동시 축출 버스트 대응은 범위 외 (워크리스트 명시 — 별도 판단).

### W7. 회귀·AST 가드

- **end-to-end**: handler 가 payload fields[13] 을 파싱해 on_tick 에 전달하고 risk 가 tick_volume 에 기록함을 프로덕션 코드 경유로 검증 — **P0 를 처음부터 잡았을 바로 그 테스트** (대입부 존재 검증).
- **AST-1**: 전 소스에서 `ticker_prices[...]["acml_vol"]` **대입** 0건 영구 (유령 키 재발 + donchian 커플링 차단).
- **AST-2**: BFB/VCP 기존 거래량 컷 블록 byte 불변 (Stage 0 봉인 — 게이트 전환 사이클에서 이 가드를 의미 전환).
- **AST-3**: handler `len(fields) < 10` 가드 불변 (상향 금지).
- 은폐 테스트 3파일(`test_bull_flag_breakout.py`/`test_bull_flag_breakout_retention.py`/`test_vcp_breakout.py` 의 `ticker_prices["acml_vol"]` 손주입): Stage 0 에서는 게이트가 여전히 그 키를 읽으므로 **유지**하되, 각 주입 지점에 "게이트 전환 사이클에서 tick_volume 주입으로 의미 전환 의무" 주석 마커. 전환 사이클 의무로 워크리스트에 기재.
- 전체 백엔드 회귀 PASS.

### W8. 문서 동기화 (구현 완료 후)

- `CLAUDE.md` 하네스 표 1행(15행 유지) + `docs/HARNESS_CHANGELOG.md` verbatim append.
- `src/engine/strategies/CLAUDE.md` BFB/VCP 헤더 — "Stage 0 관측 중 (게이트 미전환, 매수 여전히 차단)" 상태 명시.
- `_workspace/00_URGENT_WORKLIST.md` P0-1(Stage 0 완료·관측 중·전환 판정 기준)·P0-2(시정 완료) 갱신.

## 제약 (전 에이전트 공통)

- 8영역 수정은 **handler.py + risk.py 두 파일, 위 명세 범위 한정**. 그 외 8영역(order_engine/auth/api/order.py/session.py/scanner.py/strategy_registry.py) diff 0.
- **scheduler.py diff 0** (미커밋 cycle221 잔류와의 커밋 분리 — 날짜 키 자기 리셋 설계가 그 목적).
- `git checkout` / `stash` / `restore` 절대 금지 (cycle221 잔류 보호).
- 커밋·푸시 금지 — 사용자 명시 지시 대기.
- 진입 임계 값(breakout_volume_mult 등)·비중·DEFAULT_PARAMS 무변경.
- KIS 스펙 의문은 kis-mcp-query (FHKST01010300 output 의 acml_vol 존재 여부 W6 필수 확인).
