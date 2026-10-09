"""cycle416 Red — `GET /api/market/breadth` 라우트 + 날짜 창·캐시·동시성 (R1~R6 · W1~W18).

명세: `_workspace/red/cycle416/breadth_spec.md` §2 · §5.2~§5.5 · §7.3
계약: `_workspace/red/cycle416/breadth_contract.md` 「2. 라우트」

## 봉인하는 계약 (이름·형태가 다르면 FAIL)

`src/routes/market_breadth.py`
  * `router` — `prefix="/api/market"`, GET `/breadth` 하나, `days: int = Query(20, ge=1, le=60)`.
    `src/main.py` 가 `app.include_router(market_breadth.router)` 로 싣는다.
  * `async def compute_breadth(days: int) -> ApiResponse` — 라우트 본문 전체(설정 확인·창 채우기·
    캐시·집계·메시지). 라우트는 이것을 그대로 돌려준다. 이벤트 루프 하나에서 이어지는 동작
    (시한 뒤에도 도는 태스크·동시 요청 합치기·캐시 수명)은 이 함수로 잰다 — TestClient 는 요청마다
    루프를 새로 만들고 닫아 남은 태스크를 죽이기 때문이다.
  * `def reset_state() -> None` — 캐시·진행 중 표·하루 호출 카운터·예산 경고 래치·세마포어를 비운다
    (테스트 seam). 모든 케이스가 시작 전에 부른다.
  * 모듈 상수(테스트가 monkeypatch 한다 — **호출 시점에 모듈 전역을 읽을 것**):
    `_KRX_CONCURRENCY=4` · `_REQUEST_DEADLINE_SECS=45.0` · `_RETRY_DELAY_SECS=1.0` ·
    `_EMPTY_TTL_SECS=600` · `_EMPTY_PERMANENT_AFTER_DAYS=7` · `_DAILY_CALL_BUDGET=1000` ·
    `_CACHE_MAX_ENTRIES=512`
  * KRX 호출은 모듈 참조 `krx.fetch_stk_bydd_trd(ymd)` · `krx.fetch_ksq_bydd_trd(ymd)` 뿐 —
    이 파일이 `src.api.krx.fetch_*` 를 갈아끼운다. 설정은 `system_config.get_krx_open_api_config()`
    (모듈 참조) 를 요청당 1번 읽는다 — 이 파일이 `src.db.system_config.get_krx_open_api_config` 를
    갈아끼운다.
  * 시한은 이벤트 루프 시계(`asyncio.wait`/`asyncio.timeout`)로, 빈 응답 캐시 수명·하루 카운터는
    `time.monotonic()`/`datetime.now(KST)` 로 잰다 — 이 파일은 freezegun `real_asyncio=True` 로
    벽시계만 움직인다.

인증 미들웨어는 `tests/conftest.py::_neutralize_api_auth` 가 중립화한다(R6 만 실제 판정).

RED: 라우트 모듈 부재 → import 실패로 전 케이스 FAIL.
"""

from __future__ import annotations

import ast
import asyncio
import logging
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from freezegun import freeze_time

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
MAIN_SRC = ROOT / "src" / "main.py"
URL = "/api/market/breadth"

NOW = "2026-10-09 11:00:00+09:00"          # 금요일 11:00 KST — 명세 §2.3 예시
W1_EMPTY = {"20261005", "20260925", "20260924"}  # 합성 휴장일
W1_SLOTS = [
    "2026-10-08", "2026-10-07", "2026-10-06", "2026-10-02", "2026-10-01", "2026-09-30",
    "2026-09-29", "2026-09-28", "2026-09-23", "2026-09-22", "2026-09-21", "2026-09-18",
    "2026-09-17", "2026-09-16", "2026-09-15", "2026-09-14", "2026-09-11", "2026-09-10",
    "2026-09-09", "2026-09-08",
]
# 휴장 없는 경우의 20칸 (10-08 → 09-11)
PLAIN_SLOTS_FROM = "2026-09-11"

KEY_MARKER = "KRXKEYMARKERc416notarealkey0000"   # 실제 키 아님 — 노출 탐지용 표지

DATA_KEYS = {
    "asof_kst", "window", "days", "summary", "adr_reference", "source",
    "missing_dates", "empty_dates", "pending_date",
}
WINDOW_KEYS = {"from", "to", "n_days", "requested", "complete", "lookback_from"}
DAY_KEYS = {
    "rows", "traded", "up", "down", "flat", "limit_up", "limit_down", "no_trade",
    "out_of_band", "unparsed", "up_ratio",
}
SUMMARY_KEYS = {"n_days", "up", "down", "flat", "limit_up", "limit_down", "no_trade", "up_ratio", "adr"}
SOURCE = "KRX 공개 API 일별 매매정보(유가증권·코스닥)"

MSG_DISABLED = "KRX 공개 API 가 꺼져 있어 시장 등락 통계를 만들 수 없습니다 — 설정 화면의 외부 연동에서 켤 수 있습니다"
MSG_NO_KEY = "KRX 공개 API 키가 등록돼 있지 않아 시장 등락 통계를 만들 수 없습니다"
MSG_CONFIG_ERR = "KRX 연동 설정을 읽지 못했습니다 — 서버 로그 [market_breadth_error] 확인"
MSG_ALL_FAILED = "KRX 에서 자료를 받지 못했습니다 — 잠시 후 다시 시도하세요"
MSG_BUDGET = "오늘 이 화면의 KRX 조회 한도를 다 썼습니다 — 내일 다시 볼 수 있습니다"


