"""cycle253 Red — KRX 단독 채널(H0STCNT0) 다크런치 프로브 엔드포인트 계약.

> 정본 명세: `spec_cycle253_channel_probe.md` §1(범위) / §2(Red P1~P8)
> 포렌식 근거: `_workspace/forensics/stale_candidates_0904.md` ⑥-1
> 설계 메모: `_workspace/forensics/krx_channel_probe_design.md` §2

## 이 엔드포인트가 답하려는 단 하나의 질문

"`H0STCNT0` 가 `nxt_tradable=False`(KRX 단독) 종목의 체결 프레임을 **실제로** 송출하는가."
나흘 실측이 확정한 것은 "통합 채널 `H0UNCNT0` 은 안 보낸다"까지이고, "KRX 단독 채널은
보낸다"는 **기대이지 실측이 아니다**. 이 답 없이 B(속성 기반 채널 리졸버, 8영역 4파일)를
착수하면 8영역 승인·sha 재핀·뮤테이션 비용을 가설 위에 얹는 것이다.

## 이 파일이 봉인하는 계약 (이름·형태가 다르면 FAIL)

`src/routes/realtime.py`
  * `POST   /api/realtime/channel-probe`      — 프로브 시작 (허용 tr_id = H0STCNT0 / H0NXCNT0)
  * `GET    /api/realtime/channel-probe`      — 상태 폴링 (구독 변경 0)
  * `DELETE /api/realtime/channel-probe/{ticker}` — 프로브 종료
  * 모듈 상태 `_channel_probes: dict[str, dict]`
  * 프로브 경로는 모듈 전역 `write_log` 를 **호출하지 않는다** — `src.` 로거의 INFO 는
    `main._DbLogHandler` 가 이미 system_logs 에 적재하므로 write_log 병행은 액션당 2행
    이중 INSERT(cycle72 G-6 의 결함 그 자체, Verify F1). `write_log` seam 은 "0회" 단언용.

## Verify 시정 회귀 (2026-09-05)

F1 이중 INSERT(P1/P11) · F2 `price` 생산 키(P5) · F3 HIGH 승격 고아 + 라이브 LOW 억제
(P6b/P6c, 실 풀) · F5 전날 등록부 축출(P10) · F6 스윙 후보 게이트(P3h) · F7 `subscribed`
튜플 키 판정(P5b) · F9 `subscribe_dropped`(P9a/P9b).

## 왜 배제 조건이 계약의 본체인가

`WebsocketPool._ticker_to_session` 은 **tr_key 단일 키**다. 같은 종목이 이미 `H0UNCNT0`
로 구독돼 있으면 프로브 구독이 그 라우팅 맵을 덮어써 라이브 시세 경로를 훔친다. 그리고
프레임이 실제로 오면 `risk.on_tick` 이 그대로 도므로, 프로브 종목이 매수 후보였다면
**실매수 신호가 난다**. 그래서 409 거부 5종(already_probing / already_tick_subscribed /
held_or_pending_clear / in_desired_universe / probe_cap)은 편의가 아니라 안전 장치다 —
하나라도 지워지면 다크런치 프로브가 라이브 매매를 건드리는 경로가 열린다.

`bypass_limit=True` 금지도 같은 급이다(진단 도구가 HIGH 보유 종목의 41 슬롯을 밀어낸다).

검증 패턴 = TestClient(`tests/unit/routes/test_cycle249_log_reports_bundle_external.py`)
+ `tests/conftest.py::_neutralize_api_auth`(autouse 인증 중립화). 상태 코드(422/409/400/404)가
계약의 일부라 라우트 함수 직접 await(사이클 127/186/239 패턴)로는 422 를 잴 수 없다.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

PROBE = "/api/realtime/channel-probe"
LOGGER_NAME = "src.routes.realtime"

#: 프로브 표본 = 삼성전자우. 포렌식 ②-1 의 `nxt_tradable=False` × 거래대금 3,538억
#: (침묵이 아니라 채널 결함임을 증명한 대표 종목).
PROBE_TICKER = "005935"
#: 라이브 통합 채널 구독 표본 = 삼성전자(`nxt_tradable=True`, 프레임 20,781건/일).
LIVE_TICKER = "005930"


# ===========================================================================
# 대역 — 풀 / 스케줄러
# ===========================================================================
class _FakeSession:
    """`KisWebSocket` 대역 — 라우트가 읽는 3 필드 + `unsubscribe`(세션 전수 순회 해제 경로)."""

    def __init__(
        self, label: str, *, ws: object | None, pool: "_FakePool | None" = None
    ) -> None:
        self._label = label
        self._ws = ws
        self._pool = pool
        self._subscriptions: set[tuple[str, str]] = set()
        self._subscriptions_acked: set[tuple[str, str]] = set()

    async def unsubscribe(self, tr_id: str, tr_key: str) -> None:
        """실 `KisWebSocket.unsubscribe` 와 같은 효과 — 두 set 에서 discard."""
        self._subscriptions.discard((tr_id, tr_key))
        self._subscriptions_acked.discard((tr_id, tr_key))
        if self._pool is not None:
            self._pool.unsubscribe_calls.append((tr_id, tr_key))


class _FakePool:
    """`WebsocketPool` 대역.

    `_subscriptions` / `_subscriptions_acked` 를 **실제 풀과 같은 프로퍼티(전 세션 합집합)**
    로 제공한다 — 구현이 `pool._subscriptions` 를 보든 `[pool._main, *pool._quotes]` 를
    순회하든 어느 쪽이든 같은 답이 나오게 해서, 이 파일이 배선 형태를 강제하지 않는다.

    `subscribe` 는 실 풀의 세 결과를 흉내 낸다 — 정상(튜플 추가 + `_ticker_to_session`
    기록) / `subscribe_result=None`(전 세션 만석 drop) / `add_tuple=False`(잔존 라우팅
    LOW noop — label 만 돌려주고 튜플 미추가, Verify F9 E6).
    `unsubscribe_calls` 는 **세션** `unsubscribe` 기록(실제 해제), `unsubscribe_in_pool_calls`
    는 라우트가 써서는 안 되는 경로의 기록(Verify F3 — 승격된 라이브 라우팅 pop).
    """

    def __init__(self) -> None:
        self._main = _FakeSession("main", ws=object(), pool=self)
        self._quotes: list[_FakeSession] = [_FakeSession("quote-1", ws=object(), pool=self)]
        self._ticker_to_session: dict[str, _FakeSession] = {}
        self.subscribe_calls: list[dict] = []
        self.unsubscribe_calls: list[tuple[str, str]] = []
        self.unsubscribe_in_pool_calls: list[tuple[str, str]] = []
        self.subscribe_result: str | None = "quote-1"
        self.add_tuple: bool = True

    # -- 라우트가 읽는 뷰 ------------------------------------------------
    @property
    def _ws(self):
        return self._main._ws

    @property
    def _subscriptions(self) -> set[tuple[str, str]]:
        out: set[tuple[str, str]] = set()
        for ws in [self._main, *self._quotes]:
            out |= ws._subscriptions
        return out

    @property
    def _subscriptions_acked(self) -> set[tuple[str, str]]:
        out: set[tuple[str, str]] = set()
        for ws in [self._main, *self._quotes]:
            out |= ws._subscriptions_acked
        return out

    def get_subscribed_tickers(self) -> set[str]:
        from src.engine.scanner import TICK_TR_ID

        return {k for tr_id, k in self._subscriptions if tr_id == TICK_TR_ID}

    def get_acked_tickers(self) -> set[str]:
        from src.engine.scanner import TICK_TR_ID

        return {k for tr_id, k in self._subscriptions_acked if tr_id == TICK_TR_ID}

    def get_session_status(self) -> list[dict]:
        from src.engine.scanner import TICK_TR_ID

        return [
            {
                "label": ws._label,
                "tickers": {
                    "subscribed": sorted(
                        k for t, k in ws._subscriptions if t == TICK_TR_ID
                    ),
                    "acked": sorted(
                        k for t, k in ws._subscriptions_acked if t == TICK_TR_ID
                    ),
                },
            }
            for ws in [self._main, *self._quotes]
        ]

    # -- 라우트가 호출하는 변경 경로 --------------------------------------
    async def subscribe(
        self,
        tr_id: str,
        tr_key: str,
        *,
        priority: str = "LOW",
        bypass_limit: bool = False,
    ) -> str | None:
        self.subscribe_calls.append(
            {
                "tr_id": tr_id,
                "tr_key": tr_key,
                "priority": priority,
                "bypass_limit": bypass_limit,
            }
        )
        if self.subscribe_result is None:
            return None  # 전 세션 만석 — 실 풀은 구독 없이 None
        if not self.add_tuple:
            return self.subscribe_result  # 잔존 라우팅 LOW noop — 구독 없이 label 만
        target = self._quotes[0] if self._quotes else self._main
        target._subscriptions.add((tr_id, tr_key))
        self._ticker_to_session[tr_key] = target
        return self.subscribe_result

    async def unsubscribe_in_pool(self, tr_id: str, tr_key: str) -> None:
        """라우트가 **쓰면 안 되는** 경로 — 기록만 남기고 아무것도 해제하지 않는다.

        실 풀의 이 함수는 `_ticker_to_session.pop(ticker)` 한 세션에서만 해제하므로,
        HIGH 승격 뒤에는 고아를 못 지우면서 라이브 라우팅만 지운다(Verify F3).
        """
        self.unsubscribe_in_pool_calls.append((tr_id, tr_key))


class _FakeStrategy:
    def __init__(self, positions: dict[str, object] | None = None) -> None:
        self.state = type("_S", (), {})()
        self.state.positions = dict(positions or {})


class _FakeRegistry:
    def __init__(self) -> None:
        self._strategies: list[_FakeStrategy] = [_FakeStrategy()]

    def all(self) -> list[_FakeStrategy]:
        return list(self._strategies)


class _FakeScheduler:
    """`trading_scheduler` 대역 — 라우트가 배제 판정에 쓰는 3 소스만."""

    def __init__(self) -> None:
        self.registry = _FakeRegistry()
        self._pending_next_day_clear: set[tuple[str, str]] = set()
        self.breakout: list[str] = []
        self.swing: list[str] = []

    def _collect_breakout_tickers(self) -> list[str]:
        return list(self.breakout)

    def _collect_swing_tickers(self) -> list[str]:
        return list(self.swing)


class _Env:
    def __init__(self, pool, scheduler, scanner, write_logs) -> None:
        self.pool = pool
        self.scheduler = scheduler
        self.scanner = scanner
        self.write_logs = write_logs

    def hold(self, ticker: str) -> None:
        self.scheduler.registry._strategies[0].state.positions[ticker] = object()


# ===========================================================================
# 픽스처
# ===========================================================================
@pytest.fixture(autouse=True)
def _reset_probe_state():
    """모듈 상태 `_channel_probes` + 프로브 제외 등록 격리.

    🔴 cycle293 Green (적대 검증 HIGH) — `PROBE_EXCLUDED_TUPLES` 도 함께 비운다.
    이 파일의 `test_p1c_*` 가 `("H0NXCNT0","005935")` 를 넣고 회수하지 않아
    **다음 파일로 새고 있었다**: `tests/unit/routes` 를 `tests/unit/engine` 보다
    먼저 수집하는 순서에서 `test_g5_pool_aggregation_keeps_all_three_channels`
    가 005935 소실로 붉어졌다(기본 알파벳 순서에서는 잠복, 3덩어리 분할 실행은
    프로세스가 갈려 구조적으로 못 본다). 검증 신호까지 오염시켰다 — 뮤테이션
    2건이 이 누수 때문에 "KILLED" 로 잘못 보고됐다.
    """
    import src.routes.realtime as rt

    def _clear() -> None:
        probes = getattr(rt, "_channel_probes", None)
        if isinstance(probes, dict):
            probes.clear()
        try:
            from src.realtime.websocket import reset_probe_exclusions

            reset_probe_exclusions()
        except Exception:  # pragma: no cover — Red 단계 graceful
            pass

    _clear()
    yield
    _clear()


@pytest.fixture
def client() -> TestClient:
    from src.main import app

    return TestClient(app)


def _patch_write_log(monkeypatch, *, raises: bool = False) -> list[tuple[str, str]]:
    """`write_log` seam — 라우트 모듈 전역 이름 하나만 갈아끼운다."""
    import src.routes.realtime as rt

    calls: list[tuple[str, str]] = []

    async def _fake(level, message):
        calls.append((level, message))
        if raises:
            raise RuntimeError("write_log down (P7)")

    monkeypatch.setattr(rt, "write_log", _fake, raising=False)
    return calls


@pytest.fixture
def env(monkeypatch) -> _Env:
    import src.engine.scanner as scanner
    import src.engine.scheduler as scheduler_mod
    import src.realtime.websocket_pool as wsp

    pool = _FakePool()
    monkeypatch.setattr(wsp, "kis_ws_pool", pool, raising=False)

    sched = _FakeScheduler()
    monkeypatch.setattr(scheduler_mod, "trading_scheduler", sched, raising=False)
    monkeypatch.setattr(scanner, "_last_scan_result", [], raising=False)

    # 모듈 전역 dict — 스냅샷 후 복원 (다른 테스트 오염 금지)
    tick_backup = dict(scanner.ticker_last_tick)
    price_backup = dict(scanner.ticker_prices)
    scanner.ticker_last_tick.clear()
    scanner.ticker_prices.clear()

    # cycle227 leaf — acml_vol 관측 상태 격리 (price.acml_vol 의 유일 소스)
    from src.engine import tick_volume

    tick_volume.reset_for_test()

    logs = _patch_write_log(monkeypatch)

    yield _Env(pool=pool, scheduler=sched, scanner=scanner, write_logs=logs)

    scanner.ticker_last_tick.clear()
    scanner.ticker_last_tick.update(tick_backup)
    scanner.ticker_prices.clear()
    scanner.ticker_prices.update(price_backup)
    tick_volume.reset_for_test()


# ===========================================================================
# 헬퍼
# ===========================================================================
def _status(resp, expected: int, what: str) -> dict:
    assert resp.status_code == expected, (
        f"{what} — 기대 {expected}, 실제 {resp.status_code}. body={resp.text[:400]}"
    )
    return resp.json()


def _detail(resp) -> str:
    try:
        return str(resp.json().get("detail"))
    except Exception:  # pragma: no cover - 방어
        return resp.text


def _start(client, ticker: str = PROBE_TICKER, tr_id: str | None = "H0STCNT0"):
    body: dict = {"ticker": ticker}
    if tr_id is not None:
        body["tr_id"] = tr_id
    return client.post(PROBE, json=body)


def _rows(client) -> dict[str, dict]:
    data = _status(client.get(PROBE), 200, "GET channel-probe")["data"]
    assert isinstance(data.get("probes"), list), f"probes 누락: {data}"
    assert data.get("count") == len(data["probes"]), "count ↔ probes 길이 불일치"
    return {row["ticker"]: row for row in data["probes"]}


# ===========================================================================
# P1 — 정상 start
# ===========================================================================
def test_p1_start_when_clean_then_subscribes_low_without_bypass(client, env, caplog):
    """POST 는 `subscribe(tr_id, ticker, priority="LOW", bypass_limit=False)` 정확히 1회.

    `bypass_limit=True` 는 HIGH(보유·익일청산) 슬롯을 밀어내는 경로다 — 진단 도구가
    손절 시세를 굶기면 안 된다.
    """
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = _start(client)

    body = _status(resp, 200, "정상 프로브 시작")
    assert body["success"] is True
    data = body["data"]

    assert data["ticker"] == PROBE_TICKER
    assert data["tr_id"] == "H0STCNT0"
    assert data["session_label"] == "quote-1"
    assert data["first_tick_at"] is None, "시작 시점에 first_tick_at 이 채워지면 안 된다"

    started = datetime.fromisoformat(data["started_at"])
    assert started.utcoffset() == timedelta(hours=9), (
        f"started_at 은 KST(+09:00) 명시 iso 여야 한다 — {data['started_at']}"
    )

    assert len(env.pool.subscribe_calls) == 1, env.pool.subscribe_calls
    call = env.pool.subscribe_calls[0]
    assert call["tr_id"] == "H0STCNT0"
    assert call["tr_key"] == PROBE_TICKER
    assert call["priority"] == "LOW", "프로브는 LOW — HIGH 승격은 메인 슬롯 강탈"
    assert call["bypass_limit"] is False, "bypass_limit=True 금지 (41 cap 우회)"

    msgs = [r.getMessage() for r in caplog.records]
    assert any(
        "[krx_channel_probe] action=start" in m
        and PROBE_TICKER in m
        and "H0STCNT0" in m
        for m in msgs
    ), f"start 로그 서식 불일치 — {msgs}"

    # 영구 기록은 logger.info 한 줄 — write_log 병행은 액션당 2행 이중 INSERT (Verify F1)
    assert env.write_logs == [], (
        "프로브 경로가 write_log 를 호출했다 — `src.` 로거 INFO 는 `_DbLogHandler` 가 이미 "
        f"system_logs 에 적재한다(cycle72 G-6 이중 INSERT) — {env.write_logs}"
    )


def test_p1b_start_when_tr_id_omitted_then_defaults_to_h0stcnt0(client, env):
    """tr_id 기본값 = `H0STCNT0` (프로브의 존재 이유인 채널)."""
    body = _status(_start(client, tr_id=None), 200, "tr_id 생략 기본값")
    assert body["data"]["tr_id"] == "H0STCNT0"
    assert env.pool.subscribe_calls[0]["tr_id"] == "H0STCNT0"


def test_p1c_start_when_nxt_channel_then_allowed(client, env):
    """허용 집합 = {H0STCNT0, H0NXCNT0} — NXT 단독 채널도 프로브 대상."""
    body = _status(_start(client, tr_id="H0NXCNT0"), 200, "H0NXCNT0 허용")
    assert body["data"]["tr_id"] == "H0NXCNT0"
    assert env.pool.subscribe_calls[0]["tr_id"] == "H0NXCNT0"


# ===========================================================================
# P2 — 422 (입력 계약)
# ===========================================================================
@pytest.mark.parametrize(
    "payload, why",
    [
        (
            {"ticker": PROBE_TICKER, "tr_id": "H0UNCNT0"},
            "라이브 통합 채널 — `_ticker_to_session` 단일 키를 덮어써 라이브 경로를 훔친다",
        ),
        ({"ticker": PROBE_TICKER, "tr_id": "H0STCNI0"}, "체결통보 TR — 시세 채널 아님"),
        ({"ticker": PROBE_TICKER, "tr_id": ""}, "빈 tr_id"),
        ({"ticker": "00593"}, "5자리"),
        ({"ticker": "ABC123"}, "영문 포함 (ETF·신주인수권 진입 차단 규약과 동일)"),
    ],
)
def test_p2_start_when_invalid_input_then_422_and_no_subscribe(
    client, env, payload, why
):
    resp = client.post(PROBE, json=payload)
    assert resp.status_code == 422, (
        f"입력 거부 실패({why}) — payload={payload} status={resp.status_code} "
        f"body={resp.text[:300]}"
    )
    assert env.pool.subscribe_calls == [], "거부된 요청이 구독을 발사했다"


# ===========================================================================
# P3 — 409 (배제 조건 5종)
# ===========================================================================
def test_p3a_start_when_already_probing_then_409(client, env):
    _status(_start(client), 200, "1차 프로브")
    resp = _start(client)
    _status(resp, 409, "중복 프로브")
    assert "already_probing" in _detail(resp)
    assert len(env.pool.subscribe_calls) == 1, "중복 요청이 구독을 또 발사했다"


def test_p3b_start_when_already_tick_subscribed_then_409(client, env):
    """이미 `H0UNCNT0` 로 구독 중 — 프로브가 라우팅 맵을 덮어쓰면 라이브 시세가 끊긴다."""
    from src.engine.scanner import TICK_TR_ID

    env.pool._main._subscriptions.add((TICK_TR_ID, PROBE_TICKER))

    resp = _start(client)
    _status(resp, 409, "라이브 TICK 구독 종목")
    assert "already_tick_subscribed" in _detail(resp)
    assert env.pool.subscribe_calls == []


def test_p3c_start_when_held_then_409(client, env):
    """보유 종목 — 프레임이 오면 `risk.on_tick` 이 그대로 돌아 청산 평가에 개입한다."""
    env.hold(PROBE_TICKER)

    resp = _start(client)
    _status(resp, 409, "보유 종목")
    assert "held_or_pending_clear" in _detail(resp)
    assert env.pool.subscribe_calls == []


def test_p3d_start_when_pending_next_day_clear_then_409(client, env):
    """익일 청산 대기 — HIGH 보장 대상이라 프로브가 세션을 흔들면 안 된다."""
    env.scheduler._pending_next_day_clear.add((PROBE_TICKER, "donchian_swing"))

    resp = _start(client)
    _status(resp, 409, "익일청산 대기 종목")
    assert "held_or_pending_clear" in _detail(resp)
    assert env.pool.subscribe_calls == []


def test_p3e_start_when_in_breakout_universe_then_409(client, env):
    """브레이크아웃 후보 — 프레임 수신 시 **실매수 신호**가 날 수 있는 경로."""
    env.scheduler.breakout = [PROBE_TICKER]

    resp = _start(client)
    _status(resp, 409, "브레이크아웃 후보")
    assert "in_desired_universe" in _detail(resp)
    assert env.pool.subscribe_calls == []


def test_p3f_start_when_in_last_scan_result_then_409(client, env, monkeypatch):
    """모멘텀 스캔 결과도 같은 매수 경로다."""
    monkeypatch.setattr(env.scanner, "_last_scan_result", [PROBE_TICKER], raising=False)

    resp = _start(client)
    _status(resp, 409, "모멘텀 스캔 후보")
    assert "in_desired_universe" in _detail(resp)
    assert env.pool.subscribe_calls == []


def test_p3h_start_when_in_swing_candidates_then_409(client, env):
    """스윙 후보(donchian/kojiro `_candidates`)도 desired 다 (Verify F6).

    첫 `_scan_loop` 뒤에는 TICK 집합 밖이라 `already_tick_subscribed` 검사로는 새지만,
    프레임이 오면 09:05~09:30 창에서 tick 경로 BUY 가 구조적으로 가능하다.
    """
    env.scheduler.swing = [PROBE_TICKER]

    resp = _start(client)
    _status(resp, 409, "스윙 후보")
    assert "in_desired_universe" in _detail(resp)
    assert env.pool.subscribe_calls == []


def test_p3g_start_when_cap_exceeded_then_409(client, env):
    """동시 프로브 상한 3 — 진단 도구가 슬롯 예산을 잠식하지 않게."""
    for ticker in ("005935", "000815", "003490"):
        _status(_start(client, ticker=ticker), 200, f"프로브 {ticker}")

    resp = _start(client, ticker="034020")
    _status(resp, 409, "4번째 프로브")
    assert "probe_cap" in _detail(resp)
    assert len(env.pool.subscribe_calls) == 3, "cap 초과 요청이 구독을 발사했다"


# ===========================================================================
# P4 — 400 (WebSocket 끊김)
# ===========================================================================
def test_p4_start_when_main_ws_none_then_400(client, env):
    """메인 `_ws is None` → 400 (기존 `/resubscribe` 규약 — 조용한 200 금지)."""
    env.pool._main._ws = None

    resp = _start(client)
    _status(resp, 400, "WebSocket 끊김")
    assert env.pool.subscribe_calls == []


# ===========================================================================
# P5 — GET (수신 판정)
# ===========================================================================
def test_p5_get_reports_freshness_and_pins_first_tick(client, env):
    """`received` 는 **`started_at` 기준** 이고 `first_tick_at` 은 한 번 고정되면 불변.

    구독 이전의 잔존 `ticker_last_tick` 값을 수신으로 세면 프로브가 자기 가설을
    스스로 확증한다 — 이 사이클이 답하려는 질문 자체가 무의미해진다.
    """
    from src.engine.scanner import TICK_TR_ID

    with freeze_time("2026-09-07 00:30:00") as frozen:  # KST 09:30:00
        data = _status(_start(client), 200, "프로브 시작")["data"]
        started = datetime.fromisoformat(data["started_at"])

        # (1) 틱 없음 — received False / last_tick_at None / age_secs None
        row = _rows(client)[PROBE_TICKER]
        for key in (
            "ticker", "tr_id", "started_at", "session_label", "subscribed", "acked",
            "last_tick_at", "age_secs", "first_tick_at", "received", "price",
            "live_tick_subscribed", "in_desired_now",
        ):
            assert key in row, f"GET row 키 누락 — {key}: {row}"
        assert row["received"] is False
        assert row["last_tick_at"] is None
        assert row["age_secs"] is None
        assert row["first_tick_at"] is None
        assert row["price"] in (None, {}), f"틱 전 price 노출: {row['price']}"
        # 프로브 시작 시점 = 라이브 TICK 집합·desired 밖 (POST 게이트가 보장한 상태)
        assert row["live_tick_subscribed"] is False
        assert row["in_desired_now"] is False

        # subscribed / acked 는 (tr_id, ticker) 튜플 존재로 판정 — H0UNCNT0 튜플은 무시
        assert row["subscribed"] is True, "프로브 튜플이 세션에 있는데 subscribed=False"
        assert row["acked"] is False

        # 같은 종목의 **H0UNCNT0 튜플은 판정에 쓰이지 않는다** (tr_id 쌍으로 판정)
        # — 대신 라이브 편입은 `live_tick_subscribed` 로 드러난다 (Verify F3 가시화)
        env.pool._main._subscriptions.add((TICK_TR_ID, PROBE_TICKER))
        env.pool._main._subscriptions_acked.add((TICK_TR_ID, PROBE_TICKER))
        row = _rows(client)[PROBE_TICKER]
        assert row["acked"] is False, "H0UNCNT0 ACK 튜플을 프로브 ACK 으로 오인했다"
        assert row["live_tick_subscribed"] is True, "라이브 TICK 편입이 GET 에 보이지 않는다"

        # desired 편입도 같은 방식으로 드러난다 (프로브 시작 **후** 후보 편입 = 즉시 DELETE 신호)
        env.scheduler.breakout = [PROBE_TICKER]
        assert _rows(client)[PROBE_TICKER]["in_desired_now"] is True
        env.scheduler.breakout = []
        assert _rows(client)[PROBE_TICKER]["in_desired_now"] is False

        env.pool._quotes[0]._subscriptions_acked.add(("H0STCNT0", PROBE_TICKER))
        assert _rows(client)[PROBE_TICKER]["acked"] is True

        # (2) 구독 **이전** 잔존값 — 수신이 아니다
        env.scanner.ticker_last_tick[PROBE_TICKER] = started - timedelta(seconds=60)
        row = _rows(client)[PROBE_TICKER]
        assert row["received"] is False, "started_at 이전 잔존 틱을 수신으로 셌다"
        assert row["last_tick_at"] == (started - timedelta(seconds=60)).isoformat()
        assert row["age_secs"] == 60
        assert row["first_tick_at"] is None

        # (3) 첫 실수신 — received True + first_tick_at 고정
        frozen.tick(120)  # now = 09:32:00
        first_tick = started + timedelta(seconds=60)  # 09:31:00
        env.scanner.ticker_last_tick[PROBE_TICKER] = first_tick
        # 생산 키 그대로 — `risk.on_tick` 이 쓰는 4키. `acml_vol` 은 여기 **없다**
        # (P0-1 확정 사실: tick_volume leaf 로만 흐른다). 미끼 키 `acml_vol` 은 무시돼야 한다.
        env.scanner.ticker_prices[PROBE_TICKER] = {
            "current_price": 61000, "open_price": 60500, "change_rate": 0.83,
            "prdy_ctrt": 0.83, "acml_vol": 999,
        }

        row = _rows(client)[PROBE_TICKER]
        assert row["received"] is True
        assert row["last_tick_at"] == first_tick.isoformat()
        assert row["first_tick_at"] == first_tick.isoformat()
        assert row["age_secs"] == 60
        assert row["price"] == {"price": 61000, "acml_vol": None, "open_price": 60500}, (
            "price 는 ticker_prices 의 `current_price`/`open_price` 를 읽어야 한다(`price` "
            "키는 운영에 존재하지 않아 항상 null — Verify F2) + acml_vol 은 ticker_prices "
            f"가 아니라 tick_volume 관측값만 — {row['price']}"
        )

        # acml_vol 의 유일 소스 = cycle227 tick_volume leaf
        from src.engine import tick_volume

        tick_volume.record_acml_vol(PROBE_TICKER, 12345)
        row = _rows(client)[PROBE_TICKER]
        assert row["price"] == {"price": 61000, "acml_vol": 12345, "open_price": 60500}, (
            "price 는 price/acml_vol/open_price 세 키만 — 틱 dict 통째 노출 금지(09-09 "
            f"채널 시가 비교용 open_price 추가) — {row['price']}"
        )

        # (4) 이후 틱이 더 뒤로 가도 first_tick_at 은 불변 (폴링 기반 근사의 정본)
        frozen.tick(60)  # now = 09:33:00
        later = started + timedelta(seconds=150)  # 09:32:30
        env.scanner.ticker_last_tick[PROBE_TICKER] = later

        row = _rows(client)[PROBE_TICKER]
        assert row["received"] is True
        assert row["last_tick_at"] == later.isoformat()
        assert row["first_tick_at"] == first_tick.isoformat(), (
            "first_tick_at 이 갱신되면 '첫 프레임 시각' 이라는 의미가 사라진다"
        )
        assert row["age_secs"] == 30

    # GET 은 읽기 전용 — 구독을 건드리지 않는다
    assert len(env.pool.subscribe_calls) == 1
    assert env.pool.unsubscribe_calls == []


# ===========================================================================
# P6 — DELETE
# ===========================================================================
def test_p6_delete_unsubscribes_and_clears_state(client, env, caplog):
    with freeze_time("2026-09-07 00:30:00") as frozen:
        data = _status(_start(client), 200, "프로브 시작")["data"]
        started = datetime.fromisoformat(data["started_at"])
        frozen.tick(120)
        env.scanner.ticker_last_tick[PROBE_TICKER] = started + timedelta(seconds=60)

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            resp = client.delete(f"{PROBE}/{PROBE_TICKER}")

        body = _status(resp, 200, "프로브 종료")
        assert body["success"] is True
        assert body["data"]["ticker"] == PROBE_TICKER
        assert body["data"]["tr_id"] == "H0STCNT0"
        assert body["data"]["received"] is True
        assert body["data"]["removed_from"] == ["quote-1"], body["data"]

        # 해제는 **세션** unsubscribe(tr_id, ticker) — 튜플을 가진 세션에서 정확히 1회
        assert env.pool.unsubscribe_calls == [("H0STCNT0", PROBE_TICKER)], (
            f"세션 unsubscribe 미호출/오호출 — {env.pool.unsubscribe_calls}"
        )
        # `unsubscribe_in_pool` 금지 — HIGH 승격 뒤 고아를 못 지우면서 라이브 라우팅을 pop (Verify F3)
        assert env.pool.unsubscribe_in_pool_calls == [], (
            f"DELETE 가 unsubscribe_in_pool 을 썼다 — {env.pool.unsubscribe_in_pool_calls}"
        )
        assert PROBE_TICKER not in env.pool._ticker_to_session, "프로브 라우팅 잔존 — 라이브 LOW 억제"

        assert _rows(client) == {}, "DELETE 후에도 상태가 남아 있다"

        # 두 번째 DELETE — 404
        _status(client.delete(f"{PROBE}/{PROBE_TICKER}"), 404, "없는 프로브 종료")
        assert len(env.pool.unsubscribe_calls) == 1, "404 경로가 해제를 또 발사했다"

    msgs = [r.getMessage() for r in caplog.records]
    assert any(
        "[krx_channel_probe] action=stop" in m
        and "received=" in m
        and "first_tick_at=" in m
        for m in msgs
    ), f"stop 로그 서식 불일치 — {msgs}"


# ===========================================================================
# P7 — 영구 기록 = logger.info 단독 (write_log 0회) — Verify F1
# ===========================================================================
def test_p7_probe_persists_via_logger_only_and_never_calls_write_log(
    client, env, monkeypatch, caplog
):
    """`src.` 로거의 INFO 이상은 `main._DbLogHandler` 가 system_logs 에 적재한다.

    같은 내용을 `write_log` 로 또 쓰면 액션당 2행이다(메시지가 `[src.routes.realtime] `
    접두 유무로 달라 500ms dedupe 도 비껴간다) — cycle72 G-6 이 막는 이중 INSERT 그
    자체. 계약 = (1) 프로브 경로는 write_log 0회 (2) start/stop 레코드가 `_DbLogHandler`
    수용 조건(로거 이름 `src.` 접두 + INFO 이상)을 만족하고 실제 핸들러가 큐에 각 1행씩
    적재한다. write_log seam 이 예외를 던지게 두어도 행위는 무영향이어야 한다.
    """
    import src.main as main_mod

    calls = _patch_write_log(monkeypatch, raises=True)

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        _status(_start(client), 200, "프로브 시작")
        _rows(client)
        _status(client.delete(f"{PROBE}/{PROBE_TICKER}"), 200, "프로브 종료")

    assert len(env.pool.subscribe_calls) == 1
    assert env.pool.unsubscribe_calls == [("H0STCNT0", PROBE_TICKER)]
    assert calls == [], f"프로브 경로가 write_log 를 호출했다 (이중 INSERT) — {calls}"

    probe_records = [r for r in caplog.records if "[krx_channel_probe]" in r.getMessage()]
    assert probe_records, "logger 기록 자체가 없다 — 영구 기록 소실"
    for r in probe_records:
        assert r.name.startswith("src."), f"_DbLogHandler 는 `src.` 로거만 적재 — {r.name}"
        assert r.levelno >= logging.INFO, f"_DbLogHandler 레벨(INFO) 미만 — {r.levelname}"

    # 실제 핸들러로 적재 확인 — 큐만 교체해 운영 큐 무접촉
    queue: asyncio.Queue = asyncio.Queue()
    monkeypatch.setattr(main_mod, "_LOG_QUEUE", queue)
    handler = main_mod._DbLogHandler()
    for r in probe_records:
        handler.emit(r)
    queued: list[tuple[str, str]] = []
    while not queue.empty():
        queued.append(queue.get_nowait())
    msgs = [m for _lv, m in queued]
    assert sum("action=start" in m for m in msgs) == 1, msgs
    assert sum("action=stop" in m for m in msgs) == 1, msgs
    assert all(lv == "INFO" for lv, _m in queued), queued


# ===========================================================================
# P8 — TICK 필터 격리 (실 WebsocketPool / KisWebSocket 인스턴스, 네트워크 0)
# ===========================================================================
class _FakeConn:
    """`ClientConnection` 대역 — `_send_subscribe` 가 부르는 `send` 만. 네트워크 0."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, payload: str) -> None:
        self.sent.append(payload)


