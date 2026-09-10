# cycle272 — VB·LTV `main` 목표가 기준가를 KRX REST 로 교체 (설계 확정 자문)

- 작성 2026-09-10 (목) 장 종료 후 · domain-expert · **읽기 전용** (코드·DB·설정·git 무변경)
- 근거 입력 = `_workspace/analysis/2026-09-10_cycle272_U1_open_price_path.md`(경로 전수) ·
  `..._U2_rest_capacity.md`(용량 실측) · `..._U3_guards_and_rollback.md`(가드·롤백) +
  `_workspace/analysis/2026-09-10_cycle265_direction_report.md` ·
  `_workspace/analysis/2026-09-10_open_scope_3way_readout.md` ·
  `_workspace/consult/2026-09-07_open_price_scope_filter.md`
- 기준 HEAD `a10191b` · `wc -l src/engine/scheduler.py` = **3,898**

> **표기** — **[코드]** 소스 직접 확인 / **[실측]** 운영 로그·덤프 관측 / **[산출]** 실측 계산 /
> **[추론]** 그 밖. **[추론] 위에 배포 결정을 세우지 마라.**
>
> **범위 계약 (사용자 D1 §범위, 그대로 지킨다)** — 전략 비중 · `position_ratio` · `max_positions` ·
> 랏 캡(K·K_ρ) · `open_entry_hold_secs`(90초) · LTV 청산 규약, 이 **여섯은 무접촉**이다.
> 이 문서의 어떤 항목도 그 값을 바꾸지 않는다. 90초 보류는 **바꾸는 대상이 아니라 예산으로만** 쓴다.
>
> **이 문서는 D1 을 그대로 구현하는 설계 하나를 확정한다.** 대안·이견은 §9(열린 질문)에만 적었고
> 본문에서 값을 바꾸지 않았다.

---

## 1. 결정 요약 — 한 장

| # | 결정 | 내용 |
|---|---|---|
| **D-1** | **`main` 기준가 = KRX REST `stck_oprc`(`J`) 단일 출처** | 통합 채널 WS `[7]` 은 `board=="main"` 목표가에 **쓰지 않는다**. 판별자 `[24] OPRC_HOUR` 도 쓰지 않는다(사용자: "체크할 필요 없이 KRX 시가를 쓰는 게 원칙") |
| **D-2** | **좁은 목은 `on_open_price_confirmed` 하나** | WS 가 이기는 세 경로(스케줄러 WS 폴링 · 2차 폴백 우선순위 · 전략 인라인 확정)가 **전부 이 setter 로 수렴**한다[코드]. setter 에 **출처 게이트**를 달면 한 곳에서 셋이 닫힌다 |
| **D-3** | **`source` 기본값 = `"ws"`(불신)** | 새 키워드 전용 인자 `source: str = "ws"`. 신뢰 목록은 `("rest",)` 뿐. ⇒ **WS 3 호출부는 한 글자도 안 고친다**(기본값이 이미 불신) ⇒ `check_buy_signal` **byte 동일** ⇒ cycle264 `_STRATEGY_PINS` **6개 전부 불변** |
| **D-4** | **REST 확보는 신규 leaf `src/engine/open_price_rest.py` 가 소유** | R1 = **09:00:35**, 30초 간격 **9라운드**(마지막 09:04:35), 이후 5분 간격 슬로우 라운드 15:20 까지. `scheduler.py` 순증 **+1행** |
| **D-5** | **09:00:05 의 `main` 확정은 leaf 창(∼09:05:00) 동안 스케줄러에서 비운다** | `owns_board()` 로 대상에서 제외 ⇒ REST 0콜·WS 폴링 0초 ⇒ **`_drain_pending_next_day_clear`(익일청산 시장가)가 09:00:14 → 09:00:05 로 앞당겨진다**(U2 R-3 부작용을 없애는 방향) |
| **D-6** | **미프린트(`stck_oprc="0"`)는 "목표가 없음"** | 그 종목은 그 시점 **매수 불가**. 유계 재시도로 확보되면 그때부터 목표가 활성. 상한(09:04:35) 초과분은 `[main_rest_basis_unresolved]` 로 계수하고 슬로우 라운드 + 09:35 스케줄러 백스톱에 넘긴다 |
| **D-7** | **킬스위치 `open_price_scope_mode`**, 전략별, **기본 `"enforce"`(= REST)** | `"off"` 만이 롤백값(대소문자·공백 무시 정확 일치). 그 외 모든 값·부재·예외 = `enforce`. `PARAM_RANGES`/`INT_PARAMS` 편입 금지 |
| **D-8** | **8영역 접촉 0** | `risk.py`·`handler.py`·`scanner.py`·`session.py`·`strategy_registry.py`·`order_engine.py`·`api/order.py`·`realtime/**`·`auth/**` **전부 diff 0**. leaf 는 `scanner.ticker_prices` 를 **읽기만** 한다 |
| **D-9** | **leaf 는 `enabled=False` 전략도 스윕한다** | 오늘 17:07 부로 VB·LTV 둘 다 `enabled=False weight=0`[실측 U2 §1]. 이 결정이 **비중을 한 글자도 안 건드리고** 금요일 실측을 가능하게 하는 유일한 수단이다(§5-c). 비활성 전략은 매수 평가 자체를 안 받으므로 매매 위험 0 |
| **D-10** | **`pre_nxt`/`post_nxt` 전면 무접촉** | 게이트는 `board=="main"` 스코프. LTV 08:00 프리장 확정·목표가·야간 매수·청산 규약 **byte 동일** |

**한 줄** — *"통합 채널이 실어 오는 어제/프리장 시가로 오늘의 돌파선을 긋는 일을 멈춘다. 대신
KRX 시가가 실제로 프린트될 때까지 기다렸다가, 프린트된 그 값으로만 선을 긋는다. 못 기다린
종목은 오늘 안 산다."*

---

## 2. 사용자 질문에 대한 답 — "장 시작 시점에 모든 구독대상 REST 확보가 가능한가"

**결론: 시간은 넉넉히 되고, 값은 09:00:05 에는 3분의 1만 있고 09:00:30 을 넘기면 97%가 있다.
그래서 "09:00:05 에 한 번" 이 아니라 "09:00:35 를 1라운드로 하는 유계 재시도" 로 설계했다.**

**시간(용량).** 대상은 VB·LTV `_targets` 의 **합집합 distinct 종목**이고 3영업일 실측 **73~135**,
오늘 저녁 prepare 기준 **75**(VB 55 ∪ LTV 43, 교집합 23), 설계 상한은 **N=140** 으로 잡는다
(전 구독 종목 `[tick_coverage] subscribed=` 조차 99~139 를 넘은 적이 없다)[실측 U2 §2-b].
1콜 순수 왕복은 **110~150ms**(09:05:30 대조 배치의 순차 실측에서 설계 sleep 0.2초를 뺀 값)[산출 U2 §6-a].
종목 간 `sleep 0.05` 를 넣으면 1콜당 160~200ms, **N=75 → 12~15초 · N=140 → 22~28초**이고,
네트워크 오류 1건이 3회 재시도·backoff 로 최대 4초를 먹으므로 **꼬리 예산 +10초**를 더해도
**09:00:35 시작 → 늦어도 09:01:13 종료**다. cycle262 보류 해제(09:01:30) **안**이다
— 보류 값은 바꾸지 않고 예산으로만 썼다. 전역 리미터는 **20건/초**(메인·보조 7계정 공용,
`src/api/base.py:437-451`)인데 **순차 `await` 의 상한이 애초에 6~9건/초**라 리미터에 닿지 않는다
(한도의 30~45%). 그리고 그 90초 창의 실제 매수 트래픽은 **09-08·09-09 실측 BUY 0건**
(첫 BUY 는 09:01:34 / 09:04:42), 같은 창의 `[quote_pool] 네트워크 오류` 0건, `[token] 분당 한도 대기`
0건이다[실측 U2 §4-b] ⇒ **매수 주문과 다투지 않는다.**