# ─────────────────────────────────────────────────────────────────────────────
# 가짜 KRX 행 — 실제 키 15개, 값은 문자열
# ─────────────────────────────────────────────────────────────────────────────

def _row(close: int, cmp: int, *, vol: str = "1,000", high: int | None = None, low: int | None = None,
         fluc: str | None = None) -> dict[str, str]:
    base = close - cmp
    hi = close if high is None else high
    lo = min(close, base) if low is None else low
    if fluc is None:
        fluc = "0.00" if cmp == 0 else f"{cmp * 100 / base:.2f}"
    return {
        "BAS_DD": "", "ISU_CD": "000000", "ISU_NM": "가짜", "MKT_NM": "", "SECT_TP_NM": "",
        "TDD_CLSPRC": f"{close:,}", "CMPPREVDD_PRC": f"{cmp:,}", "FLUC_RT": fluc,
        "TDD_OPNPRC": f"{lo:,}", "TDD_HGPRC": f"{hi:,}", "TDD_LWPRC": f"{lo:,}",
        "ACC_TRDVOL": vol, "ACC_TRDVAL": "1,000,000", "MKTCAP": "100,000,000", "LIST_SHRS": "10,000",
    }


def _no_trade(close: int) -> dict[str, str]:
    r = _row(close, 0, vol="0")
    r.update({"TDD_OPNPRC": "0", "TDD_HGPRC": "0", "TDD_LWPRC": "0"})
    return r


# 코스피 하루: 상승 2 · 하락 1 · 보합 1 · 거래 없음 1 → rows 5 · traded 4 · up_ratio 0.5
KOSPI_ROWS = [_row(10_100, 100), _row(5_010, 10), _row(9_990, -10), _row(20_000, 0, high=20_050, low=19_950),
              _no_trade(7_000)]
# 코스닥 하루: 상승 1 · 하락 2 → rows 3 · traded 3 · up_ratio 0.3333
KOSDAQ_ROWS = [_row(1_001, 1), _row(999, -1), _row(3_195, -5)]

DAY_KOSPI = dict(rows=5, traded=4, up=2, down=1, flat=1, limit_up=0, limit_down=0, no_trade=1,
                 out_of_band=0, unparsed=0, up_ratio=0.5)
DAY_KOSDAQ = dict(rows=3, traded=3, up=1, down=2, flat=0, limit_up=0, limit_down=0, no_trade=0,
                  out_of_band=0, unparsed=0, up_ratio=0.3333)
DAY_TOTAL = dict(rows=8, traded=7, up=3, down=3, flat=1, limit_up=0, limit_down=0, no_trade=1,
                 out_of_band=0, unparsed=0, up_ratio=0.4286)


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


class FakeKrx:
    """가짜 KRX 두 함수. `(market, ymd)` 별 행동을 표로 받는다.

    empty        : 두 시장 모두 빈 배열인 ymd 집합
    valid_only   : 이 집합 밖 ymd 는 전부 빈 배열(지정 시)
    kospi_empty  : 코스피만 빈 배열인 ymd 집합
    fail         : 언제나 KrxApiError 인 (market, ymd) 집합 — `("*", "*")` = 전부
    fail_times   : (market, ymd) → 처음 n 번만 실패
    slow         : 이 ymd 는 slow_secs 동안 잔다
    delay        : 모든 호출이 이만큼 잔다(동시성 관측용)
    extra_rows   : (market, ymd) → 기본 행에 덧붙일 행
    fail_text    : 예외 메시지(키 노출 탐지용)
    """

    def __init__(self, *, empty=(), valid_only=None, kospi_empty=(), fail=(), fail_times=None,
                 slow=(), slow_secs=0.0, delay=0.0, extra_rows=None, fail_text="가짜 KRX 실패"):
        self.empty = set(empty)
        self.valid_only = None if valid_only is None else set(valid_only)
        self.kospi_empty = set(kospi_empty)
        self.fail = set(fail)
        self.fail_times = dict(fail_times or {})
        self.slow = set(slow)
        self.slow_secs = slow_secs
        self.delay = delay
        self.extra_rows = dict(extra_rows or {})
        self.fail_text = fail_text
        self.calls: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0

    async def stk(self, ymd: str) -> list[dict]:
        return await self._serve("kospi", ymd)

    async def ksq(self, ymd: str) -> list[dict]:
        return await self._serve("kosdaq", ymd)

    async def _serve(self, market: str, ymd: str) -> list[dict]:
        from src.api.krx import KrxApiError

        self.calls.append((market, ymd))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            if ymd in self.slow:
                await asyncio.sleep(self.slow_secs)
            key = (market, ymd)
            if ("*", "*") in self.fail or key in self.fail:
                raise KrxApiError(self.fail_text)
            if self.fail_times.get(key, 0) > 0:
                self.fail_times[key] -= 1
                raise KrxApiError(self.fail_text)
            if ymd in self.empty or (self.valid_only is not None and ymd not in self.valid_only):
                return []
            if market == "kospi" and ymd in self.kospi_empty:
                return []
            base = KOSPI_ROWS if market == "kospi" else KOSDAQ_ROWS
            return [dict(r) for r in base] + [dict(r) for r in self.extra_rows.get(key, [])]
        finally:
            self.active -= 1

    def dates(self) -> set[str]:
        return {ymd for _, ymd in self.calls}