def _real_pool():
    """실 `WebsocketPool` + 실 `KisWebSocket` 2세션 (`_ws` 만 대역)."""
    from src.realtime.websocket import KisWebSocket
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    main = KisWebSocket(is_main=True, label="main")
    main._ws = _FakeConn()
    quote = KisWebSocket(is_main=False, label="quote-1")
    quote._ws = _FakeConn()
    pool._main = main
    pool._quotes = [quote]
    pool._ticker_to_session = {}
    return pool


def test_p8a_tick_filter_excludes_probe_tuple_on_real_pool():
    """라우트 없이도 성립하는 **구조 사실** — TICK 집합 함수는 프로브를 뺀다.

    K stale watcher · universe guard · delta unsubscribe · F1 재검증이 전부 이
    필터를 지나므로, 프로브 튜플은 그 어느 경로에도 등장하지 않는다(재등록 대상
    아님 · 삭제 대상 아님 · stale 집계 밖).

    🔴 **의미 전환 (cycle293, 2026-09-14) — 격리 기준이 채널에서 프로브 정체성으로
    옮겨졌다.** 종전 계약은 "필터는 `tr_id` 로 자른다"(= `H0UNCNT0` 만 센다)였고 이
    테스트는 등록되지 않은 `("H0STCNT0", …)` 튜플이 집계 밖임을 단언했다. cycle293
    이 그 전용 채널을 **실제 구독**에 쓰기 시작하면서(§5-B — 실 구독이 집계에서
    사라지면 K stale watcher 가 그 종목을 영원히 못 보고 `[tick_coverage]` 분모만
    좋아진다) 채널 동일성으로는 프로브와 실 구독을 구분할 수 없게 됐다. 그래서
    격리는 `websocket.PROBE_EXCLUDED_TUPLES`(프로브 시작/종료가 유지)로 판정한다.

    아래 단언은 **두 방향을 함께** 잠근다 — (1) 등록된 프로브 튜플은 여전히 집계
    밖 (2) 등록되지 않은 전용 채널 튜플(= cycle293 의 실 구독)은 **반드시 집계 안**.
    (2)가 없으면 채널 기준 격리로 되돌아가도 이 테스트가 초록이 된다.
    """
    from src.engine.scanner import TICK_TR_ID
    from src.realtime.websocket import PROBE_EXCLUDED_TUPLES

    pool = _real_pool()
    pool._main._subscriptions.update(
        {(TICK_TR_ID, LIVE_TICKER), ("H0STCNT0", PROBE_TICKER)}
    )
    pool._main._subscriptions_acked.update(
        {(TICK_TR_ID, LIVE_TICKER), ("H0STCNT0", PROBE_TICKER)}
    )

    # (2) 프로브 등록 **전** — 전용 채널 구독은 실 구독으로 셈된다 (cycle293 §5-B)
    assert pool.get_subscribed_tickers() == {LIVE_TICKER, PROBE_TICKER}
    assert pool.get_acked_tickers() == {LIVE_TICKER, PROBE_TICKER}

    # (1) 프로브로 등록하면 집계 밖 — 라우트의 `_register_probe_exclusion` 과 동일
    PROBE_EXCLUDED_TUPLES.add(("H0STCNT0", PROBE_TICKER))
    try:
        assert pool.get_subscribed_tickers() == {LIVE_TICKER}
        assert pool.get_acked_tickers() == {LIVE_TICKER}
        for session in pool.get_session_status():
            assert PROBE_TICKER not in session["tickers"]["subscribed"]
            assert PROBE_TICKER not in session["tickers"]["acked"]
    finally:
        PROBE_EXCLUDED_TUPLES.discard(("H0STCNT0", PROBE_TICKER))

    # 슬롯은 정직하게 셈된다 (41 cap 은 tr_id 무관 `_subscriptions` 길이)
    assert len(pool._main._subscriptions) == 2


