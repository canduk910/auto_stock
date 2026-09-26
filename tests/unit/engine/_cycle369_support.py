"""cycle369 Red — 관리종목(51)·단기과열(59) 보유 청산 + 당일 매수 차단 · 공용 지원.

명세 정본 = `_workspace/red/cycle369_status_exit_spec.md`
자문 정본 = `_workspace/domain_consult/cycle369_status_51_59_exit.md`

이 모듈은 테스트가 아니다(파일명이 `test_` 로 시작하지 않는다). cycle369 테스트 파일
여럿이 같은 픽스처·응답 원형·시계를 쓰도록 모아 둔 것이다.

## 새 leaf 에 기대하는 표면 (Red 가 못박는 계약)

``src/engine/status_exit_watch.py`` — 최상위 import 는 표준 라이브러리만.

| 이름 | 계약 |
|---|---|
| ``logger`` | ``logging.getLogger(__name__)`` (= ``src.engine.status_exit_watch``) |
| ``_now_kst()`` | KST aware ``datetime`` — 테스트 시계 seam |
| ``_monotonic()`` | 패스 벽시계 상한(P1 25초) seam — ``open_price_rest._monotonic`` 선례 |
| ``_sleep(seconds)`` | ``task_loop`` 의 대기 seam(코루틴). 루프는 **이것 또는** ``sched._wait_until`` 로만 기다린다 |
| ``classify(output)`` | 순수·never-raise → ``StatusRead`` (속성: ``managed`` ``overheat`` ``halted`` ``flags_missing`` ``price_ok`` ``fetch_fail`` ``iscd_conflict`` ``unknown_values`` ``reason`` ``mang`` ``short_over`` ``iscd``) |
| ``record_read(ticker, read, *, now, src)`` | 레지스트리 갱신(명세 §4.3 규칙 1~4) · never-raise |
| ``observe_fhkst(ticker, output)`` | 관측 훅 진입점 = ``classify`` + ``record_read(now=_now_kst(), src="fetch")`` · never-raise |
| ``buy_gate(ticker, strategy_id) -> bool`` | hot path 순수 조회(명세 §4.6) |
| ``buy_targets(registry) -> list[str]`` | 명세 §4.2 · P1 우선순위 순서 |
| ``pre_pass_time(registry) -> time`` | 08:45 / enabled 전략 ``pre_nxt`` 면 07:59 |
| ``run_pre_pass(sched)`` · ``run_buy_pass(sched, *, kind)`` (``kind`` = ``"p1"``/``"inc"``) · ``run_sell_pass(sched)`` | 코루틴. 조회는 ``src.api.condition.fetch_stock_detail`` 만(함수 안 지연 import) |
| ``task_loop(sched)`` | 코루틴. 계획(P0·P1·INC·청산)은 루프가 들고, 패스는 모듈 전역 이름으로 부른다 |
| ``refresh_modes()`` · ``apply_mode(kind, mode)`` · ``current_modes()`` | ``kind`` ∈ ``"sell"``/``"buy"`` · ``current_modes()`` = ``{"sell": str, "buy": str}`` |
| ``snapshot()`` | ``{"blocks": [...], "armed": [...], "passes": {...}}`` — blocks 원소는 ``ticker`` ``reason`` ``phase`` ``src`` ``skips`` 키를 가진 dict |
| ``reset_state_for_test()`` | 레지스트리·카운터·로그 상한·모드(enforce) 초기화 |

``StrategyBase._status_buy_blocked(ticker)`` · ``Signal.STATUS_EXIT`` ·
``condition._notify_status_observer(ticker, output)`` · ``system_config.{get,set}_status_*``
는 각 테스트 파일 docstring 에 있다.
"""
from __future__ import annotations

import asyncio
import copy
import logging
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

KST = timezone(timedelta(hours=9))
LEAF_LOGGER = "src.engine.status_exit_watch"
DAY = date(2026, 9, 28)        # 월요일 — 영업일
NEXT_DAY = date(2026, 9, 29)

ALL_SIDS: tuple[str, ...] = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
    "bull_flag_breakout",
    "vcp_breakout",
    "kojiro",
)


def leaf():
    """새 leaf 를 불러온다. 없으면 Red 사유를 명시하고 실패한다(skip 금지)."""
    try:
        from src.engine import status_exit_watch
    except ImportError as exc:  # pragma: no cover — Red 단계
        pytest.fail(f"[Red] src/engine/status_exit_watch.py 미존재 — {exc}")
    return status_exit_watch


def kst(h: int, m: int = 0, s: int = 0, *, day: date = DAY) -> datetime:
    return datetime(day.year, day.month, day.day, h, m, s, tzinfo=KST)