# ─────────────────────────────────────────────────────────────────────────────
# 픽스처 · 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _mbr():
    from src.routes import market_breadth

    return market_breadth


def _cfg(*, enabled: bool = True, key: str = KEY_MARKER):
    from src.models.krx_open_api import KrxOpenApiConfig

    return KrxOpenApiConfig(enabled=enabled, key=key)


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    mbr = _mbr()
    mbr.reset_state()
    monkeypatch.setattr(mbr, "_RETRY_DELAY_SECS", 0.0)
    yield
    mbr.reset_state()


@pytest.fixture
def install(monkeypatch):
    """가짜 KRX + 설정 주입. 반환 = 설정 읽기 AsyncMock."""

    def _install(fake: FakeKrx | None, *, config: Any = None, config_raises: BaseException | None = None):
        from src.api import krx
        from src.db import system_config

        if fake is not None:
            monkeypatch.setattr(krx, "fetch_stk_bydd_trd", fake.stk)
            monkeypatch.setattr(krx, "fetch_ksq_bydd_trd", fake.ksq)
        # 공용 래퍼를 직접 부르면 실제 KRX 로 나간다 — 두 함수만 쓰는 계약
        monkeypatch.setattr(krx, "fetch_krx_open_api", AsyncMock(side_effect=AssertionError("fetch_krx_open_api 직접 호출 금지")))
        cfg = AsyncMock(return_value=config if config is not None else _cfg(), side_effect=config_raises)
        monkeypatch.setattr(system_config, "get_krx_open_api_config", cfg)
        return cfg

    return _install


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(_mbr().router)
    return TestClient(app, raise_server_exceptions=False)


def _warnings(caplog, prefix: str) -> list[str]:
    return [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING and r.getMessage().startswith(prefix)
    ]


def _assert_sane_calls(fake: FakeKrx, today: date, lookback: int) -> None:
    for market, ymd in fake.calls:
        d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))
        assert market in {"kospi", "kosdaq"}
        assert d < today, f"오늘({today}) 이후 조회 금지 — {ymd}"
        assert d.weekday() < 5, f"주말 조회 금지 — {ymd}"
        assert d >= today - timedelta(days=lookback), f"거슬러 보는 한도 밖 — {ymd}"


async def _run(days: int = 20):
    return await _mbr().compute_breadth(days)


# ═════════════════════════════════════════════════════════════════════════════
# R1 — 성공 응답 모양 (명세 §5.4) + W1 날짜 창
# ═════════════════════════════════════════════════════════════════════════════

def test_r1_success_envelope_shape_and_w1_window(install):
    """R1·W1 — HTTP 200 · success=true · data 키 정확 · 날짜 창 = §2.3 예시 그대로 · JSON 정수."""
    fake = FakeKrx(empty=W1_EMPTY)
    install(fake)

    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL)

    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True, body
    assert body["message"] == "최근 20영업일 (2026-09-08~2026-10-08)"
    data = body["data"]
    assert set(data) == DATA_KEYS
    assert set(data["window"]) == WINDOW_KEYS
    assert data["window"] == {
        "from": "2026-09-08", "to": "2026-10-08", "n_days": 20, "requested": 20,
        "complete": True, "lookback_from": "2026-08-30",
    }
    assert [d["date"] for d in data["days"]] == W1_SLOTS, "최신 먼저 · 휴장 3일은 칸을 쓰지 않는다"
    assert data["empty_dates"] == ["2026-10-05", "2026-09-25", "2026-09-24"]
    assert data["missing_dates"] == []
    assert data["pending_date"] is None
    assert data["adr_reference"] == {"oversold": 75, "overheated": 120}
    assert data["source"] == SOURCE
    assert data["asof_kst"].startswith("2026-10-09T11:00:00") and data["asof_kst"].endswith("+09:00")

    for day in data["days"]:
        assert set(day) == {"date", "kospi", "kosdaq", "total"}
        assert day["kospi"] == DAY_KOSPI
        assert day["kosdaq"] == DAY_KOSDAQ
        assert day["total"] == DAY_TOTAL, "합계 up_ratio 는 합계 숫자로 다시 계산(평균 아님)"
        for m in ("kospi", "kosdaq", "total"):
            for k in DAY_KEYS - {"up_ratio"}:
                assert type(day[m][k]) is int, f"{m}.{k} = JSON 정수"

    summ = data["summary"]
    assert set(summ) == {"kospi", "kosdaq", "total"}
    for m in summ:
        assert set(summ[m]) == SUMMARY_KEYS
    assert summ["kospi"] == dict(n_days=20, up=40, down=20, flat=20, limit_up=0, limit_down=0,
                                 no_trade=20, up_ratio=0.5, adr=200.0)
    assert summ["kosdaq"] == dict(n_days=20, up=20, down=40, flat=0, limit_up=0, limit_down=0,
                                  no_trade=0, up_ratio=0.3333, adr=50.0)
    assert summ["total"] == dict(n_days=20, up=60, down=60, flat=20, limit_up=0, limit_down=0,
                                 no_trade=20, up_ratio=0.4286, adr=100.0)

    _assert_sane_calls(fake, date(2026, 10, 9), 40)
    assert ("kospi", "20261009") not in fake.calls, "오늘은 언제나 제외(「전일까지」)"
    # 배치로 부른다 — 첫 배치 22개 평일(칸 20 + 2), 칸 1개 모자라 다음 배치 3개(1 + 2) = 25 날짜 이내
    assert len(fake.dates()) <= 25, f"후보 전체를 한꺼번에 부르지 않는다 — {len(fake.dates())}개 날짜 조회"
    assert Counter(fake.calls).most_common(1)[0][1] == 1, "같은 (시장, 날짜)는 한 번만"


