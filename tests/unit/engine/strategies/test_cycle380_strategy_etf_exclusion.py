"""cycle380 Red — 6 전략 `_scan_universe` 의 ETF 제외가 증권그룹코드로 판정된다.

명세 = `_workspace/red/cycle380_etf_group_code.md` §3.

대상 = VB · LTV · donchian · BFB · VCP · kojiro (`stock_master.list_by_filter` 를 쓰는 6 전략 전부).

계약(전략마다 같다):
1. `list_by_filter(..., exclude_etf_like=True)` 로 부른다 — SQL 단계에서 LIMIT **전에** 거른다
   (VB·LTV 는 `max_scan_stocks=100` 으로 먼저 자르므로, 뒤에서 거르면 ETF 가 100칸 일부를 먹는다).
2. 돌아온 행은 한 번 더 `is_etf_like(row["raw"], name)` 로 거른다(방어 겹 — SQL 이 이름 폴백을
   못 본 행, mock 환경). `name` 은 지금처럼 `row["name"] or raw["prdt_abrv_name"]`.
3. 6자리 숫자 규칙(`isdigit`)은 그대로다.

결과(같은 입력 → 같은 출력):
- 새던 ETF(KIWOOM·TIME·1Q, grp=EF) · ETN(grp=EN) · 해외ETF(grp=" fe " 변형) → 빠진다.
- YG PLUS · BNK금융지주(grp=ST) → **들어온다**(새 매수 후보).
- 코드 없는 행 → 기존 이름 규칙(TIGER 200 빠짐 · 삼성전자 들어옴).
- RT/IF/DR → 전과 같이 들어온다(이번 사이클 범위 밖).
- 영숫자 코드 → 전과 같이 빠진다.

## HEAD 기준

전부 RED — (a) 새는 ETF 3종이 통과하고 YG PLUS·BNK 가 빠진다 (b) `exclude_etf_like` 인자 부재.
"""
from __future__ import annotations

import pytest

from src.db.system_config import PriceFilter
from src.engine.strategy_base import StrategyConfig

pytestmark = pytest.mark.unit


def _row(ticker: str, name: str, raw: dict | None) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "excg_dvsn_cd": "02",
        "nxt_tradable": False,
        "is_kospi200": False,
        "is_kosdaq150": False,
        "raw": raw if raw is not None else {},
    }


# list_by_filter 가 돌려준 순서 그대로(= refreshed_at DESC).
_ROWS = [
    _row("153270", "KIWOOM 코스피100", {"scty_grp_id_cd": "EF"}),          # 새던 ETF → 제외
    _row("037270", "YG PLUS", {"scty_grp_id_cd": "ST"}),                    # 오탐 주식 → 포함
    _row("426030", "TIME 미국나스닥100액티브", {"scty_grp_id_cd": "EF"}),   # 새던 ETF → 제외
    _row("138930", "BNK금융지주", {"scty_grp_id_cd": "ST"}),                # 오탐 주식 → 포함
    _row("491610", "1Q CD금리액티브(합성)", {"scty_grp_id_cd": "EF"}),      # 새던 ETF → 제외
    _row("530001", "QV 샘플 상장지수증권", {"scty_grp_id_cd": "EN"}),       # ETN(가상) → 제외
    _row("530002", "글로벌 샘플 인덱스", {"scty_grp_id_cd": " fe "}),       # 해외ETF 변형 → 제외
    _row("102110", "TIGER 200", {}),                                        # 코드 없음·키워드 → 제외
    _row("005930", "삼성전자", {}),                                         # 코드 없음·주식 → 포함
    _row("395400", "SK리츠", {"scty_grp_id_cd": "RT"}),                     # 범위 밖 그룹 → 포함
    _row("088980", "맥쿼리인프라", {"scty_grp_id_cd": "IF"}),               # 범위 밖 그룹 → 포함
    _row("950160", "코오롱티슈진", {"scty_grp_id_cd": "DR"}),               # 범위 밖 그룹 → 포함
    _row("0001A0", "영숫자주식", {"scty_grp_id_cd": "ST"}),                 # isdigit 규칙 → 제외
    _row("069500", "", {"scty_grp_id_cd": "EF", "prdt_abrv_name": "KODEX 200"}),  # 이름 빈 ETF → 제외
    _row("000660", "", {"scty_grp_id_cd": "ST", "prdt_abrv_name": "SK하이닉스"}),  # 이름 빈 주식 → 포함
]