# ===========================================================================
# FHKST01010100 응답 원형
#
# 바탕 = `docs/kis/domestic-stock-quote.md` 의 FHKST01010100 응답 예시(키 모양).
# 종목상태 4칸(`iscd_stat_cls_code`·`mang_issu_cls_code`·`short_over_yn`·
# `temp_stop_yn`)의 값은 **자문 §2.3 실측 원문**(2026-09-26 02:1x 라이브 조회)을
# 그대로 옮겼다. 가격 칸은 합성값이다.
# ===========================================================================
_BASE_OUTPUT: dict = {
    "iscd_stat_cls_code": "55",
    "marg_rate": "20.00",
    "rprs_mrkt_kor_name": "KOSDAQ",
    "bstp_kor_isnm": "전기.전자",
    "temp_stop_yn": "N",
    "oprc_rang_cont_yn": "N",
    "clpr_rang_cont_yn": "N",
    "crdt_able_yn": "Y",
    "stck_prpr": "12000",
    "prdy_vrss": "0",
    "prdy_vrss_sign": "3",
    "prdy_ctrt": "0.00",
    "acml_tr_pbmn": "3445701375",
    "acml_vol": "266907",
    "stck_oprc": "11900",
    "stck_hgpr": "12300",
    "stck_lwpr": "11800",
    "stck_mxpr": "15600",
    "stck_llam": "8400",
    "stck_sdpr": "12000",
    "hts_avls": "935",
    "per": "19.67",
    "pbr": "1.72",
    "lstn_stcn": "7280023",
    "vi_cls_code": "N",
    "ovtm_vi_cls_code": "N",
    "invt_caful_yn": "N",
    "mrkt_warn_cls_code": "00",
    "short_over_yn": "N",
    "sltr_yn": "N",
    "mang_issu_cls_code": "N",
}


def fhkst(ticker: str, *, iscd: str | None = "55", mang: str | None = "N",
          short_over: str | None = "N", temp_stop: str | None = "N",
          prpr: str | None = "12000", **extra) -> dict:
    out = copy.deepcopy(_BASE_OUTPUT)
    out.update(
        stck_shrn_iscd=ticker,
        iscd_stat_cls_code=iscd,
        mang_issu_cls_code=mang,
        short_over_yn=short_over,
        temp_stop_yn=temp_stop,
        stck_prpr=prpr,
    )
    out.update(extra)
    return out


def _live_043090() -> dict:
    # 관리종목인데 iscd 가 00 이고 전용 플래그 칸이 None, 현재가 0 — 「모름」이지 「해당 없음」이 아니다
    out = fhkst("043090", iscd="00", mang=None, short_over="N", temp_stop="N", prpr="0")
    for k in ("stck_oprc", "stck_hgpr", "stck_lwpr", "per", "pbr", "hts_avls"):
        out[k] = None
    return out


#: 자문 §2.3 실측 7건 (2026-09-26 02:1x KST, 컨테이너 안 kis_get)
LIVE: dict[str, dict] = {
    "294140": fhkst("294140", iscd="51", mang="Y", short_over="N"),    # 관리
    "016790": fhkst("016790", iscd="58", mang="Y", short_over="N"),    # 관리 + 거래정지(58)
    "043090": _live_043090(),                                         # 관리(칸 None · 현재가 0)
    "005160": fhkst("005160", iscd="59", mang="N", short_over="Y"),    # 단기과열 지정
    "000545": fhkst("000545", iscd="59", mang="N", short_over="Y"),    # 단기과열 연장
    "356680": fhkst("356680", iscd="57", mang="N", short_over="N"),    # 단기과열 **예고**
    "005930": fhkst("005930", iscd="55", mang="N", short_over="N"),    # 정상
}


def managed(ticker: str, **kw) -> dict:
    return fhkst(ticker, iscd="51", mang="Y", short_over="N", **kw)


def overheat(ticker: str, **kw) -> dict:
    return fhkst(ticker, iscd="59", mang="N", short_over="Y", **kw)


def clean(ticker: str, **kw) -> dict:
    return fhkst(ticker, iscd="55", mang="N", short_over="N", **kw)


# ===========================================================================
# 시계
# ===========================================================================
class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def set(self, h: int, m: int = 0, s: int = 0, *, day: date = DAY) -> datetime:
        self.now = kst(h, m, s, day=day)
        return self.now

    def advance(self, secs: float) -> None:
        self.now = self.now + timedelta(seconds=secs)


@pytest.fixture
def clock(monkeypatch):
    lf = leaf()
    c = Clock(kst(10, 0))
    monkeypatch.setattr(lf, "_now_kst", lambda: c.now)
    return c