# ═════════════════════════════════════════════════════════════════════════════
# W2~W4 — 「아직 없음」 과 휴장 (명세 §2.2)
# ═════════════════════════════════════════════════════════════════════════════

async def test_w2_latest_weekday_empty_before_10am_is_pending(install):
    """W2 — 목 10-08 09:30, 10-07 빈 배열 → pending_date=10-07 · to=10-06 · empty_dates 에 없음."""
    install(FakeKrx(empty={"20261007"}))
    with freeze_time("2026-10-08 09:30:00+09:00", real_asyncio=True):
        r = await _run()
    assert r.success is True
    d = r.data
    assert d["pending_date"] == "2026-10-07"
    assert d["window"]["to"] == "2026-10-06"
    assert d["days"][0]["date"] == "2026-10-06"
    assert "2026-10-07" not in d["empty_dates"]
    assert d["window"]["n_days"] == 20 and d["window"]["complete"] is True, "pending 은 칸을 쓰지 않는다"


async def test_w3_same_empty_after_10am_is_holiday(install):
    """W3 — W2 를 10:30 에 → pending_date=null · empty_dates=[10-07] (칸 계산은 같다)."""
    install(FakeKrx(empty={"20261007"}))
    with freeze_time("2026-10-08 10:30:00+09:00", real_asyncio=True):
        r = await _run()
    d = r.data
    assert d["pending_date"] is None
    assert d["empty_dates"] == ["2026-10-07"]
    assert d["window"]["to"] == "2026-10-06"
    assert d["window"]["n_days"] == 20


async def test_w4_friday_empty_is_pending_all_weekend(install):
    """W4 — 일 10-11 15:00, 금 10-09 빈 배열 → 월 10-12 10:00 전이라 pending_date=10-09."""
    fake = FakeKrx(empty={"20261009"})
    install(fake)
    with freeze_time("2026-10-11 15:00:00+09:00", real_asyncio=True):
        r = await _run()
    d = r.data
    assert d["pending_date"] == "2026-10-09"
    assert d["window"]["to"] == "2026-10-08"
    assert "2026-10-09" not in d["empty_dates"]
    _assert_sane_calls(fake, date(2026, 10, 11), 40)


# ═════════════════════════════════════════════════════════════════════════════
# W5·W6 — 호출 실패 · 부분 응답은 칸을 쓴다 (명세 §2.1 MISSING)
# ═════════════════════════════════════════════════════════════════════════════

async def test_w5_retry_once_then_missing_takes_a_slot(install, caplog):
    """W5 — 코스닥 09-30 이 두 번 연속 KrxApiError → 재시도 1회(호출 정확히 2번) · missing · 칸 차지 ·
    days 19 · n_days 19 · complete=false · fetch_error WARNING 1줄(예외 클래스 이름만)."""
    caplog.set_level(logging.WARNING)
    fake = FakeKrx(fail={("kosdaq", "20260930")})
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        r = await _run()

    assert r.success is True
    d = r.data
    assert d["missing_dates"] == ["2026-09-30"]
    assert len(d["days"]) == 19
    assert "2026-09-30" not in [x["date"] for x in d["days"]]
    assert d["window"]["from"] == PLAIN_SLOTS_FROM and d["window"]["to"] == "2026-10-08", "빠진 날도 칸이다 — 창이 밀리지 않는다"
    assert d["window"]["n_days"] == 19 and d["window"]["requested"] == 20
    assert d["window"]["complete"] is False
    for m in ("kospi", "kosdaq", "total"):
        assert d["summary"][m]["n_days"] == 19
    calls = Counter(fake.calls)
    assert calls[("kosdaq", "20260930")] == 2, "실패 시 1회 재시도"
    assert calls[("kospi", "20260930")] == 1
    assert r.message == "최근 20영업일 (2026-09-11~2026-10-08) — 1일은 KRX 응답이 없어 비었습니다"

    lines = _warnings(caplog, "[market_breadth_fetch_error] ")
    hits = [ln for ln in lines if "market=kosdaq" in ln and "date=2026-09-30" in ln]
    assert len(hits) == 1, lines
    assert "err=KrxApiError" in hits[0]
    assert "가짜 KRX 실패" not in hits[0], "예외 메시지 본문은 싣지 않는다"


async def test_w5b_failures_are_not_cached(install):
    """W5b — 실패는 캐시하지 않는다: 다음 조회에서 실패한 (시장, 날짜)만 다시 부르고 채운다."""
    fake = FakeKrx(fail_times={("kosdaq", "20260930"): 2})
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        first = await _run()
        assert first.data["missing_dates"] == ["2026-09-30"]
        n = len(fake.calls)
        second = await _run()
    assert fake.calls[n:] == [("kosdaq", "20260930")], "성공한 코스피 09-30 은 캐시에서"
    assert second.data["missing_dates"] == []
    assert second.data["window"]["n_days"] == 20 and second.data["window"]["complete"] is True


