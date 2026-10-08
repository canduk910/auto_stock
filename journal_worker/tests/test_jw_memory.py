"""cycle412 보완 Red — 결함 1(높음·배포 차단): 짝짓기 보관 정책 — 메모리가 시간에 따라 늘지 않는다.

직전 판정: `jw/pairing.py` 가 G0 스냅샷 **원본**을 2000개까지 쌓았다가 1000개로 줄였다(1개 ≈114KB →
직전 228MB). 컨테이너 상한 160m 를 4~5시간마다 넘어 OOM → 재시작마다 링·짝짓기 대기분이 사라진다.
보완 결정(메인 세션) = 「개수 상한을 넣은 뒤 줄이기」가 아니라 **보관 정책 자체를 바꾼다** — 짝짓기에
필요한 것만 남긴다(전략·종목별 최근 신호 링 TTL 10분 · 직전 스냅샷의 필요한 칸 · 짝짓기 대기 항목 TTL).
전체 스냅샷 원본은 보관하지 않는다.

측정 = 객체 그래프 크기(`jw_testkit.retained_bytes` — root 에서 닿는 객체의 `sys.getsizeof` 합, 클래스·
모듈·함수·로거 제외). 같은 하루 패턴(08:00 부터 15초 간격 1500회전)을 되풀이하고 **하루 중 같은 시각**
(그날 500번째 회전)에서 잰다 — 하루 단위로 비우는 상태(그날 접수 전문·익일청산 보류 줄)는 날마다 같은
크기라 허용되고, 날을 넘어 쌓이는 것만 걸린다.

| # | 계약 |
|---|---|
| M1 | `Pairer` — N=500·2000·5000 회전 뒤 보관 크기가 같다(첫날 → 둘째 날 +25% 이내 · 둘째 날 → 넷째 날 +2% 이내) · 절대 2MB 미만 |
| M2 | 스냅샷 원본을 들고 있지 않다 — G0/G1 dict·목록과 짝짓기에 안 쓰는 칸의 값이 `Pairer` 에서 닿지 않는다 |
| M3 | `Worker` 전체(짝짓기 + 손절선 + 대사 누적 + 커서) 도 같은 조건에서 크기가 같다 |
| M4 | 과거분 모드(`source="log_restore"`)는 이 정책 밖이다 — 골든 3주를 한 번에 넣어도 외부 접수 전문 후보가 남는다(골든 P8 과 같은 사실) |
"""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta

import httpx
import pytest

from jw_testkit import (FakeJournalDB, golden_lines, jw, kst, log_line, parse_all, reachable_ids,
                        retained_bytes)

pytestmark = pytest.mark.unit

DAY_ROT = 1500          # 하루 회전 수 — 08:00 부터 15초 간격(6시간 15분)
STEP_S = 15
CHECKPOINTS = (500, 2000, 5000)   # 셋 다 그날 500번째 회전 뒤 = 같은 시각(10:05:00)
SIDS = ("kojiro", "donchian_swing", "bull_flag_breakout", "vcp_breakout", "volatility_breakout",
        "long_tail_volatility", "momentum")
HOLD = tuple(f"{100000 + k:06d}" for k in range(10))
HOLD_PAIRS = tuple((SIDS[k % len(SIDS)], tk) for k, tk in enumerate(HOLD))
OE = "src.engine.order_engine"


def _rot_time(i):
    day, j = divmod(i, DAY_ROT)
    return day, j, kst(2026, 10, 13, 8, 0, 0) + timedelta(days=day, seconds=STEP_S * j)


def _hms(dt):
    return dt.strftime("%H:%M:%S")


