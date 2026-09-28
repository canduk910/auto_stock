"""cycle386 Red — 부팅 prepare 직전 「잠정 봉」 확정 leaf (`src/engine/daily_bar_finalize.py`).

명세 = `_workspace/domain_consult/cycle386_daily_close_after_market.md` §8 (8-3 판정 · 8-4 흐름 ·
8-6 실패 · 8-9 G2/G3/G4). 사용자 결정 2026-09-28 「지금 최우선」「일단 종가결함만 수정」 —
momentum 전일종가 정의·전략 임계값은 **건드리지 않는다**. 이 파일은 leaf 의 행위만 잰다.

## 왜 (실측 한 줄)
KIS 일봉(FHKST03010100 `J`)은 D일 20:00 애프터마켓 뒤에도 그날 봉의 종가 = **19:59 애프터 마지막
체결가**, 고저 = 애프터 포함 범위를 준다. 정규장 값으로 바뀌는 것은 D일 23:12 뒤 ~ D+1일 05:28 전이다.
우리 20:30 적재가 가짜 값을 박고 D+1 아침 모든 prepare 가 그것을 읽는다(09-23 봉 모집단 약 60%).

## leaf 계약 (이 파일이 강제하는 것)
- 공개 = `spawn(*, phase)` · `wait_for_boot(task, *, budget_secs)` · `finalize_once(*, now_kst=None, phase)`.
- 헤드 `P` = `stock_master_daily.max_bas_dd_before(오늘)` = `max(bas_dd) WHERE bas_dd < 오늘`(§8-3, F1+F2).
  예외를 삼키지 않는다(실패 = `result=error stage=head`). 오늘·미래 봉은 SQL 조건에 걸려 헤드가 될 수 없다 —
  받는 구간의 끝이 오늘에 닿을 길을 막는다(§8-7 · G5(d), 실 SQL 증명 = 통합 `test_g1_7`).
- 대상 = `stock_master_daily.list_provisional_rows(since=T−21일, head=P, today_boundary=T 06:00 KST)`.
- 받기 = `condition.fetch_daily_chart_ranged_with_summary(ticker, start, end)` · `start = oldest − 10일` ·
  `end = newest`(≤ P) · `end − start > 130일` 이면 `start = end − 130일` + `span_clipped`.
- 거르기 = 응답에서 `[start, newest]` 밖 봉은 버린다(오늘 봉 포함).
- 교차검증(종목의 `newest == P` 일 때) = `output1.stck_prdy_clpr` 가 P 봉 종가면 `verified`,
  P 바로 앞 봉 종가면 `unrolled`(받아들인다), 그 밖(결측 포함)은 `mismatch` → **쓰지 않는다**.
  종목의 newest 봉이 응답에 없으면 `missing` → 쓰지 않는다. `newest < P`(유니버스 이탈분)는 교차검증 없이 쓴다.
- 쓰기(`enforce`) = `stock_master_daily.upsert_batch(ticker, 받은 구간 봉 전부)`. 반환 건수가 봉 수보다
  적거나 예외면 `db_write_failures`(upsert_batch 는 청크 실패를 삼키고 건수만 줄여 돌려준다).
- 모드 = `system_config.daily_bar_finalize_mode`(JSONB `{"value": ...}`) — 키 없음 `enforce` ·
  `observe`(받고 비교, 쓰기 0) · `off`(DB 대상 조회·KIS 0) · 모양이 틀림 `observe` · 조회 실패 `enforce`
  (요약에 `mode=enforce(db_error)` 류로 남긴다).
- 순서 = ① `069500`·`229200` ② DB `positions` 보유 ③ 나머지 `newest` 내림차순 → 티커 오름차순.
- 요약 마커 `[daily_bar_finalize] phase= mode= result= ... key=value` 1행. INFO 는 `result=ok|noop` 이고
  `failed=missing=mismatch=db_write_failures=0` 일 때뿐, 그 밖은 WARNING. 예산 초과면 `phase=boot
  result=budget_exceeded ... pending=`(WARNING) + 배경 끝에 `phase=background` 1행.
- never-raise — 어떤 실패도 부팅을 막지 않는다(fail-open + 마커).

## 테스트가 쓰는 seam (구현이 지켜야 하는 것)
- `stock_master_daily.{max_bas_dd_before, list_provisional_rows, upsert_batch}` · `positions.load_all` ·
  `condition.fetch_daily_chart_ranged_with_summary` 는 **호출 시점에 모듈 속성으로** 찾는다
  (`from src.db import stock_master_daily as m; m.f()` 또는 함수 안 지연 import). 모듈 최상단
  `from ... import f` 는 테스트 패치를 못 받는다.
- 모드는 `src.db.pg.fetch/fetchrow/fetchval` 경로로 읽힌다(system_config 헬퍼 경유) — 테스트가 그 층을 가짜로 둔다.
- `daily_bar_finalize._now_kst()` — `finalize_once(now_kst=None)`·`spawn` 이 쓰는 시계 seam(벽시계 게이트
  교훈: 테스트가 시계를 바꿀 수 있어야 한다). freezegun 은 쓰지 않는다(asyncio 타이머가 멈춘다).
- `BOOT_WORKERS`·`BG_SLEEP_SECS`·`HARD_CAP_SECS` 는 **실행 시점에** 모듈 전역을 읽는다(테스트가 줄인다).
- `wait_for_boot` 가 예산에서 돌아올 때 배경 전환은 **이미 적용돼 있다**(돌아온 뒤 새로 시작하는 호출은
  배경 보폭 — 한 번에 하나, `BG_SLEEP_SECS` 간격).
- `_BG_TASKS` — spawn 한 태스크의 강한 참조(`funnel_capture._BG_TASKS` 관례).

## HEAD 기준
전부 RED — `src.engine.daily_bar_finalize` 모듈이 없다(ImportError). 이 파일은 `real_daily_bar_finalize`
마커로 conftest 무력화를 벗어난다(실제 `finalize_once` 를 타야 한다).
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, time, timedelta, timezone

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.real_daily_bar_finalize]

KST = timezone(timedelta(hours=9))
T = date(2026, 9, 28)            # 월 — 09-24~26 추석 연휴
P = date(2026, 9, 23)            # 수 — 헤드(직전 거래일)
NOW = datetime(2026, 9, 28, 7, 46, tzinfo=KST)
_PREFIX = "[daily_bar_finalize] "
_MODE_KEY = "daily_bar_finalize_mode"


# ===========================================================================
# 합성 자료
# ===========================================================================
def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _bar(d: date, o: int, h: int, l: int, c: int, v: int = 1_000_000) -> dict:
    return {
        "stck_bsop_date": _ymd(d), "stck_oprc": str(o), "stck_hgpr": str(h),
        "stck_lwpr": str(l), "stck_clpr": str(c), "acml_vol": str(v),
        "acml_tr_pbmn": str(v * c), "flng_cls_code": "00", "prtt_rate": "0.00",
        "prdy_vrss": "0", "prdy_vrss_sign": "3", "mod_yn": "N",
    }


def _trading_days_back(end: date, n: int) -> list[date]:
    """end 포함, 주말·09-24~26 을 건너뛴 n 개 거래일(내림차순)."""
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5 and d not in (date(2026, 9, 24), date(2026, 9, 25)):
            out.append(d)
        d -= timedelta(days=1)
    return out


def _series(ticker_close: int, end: date = P, n: int = 30) -> list[dict]:
    """end 까지 n 거래일의 최종 봉(내림차순). 종가는 조금씩 다르게."""
    bars = []
    for i, d in enumerate(_trading_days_back(end, n)):
        c = ticker_close - i * 10
        bars.append(_bar(d, c - 20, c + 50, c - 60, c))
    return bars


def _prov(ticker: str, d: date, o: int, h: int, l: int, c: int) -> dict:
    return {"ticker": ticker, "bas_dd": d, "open_price": o, "high_price": h,
            "low_price": l, "close_price": c}


def _norm_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v)
    if len(s) == 8 and s.isdigit():
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return date.fromisoformat(s[:10])


def _markers(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith(_PREFIX)]


def _warn_markers(caplog) -> list[logging.LogRecord]:
    return [r for r in _markers(caplog) if r.levelno >= logging.WARNING]


def _kv(rec: logging.LogRecord) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S*)", rec.getMessage()))


def _only_marker(caplog) -> tuple[logging.LogRecord, dict[str, str]]:
    ms = _markers(caplog)
    assert len(ms) == 1, (
        f"실행 1회 = 요약 마커 정확히 1행이어야 한다(「안 돌았다」와 「고칠 게 없었다」를 가르는 유일한 "
        f"흔적) — 실측 {len(ms)}행: {[m.getMessage() for m in ms]}"
    )
    return ms[0], _kv(ms[0])


def _int(kv: dict, key: str) -> int:
    assert key in kv, f"요약 마커에 `{key}=` 가 없다 — 운영자가 볼 수 없는 수는 없는 것과 같다: {kv}"
    return int(kv[key])


# ===========================================================================
# 하네스 — DB·KIS 전부 가짜 (실 KIS/DB 에 닿는 테스트는 쓰지 않는다)
# ===========================================================================
class _MissingKey:
    pass


_ABSENT = _MissingKey()


class Harness:
    def __init__(self, monkeypatch):
        import src.api.condition as cond
        import src.db.pg as pg
        import src.db.positions as pos
        import src.db.stock_master_daily as smd

        self.head: date | None = P
        self.head_exc: BaseException | None = None
        self.prov: list[dict] = []
        self.list_exc: BaseException | None = None
        self.list_calls: list[dict] = []
        self.truth: dict[str, list[dict]] = {}
        self.prdy: dict[str, object] = {}
        self.kis_exc: dict[str, BaseException] = {}
        self.kis_empty: set[str] = set()
        self.kis_delay = 0.0
        self.overshoot = False
        self.fetch_calls: list[dict] = []
        self.upserts: list[tuple[str, list[dict]]] = []
        self.upsert_exc: dict[str, BaseException] = {}
        self.upsert_short: set[str] = set()
        self.positions: list[dict] = []
        self.positions_exc: BaseException | None = None
        self.mode: object = _ABSENT
        self.mode_exc: BaseException | None = None
        self.mode_reads = 0
        self._inflight = 0

        async def _max_bas_dd_before(today):
            if self.head_exc is not None:
                raise self.head_exc
            # F1+F2 — 실제 SQL 은 `bas_dd < $today` 다. 하네스가 설정한 원값(`self.head`)이
            # 그 조건을 만족하지 않으면(오늘 이상) 진짜 쿼리처럼 그 값을 못 본 것으로 친다.
            if self.head is not None and self.head >= today:
                return None
            return self.head

        async def _list(*, since, head, today_boundary):
            self.list_calls.append({"since": since, "head": head, "today_boundary": today_boundary})
            if self.list_exc is not None:
                raise self.list_exc
            return [dict(r) for r in self.prov]

        async def _upsert(ticker, candles):
            bars = [dict(c) for c in candles]
            if ticker in self.upsert_exc:
                raise self.upsert_exc[ticker]
            self.upserts.append((ticker, bars))
            return 0 if ticker in self.upsert_short else len(bars)

        async def _load_all():
            if self.positions_exc is not None:
                raise self.positions_exc
            return [dict(p) for p in self.positions]

        async def _fetch(ticker, start, end):
            loop = asyncio.get_running_loop()
            s, e = _norm_date(start), _norm_date(end)
            rec = {"ticker": ticker, "start": s, "end": e, "t0": loop.time(), "t1": None}
            self.fetch_calls.append(rec)
            self._inflight += 1
            try:
                if self.kis_delay:
                    await asyncio.sleep(self.kis_delay)
                if ticker in self.kis_exc:
                    raise self.kis_exc[ticker]
                if ticker in self.kis_empty:
                    return {}, []
                bars = self.truth.get(ticker, [])
                if not self.overshoot:
                    bars = [b for b in bars if s <= _norm_date(b["stck_bsop_date"]) <= e]
                out1 = {}
                if ticker in self.prdy and self.prdy[ticker] is not None:
                    out1 = {"stck_prdy_clpr": str(self.prdy[ticker])}
                return out1, [dict(b) for b in bars]
            finally:
                rec["t1"] = loop.time()
                self._inflight -= 1

        def _mode_payload():
            self.mode_reads += 1
            if self.mode_exc is not None:
                raise self.mode_exc
            return self.mode

        def _is_mode_query(sql, args) -> bool:
            return _MODE_KEY in [a for a in args if isinstance(a, str)] or (
                "system_config" in str(sql) and _MODE_KEY in str(sql)
            )

        async def _pg_fetch(sql, *args):
            if _is_mode_query(sql, args):
                v = _mode_payload()
                return [] if v is _ABSENT else [{"key": _MODE_KEY, "value": v}]
            return []

        async def _pg_fetchrow(sql, *args):
            if _is_mode_query(sql, args):
                v = _mode_payload()
                return None if v is _ABSENT else {"key": _MODE_KEY, "value": v}
            return None

        async def _pg_fetchval(sql, *args):
            if _is_mode_query(sql, args):
                v = _mode_payload()
                return None if v is _ABSENT else v
            return None

        async def _pg_write(*_a, **_k):
            raise AssertionError("finalize 가 upsert_batch 밖의 pg 쓰기를 했다")

        monkeypatch.setattr(smd, "max_bas_dd_before", _max_bas_dd_before, raising=False)
        monkeypatch.setattr(smd, "list_provisional_rows", _list, raising=False)
        monkeypatch.setattr(smd, "upsert_batch", _upsert)
        monkeypatch.setattr(pos, "load_all", _load_all)
        monkeypatch.setattr(cond, "fetch_daily_chart_ranged_with_summary", _fetch, raising=False)
        monkeypatch.setattr(pg, "fetch", _pg_fetch)
        monkeypatch.setattr(pg, "fetchrow", _pg_fetchrow)
        monkeypatch.setattr(pg, "fetchval", _pg_fetchval)
        monkeypatch.setattr(pg, "execute", _pg_write)
        monkeypatch.setattr(pg, "executemany", _pg_write)

    # 편의 --------------------------------------------------------------
    def add(self, ticker: str, prov_rows: list[dict], truth: list[dict], prdy=None) -> None:
        self.prov.extend(prov_rows)
        self.truth[ticker] = truth
        if prdy is not None:
            self.prdy[ticker] = prdy

    def add_simple(self, ticker: str, close_final: int, *, fake_close: int | None = None,
                   prdy="auto") -> None:
        truth = _series(close_final)
        head_bar = truth[0]
        fc = fake_close if fake_close is not None else close_final + 7
        self.prov.append(_prov(ticker, P, int(head_bar["stck_oprc"]), int(head_bar["stck_hgpr"]),
                               int(head_bar["stck_lwpr"]), fc))
        self.truth[ticker] = truth
        self.prdy[ticker] = close_final if prdy == "auto" else prdy

    def upserted_tickers(self) -> list[str]:
        return [t for t, _ in self.upserts]

    def upserted_bars(self, ticker: str) -> dict[date, dict]:
        out: dict[date, dict] = {}
        for t, bars in self.upserts:
            if t == ticker:
                for b in bars:
                    out[_norm_date(b["stck_bsop_date"])] = b
        return out


@pytest.fixture
def dbf():
    from src.engine import daily_bar_finalize

    return daily_bar_finalize


@pytest.fixture
def h(monkeypatch, dbf):
    harness = Harness(monkeypatch)
    monkeypatch.setattr(dbf, "_now_kst", lambda: NOW, raising=False)
    return harness


async def _run(dbf, caplog, *, now=NOW):
    caplog.set_level(logging.DEBUG)
    return await dbf.finalize_once(now_kst=now, phase="boot")


# ===========================================================================
# G2 — 쓰기 · 비교 · 교차검증
# ===========================================================================
@pytest.mark.asyncio
async def test_g2_1_394800_fake_close_is_replaced_by_regular_close(dbf, h, caplog):
    """394800 쓰리빌리언 09-23 — 가짜 {O5700,H6100,L5280,C5520} → KIS 확정 C5800, prdy=5800 → verified."""
    truth = _series(5800)
    truth[0] = _bar(P, 5700, 6100, 5280, 5800, 3_785_681)
    h.add("394800", [_prov("394800", P, 5700, 6100, 5280, 5520)], truth, prdy=5800)

    await _run(dbf, caplog)

    assert h.upserted_tickers() == ["394800"], f"확정값을 써야 한다 — 쓰기 {h.upserted_tickers()}"
    written = h.upserted_bars("394800")
    assert written[P]["stck_clpr"] == "5800", "P 봉 종가가 정규장 종가(5,800)로 바뀌어야 한다"
    rec, kv = _only_marker(caplog)
    assert rec.levelno == logging.INFO, f"깨끗한 실행은 INFO — {rec.getMessage()}"
    assert kv.get("result") == "ok"
    assert kv.get("phase") == "boot"
    assert _int(kv, "verified") == 1
    assert _int(kv, "close_changed") == 1
    assert _int(kv, "hl_changed") == 0
    assert _int(kv, "targets") == 1
    assert _int(kv, "upserted_rows") == len(written)
    assert kv.get("head") == P.isoformat()
    assert kv.get("since") == (T - timedelta(days=21)).isoformat()


@pytest.mark.asyncio
async def test_g2_2_323350_after_market_high_is_narrowed(dbf, h, caplog):
    """323350 09-23 — 가짜 {H10580,C10200} → 확정 {H9970,C9970}. 고저 차이도 센다."""
    truth = _series(9970)
    truth[0] = _bar(P, 9500, 9970, 8920, 9970)
    h.add("323350", [_prov("323350", P, 9500, 10580, 8920, 10200)], truth, prdy=9970)

    await _run(dbf, caplog)

    assert h.upserted_bars("323350")[P]["stck_hgpr"] == "9970"
    _, kv = _only_marker(caplog)
    assert _int(kv, "hl_changed") == 1
    assert _int(kv, "close_changed") == 1


@pytest.mark.asyncio
async def test_g2_3_unrolled_prdy_equals_previous_bar_close_is_accepted(dbf, h, caplog):
    """output1 이 아직 넘어가지 않은 아침(prdy == P 앞 봉 종가) — 시각 기준으로 받아들여 쓴다."""
    truth = _series(5800)
    prev_close = int(truth[1]["stck_clpr"])
    h.add("394800", [_prov("394800", P, 5700, 6100, 5280, 5520)], truth, prdy=prev_close)

    await _run(dbf, caplog)

    assert h.upserted_tickers() == ["394800"], "unrolled 는 실패가 아니다 — 써야 한다"
    rec, kv = _only_marker(caplog)
    assert _int(kv, "unrolled") == 1
    assert _int(kv, "verified") == 0
    assert rec.levelno == logging.INFO, "unrolled 만 있는 실행은 깨끗한 실행이다"


@pytest.mark.asyncio
async def test_g2_4_mismatch_writes_nothing_for_that_ticker(dbf, h, caplog):
    """prdy 가 P 봉·앞 봉 어느 쪽과도 다르면 그 종목은 쓰지 않는다(잠정 상태를 남겨 재시도 여지를 지킨다)."""
    h.add_simple("111110", 10000, prdy=12345)   # mismatch
    h.add_simple("222220", 20000)               # 정상

    await _run(dbf, caplog)

    assert "111110" not in h.upserted_tickers(), "mismatch 종목을 썼다 — 확인 안 된 값을 확정으로 찍는다"
    assert "222220" in h.upserted_tickers(), "한 종목의 mismatch 가 다른 종목의 확정을 막으면 안 된다"
    warns = _warn_markers(caplog)
    assert len(warns) == 1, f"mismatch 가 있으면 요약은 WARNING — {[m.getMessage() for m in _markers(caplog)]}"
    kv = _kv(warns[0])
    assert _int(kv, "mismatch") == 1
    assert "111110" in kv.get("sample_mismatch", ""), f"표본 종목이 없다 — {kv}"


@pytest.mark.asyncio
async def test_g2_4b_mismatch_when_output1_has_no_prdy(dbf, h, caplog):
    """output1 이 비었거나 전일종가가 없으면 확인 불가 = mismatch(쓰지 않는다, 예외 없이)."""
    h.add_simple("111110", 10000, prdy=None)
    h.prdy.pop("111110", None)

    await _run(dbf, caplog)

    assert h.upserted_tickers() == []
    warns = _warn_markers(caplog)
    assert len(warns) == 1
    assert _int(_kv(warns[0]), "mismatch") == 1


@pytest.mark.asyncio
async def test_g2_5_missing_head_bar_writes_nothing(dbf, h, caplog):
    """P 봉을 요청했는데 응답에 없다 → missing, 쓰기 0, WARNING.

    M12c — `prdy` 를 (없어진 P 봉이 아니라) **남은 첫 봉(P 의 직전 거래일) 종가**와
    일치시킨다. `p_bar is None` 검사가 prdy 비교보다 **먼저** 와야 하는 회귀다 — 순서가
    바뀌면 이 prdy 값이 "unrolled" 조건을 우연히 만족시켜 missing 대신 조용히 써 버릴 수
    있다. `mismatch == 0` 도 함께 확인해 missing 이 mismatch 로 오분류되지 않는지 본다.
    """
    truth = _series(10000)[1:]   # P 봉이 없는 응답 — truth[0] 은 이제 P 의 직전 거래일 봉
    prev_close = int(truth[0]["stck_clpr"])
    h.add("111110", [_prov("111110", P, 9980, 10050, 9940, 10007)], truth, prdy=prev_close)

    await _run(dbf, caplog)

    assert h.upserted_tickers() == []
    warns = _warn_markers(caplog)
    assert len(warns) == 1
    kv = _kv(warns[0])
    assert _int(kv, "missing") == 1
    assert _int(kv, "mismatch") == 0, "P 봉 부재가 mismatch 로 오분류됐다 — 순서 회귀"
    assert kv.get("result") == "ok", (
        f"missing 은 종목 단위로 건너뛰는 것이다(실행은 끝까지 간다) — 일꾼이 죽은 흔적이다: {kv}"
    )


@pytest.mark.asyncio
async def test_g2_6_fetch_range_is_oldest_minus_pad_to_newest(dbf, h, caplog):
    """start = 가장 오래된 잠정 봉 − 10일, end = 가장 새 잠정 봉. 유니버스 이탈분(newest < P)은 교차검증 없이 쓴다."""
    d_old = date(2026, 9, 16)
    t1 = _series(10000)
    h.add("111110", [_prov("111110", d_old, 1, 2, 1, 2), _prov("111110", P, 1, 2, 1, 2)], t1, prdy=10000)
    t2 = _series(7000, end=d_old)
    # 유니버스 이탈 종목 — output1 전일종가는 오늘 기준 값이라 그 종목의 09-16 종가와 무관하다
    h.add("222220", [_prov("222220", d_old, 1, 2, 1, 2)], t2, prdy=99999)

    await _run(dbf, caplog)

    calls = {c["ticker"]: c for c in h.fetch_calls}
    assert calls["111110"]["start"] == d_old - timedelta(days=10)
    assert calls["111110"]["end"] == P
    assert calls["222220"]["start"] == d_old - timedelta(days=10)
    assert calls["222220"]["end"] == d_old, "end 는 그 종목의 가장 새 잠정 봉이다(P 가 아니다)"
    assert "222220" in h.upserted_tickers(), (
        "유니버스 이탈분(P 봉 없음)을 교차검증 대상으로 착각해 버렸다 — 영구 가짜 봉(§4-3)이 고쳐지지 않는다"
    )
    _, kv = _only_marker(caplog)
    assert _int(kv, "verified") + _int(kv, "unrolled") + _int(kv, "mismatch") == 1, (
        "교차검증은 newest == P 인 종목에만 한다"
    )


@pytest.mark.asyncio
async def test_g2_7_bars_outside_range_and_today_are_never_written(dbf, h, caplog):
    """KIS 가 구간 밖 봉(오늘 껍데기 포함)을 줘도 [start, newest] 밖은 버린다(M3 방어)."""
    truth = _series(10000, end=T, n=40)       # 오늘(09-28) 봉까지 들어 있는 응답
    h.add("111110", [_prov("111110", P, 1, 2, 1, 2)], truth, prdy=int(truth[1]["stck_clpr"]))
    h.overshoot = True

    await _run(dbf, caplog)

    written = h.upserted_bars("111110")
    assert written, "정상 종목을 쓰지 않았다"
    start = P - timedelta(days=10)
    assert all(start <= d <= P for d in written), (
        f"[start, P] 밖 봉을 썼다 — {sorted(d for d in written if not start <= d <= P)}"
    )
    assert T not in written, "오늘 껍데기 봉을 썼다 — 장중 부분봉이 일봉으로 굳는다"


@pytest.mark.asyncio
async def test_g2_8_all_bars_in_range_are_written(dbf, h, caplog):
    """받은 구간의 봉을 전부 덮는다(20:30 7일 창과 같은 방식 — 한 시점의 KIS 값으로 연속 구간을 맞춘다)."""
    truth = _series(10000)
    h.add("111110", [_prov("111110", P, 1, 2, 1, 2)], truth, prdy=10000)

    await _run(dbf, caplog)

    start = P - timedelta(days=10)
    expect = {_norm_date(b["stck_bsop_date"]) for b in truth if start <= _norm_date(b["stck_bsop_date"]) <= P}
    assert set(h.upserted_bars("111110")) == expect


@pytest.mark.asyncio
async def test_g2_9_target_query_uses_since_head_and_six_oclock_boundary(dbf, h, caplog):
    """대상 조회 인자 = since(T−21일) · head(P) · today_boundary(T 06:00 KST, aware)."""
    h.add_simple("111110", 10000)

    await _run(dbf, caplog)

    assert len(h.list_calls) == 1, f"대상 조회는 실행당 1회 — {h.list_calls}"
    call = h.list_calls[0]
    assert _norm_date(call["since"]) == T - timedelta(days=21)
    assert _norm_date(call["head"]) == P
    b = call["today_boundary"]
    assert isinstance(b, datetime) and b.tzinfo is not None, "경계는 시간대가 붙은 datetime 이어야 한다"
    assert b.astimezone(KST) == datetime(2026, 9, 28, 6, 0, tzinfo=KST), f"경계 = 오늘 06:00 KST — {b!r}"


@pytest.mark.asyncio
async def test_g2_10_end_never_reaches_today_even_with_a_today_shell_head(dbf, h, caplog):
    """G5(d) 런타임 — 대상 조회가 잘못 오늘 행을 돌려줘도 받는 구간의 끝은 오늘 전이다.

    F1+F2 이후 헤드 SQL 자체가 `bas_dd < 오늘` 이라, 헤드가 오늘 이상이 되는 경로는 더
    이상 없다(`max_bas_dd_before` 가 구조적으로 막는다 — 그 SQL 은 하네스가 가짜로 두므로
    실 SQL 증명은 통합 `test_cycle386_provisional_predicate_pg.py::test_g1_7`). 이 테스트가 재현하는 것은 그
    **다음** 방어선이다 — `list_provisional_rows`(대상 조회)가 실수로 오늘 날짜 행을
    돌려줘도 `_group_targets` 가 그 행을 버려 KIS 조회·쓰기 어느 쪽에도 닿지 않는다.
    """
    truth = _series(10000, end=P, n=40)
    h.prov = [
        _prov("111110", P, 1, 2, 1, 2),
        _prov("222220", T, 1, 2, 1, 2),   # 대상 조회가 잘못 돌려준 오늘 행 — 받지 않아야 한다
    ]
    h.truth = {"111110": truth, "222220": truth}
    h.prdy = {"111110": int(truth[0]["stck_clpr"]), "222220": int(truth[0]["stck_clpr"])}

    await _run(dbf, caplog)

    assert h.list_calls and _norm_date(h.list_calls[0]["head"]) < T, (
        f"헤드가 오늘로 넘어갔다 — {h.list_calls}"
    )
    assert [c["ticker"] for c in h.fetch_calls] == ["111110"], (
        f"오늘 행만 있던 222220 이 KIS 조회까지 갔다 — {h.fetch_calls}"
    )
    assert all(c["end"] < T for c in h.fetch_calls), (
        f"받는 구간의 끝이 오늘에 닿았다 — {[(c['ticker'], c['end']) for c in h.fetch_calls]}"
    )
    for t, bars in h.upserts:
        assert all(_norm_date(b["stck_bsop_date"]) < T for b in bars), f"{t} 오늘 봉을 썼다"


@pytest.mark.asyncio
async def test_g2_11_span_is_clipped_to_one_kis_call(dbf, h, caplog, monkeypatch):
    """(end − start) 가 MAX_SPAN_CAL_DAYS 를 넘으면 start 를 잘라 최근만 받고 span_clipped 로 센다."""
    far = P - timedelta(days=200)
    h.add("111110", [_prov("111110", far, 1, 2, 1, 2), _prov("111110", P, 1, 2, 1, 2)],
          _series(10000, n=120), prdy=10000)

    await _run(dbf, caplog)

    c = h.fetch_calls[0]
    assert (c["end"] - c["start"]).days <= dbf.MAX_SPAN_CAL_DAYS, (
        f"한 호출 구간이 {(c['end'] - c['start']).days}일 — KIS 100봉 한도를 넘어 앞이 잘린다"
    )
    assert c["end"] == P
    _, kv = _only_marker(caplog)
    assert _int(kv, "span_clipped") == 1


@pytest.mark.asyncio
async def test_g2_12_priority_order(dbf, h, caplog, monkeypatch):
    """① 069500·229200 ② DB 보유 ③ newest 내림차순 → 티커 오름차순 (일꾼 1명으로 순서를 본다)."""
    monkeypatch.setattr(dbf, "BOOT_WORKERS", 1)
    d22, d16 = date(2026, 9, 22), date(2026, 9, 16)
    for t in ("005930", "000660", "229200", "069500", "333330"):
        h.add_simple(t, 10000)
    h.add("111110", [_prov("111110", d16, 1, 2, 1, 2)], _series(7000, end=d16), prdy=1)
    h.add("222220", [_prov("222220", d22, 1, 2, 1, 2)], _series(7000, end=d22), prdy=1)
    h.positions = [{"ticker": "333330"}, {"ticker": "999990"}]   # 999990 = 대상 아님

    await _run(dbf, caplog)

    order = [c["ticker"] for c in h.fetch_calls]
    assert order == ["069500", "229200", "333330", "000660", "005930", "222220", "111110"], (
        f"순서가 틀렸다 — {order}. 예산을 넘겨도 시장 유닛·보유 청산 입력·헤드가 먼저 확정돼야 한다"
    )


@pytest.mark.asyncio
async def test_g2_13_positions_failure_does_not_block(dbf, h, caplog):
    """보유 조회가 실패해도 우선순위만 잃고 확정은 계속한다."""
    h.add_simple("111110", 10000)
    h.add_simple("222220", 20000)
    h.positions_exc = ConnectionError("positions down")

    await _run(dbf, caplog)

    assert sorted(h.upserted_tickers()) == ["111110", "222220"]


@pytest.mark.asyncio
async def test_g2_14_noop_when_no_targets(dbf, h, caplog):
    """대상 0 도 1행을 남긴다 — 「안 돌았다」와 「고칠 것이 없었다」를 가른다."""
    await _run(dbf, caplog)

    assert h.fetch_calls == []
    rec, kv = _only_marker(caplog)
    assert kv.get("result") == "noop"
    assert rec.levelno == logging.INFO
    assert _int(kv, "targets") == 0


@pytest.mark.asyncio
async def test_g2_15_empty_table_is_noop_without_query(dbf, h, caplog):
    """빈 테이블(헤드 None) — 대상 조회도 KIS 도 없다."""
    h.head = None

    await _run(dbf, caplog)

    assert h.list_calls == [] and h.fetch_calls == []
    rec, kv = _only_marker(caplog)
    assert kv.get("result") == "noop"
    assert rec.levelno == logging.INFO


@pytest.mark.asyncio
async def test_g2_16_upsert_short_count_is_a_write_failure(dbf, h, caplog):
    """upsert_batch 는 청크 실패를 삼키고 건수만 줄여 돌려준다 — 0 건 반환을 성공으로 세면 안 된다."""
    h.add_simple("111110", 10000)
    h.upsert_short.add("111110")

    await _run(dbf, caplog)

    warns = _warn_markers(caplog)
    assert len(warns) == 1, "쓰기 실패를 INFO 로 덮었다"
    assert _int(_kv(warns[0]), "db_write_failures") == 1


# ---------------------------------------------------------------------------
# 모드 (system_config.daily_bar_finalize_mode)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_g2_mode_1_absent_key_means_enforce(dbf, h, caplog):
    h.add_simple("111110", 10000)
    h.mode = _ABSENT

    await _run(dbf, caplog)

    assert h.mode_reads >= 1, "모드를 system_config 에서 읽지 않았다"
    assert h.upserted_tickers() == ["111110"], "키 없음 = enforce(쓴다)"
    _, kv = _only_marker(caplog)
    assert kv.get("mode", "").startswith("enforce")


@pytest.mark.asyncio
async def test_g2_mode_2_observe_fetches_and_compares_without_writing(dbf, h, caplog):
    h.add_simple("111110", 10000, fake_close=10500)
    h.mode = {"value": "observe"}

    await _run(dbf, caplog)

    assert [c["ticker"] for c in h.fetch_calls] == ["111110"], "observe 도 받아서 비교한다"
    assert h.upserts == [], "observe 가 썼다"
    _, kv = _only_marker(caplog)
    assert kv.get("mode", "").startswith("observe")
    assert _int(kv, "close_changed") == 1, "observe 의 쓸모는 「몇 개가 바뀌었을지」 다"
    assert _int(kv, "upserted_rows") == 0


@pytest.mark.asyncio
async def test_g2_mode_3_off_touches_nothing(dbf, h, caplog):
    h.add_simple("111110", 10000)
    h.mode = {"value": "off"}

    await _run(dbf, caplog)

    assert h.list_calls == [] and h.fetch_calls == [] and h.upserts == [], "off 가 무언가를 했다"
    assert _warn_markers(caplog) == [], "의도적으로 끈 것은 경보가 아니다"


@pytest.mark.parametrize("raw", ["garbage", {"value": 3}, {"x": "enforce"}, ["enforce"]])
@pytest.mark.asyncio
async def test_g2_mode_4_malformed_value_means_observe(dbf, h, caplog, raw):
    h.add_simple("111110", 10000)
    h.mode = raw

    await _run(dbf, caplog)

    assert h.fetch_calls, "모양이 틀린 값 = observe (받기는 한다)"
    assert h.upserts == [], f"모양이 틀린 값({raw!r})으로 썼다 — observe 로 떨어져야 한다"


@pytest.mark.asyncio
async def test_g2_mode_5_db_error_means_enforce_and_says_so(dbf, h, caplog):
    """조회 실패 = enforce(쓰는 값이 KIS 확정값이라 수정 자체가 안전하다) + 요약에 사유."""
    h.add_simple("111110", 10000)
    h.mode_exc = ConnectionError("pg down")

    await _run(dbf, caplog)

    assert h.upserted_tickers() == ["111110"]
    _, kv = _only_marker(caplog)
    assert kv.get("mode", "").startswith("enforce") and "db_error" in kv.get("mode", ""), (
        f"모드 조회 실패가 요약에 안 보인다 — {kv.get('mode')!r}"
    )


# ===========================================================================
# G3 — 실패 경로 never-raise + WARNING (caplog 는 WARNING 이상 + 접두사로만 단언)
# ===========================================================================
@pytest.mark.asyncio
async def test_g3_1_select_failure_is_warning_and_fixes_nothing(dbf, h, caplog):
    h.add_simple("111110", 10000)
    h.list_exc = ConnectionError("select down")

    await _run(dbf, caplog)   # 예외 전파 금지

    assert h.fetch_calls == [] and h.upserts == []
    warns = _warn_markers(caplog)
    assert len(warns) == 1, f"대상 조회 실패가 조용하다 — {[m.getMessage() for m in _markers(caplog)]}"
    kv = _kv(warns[0])
    assert kv.get("result") == "error"
    assert kv.get("stage") == "select"


@pytest.mark.asyncio
async def test_g3_2_kis_failure_for_one_ticker(dbf, h, caplog):
    h.add_simple("111110", 10000)
    h.add_simple("222220", 20000)
    h.kis_exc["111110"] = RuntimeError("KIS 500")

    await _run(dbf, caplog)

    assert h.upserted_tickers() == ["222220"], "한 종목 실패가 다른 종목을 막았다"
    warns = _warn_markers(caplog)
    assert len(warns) == 1
    kv = _kv(warns[0])
    assert _int(kv, "failed") == 1
    assert "111110" in kv.get("sample_failed", "")


@pytest.mark.asyncio
async def test_g3_3_empty_kis_response_is_a_failure(dbf, h, caplog):
    h.add_simple("111110", 10000)
    h.kis_empty.add("111110")

    await _run(dbf, caplog)

    assert h.upserts == []
    warns = _warn_markers(caplog)
    assert len(warns) == 1
    assert _int(_kv(warns[0]), "failed") == 1


@pytest.mark.asyncio
async def test_g3_4_upsert_exception_is_counted_and_next_ticker_continues(dbf, h, caplog, monkeypatch):
    monkeypatch.setattr(dbf, "BOOT_WORKERS", 1)
    h.add_simple("111110", 10000)
    h.add_simple("222220", 20000)
    h.upsert_exc["111110"] = ConnectionError("write down")

    await _run(dbf, caplog)

    assert "222220" in h.upserted_tickers()
    warns = _warn_markers(caplog)
    assert len(warns) == 1
    assert _int(_kv(warns[0]), "db_write_failures") == 1


@pytest.mark.asyncio
async def test_g3_5_head_query_failure_is_stage_head_via_the_real_function(dbf, caplog, monkeypatch):
    """F1+F2 — §8-3 헤드 SQL 실패는 `result=error stage=head` 여야 한다.

    **진짜** `stock_master_daily.max_bas_dd_before` 를 태운다(하네스의 가짜 `head_exc`
    스텁을 쓰지 않는다) — `max_bas_dd(None)` 은 DB 예외를 삼켜 이 실패를 noop(INFO,
    "깨끗하다")으로 둔갑시켰다. 그 결함이 재발하지 않는지는 프로덕션이 실제로 경유하는
    `pg.fetchval` 을 터뜨려야 증명된다 — 하네스 스텁은 함수가 진짜로 예외를 전파하는지
    말해 주지 않는다. 이 테스트는 `h` 픽스처(하네스)를 쓰지 않는다.
    """
    import src.db.pg as pg

    async def _fetch(sql, *args):
        return []   # 모드 조회 — 행 없음 = enforce

    async def _boom_fetchval(sql, *args):
        raise ConnectionError("pg down")

    async def _no_write(*_a, **_k):
        raise AssertionError("헤드 조회 실패 뒤에 다른 조회·쓰기가 나갔다")

    monkeypatch.setattr(pg, "fetch", _fetch)
    monkeypatch.setattr(pg, "fetchrow", _no_write)
    monkeypatch.setattr(pg, "fetchval", _boom_fetchval)
    monkeypatch.setattr(pg, "execute", _no_write)
    monkeypatch.setattr(pg, "executemany", _no_write)
    monkeypatch.setattr(dbf, "_now_kst", lambda: NOW, raising=False)

    await _run(dbf, caplog)   # 예외 전파 금지

    warns = _warn_markers(caplog)
    assert len(warns) == 1, f"헤드 조회 실패가 조용하다 — {[m.getMessage() for m in _markers(caplog)]}"
    kv = _kv(warns[0])
    assert kv.get("result") == "error"
    assert kv.get("stage") == "head"


@pytest.mark.asyncio
async def test_g3_6_wait_for_boot_never_raises(dbf, h, caplog):
    """wait_for_boot — 태스크 없음 · 태스크가 예외로 끝남 모두 부팅을 막지 않는다.

    R4 — 예외로 끝난 태스크를 흡수할 때 WARNING 을 남긴다(조용한 흡수 금지).
    """
    caplog.set_level(logging.DEBUG)
    await dbf.wait_for_boot(None, budget_secs=0.1)

    async def _boom():
        raise RuntimeError("task died")

    t = asyncio.create_task(_boom())
    await dbf.wait_for_boot(t, budget_secs=1.0)
    assert t.done()
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING and "wait_for_boot" in r.getMessage()]
    assert len(warns) == 1, f"예외로 죽은 확정 태스크를 조용히 흡수했다 — {[r.getMessage() for r in caplog.records]}"


@pytest.mark.asyncio
async def test_g3_7_worker_exception_is_stage_processing_and_stops_siblings(
    dbf, h, caplog, monkeypatch,
):
    """R3 — 워커 하나가 못 잡는 예외로 죽으면 형제를 취소하고 **기다린 뒤에만**
    `stage=processing` 요약을 낸다.

    `asyncio.gather` 기본 동작은 한 태스크가 실패해도 형제를 취소하지 않는다 — 그대로
    두면 형제가 요약이 나간 **뒤에도** 계속 써서 "쓰기는 요약 이전에 멈춘다" 는 계약이
    깨진다. 이 테스트는 느린 종목(`111110`)이 KIS 응답을 기다리는 동안 다른 종목
    (`999999`)이 즉시 예외로 죽는 경합을 재현한다.
    """
    monkeypatch.setattr(dbf, "BOOT_WORKERS", 2)
    h.add_simple("999999", 10000)   # 즉시 예외
    h.add_simple("111110", 20000)   # 예외가 날 때 아직 KIS 응답을 기다리는 종목
    h.kis_delay = 0.05

    real_process_ticker = dbf._RunCtx.process_ticker

    async def _boom_process_ticker(self, ticker, info):
        if ticker == "999999":
            raise RuntimeError("worker exploded")
        return await real_process_ticker(self, ticker, info)

    monkeypatch.setattr(dbf._RunCtx, "process_ticker", _boom_process_ticker)

    await _run(dbf, caplog)   # 예외 전파 금지

    assert any(c["ticker"] == "111110" for c in h.fetch_calls), (
        "전제 위반 — 형제 워커(111110)가 시작도 못 했다(경합을 재현하지 못했다)"
    )
    # 요약이 나간 순간(= `finalize_once` 가 돌아온 순간) 형제의 KIS 호출은 이미 풀려 있어야 한다 —
    # 취소만 걸고 기다리지 않으면 형제는 아직 살아 있다(하네스 `_fetch` 의 finally 가 `t1` 을 찍는다).
    assert all(c["t1"] is not None for c in h.fetch_calls), (
        f"요약이 나간 뒤에도 형제 일꾼이 살아 있다 — {[(c['ticker'], c['t1']) for c in h.fetch_calls]}"
    )
    # 형제의 KIS 응답이 올 시간이 지나도 쓰기가 없어야 한다(취소 없이 두면 요약 뒤에 쓴다).
    await asyncio.sleep(h.kis_delay * 4)
    assert h.upserted_tickers() == [], (
        "형제 워커가 취소되지 않고 계속 써서 `stage=processing` 요약 뒤에도 값이 남았다"
    )
    warns = _warn_markers(caplog)
    assert len(warns) == 1, f"조용히 사라졌다 — {[m.getMessage() for m in _markers(caplog)]}"
    kv = _kv(warns[0])
    assert kv.get("result") == "error"
    assert kv.get("stage") == "processing"
    # §8-6 — 예상 밖 예외는 WARNING + traceback. 없으면 예외 종류·메시지가 통째로 사라진다.
    assert warns[0].exc_info is not None and warns[0].exc_info[0] is not None, (
        "`stage=processing` WARNING 에 traceback 이 없다 — 일꾼을 죽인 예외가 기록되지 않는다"
    )


@pytest.mark.asyncio
async def test_g3_8_wait_for_boot_absorbs_a_foreign_cancellation(dbf, caplog):
    """R4 — 확정 태스크만 외부에서 취소됐고, `wait_for_boot` 를 부른 태스크(=부팅) 자신은
    취소 요청을 받지 않았다 — 부팅까지 취소되면 안 된다."""
    caplog.set_level(logging.DEBUG)

    async def _hang():
        await asyncio.Event().wait()

    t = asyncio.create_task(_hang())
    await asyncio.sleep(0)
    t.cancel()   # 확정 태스크만 취소한다 — 이 테스트(부팅 역) 자신은 취소되지 않는다

    await dbf.wait_for_boot(t, budget_secs=1.0)   # 예외를 올리면 안 된다(R4)

    assert t.cancelled()
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("wait_for_boot" in r.getMessage() for r in warns), (
        f"흡수한 취소가 조용하다 — {[r.getMessage() for r in warns]}"
    )


@pytest.mark.asyncio
async def test_g3_9_wait_for_boot_propagates_when_its_own_task_is_cancelled(dbf):
    """R4 — `wait_for_boot` 를 부른 태스크 자신(부팅)이 취소되면 흡수하지 않고
    전파한다(확정 태스크는 `shield` 로 보호돼 그대로 계속 돈다)."""
    finalize_started = asyncio.Event()
    finalize_may_finish = asyncio.Event()

    async def _slow_finalize():
        finalize_started.set()
        await finalize_may_finish.wait()

    finalize_task = asyncio.create_task(_slow_finalize())
    await finalize_started.wait()

    async def _boot_like():
        await dbf.wait_for_boot(finalize_task, budget_secs=10.0)

    boot_task = asyncio.create_task(_boot_like())
    await asyncio.sleep(0)      # boot_task 가 wait_for_boot 안에서 대기하도록 한 틱 양보
    boot_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await boot_task

    assert not finalize_task.done(), "확정 태스크까지 취소됐다 — shield 가 깨졌다"
    finalize_may_finish.set()
    await asyncio.wait_for(finalize_task, timeout=1)


@pytest.mark.asyncio
async def test_g3_10_unexpected_exception_outside_stages_is_stage_unexpected(
    dbf, h, caplog, monkeypatch,
):
    """R1 — 단계별 try 사이(정렬 등)가 터져도 조용히 사라지지 않고 `stage=unexpected`
    로 요약한다."""
    h.add_simple("111110", 10000)

    def _boom(*_a, **_k):
        raise RuntimeError("order blew up")

    monkeypatch.setattr(dbf, "_order_targets", _boom)

    await _run(dbf, caplog)   # 예외 전파 금지

    warns = _warn_markers(caplog)
    assert len(warns) == 1, f"조용히 사라졌다 — {[m.getMessage() for m in _markers(caplog)]}"
    kv = _kv(warns[0])
    assert kv.get("result") == "error"
    assert kv.get("stage") == "unexpected"
    ei = warns[0].exc_info
    assert ei and ei[0] is RuntimeError, (
        f"예상 밖 예외의 traceback 이 요약에 붙지 않았다(§8-6 「WARNING + traceback」) — {ei!r}"
    )


@pytest.mark.asyncio
async def test_g3_11_cancelled_error_still_propagates_through_the_outer_try(
    dbf, h, caplog, monkeypatch,
):
    """R1 — 바깥 try 가 `CancelledError` 까지 삼키면 안 된다(취소는 취소로 남아야 한다)."""
    h.add_simple("111110", 10000)

    def _boom(*_a, **_k):
        raise asyncio.CancelledError()

    monkeypatch.setattr(dbf, "_order_targets", _boom)

    with pytest.raises(asyncio.CancelledError):
        await _run(dbf, caplog)


# ===========================================================================
# G4 — 예산 · 보폭 · 하드캡 (spawn → wait_for_boot → 배경)
# ===========================================================================
def _overlap_max(calls: list[dict]) -> int:
    pts = []
    for c in calls:
        pts.append((c["t0"], 1))
        pts.append((c["t1"], -1))
    pts.sort(key=lambda x: (x[0], x[1]))
    cur = best = 0
    for _, d in pts:
        cur += d
        best = max(best, cur)
    return best


@pytest.mark.asyncio
async def test_g4_1_fast_run_finishes_within_budget_with_one_marker(dbf, h, caplog):
    caplog.set_level(logging.DEBUG)
    for i in range(3):
        h.add_simple(f"11111{i}", 10000 + i * 100)

    task = dbf.spawn(phase="boot")
    assert isinstance(task, asyncio.Task)
    await dbf.wait_for_boot(task, budget_secs=5.0)

    assert task.done(), "예산 안에 끝났는데 부팅이 태스크를 기다리지 않았다"
    assert sorted(h.upserted_tickers()) == ["111110", "111111", "111112"]
    rec, kv = _only_marker(caplog)
    assert kv.get("phase") == "boot" and kv.get("result") == "ok"


@pytest.mark.asyncio
async def test_g4_2_budget_exceeded_then_background_finishes_serially(dbf, h, caplog, monkeypatch):
    """예산을 넘기면 부팅은 돌아가고, 나머지는 배경에서 한 번에 하나 · BG_SLEEP_SECS 간격으로 끝낸다."""
    caplog.set_level(logging.DEBUG)
    bg_sleep = 0.02
    monkeypatch.setattr(dbf, "BG_SLEEP_SECS", bg_sleep)
    tickers = [f"{100000 + i:06d}" for i in range(15)]
    for t in tickers:
        h.add_simple(t, 10000)
    h.kis_delay = 0.03
    loop = asyncio.get_running_loop()

    task = dbf.spawn(phase="boot")
    t_spawn = loop.time()
    await dbf.wait_for_boot(task, budget_secs=0.08)
    t_b = loop.time()

    assert t_b - t_spawn < 0.08 + 0.5, f"부팅이 예산을 넘겨 기다렸다 ({t_b - t_spawn:.3f}s)"
    assert not task.done(), "전제 위반 — 예산 안에 다 끝나 버렸다(지연을 늘려야 한다)"
    assert not task.cancelled()

    await asyncio.wait_for(asyncio.shield(task), timeout=10)

    assert sorted(h.upserted_tickers()) == sorted(tickers), "배경이 나머지를 끝내지 않았다"
    pre = [c for c in h.fetch_calls if c["t0"] < t_b]
    post = [c for c in h.fetch_calls if c["t0"] >= t_b]
    assert pre and post, f"전제 — 부팅 중 {len(pre)}건 · 배경 {len(post)}건"
    assert 2 <= _overlap_max(pre) <= 3, f"부팅 중 동시 호출 = {_overlap_max(pre)} (한도 3)"
    assert _overlap_max(post) == 1, (
        f"배경 동시 호출 = {_overlap_max(post)} — 배경은 일꾼 1명이다(주문 경로와 전역 20건/초를 나눠 쓴다)"
    )
    post.sort(key=lambda c: c["t0"])
    gaps = [b["t0"] - a["t1"] for a, b in zip(post, post[1:])]
    assert gaps and min(gaps) >= bg_sleep * 0.8, f"배경 보폭이 없다 — 간격 {min(gaps):.4f}s < {bg_sleep}s"

    ms = _markers(caplog)
    boot = [m for m in ms if _kv(m).get("phase") == "boot"]
    bg = [m for m in ms if _kv(m).get("phase") == "background"]
    assert len(boot) == 1 and _kv(boot[0]).get("result") == "budget_exceeded", (
        f"예산 초과 요약이 없다 — {[m.getMessage() for m in ms]}"
    )
    assert boot[0].levelno >= logging.WARNING
    assert _int(_kv(boot[0]), "pending") > 0
    assert len(bg) == 1, f"배경 끝 요약 1행 — {[m.getMessage() for m in ms]}"


@pytest.mark.asyncio
async def test_g4_3_hard_cap_stops_the_background(dbf, h, caplog, monkeypatch):
    """하드캡 — 어떤 경우에도 멈춘다(20:45 토큰 창 증명의 전제). 남은 수를 WARNING 으로 남긴다."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(dbf, "HARD_CAP_SECS", 0.3)
    monkeypatch.setattr(dbf, "BG_SLEEP_SECS", 0.0)
    tickers = [f"{200000 + i:06d}" for i in range(40)]
    for t in tickers:
        h.add_simple(t, 10000)
    h.kis_delay = 0.05
    loop = asyncio.get_running_loop()

    t_spawn = loop.time()
    task = dbf.spawn(phase="boot")
    await dbf.wait_for_boot(task, budget_secs=0.05)
    await asyncio.wait_for(asyncio.shield(task), timeout=5)
    t_done = loop.time()

    assert t_done - t_spawn <= 0.3 + 0.4, f"하드캡을 넘겨 돌았다 ({t_done - t_spawn:.3f}s)"
    assert len(h.fetch_calls) < len(tickers), "전제 위반 — 하드캡 전에 다 끝났다"
    late = [c for c in h.fetch_calls if c["t0"] > t_spawn + 0.3 + 0.05]
    assert late == [], f"하드캡 뒤에 새 호출이 나갔다 — {len(late)}건"
    warns = [m for m in _warn_markers(caplog) if _kv(m).get("result") == "hard_cap"]
    assert len(warns) == 1, f"하드캡 요약이 없다 — {[m.getMessage() for m in _markers(caplog)]}"
    assert _int(_kv(warns[0]), "pending") > 0