_EXPECTED = ["037270", "138930", "005930", "395400", "088980", "950160", "000660"]
_EXCLUDED_ETF_LIKE = {"153270", "426030", "491610", "530001", "530002", "102110", "069500"}


def _make(strategy_id: str):
    if strategy_id == "volatility_breakout":
        from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy as C
    elif strategy_id == "long_tail_volatility":
        from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy as C
    elif strategy_id == "donchian_swing":
        from src.engine.strategies.donchian_swing import DonchianSwingStrategy as C
    elif strategy_id == "bull_flag_breakout":
        from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy as C
    elif strategy_id == "vcp_breakout":
        from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy as C
    elif strategy_id == "kojiro":
        from src.engine.strategies.kojiro import KojiroStrategy as C
    else:  # pragma: no cover
        raise AssertionError(strategy_id)
    return C(StrategyConfig(strategy_id=strategy_id, name=strategy_id, weight=0.1))


_STRATEGIES = [
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
    "bull_flag_breakout",
    "vcp_breakout",
    "kojiro",
]


@pytest.fixture
def _env(monkeypatch):
    """list_by_filter 가짜(호출 인자 기록) + 가격필터 무력화 + ticker_names 격리."""
    calls: list[dict] = []

    async def _fake_list_by_filter(**kwargs):
        calls.append(dict(kwargs))
        rows = [dict(r, raw=dict(r["raw"])) for r in _ROWS]
        if kwargs.get("return_stage_counts"):
            tickers = [r["ticker"] for r in rows]
            return rows, {
                "union_tickers": list(tickers),
                "mcap_tickers": list(tickers),
                "trade_tickers": list(tickers),
            }
        return rows

    async def _no_price_filter():
        return PriceFilter(min_price=0, max_price=0)

    names: dict[str, str] = {}
    monkeypatch.setattr("src.db.stock_master.list_by_filter", _fake_list_by_filter)
    monkeypatch.setattr("src.db.system_config.get_price_filter", _no_price_filter)
    monkeypatch.setattr("src.engine.scanner.ticker_names", names)
    return calls, names


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_id", _STRATEGIES)
async def test_scan_universe_excludes_by_group_code_and_allows_misnamed_stocks(
    _env, strategy_id
):
    calls, _names = _env
    strat = _make(strategy_id)

    result = await strat._scan_universe()

    assert result == _EXPECTED, (
        f"{strategy_id}: 코드 기준 판정 결과가 다르다\n  got={result}\n  want={_EXPECTED}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_id", _STRATEGIES)
async def test_scan_universe_asks_sql_to_exclude_etf_like_before_limit(_env, strategy_id):
    calls, _names = _env
    strat = _make(strategy_id)

    await strat._scan_universe()

    assert len(calls) == 1, f"{strategy_id}: list_by_filter 호출 {len(calls)}회"
    assert calls[0].get("exclude_etf_like") is True, (
        f"{strategy_id}: list_by_filter(exclude_etf_like=True) 로 불러야 LIMIT 전에 걸러진다 "
        f"(got kwargs={sorted(calls[0])})"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy_id", _STRATEGIES)
async def test_excluded_etf_like_names_not_registered(_env, strategy_id):
    """ticker_names 는 통과 종목만 기록한다(현행) — 빠진 ETF 는 기록되지 않는다."""
    _calls, names = _env
    strat = _make(strategy_id)

    await strat._scan_universe()

    assert _EXCLUDED_ETF_LIKE.isdisjoint(names), (
        f"{strategy_id}: 제외된 ETF 가 ticker_names 에 남았다 {sorted(_EXCLUDED_ETF_LIKE & set(names))}"
    )
    assert names.get("037270") == "YG PLUS"
    assert names.get("138930") == "BNK금융지주"
    assert names.get("000660") == "SK하이닉스"
