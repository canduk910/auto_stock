# cycle382 명세 — 시장 유닛(단계형) · 터틀 4전략 신규 진입 설계 랏 축소 · shadow 로 시작

- 작성: domain-expert(명세 저자) · 2026-09-27(일, 휴장) · HEAD `9a0af9e3` · 범위 = 구현 명세. `src/`·`tests/` 무수정 · 운영 DB·KIS 호출 0 · 커밋 없음
- 설계 정본: [`_workspace/domain_consult/cycle376_market_unit.md`](../domain_consult/cycle376_market_unit.md)(이하 「자문」) §6.3 · §7.3 · §10 · §11
- 사용자 결정(2026-09-27): 「시장유닛 단계형 권고대로 채택」 — 워크리스트 「09-27 결정 세트」 첫 줄(터틀 4전략 · 축소일 1주 폴백 금지 · 1주 shadow 뒤 enforce · `cash_usage_ratio` 가 아니라 신규 진입 크기)
- 이 명세가 자문 §7.3 에서 **바꾼 것** 다섯 가지(모두 과업 지시 또는 아래 근거):
  1. 계산 자리 = `boot_manager` 가 아니라 **4전략 `prepare()`**(과업 지시). 결과는 전략 객체에 **거래일별로** 둔다(§3).
  2. 관문 `_apply_budget_limit` 에 `allow_fallback` 키워드를 **더하지 않는다**. 축소일 분기는 수량 0 을 관문에 넘기기 전에 `return 0` 한다 — 폴백 분기에 구조적으로 닿지 않는다. 관문 계약(G-242-3·G-245-3 순서 가드)이 한 글자도 안 바뀐다(§5.4).
  3. 축소일 터틀 → 비중 경로 낙하 금지를 **원인 불문**으로 적용한다(사용자 결정 원문 그대로). 자문은 데이터 결손(ATR 0 등) 낙하는 남겨 두자고 했다(§5.5).
  4. `rounds_to_zero`(½·¾ 로 줄였더니 0주)도 **신호 시점**에 거른다. 자문은 수량 단계에서 0 을 돌려주자고 했다. 그러면 donchian·VCP 의 ½ 날 매수 대부분이 `order_engine` 의 「매수 수량 0 → 900s cooldown (투자금: …)」 WARNING 으로 찍혀 cycle316 과 같은 「투자금 부족」 오귀인이 된다(§6).
  5. 마커를 과업 서식에 맞춰 다시 짰다 — 매수 시도 1건 = `[market_unit]` 한 줄(§7).

---

## 0. 결론

1. **규칙** — KODEX 200(`069500`) 일봉 종가로, 그 거래일의 **직전 영업일 봉**(D−1)에서 판정한다. 60일선 위·60일선 상승 = **1**, 위·하락 = **¾**, 아래·상승 = **½**, 아래·하락 = **0**.
2. **자리** — 4전략(kojiro · donchian_swing · bull_flag_breakout · vcp_breakout) `prepare()` 가 계산해 전략 객체에 저장한다. `calc_buy_quantity`·`check_buy_signal` 은 **메모리만 읽는다**(await·DB·HTTP 0 — A-PURE·A-ATOMIC 그대로).
3. **효과** — 신규 진입의 **설계 랏만** m 배 한다(터틀 유닛·비중 경로 모두 `int(예산 × m)` 로 계산). 예산(`total_investment`)·잔여·K축·ρ축·일일 손실 한도·오픈리스크 분모·보유분·청산 규약은 **전부 그대로**다.
4. **축소일(m < 1)** — 1주 폴백 없음 · 터틀 → 비중 경로 낙하 없음 · 터틀 ATR 스탬프는 m 과 무관하게 사이징 ATR 그대로.
5. **m = 0(과 줄여서 0주가 되는 경우)** 은 신호 단계에서 `Signal.NONE` — 주문 엔진에 닿지 않으므로 「투자금 부족」·900초 쿨다운으로 기록되지 않는다.
6. **결측·stale·예외 → m = 1**(현행 동작) + WARNING. 결측이 매수를 조용히 줄이지 않는다.
7. **모드** `market_unit_mode ∈ off|shadow|enforce`. 4전략 `DEFAULT_PARAMS` 기본 **`shadow`**(계산·기록만, 수량 불변). 키 부재·오타 = `off`. `PARAM_RANGES`·`INT_PARAMS`·AI 자동 적용 경로 편입 금지. 킬스위치·집행 전환 = `PUT /api/strategies/{id}/params` **즉시**.
8. **8영역·`scheduler.py`·`boot_manager.py` 무접촉.** 바뀌는 코드 = 새 leaf `src/engine/market_unit.py` · `strategy_base.py`(헬퍼 추가, 관문 본문 무변경) · 전략 4파일 · `param_catalog.py`.
9. **`needs_user = false`** — 사용자 결정 범위 안에서 모두 정해진다. enforce 전환(1주 뒤)은 별도 사용자 승인 뒤 PUT 이다.

---

## 1. 상태 규칙 (정확한 정의)

### 1.1 입력 봉

| 항목 | 정의 |
|---|---|
| 원천 | `stock_master_daily` 의 `ticker = "069500"`(KODEX 200) `close_price`. 조회 = `stock_master_daily.get_recent_daily("069500", FETCH_ROWS=120)`(DB 전용, KIS 폴백 없음 — `market_regime._compute_single_etf_stage` 와 같은 seam) |
| 기준 거래일 `as_of_date` | `prepare()` 의 `_resolve_prepare_as_of(as_of)` 반환값 그대로. 라이브(`as_of=None`) = 오늘(KST), 저녁 미리보기 = 다음 거래일 |
| 쓰는 봉 | **`bas_dd < as_of_date` 인 행만.** `bas_dd` 오름차순 정렬 후 **마지막 80행**(창 `w`, `w[-1]` = D−1 봉) |
| D−1 의 뜻 | 라이브 07:45 부팅 = 전 영업일 20:30 적재 봉. 라이브 재준비가 20:30 뒤에 돌아도 오늘 봉은 `bas_dd < 오늘` 로 빠진다(장중 재계산 없음과 같은 값). 미리보기(21:00, `as_of`=다음 거래일) = **오늘 봉**(`as_of−1` 봉) |
| `bas_dd` 파싱 | `date`·`datetime`·ISO 문자열 수용(`market_regime._is_daily_row_stale` 와 같은 관용). 파싱 불가 행은 버린다 |

### 1.2 판정식 — 합으로 비교한다(정확 산술)

```
w      = 마지막 80개 종가 (오름차순)          # w[0] = D−80, w[-1] = D−1
sum60      = sum(w[20:80])                   # SMA60(D−1) × 60
sum60_prev = sum(w[0:60])                    # SMA60(D−21) × 60  (= 20봉 전의 60일선)
above   = w[-1] * 60 >  sum60                # 종가 > SMA60(D−1)      — 엄격 부등호
rising  = sum60      >  sum60_prev           # SMA60(D−1) > SMA60(D−21) — 엄격 부등호
```

- 두 창의 길이가 같아(60) **평균 비교 = 합 비교**다. 합은 정수(또는 `Decimal(str(v))`)로 더한다 — 부동소수 평균의 동률 흔들림을 없앤다.
- **기울기 정의** = 「오늘의 60일선이 **20봉 전**의 60일선보다 높은가」. 봉 기준이다(달력일 아님). 재현(`c376_signals.py` `ks_slope60` = `m60 > m60[t−20]`)과 같다.
- **동률은 약한 쪽으로** — `종가 == SMA60` 이면 `above=False`, `SMA60 == 20봉 전 SMA60` 이면 `rising=False`. 재현의 `x > m` · `m60 > m60_prev` 와 같다.
- 로그용 `sma60 = sum60/60`, `sma60_prev = sum60_prev/60`(소수 둘째 자리).

### 1.3 배수표 (모듈 상수 — 파라미터로 열지 않는다)

| state | above | rising | m | 트레이더 한 줄 |
|---|---|---|---|---|
| `up_rising` | 1 | 1 | **1.0** | 추세 확인 — 설계 랏 그대로 |
| `up_falling` | 1 | 0 | **0.75** | 60일선 위지만 선이 꺾였다 — 조금 줄인다 |
| `down_rising` | 0 | 1 | **0.5** | 60일선 아래지만 선은 아직 오른다 — 반만 |
| `down_falling` | 0 | 0 | **0.0** | 확인된 하락 추세 — 돌파를 사지 않는다 |
| `unavailable` | — | — | **1.0** | 모른다 — 현행 그대로(fail-open) |