**값(미프린트).** 여기가 진짜 병목이다. 09:00:10~09:00:14 에 실제로 돈 현행 REST 폴백의
성공률은 **36.3%(58/160, 3영업일)** 이고[실측 U2 §5-b], 첫 MAIN 체결 누적 분포는
**09:00:05 에 12~21% → 09:00:30 에 96.9~97.8%** 로 **09:00:30 이 무릎**이다. 즉 09:00:05 에
전 종목을 훑으면 5분의 4를 재시도 대기열로 밀어 넣게 되고, 그 대기열 자체가 랜덤엔드 취약성이다.
**R1 을 09:00:35 로 두면 한 라운드로 ~97%가 끝난다.** 잔여 2~3%는 30초 간격 8라운드(→09:04:35)로
회수하고, 총 콜은 **≈1.25N ≈ 175건 / 5분 = 평균 0.6건/초**(전역 한도의 3%)다. 재시도 간격의
**하한은 5초**다 — `fetch_stock_detail` 캐시 TTL 이 5초라 그보다 짧은 재시도는 같은 캐시값을 다시
읽어 무의미하다(`src/api/condition.py:122`). 30초는 이 계약을 넉넉히 만족한다.

**확보가 어려운 부분을 숨기지 않는다.** 위 97%의 분모는 **"그날 MAIN 틱을 한 번이라도 받은 종목"**
(90/65/91)이고, 구독 종목(139/99/108) 중 **17~49종목이 통째로 빠져 있다** — 대부분 cycle252 가
확인한 `nxt_false` 무송출 코호트다[실측 U2 §5-c]. **A안이 정확히 그들을 구하려는 것인데 그들의
KRX 시가 프린트 시각은 한 번도 측정된 적이 없다**(O-2). 그래서 정직하게 말하면 **전체 대상의
09:00:35 미프린트율은 "3%보다는 크고 64%보다는 훨씬 작다" 까지만 말할 수 있다.** 유계 재시도
9라운드 + 슬로우 라운드가 바로 그 불확실성에 대한 보험이고, 남는 종목은 **오염된 기준가로
들어가는 대신 오늘 안 사는 쪽**으로 떨어진다. 트레이더 판단으로 이 방향이 옳다 —
**틀린 목표선으로 들어간 포지션은 손절선까지 틀리지만, 안 들어간 종목은 기회비용만 남는다.**

**우선순위 큐는 두지 않는다.** N=140 전체가 30초 안에 끝나므로 줄 세울 이유가 없고, 줄을 세우면
"어느 종목이 뒤로 밀렸는가" 라는 새 판독 축이 생겨 D+1 귀인만 흐려진다. 대신 라운드가 길어지는
비상 상황(네트워크 열화)에 대비해 **라운드당 벽시계 상한 45초**를 두고, 초과하면 그 라운드를
끊고 다음 라운드로 넘긴다(`[main_rest_basis_round] truncated=1`).

---

## 3. 설계

### 3-a. 왜 setter 한 곳인가 — 좁은 목 [코드]

`main` 기준가를 만드는 경로는 셋이고 **전부 `on_open_price_confirmed` 로 수렴한다**[U1 §3].

| 순위 | 경로 | 파일:줄 | 왜 WS 가 이기나 |
|---|---|---|---|
| 1 | 스케줄러 1차 WS 폴링 | `scheduler.py:1660-1662` | `ticker_prices[t]["open_price"]` 의 **나이를 안 본다**. 08:00 프리장 틱이 남긴 값이 그대로 살아 있어 MAIN 틱이 0개여도 확정된다 |
| 2 | 스케줄러 2차 REST 폴백 | `scheduler.py:1670-1682` | **미확정 종목만** 본다. 1차가 이미 심었으므로 차례가 오지 않는다 |
| 3 | 전략 인라인 확정 | `volatility_breakout.py:899-901` / `long_tail_volatility.py:705-707` | 첫 MAIN 틱에서 09:00:05 스케줄러보다 **먼저** 확정할 수 있다 |

⇒ **setter 첫 문장에 출처 게이트**를 두면 셋이 한 번에 닫힌다. 그리고 `source` 기본값을
**`"ws"`(불신)** 으로 두면 위 1·3 호출부는 **한 글자도 고치지 않아도** 거부된다.

### 3-b. 게이트 (전략 2파일, VB·LTV 동형)

```python
# on_open_price_confirmed 의 **첫 문장**
def on_open_price_confirmed(
    self, ticker: str, open_price: int, board: str = "main", *, source: str = "ws",
) -> None:
    if open_price_rest.reject_untrusted_main_basis(
        self.config.params, board, source,
        strategy_id=self.config.strategy_id, ticker=ticker, tick_open=open_price, dest_logger=logger,
    ):
        return
    ...  # 이하 현행 본문 **byte 동일**
```

leaf 쪽 판정 본체(순서가 계약이다):

```python
_MAIN_BOARD = "main"
_TRUSTED_MAIN_SOURCES = ("rest",)          # 채널 분리(P1-7 B) 때 "ws_krx" 가 여기에 꽂힌다
MODE_KEY, MODE_ENFORCE, MODE_OFF = "open_price_scope_mode", "enforce", "off"

def reject_untrusted_main_basis(params, board, source, **obs) -> bool:
    if board != _MAIN_BOARD:                 # ① 순수 비교 — 예외 불가
        return False
    if source in _TRUSTED_MAIN_SOURCES:      # ② REST 경로는 params 를 읽기 전에 통과
        return False
    try:
        mode = resolve_mode(params)
    except Exception:
        mode = MODE_ENFORCE                  # 선언된 기본값
    if mode == MODE_OFF:
        return False
    _emit_config_canary(...)                 # never-raise, 별도 try
    return True
```

**②가 ③(try/params 접근)보다 앞이라는 것이 안전 계약이다** — 이 순서 덕분에 게이트가 무슨
이유로 터지든 **REST 경로는 구조적으로 면역**이고, "게이트 고장 = 종일 목표가 0" 이라는
P0-1 계열 사고가 성립하지 않는다. AST 가드로 못 박는다(C5).

**모드 해석**: `str(params.get(MODE_KEY, MODE_ENFORCE) or MODE_ENFORCE).strip().lower()` 가
정확히 `"off"` 일 때만 `off`, 그 외(부재·`None`·`""`·오타·타입 이상·예외) 전부 `enforce`.
오타로 롤백이 조용히 실패하는 것을 막기 위해 **카나리아가 원문 값을 함께 남긴다**
(`mode=enforce raw="of"` ⇒ 5분 안에 눈에 띈다).

### 3-c. leaf `src/engine/open_price_rest.py` (신규) — **행위 leaf**

> ⚠️ cycle264 의 `open_price_observe.py` 는 "행위 변경 0" 이 첫 계약인 **관측 leaf** 였다.
> 이 모듈은 반대다 — **목표가를 실제로 세우는 행위 leaf** 이며, 그 사실을 docstring 첫 줄에
> 명시한다. never-raise 는 **관측에만** 적용하고, 확보 실패는 침묵하지 않고 계수·기록한다.