def test_p8b_started_probe_invisible_to_tick_filter_on_real_pool(
    client, env, monkeypatch
):
    """라우트가 실제 풀에 건 프로브가 TICK 뷰에 안 보인다 (격리 실증)."""
    import src.realtime.websocket_pool as wsp
    from src.engine.scanner import TICK_TR_ID

    pool = _real_pool()
    pool._main._subscriptions.add((TICK_TR_ID, LIVE_TICKER))
    pool._main._subscriptions_acked.add((TICK_TR_ID, LIVE_TICKER))
    monkeypatch.setattr(wsp, "kis_ws_pool", pool, raising=False)

    _status(_start(client), 200, "실 풀 프로브 시작")

    # 프로브 튜플은 실재한다
    tuples: set[tuple[str, str]] = set()
    for ws in [pool._main, *pool._quotes]:
        tuples |= ws._subscriptions
    assert ("H0STCNT0", PROBE_TICKER) in tuples, "실 풀에 프로브 구독이 걸리지 않았다"

    # 그러나 TICK 필터 뷰에는 없다
    assert pool.get_subscribed_tickers() == {LIVE_TICKER}
    assert PROBE_TICKER not in pool.get_acked_tickers()
    for session in pool.get_session_status():
        assert PROBE_TICKER not in session["tickers"]["subscribed"]

    # GET 은 원시 튜플을 보므로 프로브를 인지한다 (두 뷰의 분리가 계약)
    assert _rows(client)[PROBE_TICKER]["subscribed"] is True