`MA_WINDOW=60` · `SLOPE_LOOKBACK=20` · 배수 4개는 `market_unit.py` **한 곳에만** 둔다(AST A02).

### 1.4 첫 실전일 기대값 (tester 손계산 대상)

- 09-28(월) 부팅의 D−1 = **09-23(수)**(09-24~26 추석). `previous_trading_day(09-28)` 이 09-23 을 돌려주는지부터 본다.
- 자문 §1 의 코스피 지수 기준 09-23 상태는 **`up_falling`(¾)** 이다. KODEX 200 판정은 코스피와 94.8% 일치하므로 같은 값일 가능성이 크지만 **추정**이다. 손계산 쿼리:
  `SELECT bas_dd, close_price FROM stock_master_daily WHERE ticker='069500' AND bas_dd < '2026-09-28' ORDER BY bas_dd DESC LIMIT 80;`

---

## 2. 데이터 충분성 · 신선도 · 실패 (전부 m = 1)

판정 순서 = ① 행 수 → ② 신선도 → ③ 종가 품질. 첫 실패에서 멈춘다.

| reason | 조건 | 결과 |
|---|---|---|
| `rows_short` | 필터 뒤 행 < **80**(`MIN_ROWS = MA_WINDOW + SLOPE_LOOKBACK`). `get_recent_daily` 는 DB 오류 때 `[]` 를 돌려주므로 조회 실패도 여기로 온다 | m=1 + WARNING |
| `stale_head` | `expected_head = await trading_calendar.previous_trading_day(as_of_date)`. 값이 있으면 **`head < expected_head`** 이면 stale(`head > expected_head` 는 신선으로 본다 — 달력 불일치여도 데이터는 충분히 새롭다). 값이 `None`(달력 모름)이면 `(as_of_date − head).days > 10`(`STALE_FALLBACK_MAX_CALENDAR_DAYS`, `market_regime.ETF_STALE_MAX_CALENDAR_DAYS` 와 같은 값 — 테스트로 묶는다) | m=1 + WARNING |
| `bad_close` | 창 80행 안에 `None`·비수치·비유한·≤0 종가가 하나라도 있다(창 밖 행은 무시) | m=1 + WARNING |
| `exception` | 그 밖의 어떤 예외 | m=1 + WARNING |

- **엄격 신선도를 택한 이유** — cycle363 「직전 영업일」 규약과 같고, 20:30 적재 실패는 이미 `[daily_head_stale]` 로 시끄럽다. 대가: 0 상태 국면에서 적재가 실패한 날 하루는 설계 랏 그대로 산다. 기각한 대안 ① 1영업일 지연 허용(맞을 확률 ≈96.5% 이지만 규칙이 하나 더 는다) ② KIS 폴백(`get_recent_daily_normalized`)(키 모양이 다르고 자문의 「추가 KIS 호출 0」 과 어긋난다).
- **일봉 적재 대상 여부** — `069500` 은 지수 편입이 아니라 시총·거래대금 자격(`scanner._is_daily_load_universe`)으로 적재된다. 그 자격을 잃으면 매일 `stale_head` 로 m=1 이 된다. 적재 강제 포함은 `scanner.py`(8영역)라 이번 범위 밖이다 — `[market_unit_unavailable]` 가 **매일** 뜨면 그것이 신호다(§12 후속).
- **중간 결측 봉** — 검사하지 않는다. 증분 적재가 T−7 창으로 다음 날 메우고, 한 봉 밀림의 판정 영향은 무시할 만하다.

---

## 3. 계산 자리와 저장

### 3.1 새 leaf `src/engine/market_unit.py`

- import: 표준 라이브러리만(`dataclasses`·`datetime`·`decimal`·`logging`·`math`·`types.MappingProxyType`). `src.db.stock_master_daily` 와 `src.engine.trading_calendar` 는 **함수 안 지연 import**(호출 시점 모듈 속성 조회 — 테스트 monkeypatch seam). 8영역·`scheduler`·`boot_manager`·`market_regime` import 0.
- 로거 = `logging.getLogger("src.engine.market_unit")` — **모든 시장 유닛 마커는 이 로거 하나로** 낸다(테스트가 `caplog.set_level(logging.INFO, logger="src.engine.market_unit")` 한 줄로 잡도록).
- 공개 이름:

| 이름 | 종류 | 내용 |
|---|---|---|
| `SOURCE_TICKER="069500"` · `MA_WINDOW=60` · `SLOPE_LOOKBACK=20` · `MIN_ROWS=80` · `FETCH_ROWS=120` · `STALE_FALLBACK_MAX_CALENDAR_DAYS=10` | 상수 | |
| `MULTIPLIERS` | `MappingProxyType` | §1.3 네 칸 |
| `MODE_KEY="market_unit_mode"` · `MODES=("off","shadow","enforce")` | 상수 | |
| `normalize_mode(raw) -> tuple[str, bool]` | 순수 | 부재·`None` → `("off", True)`. 문자열은 `strip().lower()` 해서 `MODES` 안이면 `(값, True)`. 그 밖(오타·비문자열) → `("off", False)` |
| `classify(closes) -> tuple[Classification \| None, str]` | 순수 | §1.2. reason ∈ `ok`·`rows_short`·`bad_close`. 입력은 오름차순, 마지막 80개만 본다 |
| `Snapshot` | frozen dataclass | `as_of: date` · `preview: bool` · `ok: bool` · `state: str` · `m: float` · `reason: str` · `bar_date` · `expected_head` · `rows: int` · `close` · `sma60` · `sma60_prev` · `above` · `rising` |
| `async compute_snapshot(as_of_date, *, preview) -> Snapshot` | never-raise | §1.1 → §2 → §1.2. 실패는 `ok=False, state="unavailable", m=1.0` |
| `emit_*` | never-raise | §7 마커 서식. 로깅 예외도 삼킨다 |

### 3.2 `StrategyBase` 추가분 (관문 `_apply_budget_limit` 본문은 **byte 무변경**)

| 이름 | 종류 | 내용 |
|---|---|---|
| `_MARKET_UNIT_ATR_KEY: ClassVar[str \| None] = None` | 클래스 상수 | 4전략이 덮는다: kojiro `"atr"` · donchian `"atr"` · BFB `"atr14"` · VCP `"atr14"`(각 전략 터틀 블록이 실제로 읽는 키와 같아야 한다 — AST A09·행위 R24). 값 ∈ `_SIZING_ATR_KEYS` |
| `__init__` | 속성 | `self._market_unit_snaps: dict[date, Snapshot] = {}` · `self._market_unit_caps`(`KstDailyEmitCap` 3개: state·attempt·warn) · `self._market_unit_tally = None` |
| `async _refresh_market_unit(*, as_of_date, preview) -> None` | never-raise | §3.3 |
| `_market_unit_view() -> MarketUnitView(mode, m, state, reason)` | 순수 | §4 |
| `_market_unit_lots(current_price, ticker, m) -> MarketUnitLots` | 순수 | §5.2 |
| `_market_unit_skip_reason(m, lots) -> str \| None` | 순수 | §5.3 |
| `_market_unit_sizing(current_price, ticker) -> MarketUnitLots \| None` | 순수(로그만) | §5.4 — calc 진입점 |
| `_market_unit_blocks_entry(ticker, current_price) -> bool` | 순수(로그만) | §6 — 신호 진입점 |

- 순수 = `await` 0 · `src.db`/`httpx`/`requests`/`asyncio`/`aiohttp` import 0(A-PURE 탐지기와 같은 목록, AST A05). 시계는 `datetime.now(_KST)`(모듈 상수 `_KST`) 한 번. 터틀 계산은 `turtle_sizing.compute_unit_qty_guarded`(순수 모듈) 재사용.
- 3전략(VB·LTV·momentum)은 속성만 물려받고 **한 번도 부르지 않는다**(파일 무접촉 — AST A04).

### 3.3 `_refresh_market_unit` — 4전략 `prepare()` 에서 1회