async def test_w6_one_market_empty_is_missing_not_holiday(install):
    """W6 — 한 날짜에 코스피만 빈 배열 · 코스닥 유효 → MISSING(부분). 휴장도 거래일도 아니다."""
    install(FakeKrx(kospi_empty={"20261001"}))
    with freeze_time(NOW, real_asyncio=True):
        r = await _run()
    d = r.data
    assert "2026-10-01" in d["missing_dates"]
    assert "2026-10-01" not in d["empty_dates"]
    assert "2026-10-01" not in [x["date"] for x in d["days"]]
    assert d["window"]["from"] == PLAIN_SLOTS_FROM


# ═════════════════════════════════════════════════════════════════════════════
# W7·W8 — 거슬러 보는 한도 (명세 §2.1 L = max(40, 2×days))
# ═════════════════════════════════════════════════════════════════════════════

async def test_w7_only_five_valid_days_within_40(install):
    """W7 — 40일 안에 유효 날짜 5개뿐 → n_days=5 · complete=false · 조회 날짜 전부 today−40 이후."""
    valid = {"20261008", "20261002", "20260921", "20260910", "20260831"}
    fake = FakeKrx(valid_only=valid)
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        r = await _run()
    assert r.success is True
    d = r.data
    assert [x["date"] for x in d["days"]] == ["2026-10-08", "2026-10-02", "2026-09-21", "2026-09-10", "2026-08-31"]
    assert d["window"]["n_days"] == 5 and d["window"]["complete"] is False
    assert d["window"]["lookback_from"] == "2026-08-30"
    assert d["missing_dates"] == []
    assert r.message == "최근 5영업일 (2026-08-31~2026-10-08)"
    _assert_sane_calls(fake, date(2026, 10, 9), 40)


async def test_w8_days_60_looks_back_120_calendar_days(install):
    """W8 — days=60 → 거슬러 보는 한도 120일(06-11). 그보다 앞은 부르지 않는다."""
    valid = {_ymd(date(2026, 10, 9) - timedelta(days=k)) for k in range(1, 50)}
    fake = FakeKrx(valid_only=valid)
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        r = await _run(60)
    d = r.data
    assert d["window"]["lookback_from"] == "2026-06-11"
    assert d["window"]["requested"] == 60 and d["window"]["complete"] is False
    _assert_sane_calls(fake, date(2026, 10, 9), 120)
    assert "20260611" in fake.dates(), "한도일까지 내려가야 한다(40일에서 멈추면 days=60 이 못 채운다)"


# ═════════════════════════════════════════════════════════════════════════════
# W9~W12 — 시한 · 중복 합치기 · 동시성 · 캐시 (명세 §5.3)
# ═════════════════════════════════════════════════════════════════════════════

async def test_w9_deadline_keeps_tasks_running_and_fills_cache(install, monkeypatch):
    """W9 — 전체 시한 초과 → 끝난 날만 days · 나머지 missing. 남은 태스크는 취소하지 않고 끝까지 돌아
    캐시를 채운다 → 다시 부르면 새 호출 0 으로 전부 나온다."""
    mbr = _mbr()
    monkeypatch.setattr(mbr, "_REQUEST_DEADLINE_SECS", 0.3)
    fake = FakeKrx(slow={"20261006"}, slow_secs=0.8)
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        first = await _run()
        assert first.success is True
        assert first.data["missing_dates"] == ["2026-10-06"]
        assert len(first.data["days"]) == 19
        assert first.data["window"]["complete"] is False
        await asyncio.sleep(1.0)  # 응답 뒤에도 느린 두 호출이 끝나 캐시가 찬다
        n = len(fake.calls)
        second = await _run()
    assert len(fake.calls) == n, f"새 호출 0 이어야 한다 — {fake.calls[n:]}"
    assert second.data["missing_dates"] == []
    assert second.data["window"]["n_days"] == 20 and second.data["window"]["complete"] is True
    assert Counter(fake.calls)[("kospi", "20261006")] == 1, "시한 때문에 다시 부르지 않았다(태스크가 살아 있었다)"


async def test_w10_concurrent_requests_share_calls(install):
    """W10 — 같은 요청 둘을 동시에 → 각 (시장, 날짜) 호출 1번."""
    fake = FakeKrx(empty=W1_EMPTY, delay=0.01)
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        a, b = await asyncio.gather(_run(), _run())
    assert a.data["days"] == b.data["days"]
    dup = {k: v for k, v in Counter(fake.calls).items() if v > 1}
    assert dup == {}, f"중복 호출 — {dup}"


async def test_w11_max_concurrency_is_four(install):
    """W11 — 가짜 KRX 안에서 잰 최대 동시 실행 = 4 (전역 세마포어)."""
    fake = FakeKrx(delay=0.01)
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        r = await _run()
    assert r.success is True
    assert fake.max_active == _mbr()._KRX_CONCURRENCY == 4, f"최대 동시 {fake.max_active}"