# ===========================================================================
# Verify 시정 회귀 — F3 / F5 / F7 / F9
# ===========================================================================
def test_p5b_subscribed_is_keyed_by_tr_id_tuple_not_ticker(client, env):
    """뮤테이션 M16 봉인 (Verify F7) — `subscribed` 는 `(tr_id, ticker)` 튜플 판정.

    프로브 튜플이 사라지고 같은 종목의 H0UNCNT0 튜플만 남으면 False 여야 한다 — ticker
    단일 키로 판정하면 라이브 구독을 프로브 구독으로 오인해 "subscribed ∧ ¬received"
    반증 판독이 오염된다.
    """
    from src.engine.scanner import TICK_TR_ID

    _status(_start(client), 200, "프로브 시작")
    assert _rows(client)[PROBE_TICKER]["subscribed"] is True

    # 프로브 튜플 제거(20:00 unsubscribe_all 이후 상태) + 라이브 TICK 튜플만 존재
    for ws in [env.pool._main, *env.pool._quotes]:
        ws._subscriptions.discard(("H0STCNT0", PROBE_TICKER))
    env.pool._main._subscriptions.add((TICK_TR_ID, PROBE_TICKER))

    row = _rows(client)[PROBE_TICKER]
    assert row["subscribed"] is False, "H0UNCNT0 튜플을 프로브 구독으로 오인 (ticker 단일 키 판정)"
    assert row["live_tick_subscribed"] is True

    # 프로브 튜플 복귀 → 다시 True (반대 방향도 튜플 키)
    env.pool._quotes[0]._subscriptions.add(("H0STCNT0", PROBE_TICKER))
    assert _rows(client)[PROBE_TICKER]["subscribed"] is True