- 자리: 각 `prepare()` 의 `as_of_date, preview = self._resolve_prepare_as_of(as_of)` **바로 다음 줄**. 어떤 조기 `return`(유니버스 0 등)보다 앞이다(AST A08). kojiro 의 stock_master 0건 재시도 루프보다도 앞이다.
- 동작:
  1. `snap = await market_unit.compute_snapshot(as_of_date, preview=preview)`(never-raise, 바깥 try 로 한 번 더 감싼다).
  2. **보존 규칙** — 같은 `as_of_date` 에 `ok=True` 스냅샷이 이미 있고 새 것이 `ok=False` 면 **옛 것을 둔다**(`kept=1`). 저녁 21:00 미리보기가 만든 좋은 값을 다음 날 07:45 부팅의 일시 DB 실패가 지우지 않게 한다. 새 것이 `ok=True` 면 항상 덮는다.
  3. `self._market_unit_snaps[as_of_date] = snap`(보존 아닐 때). 오늘(KST)보다 과거 키는 지운다 — 사전에는 최대 「오늘 · 다음 거래일」 두 칸만 남는다.
  4. 일일 집계 롤(§8) → `[market_unit_state]`(ok) 또는 `[market_unit_unavailable]`(실패) 마커.
- **미리보기와 PV-1** — 미리보기는 `snaps[다음 거래일]` 한 칸만 쓴다. 오늘 매수가 읽는 `snaps[오늘]` 은 건드리지 않는다. 이 헬퍼는 `_candidates`·`positions`·`_entry_atr`·`_position_setup`·`_position_atr`·`_breakout_high` 어느 것도 읽거나 쓰지 않는다(AST A07) — PV-1 이 지키는 보유 청산 입력과 교집합 0 이다.
- 모드가 `off` 여도 계산한다 — 그래야 `enforce` PUT 이 재시작 없이 즉시 먹는다.
- 비용: 4전략 × 1쿼리(120행) × 준비 횟수. 캐시하지 않는다(4전략 값이 다르면 그 자체가 신호 — `[market_unit_state]` 4줄 대조).

---

## 4. 모드 읽기 — `_market_unit_view()`

```
mode, valid = normalize_mode(params.get("market_unit_mode"))
if not valid: [market_unit_config] WARNING 1회/일 → mode = "off"
if mode == "off": return (off, 1.0, "-", "off")                    # 계산·로그 0, 현행 byte 동일
snap = self._market_unit_snaps.get(datetime.now(_KST).date())
if snap is None:      return (mode, 1.0, "unavailable", "not_computed")   + [market_unit_unavailable] where=view 1회/일
if not snap.ok:       return (mode, 1.0, "unavailable", snap.reason)      # 경보는 refresh 가 이미 냈다
return (mode, snap.m, snap.state, "ok")
```

- 모드는 **매 호출마다** 읽는다 → PUT 즉시 반영(킬스위치).
- `m` 은 반드시 `MULTIPLIERS` 값 중 하나이거나 1.0 이다.

---

## 5. `calc_buy_quantity` 적용 (4전략 공통 모양)

### 5.1 적용 범위

| 전략 | 운영 사이징(2026-09-27) | 축소일 경로 |
|---|---|---|
| kojiro | turtle · `risk_pct` 0.005 · `position_ratio` 0.166 · 슬롯 6 | 터틀 |
| donchian_swing | turtle · 0.01 · 0.2 · 5 | 터틀 |
| vcp_breakout | turtle · 0.01(09-26 전환) | 터틀 |
| bull_flag_breakout | **position_ratio** · 0.25 · 4 (보유 3종목이 나간 뒤 turtle 전환 예정) · 지금 `entry_end=09:04` 라 진입 창 없음 | 비중 → 전환 후 자동으로 터틀 |

경로는 **매 호출** `sizing_mode == "turtle" and ticker is not None` 으로 정한다(기존 분기와 같은 조건) — BFB 전환 PUT 을 코드가 따라간다.

### 5.2 설계 랏 — `_market_unit_lots(current_price, ticker, m)`

```
budget        = int(self.state.total_investment)                # 줄이지 않는다
remaining     = max(0, budget - self._calc_used_funds())        # 줄이지 않는다
remaining_qty = remaining // current_price
sizing_budget(x) = int(budget * x)

turtle 경로:
  atr = float((self._candidates.get(ticker) or {}).get(self._MARKET_UNIT_ATR_KEY) or 0)
  design(x) = compute_unit_qty_guarded(
                  sizing_budget(x), atr, current_price, float(params.get("risk_pct") or 0),
                  remaining_budget=remaining,                                   # 실제 잔여
                  min_vol_pct=float(params.get("min_vol_floor_pct", 1.0)),
                  position_ratio=float(params.get("position_ratio") or 0))      # 명목 상한도 sizing_budget 기준으로 같이 준다
비중 경로:
  design(x) = int(sizing_budget(x) * params["position_ratio"]) // current_price

design_before = design(1.0)
design_after  = 0 if m <= 0 else design(m)
lot_before    = min(design_before, remaining_qty)
lot_after     = min(design_after,  remaining_qty)      # = enforce 시 실제 주문 수량(아래 §9 증명)
fallback      = "pr" (turtle ∧ design_before==0) | "one_share" (ratio ∧ design_before==0) | "-"
```

- **`fraction=m` 으로 구현하지 않는다** — `compute_unit_qty_guarded` 의 명목 상한(`strategy_budget × position_ratio`)이 안 줄어 저ATR 종목에서 랏이 그대로 남는다(G-242-7 이 이미 `fraction=` kwarg 를 금지한다 · 돌연변이 M11).
- **잔여를 m 으로 줄이지 않는다** — 줄이면 자문이 재현하지 않은 「예산 경로」 가 된다(자문 §7.3 ⚠️).
- 부동소수: `budget` 는 정수, m ∈ {0.75, 0.5} 는 이진 정확값이라 `int(budget*m)` 는 결정적이다.
- m = 1 일 때 `design_before` 는 그 전략의 기존 터틀 수량(스탬프 부수효과 제외)과 **항상 같아야 한다**(행위 R24 — ATR 키·읽기 관용 불일치를 잡는다).

### 5.3 스킵 사유 — `_market_unit_skip_reason(m, lots)`

```
if m <= 0:                 "zero_state"
if lots.lot_after > 0:     None            # 줄여서 산다
if lots.remaining_qty < 1: "funds"         # 시장 유닛 탓이 아니다 — 기존 자금 경로로 보낸다
if lots.design_before > 0: "rounds_to_zero"
return                     "no_fallback"   # m=1 이었으면 1주 폴백 또는 터틀→비중 낙하로 샀을 종목
```

### 5.4 calc 앞머리 (4전략 동일, 기존 본문은 **그대로 아래에 둔다**)

```python
def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
    if current_price <= 0:
        return 0
    lots = self._market_unit_sizing(current_price, ticker)      # enforce ∧ m<1 일 때만 값, 그 밖 None
    if lots is not None:
        if lots.lot_after <= 0:
            return 0                                             # 폴백·낙하 없음
        if lots.path == "turtle":
            self._entry_atr[ticker] = lots.atr                   # donchian·BFB·VCP 만. kojiro 는 이 줄 없음
        return self._apply_budget_limit(lots.design_after, current_price, ticker)
    ... 기존 본문 byte 동일 ...
```

- `_market_unit_sizing`: view 를 읽고 `mode ∈ {shadow, enforce}` ∧ `m < 1` 이면 lots·사유를 계산하고 `[market_unit] where=calc` 한 줄(§7)과 집계(§8)를 남긴다. **shadow 면 `None` 을 돌려준다**(수량 불변). 어떤 예외든 `[market_unit_error] where=calc` + `None`(= m=1 경로).
- A-GATE 는 그대로 선다 — 새 return 은 상수 0 과 관문 호출뿐이다.
- 관문에 넘기는 값은 `design_after > 0`(`lot_after > 0` 이면 참) — 관문의 `qty <= 0 → _fallback_one_share` 분기는 축소일에 **도달 불가**다. 그래서 관문 키워드 추가가 필요 없다.
- **터틀 ATR 손절 불변** — 스탬프 값 = 사이징 ATR = m=1 때와 같은 값. 수량만 준다. kojiro 는 `_position_atr` 을 신호 시점에 `info["atr"]` 로 찍으므로(`kojiro.py` `check_buy_signal` BUY 직전) 영향 없다.
- 축소일에 사이즈드 터틀 0 이면 스탬프하지 않는다(기존 `_turtle_buy_quantity` 의 「qty>0 일 때만 스탬프」 와 같다).

### 5.5 축소일 낙하 금지의 범위 (자문과 다른 점)