def frozen_datetime_class(clock: Clock):
    """`datetime.now()`(naive)·`datetime.now(tz)` 둘 다 이 Clock 의 KST 를 따르는 서브클래스.

    freezegun 은 naive 벽시계를 UTC 로 돌려준다(컨테이너는 `TZ=Asia/Seoul`). 전략
    모듈은 naive(`donchian` 시간 가드)와 aware(`momentum`·`VB` 15:20 컷)를 섞어
    쓰므로 모듈의 `datetime` 이름을 이 클래스로 바꿔 두 쪽을 같은 KST 로 맞춘다
    (`tests/unit/engine/test_swing_poll_loop.py::freeze_time` 선례).
    """

    real = datetime

    class _Frozen(real):
        @classmethod
        def now(cls, tz=None):  # noqa: D401
            aware = clock.now
            if tz is None:
                return aware.replace(tzinfo=None)
            return aware.astimezone(tz)

    return _Frozen


def pin_module_clock(monkeypatch, clock: Clock, *modules) -> None:
    frozen = frozen_datetime_class(clock)
    for mod in modules:
        monkeypatch.setattr(mod, "datetime", frozen)


# ===========================================================================
# 조회 스텁 — `src.api.condition.fetch_stock_detail` 교체
# ===========================================================================
class FetchStub:
    def __init__(self) -> None:
        self.table: dict[str, object] = {}
        self.calls: list[str] = []
        self.on_call = None

    async def __call__(self, ticker: str) -> dict:
        self.calls.append(ticker)
        if self.on_call is not None:
            self.on_call(ticker)
        value = self.table.get(ticker)
        if value is None:
            value = clean(ticker)
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            value = value()
        return copy.deepcopy(value)

    def count(self, ticker: str) -> int:
        return self.calls.count(ticker)


@pytest.fixture
def fetch(monkeypatch):
    from src.api import condition

    stub = FetchStub()
    monkeypatch.setattr(condition, "fetch_stock_detail", stub)
    return stub


# ===========================================================================
# 킬스위치 DB 값 — `system_config.get_status_*_raw` 교체
#
# 패스는 시작할 때마다 모드를 DB 에서 다시 읽는다(명세 §5). 그래서 테스트가 모드를
# 바꾸려면 메모리(`apply_mode`)가 아니라 **DB 값**을 바꿔야 한다 — 그래야 운영과 같은
# 경로(SQL UPDATE 가 다음 패스에 반영)를 탄다. 기본 = 두 키 모두 없음(None → enforce).
# ===========================================================================
def set_db_modes(monkeypatch, *, sell=None, buy=None, sell_exc=None, buy_exc=None) -> None:
    from src.db import system_config as sc

    async def _sell():
        if sell_exc is not None:
            raise sell_exc
        return sell

    async def _buy():
        if buy_exc is not None:
            raise buy_exc
        return buy

    monkeypatch.setattr(sc, "get_status_exit_mode_raw", _sell, raising=False)
    monkeypatch.setattr(sc, "get_status_buy_block_mode_raw", _buy, raising=False)


@pytest.fixture
def db_modes(monkeypatch):
    set_db_modes(monkeypatch)

    def _set(**kw):
        set_db_modes(monkeypatch, **kw)

    return _set


# ===========================================================================
# system_logs 캡처 (write_log · safe_write_log)
# ===========================================================================
class LogSink:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str]] = []

    async def write_log(self, level, message, *args, **kwargs):
        self.rows.append((str(level), str(message)))

    async def safe_write_log(self, level, message, *args, **kwargs):
        self.rows.append((str(level), str(message)))

    def lines(self, marker: str) -> list[str]:
        return [m for (_lvl, m) in self.rows if m.startswith(marker)]

    def levels(self, marker: str) -> list[str]:
        return [lvl for (lvl, m) in self.rows if m.startswith(marker)]


@pytest.fixture
def dblog(monkeypatch):
    from src.db import system_logs

    sink = LogSink()
    monkeypatch.setattr(system_logs, "write_log", sink.write_log)
    monkeypatch.setattr(system_logs, "safe_write_log", sink.safe_write_log)
    return sink


# ===========================================================================
# 전략 더블 · 스케줄러 더블
# ===========================================================================
def _strategy_classes():
    from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

    class Holder(StrategyBase):
        """후보 목록이 없는 전략(momentum 모양) — `get_scanned_tickers` 없음."""

        def __init__(self, sid: str, *, enabled: bool = True, boards=("main",)) -> None:
            super().__init__(StrategyConfig(
                strategy_id=sid, name=sid, enabled=enabled, weight=0.1,
                params={"exchange": "KRX", "tradable_boards": list(boards)},
            ))
            self.state.total_investment = 10_000_000

        async def prepare(self) -> None:
            return None

        def check_buy_signal(self, ticker, current_price, open_price):
            return Signal.NONE

        def check_exit_signal(self, ticker, current_price, open_price):
            return Signal.NONE

        def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
            return 0

    class Cand(Holder):
        """후보 목록이 있는 전략 — `get_scanned_tickers` · `_targets` · `_candidates`."""

        def __init__(self, sid: str, *, enabled: bool = True, boards=("main",),
                     scanned=(), targets=(), candidates=()) -> None:
            super().__init__(sid, enabled=enabled, boards=boards)
            self._scanned = list(scanned)
            self._targets = {t: {"target_price": 0} for t in targets}
            self._candidates = {t: {"prev_close": 10000} for t in candidates}

        def get_scanned_tickers(self) -> list[str]:
            return list(self._scanned)

    return Holder, Cand