def test_p6b_delete_removes_orphan_tuple_after_high_promotion_on_real_pool(env, monkeypatch):
    """Verify F3 (실 풀 실증 E4 재현) — 프로브 중 같은 종목이 매수돼 HIGH 승격되면
    프로브 튜플이 보조 세션에 고아로 남고 라우팅은 main 을 가리킨다.

    DELETE 는 (1) 그 고아를 지우고 (2) main 의 라이브 튜플과 라우팅은 건드리지 않아야
    한다. `unsubscribe_in_pool` 은 정반대다 — 라우팅이 가리키는 main 에서만 해제를
    시도해 고아를 못 지우고, 승격된 라이브 종목의 라우팅을 pop 한다.
    핸들러를 한 이벤트 루프 안에서 직접 await 한다(사이클 127/186/239 패턴) — 실
    `KisWebSocket` 의 루프 바인딩 객체를 TestClient 루프와 섞지 않기 위해서다.
    """
    import src.realtime.websocket_pool as wsp
    import src.routes.realtime as rt
    from src.engine.scanner import TICK_TR_ID

    pool = _real_pool()
    monkeypatch.setattr(wsp, "kis_ws_pool", pool, raising=False)
    quote = pool._quotes[0]

    async def _scenario():
        await rt.start_channel_probe(rt.ChannelProbeIn(ticker=PROBE_TICKER))
        assert ("H0STCNT0", PROBE_TICKER) in quote._subscriptions, "전제: LOW 프로브는 보조 세션"
        assert pool._ticker_to_session[PROBE_TICKER] is quote

        # 체결 → order_engine 이 부르는 HIGH 승격 경로 (websocket_pool 무변경 사실의 재현)
        label = await pool.subscribe(
            TICK_TR_ID, PROBE_TICKER, priority="HIGH", bypass_limit=True,
        )
        assert label == "main"
        assert (TICK_TR_ID, PROBE_TICKER) in pool._main._subscriptions
        assert pool._ticker_to_session[PROBE_TICKER] is pool._main
        assert ("H0STCNT0", PROBE_TICKER) in quote._subscriptions, (
            "전제: 승격이 프로브 튜플을 보조 세션에 고아로 남긴다"
        )

        row = (await rt.get_channel_probes()).data["probes"][0]
        assert row["live_tick_subscribed"] is True, "라이브 편입이 GET 에 보이지 않는다"
        assert row["subscribed"] is True

        return (await rt.stop_channel_probe(PROBE_TICKER)).data

    data = asyncio.run(_scenario())

    assert data["removed_from"] == ["quote-1"], data
    assert ("H0STCNT0", PROBE_TICKER) not in quote._subscriptions, "고아 프로브 튜플 잔존"
    assert (TICK_TR_ID, PROBE_TICKER) in pool._main._subscriptions, "라이브 HIGH 튜플을 지웠다"
    assert pool._ticker_to_session.get(PROBE_TICKER) is pool._main, (
        "승격된 라이브 라우팅을 pop 했다 (unsubscribe_in_pool 결함)"
    )
    assert rt._channel_probes == {}