| 상수 | 값 | 근거 |
|---|---|---|
| `TIME_MAIN_REST_BASIS_R1` | **09:00:35** | 09:00:30 이 프린트 무릎[실측]. `SWING_REST_POLL_EARLY_START=09:00:30`(보유 6~8종목 폴)과 **같은 순간을 피하려고 +5초**. 곡선이 그 뒤로 평평하므로 5초는 아무것도 잃지 않는다 |
| `MAIN_REST_BASIS_ROUND_INTERVAL_S` | **30.0** | 캐시 TTL 5초 하한을 6배 넘김. 라운드당 잔여 2~3% |
| `MAIN_REST_BASIS_FAST_ROUNDS` | **9** (09:00:35 … 09:04:35) | 09:05:00 `_swing_buy_poll_loop` 정각·09:05:30 cycle264 대조 배치 **둘 다 피한다** |
| `MAIN_REST_BASIS_SLOW_INTERVAL_S` | **300.0** | 09:05~15:20. 재-prepare(`_reprepare_breakout_if_empty`)로 되살아난 미확정 종목 회수 + 킬스위치 카나리아의 종일 채널 |
| `TIME_MAIN_REST_BASIS_STOP` | **15:20** | VB 매수컷(`BUY_CUTOFF_KST`)과 같은 시각. 그 뒤에 목표가를 세울 이유가 없다 |
| `TIME_MAIN_REST_BASIS_HANDOFF` | **09:05:00** | 이후 `owns_board()` = False ⇒ 스케줄러 백스톱 부활 |
| `_TICKER_SLEEP_S` | **0.05** | `_swing_rest_poll_once` 선례(20/s 상한 대비 순차 실효 6~9/s) |
| `_ROUND_WALL_CLOCK_MAX_S` | **45.0** | 라운드가 다음 라운드를 침범하지 않게 |
| `_READY_POLL_INTERVAL_S / _MAX_S` | 2.0 / 90.0 | cycle264 선례(prepare 미완료 대기, 타임아웃은 **침묵 금지**) |

**한 라운드의 처리 순서 (계약)**

1. 대상 전략 = `("volatility_breakout", "long_tail_volatility")` 중 (i) `main ∈ get_tradable_boards`
   (ii) `resolve_mode(params) == "enforce"` 인 것. **`config.enabled` 는 보지 않는다**(D-9).
2. 각 전략의 `_targets` 스냅샷에서 `_open_confirmed[t].get("main") is not True` 인 종목을 모으고,
   **전략 합집합의 distinct ticker** 로 접는다(같은 종목을 두 번 조회하지 않는다 — 5초 캐시에만
   기대지 않는다. 스윕이 15~28초라 캐시 TTL 밖이다).
3. 조회 **직전에** `scanner.ticker_prices.get(t, {}).get("open_price", 0)` 를 읽어 둔다
   (= 옛 코드가 그 순간 썼을 값 = **shadow**). **읽기만 한다.**
4. `fetch_stock_detail(t)` → `stck_oprc` 파싱.
   - `>0` → 그 종목을 필요로 하는 **모든** 대상 전략에 대해
     `strategy.on_open_price_confirmed(t, v, board="main", source="rest")` +
     `open_price_observe.mark_confirmed_via_rest(sid, t, "main")` +
     `[main_rest_basis_confirmed]` 1행(shadow 병기).
   - `0`/빈/비숫자 → 확정 없음, `reason=rest_zero` 계수.
   - 예외 → 확정 없음, `reason=rest_error` 계수. **둘을 분리한다**(현행은 한 `except` 로 삼켜
     구분 불가 — O-1 이 하루 만에 갈린다).
5. 종목 간 `await asyncio.sleep(0.05)`.
6. 라운드 종료 시 전략별 `[main_rest_basis_round]` 1행.
7. **빠른 창의 마지막 라운드(09:04:35) 직후**, 남은 미확정 종목마다
   `[main_rest_basis_unresolved]` 1행(1회/(전략,종목)/일).

**never-raise / lifecycle**: 라운드 본체는 통째로 `try/except Exception` 이고 `CancelledError` 는
re-raise. task 속성명은 **`_main_rest_basis_task`**(`_*_task_handle` 은 cycle79 수집기에 안 잡힌다),
`start()`·`run_daily()`·`stop()` **세 취소 목록 전부**에 등재(cycle264 체크리스트).

### 3-d. `scheduler.py` — 5곳, 순증 **+1행** (3,898 → 3,899 < 3,900)

| # | 위치 | 변경 | 라인 |
|---|---|---|---|
| S1 | `:42` | `from src.engine import open_price_observe, open_price_rest  # cycle264 관측 leaf / cycle272 기준가 leaf` — **기존 import 행에 합류** | **+0** |
| S2 | `:723-726` 옆 | `self._main_rest_basis_task = asyncio.create_task(open_price_rest.main_rest_basis_task_loop(self))  # cycle272 — …` (cycle269 1행 스타일) | **+1** |
| S3 | `:1622` | `if MarketBoard(board) not in allowed or open_price_rest.owns_board(strategy, board):` | +0 |
| S4 | `:1679` | `strategy.on_open_price_confirmed(ticker, open_price, board=board, source="rest")` | +0 |
| S5 | `:1013 / :1140 / :1176` | 취소 목록 3행에 `"_main_rest_basis_task",` 추가(같은 행 안) | +0 |

> **권고(선택)** — `:723-725` 3행을 cycle269 처럼 1행으로 접으면 **−2행**(AST 동일, 가드 무영향)
> 이 되어 3,897L 로 여유 2행을 남긴다. 접지 않으면 상한까지 **여유 0** 이며 다음 사이클이
> scheduler 를 손대려면 무조건 다이어트가 선행된다. 기능과 무관한 정리이므로 사이클 명세에
> 넣되 **필수 계약은 "≤ 3,899"** 로 둔다.

`owns_board(strategy, board, *, now=None)` = `board=="main" ∧ resolve_mode(params)=="enforce" ∧
now_kst.time() < 09:05:00`. **예외는 False(fail-open = 스케줄러가 계속 담당)**. 이 함수 하나로
09:00:05 의 `main` 확정이 비고 `_drain_pending_next_day_clear` 가 앞당겨진다.

### 3-e. 타임라인 (배포 후 정상 하루)

```
07:55  prepare — _targets 채워짐, _open_confirmed[t] = {}
08:00:05  LTV pre_nxt 확정 (board="pre_nxt")            ← 무접촉, byte 동일
09:00:00~ 첫 MAIN 틱 → 인라인 확정 시도 → 게이트가 거부(main) → 목표가 없음 → Signal.NONE
09:00:05  _confirm_breakout_open_prices(board="main") → owns_board=True → 대상 0 → 즉시 반환
09:00:05.x _drain_pending_next_day_clear (익일청산 시장가)   ← 현행 09:00:14 대비 **~9초 앞당김**
09:00:35  R1 — distinct 75~140종목 REST 스윕 (12~28초) → ~97% 확정
09:01:05  R2 … 09:04:35 R9 — 미확정만 재조회
09:01:30  cycle262 보류 해제 — 이 시점에 목표가는 이미 서 있다
09:05:00  owns_board=False — 스케줄러 백스톱 부활
09:05:30  cycle264 [open_source_compare] — used_src 전부 rest, delta_bp 전부 0 (= 시정 발효 서명)
09:10~15:20  슬로우 라운드 5분 간격(미확정 0이면 REST 0콜·로그 0행)
09:35~     _scan_loop 5분 주기 [open_confirm_retry] → 스케줄러 REST 폴백(백스톱)
```

---

## 4. 킬스위치와 롤백