사용자 결정 「축소일 1주 폴백 금지 · 터틀→비중 낙하 금지」 를 **원인 불문**으로 적용한다. 축소일(enforce ∧ 0<m<1)에 터틀 모드 전략은 ATR 결측·저변동 floor·예외 어느 이유로 터틀이 0 이어도 비중 경로로 떨어지지 않고 스킵한다(`no_fallback`). 이유: 낙하 랏은 `_entry_atr` 미스탬프라 **고정% 손절**을 타고, 명목이 줄인 유닛보다 커질 수 있다 — 약세 날에 손절 규약이 느슨한 큰 랏이 생기는 방향이다. m = 1 인 날의 데이터 결손 낙하는 **현행 그대로**다.

---

## 6. 신호 시점 필터 — `_market_unit_blocks_entry(ticker, current_price)`

```
view = self._market_unit_view()
if view.mode != "enforce" or view.m >= 1.0: return False
lots   = self._market_unit_lots(current_price, ticker, view.m)
reason = self._market_unit_skip_reason(view.m, lots)
if reason in (None, "funds"): return False       # 사거나, 자금 문제면 기존 경로(쿨다운 귀인이 맞다)
[market_unit] where=signal skip=1 reason=<zero_state|rounds_to_zero|no_fallback>  (1회/(ticker)/일) + 집계
return True
예외 → [market_unit_error] where=signal, return False (fail-open)
```

- **부작용 0** — 로그 cap·집계 외에 어떤 상태도 바꾸지 않는다: `_bought_today` 추가 없음 · `buy_signals` 추가 없음 · `_vol_latch` 무장/해제 없음 · `_position_setup`·`_breakout_high`·`_position_atr`·`_position_sectors` 스탬프 없음. 그래서 킬스위치(PUT `off`)가 **다음 틱/다음 폴부터** 그대로 먹는다.
- **자리 = 각 전략의 「매수 확정 블록」 바로 앞, 다른 모든 매수 게이트 뒤.** 첫 문장(`_account_soft_gate_blocked`)은 그대로 첫 문장이다(cycle233·369 가드).

| 전략 | 삽입 자리 | 이유 |
|---|---|---|
| kojiro `check_buy_signal` | `observe_gap(..., "pass", ...)` try 블록 **뒤**, `self._bought_today.add(ticker)` **앞** | `pass` 관측은 cap 이 있고(1회/(ticker,caller,verdict)/일) shadow·enforce 에서 같은 줄이 남아 cycle268 갭 코호트가 흔들리지 않는다. `_position_atr`·`_position_sectors` 스탬프 전에 멈춘다 |
| donchian `check_buy_signal` | `[donchian_extension_skip]` 블록 **뒤**, `self._bought_today.add(ticker)` **앞** | `_breakout_high` 스탬프 전에 멈춘다 |
| BFB `_evaluate_vol_gate` | 추격 상한(`max_breakout_extension_pct`) 거부 블록 **뒤**, `latch_age_sec = 0` **앞** | edge-crossing 기준가 `_prev_price` 는 이미 이번 틱 값으로 갱신된 뒤다 → 끈 뒤 첫 틱의 **거짓 교차가 생기지 않는다**(cycle369 Q7 과 같은 함정). 래치는 무장도 해제도 안 한다 |
| VCP `_evaluate_vol_gate` | BFB 와 같은 자리 | 같음 |

- 경로 커버리지: donchian·kojiro = `scheduler._swing_buy_poll_loop` → `check_buy_signal`(틱 매수 평가는 `risk._TICK_BUY_EVAL_SKIP_STRATEGIES` 로 이미 빠진다). BFB·VCP = `risk.on_tick` → `check_buy_signal`. 두 경로 모두 전략 메서드 안에서 걸리므로 **8영역·scheduler 수정 0**.
- 알려진 비용: m=0 날에도 스윙 폴은 후보마다 `fetch_stock_detail` 을 부른 뒤 신호에서 걸러진다(지금도 갭 스킵 전까지는 같은 비용). 후보 수 × 26회/일 수준이라 받아들인다.

---

## 7. 마커 (전부 로거 `src.engine.market_unit`, 전부 never-raise)

| 마커 | 수준 | 언제 | 서식(필드 순서 고정) |
|---|---|---|---|
| `[market_unit]` | INFO | calc: mode ∈ {shadow, enforce} ∧ m<1 인 매수 시도 · signal: enforce 스킵 | `[market_unit] strategy= state= m= lot_before= lot_after= mode= ticker= path=turtle\|ratio price= fallback=-\|pr\|one_share skip=0\|1 reason=-\|zero_state\|rounds_to_zero\|no_fallback\|funds where=calc\|signal` — 앞 6필드는 과업 지정 순서. cap 1회/(ticker, where)/일/전략 |
| `[market_unit_state]` | INFO | refresh 성공 | `[market_unit_state] strategy= as_of= preview=0\|1 source=069500 bar= close= sma60= sma60_prev= above=0\|1 rising=0\|1 state= m= mode= rows= expected_head=` — cap = (as_of, preview, state, m) 조합당 1회 |
| `[market_unit_unavailable]` | WARNING | refresh 실패 · view 에 오늘 스냅샷 없음 | `[market_unit_unavailable] strategy= as_of= preview= reason= rows= head= expected_head= kept=0\|1 where=refresh\|view → m=1.00` — cap (as_of, reason, where)/일 |
| `[market_unit_daily]` | INFO | 일일 요약(§8) | `[market_unit_daily] strategy= date= state= m= modes= calc_attempts= would_skip= reduced= signal_skips= lot_before_sum= lot_after_sum=` |
| `[market_unit_config]` | WARNING | 모드 값이 오타·비문자열 | `[market_unit_config] strategy= raw=<repr> → off` — 1회/일 |
| `[market_unit_error]` | WARNING | calc·signal 헬퍼 예외(fail-open) | `[market_unit_error] strategy= where=calc\|signal ticker= → m=1.00` — 1회/(where)/일, 트레이스는 DEBUG |

- `lot_before`·`lot_after` 는 §5.2 의 **잔여 클램프까지 한 설계 랏**이다. `lot_after` 는 enforce 시 실제 주문 수량과 같다(§9). `lot_before` 는 `fallback=-` 일 때 현행 주문 수량과 같고, `fallback≠-` 이면 현행은 1주 폴백(또는 비중 낙하)으로 산다는 뜻이다.
- shadow 에서 m=0 이면 calc 줄이 `lot_after=0 skip=1 reason=zero_state where=calc` 로 남는다(수량은 그대로 산다).
- `system_logs` 적재는 하지 않는다(기존 WARNING 핸들러가 있으면 그대로 탄다 — 추가 `write_log` 0, G-242-9 류 이중 INSERT 금지).
- 미리보기 P3(「미리보기는 관측 전용 부수 로그로 일일 cap 을 소비하지 않는다」) 와 충돌하지 않는다 — 미리보기가 내는 것은 `[market_unit_state] preview=1`(그 미리보기의 산출물)과 끝난 날의 `[market_unit_daily]` 뿐이고, state cap 키에 `preview` 가 들어 있어 라이브 줄의 cap 을 먹지 않는다. 매수 시도 줄(`[market_unit]`)은 미리보기에서 나올 일이 없다.

---

## 8. 일일 요약 `[market_unit_daily]`

- 전략 객체의 메모리 집계 `self._market_unit_tally = {date, state, m, modes:set, calc_attempts, would_skip, reduced, signal_skips, lot_before_sum, lot_after_sum}`.
- 올림 규칙(하나의 헬퍼 `_market_unit_tally_roll(day)`):
  - `_refresh_market_unit(as_of_date)` 에서 `tally.date < as_of_date` 면 그 날 줄을 내보내고 `as_of_date` 로 새로 연다.
  - 매수 시도·스킵 이벤트에서 `tally.date < 오늘`(더 늦은 날짜)이면 같은 방식으로 내보내고 연다.
- 결과: 거래일마다 전략당 **정확히 1줄**이 보통 **그날 21:00 저녁 미리보기**에서 나온다(모든 매수가 끝난 뒤). 미리보기가 없으면 다음 날 07:45 부팅이 낸다.
- 세는 것: `calc_attempts` = calc 줄 수(cap 무관 전수) · `would_skip` = 그중 `lot_after==0` · `reduced` = 그중 `0<lot_after<lot_before` · `signal_skips` = signal 스킵 **종목 수**(처음 1회만) · 합계 둘 = calc 시도의 `lot_before`·`lot_after` 합.
- 한계: 메모리 집계라 재시작하면 그날 앞부분이 빠진다. 정본은 `[market_unit]` 개별 줄이다.
- 21:30 일일 로그 분석(`log_analysis_engine`) 편입은 이번 범위 밖(§12).