@pytest.mark.asyncio
async def test_g4_4_spawn_holds_a_strong_reference(dbf, h, caplog):
    """asyncio 는 버린 Task 를 약한 참조로만 쥔다 — 모듈 전역 집합이 붙들고, 끝나면 스스로 빠진다."""
    h.add_simple("111110", 10000)
    h.kis_delay = 0.05

    task = dbf.spawn(phase="boot")
    assert task in dbf._BG_TASKS
    await dbf.wait_for_boot(task, budget_secs=5.0)
    await asyncio.sleep(0)
    assert task not in dbf._BG_TASKS


@pytest.mark.asyncio
async def test_g4_5_boot_waits_for_finalize_before_prepare(dbf, monkeypatch):
    """부팅 배선 런타임 — prepare 는 확정이 끝난 뒤에 돈다(예산 안이면)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.engine import boot_manager

    order: list[str] = []

    async def _probe_finalize(*_a, **_k):
        await asyncio.sleep(0.05)
        order.append("finalize_done")

    async def _probe_head():
        order.append("head_stale")

    monkeypatch.setattr(dbf, "finalize_once", _probe_finalize)
    monkeypatch.setattr(boot_manager, "emit_daily_head_staleness", _probe_head)

    class _S:
        strategy_id = "vb"

        async def prepare(self, *a, **k):
            order.append("prepare")

    s = MagicMock()
    s._preissue_all_tokens = AsyncMock()
    s._load_strategy_config = AsyncMock()
    s._refresh_market_regime_and_persist = AsyncMock()
    s._resolve_cash_usage_ratio = AsyncMock(return_value=1.0)
    s.registry = MagicMock()
    s.registry.enabled = MagicMock(return_value=[_S()])
    summary = MagicMock(net_asset=1_000_000)
    with patch.object(boot_manager, "get_balance", AsyncMock(return_value=([], summary))), \
            patch.object(boot_manager, "token_manager") as tm, \
            patch.object(boot_manager, "get_daily_orders", AsyncMock(return_value=[])), \
            patch("src.db.stock_master.count_active", AsyncMock(return_value=100)), \
            patch.object(boot_manager, "write_log", AsyncMock()):
        tm.get_token = AsyncMock()
        try:
            await boot_manager.boot(s)
        except Exception:
            pass   # prepare 뒤 단계(포지션 복구)는 이 테스트의 대상이 아니다

    assert "prepare" in order, f"prepare 까지 가지 않았다 — {order}"
    assert order.index("finalize_done") < order.index("head_stale") < order.index("prepare"), (
        f"확정 → 헤드 관측 → prepare 순서가 아니다 — {order}"
    )


@pytest.mark.asyncio
async def test_g4_6_boot_is_not_held_beyond_the_budget(dbf, monkeypatch):
    """확정이 끝나지 않아도 부팅은 예산에서 prepare 로 간다(매수를 막지 않는다 · fail-open)."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from src.engine import boot_manager

    hang = asyncio.Event()
    order: list[str] = []

    async def _hanging_finalize(*_a, **_k):
        await hang.wait()

    monkeypatch.setattr(dbf, "finalize_once", _hanging_finalize)
    monkeypatch.setattr(dbf, "BOOT_BUDGET_SECS", 0.1)
    monkeypatch.setattr(boot_manager, "BOOT_BUDGET_SECS", 0.1, raising=False)

    class _S:
        strategy_id = "vb"

        async def prepare(self, *a, **k):
            order.append("prepare")

    s = MagicMock()
    s._preissue_all_tokens = AsyncMock()
    s._load_strategy_config = AsyncMock()
    s._refresh_market_regime_and_persist = AsyncMock()
    s._resolve_cash_usage_ratio = AsyncMock(return_value=1.0)
    s.registry = MagicMock()
    s.registry.enabled = MagicMock(return_value=[_S()])
    summary = MagicMock(net_asset=1_000_000)
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    with patch.object(boot_manager, "get_balance", AsyncMock(return_value=([], summary))), \
            patch.object(boot_manager, "token_manager") as tm, \
            patch.object(boot_manager, "get_daily_orders", AsyncMock(return_value=[])), \
            patch("src.db.stock_master.count_active", AsyncMock(return_value=100)), \
            patch.object(boot_manager, "emit_daily_head_staleness", AsyncMock()), \
            patch.object(boot_manager, "write_log", AsyncMock()):
        tm.get_token = AsyncMock()
        try:
            await asyncio.wait_for(boot_manager.boot(s), timeout=10)
        except asyncio.TimeoutError:
            pytest.fail("확정이 끝나지 않자 부팅이 멈췄다 — 예산이 없다")
        except Exception:
            pass
    try:
        assert order == ["prepare"], f"prepare 가 돌지 않았다 — {order}"
        assert loop.time() - t0 < 5, "부팅이 예산을 크게 넘겨 기다렸다"
    finally:
        hang.set()
        for t in list(getattr(dbf, "_BG_TASKS", ())):
            t.cancel()
        await asyncio.sleep(0)