| 축 | 내용 |
|---|---|
| **키** | `open_price_scope_mode` — VB·LTV **각각의** `DEFAULT_PARAMS`(상호 import 금지, cycle262 G-262-9 답습) |
| **값** | `"enforce"`(기본) = `main` 기준가는 KRX REST 만 / `"off"` = cycle271 이전 행위(WS 캐시·인라인 확정 허용) |
| **부재 시** | **`enforce`**(= 새 기본). 사용자 D1 "체크할 필요 없이 KRX 시가를 쓰는 게 원칙" 의 직역이다 |
| **"부재=새 행위" 위험의 봉인** | AST glob 가드(C27)가 키 리터럴이 **정확히 {VB, LTV}** 의 `DEFAULT_PARAMS` 에 값 `"enforce"` 로 존재함을 강제한다. DB 오버레이는 **알려진 키만** 덮으므로(라우트·`_load_strategy_config` 둘 다 `if key in params`) 운영에서 "키가 사라지는" 경로는 소스 삭제뿐이고 그건 가드가 붉어진다 |
| **금지** | `PARAM_RANGES`·`INT_PARAMS` 편입 금지(진입 정체성 상수) + AI 자문 자동 적용 화이트리스트 배제 |
| **장중 롤백** | `PUT /api/strategies/{id}/params {"open_price_scope_mode":"off"}` — 라우트가 in-memory `config.params` 를 즉시 덮는다. `strategy_config` SQL UPDATE 는 **다음 재시작에서만** 반영되고 cycle232 D6 가 보유 중 장중 재시작을 금지하므로 **장중 실효 수단은 PUT 뿐** |
| **⚠️ 배포 전 PUT 은 무음 실패** | 라우트가 미지 키를 조용히 버리고 `params` JSONB 를 통째로 덮어 먼저 넣은 SQL 값까지 지운다(cycle245 실측). **DB 선반영 금지** |
| **부분 롤백** | 전략별 키이므로 "VB 만 off, LTV 는 enforce" 가능 |

### 4-a. ⚠️ 롤백의 비대칭 — 반드시 명세·보고서에 남길 것

`open_entry_hold_secs`(cycle262)는 `check_buy_signal` 이 **매 틱** `config.params` 를 다시 읽어
PUT 이 그 즉시 행위를 바꿨다. **목표가 기준가는 다르다** — 한 번 `_targets[t]["boards"]["main"]`
에 박히면 그날 그 값이다. 그래서:

- **enforce → off 로 PUT 하면**: 이미 REST 로 확정된 종목의 목표가는 **그대로 남는다**(그 값이
  올바른 KRX 시가이므로 문제되지 않는다). 바뀌는 것은 **아직 미확정인 종목**뿐이고, 그들은
  다음 틱의 인라인 확정 또는 스케줄러 WS 폴링으로 구(舊) 경로를 탄다.
- **즉 롤백은 "전진 방향" 으로만 듣는다.** 그날 이미 선 목표선을 되돌리는 수단은 없다.
- 완전 복원 단위는 **다음 영업일**이다. 코드 롤백은 `src/**` 변경이라 cycle248 **full 모드**
  ⇒ 장외 창(15:30~19:55 · 20:20~익일 07:45 · 주말, **20:00~20:15 금지**)에서만.
- **롤백이 실제로 먹혔는지 확인하는 채널** = `[main_rest_basis_config]` 의 **값-민감 cap**
  (`key = f"cfg|{mode}"`, cycle262 G-262-7e 답습). 단일 키였다면 그날 첫 행이 cap 을 소진해
  바뀐 값을 확인할 마커가 0행이 된다. 슬로우 라운드가 5분 주기이므로 **PUT 후 5분 안에**
  `mode=off` 행이 뜬다.

---

## 5. 관측과 D+1 (금 09-11)

### 5-a. 마커 4종 (전부 신규 — cycle264 마커 이름 재사용 금지)

```
[main_rest_basis_config]    emitter=leaf|gate strategy=%s mode=enforce|off raw=%s source=default|override
                            # 1회/(전략,모드,emitter)/일 — 값-민감 cap
[main_rest_basis_round]     round=%d/%d kind=fast|slow mode=%s strategy=%s board=main
                            total=%d confirmed=%d pending=%d ok=%d zero=%d err=%d
                            calls=%d elapsed_ms=%d truncated=0|1
                            # fast 라운드는 항상, slow 라운드는 pending>0 일 때만
[main_rest_basis_confirmed] strategy=%s ticker=%s board=main round=%d rest_open=%d
                            ws_open=%d ws_src=cache|absent delta_bp=%+.1f
                            target_rest=%d target_ws=%d
                            # 1회/(전략,종목)/일 — **오염 규모의 새 정본(shadow)**
[main_rest_basis_unresolved] strategy=%s ticker=%s board=main reason=rest_zero|rest_error|no_tick
                            rounds=%d
                            # 1회/(전략,종목)/일 — **커버리지 손실 정본**. 0이 아니면
                            # "고치려다 매수를 잃고 있다" 는 뜻이다
```

**공통 계약** — 모든 emit 은 `try/except` + `observer_trace.trace_observer_failure`(never-raise),
cap 은 **마커마다 별개 `KstDailyEmitCap` 인스턴스**(`now=` 키워드 전용), `logger` 만 사용
(`write_log`/DB/`await` 금지), **행위는 관측 밖**이다.

### 5-b. `delta_bp=0` 산술 항등 문제를 어떻게 남기는가 (질문 5의 핵심)

시정 후 cycle264 `[open_source_compare]` 는 `used_open` 이 곧 REST 값이라 **`used_src` 100% rest ·
`delta_bp` 100% 0** 으로 붕괴한다. 그것을 **없애지 않고 서명으로 재해석**한다.

| 채널 | 시정 후 의미 |
|---|---|
| `[open_source_compare] used_src` | **전부 `rest` 여야 정상.** `ws` 행이 **한 줄이라도** 있으면 게이트를 뚫은 값이 있다는 **결함 서명**이다(영구 회귀 탐지기로 승격) |
| `[open_source_compare] delta_bp` | 전부 0 — **산술 항등이므로 오염 지표로 읽지 마라.** ⚠️ **배포 전후 grep 합산 금지** |
| **`[main_rest_basis_confirmed]` 의 `ws_open`/`delta_bp`** | **오염 규모의 새 정본.** leaf 가 REST 조회 **직전에** `ticker_prices` 를 읽어 "옛 코드가 그 순간 썼을 값" 을 그대로 병기한다. 3일치 판독의 `delta_bp` 중앙값 73.7~118.4bp·>100bp 46.3% 와 **같은 축에서 이어 읽을 수 있다** |
| `ws_src=absent` | 그 종목은 그 시각 WS 캐시에 시가가 아예 없었다 = **오염이 아니라 부재**였던 코호트. 채널 분리(P1-7 B)가 못 고치는 부분의 크기를 처음으로 잰다 |

> ⚠️ shadow 의 한계 — leaf 가 읽는 시각은 09:00:35 이고 옛 코드가 읽던 시각은 09:00:05~14 다.
> `[7]` 은 일-스코프 상수라 그 30초 사이에 바뀌지 않는 것이 **결함의 본질**이므로 실무상 같은
> 값이지만, **동일 시각 대조는 아니다**. 판독문에 이 문장을 그대로 남길 것.

### 5-c. ⚠️ 금요일에 볼 것이 0행일 수 있다 — 먼저 알린다

**[실측 U2 §1]** 오늘 **17:07:25** 에 운영 DB `strategy_config` 가 바뀌어 **VB·LTV·momentum 이
`enabled=false weight=0`** 이다(`[src.engine.strategy_registry] 비중 변경: 변동성 돌파 → 0%` 7행 세트).
이 변경은 어느 정본 문서에도 기록돼 있지 않다. 비중은 **사용자 결정 항목이자 무접촉 6종**이므로
이 자문은 바꾸자고 제안하지 않는다. 대신 사실을 그대로 놓는다:

- `_confirm_breakout_open_prices` 는 `config.enabled` 로 거르고, cycle264 `[open_source_compare]` 도
  `config.enabled` 로 거른다 ⇒ **현재 상태 그대로면 금요일 09:00 에 그 둘은 0행**이다.
  이는 cycle272 배포와 무관한 기존 동작이다.
- **그래서 D-9 를 넣었다** — leaf 는 `enabled` 를 보지 않고 `_targets`(저녁 prepare 로 살아 있다,
  오늘 실측 VB 55 · LTV 43 · 합집합 75)만 본다. 비활성 전략은 `check_buy_signal` 자체가 호출되지
  않으므로 **매수 위험 0** 이고, 그 결과 **비중을 한 글자도 안 건드리고** `[main_rest_basis_*]` 4종이
  정상 발화해 금요일 실측이 성립한다.
- 다만 **"진입 건수" 축은 여전히 못 잰다** — 비활성 전략은 애초에 사지 않는다. 금요일에 검증되는
  것은 (i) REST 확보 성공률·시각 (ii) 오염 규모 shadow (iii) 게이트가 실제로 WS 를 막는가 (iv) 부하·
  타이밍 이고, **진입 건수 영향은 두 전략 중 하나가 켜진 날에만** 읽을 수 있다(§9 O-A).

### 5-d. D+1 판독 체크리스트 (09-11 금, INFO 는 2일 보존 — 그날 안에 구조 덤프)

1. `[main_rest_basis_config]` — `mode=enforce source=default` 가 VB·LTV 각 1행씩(emitter=leaf).
   `raw` 가 `enforce` 그대로인지.
2. `[main_rest_basis_round] round=1/9 kind=fast` 가 **09:00:35~09:01:15 사이**에 존재.
   **이 행이 없으면 leaf task 가 안 떴다는 뜻** — 최우선 알람.
3. R1 의 `confirmed/total` ≥ **0.90**(기대 ~0.97), `elapsed_ms` ≤ **30,000**, `truncated=0`.
4. R2~R9 의 `pending` 이 단조 감소하고 R9 에서 0 또는 한 자릿수.
5. `[main_rest_basis_unresolved]` 행 수 — **0~5 가 기대. 두 자릿수면 설계 전제(97% 무릎)가
   그 날 깨진 것**이고 재시도 일정을 재검토한다. `reason` 분포로 O-1(미프린트 vs 예외)이 갈린다.
6. `[main_rest_basis_confirmed]` 행 수 ≈ 75~140, `ws_src=absent` 비율(= 채널이 못 준 코호트 크기),
   `delta_bp` 분포를 3일치(중앙값 73.7 / 78.0 / 118.4bp)와 나란히.
7. `[open_source_compare]` — **`used_src=ws` 0행**(있으면 결함), `reason≠ok` 0행.
   ※ 두 전략이 비활성인 한 이 마커 자체가 0행이다(5-c).
8. `[breakout_open_confirm] board=main` 이 **09:00:1x 에 사라진다** — `owns_board` 로 대상이
   비기 때문이다(의도된 침묵). 09:35 이후 pending 이 있을 때만 다시 나타난다.
   **배포 전후 행 수 합산 금지.**
9. `_drain_pending_next_day_clear` 관련 로그(`[next_day_clear_drained]`)의 시각이 **09:00:06 이전**
   으로 앞당겨졌는지(현행 09:00:14.4 실측 대비).
10. `[quote_pool] 네트워크 오류` / `[token] 분당 한도 대기` 가 09:00~09:06 구간에 **0건 유지**.

### 5-e. 진입 건수 변화의 귀인 — cycle262(90초 보류)와 어떻게 가르는가

- **시각으로 가른다.** cycle262 는 **09:00:00~09:01:30** 창 안에서만 매수를 막고, cycle272 는
  **목표가가 서는 시각을 09:00:0x → 09:00:35~09:04:35 로 옮긴다.** 두 효과가 겹치는 구간은
  보류 창 안뿐인데 그 창은 어차피 매수 0 이다 ⇒ **09:01:30 이후의 진입 변화는 전부 cycle272 몫**이다.
- **`[open_entry_hold_blocked]`(cycle262 would_buy 정본)의 감소는 cycle272 의 부수 효과이지
  새로운 억제가 아니다** — 목표가가 없는 동안에는 발사점까지 가지 못해 그 마커가 찍히지 않는다.
  이 마커의 감소를 "보류가 더 세졌다" 로 읽지 말 것.
- **종목 단위 대조가 가능하다** — `[main_rest_basis_confirmed]` 가 종목별로
  `target_ws` / `target_rest` 를 둘 다 남기므로, 그날 실제 체결(있다면)이 어느 목표선에서
  나왔는지 사후에 정확히 귀인된다.

---

## 6. Red 계약 (C1~C28)

> 전부 **테스트 가능한 한 줄** 형태다. 신규 파일 =
> `tests/unit/engine/strategies/test_cycle272_main_rest_basis.py`(게이트) ·
> `tests/unit/engine/test_cycle272_open_price_rest_leaf.py`(leaf) ·
> `tests/unit/ast/test_cycle272_ast_main_rest_basis.py`(구조).

**게이트 (전략 2파일)**
- **C1** `open_price_scope_mode="enforce"` 에서 `on_open_price_confirmed(t, 80000, board="main")`
  (source 미지정)은 `boards["main"]` 을 만들지 않고 `_open_confirmed[t]["main"]` 도 True 가 되지 않는다 — VB·LTV 각각.
- **C2** 같은 호출에 `source="rest"` 를 주면 `boards["main"]` 3키(`open_price`/`target_price`/
  `target_offset`)가 **현행과 값이 완전히 같다**(`k_value_krx_main` 적용 격자 포함).
- **C3** `open_price_scope_mode="off"` 면 `source` 미지정 호출도 현행대로 확정된다(두 전략 독립 —
  VB off · LTV enforce 조합에서 각자 다르게 동작).
- **C4** `board ∈ {"pre_nxt","post_nxt"}` 는 mode×source 4조합 전부에서 **현행 byte 동일**
  (LTV 08:00 프리장 확정·목표가·`_BOARD_K_KEY` 선택 포함).
- **C5** (AST) `reject_untrusted_main_basis` 안에서 `board != "main"` 조기 반환과
  `source in _TRUSTED_MAIN_SOURCES` 조기 반환이 **모든 `try` 블록·`params` 접근보다 앞**이다.
- **C6** 모드 해석 격자 — `{부재, None, "", "  ", "ENFORCE", "enforce", "Off", " off ", "OFF",
  "true", 0, [], {"a":1}}` 에 대해 `"off"` 로 해석되는 것은 **대소문자·공백 무시 `off` 뿐**이고
  나머지는 전부 `"enforce"`. `params` 접근이 예외를 던져도 `"enforce"`.
- **C7** (AST/sha) `check_buy_signal`·`check_exit_signal`·`calc_buy_quantity` 는 VB·LTV 모두
  **한 글자도 바뀌지 않는다** — cycle264 `_STRATEGY_PINS` **6개 sha 전부 불변**(갱신 금지가 계약).
- **C8** enforce+main 에서 목표가가 없는 동안 `check_buy_signal` 은 `Signal.NONE` 을 반환하고
  `_prev_price[t]["main"]` 을 **쓰지 않는다**(조기 return 이 baseline 갱신보다 앞이라는 현행 구조 재확인).