---

## 9. 기존 캡 · 불변식과의 관계

| 항목 | 관계 | 근거 |
|---|---|---|
| `state.total_investment` | **무접촉.** 전략 코드는 대입하지 않는다(AST A06) | 일일 손실 분모 `strategy_base.is_daily_loss_exceeded` · 정산 기준선 · 비중 하한선 검증 · kojiro `_is_open_risk_capped` 분모 전부 그대로 |
| `position_ratio × max_positions ≤ 1.0` | 무접촉. m ≤ 1 이라 랏만 준다. 슬롯 수 그대로(m=0 이면 슬롯이 빈 채로 남는다) | C-DEFAULT 가드 그대로 |
| ② 잔여 캡 | 잔여는 줄이지 않은 예산 기준 — 관문의 `min(qty, 잔여//가격)` 그대로 | §5.2 |
| K축 `max_lot_units`(2.0) | 줄이지 않은 예산으로 계산. 축소 랏은 **항상 캡 아래**: `design_after ≤ unit(예산) ≤ floor(K×예산×risk÷ATR)` (K ≥ 1 클램프) → 캡 no-op | 캡에 m 을 곱하지 않는다(재현이 시험하지 않은 결합) |
| ρ축 `max_lot_ratio_mult`(2.5) | 축소 랏 명목 ≤ `예산×m×position_ratio` ≤ `2.5×position_ratio×예산` → no-op. 축소일엔 폴백 랏이 없으니 ρ축의 유일한 실효 대상도 없다 | |
| kojiro `max_open_risk_pct`(4.5%) | 분모 그대로. 줄인 랏은 위험을 덜 써 캡이 덜 걸린다 | |
| 관문 순서 계약 | **본문 byte 무변경** — 폴백·잔여 클램프 → K축 → `[oversized_fallback]` → ρ축 | §5.4 |
| `cash_usage_ratio` · 매크로 레짐 | 무접촉. 결합 규칙(자문 §6.3 (나))은 `auto_regime_adjust` 를 켤 때 정한다 | |
| 청산(손절·트레일링·익일·15:20·상한가) | 무접촉. `check_exit_signal`·`get_effective_stop_price`·`_position_stop_price`·`_effective_setup`·`_effective_atr` 는 시장 유닛을 읽지 않는다(AST A07) | 보유분은 줄이지 않는다 |

`lot_after` = 실제 주문 수량 증명: 관문에 `design_after>0` 이 들어가면 `min(design_after, 잔여//가격)` = `lot_after`, 이어서 K축·ρ축은 위 표대로 no-op 이다(ATR 결측·모호로 K축이 fail-open 하는 경우도 수량을 늘리지 않는다).

---

## 10. 파일 · 무접촉 · 재핀

### 10.1 바뀌는 파일

| 파일 | 내용 |
|---|---|
| **새** `src/engine/market_unit.py` | §3.1 |
| `src/engine/strategy_base.py` | §3.2 헬퍼 · `__init__` 속성 · `ClassVar`. `_apply_budget_limit` 와 그 하위 헬퍼 본문 무변경 |
| `src/engine/strategies/kojiro.py` · `donchian_swing.py` · `bull_flag_breakout.py` · `vcp_breakout.py` | `DEFAULT_PARAMS["market_unit_mode"] = "shadow"`(주석: cycle382 · 부재=off · `PARAM_RANGES`/`INT_PARAMS` 편입 금지 · 킬스위치=PUT) · `_MARKET_UNIT_ATR_KEY` · `prepare()` 1줄 · `calc_buy_quantity` 앞머리 · 신호 필터 1곳 |
| `src/engine/param_catalog.py` | `market_unit_mode` 1행: `type="enum"`, choices `off`(끄기 — 현행)·`shadow`(기록만)·`enforce`(설계 랏 축소), `risk="identity"`, `auto_tunable=False`, `applies_to=_TURTLE4`, `range_src="enum"`, help 에 「부재·오타 = off」·「m=0 날은 신규 진입 없음」. 키 수 103→104 · identity 16→17 · `CATALOG_VERSION` → `"cycle382.1"` |
| `frontend/src/test/fixtures/paramSchema.fixture.ts` · `e2e/fixtures/param-schema.fixture.ts` | 카탈로그 재생성분(cycle352 선례) — 프론트 스위트 실행 |
| `src/engine/market_regime.py` | **주석만** — E-1 블록의 「block_reason 통합 … E-2(2주 관찰 후) 인계」 를 「E-2 는 폐기(cycle382 — 장세 축소는 시장 유닛이 전략 사이징에서 한다)」 로. 핀이 걸려 있으면 값만 재핀 |

### 10.2 무접촉 (확인 대상)

8영역(`risk`·`order_engine`·`session`·`scanner`·`strategy_registry`·`api/order`·`realtime/**`·`auth/**`) · `scheduler.py`(3,777줄 그대로) · `boot_manager.py` · `turtle_sizing.py` · `recommendation_engine.py`(`PARAM_RANGES`·`INT_PARAMS` sha 핀 그대로) · VB·LTV·momentum 3파일(C31 핀이 **바뀌지 않아야** 한다 — 음성 대조).

### 10.3 예상 재핀 (값만 · 주석 `🔁 cycle382 재핀 — 시장 유닛(사용자 결정 09-27)`)

- `tests/unit/ast/test_cycle278_ast_catalog_guards.py` — `_DEFAULT_PARAMS_SHA` 4개(kojiro·donchian·BFB·VCP) · `_BASE_SHA` 5개(`strategy_base.py` + 4전략)
- 4전략 `prepare`·`check_buy_signal`·`_evaluate_vol_gate`·`calc_buy_quantity` 소스 세그먼트를 핀한 가드(cycle364 PV-1 · cycle228 · cycle355 계열) — 전체 스위트가 가리키는 것만
- `tests/unit/engine/test_cycle278_param_catalog.py` 키 수 103→104 서술 · `tests/contract/test_routes_strategies.py`(cycle352 선례)
- 재핀 전 반드시 diff 가 이 명세의 자리뿐인지 눈으로 본다(핀을 먼저 재산출하지 않는다).

### 10.4 배포

`src/` 변경 → **full**(backend 재시작). 창 = 주말 종일 · 15:30~16:00 · 21:35~익일 07:45. 첫 shadow 거래일 = 09-28(월).

---

## 11. 테스트 목록 (Red)

파일 제안: `tests/unit/engine/test_cycle382_market_unit_leaf.py`(R01~R16) · `tests/unit/engine/strategies/test_cycle382_market_unit_sizing.py`(R17~R31) · `tests/unit/engine/strategies/test_cycle382_market_unit_signal.py`(R32~R40) · `tests/unit/engine/test_cycle382_market_unit_refresh.py`(R41~R48) · `tests/unit/ast/test_cycle382_ast_market_unit.py`(A01~A12) · 선택 `tests/integration/test_cycle382_market_unit_pg.py`(P01).
공통: 시계는 freezegun 또는 모듈 시계 주입(cycle369 `_cycle369_support.Clock` 패턴). INFO 마커는 `caplog.set_level(logging.INFO, logger="src.engine.market_unit")` + 접두사로, WARNING 은 WARNING 이상 + 접두사로 단언한다. seam = `src.db.stock_master_daily.get_recent_daily` · `src.engine.trading_calendar.previous_trading_day` monkeypatch.

### 11.1 판정 고정 시계열 (합으로 미리 검산함)