async def test_w12_cache_ok_forever_recent_empty_600s_old_empty_forever(install):
    """W12 — 유효 날짜는 두 번째 조회에서 새 호출 0 · 최근(7일 안) 빈 날(10-05)은 600초 뒤 다시 부른다 ·
    8일 이전 빈 날(09-24·09-25)은 다시 안 부른다."""
    fake = FakeKrx(empty=W1_EMPTY)
    install(fake)
    with freeze_time(NOW, real_asyncio=True) as frozen:
        await _run()
        n0 = len(fake.calls)
        await _run()
        assert len(fake.calls) == n0, f"캐시 적중 — 새 호출 0 이어야 한다: {fake.calls[n0:]}"

        frozen.tick(timedelta(seconds=599))
        await _run()
        assert len(fake.calls) == n0, "600초 안에는 빈 응답도 캐시에서"

        frozen.tick(timedelta(seconds=2))
        r = await _run()
        new = Counter(fake.calls[n0:])
    assert new == Counter({("kospi", "20261005"): 1, ("kosdaq", "20261005"): 1}), new
    assert r.data["empty_dates"] == ["2026-10-05", "2026-09-25", "2026-09-24"]


async def test_w12b_permanent_empty_is_logged(install, caplog):
    """W12b (검증 결함 suites#1 LOW) — 빈 응답이 "영구(휴장)" 로 굳는 순간을 WARNING 으로 남긴다.
    8일 이전 빈 날(09-24·09-25, 코스피·코스닥)만 — 아직 영구가 아닌 10-05 는 남기지 않는다."""
    caplog.set_level(logging.WARNING)
    fake = FakeKrx(empty=W1_EMPTY)
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        await _run()

    lines = _warnings(caplog, "[market_breadth_permanent_empty] ")
    hit_dates = {ln.split("date=")[1].split(" ")[0] for ln in lines}
    assert hit_dates == {"2026-09-25", "2026-09-24"}, lines
    assert all("market=kospi" in ln or "market=kosdaq" in ln for ln in lines)
    assert not any("2026-10-05" in ln for ln in lines), "아직 영구가 아닌 날은 남기지 않는다"


async def test_w12c_sibling_market_ok_blocks_premature_permanent(install, monkeypatch, caplog):
    """W12c (남은 결함 #1 시정) — 같은 날짜의 다른 시장이 이미 "정상"(rows>0)으로 캐시돼 있으면
    7일 넘은 빈 응답을 영구 "휴장"으로 굳히지 않는다. KRX 가 한쪽 시장만 실패로 빈 OutBlock_1 을
    줬을 가능성을 **추가 호출 없이**(같은 (시장,날짜) 재호출 금지 — R1 "한 번만" 계약) 배제한다.

    코스닥이 먼저 응답하게(지연 0) 두고 코스피만 50ms 늦춰 코스닥의 "정상" 결과가 먼저 캐시되게
    만든다 — 코스피가 저장될 때 이미 코스닥 캐시를 볼 수 있다."""
    caplog.set_level(logging.WARNING)
    install(None)
    from src.api import krx

    target = "20260901"  # NOW(2026-09-10) 기준 9일 전 — candidate_permanent(>7일)
    calls: list[tuple[str, str]] = []

    async def _stk(ymd: str) -> list[dict]:
        calls.append(("kospi", ymd))
        if ymd == target:
            await asyncio.sleep(0.05)  # 코스닥이 먼저 캐시에 "정상" 으로 저장되도록 지연
            return []
        return [dict(r) for r in KOSPI_ROWS]

    async def _ksq(ymd: str) -> list[dict]:
        calls.append(("kosdaq", ymd))
        return [dict(r) for r in KOSDAQ_ROWS]

    monkeypatch.setattr(krx, "fetch_stk_bydd_trd", _stk)
    monkeypatch.setattr(krx, "fetch_ksq_bydd_trd", _ksq)

    with freeze_time("2026-09-10 11:00:00+09:00", real_asyncio=True):
        await _run()

    lines = _warnings(caplog, "[market_breadth_permanent_empty] ")
    assert not any("market=kospi" in ln and "date=2026-09-01" in ln for ln in lines), lines
    assert calls.count(("kospi", target)) == 1, "추가 호출 없이 이미 받은 결과만 본다"


# ═════════════════════════════════════════════════════════════════════════════
# W13·W14 — 실패는 HTTP 200 + success=false (명세 §5.5)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"enabled": False, "key": KEY_MARKER}, MSG_DISABLED),
        ({"enabled": True, "key": ""}, MSG_NO_KEY),
    ],
)
def test_w13_disabled_or_no_key_makes_no_krx_call(install, config, message):
    """W13 — KRX 꺼짐 / 키 빈 값 → success=false · 정해진 문장 · KRX 호출 0."""
    fake = FakeKrx()
    cfg = install(fake, config=_cfg(**config))
    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL)
    assert res.status_code == 200
    body = res.json()
    assert body == {"success": False, "data": None, "message": message}
    assert fake.calls == []
    cfg.assert_awaited_once()


def test_w13b_config_read_error_is_success_false(install, caplog):
    """W13b — 설정 읽기 예외(DB) → success=false · 정해진 문장 · `[market_breadth_error] stage=` WARNING · 500 아님."""
    caplog.set_level(logging.WARNING)
    fake = FakeKrx()
    install(fake, config_raises=RuntimeError("db down — SECRET-c416-detail"))
    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL)
    assert res.status_code == 200
    assert res.json() == {"success": False, "data": None, "message": MSG_CONFIG_ERR}
    assert "SECRET-c416-detail" not in res.text
    assert fake.calls == []
    lines = _warnings(caplog, "[market_breadth_error] ")
    assert any("stage=" in ln and "err=RuntimeError" in ln for ln in lines), lines