def test_p6c_delete_releases_routing_so_live_low_subscribe_resumes_on_real_pool(
    env, monkeypatch
):
    """Verify F3(1) — 프로브 중 같은 종목이 desired 에 편입되면 `_scan_loop` 의 LOW TICK
    구독이 `_ticker_to_session` 단일 키 때문에 무음 억제된다(label 만 반환, 튜플 없음).

    GET 은 이를 `in_desired_now ∧ ¬live_tick_subscribed` 로 드러내고, DELETE 뒤에는
    라우팅이 풀려 다음 LOW 구독이 **실제로** 걸려야 한다 — 라우팅을 남기면 억제가 20:00
    까지 이어진다.
    """
    import src.realtime.websocket_pool as wsp
    import src.routes.realtime as rt
    from src.engine.scanner import TICK_TR_ID

    pool = _real_pool()
    monkeypatch.setattr(wsp, "kis_ws_pool", pool, raising=False)

    async def _scenario():
        await rt.start_channel_probe(rt.ChannelProbeIn(ticker=PROBE_TICKER))
        env.scheduler.breakout = [PROBE_TICKER]  # 프로브 **이후** 후보 편입

        label = await pool.subscribe(
            TICK_TR_ID, PROBE_TICKER, priority="LOW", bypass_limit=False,
        )
        assert label is not None
        assert (TICK_TR_ID, PROBE_TICKER) not in pool._subscriptions, (
            "전제: 프로브 라우팅이 라이브 LOW 구독을 억제한다 (websocket_pool 무변경 사실)"
        )

        row = (await rt.get_channel_probes()).data["probes"][0]
        assert row["in_desired_now"] is True
        assert row["live_tick_subscribed"] is False, "억제된 편입이 GET 에 드러나야 한다"

        await rt.stop_channel_probe(PROBE_TICKER)
        assert PROBE_TICKER not in pool._ticker_to_session, (
            "DELETE 후 라우팅 잔존 — 라이브 LOW 억제가 20:00 까지 이어진다"
        )

        return await pool.subscribe(
            TICK_TR_ID, PROBE_TICKER, priority="LOW", bypass_limit=False,
        )

    label2 = asyncio.run(_scenario())
    assert label2 is not None
    assert (TICK_TR_ID, PROBE_TICKER) in pool._subscriptions, (
        "DELETE 후에도 라이브 LOW 구독이 걸리지 않는다"
    )