| id | 종가(오름차순) | 기대 | 잡는 돌연변이 |
|---|---|---|---|
| F1 | `[10000 + 10*i for i in range(80)]` | up_rising · 1.0 | 배수표 |
| F2 | `[12000 - 10*i for i in range(79)] + [12500]` | up_falling · 0.75 | 배수표 |
| F3 | `[10000 + 10*i for i in range(79)] + [9000]` | down_rising · 0.5 | 배수표 |
| F4 | `list(reversed(F1))` | down_falling · 0.0 | 배수표 |
| T2 | `[9000]*20 + [10000]*60` | 종가=SMA60 동률 → down_rising · 0.5 | `>`→`>=`(above) 면 1.0 |
| T3 | `[10000]*20 + [9000]*40 + [10000]*20` | 기울기 동률 → up_falling · 0.75 | `>`→`>=`(rising) 면 1.0 |
| TF | `[10000]*80` | 이중 동률 → down_falling · 0.0 | |
| D1 | `[50000] + [10000]*60 + [10010]*20` (81개) | up_rising · 1.0 | 기울기 창 한 칸 과거 이동 · lookback 21 → 0.75 |
| D3 | `[10000]*60 + [20000] + [9990]*19` | down_rising · 0.5 | lookback 19 → 0.0 |
| D2 | `[10000]*20 + [10100] + [10000]*59 + [10001]` (81개) | up_falling · 0.75 | MA 창 61 → 0.5 |
| D4 | `[10000]*20 + [20000] + [10000]*58 + [10100]` | down_rising · 0.5 | MA 창 59 → 0.75 |

### 11.2 목록

**leaf (순수·로더)**
- R01~R04 F1~F4 → 네 상태·배수(각 1건, 과업 「each state」).
- R05 T2 종가 동률 → `above=False`. R06 T3 기울기 동률 → `rising=False`. R07 TF → 0.0.
- R08 D1·D3 — 기울기 창 정렬(lookback 20, `w[0:60]` 대 `w[20:80]`).
- R09 D2·D4 — MA 창 60.
- R10 81개 이상 입력은 마지막 80개만 본다(D1 의 `50000` 이 결과를 안 바꾼다).
- R11 79행 → `rows_short` · m=1. 80행 → ok(경계).
- R12 창 안 종가 `0`·음수·`None`·`nan`·`"abc"` 각각 → `bad_close` · m=1. 창 **밖** 81번째 행이 `None` 이면 ok.
- R13 `normalize_mode` — 부재/`None`→(off,True) · `" Shadow "`→(shadow,True) · `"ENFORCE"`→(enforce,True) · `"on"`·`1`·`True`→(off,False).
- R14 **라이브 as_of** — as_of=09-28, 행에 `bas_dd=09-28` 인 극단 값 봉(포함되면 상태가 뒤집히도록)을 섞는다 → 그 봉은 제외, `bar_date=09-23`, 달력 대역 `previous_trading_day(09-28)=09-23` → ok.
- R15 **미리보기 as_of** — as_of=09-29(화), 시계 09-28 21:05, 행 머리 `09-28` → `bar_date=09-28`(as_of−1 봉) · `expected_head=09-28` · ok · `preview=True`.
- R16 **stale 머리** — as_of=09-28, expected 09-23, 머리 09-22 → `stale_head` · m=1 · WARNING `[market_unit_unavailable] … reason=stale_head`. 달력 `None` 이면 머리 09-23(5일) → ok, 머리 09-17(11일) → stale. seam 이 예외를 던지면 `exception` · m=1 · **예외가 밖으로 나오지 않는다**. seam 인자 = `("069500", ≥80)`. `STALE_FALLBACK_MAX_CALENDAR_DAYS == market_regime.ETF_STALE_MAX_CALENDAR_DAYS`.

**calc (4전략 파라미터화 — kojiro·donchian·VCP 는 turtle, BFB 는 position_ratio 와 turtle 둘 다)**
- R17 **off·shadow 는 현행 byte 동일** — 가격·ATR·예산·사용액 격자에서 `mode=off` 결과 == `mode=shadow` 결과 == 명세 이전 알고리즘(시험 안에 옮겨 적은 오라클) 결과, m ∈ {1, .75, .5, 0} 모두.
- R18 **shadow 기록** — kojiro turtle, 예산 2,000,000 · risk 0.005 · ATR 1,000 · 가격 50,000 · ratio 0.166 · 사용 0: 반환 **6**(현행), `[market_unit] … m=0.75 lot_before=6 lot_after=4 mode=shadow … where=calc`. m=0.5 → `lot_after=3`.
- R19 **enforce 터틀** — 같은 입력 m=0.75 → **4**, m=0.5 → **3**, m=1 → 6.
- R20 **잔여는 줄이지 않는다** — donchian turtle, 예산 1,000,000 · 사용 500,000 · 가격 10,000 · ATR 500 · risk 0.01 · ratio 0.2, m=0.5 → **10**(잔여를 줄이면 0).
- R21 **명목 상한도 m 으로 준다** — 예산 1,000,000 · 가격 10,000 · ATR 150 · risk 0.01 · ratio 0.2: m=1 → 20, m=0.5 → **10**(`fraction=` 식이면 20).
- R22 **enforce 비중 경로(BFB)** — 예산 1,000,000 · ratio 0.25 · 가격 30,000: m=1 → 8, 0.75 → 6, 0.5 → 4.
- R23 **1주 폴백 차단** — BFB 비중, 가격 300,000(설계 0주): m=1 → **1**(현행 폴백, ρ컷 625,000 ≥ 가격), m=0.5 enforce → **0**, 마커 `fallback=one_share`. 가격 150,000: m=1 → 1, m=0.5 → 0(`rounds_to_zero`).
- R24 **ATR 키 동치** — 4전략 각각, m=1 `design_before` == 기존 터틀 수량(`_turtle_buy_quantity` 또는 kojiro 인라인 블록 재현)을 격자로 대조.
- R25 **터틀→비중 낙하 금지** — donchian turtle, `_candidates[t]` 에 ATR 없음: m=1 → 비중 20주(현행 낙하), enforce m=0.5 → **0** · `_entry_atr` 에 `t` 없음. 저변동 floor(ATR/가격 < 1%) 도 같은 결과.
- R26 **스탬프 불변** — donchian·BFB(turtle)·VCP, enforce m=0.5 매수 → `_entry_atr[t]` == 사이징 ATR(m=1 때와 같은 값). 그 포지션의 `check_exit_signal`·`get_effective_stop_price` 가 같은 매수가 · 같은 ATR 의 m=1 포지션과 **같은 손절선**을 낸다.
- R27 **예산 불변** — calc 전후 `state.total_investment` 같음 · `is_daily_loss_exceeded` 분모 · kojiro `_is_open_risk_capped` 한도 같음.
- R28 **K·ρ 캡 무접촉** — 축소 랏에서 `[fallback_notional_capped]`·`[ratio_notional_blocked]`·`[fallback_cap_skipped]` 0건 · 최종 수량 == `lot_after`.
- R29 **enforce m=0 이 calc 에 닿으면**(방어선) → 0.
- R30 **스냅샷 없음·실패 = off 와 같다** — enforce · 오늘 스냅샷 없음 → 반환이 off 와 같고 `[market_unit_unavailable] … where=view` WARNING 1회(두 번째 호출엔 없음). mode=off 면 WARNING 0.
- R31 **fail-open** — `_market_unit_lots` 가 예외를 던지게 하면 반환 == off, `[market_unit_error] where=calc` 1회.

**신호 (4전략)**
- R32 **m=0 필터** — enforce, 다른 게이트는 모두 통과하는 입력(kojiro·donchian 09:05~09:30 · BFB·VCP 돌파+거래량 충족) → `Signal.NONE` · `[market_unit] … skip=1 reason=zero_state where=signal` **1회**(같은 종목 두 번째 평가엔 줄 없음). `_bought_today`·`buy_signals`·`_position_setup`·`_breakout_high`·`_position_atr`·`_position_sectors`·`_vol_latch` 변화 0.
- R33 **투자금 부족으로 기록되지 않는다** — cycle369 `test_j0_*`(틱)·`test_j13_*`(스윙 폴) 경로를 그대로 써서 enforce m=0 종목을 흘린다 → `execute_buy`·`calc_buy_quantity`·`get_buyable` 호출 0 · `state.is_low_funds_blocked(t, now)` False · `매수 수량 0` WARNING 0.
- R34 **양성 대조** — 같은 입력 m=1(enforce) → `Signal.BUY`, 기존 부수효과 그대로.
- R35 **½ 날 줄여서 0주** — BFB 비중 가격 150,000, m=0.5 → NONE `reason=rounds_to_zero`. 가격 300,000 → `reason=no_fallback`. donchian turtle ATR 결측, m=0.5 → `no_fallback`.
- R36 **자금 부족은 거르지 않는다** — 잔여 < 가격, m=0.5 → 신호는 현행대로(BUY), 줄 없음. (m=0 이면 잔여와 무관하게 `zero_state`.)
- R37 **shadow 는 거르지 않는다** — shadow m=0 → 신호 BUY(현행), signal 줄 0.
- R38 **킬스위치 즉시** — enforce m=0 → NONE, 같은 프로세스에서 `config.params["market_unit_mode"]="off"`(재준비 없음) → 다음 평가 BUY.
- R39 **기준가 얼음 없음(BFB·VCP)** — enforce m=0 에서 교차 틱이 걸러진 뒤 가격이 돌파선 위에 머문 채 모드를 `off` 로 바꾸면, 다음 틱은 **새 교차가 아니다**(`_prev_price` 가 걸러진 틱 값으로 이미 갱신돼 있다) → NONE. 가격이 돌파선 아래로 갔다 다시 넘으면 BUY(BFB 는 `breakout_retention_minutes=0` 으로 두거나 시계를 retention 만큼 넘긴다). 대조: 걸러질 때 이미 **래치가 무장돼 있던** 종목은 래치가 그대로 남으므로, 모드를 끈 뒤 돌파선 위 첫 틱에서 래치 재평가로 BUY 한다(기준가와 무관한 기존 경로).
- R40 **첫 문장 게이트 순서 보존** — `_account_soft_gate_blocked` 가 True 면 시장 유닛 헬퍼가 불리지 않는다(스파이).