- **C9** 게이트 관측(`[main_rest_basis_config]`)이 예외를 던져도 `on_open_price_confirmed` 의
  반환값·상태 변화가 동일하다(폭발기 주입, cycle262 `test_c10_4` 패턴).
- **C10** `on_open_price_confirmed` 의 시그니처는 `(self, ticker, open_price, board="main", *, source="ws")`
  이고 `source` 는 **키워드 전용**, 기본값 리터럴은 **`"ws"`**, 신뢰 목록 리터럴은 **`("rest",)`**(AST).

**leaf**
- **C11** 라운드 발화 시각이 정확히 09:00:35 · 09:01:05 · … · 09:04:35(9회) 이후 5분 간격
  15:20 까지다(freezegun 전수).
- **C12** 라운드 대상 = `main ∈ get_tradable_boards ∧ mode=="enforce" ∧ _open_confirmed[t]["main"] is not True`
  인 종목뿐이며 **`config.enabled` 는 대상 판정에 쓰이지 않는다**(비활성 전략도 스윕).
- **C13** VB·LTV 공통 종목에 대해 한 라운드의 `fetch_stock_detail` 호출은 **정확히 1회**이고,
  확정은 **두 전략 모두에** 적용된다.
- **C14** `stck_oprc>0` → `on_open_price_confirmed(..., board="main", source="rest")` **와**
  `open_price_observe.mark_confirmed_via_rest(sid, t, "main")` 를 **둘 다** 호출한다.
- **C15** `stck_oprc` 가 `"0"`/`""`/`"abc"` 면 `reason=rest_zero`, 예외면 `reason=rest_error` 로
  **분리 계수**되고 어느 쪽도 확정하지 않는다.
- **C16** 종목 간 `asyncio.sleep(0.05)` 가 실제로 삽입되고, 한 라운드의 REST 호출이 어떤 1초
  구간에서도 **20건을 넘지 않는다**(가짜 시계 + 호출 타임스탬프).
- **C17** 라운드 벽시계가 45초를 넘으면 그 라운드를 끊고 `truncated=1` 로 남긴 뒤 다음 라운드가
  예정 시각에 정상 발화한다.
- **C18** 라운드 본체 예외에도 task 는 죽지 않고 다음 라운드가 돈다; `CancelledError` 는 re-raise.
- **C19** `_targets` 가 비면 REST 0콜로 지나가고 준비 폴링 90초 초과 시
  `skipped reason=no_target` 1행을 **침묵하지 않고** 남긴다.
- **C20** leaf 는 `scanner.ticker_prices` 를 **읽기만** 한다 — 라운드 전후 dict 의 키·값 스냅샷 동일.
- **C21** 빠른 창 마지막 라운드 직후 미확정 종목마다 `[main_rest_basis_unresolved]` 1행
  (1회/(전략,종목)/일), `reason`·`rounds` 포함.
- **C22** task 속성명은 `_main_rest_basis_task` 이고 `start()`·`run_daily()`·`stop()`
  **세 취소 목록 전부**에 등재된다(cycle264 `_create_task_attrs` 수집기 재사용).

**scheduler**
- **C23** `owns_board(strategy,"main")` True 인 동안 `_confirm_breakout_open_prices(board="main")` 은
  그 전략을 대상에서 빼고, 두 전략 모두 빠지면 **WS 폴링 0초·REST 0콜**로 즉시 반환한다.
- **C24** 그 결과 09:00:05 phase 에서 `_drain_pending_next_day_clear` 가 confirm 반환 직후
  실행된다(호출 순서 불변, 소요 0 확인).
- **C25** `owns_board` 는 09:05:00 이후 False 이고, 그때부터 `_confirm_breakout_open_prices` 의
  2차 REST 폴백이 백스톱으로 정상 확정한다(1차 WS 폴링은 게이트가 전부 거부해 확정 0).
  `owns_board` 예외는 **False(fail-open)**.
- **C26** (AST) `scheduler.py:1679` 호출만 `source="rest"` 키워드를 **명시**하고, `:1662`·VB·LTV
  인라인 3곳은 **명시하지 않는다**(기본 `"ws"` 의존이 계약).
- **C27** `wc -l src/engine/scheduler.py ≤ 3,899` 이며 cycle257 리터럴 대조 가드
  (`test_c7_scheduler_line_cap_matches_cycle257_guard`)가 계속 통과한다.

**파라미터·범위·문서**
- **C28** `open_price_scope_mode` 는 `PARAM_RANGES`·`INT_PARAMS` 어디에도 없고
  `recommendation_engine.py` 소스에 문자열 리터럴 **0건**(cycle262 G-262-1a/1b 동형) ·
  전략 `*.py` glob 전수에서 이 키를 `DEFAULT_PARAMS` 에 가진 파일은 **정확히 {VB, LTV}**,
  값 리터럴은 `"enforce"` · 8영역 9경로 diff 0 · 전략 7파일 중 VB·LTV 외 5파일 diff 0 ·
  `_workspace/00_leader_trading_rules.md` 와 `src/engine/strategies/CLAUDE.md` 에 새 키가 기재됨
  (cycle254 G-254-4 문서 가드 패턴).

### 6-a. 의도적으로 깨질 기존 테스트 — 처리 방침 (U3 §6)

> **원칙 — 삭제하지 않는다.** `off` 경로는 살아 있는 롤백 경로이므로 그 계약을 검증하는
> 테스트도 살아 있어야 한다. 기존 테스트는 **"레거시(off) 경로 회귀 가드" 로 재분류**하고,
> enforce 판은 cycle272 신규 파일에 추가한다.

| 묶음 | 파일 | 처리 |
|---|---|---|
| WS 캐시가 main 기준가를 만든다는 계약 | `tests/integration/test_confirm_open_prices.py` (`..._when_open_price_in_cache_then_target_set`, `..._falls_back_to_kis_api_when_open_price_missing`, idempotent/partial 2건) | 픽스처에 `open_price_scope_mode="off"` 명시 → **현행 계약 그대로 유지**. enforce 판(=WS 무시·REST 채택·owns_board 조기 반환)은 신규 파일에 |
| 인라인 자동확정 의존 | `test_volatility_breakout.py` L130~203 5건 · `test_long_tail_volatility.py` L74~98 2건 | 동일하게 `"off"` 픽스처. **행위를 검증하는 테스트는 off 로** |
| setter 직접 호출로 상태만 세팅 | `test_cycle262_open_entry_hold.py`(`_armed`) · `test_cycle201_vb_reentry_cooldown.py` · `test_cycle213_ltv_reentry_cooldown.py` · `test_cycle229_vb_buy_cutoff.py` · `test_cycleG_vb_failed_breakout_exit.py` · `test_volatility_breakout.py::test_on_open_records_top_level_compat...` | 셋업 호출에 **`source="rest"` 한 인자 추가**. **상태 셋업이 목적인 테스트는 source 로** — 의미상으로도 정직하다("이 테스트는 REST 로 확정된 기준가를 심는다") |
| 구조/AST — 생존 예상, 재확인 필수 | `tests/integration/test_post_nxt_open_price_confirm.py`(board 인자 명시 검사) · `tests/unit/engine/test_cycle164_open_confirm_retry_chain.py`(09:35 시각) · `tests/unit/engine/test_cycle264_open_source_compare.py`(라벨 부여 규칙 자체는 불변) | 실행해 확인만 |
| 시각 의존으로 흔들릴 수 있음 | `tests/unit/engine/scheduler/test_confirm_open_prices_main_only.py` | `owns_board` 때문에 09:00~09:05 구간에서 main 대상이 0 이 된다 ⇒ freezegun 으로 **09:35 고정** 또는 `"off"` 픽스처로 재조정 |
| cycle264 킬스위치 금지 목록 | `tests/unit/ast/test_cycle264_scope_and_pins.py::test_c7_no_killswitch_param_introduced` | 금지 목록에서 **`open_price_scope_mode` 하나만 제거**. `open_scope_observe_enabled`·`open_source_compare_enabled` 금지는 **유지**(관측 킬스위치 금지 계약 보존). 테스트 자체는 삭제하지 않는다 |
| cycle264 sha 핀 | 같은 파일 `_STRATEGY_PINS` 6개 | **갱신하지 않는다.** cycle264 docstring 은 "cycle265 가 갱신한다" 고 예고했으나 이 설계는 `check_*`/`calc_*` 를 건드리지 않으므로 **6/6 불변이 곧 "여섯 가지 무접촉" 의 기계적 증거**다. docstring 의 예고 문장만 정정한다 |
| 커밋 직전 절차 | `test_cycle223_ast_donchian_exit_fix.py::test_g223_12`(`_CYCLE228_STRATEGY_CONTENT_SHA`, 현재 빈 dict) | VB·LTV 2항목을 **커밋 직전에 한시 등록, 커밋 직후 삭제**. 8영역 무접촉이므로 자매 가드 4곳은 손대지 않는다. ⚠️ 다른 에이전트가 같은 창에 전략/8영역을 건드리면 핀이 뒤엉킨다 — 커밋 직전 `git status` 재확인 |