def test_p9a_start_when_pool_drops_then_409_and_no_state(client, env):
    """Verify F9 — 전 세션 만석이면 풀은 구독 없이 None 을 돌려준다. 200 + 상태 등록은 거짓."""
    env.pool.subscribe_result = None

    resp = _start(client)
    _status(resp, 409, "전 세션 만석 drop")
    assert "subscribe_dropped" in _detail(resp)
    assert len(env.pool.subscribe_calls) == 1
    assert _rows(client) == {}, "구독 0건인데 상태가 등록됐다"


def test_p9b_start_when_label_without_tuple_then_409_and_stale_routing_released(client, env):
    """Verify F9 (실 풀 E6) — `_ticker_to_session` 에 튜플 없는 잔존 라우팅이 있으면 LOW 는
    구독 없이 label 만 돌려준다. 409 + 미등록이어야 하고, 그 고아 라우팅(라이브 LOW 억제원)은
    함께 풀려야 한다.
    """
    env.pool.add_tuple = False
    env.pool._ticker_to_session[PROBE_TICKER] = env.pool._quotes[0]  # 튜플 없는 고아 라우팅

    resp = _start(client)
    _status(resp, 409, "튜플 없는 label")
    assert "subscribe_dropped" in _detail(resp)
    assert len(env.pool.subscribe_calls) == 1
    assert _rows(client) == {}, "구독 0건인데 상태가 등록됐다"
    assert PROBE_TICKER not in env.pool._ticker_to_session, "고아 라우팅 잔존 — 라이브 LOW 억제 지속"


