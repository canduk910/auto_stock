"""cycle297 Red — G3: 주간 회고 조인·집계 leaf (`src/engine/llm_retrospective.py`, 순수 함수).

명세 = `_workspace/red/cycle297_llm_gate_all_strategies_spec.md` §3.5 · §5.1 G3.

**Red 단계 — 테스트만. `src/` 미변경.** Green = backend-dev.

## 왜 순수 함수 leaf 인가

"매수 시점 점수 ↔ 청산 손익" 의 **정의**는 하나여야 한다(자문 §7.3). SQL 뷰로 다시 쓰면
페어링 정의가 둘이 되고(`get_trade_pairs` 는 Python 이다), 라우트 안에 두면 응답 형식이
바뀔 때마다 분석 로직이 함께 흔들린다. 표만 넣어 골든으로 잴 수 있어야 목요일 루틴이
읽는 숫자를 사람이 손으로 검산할 수 있다.

## 계약 (Green 이 맞춰야 할 것)

```
join_pairs_with_evaluations(pairs, eval_rows, *, since_date, until_date) -> list[dict]
aggregate(rows, *, cost_pct) -> dict
```

- **매칭 축은 `(order_no, trade_date)`** — KIS ODNO 는 하루 단위로만 유일하다
  (`llm_buy_evaluations.py:6-8`). 주문번호 단독 매칭은 같은 번호의 **다른 날짜** 평가를
  그 페어에 붙인다(M17).
- **`primary` = 첫 매수 주문의 평가** — 한 페어에 매수가 2건 이상인 사례가 운영 DB 실측
  9건이고, 사이클을 연 판단은 첫 매수다(M18).
- **평가 없는 페어를 버리지 않는다** — 버리면 분모가 사라져 커버리지를 못 잰다(M19).
- **손실 정의는 `profit_rate < cost_pct`** — `get_trade_pairs.profit_loss` 는 수수료·세금
  **전** 값인데 SYSTEM_PROMPT 의 점수 정의는 "수수료·세금 차감 후 플러스 확률" 이다.
  0 을 기준으로 삼으면 두 정의가 어긋난다(M20).

## 양성 대조군

부정 단언("버리지 않는다", "다른 날짜를 붙이지 않는다") 옆에 항상 **붙어야 할 것이 실제로
붙었는지**를 같은 테스트 안에서 잰다 — 함수가 통째로 빈 리스트를 돌려줘도 초록이 되지
않게 한다(cycle292 교훈).
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.unit

_RETRO_MOD = "src.engine.llm_retrospective"

_SINCE = "2026-09-10"
_UNTIL = "2026-09-17"


def _retro():
    """leaf — 부재면 `ModuleNotFoundError`(skip 금지 = 정직한 Red)."""
    return importlib.import_module(_RETRO_MOD)


# ---------------------------------------------------------------------------
# 픽스처 — `get_trade_pairs()` / `list_by_order_nos()` 가 실제로 주는 모양
# ---------------------------------------------------------------------------
def _pair(
    *,
    ticker="005930",
    strategy="donchian_swing",
    buy_date="2026-09-11",
    sell_date="2026-09-15",
    profit_rate=-3.5,
    profit_loss=-12_000.0,
    buy_order_nos=("0000123456",),
    status="closed",
) -> dict:
    return {
        "buy_date": buy_date,
        "buy_time": "09:05:12",
        "sell_date": sell_date,
        "sell_time": "10:31:02",
        "ticker": ticker,
        "ticker_name": "삼성전자",
        "buy_price": 80_000.0,
        "buy_qty": 10,
        "sell_price": 77_200.0,
        "sell_qty": 10,
        "profit_loss": profit_loss,
        "profit_rate": profit_rate,
        "status": status,
        "strategy": strategy,
        "buy_order_nos": list(buy_order_nos),
        "sell_order_nos": ["0000999999"],
        "pair_key": f"{strategy}:{ticker}:{buy_order_nos[0]}" if buy_order_nos else None,
    }


def _ev(
    *,
    order_no="0000123456",
    trade_date="2026-09-11",
    ticker="005930",
    strategy_id="donchian_swing",
    score=42,
    min_score=70,
    would_block=True,
    result="ok",
    reason=None,
    prompt_version="aaaaaaaaaaaa",
    feature_version="bbbbbbbbbbbb",
    model="gpt-5.6-luna",
) -> dict:
    return {
        "order_no": order_no,
        "trade_date": trade_date,
        "account_no": "12345678",
        "account_product": "01",
        "ticker": ticker,
        "strategy_id": strategy_id,
        "mode": "shadow",
        "result": result,
        "reason": reason,
        "score": score,
        "min_score": min_score,
        "would_block": would_block,
        "prompt_version": prompt_version,
        "feature_version": feature_version,
        "model": model,
    }


def _join(pairs, evs, *, since=_SINCE, until=_UNTIL):
    return _retro().join_pairs_with_evaluations(
        pairs, evs, since_date=since, until_date=until
    )


# ===========================================================================
# G3-1 — 창·상태 필터
# ===========================================================================
def test_g3_1a_open_pairs_are_excluded_but_closed_ones_survive() -> None:
    """G3-1 — `status="open"` 페어는 빠지고 `closed` 는 남는다.

    **양성 대조군** = 같은 호출에서 closed 1건이 실제로 남는지 함께 잰다(전부 버리는
    구현이 "open 을 잘 걸렀다" 로 위장하지 못한다).
    """
    rows = _join(
        [_pair(ticker="005930", status="closed"),
         _pair(ticker="000660", status="open", sell_date=None)],
        [],
    )
    assert [r["ticker"] for r in rows] == ["005930"]


def test_g3_1b_sell_date_outside_window_is_excluded() -> None:
    """G3-1 — `sell_date` 가 `[since, until]` 밖이면 빠진다(경계는 **포함**)."""
    rows = _join(
        [
            _pair(ticker="111111", sell_date="2026-09-09"),   # since 하루 전
            _pair(ticker="222222", sell_date="2026-09-10"),   # since 당일 = 포함
            _pair(ticker="333333", sell_date="2026-09-17"),   # until 당일 = 포함
            _pair(ticker="444444", sell_date="2026-09-18"),   # until 하루 뒤
        ],
        [],
    )
    assert sorted(r["ticker"] for r in rows) == ["222222", "333333"]


def test_g3_1c_empty_input_yields_empty_rows_and_zeroed_aggregate() -> None:
    """G3-1 — 빈 입력에 예외가 없다(라우트가 200 + 빈 집계를 돌려주는 근거).

    "이번 주 청산 없음" 은 오류가 아니다 — 404 로 만들면 목요일 루틴이 휴장 주간마다
    장애로 오인한다.
    """
    retro = _retro()
    rows = _join([], [])
    assert rows == []
    agg = retro.aggregate(rows, cost_pct=0.25)
    overall = agg["overall"]
    assert overall["n_pairs"] == 0 and overall["n_scored"] == 0
    assert overall["block_hit_rate"] is None and overall["pass_loss_rate"] is None
    assert agg["by_strategy"] == {} and agg["by_prompt_version"] == {}
    assert len(overall["buckets"]) == 10
    assert sum(b["n"] for b in overall["buckets"]) == 0


# ===========================================================================
# G3-2 — 매칭 축 `(order_no, trade_date)`
# ===========================================================================
def test_g3_2a_same_order_no_on_a_different_date_is_not_attached() -> None:
    """G3-2 (M17) — 같은 주문번호의 **다른 날짜** 평가는 붙지 않는다.

    KIS ODNO 는 하루 단위로만 유일하다. 단독 매칭이면 3주 전 같은 번호의 평가가
    이번 주 페어의 점수로 응답된다 — 회고 전체가 조용히 거짓이 된다.

    **양성 대조군** = 같은 호출에서 올바른 날짜 행(score=42)이 실제로 붙는지 함께 잰다.
    """
    rows = _join(
        [_pair(buy_date="2026-09-11", sell_date="2026-09-15",
               buy_order_nos=("0000123456",))],
        [
            _ev(order_no="0000123456", trade_date="2026-08-20", score=91, would_block=False),
            _ev(order_no="0000123456", trade_date="2026-09-11", score=42, would_block=True),
        ],
    )
    assert len(rows) == 1
    primary = rows[0]["primary"]
    assert primary is not None, "올바른 날짜의 평가가 붙지 않았다"
    assert primary["score"] == 42, f"다른 날짜(08-20, score=91) 평가가 붙었다 — {primary}"
    assert primary["trade_date"] == "2026-09-11"


def test_g3_2b_evaluation_outside_holding_window_is_not_attached() -> None:
    """G3-2 — `buy_date ≤ trade_date ≤ sell_date` 밖의 평가는 붙지 않는다.

    보유 구간 밖 날짜는 이 사이클의 판단이 아니다.
    """
    rows = _join(
        [_pair(buy_date="2026-09-11", sell_date="2026-09-15")],
        [_ev(order_no="0000123456", trade_date="2026-09-16", score=91)],
    )
    assert rows[0]["primary"] is None
    assert rows[0]["evaluations"] == []


# ===========================================================================
# G3-3 — 한 페어 매수 2건 (운영 DB 실측 9건)
# ===========================================================================
def test_g3_3a_two_buy_orders_yield_two_evaluations_and_first_is_primary() -> None:
    """G3-3 (M18) — `evaluations` 2개, `primary` = `buy_order_nos[0]` 의 평가.

    사이클을 연 판단은 첫 매수다. 마지막 매수를 primary 로 삼으면 "첫 진입 판단의 품질"
    이라는 질문 자체가 바뀐다.

    **양성 대조군** = 두 평가가 모두 `evaluations` 에 실려 있는지 함께 잰다(둘 중 하나를
    버리는 구현이 "primary 는 맞다" 로 통과하지 못한다).
    """
    rows = _join(
        [_pair(buy_order_nos=("0000123456", "0000123457"))],
        [
            _ev(order_no="0000123457", score=88, would_block=False),
            _ev(order_no="0000123456", score=42, would_block=True),
        ],
    )
    row = rows[0]
    assert {e["order_no"] for e in row["evaluations"]} == {"0000123456", "0000123457"}
    assert row["primary"]["order_no"] == "0000123456"
    assert row["primary"]["score"] == 42


def test_g3_3b_pair_without_any_evaluation_is_kept_with_null_primary() -> None:
    """G3-3 (M19) — 평가가 없는 페어도 **행으로 남는다**(`primary=None`).

    배포 전 매수·`mode=off` 시절·cap 초과 페어를 빼면 커버리지의 분모가 사라진다 —
    "게이트가 몇 %를 실제로 봤는가" 를 영원히 못 잰다.
    """
    rows = _join([_pair(ticker="005930"), _pair(ticker="000660")],
                 [_ev(order_no="0000123456")])
    assert len(rows) == 2, "평가 없는 페어가 사라졌다"
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["000660"]["primary"] is None
    assert by_ticker["000660"]["evaluations"] == []
    # 양성 대조군 — 있는 쪽은 실제로 붙었다.
    assert by_ticker["005930"]["primary"] is not None


def test_g3_3c_row_shape_carries_the_documented_whitelist_and_no_account() -> None:
    """G3-3 — 행 키 집합이 명세 §3.5-4 그대로이고 `account_no` 는 **어디에도 없다**.

    리포터 스코프 키가 GET 을 경로 무관 통과시키므로(cycle249) 이 표면에 계좌가 실리면
    외부 루틴이 계좌번호를 읽는다. leaf 에서 이미 떨어져야 라우트 실수의 여지가 없다.
    """
    rows = _join([_pair()], [_ev()])
    row = rows[0]
    required = {
        "strategy", "ticker", "ticker_name", "pair_key", "buy_date", "sell_date",
        "buy_price", "sell_price", "buy_qty", "profit_loss", "profit_rate",
        "buy_order_nos", "evaluations", "primary", "outcome",
    }
    assert required <= set(row), f"행 키 부족 — 누락 {sorted(required - set(row))}"
    assert "account_no" not in row
    for ev in row["evaluations"]:
        assert "account_no" not in ev, "평가 행에 계좌번호가 실렸다"
        assert {"order_no", "trade_date", "score", "would_block", "prompt_version"} <= set(ev)


# ===========================================================================
# G3-4 — 손실 정의 `profit_rate < cost_pct`
# ===========================================================================
@pytest.mark.parametrize(
    "profit_rate,cost_pct,expected",
    [
        (0.10, 0.25, "loss"),   # 수수료·세금을 넘지 못했다
        (0.10, 0.00, "win"),    # 비용 0 가정이면 이익
        (0.25, 0.25, "loss"),   # 경계 — 비용과 같으면 남는 게 없다
        (0.26, 0.25, "win"),
        (-3.5, 0.25, "loss"),
        (5.0, 0.25, "win"),
    ],
)
def test_g3_4a_outcome_uses_cost_pct_not_zero(profit_rate, cost_pct, expected) -> None:
    """G3-4 (M20) — 손실 판정이 `profit_rate < cost_pct` 다(`profit_loss < 0` 고정 금지).

    `get_trade_pairs.profit_loss` 는 수수료·세금 **전** 값이고 SYSTEM_PROMPT 의 점수 정의는
    "차감 **후** 플러스 확률" 이다. 0 을 기준으로 삼으면 +0.1% 왕복이 "게이트가 틀렸다" 로
    집계돼 적중률이 구조적으로 낮게 나온다.
    """
    retro = _retro()
    rows = _join([_pair(profit_rate=profit_rate)], [_ev()])
    agg = retro.aggregate(rows, cost_pct=cost_pct)
    assert rows[0]["outcome"] in ("win", "loss")
    n_block_loss = agg["overall"]["n_block_loss"]
    assert (n_block_loss == 1) is (expected == "loss"), (
        f"profit_rate={profit_rate} cost_pct={cost_pct} → n_block_loss={n_block_loss}"
    )


def test_g3_4b_pair_without_profit_rate_is_unscored_not_a_win() -> None:
    """G3-4 — `profit_rate=None`(미실현/이상 데이터)을 이익으로 세지 않는다.

    `None < 0.25` 는 파이썬에서 `TypeError` 이고, 그것을 try 로 삼켜 `win` 으로 떨어뜨리면
    적중률이 조용히 부풀려진다.
    """
    rows = _join([_pair(profit_rate=None, profit_loss=None)], [_ev()])
    assert rows[0]["outcome"] is None
    agg = _retro().aggregate(rows, cost_pct=0.25)
    assert agg["overall"]["n_block_loss"] == 0


# ===========================================================================
# G3-5 — 집계
# ===========================================================================
def _mixed_rows():
    """block 2건(1손실) + pass 2건(1손실) + 평가 없음 1건."""
    pairs = [
        _pair(ticker="000001", buy_order_nos=("A1",), profit_rate=-5.0),
        _pair(ticker="000002", buy_order_nos=("A2",), profit_rate=+8.0),
        _pair(ticker="000003", buy_order_nos=("A3",), profit_rate=-2.0),
        _pair(ticker="000004", buy_order_nos=("A4",), profit_rate=+3.0),
        _pair(ticker="000005", buy_order_nos=("A5",), profit_rate=+1.0),
    ]
    evs = [
        _ev(order_no="A1", score=35, would_block=True),
        _ev(order_no="A2", score=44, would_block=True),
        _ev(order_no="A3", score=75, would_block=False),
        _ev(order_no="A4", score=82, would_block=False),
        # A5 는 평가 없음
    ]
    return _join(pairs, evs)


def test_g3_5a_overall_counts_and_rates() -> None:
    """G3-5 — 표 하나를 손으로 검산한 골든.

    `n_pairs=5` · `n_scored=4` · `n_unscored=1` ·
    block 2 중 손실 1 → `block_hit_rate=0.5` · pass 2 중 손실 1 → `pass_loss_rate=0.5` ·
    `coverage_pass_rate = n_pass / n_scored = 0.5`.
    """
    agg = _retro().aggregate(_mixed_rows(), cost_pct=0.25)
    o = agg["overall"]
    assert (o["n_pairs"], o["n_scored"], o["n_unscored"]) == (5, 4, 1)
    assert (o["n_block"], o["n_block_loss"]) == (2, 1)
    assert (o["n_pass"], o["n_pass_loss"]) == (2, 1)
    assert o["block_hit_rate"] == pytest.approx(0.5)
    assert o["pass_loss_rate"] == pytest.approx(0.5)
    assert o["coverage_pass_rate"] == pytest.approx(0.5)


def test_g3_5b_pnl_sums_split_by_cohort() -> None:
    """G3-5 — `pnl_block_sum`/`pnl_pass_sum` 이 코호트별 실현손익 합.

    `−pnl_block_sum` 이 "enforce 였다면 피했을 금액" 의 1차 근사다(반사실 대체매수 무시).
    """
    pairs = [
        _pair(ticker="000001", buy_order_nos=("A1",), profit_rate=-5.0, profit_loss=-50_000.0),
        _pair(ticker="000002", buy_order_nos=("A2",), profit_rate=+8.0, profit_loss=+80_000.0),
        _pair(ticker="000003", buy_order_nos=("A3",), profit_rate=-2.0, profit_loss=-20_000.0),
    ]
    evs = [
        _ev(order_no="A1", would_block=True, score=30),
        _ev(order_no="A2", would_block=True, score=40),
        _ev(order_no="A3", would_block=False, score=80),
    ]
    o = _retro().aggregate(_join(pairs, evs), cost_pct=0.25)["overall"]
    assert o["pnl_block_sum"] == pytest.approx(30_000.0)
    assert o["pnl_pass_sum"] == pytest.approx(-20_000.0)


def test_g3_5c_avg_score_split_by_outcome() -> None:
    """G3-5 — `avg_score_win`/`avg_score_loss`. 두 분포가 갈리면 게이트가 유효하다."""
    o = _retro().aggregate(_mixed_rows(), cost_pct=0.25)["overall"]
    # 손실 = A1(35) · A3(75) → 55.0 / 이익 = A2(44) · A4(82) → 63.0
    assert o["avg_score_loss"] == pytest.approx(55.0)
    assert o["avg_score_win"] == pytest.approx(63.0)


def test_g3_5d_buckets_are_ten_slots_and_sum_to_n_scored() -> None:
    """G3-5 — 10점 버킷 10칸, `lo=i*10+1`·`hi=i*10+10`, Σn == `n_scored`.

    score ∈ [1,100] 이므로 1-based 가 정확하다(0-based 면 100 이 11번째 칸을 만든다).
    자문 §7.5-B 보정 곡선의 원자료이고, 단조성 검정은 루틴 몫이다.
    """
    o = _retro().aggregate(_mixed_rows(), cost_pct=0.25)["overall"]
    buckets = o["buckets"]
    assert len(buckets) == 10
    assert [(b["lo"], b["hi"]) for b in buckets] == [(i * 10 + 1, i * 10 + 10) for i in range(10)]
    assert sum(b["n"] for b in buckets) == o["n_scored"]
    # A1=35 → (31,40) · A2=44 → (41,50) · A3=75 → (71,80) · A4=82 → (81,90)
    by_lo = {b["lo"]: b for b in buckets}
    assert by_lo[31]["n"] == 1 and by_lo[41]["n"] == 1
    assert by_lo[71]["n"] == 1 and by_lo[81]["n"] == 1
    assert by_lo[31]["loss_rate"] == pytest.approx(1.0)
    assert by_lo[41]["loss_rate"] == pytest.approx(0.0)


def test_g3_5e_boundary_scores_land_in_the_right_bucket() -> None:
    """G3-5 — 경계 점수(1·10·70·100)가 기대 칸에 들어간다."""
    retro = _retro()
    pairs = [_pair(ticker=f"{i:06d}", buy_order_nos=(f"B{i}",), profit_rate=-1.0)
             for i in range(4)]
    evs = [_ev(order_no=f"B{i}", score=s, would_block=True)
           for i, s in enumerate((1, 10, 70, 100))]
    buckets = retro.aggregate(_join(pairs, evs), cost_pct=0.25)["overall"]["buckets"]
    by_lo = {b["lo"]: b["n"] for b in buckets}
    assert by_lo[1] == 2      # 1 · 10
    assert by_lo[61] == 1     # 70
    assert by_lo[91] == 1     # 100


def test_g3_5f_grouped_by_strategy_and_by_prompt_version() -> None:
    """G3-5 — `by_strategy[sid]` · `by_prompt_version["<sid>|<pv>"]`.

    판정 단위는 **(전략, prompt_version)** 이다(명세 §3.6) — 같은 전략이라도 컨텍스트
    문구를 고치면 다른 표본이다. JSON 키는 문자열이어야 하므로 `|` 로 잇는다(두 값 어디에도
    `|` 가 나타나지 않는다 — sid 는 식별자, pv 는 sha256 앞 12자).
    """
    pairs = [
        _pair(ticker="000001", strategy="donchian_swing", buy_order_nos=("A1",), profit_rate=-5.0),
        _pair(ticker="000002", strategy="kojiro", buy_order_nos=("A2",), profit_rate=+8.0),
    ]
    evs = [
        _ev(order_no="A1", strategy_id="donchian_swing", prompt_version="pv0000000001",
            would_block=True, score=30),
        _ev(order_no="A2", strategy_id="kojiro", prompt_version="pv0000000002",
            would_block=False, score=80),
    ]
    agg = _retro().aggregate(_join(pairs, evs), cost_pct=0.25)
    assert set(agg["by_strategy"]) == {"donchian_swing", "kojiro"}
    assert agg["by_strategy"]["donchian_swing"]["n_block"] == 1
    assert set(agg["by_prompt_version"]) == {
        "donchian_swing|pv0000000001", "kojiro|pv0000000002",
    }
    assert agg["by_prompt_version"]["donchian_swing|pv0000000001"]["n_scored"] == 1


def test_g3_5g_failed_evaluations_count_as_unscored_not_as_pass() -> None:
    """G3-5 — `result != "ok"`(score=None) 행은 `n_unscored` 다.

    실패를 `would_block=False` 코호트에 넣으면 "통과시킨 것의 손실률" 이 배관 장애로
    오염된다 — 그 축은 `[llm_buy_score_failed]` 비율이 따로 잰다(명세 §3.6 배관 축).
    """
    rows = _join(
        [_pair(buy_order_nos=("A1",), profit_rate=-5.0)],
        [_ev(order_no="A1", result="failed", reason="no_bars",
             score=None, would_block=None)],
    )
    o = _retro().aggregate(rows, cost_pct=0.25)["overall"]
    assert (o["n_pairs"], o["n_scored"], o["n_unscored"]) == (1, 0, 1)
    assert o["n_pass"] == 0 and o["n_block"] == 0


def test_g3_5h_aggregate_is_read_only_on_its_input() -> None:
    """G3-5 — `aggregate` 가 입력 행을 변형하지 않는다(순수 함수 계약).

    라우트가 같은 리스트를 응답 본문에도 싣기 때문에, 집계가 행을 건드리면 응답이
    조용히 오염된다.
    """
    import copy

    rows = _mixed_rows()
    before = copy.deepcopy(rows)
    _retro().aggregate(rows, cost_pct=0.25)
    assert rows == before, "aggregate 가 입력을 변형했다"


# ===========================================================================
# G3-7 ~ G3-10 — 검증 후속(2026-09-17)
# ===========================================================================
# 뮤테이션 렌즈가 ESCAPED 로 잡은 네 축을 닫는다.
#   R7  행 `outcome` 을 항상 "win" 으로 → 23건 전부 통과(이 필드는 무가드였다)
#   R6  `_accumulate` 의 `result == "ok"` 삭제 → 운영 데이터에서 동치라 통과
#   R14 `status == "closed"` 필터 삭제 → `sell_date=None` 이 대신 걸러 통과
#   §3.5-3 `trade_date == buy_date` 우선 규칙이 구현되지 않음(입력 순서 의존)


def test_g3_7_row_outcome_uses_the_same_definition_as_the_aggregate() -> None:
    """G3-7 — 행 `outcome` 과 집계 분류가 **모든 행에서 일치**한다(정의는 하나다).

    `0 < profit_rate <= cost_pct` 구간이 유일한 갈림길이다 — 0 기준 부호로 매기면
    표에서는 `win` 인데 집계는 손실로 센다. **양성 대조군** = 같은 표를 `cost_pct=0` 으로
    다시 돌려 그때는 `win` 이 되는지도 잰다(항상 `loss` 를 돌려주는 구현 차단).
    """
    retro = _retro()
    pairs = [
        _pair(ticker="000001", buy_order_nos=("A1",), profit_rate=0.10, profit_loss=800.0),
        _pair(ticker="000002", buy_order_nos=("A2",), profit_rate=5.0, profit_loss=40_000.0),
        _pair(ticker="000003", buy_order_nos=("A3",), profit_rate=-3.5, profit_loss=-28_000.0),
    ]
    evs = [_ev(order_no="A1"), _ev(order_no="A2"), _ev(order_no="A3")]

    rows = retro.join_pairs_with_evaluations(
        pairs, evs, since_date=_SINCE, until_date=_UNTIL, cost_pct=0.25,
    )
    assert [r["outcome"] for r in rows] == ["loss", "win", "loss"]
    agg = retro.aggregate(rows, cost_pct=0.25)
    assert agg["overall"]["n_block_loss"] == 2, "집계가 행 표와 다른 정의를 쓴다"

    rows0 = retro.join_pairs_with_evaluations(
        pairs, evs, since_date=_SINCE, until_date=_UNTIL, cost_pct=0.0,
    )
    assert [r["outcome"] for r in rows0] == ["win", "win", "loss"], (
        "cost_pct 를 낮췄는데 행 판정이 안 바뀐다 — 인자가 안 쓰인다"
    )


def test_g3_8_primary_prefers_the_evaluation_stamped_on_the_buy_date() -> None:
    """G3-8 (§3.5-3) — 같은 주문번호가 보유 구간 안 여러 날짜에 있으면 **매수일** 행을 고른다.

    호출자(`list_by_order_nos`)가 `ORDER BY trade_date DESC` 라 입력 순서에 맡기면
    **가장 늦은 날짜**가 primary 가 된다. 사이클을 연 판단은 첫 매수일의 평가다.

    **양성 대조군** = 두 평가가 `evaluations` 에는 **둘 다** 실린다(노출은 하되 집계 기준만 고른다).
    """
    rows = _join(
        [_pair(buy_date="2026-09-11", sell_date="2026-09-15", buy_order_nos=("A1",))],
        # DESC 순서 그대로 — 늦은 날짜가 먼저 들어온다
        [_ev(order_no="A1", trade_date="2026-09-14", score=90),
         _ev(order_no="A1", trade_date="2026-09-11", score=42)],
    )
    assert len(rows) == 1
    assert len(rows[0]["evaluations"]) == 2, "양성 대조군 실패 — 두 평가가 다 실려야 한다"
    assert rows[0]["primary"]["trade_date"] == "2026-09-11", (
        f"primary trade_date={rows[0]['primary']['trade_date']} — 매수일 행을 골라야 한다"
    )
    assert rows[0]["primary"]["score"] == 42


def test_g3_9_failed_evaluations_are_never_scored_even_with_a_score_value() -> None:
    """G3-9 (R6) — `result != "ok"` 인 평가는 점수가 붙어 있어도 **미채점**이다.

    현재 leaf 는 실패 행에 항상 `score=None` 을 쓰므로 운영 데이터에서는 `result` 검사가
    동치다 — 그래서 그 조건을 지우는 뮤테이션이 통과했다. 나중에 실패 행에 부분 점수를
    남기는 변경이 오면 그 순간 적중률 분모가 오염된다.
    """
    retro = _retro()
    rows = _join(
        [_pair(buy_order_nos=("A1",))],
        [_ev(order_no="A1", result="failed", reason="timeout", score=17, would_block=True)],
    )
    agg = retro.aggregate(rows, cost_pct=0.25)
    assert agg["overall"]["n_pairs"] == 1
    assert agg["overall"]["n_scored"] == 0, "실패 평가가 채점 표본에 들어갔다"
    assert agg["overall"]["n_unscored"] == 1
    assert agg["overall"]["n_block"] == 0


def test_g3_10_open_pairs_are_excluded_even_when_sell_date_is_filled() -> None:
    """G3-10 (R14) — `status="open"` 은 `sell_date` 가 채워져 있어도 제외된다.

    현재 `get_trade_pairs` 는 open 페어에 `sell_date=None` 을 넣으므로 그 널 검사가
    상태 필터를 대신한다 — 그래서 `status` 조건을 지워도 통과했다. 부분 청산 표기 등으로
    open 페어에 날짜가 붙는 날 미실현 손익이 적중률에 섞인다.

    **양성 대조군** = 같은 호출의 closed 1건은 남는다.
    """
    rows = _join(
        [_pair(ticker="005930", status="closed"),
         _pair(ticker="000660", status="open", sell_date="2026-09-15")],
        [],
    )
    assert [r["ticker"] for r in rows] == ["005930"], (
        f"open 페어가 남았다 — {[r['ticker'] for r in rows]}"
    )