---

## 7. 행위 영향 추정 (예상은 예상으로)

### 7-a. 진입 건수 — **단일 숫자로 말할 수 없다. 부호까지 날마다 뒤집힌다.**

| 모집단 | 값 | 성격 |
|---|---|---|
| 후보-레벨 3영업일(ws 종목 257행, 일봉 고가 대용) | 09-08 **−24.4%** · 09-09 **−3.6%** · 09-10 **+17.1%** (합 −4.8%) | [실측] 방향 리포트 §1-b |
| VB 실제 BUY 116건 재계산(2026-04-24~09-04) | **−27.6%** | [인용] 자문 §9. **선택 편향 코호트**(기준가가 낮을수록 매수가 난다) |
| 목표가 이동폭 | median **+85.3bp** · mean **+196.1bp**, 상승(=진입 어려워짐) 방향 68% | [인용] 자문 §9 |

> **승인 문서에 "−27.6%" 를 확정 수치처럼 쓰지 마라.** 제시 형태는
> **"레짐별 분포, 3영업일 관측 범위 −24.4% ~ +17.1%"** 여야 한다. 그리고 두 수치는
> **모집단이 다르므로 나란히 놓지 마라.**

### 7-b. 이 설계 고유의 추가 증감 요인

| 요인 | 방향 | 크기 추정 |
|---|---|---|
| 09:00:00~09:00:35 목표가 부재 | 감소 | **실효 0** — cycle262 보류가 09:01:30 까지 매수를 막는다. 다만 **보류 값에 의존하지 않는 설계**여야 하므로(자문 §10-5) 보류가 0 으로 롤백돼도 "목표가 없으면 신호 없음" 으로 안전하게 떨어진다는 것을 C8 이 못 박는다 |
| 미해결 코호트(R9 이후 남는 종목)의 종일 매수 불가 | 감소 | **[추론] 0~3%**(무릎 이후 잔여율). `[main_rest_basis_unresolved]` 가 유일한 계수 수단. 두 자릿수면 전제 붕괴 |
| `nxt_false` 무송출 코호트가 처음으로 목표가를 갖게 됨 | **증가** | **미측정**(O-2). 이들은 지금 WS `[7]` 이 아예 없어 인라인 확정이 안 되고 09:00:05 REST 폴백에만 의존한다. REST 주경로로 바뀌면 커버리지가 **늘어난다** — 이 사이클의 유일한 "진입 증가" 요인 |
| 09:35 이후 재-prepare 종목 | 중립 | 기준가만 REST 로 바뀐다 |

### 7-c. 진입 이외 축

- **청산 규약**: 전면 무접촉. LTV 익일 갭률(`long_tail_volatility.py:938`)·momentum·kojiro 갭 가드는
  `[7]` 을 계속 쓴다(후속 F-3/F-3b, **이번 범위 밖**). `check_exit_signal` diff 0.
- **익일청산(개선)**: `_drain_pending_next_day_clear` 가 **09:00:14 → 09:00:05** 로 앞당겨진다.
  개장 직후 변동성 구간의 시장가 청산이 ~9초 빨라지는 것은 슬리피지 관점에서 **유리**하다.
- **수량·사이징**: `calc_buy_quantity`·`_apply_budget_limit`·랏 캡(K·K_ρ) diff 0.
- **돌파 판정의 성립 여부(U2 O-5 에 대한 도메인 답)**: **성립한다.** VB 는
  `prev < target ≤ current` 를 요구하고 `_prev_price` 는 목표가가 선 뒤 첫 틱에서 처음 기록되며
  그 틱은 `prev == 0` 이라 **기록만** 한다. 이 구조는 현행과 **동일**하고 시점만 ~35~55초 뒤로
  밀린다. "이미 목표가 위에서 시작한 종목은 안 산다"(추격 금지)는 성질도 양쪽 동일하다.
  차이는 **목표선 자체가 옳아진다**는 것뿐이다. 트레이더 어법으로: *"돌파를 늦게 보는 게 아니라,
  그동안 잘못 그어 둔 선을 지우고 제대로 긋고 나서 보는 것"* 이다.
- **표본 감소의 대가**: 진입 빈도가 줄면 손익비 개선을 확인하는 데 **더 오래 걸린다**.
  이건 트레이드오프이지 공짜가 아니다. 사용자가 "VB 가 갑자기 안 산다" 를 결함으로 오해하지
  않도록 배포 보고서에 이 문장을 넣을 것.

---

## 8. 반례 / 한계 — 이 설계가 틀릴 수 있는 경우

1. **REST `J` 가 정말 KRX 시가라는 것은 나흘 343/343 일치로 강하게 지지되지만**(확정 일봉 대조),
   KRX 거래소 원천과의 직접 대조는 아직 0회다. KIS 가 통합 피드를 섞기 시작하면 **틀린 수를
   다른 틀린 수로 바꾸는 것**이 된다. `[main_rest_basis_confirmed]` + `stock_master_daily` 3자 대조가
   유일한 방어이며 **매일 돌아야 한다**.
2. **"프리장 시가가 진짜 시가" 인 종목군이 있다.** NXT 프리장에 실질 유동성이 붙은 대형주에서는
   이번 시정이 정상 신호를 지우는 쪽으로 작동할 수 있다. 코호트 분해는 후속 과제.
3. **97% 무릎은 "MAIN 틱을 받은 종목" 의 통계다**(§2). 무송출 코호트가 훨씬 늦게 프린트하면
   R1 성공률이 기대보다 낮고 미해결이 늘어난다 — 그때는 슬로우 라운드가 받아내지만 그날
   오전 진입 기회는 잃는다.
4. **leaf task 단일 실패점.** task 가 안 뜨면 09:05 까지 목표가가 하나도 없다(그 뒤 스케줄러
   백스톱). 완화 = `owns_board` 의 09:05 시간 상한 + D+1 서명 2번 + task 3목록 등재 가드.
5. **`enabled=False` 전략을 스윕하는 결정(D-9)은 "쓰지 않을 값을 만드는" 일이다.** 매매 위험은
   0 이지만 `_targets` 상태와 대시보드 표시가 비활성 전략에도 채워진다. 되돌리려면 대상 판정에
   `config.enabled` 를 한 줄 넣으면 되고, 그 순간 금요일 실측이 사라진다.