def test_p10_post_evicts_previous_day_entries_but_keeps_today(client, env, caplog):
    """Verify F5 — 20:00 `unsubscribe_all` 은 구독 튜플만 지우고 `_channel_probes` 는 남긴다.

    그대로면 익일 같은 종목 POST 가 409 `already_probing` 이고 잔존 3건이 cap 을 채운다.
    POST 진입 시 전날(KST) 항목을 축출하되 **오늘** 항목은 건드리지 않는다. 튜플이 남아
    있던 항목(20:00 이후 시작)은 축출 시 세션 해제까지 시도한다.
    """
    with freeze_time("2026-09-07 00:30:00") as frozen:  # KST 09-07 09:30
        for t in ("005935", "000815", "003490"):
            _status(_start(client, ticker=t), 200, f"프로브 {t}")
        assert len(env.pool.subscribe_calls) == 3

        # 20:00 unsubscribe_all 재현 — 두 종목은 튜플 소실, 000815 는 튜플 잔존 가정
        for ws in [env.pool._main, *env.pool._quotes]:
            ws._subscriptions.discard(("H0STCNT0", "005935"))
            ws._subscriptions.discard(("H0STCNT0", "003490"))

        # 같은 날 재-POST 는 여전히 409 — 오늘 항목은 축출 대상이 아니다
        resp = _start(client, ticker="005935")
        _status(resp, 409, "같은 날 중복")
        assert "already_probing" in _detail(resp)

        frozen.tick(24 * 3600)  # 익일 09:30 KST
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            resp = _start(client, ticker="005935")
        _status(resp, 200, "익일 같은 종목 재프로브 — 전날 등록부 자동 축출")

        rows = _rows(client)
        assert set(rows) == {"005935"}, f"전날 항목 잔존 — {sorted(rows)}"
        assert len(env.pool.subscribe_calls) == 4
        assert ("H0STCNT0", "000815") in env.pool.unsubscribe_calls, (
            "튜플이 남은 전날 프로브를 축출하며 해제하지 않았다"
        )

    msgs = [r.getMessage() for r in caplog.records]
    evicts = [m for m in msgs if "[krx_channel_probe] action=evict" in m]
    assert len(evicts) == 3, evicts
    assert all("reason=stale_day" in m for m in evicts), evicts