def test_w14_all_calls_fail_is_success_false_http_200(install):
    """W14 — 전부 실패 → HTTP 200 · success=false · data=null."""
    fake = FakeKrx(fail={("*", "*")})
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL)
    assert res.status_code == 200
    assert res.json() == {"success": False, "data": None, "message": MSG_ALL_FAILED}
    assert fake.calls, "부르기는 했다"


def test_w14b_no_data_within_lookback_is_success_false(install):
    """W14b — 한도(40일) 안 평일이 전부 빈 응답 → success=false 「최근 40일 안에 KRX 자료가 없습니다」."""
    install(FakeKrx(valid_only=set()))
    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL)
    assert res.status_code == 200
    assert res.json() == {"success": False, "data": None, "message": "최근 40일 안에 KRX 자료가 없습니다"}


def test_w14c_unexpected_exception_never_500(install, monkeypatch, caplog):
    """W14c — 집계 단계 예외도 라우트 밖으로 새지 않는다(500 금지) — WARNING + success=false."""
    caplog.set_level(logging.WARNING)
    from src.engine import market_breadth as leaf

    def _boom(rows):
        raise ValueError("SECRET-agg")

    install(FakeKrx())
    # 라우트는 leaf 를 모듈 참조로 쓴다(계약 2.4) — 여기서 갈아끼운 함수가 실제로 불린다
    monkeypatch.setattr(leaf, "aggregate_rows", _boom)
    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL)
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False and body["data"] is None
    assert "SECRET-agg" not in res.text
    assert _warnings(caplog, "[market_breadth_"), "실패 흔적은 WARNING 으로 남는다"


# ═════════════════════════════════════════════════════════════════════════════
# W15 — 하루 KRX 호출 상한 (명세 §5.3)
# ═════════════════════════════════════════════════════════════════════════════

async def test_w15_daily_budget_caps_calls_warns_once_and_resets_next_day(install, monkeypatch, caplog):
    """W15 — 상한(작게 10) 뒤 새 호출 0 · 남은 칸은 missing · `[market_breadth_budget_exhausted]` 하루 1번 ·
    KST 날짜가 바뀌면 카운터가 새로 시작한다."""
    caplog.set_level(logging.WARNING)
    mbr = _mbr()
    monkeypatch.setattr(mbr, "_DAILY_CALL_BUDGET", 10)
    fake = FakeKrx()
    install(fake)
    with freeze_time(NOW, real_asyncio=True) as frozen:
        r1 = await _run()
        assert len(fake.calls) == 10, f"재시도 포함 실제 호출이 상한에서 멈춘다 — {len(fake.calls)}"
        if r1.success:
            d = r1.data
            assert d["missing_dates"], "상한으로 못 부른 날은 missing"
            assert len(d["days"]) + len(d["missing_dates"]) == 20
            assert d["window"]["complete"] is False
        else:
            assert r1.message == MSG_BUDGET
        await _run()
        assert len(fake.calls) == 10, "같은 날 두 번째 요청도 새 호출 0"
        assert len(_warnings(caplog, "[market_breadth_budget_exhausted]")) == 1, "하루 1번"

        frozen.move_to("2026-10-10 11:00:00+09:00")
        await _run()
    assert len(fake.calls) == 20, "다음 KST 날짜에는 다시 상한까지"
    assert len(_warnings(caplog, "[market_breadth_budget_exhausted]")) == 2


def test_w15b_zero_budget_is_success_false_budget_message(install, monkeypatch):
    """W15b — 한도에 걸려 n_days == 0 → success=false · 한도 문장 · 호출 0."""
    monkeypatch.setattr(_mbr(), "_DAILY_CALL_BUDGET", 0)
    fake = FakeKrx()
    install(fake)
    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL)
    assert res.status_code == 200
    assert res.json() == {"success": False, "data": None, "message": MSG_BUDGET}
    assert fake.calls == []


# ═════════════════════════════════════════════════════════════════════════════
# W16 — 인자 위반만 422
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("params", [{"days": 0}, {"days": 61}, {"days": -1}, {"days": "abc"}, {"days": "1.5"}])
def test_w16_days_out_of_range_is_422_without_side_effects(install, params):
    fake = FakeKrx()
    cfg = install(fake)
    res = _client().get(URL, params=params)
    assert res.status_code == 422
    assert fake.calls == []
    cfg.assert_not_awaited()


@pytest.mark.parametrize("days", [1, 60])
def test_w16b_days_bounds_are_accepted(install, days):
    install(FakeKrx())
    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL, params={"days": days})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["window"]["requested"] == days
    assert len(body["data"]["days"]) == days


