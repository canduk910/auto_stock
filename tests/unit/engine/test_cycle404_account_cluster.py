"""cycle404 Red — 계좌 묶음 배정 기록(단계 0) 행위 테스트.

명세 = `_workspace/red/cycle404_account_cluster_assign_spec.md` §1~§7 · §9-1~6.
자문 = `_workspace/domain_consult/cycle400_account_risk_budget.md`(R1~R5) ·
`_workspace/domain_consult/cycle404_factor_etf_list.md`(요인 후보안 · 명세 검토).

이 사이클은 **기록만** 한다 — 매수·수량·신호 무변경. 그래서 여기 테스트는 전부
새 leaf `src/engine/account_cluster.py` 의 계산·마커·never-raise 를 본다(배선·import 봉인은
`tests/unit/ast/test_cycle404_ast_account_cluster.py`).

Red 가 정하는 leaf 인터페이스(Green 은 이 이름·모양을 따른다):

- 상수: `WINDOW_RETURNS=120` · `MIN_OVERLAP=100` · `CORR_MIN=0.60` · `MARKET_MARGIN=0.03` ·
  `MARKET_TICKER="069500"` · `CLUSTER_CAP_U=4` · `CLUSTER_CAP_PCT=20.0` · `ACCOUNT_CAP_U=18` ·
  `INITIAL_DELAY_SECS=30` · `RUN_TIMEOUT_SECS=120` · `READ_CONCURRENCY=4` · `CAND_LIST_CAP=40` ·
  `FACTORS` = ((ticker, name), ...) 순서 = 동률 판정 순서 · `_BG_TASKS: set`
- `assign_one(stock_rets, market_rets, factors) -> (label, m, best_name, b)` — 순수.
  `*_rets` = {날짜키: 일간수익률}, `factors` = [(name, rets), ...].
- `assign_all(series, targets) -> (detail, factor_missing) | None` — 순수.
  `series` = {ticker: [(bas_dd, close), ...]}(정렬 무관), `detail` = {ticker: assign_one 결과},
  `factor_missing` = [요인 이름]. 시장 봉 부족이면 `None`.
- `summarize(detail, held, cands, net_asset) -> dict` — 순수.
  `held` = [(ticker, sid, buy_price, quantity)], `cands` = {sid: [ticker, ...]}.
- `async run_boot_assign(registry, net_asset)` — I/O. 모드 읽기 → 일봉 읽기 → 배정 → 마커.
  전체 상한 `RUN_TIMEOUT_SECS` 는 **여기서** 건다. 일봉은 `get_recent_daily` 로만 읽는다.
- `spawn_boot_assign(scheduler_or_registry, net_asset) -> Task | None` — 일반 def,
  task 는 `INITIAL_DELAY_SECS` 기다린 뒤 `run_boot_assign` 을 부른다.
- `get_assignment_map() -> dict[str, str]` — ticker → 라벨(요인 이름·market·independent·missing) 사본.

시계열은 결정적 합성이다(`random.Random(seed)` + 그람-슈미트로 상관을 정확히 맞춘다).
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import math
import random
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_FIXTURE = _ROOT / "tests" / "fixtures" / "cycle404_cluster_closes.json"
_P = "[account_cluster_assign] "
_UNAVAIL = "[account_cluster_unavailable] "
_MODE = "[account_cluster_mode] "
_NOT_CLUSTER = ("market", "independent", "missing")


def _leaf():
    try:
        return importlib.import_module("src.engine.account_cluster")
    except ImportError as exc:  # pragma: no cover - Red
        pytest.fail(f"[Red] src/engine/account_cluster.py 미구현 (cycle404 §7): {exc}")


# ══════════════════════════════════════════════════════════════════════
# 합성 시계열 헬퍼
# ══════════════════════════════════════════════════════════════════════
def _orthonormal(k: int, n: int = 120, seed: int = 7) -> list[list[float]]:
    """평균 0 · 서로 직교 · 길이 1 인 벡터 k 개. 이것들의 선형결합으로 상관을 정확히 맞춘다."""
    rng = random.Random(seed)
    basis: list[list[float]] = []
    for _ in range(k):
        v = [rng.gauss(0.0, 1.0) for _ in range(n)]
        mu = sum(v) / n
        v = [x - mu for x in v]
        for b in basis:
            d = sum(x * y for x, y in zip(v, b))
            v = [x - d * y for x, y in zip(v, b)]
        nrm = math.sqrt(sum(x * x for x in v))
        basis.append([x / nrm for x in v])
    return basis


def _combo(parts: list[tuple[float, list[float]]]) -> list[float]:
    n = len(parts[0][1])
    return [sum(c * v[i] for c, v in parts) for i in range(n)]


def _rets(keys: list, vec: list[float]) -> dict:
    return {k: 0.01 * x for k, x in zip(keys, vec)}


_KEYS = [f"d{i:03d}" for i in range(120)]


def _with(m: float, f: float, z_m, z_f, z_e) -> list[float]:
    """corr(S, M) = m · corr(S, F) = f 를 정확히 만드는 S (M=z_m, F=z_f, 직교)."""
    e = math.sqrt(max(0.0, 1.0 - m * m - f * f))
    return _combo([(m, z_m), (f, z_f), (e, z_e)])


def _weekdays(n: int, start: date = date(2026, 3, 2)) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


_DATES = _weekdays(121)


def _closes(rets: list[float], dates: list[date] = _DATES, base: float = 10_000.0) -> list[tuple]:
    """수익률 120개 → 종가 121개 [(bas_dd, close)] (오래된→최근)."""
    assert len(rets) == len(dates) - 1
    c = [base]
    for r in rets:
        c.append(c[-1] * (1.0 + r))
    return list(zip(dates, c))


def _gauss(seed: int, n: int = 120) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(0.0, 1.0) for _ in range(n)]


def _mix(*parts: tuple[float, list[float]]) -> list[float]:
    return [0.01 * x for x in _combo(list(parts))]


# ══════════════════════════════════════════════════════════════════════
# §2 · §4 상수
# ══════════════════════════════════════════════════════════════════════
def test_c0_constants_when_imported_then_preregistered_values():
    ac = _leaf()
    assert ac.WINDOW_RETURNS == 120
    assert ac.MIN_OVERLAP == 100
    assert ac.CORR_MIN == pytest.approx(0.60)
    assert ac.MARKET_MARGIN == pytest.approx(0.03)
    assert ac.MARKET_TICKER == "069500"
    assert ac.CLUSTER_CAP_U == 4
    assert ac.CLUSTER_CAP_PCT == pytest.approx(20.0)
    assert ac.ACCOUNT_CAP_U == 18
    assert ac.INITIAL_DELAY_SECS == 30
    assert ac.RUN_TIMEOUT_SECS == 120
    assert ac.READ_CONCURRENCY == 4
    assert ac.CAND_LIST_CAP == 40


def test_c0b_factors_when_inspected_then_ordered_unique_10_to_15_without_market_factors():
    ac = _leaf()
    fs = list(ac.FACTORS)
    assert 10 <= len(fs) <= 15, f"요인 10~15개(명세 §3) — 실측 {len(fs)}"
    tickers = [t for t, _ in fs]
    names = [n for _, n in fs]
    assert all(re.fullmatch(r"\d{6}", t) for t in tickers), tickers
    assert len(set(tickers)) == len(tickers) and len(set(names)) == len(names), "중복 요인"
    assert all(re.fullmatch(r"[a-z0-9_]+", n) for n in names), f"마커용 짧은 이름(공백 없음): {names}"
    assert not set(names) & set(_NOT_CLUSTER), "요인 이름이 묶음 아님 라벨과 겹친다"
    assert ac.MARKET_TICKER not in tickers, "069500 은 시장이지 요인이 아니다"
    assert "229200" not in tickers, "코스닥150 은 시장 요인 — 넣으면 「독립」 이 사라진다(자문 §1)"


# ══════════════════════════════════════════════════════════════════════
# §9-1 순수 배정 (a)~(h)
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def basis():
    return _orthonormal(5)


def test_a1a_when_factor_max_above_min_and_margin_then_factor(basis):
    ac = _leaf()
    zm, zf, ze, zg, _ = basis
    s = _rets(_KEYS, _with(0.30, 0.70, zm, zf, ze))
    label, m, bn, b = ac.assign_one(
        s, _rets(_KEYS, zm), [("fa", _rets(_KEYS, zf)), ("fb", _rets(_KEYS, zg))]
    )
    assert label == "fa" and bn == "fa"
    assert m == pytest.approx(0.30, abs=1e-6) and b == pytest.approx(0.70, abs=1e-6)


def test_a1b_when_factor_062_market_060_gap_002_then_independent(basis):
    """요인이 시장보다 높지만 차가 MARKET_MARGIN(0.03) 미만 → 묶음 아님(독립)."""
    ac = _leaf()
    zm, zf, ze, *_ = basis
    s = _rets(_KEYS, _with(0.60, 0.62, zm, zf, ze))
    label, m, bn, b = ac.assign_one(s, _rets(_KEYS, zm), [("fa", _rets(_KEYS, zf))])
    assert label == "independent", (label, m, bn, b)
    assert bn == "fa" and b == pytest.approx(0.62, abs=1e-6)


@pytest.mark.parametrize("n_overlap,expect_missing", [(99, True), (100, False)])
def test_a1c_when_overlap_99_then_missing_100_then_judged(basis, n_overlap, expect_missing):
    ac = _leaf()
    zm, zf, ze, *_ = basis
    full = _rets(_KEYS, _with(0.10, 0.90, zm, zf, ze))
    s = {k: full[k] for k in _KEYS[-n_overlap:]}
    label, *_ = ac.assign_one(s, _rets(_KEYS, zm), [("fa", _rets(_KEYS, zf))])
    if expect_missing:
        assert label == "missing"
    else:
        assert label == "fa", f"교집합 {n_overlap} ≥ MIN_OVERLAP 이면 판정해야 한다 — {label}"


def test_a1d_when_market_max_and_above_min_then_market(basis):
    ac = _leaf()
    zm, zf, ze, *_ = basis
    s = _rets(_KEYS, _with(0.80, 0.50, zm, zf, ze))
    label, m, bn, b = ac.assign_one(s, _rets(_KEYS, zm), [("fa", _rets(_KEYS, zf))])
    assert label == "market" and m == pytest.approx(0.80, abs=1e-6)


def test_a1e_when_market_max_but_below_min_and_factor_below_min_then_independent(basis):
    ac = _leaf()
    zm, zf, ze, *_ = basis
    s = _rets(_KEYS, _with(0.55, 0.50, zm, zf, ze))
    label, *_ = ac.assign_one(s, _rets(_KEYS, zm), [("fa", _rets(_KEYS, zf))])
    assert label == "independent"


@pytest.mark.parametrize("order", [("fa", "fb"), ("fb", "fa")])
def test_a1f_when_two_factors_tie_then_first_in_list(basis, order):
    ac = _leaf()
    zm, zf, ze, *_ = basis
    s = _rets(_KEYS, _with(0.20, 0.75, zm, zf, ze))
    f = _rets(_KEYS, zf)
    label, _, bn, _ = ac.assign_one(s, _rets(_KEYS, zm), [(order[0], dict(f)), (order[1], dict(f))])
    assert label == order[0] and bn == order[0], f"동률은 목록 앞 요인 — {order} → {label}"


def test_a1g_when_factor_has_zero_stdev_then_excluded_and_next_factor_wins(basis):
    ac = _leaf()
    zm, zf, ze, *_ = basis
    s = _rets(_KEYS, _with(0.20, 0.75, zm, zf, ze))
    flat = {k: 0.0 for k in _KEYS}
    label, _, bn, b = ac.assign_one(s, _rets(_KEYS, zm), [("flat", flat), ("fa", _rets(_KEYS, zf))])
    assert label == "fa" and bn == "fa", (label, bn, b)
    label2, _, bn2, b2 = ac.assign_one(s, _rets(_KEYS, zm), [("flat", flat)])
    assert bn2 is None and b2 is None, "표준편차 0 요인뿐이면 b=None"
    assert label2 == "independent"


def test_a1h1_when_dicts_in_different_orders_and_extra_keys_then_aligned_by_date(basis):
    """값의 위치가 아니라 날짜 키로 짝짓는다. 한쪽에만 있는 날은 쓰지 않는다."""
    ac = _leaf()
    zm, zf, ze, *_ = basis
    s_full = _rets(_KEYS, _with(0.10, 0.90, zm, zf, ze))
    rng = random.Random(3)
    s = {k: s_full[k] for k in reversed(_KEYS)}  # 역순 삽입
    for i in range(30):  # 종목에만 있는 날 30개(잡음)
        s[f"x{i:03d}"] = rng.gauss(0.0, 0.05)
    label, m, bn, b = ac.assign_one(s, _rets(_KEYS, zm), [("fa", _rets(_KEYS, zf))])
    assert label == "fa" and b == pytest.approx(0.90, abs=1e-6), (label, m, b)


def test_a1h2_when_stock_misses_a_day_then_gap_return_not_paired_with_one_day_return():
    """거래정지 등으로 하루가 빠진 종목의 「2일치 수익률」 을 요인의 1일 수익률과 짝짓지 않는다
    (명세 §2 「날짜가 빠진 날은 그 쌍의 수익률을 만들지 않는다」 · 자문 cycle404 §5-1).

    빠진 날 다음 재개가 ×10 이라, 그 2일치 수익률이 섞이면 이상치 하나가 상관을 지배해
    요인 배정이 깨진다."""
    ac = _leaf()
    zm, zf, ze, *_ = _orthonormal(3, n=120, seed=11)
    mkt = _closes([0.01 * x for x in zm])
    fac = _closes([0.01 * x for x in zf])
    stock = _closes([0.01 * x for x in _with(0.10, 0.90, zm, zf, ze)])
    gap = 60
    stock = [(d, c * (10.0 if i > gap else 1.0)) for i, (d, c) in enumerate(stock) if i != gap]
    ft, fname = ac.FACTORS[0]
    series = {ac.MARKET_TICKER: mkt, ft: fac, "900001": list(reversed(stock))}
    out = ac.assign_all(series, ["900001"])
    assert out is not None
    detail, _missing = out
    label, m, bn, b = detail["900001"]
    assert label == fname, f"2일치 수익률이 짝지어져 배정이 깨졌다 — {label} m={m} b={b}"


# ══════════════════════════════════════════════════════════════════════
# assign_all — 시장·요인 결측
# ══════════════════════════════════════════════════════════════════════
def _universe(ac, n_bars: int = 121, short_factor: str | None = None, short_market: bool = False):
    """시장 + 전 요인(서로 독립 잡음) 종가."""
    zm = _gauss(1)
    series = {ac.MARKET_TICKER: _closes([0.01 * x for x in zm])}
    if short_market:
        series[ac.MARKET_TICKER] = series[ac.MARKET_TICKER][-50:]
    zfs = {}
    for i, (t, _n) in enumerate(ac.FACTORS):
        z = _gauss(100 + i)
        zfs[t] = z
        series[t] = _closes([0.01 * x for x in z])
        if t == short_factor:
            series[t] = series[t][-50:]
    return series, zm, zfs


def test_a2a_when_market_series_short_then_none():
    ac = _leaf()
    series, *_ = _universe(ac, short_market=True)
    series["900001"] = _closes([0.01 * x for x in _gauss(5)])
    assert ac.assign_all(series, ["900001"]) is None, "시장 봉 부족 → 그날 배정 전체를 건너뛴다(§2)"


def test_a2b_when_factor_series_short_then_reported_and_excluded():
    ac = _leaf()
    ft0, fn0 = ac.FACTORS[0]
    series, zm, zfs = _universe(ac, short_factor=ft0)
    series["900001"] = _closes(_mix((0.9, zfs[ft0]), (0.1, zm), (0.4, _gauss(9))))
    detail, factor_missing = ac.assign_all(series, ["900001"])
    assert fn0 in factor_missing, factor_missing
    assert detail["900001"][0] != fn0, "봉이 부족한 요인에 배정했다"


def test_a2c_when_target_series_absent_then_missing_others_judged():
    ac = _leaf()
    ft0, fn0 = ac.FACTORS[0]
    series, zm, zfs = _universe(ac)
    series["900001"] = _closes(_mix((0.9, zfs[ft0]), (0.1, zm), (0.4, _gauss(9))))
    detail, _ = ac.assign_all(series, ["900001", "900002"])
    assert detail["900002"][0] == "missing"
    assert detail["900001"][0] == fn0


# ══════════════════════════════════════════════════════════════════════
# §9-2 실측 고정 픽스처 (10-03 운영 DB 추출 — `cycle404_extract_fixture.py` 실행 완료)
# ══════════════════════════════════════════════════════════════════════
# 10개 요인 확정(chem·steel 0봉 제외, it 는 semi 와 0.96 중복 제외 — 자문
# `cycle404_factor_etf_list.md` §1) 재검산 결과 자문 cycle400 §3 의 2요인 기준표에서
# 3종목이 이동했다(`_workspace/domain_consult/cycle404_factor_check.py` 재현,
# 자문 §2 「검산 스크립트 출력으로 확정한 표가 바뀌면 이 단언을 그 표로 고친다」):
#   011790(SKC) semi → broker · 417200(LS머트리얼즈) independent → heavy ·
#   121600(나노신소재) independent → battery.
_SEMI5 = ("232140", "101160", "083450", "046890", "425040")
_INDEP4 = ("126340", "217590", "003490", "006120")
_MOVED = {"011790": "broker", "417200": "heavy", "121600": "battery"}


def test_a3_real_fixture_when_assigned_then_reproduces_resolved_table():
    """10-03 실측 재현 — 반도체 5(011790 제외) · 005930 market · 011790/417200/121600
    각각 broker/heavy/battery · 나머지 4 independent(자문 cycle404 §2 재확정표)."""
    if not _FIXTURE.exists():
        pytest.skip("tests/fixtures/cycle404_cluster_closes.json 미추출 — 운영자 실행 대기(자문 cycle404 §3)")
    ac = _leaf()
    fx = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    series = {t: [(str(d), float(c)) for d, c in rows] for t, rows in fx["series"].items()}
    targets = list(_SEMI5) + ["005930"] + list(_INDEP4) + list(_MOVED)
    out = ac.assign_all(series, targets)
    assert out is not None, "실측 픽스처인데 시장 봉 부족 판정"
    detail, _ = out
    labels = {t: detail[t][0] for t in targets}
    semi = {labels[t] for t in _SEMI5}
    assert len(semi) == 1 and not semi & set(_NOT_CLUSTER), f"반도체 5 가 한 요인으로 묶이지 않았다: {labels}"
    assert labels["005930"] == "market", labels
    assert all(labels[t] == "independent" for t in _INDEP4), labels
    for t, expected in _MOVED.items():
        assert labels[t] == expected, f"{t} 기대 {expected} 실측 {labels[t]}: {labels}"


# ══════════════════════════════════════════════════════════════════════
# §9-3 summarize 경계
# ══════════════════════════════════════════════════════════════════════
def _d(label: str, corr: float = 0.8) -> tuple:
    if label in _NOT_CLUSTER:
        return (label, 0.5, None, None)
    return (label, 0.3, label, corr)


@pytest.mark.parametrize("n,expect", [(3, 0), (4, 1)])
def test_a4a_unit_axis_boundary_3u_4u(n, expect):
    ac = _leaf()
    detail = {f"90000{i}": _d("semi") for i in range(n)}
    held = [(t, "kojiro", 1_000, 1) for t in detail]  # 명목 축은 한참 아래
    s = ac.summarize(detail, held, {}, 100_000_000)
    c = s["clusters"]["semi"]
    assert c["held_u"] == n
    assert c["would_block_next"] == expect, f"held_u {n} ≥ {ac.CLUSTER_CAP_U} 판정 — {c}"


@pytest.mark.parametrize("notional,expect", [(199_000, 0), (200_000, 1)])
def test_a4b_notional_axis_boundary_19_9_vs_20_0(notional, expect):
    ac = _leaf()
    detail = {"900001": _d("semi")}
    held = [("900001", "kojiro", notional // 10, 10)]
    s = ac.summarize(detail, held, {}, 1_000_000)
    c = s["clusters"]["semi"]
    assert c["notional"] == notional
    assert c["notional_pct"] == pytest.approx(notional / 1_000_000 * 100)
    assert c["would_block_next"] == expect


@pytest.mark.parametrize("net_asset", [0, -5])
def test_a4c_when_net_asset_not_positive_then_notional_axis_not_judged(net_asset):
    ac = _leaf()
    detail = {"900001": _d("semi")}
    held = [("900001", "kojiro", 1_000_000, 100)]
    c = ac.summarize(detail, held, {}, net_asset)["clusters"]["semi"]
    assert c["notional_pct"] is None
    assert c["would_block_next"] == 0, "분모가 없으면 명목 축은 판정하지 않는다(유닛 1U 라 0)"
    detail4 = {f"90000{i}": _d("semi") for i in range(4)}
    c4 = ac.summarize(detail4, [(t, "kojiro", 1, 1) for t in detail4], {}, net_asset)["clusters"]["semi"]
    assert c4["would_block_next"] == 1, "유닛 축은 분모와 무관하게 판정"


@pytest.mark.parametrize("n,expect", [(17, 0), (18, 1)])
def test_a4d_account_over_boundary_17_18(n, expect):
    ac = _leaf()
    detail = {f"9{i:05d}": _d("independent") for i in range(n)}
    held = [(t, "kojiro", 1_000, 1) for t in detail]
    s = ac.summarize(detail, held, {}, 100_000_000)
    assert s["held_u"] == n
    assert s["account_over"] == expect


def test_a4e_non_clusters_do_not_count_units_and_held_ticker_not_double_counted_as_candidate():
    """market·independent·missing 은 묶음이 아니다(유닛 안 셈 · fail-open).
    보유 종목이 후보에도 있으면 보유가 우선이고 후보에서 뺀다(자문 cycle404 §5-7)."""
    ac = _leaf()
    detail = {
        "900001": _d("semi"), "900002": _d("market"), "900003": _d("independent"),
        "900004": _d("missing"), "900005": _d("semi"), "900006": _d("independent"),
    }
    held = [("900001", "kojiro", 1_000, 1), ("900002", "kojiro", 1_000, 1),
            ("900003", "donchian_swing", 1_000, 1), ("900004", "kojiro", 1_000, 1)]
    cands = {"kojiro": ["900001", "900005", "900006"]}
    s = ac.summarize(detail, held, cands, 100_000_000)
    assert set(s["clusters"]) == {"semi"}, "묶음 아님 라벨이 clusters 에 들어갔다"
    c = s["clusters"]["semi"]
    assert c["held_u"] == 1
    assert {t for t, _sid in c["cand"]} == {"900005"}, f"보유 900001 이 후보로 이중 기록 — {c['cand']}"
    assert s["held_u"] == 4, "계좌 유닛은 보유 종목 전부(묶음 여부 무관)"
    assert [t for t, *_ in s["groups"]["market"]["held"]] == ["900002"]
    assert s["groups"]["independent"]["cand_n"] == 1
    assert s["groups"]["missing"]["cand_n"] == 0


# ══════════════════════════════════════════════════════════════════════
# run_boot_assign — I/O 픽스처
# ══════════════════════════════════════════════════════════════════════
class _Daily:
    """get_recent_daily 대역 — DESC 정렬 행, 호출 기록."""

    def __init__(self, series: dict, *, raise_for: set | None = None, delay: float = 0.0):
        self.series = series
        self.raise_for = raise_for or set()
        self.delay = delay
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, ticker: str, days: int = 20) -> list[dict]:
        self.calls.append((ticker, days))
        if self.delay:
            await asyncio.sleep(self.delay)
        if ticker in self.raise_for:
            raise RuntimeError(f"boom {ticker}")
        rows = self.series.get(ticker, [])
        rows = sorted(rows, key=lambda r: r[0], reverse=True)[:days]
        return [{"ticker": ticker, "bas_dd": d, "close_price": c} for d, c in rows]


def _install(monkeypatch, ac, daily: _Daily, mode=..., mode_raises: bool = False):
    import src.db.pg as pg
    import src.db.stock_master_daily as smd

    monkeypatch.setattr(smd, "get_recent_daily", daily)
    monkeypatch.setattr(ac, "get_recent_daily", daily, raising=False)

    async def _fetch(sql: str, *args):
        if "system_config" in sql:
            if mode_raises:
                raise ConnectionError("db down")
            if mode is ...:
                return []
            return [{"value": mode}]
        if "stock_master_daily" in sql:  # get_recent_daily 를 우회한 직접 조회도 같은 데이터
            return await daily(args[0], args[1] if len(args) > 1 else 20)
        return []

    monkeypatch.setattr(pg, "fetch", _fetch)
    monkeypatch.setattr(ac, "INITIAL_DELAY_SECS", 0, raising=False)


def _strategy(sid: str, enabled: bool, positions: dict, candidates=None):
    st = SimpleNamespace(
        positions={
            t: SimpleNamespace(ticker=t, buy_price=bp, quantity=q, strategy_id=sid)
            for t, (bp, q) in positions.items()
        },
        pending_buys=set(),
        pending_buy_amounts={},
    )
    s = SimpleNamespace(strategy_id=sid, config=SimpleNamespace(enabled=enabled, params={}), state=st)
    if candidates is not None:
        s._candidates = {t: {"atr": 100.0} for t in candidates}
    return s


class _Registry:
    def __init__(self, strategies, *, all_raises: bool = False):
        self._s = strategies
        self._raise = all_raises

    def all(self):
        if self._raise:
            raise RuntimeError("registry boom")
        return list(self._s)

    def enabled(self):
        return [s for s in self._s if s.config.enabled]


def _scenario(ac):
    """kojiro(켜짐): 보유 S1·S2(요인0)·M1(시장)·I1(독립), 후보 C1(요인0)·C2(독립)·S1(보유 중복).
    momentum(켜짐): `_candidates` 없음. vcp_breakout(꺼짐): 보유 S3(요인0), 후보 C3(요인0 — 세지 않음)."""
    ft0, fn0 = ac.FACTORS[0]
    series, zm, zfs = _universe(ac)

    def member(seed):
        return _closes(_mix((0.9, zfs[ft0]), (0.1, zm), (0.4, _gauss(seed))))

    series.update({
        "900011": member(11), "900012": member(12), "900013": member(13),
        "900021": _closes(_mix((0.95, zm), (0.3, _gauss(21)))),
        "900031": _closes(_mix((1.0, _gauss(31)))),
        "900041": member(41),
        "900042": _closes(_mix((1.0, _gauss(42)))),
        "900043": member(43),
    })
    reg = _Registry([
        _strategy("kojiro", True,
                  {"900011": (10_000, 10), "900012": (5_000, 10), "900021": (1_000, 10), "900031": (1_000, 10)},
                  candidates=["900041", "900042", "900011"]),
        _strategy("momentum", True, {}),
        _strategy("vcp_breakout", False, {"900013": (4_900, 10)}, candidates=["900043"]),
    ])
    return reg, series, fn0


def _recs(caplog, prefix: str, level: int = logging.WARNING):
    return [r for r in caplog.records if r.levelno >= level and r.getMessage().startswith(prefix)]


def _tok(line: str, key: str) -> str:
    m = re.search(rf"(?:^|\s){re.escape(key)}=(\S*)", line)
    assert m, f"`{key}=` 토큰 없음: {line}"
    return m.group(1)


# ══════════════════════════════════════════════════════════════════════
# §9-6 마커
# ══════════════════════════════════════════════════════════════════════
async def test_a5a_when_record_then_summary_cluster_group_lines_are_warnings(monkeypatch, caplog):
    ac = _leaf()
    reg, series, fn0 = _scenario(ac)
    daily = _Daily(series)
    _install(monkeypatch, ac, daily)
    caplog.set_level(logging.INFO)

    await ac.run_boot_assign(reg, 1_000_000)

    summ = _recs(caplog, _P + "summary")
    assert len(summ) == 1, [r.getMessage() for r in caplog.records]
    line = summ[0].getMessage()
    assert "기록 전용" in line, "정상 동작인데 WARNING 인 이유를 적는다(§5)"
    assert _tok(line, "mode") == "record"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", _tok(line, "date"))
    assert _tok(line, "phase") == "boot"
    assert _tok(line, "net_asset") == "1000000"
    assert _tok(line, "held_u") == "5", "보유 = 꺼진 전략 포함 전부(900011·12·21·31·13)"
    assert _tok(line, "account_cap_u") == "18"
    assert _tok(line, "account_over") == "0"
    assert _tok(line, "targets") == "7", "보유 5 ∪ 켜진 전략 후보(900041·42, 보유 중복 제외) — 꺼진 전략 후보 제외"
    counts = {k: int(_tok(line, k)) for k in ("clustered", "market", "independent", "missing")}
    assert sum(counts.values()) == 7, counts
    assert counts["market"] == 1 and counts["clustered"] == 4, counts
    src = _tok(line, "cand_sources")
    assert "kojiro:" in src and "momentum" in src, f"후보 없는 전략도 요약에 남긴다(§1): {src}"
    assert "vcp_breakout" not in src, "꺼진 전략 후보는 세지 않는다"
    assert re.fullmatch(r"\d+", _tok(line, "elapsed_ms"))

    cl = _recs(caplog, _P + f"cluster={fn0}")
    assert len(cl) == 1
    cline = cl[0].getMessage()
    assert _tok(cline, "held_u") == "3"
    assert _tok(cline, "cap_u") == "4"
    assert _tok(cline, "notional") == "199000"  # 100,000 + 50,000 + 49,000
    assert _tok(cline, "notional_pct") == "19.9"
    assert _tok(cline, "cap_pct") in ("20", "20.0")
    assert _tok(cline, "would_block_next") == "0"
    held = _tok(cline, "held").split(",")
    assert {h.split(":")[0] for h in held} == {"900011", "900012", "900013"}
    assert all(re.fullmatch(r"\d{6}:[a-z_]+:-?\d\.\d\d", h) for h in held), held
    assert "900013:vcp_breakout:" in _tok(cline, "held")
    assert _tok(cline, "cand") == "900041:kojiro", "보유 900011 이 후보로 이중 기록되면 안 된다"

    mk = _recs(caplog, _P + "group=market")
    ind = _recs(caplog, _P + "group=independent")
    ms = _recs(caplog, _P + "group=missing")
    assert len(mk) == len(ind) == len(ms) == 1
    assert _tok(mk[0].getMessage(), "held") == "900021:kojiro"
    assert _tok(mk[0].getMessage(), "cand_n") == "0"
    assert _tok(ind[0].getMessage(), "held") == "900031:kojiro"
    assert _tok(ind[0].getMessage(), "cand_n") == "1"

    assert not _recs(caplog, _UNAVAIL) and not _recs(caplog, _MODE)
    amap = ac.get_assignment_map()
    assert amap["900011"] == fn0 and amap["900021"] == "market" and amap["900031"] == "independent"


async def test_a5b_when_reads_then_one_read_per_ticker_with_121_bars(monkeypatch, caplog):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    daily = _Daily(series)
    _install(monkeypatch, ac, daily)
    await ac.run_boot_assign(reg, 1_000_000)
    tickers = [t for t, _ in daily.calls]
    assert len(tickers) == len(set(tickers)), f"같은 종목을 두 번 읽었다(요인·시장은 1회 읽어 재사용): {tickers}"
    assert all(n == 121 for _, n in daily.calls), daily.calls
    assert ac.MARKET_TICKER in tickers
    assert {t for t, _ in ac.FACTORS} <= set(tickers)
    assert "900043" not in tickers, "꺼진 전략 후보를 읽었다"


async def test_a5c_when_cluster_has_45_candidates_then_list_capped_40_plus_5(monkeypatch, caplog):
    ac = _leaf()
    ft0, fn0 = ac.FACTORS[0]
    series, zm, zfs = _universe(ac)
    cands = [f"91{i:04d}" for i in range(45)]
    for i, t in enumerate(cands):
        series[t] = _closes(_mix((0.9, zfs[ft0]), (0.1, zm), (0.4, _gauss(500 + i))))
    reg = _Registry([_strategy("kojiro", True, {}, candidates=cands)])
    _install(monkeypatch, ac, _Daily(series))
    await ac.run_boot_assign(reg, 1_000_000)
    cl = _recs(caplog, _P + f"cluster={fn0}")
    assert len(cl) == 1
    raw = _tok(cl[0].getMessage(), "cand")
    m = re.fullmatch(r"(.*)\+(\d+)", raw)
    assert m, f"40개 넘으면 `+N` 꼬리: {raw}"
    shown = [x for x in m.group(1).split(",") if x]
    assert len(shown) == 40 and int(m.group(2)) == 5, raw


async def test_a5d_when_factor_series_short_then_named_in_summary_factor_missing(monkeypatch, caplog):
    ac = _leaf()
    ft1, fn1 = ac.FACTORS[1]
    series, zm, zfs = _universe(ac, short_factor=ft1)
    series["900031"] = _closes(_mix((1.0, _gauss(31))))
    reg = _Registry([_strategy("kojiro", True, {"900031": (1_000, 1)})])
    _install(monkeypatch, ac, _Daily(series))
    await ac.run_boot_assign(reg, 1_000_000)
    line = _recs(caplog, _P + "summary")[0].getMessage()
    assert fn1 in _tok(line, "factor_missing"), line


# ══════════════════════════════════════════════════════════════════════
# §9-4 모드 해석 (§6 표 전 행)
# ══════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "stored,reason",
    [
        (..., None),                       # 키 부재 → record, 경고 없음
        ({"value": "record"}, None),
        ({"value": "shadow"}, "not_implemented"),
        ({"value": "enforce"}, "not_implemented"),
        ({"value": "recrod"}, "invalid"),
        ({"value": 5}, "invalid"),          # 비문자열
        (7, "invalid"),                    # dict 아닌 JSONB
    ],
)
async def test_a6a_mode_when_not_off_then_records_and_warns_only_off_vocabulary(monkeypatch, caplog, stored, reason):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    _install(monkeypatch, ac, _Daily(series), mode=stored)
    caplog.set_level(logging.INFO)
    await ac.run_boot_assign(reg, 1_000_000)
    summ = _recs(caplog, _P + "summary")
    assert len(summ) == 1 and _tok(summ[0].getMessage(), "mode") == "record"
    mode_lines = _recs(caplog, _MODE)
    if reason is None:
        assert mode_lines == [], [r.getMessage() for r in mode_lines]
    else:
        assert len(mode_lines) == 1, [r.getMessage() for r in caplog.records]
        ml = mode_lines[0].getMessage()
        assert _tok(ml, "effective") == "record" and _tok(ml, "reason") == reason, ml
        assert "value=" in ml


async def test_a6b_mode_when_db_read_fails_then_record_with_read_error_warning(monkeypatch, caplog):
    """`_get_string_or_none` 은 DB 예외를 None(=키 부재)으로 삼켜 read_error 를 가를 수 없다 —
    예외를 전파하는 읽기 경로가 필요하다(cycle369 `get_status_exit_mode_raw` 선례)."""
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    _install(monkeypatch, ac, _Daily(series), mode_raises=True)
    await ac.run_boot_assign(reg, 1_000_000)
    ml = _recs(caplog, _MODE)
    assert len(ml) == 1 and _tok(ml[0].getMessage(), "reason") == "read_error", [
        r.getMessage() for r in caplog.records
    ]
    assert _tok(_recs(caplog, _P + "summary")[0].getMessage(), "mode") == "record"


async def test_a6c_mode_off_then_no_reads_no_warnings_one_info(monkeypatch, caplog):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    daily = _Daily(series)
    _install(monkeypatch, ac, daily, mode={"value": "off"})
    caplog.set_level(logging.INFO)
    await ac.run_boot_assign(reg, 1_000_000)
    assert daily.calls == [], "off 면 일봉을 읽지 않는다"
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING and "account_cluster" in r.getMessage()]
    assert warns == [], [r.getMessage() for r in warns]
    info = [r for r in caplog.records if r.levelno == logging.INFO
            and r.getMessage().startswith(_P + "mode=off")]
    assert len(info) == 1 and "skip" in info[0].getMessage()


# ══════════════════════════════════════════════════════════════════════
# §9-5 never-raise
# ══════════════════════════════════════════════════════════════════════
async def test_a7a_when_one_stock_read_raises_then_that_stock_missing_rest_assigned(monkeypatch, caplog):
    ac = _leaf()
    reg, series, fn0 = _scenario(ac)
    _install(monkeypatch, ac, _Daily(series, raise_for={"900012"}))
    await ac.run_boot_assign(reg, 1_000_000)
    amap = ac.get_assignment_map()
    assert amap.get("900012") == "missing"
    assert amap.get("900011") == fn0
    assert len(_recs(caplog, _P + "summary")) == 1
    assert not _recs(caplog, _UNAVAIL)


async def test_a7b_when_market_read_raises_then_unavailable_once_and_empty_map(monkeypatch, caplog):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    _install(monkeypatch, ac, _Daily(series))
    await ac.run_boot_assign(reg, 1_000_000)  # 먼저 정상 1회 — 배정표가 남는다
    assert ac.get_assignment_map()
    caplog.clear()
    _install(monkeypatch, ac, _Daily(series, raise_for={ac.MARKET_TICKER}))
    await ac.run_boot_assign(reg, 1_000_000)
    un = _recs(caplog, _UNAVAIL)
    assert len(un) == 1 and "reason=" in un[0].getMessage()
    assert ac.get_assignment_map() == {}, "시장 결손이면 배정표는 빈 상태(이전 값 잔존 금지)"
    assert not _recs(caplog, _P + "summary")


async def test_a7c_when_market_series_short_then_unavailable(monkeypatch, caplog):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    series[ac.MARKET_TICKER] = series[ac.MARKET_TICKER][-50:]
    _install(monkeypatch, ac, _Daily(series))
    await ac.run_boot_assign(reg, 1_000_000)
    assert len(_recs(caplog, _UNAVAIL)) == 1
    assert ac.get_assignment_map() == {}


@pytest.mark.parametrize("which", ["all_raises", "none"])
async def test_a7d_when_registry_broken_then_unavailable_not_raise(monkeypatch, caplog, which):
    ac = _leaf()
    _reg, series, _ = _scenario(ac)
    _install(monkeypatch, ac, _Daily(series))
    reg = _Registry([], all_raises=True) if which == "all_raises" else None
    await ac.run_boot_assign(reg, 1_000_000)
    un = _recs(caplog, _UNAVAIL)
    assert len(un) == 1, [r.getMessage() for r in caplog.records]


async def test_a7e_when_reads_exceed_timeout_then_unavailable_timeout(monkeypatch, caplog):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    _install(monkeypatch, ac, _Daily(series, delay=0.5))
    monkeypatch.setattr(ac, "RUN_TIMEOUT_SECS", 0.05)
    await asyncio.wait_for(ac.run_boot_assign(reg, 1_000_000), timeout=5)
    un = _recs(caplog, _UNAVAIL)
    assert len(un) == 1 and _tok(un[0].getMessage(), "reason") == "timeout", [
        r.getMessage() for r in caplog.records
    ]


async def test_a7f_reads_are_bounded_by_read_concurrency(monkeypatch):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    inflight = {"now": 0, "peak": 0}
    base = _Daily(series)

    async def daily(ticker, days=20):
        inflight["now"] += 1
        inflight["peak"] = max(inflight["peak"], inflight["now"])
        try:
            await asyncio.sleep(0.005)
            return await base(ticker, days)
        finally:
            inflight["now"] -= 1

    _install(monkeypatch, ac, daily)  # type: ignore[arg-type]
    await ac.run_boot_assign(reg, 1_000_000)
    assert 1 <= inflight["peak"] <= ac.READ_CONCURRENCY, inflight


# ══════════════════════════════════════════════════════════════════════
# spawn — 백그라운드 task 위생 (funnel_capture._BG_TASKS 선례)
# ══════════════════════════════════════════════════════════════════════
async def test_a8a_spawn_when_called_then_task_held_until_done_and_runs(monkeypatch, caplog):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    _install(monkeypatch, ac, _Daily(series))
    sched = SimpleNamespace(registry=reg)
    task = ac.spawn_boot_assign(sched, 1_000_000)
    assert isinstance(task, asyncio.Task)
    assert task in ac._BG_TASKS
    await asyncio.wait_for(task, timeout=5)
    await asyncio.sleep(0)
    assert task not in ac._BG_TASKS, "끝난 task 는 스스로 빠진다"
    assert len(_recs(caplog, _P + "summary")) == 1


async def test_a8b_spawn_with_plain_registry_also_works(monkeypatch, caplog):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    _install(monkeypatch, ac, _Daily(series))
    task = ac.spawn_boot_assign(reg, 1_000_000)
    await asyncio.wait_for(task, timeout=5)
    assert len(_recs(caplog, _P + "summary")) == 1


async def test_a8c_spawn_waits_initial_delay_before_reading(monkeypatch):
    ac = _leaf()
    reg, series, _ = _scenario(ac)
    daily = _Daily(series)
    _install(monkeypatch, ac, daily)
    monkeypatch.setattr(ac, "INITIAL_DELAY_SECS", 0.2)
    task = ac.spawn_boot_assign(reg, 1_000_000)
    await asyncio.sleep(0.05)
    assert daily.calls == [], "부팅 직후 DB 풀 경합을 피해 INITIAL_DELAY_SECS 뒤에 읽는다(§7)"
    await asyncio.wait_for(task, timeout=5)
    assert daily.calls


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_a8d_spawn_without_running_loop_then_never_raises():
    ac = _leaf()
    out = ac.spawn_boot_assign(SimpleNamespace(registry=_Registry([])), 1_000_000)
    assert out is None or isinstance(out, asyncio.Task)