6. **레짐 의존.** 갭업이 잦은 장에서는 오염이 목표가를 낮춰 과잉 진입을 만들고, 갭다운 장에서는
   반대로 진입을 막는다. 3영업일 부호 역전이 그 증거다. **"고치면 좋아진다" 를 단일 방향으로
   약속하지 마라.** 확정적으로 말할 수 있는 것은 **"기준가가 설계와 같은 값이 된다"** 까지다.
7. **`[breakout_open_confirm] board=main` 09:00 침묵**(§5-d 8번)은 cycle264 가 방금 고친
   관측기를 다시 조용하게 만드는 것으로 **오해되기 쉽다**. 문서·보고서에 "의도된 침묵이며
   대체 채널은 `[main_rest_basis_round]` 의 `confirmed/total`" 을 명시하지 않으면 다음 조사가
   또 오도된다(cycle264 가 겪은 바로 그 사고).

---

## 9. 열린 질문 (결정하지 않았다 — 사용자/team-leader 몫)

- **O-A. 금요일 실측의 진입 축.** VB·LTV 가 오늘 17:07 부로 둘 다 `enabled=False weight=0` 이다.
  D-9 덕분에 REST 확보·오염 shadow·게이트 동작·부하는 검증되지만 **진입 건수 영향은 검증되지
  않는다.** 비중은 무접촉 6종이자 사용자 결정 항목이므로 이 자문은 제안하지 않는다 — 다만
  D1 의 "금요일 실측" 이 무엇을 가리키는지 확정이 필요하다.
- **O-B. 17:07 비중 변경이 어느 정본에도 기록되지 않았다.** 워크리스트/보고서 어디에도 없다.
  기록 누락인지 의도된 조치인지 확인이 필요하다(자문 범위 밖).
- **O-C. `owns_board` 의 09:05 상한을 둘 것인가, leaf 가 종일 소유할 것인가.** 이 설계는
  상한을 뒀다(단일 실패점 완화). 종일 소유로 하면 스케줄러 백스톱의 5초 WS 폴링 낭비가 사라지지만
  leaf 가 죽으면 회복 경로가 없다.
- **O-D. `[open_source_compare]`(cycle264) 를 언제 은퇴시키는가.** 시정 후 `delta_bp` 는 산술 0 이라
  판독 가치가 `used_src` 결함 탐지로 축소된다. 이 사이클은 **존치**를 택했다(회귀 탐지기 승격).
- **O-E. cycle264 테스트 파일의 소유권.** `test_c7_no_killswitch_param_introduced` 금지 목록 편집과
  `_STRATEGY_PINS` docstring 예고 문장 정정을 cycle272 가 그 파일 안에서 하는지, cycle272 파일로
  옮기는지. 이 자문은 **원 파일 안에서 최소 편집**(금지 이름 1개 제거 + docstring 1문장)을 권한다.
- **O-F. 미해결 종목의 "포기" 시각.** 이 설계는 빠른 창 종료(09:04:35)에 `unresolved` 를 계수하되
  슬로우 라운드로 15:20 까지 계속 시도한다 — 즉 **포기하지 않는다.** "N 라운드 후 완전 포기"
  정책을 원하면 별도 결정이 필요하다.
- **O-G. 후속 F-3 / F-3b.** momentum·LTV 익일 갭률과 kojiro 갭 가드는 여전히 오염된 `[7]` 을 쓴다.
  이번 범위 밖이며 열린 채로 남는다.
- **O-H. P1-7 B(채널 리졸버) 와의 seam.** 이 설계는 `_TRUSTED_MAIN_SOURCES = ("rest",)` 라는
  **한 줄 튜플**을 남겨 뒀다. 채널 분리 후 `"ws_krx"` 를 그 튜플에 추가하면 버려지는 작업이 없다.
  다만 **프로브(H0STCNT0 가 `nxt_false` 종목을 송출하는가)는 여전히 미실시**다.
- **O-I(명세 이견, 고치지 않고 기록).** U3 §0-C 와 cycle264 docstring 은 "cycle265/272 가
  `check_buy_signal` sha 핀 2개를 갱신한다" 고 예고했다. 이 설계는 `source` 기본값을 `"ws"` 로
  두어 **핀 6개를 전부 불변으로 남긴다** — 예고보다 좁은 접촉이며, 예고 문장 쪽을 정정해야 한다.
- **O-J(명세 이견, 기록).** 방향 리포트 §4-a 위험 ②의 "09:30 까지 1.5시간 목표가 구멍" 은 실측상
  09:00→09:35 ≈ **35분**이다(U1 §6-c). 결론(유계 재시도 필수)은 그대로 유효하고 근거는 더 강하다.
- **O-K(명세 이견, 기록).** 방향 리포트 `:217` 의 "실측 ~6.3건/초" 는 출처 미표기이고 U2 실측
  (sleep 0.2 에서 2.9~3.2건/초 · sleep 0 에서 6.7~9.1건/초 순차 상한)과 일치하지 않는다.
  이 설계의 예산은 U2 실측 위에 세웠다.

---

## 10. 후속 검증 권고 (tdd-engineer / tester)

1. **합성 시리즈 3종** — (가) WS 캐시에 프리장 시가가 있고 REST 가 KRX 시가를 주는 종목 →
   목표가는 **REST 값**으로 서고 `[main_rest_basis_confirmed] delta_bp≠0` 1행 (나) WS 캐시 부재 +
   REST 정상 → `ws_src=absent` (다) REST `"0"` → 라운드 3까지 미확정 유지 → 라운드 4에서 확정,
   **그 사이 매수 신호 0**.
2. **LTV `pre_nxt` 무접촉 격자** — 08:00~09:00 틱으로 프리장 목표가가 현행과 byte 동일.
3. **부하 회귀** — 140종목 스윕이 `_rate_limit` 전역 20/s 를 넘지 않고 30초 안에 끝난다
   (가짜 시계 + 호출 카운터 + 1초 슬라이딩 윈도우 최대값).
4. **뮤테이션** — 신뢰 목록 `("rest",)` → `("rest","ws")` · 게이트 조기 반환 순서 뒤집기 ·
   `owns_board` 시각 경계(09:04:59.9 / 09:05:00.0) · `mode=="off"` → `!=` · sleep 삭제 ·
   `mark_confirmed_via_rest` 호출 삭제 — **전부 KILL 되어야 한다.**
5. **관측 폭발기** — 4개 마커 각각의 emit 이 예외를 던져도 확정 결과·라운드 진행·틱 처리가 동일.
6. **8영역 spy** — `handler._parse_tick_prices` 반환 6-튜플 골든 케이스 불변,
   `risk.on_tick` → `check_buy_signal` 호출 인자 byte 동일.
7. **caplog 단언은 WARNING 이상 + 로거명 + prefix 3중 한정**(루트 로거 DEBUG 차이).
8. **커밋 직전** `git status` 재확인 → `_CYCLE228_STRATEGY_CONTENT_SHA` 한시 등록 → 커밋 → 즉시 삭제.
9. **배포는 cycle248 full 모드**(`src/**` 변경) ⇒ 장외 창에서만 push. **20:00~20:15 금지.**

---

*작성 2026-09-10 목 장 종료 후 · 코드·DB·설정 변경 0 · 커밋 0 · 운영 접근 없음(입력 문서 기반).
이 문서는 사용자 결정 D1 을 그대로 구현하는 설계 하나를 확정한 것이며, 대안은 §9 에만 있다.*