# ═════════════════════════════════════════════════════════════════════════════
# W17 — 키 평문 미노출
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("mode", ["ok", "fail", "disabled"])
def test_w17_key_never_in_response_or_logs(install, caplog, mode):
    """W17 — 설정 키에 표지 문자열을 넣고(실제 키 아님) 실패 경로까지 돌려도 응답·로그 어디에도 없다.
    실패 예외 메시지에 표지가 섞여 와도 로그는 예외 클래스 이름만 싣는다."""
    caplog.set_level(logging.DEBUG)
    if mode == "ok":
        install(FakeKrx())
    elif mode == "fail":
        install(FakeKrx(fail={("*", "*")}, fail_text=f"KRX 401 AUTH_KEY={KEY_MARKER}"))
    else:
        install(FakeKrx(), config=_cfg(enabled=False))
    with freeze_time(NOW, real_asyncio=True):
        res = _client().get(URL)
    assert res.status_code == 200
    assert KEY_MARKER not in res.text
    leaked = [r.getMessage() for r in caplog.records if KEY_MARKER in r.getMessage()]
    assert leaked == [], leaked


# ═════════════════════════════════════════════════════════════════════════════
# W18 — 부호 교차확인 (명세 §3.4)
# ═════════════════════════════════════════════════════════════════════════════

async def test_w18_sign_mismatch_warns_without_changing_counts(install, caplog):
    caplog.set_level(logging.WARNING)
    odd = _row(10_100, 100, fluc="-1.00")   # 대비 +100 인데 등락률 음수
    install(FakeKrx(extra_rows={("kospi", "20261008"): [odd]}))
    with freeze_time(NOW, real_asyncio=True):
        r = await _run()
    day = r.data["days"][0]
    assert day["date"] == "2026-10-08"
    assert day["kospi"]["up"] == 3, "분류는 CMPPREVDD_PRC 기준 그대로"
    assert "sign_mismatch" not in day["kospi"], "응답에는 싣지 않는다"
    lines = _warnings(caplog, "[market_breadth_sign_mismatch] ")
    assert len(lines) == 1, lines
    assert "market=kospi" in lines[0] and "date=2026-10-08" in lines[0] and "n=1" in lines[0]


# ═════════════════════════════════════════════════════════════════════════════
# R2~R6 — 메서드 · 등록 · 경로 · 인증
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("method", ["post", "put", "delete"])
def test_r2_only_get_is_allowed(install, method):
    fake = FakeKrx()
    install(fake)
    res = getattr(_client(), method)(URL)
    assert res.status_code == 405
    assert fake.calls == []


def test_r3_router_prefix_not_under_macro():
    """R3 — `/api/macro/` 접두사는 nginx·vite 가 macro 컨테이너로 보낸다 — 그 밑에 두지 않는다."""
    mbr = _mbr()
    assert mbr.router.prefix == "/api/market"
    paths = {getattr(r, "path", "") for r in mbr.router.routes}
    assert paths == {URL}
    assert not URL.startswith("/api/macro")


def test_r4_constants():
    mbr = _mbr()
    assert mbr._KRX_CONCURRENCY == 4
    assert mbr._REQUEST_DEADLINE_SECS == 45.0
    assert mbr._RETRY_DELAY_SECS == 0.0  # autouse 픽스처가 0 으로 바꿔 둔다
    assert mbr._EMPTY_TTL_SECS == 600
    assert mbr._EMPTY_PERMANENT_AFTER_DAYS == 7
    assert mbr._DAILY_CALL_BUDGET == 1_000
    assert mbr._CACHE_MAX_ENTRIES == 512


def test_r4b_retry_delay_default_is_one_second(monkeypatch):
    """R4b — 원래 값(픽스처가 바꾸기 전) = 1.0초. 소스에서 읽는다."""
    src = (ROOT / "src" / "routes" / "market_breadth.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    vals = [
        n.value for n in ast.walk(tree)
        if isinstance(n, (ast.Assign, ast.AnnAssign))
        and any(isinstance(t, ast.Name) and t.id == "_RETRY_DELAY_SECS"
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]))
    ]
    assert len(vals) == 1 and isinstance(vals[0], ast.Constant) and vals[0].value == 1.0


def test_r5_router_registered_in_main_once():
    """R5 — `src/main.py` 에 `market_breadth` import 1 · `include_router(market_breadth.router)` 1 ·
    앱 경로 표에 `/api/market/breadth`."""
    text = MAIN_SRC.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported = [
        alias for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        and node.module == "src.routes" for alias in node.names if alias.name == "market_breadth"
    ]
    assert len(imported) == 1, f"`from src.routes import (…, market_breadth)` {len(imported)}건 (기대 1)"
    includes = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "include_router"
        and "market_breadth" in (ast.get_source_segment(text, n) or "")
    ]
    assert len(includes) == 1, f"`include_router(market_breadth.router)` {len(includes)}건 (기대 1)"

    from src.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert URL in paths, "앱에 `/api/market/breadth` 가 없다 — 프론트는 404 를 받는다"


@pytest.mark.real_api_auth
def test_r6_existing_auth_covers_route(install):
    """R6 — 무키 401 · 운영 키 통과(미들웨어 코드 무변경). lifespan 을 돌리지 않는다(`with` 금지)."""
    from src.config import settings
    from src.main import app

    install(FakeKrx())
    raw = TestClient(app, raise_server_exceptions=False)
    with freeze_time(NOW, real_asyncio=True):
        unauth = raw.get(URL)
        operator = raw.get(URL, headers={"X-API-Key": settings.api_auth_key})
    assert unauth.status_code == 401
    assert operator.status_code == 200, operator.text[:200]
    assert operator.json()["success"] is True