def _ymd_hms(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class DayPattern:
    """하루 단위로 똑같이 되풀이되는 입력 — 스냅샷(G0·G1)과 그 회전에 새로 쌓인 로그 줄.

    G0·G1 은 회전마다 **새 객체**(운영에서 JSON 을 매번 새로 파싱하는 것과 같다). 주문번호는 날마다
    다르지만 길이가 같다(`DDjjjjjSSS`). 종목은 그날 회전 번호로만 정해 날마다 같다.
    """

    def __init__(self, *, positions=10, fields=8, params=15, blob=2000, buy_fallback=True):
        self.positions, self.fields, self.params, self.blob = positions, fields, params, blob
        self.buy_fallback = buy_fallback
        self._signals: dict = {}
        self._day = None

    def snapshot(self, i):
        day, j, t = _rot_time(i)
        if day != self._day:
            self._day = day
            self._signals = {sid: [] for sid in SIDS}    # 21:30 초기화 뒤 새 하루
        sid = SIDS[j % len(SIDS)]
        self._signals[sid].append({"ticker": f"{200000 + j % 50:06d}", "price": 10000 + j % 100,
                                   "time": _hms(t - timedelta(seconds=2))})
        g0 = {
            "running": True, "phase": "main_trading",
            "system": {"blob": "S" * self.blob + str(i)},
            "positions_detail": {tk: {f"f{k}": f"{tk}-{k}-{i}" for k in range(self.fields)}
                                 for tk in HOLD[:self.positions]},
            "strategies": {s: {"enabled": True,
                               "params": {f"p{k}": float(k) + (i % 3) for k in range(self.params)},
                               "buy_signals": [dict(x) for x in self._signals[s][-10:]],
                               "position_tickers": list(HOLD[:3])} for s in SIDS},
        }
        g1 = {"running": True, "as_of": t.isoformat(), "items": [
            {"strategy_id": s, "ticker": tk, "stop_price": 9000 + (i % 7), "stop_source": "effective",
             "target_price": None, "target_source": None, "buy_price": 10000, "quantity": 3,
             "high_since_buy": 10100, "buy_date": "2026-10-10", "order_no": f"{9900000000 + k}",
             "entry_atr": 400.0, "kk_armed": None, "kk_arm_price": None}
            for k, (s, tk) in enumerate(HOLD_PAIRS)]}
        return t, g0, g1

    def lines(self, i):
        day, j, t = _rot_time(i)
        ts = _ymd_hms(t - timedelta(seconds=5))
        hold_sid, hold_tk = HOLD_PAIRS[j % len(HOLD_PAIRS)]
        buy_tk = f"{200000 + j % 50:06d}"
        seq = iter(range(100))

        def no():
            return f"{day:02d}{j:05d}{next(seq):03d}"

        def L(logger, msg, level="INFO"):
            return log_line(ts, level, logger, msg)

        def done(side, tk, qty, o):
            return L("src.api.order", f"{side} 주문 완료: {tk} {qty}주 @ 0 (주문번호: {o})")

        def notice(o, side, tk, rctf="0"):
            return L("src.realtime.handler",
                     f"[order_notice] order_no={o} orig_order_no= side={side} rctf={rctf} kind=01 cond=0 "
                     f"ticker={tk} qty=0000000003 price=000000000 hour=100008 rfus=0 acpt=1 ord_qty=000000003")

        out = [
            L("src.engine.strategies.kojiro",
              f"고지로 매수 신호: {buy_tk} 현재가(70000) — 스테이지1(6→1) + EMA정배열 + ATR(1200.0)"),
            L("src.engine.strategies.kojiro", f"[kojiro_hard_stop] {hold_tk} 매수가(10000) 대비 -8.1% ≤ -8.0%"),
        ]
        if j % 5 == 0:                                   # 정상 매수
            o = no()
            out += [done("BUY", buy_tk, 3, o),
                    L(OE, f"매수 주문 접수: {buy_tk} 3주 @ 70000 (주문번호: {o}, 전략: kojiro)"),
                    notice(o, "BUY", buy_tk)]
        if j % 6 == 0:                                   # 정상 손절 매도
            o = no()
            out += [L(f"src.engine.strategies.{hold_sid}",
                      f"변동성돌파 손절: {hold_tk} 매수가(10000) 대비 -5.0% (현재가: 9500)"),
                    done("SELL", hold_tk, 3, o),
                    L(OE, f"STOP_LOSS 매도 주문 접수: {hold_tk} 3주 (주문번호: {o}, 전략: {hold_sid})"),
                    notice(o, "SELL", hold_tk)]
        if j % 10 == 0:                                  # 짝 없는 완료 줄(대기 항목 — TTL 로 사라져야 한다)
            out.append(done("BUY", f"{300000 + j % 40:06d}", 1, no()))
        if j % 12 == 0:                                  # 외부(HTS) 접수 전문
            out.append(notice(no(), "BUY", "199800"))
        if j % 15 == 0:                                  # 익일청산 보류 → 접수
            o = no()
            out += [L("src.engine.scheduler",
                      f"익일 청산 보류 (갭 1.2% < 임계 2.0%, 09:00 KRX 시장가 청산 예약): {hold_tk} "
                      f"(전략: {hold_sid})"),
                    done("SELL", hold_tk, 3, o),
                    L(OE, f"NEXT_DAY_CLEAR 매도 주문 접수: {hold_tk} 3주 (주문번호: {o}, 전략: {hold_sid})")]
        if j % 20 == 0:                                  # 종목상태 청산
            o = no()
            out += [L("src.engine.status_exit_watch",
                      f"[status_exit_fire] ticker={hold_tk} strategy={hold_sid} reason=short_over iscd=59 "
                      f"mang=N short_over=Y qty=3 mode=enforce attempt=1 bought_today=0", level="WARNING"),
                    done("SELL", hold_tk, 3, o),
                    L(OE, f"STATUS_EXIT 매도 주문 접수: {hold_tk} 3주 (주문번호: {o}, 전략: {hold_sid})")]
        if j % 25 == 0 and self.buy_fallback:            # 매수 폴백
            out += [done("BUY", buy_tk, 3, no()),
                    L(OE, f"시장가 거부 → 지정가 5호가 폴백: {buy_tk} @ 70500 (원인 [APBK1943] 시장가 불가)",
                      level="WARNING")]
        if j % 30 == 0:                                  # 부모 매도 + 손절 잔여 재주문
            parent, child = no(), no()
            out += [done("SELL", hold_tk, 5, parent),
                    L(OE, f"STOP_LOSS 매도 주문 접수: {hold_tk} 5주 (주문번호: {parent}, 전략: {hold_sid})"),
                    done("SELL", hold_tk, 2, child),
                    L(OE, f"손절 잔여 재주문: {hold_tk} 2주")]
        if j % 50 == 0:                                  # 수동 매도
            o = no()
            out += [done("SELL", hold_tk, 1, o),
                    L("src.routes.trading",
                      f"수동 매도 주문 접수: {hold_tk} 1주 (주문번호: {o}, 전략: {hold_sid})")]
        if j % 60 == 0:                                  # 매도 폴백
            o = no()
            out += [done("SELL", hold_tk, 3, o),
                    L(OE, f"매도 시장가 거부 → 지정가 5호가 폴백: {hold_tk} @ 9150 "
                          f"(원인 [APBK1943] 시장가 불가, 주문번호: {o}, 전략: {hold_sid})", level="WARNING")]
        return out


def _pairer_sizes(pattern, checkpoints):
    p = jw("pairing").Pairer()
    sizes = {}
    last = max(checkpoints)
    for i in range(last):
        t, g0, g1 = pattern.snapshot(i)
        p.feed_snapshot(g0, g1, t)
        p.feed_events(parse_all(pattern.lines(i)))
        p.drain(trade_strategies={})
        if i + 1 in checkpoints:
            sizes[i + 1] = retained_bytes(p)
    return sizes


def _assert_flat(sizes, *, label):
    """첫날은 사전 용량이 자리를 잡는 중이라 +25% 까지 · 둘째 날 이후는 날을 넘어 쌓이는 것이 없어야 한다(+2%).

    하루 단위로 비우지 않은 집합(그날 접수 전문 번호 등)이 남으면 날마다 수 KB 씩 늘어 뒤쪽 비교에 걸린다.
    """
    shown = ", ".join(f"N={k}: {v / 1024:.1f}KB" for k, v in sorted(sizes.items()))
    a, b, c = (sizes[n] for n in CHECKPOINTS)
    assert b <= a * 1.25, f"{label}: 보관 크기가 시간에 따라 는다 — {shown}"
    assert c <= b * 1.02 + 4096, f"{label}: 날을 넘어 쌓인다 — {shown}"


# ── M1 ───────────────────────────────────────────────────────────────────────

def test_m1_pairer_retention_is_flat_over_rotations():
    sizes = _pairer_sizes(DayPattern(), CHECKPOINTS)
    _assert_flat(sizes, label="Pairer")
    assert max(sizes.values()) < 2 * 1024 * 1024, {k: f"{v / 1024:.0f}KB" for k, v in sizes.items()}


# ── M2 ───────────────────────────────────────────────────────────────────────

def test_m2_raw_snapshot_objects_are_not_retained():
    pattern = DayPattern()
    p = jw("pairing").Pairer()
    held = []
    for i in range(3):
        t, g0, g1 = pattern.snapshot(i)
        g1["items"][0]["debug_blob"] = "D" * 3000 + str(i)       # 짝짓기가 안 쓰는 칸
        held.append((g0, g1))
        p.feed_snapshot(g0, g1, t)
        p.feed_events(parse_all(pattern.lines(i)))
        p.drain(trade_strategies={})
    reach = reachable_ids(p)
    for k, (g0, g1) in enumerate(held):
        raw = {
            "g0": g0, "g0.system": g0["system"], "g0.system.blob": g0["system"]["blob"],
            "g0.positions_detail": g0["positions_detail"],
            "g0.positions_detail[0]": next(iter(g0["positions_detail"].values())),
            "g0.strategies": g0["strategies"],
            "g0.strategies.kojiro.buy_signals": g0["strategies"]["kojiro"]["buy_signals"],
            "g0.strategies.kojiro.params": g0["strategies"]["kojiro"]["params"],
            "g1": g1, "g1.items": g1["items"], "g1.items[0].debug_blob": g1["items"][0]["debug_blob"],
        }
        kept = [name for name, obj in raw.items() if id(obj) in reach]
        assert kept == [], f"회전 {k} 스냅샷 원본을 Pairer 가 들고 있다: {kept}"


# ── M3 ───────────────────────────────────────────────────────────────────────

def _worker_sizes(tmp_path, checkpoints):
    # 매수 폴백은 뺀다 — 전략 빈칸 저장 실패(결함 2)가 이 측정을 가리지 않게(결함 2 는 test_jw_worker_ops)
    pattern = DayPattern(positions=3, fields=4, params=6, blob=200, buy_fallback=False)
    log = tmp_path / "auto_stock.log"
    log.write_text("", encoding="utf-8")
    state = {"g0": None, "g1": None, "now": None}

    def handler(req):
        path = req.url.raw_path.decode()
        data = state["g0"] if path.startswith("/api/trading/status") else state["g1"]
        return httpx.Response(200, content=json.dumps({"success": True, "message": "", "data": data}),
                              headers={"content-type": "application/json"})

    db = FakeJournalDB()
    client = jw("http").build_client(base_url="http://backend:8000", reporter_key="rk",
                                     transport=httpx.MockTransport(handler))
    w = jw("main").Worker(client=client, db=db, log_dir=tmp_path, now=lambda: state["now"])
    sizes = {}

    async def go():
        async with client:
            for i in range(max(checkpoints)):
                t, g0, g1 = pattern.snapshot(i)
                state.update(g0=g0, g1=g1, now=t)
                with open(log, "a", encoding="utf-8") as f:
                    f.write("".join(ln + "\n" for ln in pattern.lines(i)))
                await w.rotate()
                if i + 1 in checkpoints:
                    sizes[i + 1] = retained_bytes(w, exclude=(client, db, state))

    asyncio.run(go())
    return sizes, db


def test_m3_worker_retention_is_flat_over_rotations(tmp_path):
    sizes, db = _worker_sizes(tmp_path, CHECKPOINTS)
    assert db.orders, "워커가 행을 하나도 쓰지 않았다 — 측정이 공허하다"
    _assert_flat(sizes, label="Worker")


# ── M4 ───────────────────────────────────────────────────────────────────────

def test_m4_restore_mode_keeps_whole_input_external_candidates():
    pr = jw("pairing").Pairer(source="log_restore")
    pr.feed_events(parse_all(golden_lines()))
    pr.drain(final=True)
    assert {"0000042300", "0000340300", "0000549100", "0001402000"} <= pr.external_notice_orders()