def holder(sid: str, *, enabled: bool = True, boards=("main",)):
    Holder, _ = _strategy_classes()
    return Holder(sid, enabled=enabled, boards=boards)


def cand(sid: str, *, enabled: bool = True, boards=("main",), scanned=(), targets=(), candidates=()):
    _, Cand = _strategy_classes()
    return Cand(sid, enabled=enabled, boards=boards, scanned=scanned,
                targets=targets, candidates=candidates)


def hold(strategy, ticker: str, *, qty: int = 3, buy_date: date = date(2026, 9, 25), price: int = 12000):
    from src.engine.strategy_base import Position

    strategy.state.positions[ticker] = Position(
        ticker=ticker, buy_price=price, quantity=qty, order_no=f"ORD-{ticker}",
        strategy_id=strategy.strategy_id, buy_date=buy_date,
    )
    return strategy.state.positions[ticker]


class FakeOrderEngine:
    """`execute_sell` 만 가진 주문 엔진 더블 — 호출을 기록한다(`_selling` 은 건드리지 않는다)."""

    def __init__(self) -> None:
        self._selling: set[str] = set()
        self.calls: list[tuple] = []
        self.raise_for: dict[str, BaseException] = {}
        self.entered = asyncio.Event()
        self.hang = False

    async def execute_sell(self, ticker, signal, strategy_id, *args, **kwargs):
        self.calls.append((ticker, signal, strategy_id, args, dict(kwargs)))
        self.entered.set()
        if self.hang:
            await asyncio.Event().wait()
        exc = self.raise_for.get(ticker)
        if exc is not None:
            raise exc

    def fired(self) -> list[tuple[str, str]]:
        return [(c[0], c[2]) for c in self.calls]


def make_sched(*strategies, order_engine=None):
    from src.engine.strategy_registry import StrategyRegistry

    reg = StrategyRegistry()
    for s in strategies:
        reg.register(s)
    return SimpleNamespace(
        registry=reg,
        order_engine=order_engine or FakeOrderEngine(),
        _running=True,
    )


# ===========================================================================
# 로그 판독
# ===========================================================================
async def drain_writes(rounds: int = 20) -> None:
    """fire-and-forget 영속 쓰기(🔁 cycle369 R2 Q3)가 돌 기회를 준다 — 패스가 끝난 **뒤** `system_logs` 행을 볼 때."""
    for _ in range(rounds):
        await asyncio.sleep(0)


def lines(caplog, marker: str, *, min_level: int = logging.INFO, logger: str = LEAF_LOGGER) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == logger and r.levelno >= min_level and r.getMessage().startswith(marker)
    ]


def records(caplog, marker: str, *, min_level: int = logging.INFO, logger: str = LEAF_LOGGER):
    return [
        r for r in caplog.records
        if r.name == logger and r.levelno >= min_level and r.getMessage().startswith(marker)
    ]


def field(line: str, key: str) -> str:
    token = f"{key}="
    for part in line.split():
        if part.startswith(token):
            return part[len(token):]
    raise AssertionError(f"`{key}=` 없음: {line}")


def open_info(caplog) -> None:
    caplog.set_level(logging.INFO, logger=LEAF_LOGGER)


def blocks_by_ticker() -> dict[str, dict]:
    snap = leaf().snapshot()
    return {b["ticker"]: b for b in snap.get("blocks", [])}


def gate(ticker: str, sid: str = "momentum") -> bool:
    return bool(leaf().buy_gate(ticker, sid))


def read_of(output) -> object:
    """`classify` 결과(StatusRead) — record_read 입력용."""
    return leaf().classify(output)


def record(ticker: str, output, when: datetime, src: str = "p1") -> None:
    lf = leaf()
    lf.record_read(ticker, lf.classify(output), now=when, src=src)


#: 청산 창 경계 — 테스트는 상수를 읽지 않고 리터럴로 잰다(창 한 칸 이동 돌연변이 검출)
FIRE_START = time(9, 0, 30)
FIRE_END = time(15, 28, 0)