**refresh · 미리보기 · 요약**
- R41 **4전략 prepare 가 1회 부른다** — 유니버스 0종목으로 조기 return 하는 경우에도 스냅샷이 생긴다. 4전략이 같은 seam 에서 같은 state·m 을 얻는다.
- R42 **모드 off 여도 계산** — `off` 로 prepare → 스냅샷 있음 · `[market_unit_state] … mode=off`. 그 뒤 `enforce` 로 바꾸면 재준비 없이 즉시 m 적용.
- R43 **미리보기는 오늘을 안 바꾼다** — 오늘 스냅샷 m=0.5 인 상태에서 `prepare(as_of=다음 거래일)`(seam 이 다른 상태를 내도록) → 오늘 view 는 계속 0.5 · 사전에 다음 거래일 키가 생긴다. 시계를 다음 거래일 09:05 로 옮기면 view 가 미리보기 값을 쓴다. 보유 종목 청산 입력(PV-1 집합)은 전후 동일.
- R44 **보존 규칙** — 같은 as_of 에 ok 스냅샷이 있고 새 계산이 `rows_short` → 옛 값 유지 · WARNING `kept=1`. 다른 as_of 의 실패는 m=1 로 기록.
- R45 **never-raise** — `compute_snapshot` 자체를 예외 대역으로 바꿔도 prepare 는 끝까지 돌고 후보가 채워진다 · m=1.
- R46 **일일 요약** — 오늘 calc 3건(축소 2·0주 1) + signal 스킵 2종목 뒤 `prepare(as_of=다음 거래일)` → `[market_unit_daily] … date=<오늘> calc_attempts=3 would_skip=1 reduced=2 signal_skips=2` **정확히 1줄**. 같은 as_of 로 다시 prepare 해도 두 번째 줄 없음.
- R47 **`[market_unit_state]` 손계산 일치** — F2 에 날짜를 붙여 넣고 `close`·`sma60`·`sma60_prev`·`above`·`rising`·`state`·`m` 필드가 §1.2 계산과 같다. 같은 as_of 로 재준비를 반복해도 줄은 1개.
- R48 **DB 덮기 경로** — `strategy_config.params` 에 키가 없는 DB 행으로 `_load_strategy_config` 를 돌리면 모드는 기본 `shadow` 로 남는다. DB 에 `"enforce"` 가 있으면 enforce.

**라우트 · 자문 경로**
- R49 `PUT /api/strategies/kojiro/params {"params":{"market_unit_mode":"enforce"}}` 성공 · `"on"` 은 검증 실패(저장 0). VB 에 이 키를 PUT 하면 미지 키로 거부.
- R50 `_validate_recommendations` 가 `market_unit_mode` 추천을 버린다(적용 경로 편입 0).

**선택 — 실제 Postgres**
- P01 `pg_harness` 로 `069500` 90행을 넣고 `compute_snapshot` → 손계산과 같은 state · `bas_dd` 타입(`date`) 처리 확인.

### 11.3 AST 가드

- A01 `market_unit.py` — `classify`·`normalize_mode` 에 `await` 0 · 최상위 import 가 표준 라이브러리뿐 · 8영역·`scheduler`·`boot_manager`·`market_regime` import 0.
- A02 배수 네 값·`60`·`20` 정의가 `market_unit.py` 한 곳뿐(전략 4파일·`strategy_base.py` 에 `0.75`/`MA_WINDOW` 류 재정의 0).
- A03 `market_unit_mode` ∉ `PARAM_RANGES`·`INT_PARAMS`(런타임 dict) + `recommendation_engine.py` 소스 문자열 스캔(G-245-1 동형, 탐지기 자기시험 포함).
- A04 VB·LTV·momentum 파일에 `market_unit` 토큰 0 · 8영역 + `scheduler.py` 에 `market_unit` 토큰 0.
- A05 새 동기 헬퍼 6개(`_market_unit_view`·`_market_unit_lots`·`_market_unit_skip_reason`·`_market_unit_sizing`·`_market_unit_blocks_entry`·`_market_unit_tally_roll`)에 `await` 0 · 금지 import 0(A-PURE 탐지기 재사용).
- A06 4전략 파일에 `state.total_investment` 대입(`Assign`/`AugAssign` 대상) 0.
- A07 청산 계열(`check_exit_signal`·`get_effective_stop_price`·`_position_stop_price`·`_effective_setup`·`_effective_atr`·`check_force_clear`)이 `_market_unit` 을 참조하지 않는다 · `_refresh_market_unit` 본문이 `_candidates`·`positions`·`_entry_atr`·`_position_setup`·`_position_atr`·`_breakout_high` 를 참조하지 않는다.
- A08 4전략 `prepare` 가 `_refresh_market_unit` 를 **정확히 1회** 부르고, 그 줄이 `_resolve_prepare_as_of` 줄 뒤 · prepare 본문의 첫 `return` 앞이다(kojiro `_fetch_one` 같은 **중첩 함수 안의 return 은 제외**하고 센다).
- A09 4전략 `_MARKET_UNIT_ATR_KEY` ∈ `_SIZING_ATR_KEYS` 이고 그 전략 터틀 블록이 `_candidates`/`info` 에서 읽는 키 집합과 같다(G-242-8 탐지기 재사용).
- A10 4전략 `calc_buy_quantity` 가 `_market_unit_sizing` 을 정확히 1회, 첫 문장 뒤 기존 사이징 코드보다 앞에서 부른다 · 기존 A-GATE(`test_budget_limit_ast.py`)·G-242-7(`fraction=` 금지) 그대로 초록.
- A11 4전략 신호 필터 호출이 정확히 1회이고 §6 표의 자리(kojiro·donchian 은 `_bought_today.add` 앞 · BFB·VCP 는 `_evaluate_vol_gate` 안 `_vol_latch.pop` 앞 · 모두 `_account_soft_gate_blocked` 뒤)에 있다.
- A12 `_apply_budget_limit` 소스 세그먼트 sha **불변**(이 사이클은 관문을 안 건드린다) · 4전략 `DEFAULT_PARAMS["market_unit_mode"] == "shadow"` · 3전략엔 키 없음 · 카탈로그 `market_unit_mode` choices == {off, shadow, enforce} · identity · `auto_tunable=False` · `applies_to == _TURTLE4`.

---

## 12. 돌연변이 목록 (tester — 각 항목을 잡는 테스트)

| # | 돌연변이 | 잡는 곳 |
|---|---|---|
| M01 | `above` 의 `>` → `>=` | R05 |
| M02 | `rising` 의 `>` → `>=` | R06 |
| M03 | 기울기 비교 창 한 칸 과거(`w[-81:-21]`) 또는 lookback 21 | R08(D1) |
| M04 | lookback 19 | R08(D3) |
| M05 | MA 창 59 또는 61 | R09 |
| M06 | 배수표 ¾ ↔ ½ 뒤바꿈 | R02·R03 |
| M07 | 실패 시 m=0(fail-closed) | R11·R16·R30 |
| M08 | `bas_dd < as_of` → `<=`(오늘 봉 포함) | R14 |
| M09 | 미리보기에서 머리 봉 하나 버림(as_of−2) | R15 |
| M10 | stale 검사 삭제 | R16 |
| M11 | `sizing_budget` 대신 `fraction=m` | R21 · G-242-7 |
| M12 | 잔여도 `int(예산×m)` 기준으로 계산 | R20 |
| M13 | `lot_after <= 0 → return 0` 삭제(관문 폴백 도달) | R23 |
| M14 | 축소일 터틀 0 이면 비중 경로로 낙하 | R25 |
| M15 | 축소 매수에 스탬프 누락 또는 `atr×m` 스탬프 | R26 |
| M16 | 신호 필터 삭제 | R32·R33 |
| M17 | shadow 에서도 신호 필터 적용 | R37 |
| M18 | 신호 필터를 `_bought_today.add` 뒤(또는 BFB·VCP 에서 `_prev_price` 갱신 앞)로 이동 | R38·R39·A11 |
| M19 | 모드 부재 기본값을 `shadow`/`enforce` 로 | R13·R48 |
| M20 | 보존 규칙 삭제(실패가 ok 를 덮음) | R44 |
| M21 | view 의 오늘 날짜 검사 삭제(가장 최근 스냅샷 사용) | R43 |
| M22 | K·ρ 캡 산출에 축소 예산을 넘김 | R28 |
| M23 | `[market_unit]` cap 삭제 | R32(1회 단언) |
| M24 | `funds` 사유도 신호에서 거름 | R36 |
| M25 | refresh 를 조기 return 뒤로 이동 | R41·A08 |
| M26 | shadow 가 `lots` 를 돌려줘 수량이 바뀜 | R17 |

---

## 13. 롤아웃 · 롤백

**단계**
1. 장외 창 full 배포(기본 `shadow`). 09-28(월)부터 1주(5거래일) shadow.
2. tester 확인 항목(매일): 전략 4개 `[market_unit_state]` 가 같은 state·m 이고 손계산(§1.4 쿼리)과 같다 · `[market_unit_unavailable]` 0 · `[market_unit] mode=shadow` 의 `lot_after` 가 `lot_before × m` 근처(정수 절삭)이고 `skip=1` 이 설계대로(donchian·VCP 의 ½ 날 스킵이 많은 것은 **예상**) · `[market_unit_daily]` 가 전략당 하루 1줄 · 예상 밖 스킵 0. BFB 는 `entry_end=09:04` 라 줄이 없는 것이 정상이다(재개 뒤부터 보인다).
3. 사용자 승인 뒤 4전략 각각 `PUT /api/strategies/{id}/params {"params":{"market_unit_mode":"enforce"}}`. 반영 즉시. 장외 창에 한다.
4. 분기 복기(자문 §11) — 매수일 state 별 실현 R.

**롤백(어느 것도 보유 포지션을 건드리지 않는다 — 시장 유닛은 신규 진입만 본다)**
| 수단 | 반영 | 언제 |
|---|---|---|
| `PUT /api/strategies/{id}/params {"params":{"market_unit_mode":"off"}}` ×4 | **즉시**(다음 틱·다음 폴) | 장중 포함 언제나. 1순위 |
| 같은 PUT 으로 `"shadow"` | 즉시 | 집행만 멈추고 기록은 유지 |
| `strategy_config` SQL UPDATE | 다음 재시작에서만 | 쓰지 않는다(cycle232 D6) |
| 코드 revert | full 배포 | 장외 창만. DB 에 PUT 으로 남은 키는 읽는 코드가 없어 무해 |

🔴 **전략 끄기(`enabled`/`weight=0`)로 되돌리지 않는다** — 보유분 손절이 멈춘다(루트 금기).

---

## 14. 문서 동기화 (docs 단계 · `/sync-docs` 목록에 올릴 것)

| 문서 | 바꿀 것 |
|---|---|
| 루트 `CLAUDE.md` 「외부 통합」 매크로 레짐 줄(:163) | 「**매크로** 레짐은 관찰 지표다 — 매수를 차단·축소하지 않는다」 로 범위를 좁히고, 「장세에 따른 신규 진입 축소는 레짐이 아니라 **시장 유닛**(자금 관리 절)」 한 문장 |
| 루트 `CLAUDE.md` 「자금 관리」 | 새 항목 「시장 유닛(cycle382)」: 4전략 · 069500 60일선 계단 1/¾/½/0 · 설계 랏만 · 축소일 폴백·낙하 없음 · m=0 신호 필터 · 결측=1 · `market_unit_mode` off\|shadow\|enforce(부재=off, `PARAM_RANGES` 금지, 킬스위치 PUT 즉시) · `total_investment` 무접촉. 「매수 수량은 전략 잔여 자금 기준」 항목에 「calc 앞머리의 시장 유닛 분기는 관문 앞에서 0 을 돌려줄 뿐 관문 순서 계약은 그대로」 한 줄 |
| `src/engine/CLAUDE.md` | 새 leaf `market_unit.py` 항목 · `strategy_base` 헬퍼 · 레짐 절(:614 · :927)의 「레짐 게이트 복원 금지」 에 「시장 유닛은 레짐 게이트가 아니다 — 전략 사이징」 · `market_regime` 절 E-1 에 **E-2 폐기(cycle382)** |
| `src/engine/strategies/CLAUDE.md` | 4전략 행에 `market_unit_mode` · 신호 필터 자리 · 축소일 규칙 |
| `_workspace/00_leader_trading_rules.md` | 4전략 파라미터 표에 `market_unit_mode="shadow"` · §8-3 「레짐은 매수를 차단하거나 축소하지 않는다 … `cash_usage_ratio` 하나로만」 을 매크로 레짐 한정으로 · 새 「시장 유닛」 절(규칙·배수표·킬스위치) |
| `docs/architecture.md` 13.3 · 8.x 매수 흐름 | 매크로 레짐 = 관찰, 시장 유닛 = 전략 사이징 |
| `docs/trading_base/점진적배팅과장세판단.md` :82 · §5 | 「우리 시스템에는 이 규칙이 없다」 → 시장 유닛(cycle382) 링크. 「지금 랏으로는 만들 수 없다」 는 **종목 유닛** 한정으로 |
| `docs/history/*.history.md` | 바뀐 정본마다 append(경위 = 자문 cycle376 · 사용자 결정 09-27) · `docs/HARNESS_CHANGELOG.md` cycle382 |

---

## 15. 반례 · 한계

- **증거의 무게는 약세장 하나**(자문 §3.1 — A 구간만 유의). V자 반등 해(2025)에는 5~11%p 덜 번다. 시장 유닛은 예측이 아니라 후행 대응이다.
- **운영 표본은 반대 방향이었다**(자문 §4.5, 54건 — 판정력 없음). 분기 복기의 첫 항목이다.
- **0 상태는 최장 95영업일** 이어질 수 있다 — 네 전략이 몇 달 새로 사지 않는다. `[market_unit] reason=zero_state` 와 `[market_unit_daily]` 가 없으면 「왜 안 사지」 를 결함으로 오진한다(BFB `entry_end` 선례).
- **급락 하루는 막지 못한다** — 보유분을 건드리지 않는다.
- **신호원 차이** — 운영은 KODEX 200, 재현은 코스피 지수(판정 94.8% 일치). ETF 분배락(연 1~2%, 주로 4월)은 수정주가에 반영되지 않아 60일선 근처에서 하루 판정이 흔들릴 수 있다(추정).
- **축소일 데이터 결손 낙하 금지**(§5.5)로, 축소일에는 ATR 결측 종목을 사지 않는다. 사용자 결정 원문을 따른 것이며, m=1 날의 행위는 그대로다.
- **엄격 신선도**(§2) — 20:30 적재가 실패한 다음 날은 m=1 이다.
- **069500 적재가 시총·거래대금 자격에 기대고 있다**(§2) — 강제 포함은 8영역이라 후속.

## 16. 후속 (이번 범위 밖)

- 21:30 일일 로그 분석에 `[market_unit]` 스킵을 「투자금 부족」 과 따로 세는 칸(자문 §7.3(5)).
- `069500` 일봉 적재 강제 포함(`scanner.py`, 8영역 — 승인 필요).
- 대시보드에 오늘 state·m 표시(새 칸은 값이 찍히는지까지 실측 — 메모리 규약).
- 매크로 자동 조정과의 결합 규칙(자문 §6.3 (나)) — `auto_regime_adjust` 를 켤 때.
