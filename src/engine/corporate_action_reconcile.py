"""액면병합·분할 등 "주문 밖 수량 변경" 대사 — 순수 판정 leaf (cycle431).

사용자 결정 2026-10-10(안1). 자문 =
`_workspace/domain_consult/2026-10-10_corporate_action_qty_reconcile.md`.

07:45 부팅 1차 복구 직후(재도출보다 앞) KIS 잔고와 추적 수량이 다른 보유 종목을
예탁원 정보(액면교체·감자·합병분할) + 어제 주문내역(통보 유실)으로 설명한다.
설명되면 반영(눈금 사건) 또는 수량만 맞춤(통보 유실), 설명 안 되면 보존 + 당일
매수 차단 + ERROR. 21:30 정산·15분 잔고 동기화는 같은 판정을 **감지·관측만**
한다 — 쓰기 지점은 07:45 부팅 하나(멱등성의 전제, `classify()` 가 `match` 를
반환하면 그 뒤로는 아무 일도 없다).

판정 핵심(비율 증거·분류·날짜 키 상태)은 **순수·동기·never-raise** 다 — KIS
호출은 `src/api/corporate_actions.py`, 부팅 시점 조립은
`src/engine/boot_manager.py` 가 한다. 파일 끝의 `observe_mid_session_sync`·
`emit_settlement_detection` 둘은 **관측 전용 비동기 조립**(`selling_reconcile.py`
패턴과 동형 — 순수 판정 + 얇은 비동기 wrapper를 한 leaf 에 둔다)이고 `scheduler.py`
가 한 줄로 위임한다. 표준 라이브러리만 import(날짜 키·KIS 호출은 지연 import).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

# ---------------------------------------------------------------------------
# 비율 증거 — 예탁원 정보 → r(수량 배율) 후보
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RatioCandidate:
    """예탁원 정보에서 나온 수량 배율 후보.

    `r` = 신규 수량 ÷ 기존 수량(분할 1:10 → r=10, 병합 10:1 → r=0.1). 가격은
    반대(`/r`)로 옮긴다.
    """

    r: float
    source: Literal["rev_split", "cap_decrease"]
    face_value_old: int | None = None
    face_value_new: int | None = None


def ratio_from_face_value(old_face_value, new_face_value) -> float | None:
    """액면교체(예탁원 HHKDB669105C0) → r = 옛액면가 ÷ 새액면가.

    병합(액면가 상승) = r<1(수량 감소) · 분할(액면가 하락) = r>1(수량 증가).
    둘 중 하나라도 양수가 아니면(무액면·파싱 실패 등) `None`.
    """
    try:
        old_v = float(old_face_value)
        new_v = float(new_face_value)
    except (TypeError, ValueError):
        return None
    if old_v <= 0 or new_v <= 0:
        return None
    return old_v / new_v


def ratio_from_capital_decrease(reduce_cap_rate, comp_way) -> float | None:
    """감자(예탁원 HHKDB669106C0) → `comp_way == "곱하기"` 일 때만 r = reduce_cap_rate.

    그 밖의 계산방법은 해석 규약이 없어 판정하지 않는다(`None`).
    """
    if not isinstance(comp_way, str) or comp_way.strip() != "곱하기":
        return None
    try:
        r = float(reduce_cap_rate)
    except (TypeError, ValueError):
        return None
    if r <= 0:
        return None
    return r


def qty_ratio_matches(tracked_qty: int, kis_qty: int, r: float) -> bool:
    """KIS 수량이 `floor(추적 수량 × r)` 과 정확히 같은가."""
    if r <= 0 or tracked_qty < 0:
        return False
    return int(kis_qty) == math.floor(tracked_qty * r)


def avg_price_ratio_matches(
    tracked_buy_price: float, kis_avg_price: float, r: float, *, tol_pct: float = 0.01,
) -> bool:
    """KIS 평균단가 ≈ 추적 매입가 ÷ r (허용오차 ±`tol_pct`, 기본 1%)."""
    if r <= 0 or tracked_buy_price <= 0 or kis_avg_price <= 0:
        return False
    expected = tracked_buy_price / r
    if expected <= 0:
        return False
    return abs(kis_avg_price - expected) / expected <= tol_pct


def best_matching_ratio(
    candidates: list[RatioCandidate],
    *,
    tracked_qty: int,
    kis_qty: int,
    tracked_buy_price: float,
    kis_avg_price: float,
    tol_pct: float = 0.01,
) -> RatioCandidate | None:
    """후보 r 중 수량·매입가 증거가 **모두** 맞는 첫 후보. 없으면 `None`.

    후보를 돌려 맞추지 않는다 — r 은 전부 예탁원 응답에서 그대로 만든 값이고
    여기서는 검증만 한다(자문 Q1 증거 B).
    """
    for c in candidates:
        if qty_ratio_matches(tracked_qty, kis_qty, c.r) and avg_price_ratio_matches(
            tracked_buy_price, kis_avg_price, c.r, tol_pct=tol_pct,
        ):
            return c
    return None


def ratio_candidates_from_rev_split_rows(rows: list[dict]) -> list[RatioCandidate]:
    """예탁원 액면교체(rev-split) 응답 행 → `RatioCandidate` 목록. 판정 불가 행은 버린다."""
    out: list[RatioCandidate] = []
    for row in rows or []:
        old_fv = row.get("inter_bf_face_amt")
        new_fv = row.get("inter_af_face_amt")
        r = ratio_from_face_value(old_fv, new_fv)
        if r is not None:
            out.append(RatioCandidate(r=r, source="rev_split", face_value_old=old_fv, face_value_new=new_fv))
    return out


def ratio_candidates_from_cap_decrease_rows(rows: list[dict]) -> list[RatioCandidate]:
    """예탁원 자본감소(cap-dcrs) 응답 행 → `RatioCandidate` 목록(`comp_way="곱하기"` 만)."""
    out: list[RatioCandidate] = []
    for row in rows or []:
        r = ratio_from_capital_decrease(row.get("reduce_cap_rate"), row.get("comp_way"))
        if r is not None:
            out.append(RatioCandidate(r=r, source="cap_decrease"))
    return out


def net_qty_from_order_rows(rows: list[dict]) -> int:
    """주문내역(TTTC0081R, `pdno=ticker`)에서 그 종목의 체결 순증감을 센다.

    `sll_buy_dvsn_cd` `"02"`=매수(+)·`"01"`=매도(-), 체결수량 = `tot_ccld_qty`.
    파싱 실패 행은 그 행만 0 으로 본다(전체를 버리지 않는다 — 사용자 결정 ②
    「정확히 설명」 판정은 호출부 `classify()` 의 등호 비교가 맡는다).
    """
    net = 0
    for row in rows or []:
        try:
            qty = int(row.get("tot_ccld_qty", "0") or 0)
        except (TypeError, ValueError):
            continue
        side = row.get("sll_buy_dvsn_cd")
        if side == "02":
            net += qty
        elif side == "01":
            net -= qty
    return net


# ---------------------------------------------------------------------------
# 분류 — 보유 한 종목의 수량 불일치
# ---------------------------------------------------------------------------

ReconcileAction = Literal[
    "match", "apply_scale", "sync_qty_only", "merger_split_detected", "unexplained",
]


@dataclass(frozen=True)
class ReconcileVerdict:
    action: ReconcileAction
    r: float | None = None
    source: str | None = None
    detail: str = ""


def classify(
    *,
    tracked_qty: int,
    kis_qty: int,
    tracked_buy_price: float,
    kis_avg_price: float,
    ratio_candidates: list[RatioCandidate],
    merger_split_found: bool = False,
    yesterday_fills_net_qty: int | None = None,
) -> ReconcileVerdict:
    """보유 한 종목의 KIS 수량 불일치를 분류한다 — 순수·동기·never-raise.

    순서 ① 일치 ② 비율 증거(예탁원, 액면병합·분할·감자 — 자동 반영) ③ 어제
    주문내역이 정확히 설명(통보 유실, 사용자 결정 ②) ④ 합병·회사분할 감지(자동
    반영 없음 — 새 종목이 생겨 자동 반영 범위 밖) ⑤ 설명 안 됨.
    """
    if tracked_qty == kis_qty:
        return ReconcileVerdict("match")

    matched = best_matching_ratio(
        ratio_candidates,
        tracked_qty=tracked_qty, kis_qty=kis_qty,
        tracked_buy_price=tracked_buy_price, kis_avg_price=kis_avg_price,
    )
    if matched is not None:
        return ReconcileVerdict("apply_scale", r=matched.r, source=matched.source)

    if yesterday_fills_net_qty is not None and tracked_qty + yesterday_fills_net_qty == kis_qty:
        return ReconcileVerdict(
            "sync_qty_only", detail=f"yesterday_fills_net_qty={yesterday_fills_net_qty}",
        )

    if merger_split_found:
        return ReconcileVerdict("merger_split_detected")

    return ReconcileVerdict("unexplained")


# ---------------------------------------------------------------------------
# 적용 — 가격/거래량 차원 값을 r 로 옮긴다
# ---------------------------------------------------------------------------


def apply_ratio_to_price(value, r: float):
    """가격 차원 값을 비율 사건 r 로 옮긴다 (`/r`). 값 없음·r<=0 은 원값 유지."""
    if not value or r <= 0:
        return value
    return value / r


def apply_ratio_to_volume(value, r: float):
    """거래량 차원 값을 비율 사건 r 로 옮긴다 (`×r`). 값 없음·r<=0 은 원값 유지."""
    if not value or r <= 0:
        return value
    return value * r


@dataclass(frozen=True)
class AppliedScale:
    ticker: str
    r: float
    source: str
    new_qty: int
    new_buy_price: int
    new_high_since_buy: float


def compute_applied_scale(
    *,
    ticker: str,
    kis_qty: int,
    tracked_buy_price: float,
    tracked_high_since_buy: float,
    r: float,
    source: str,
) -> AppliedScale:
    """Position 필드(수량·매입가·고점)의 새 값을 계산한다 — DB/메모리 쓰기는 호출자."""
    new_buy_price = apply_ratio_to_price(tracked_buy_price, r)
    new_high = apply_ratio_to_price(tracked_high_since_buy, r)
    return AppliedScale(
        ticker=ticker, r=r, source=source, new_qty=int(kis_qty),
        new_buy_price=int(round(new_buy_price)), new_high_since_buy=new_high,
    )


def rederive_guard_ok(
    last_close_old_scale: float, reference_new_scale: float, quantity_r: float,
    *, tol_pct: float = 0.05,
) -> bool:
    """재도출이 읽을 일봉이 아직 옛 눈금인지 확인한다(자문 「재도출 눈금 가드」).

    `last_close_old_scale ÷ quantity_r ≈ reference_new_scale`(±`tol_pct`, 기본
    5%) 이면 그 일봉은 이미 새 눈금이라 재도출을 믿어도 된다(`True`). 그 밖은
    아직 옛 눈금이라는 뜻이라 `False` — 호출부는 재도출 결과를 버리고 반영한
    스탬프를 유지한다. 실무에서는 사용자 결정에 따라 **반영한 종목은 그날 하루
    재도출 자체를 시도하지 않는다**(`is_rescaled_today` 플랫 가드) — 이 함수는
    그 결정의 근거를 검증 가능한 형태로 남긴다.
    """
    if quantity_r <= 0 or last_close_old_scale <= 0 or reference_new_scale <= 0:
        return False
    expected = last_close_old_scale / quantity_r
    return abs(expected - reference_new_scale) <= tol_pct * reference_new_scale


# ---------------------------------------------------------------------------
# 하루 상태 — 반영된 종목 / 매수 차단 종목 (메모리, 날짜 키 자기 리셋)
# ---------------------------------------------------------------------------

#: KST 날짜(ISO) → {ticker, ...} — 오늘 비율 사건을 반영한 종목. 그날 재도출
#: 가드(`is_rescaled_today`)가 이 집합을 본다. 재시작 시 비는 것이 안전 —
#: 반영 자체가 멱등이라 다음 부팅이 다시 반영해도 결과가 같고, 가드는 "오늘
#: 하루" 한정이라 재시작은 이미 하루를 넘긴 것이다.
_RESCALED_TODAY: dict[str, set[str]] = {}

#: KST 날짜(ISO) → {ticker, ...} — 그날 장부 불일치가 설명 안 돼 신규 매수를
#: 막은 종목(`merger_split_detected`·`unexplained` 분기).
_BUY_BLOCKED_TODAY: dict[str, set[str]] = {}


def _today_key(today: date | None) -> str:
    if today is not None:
        return today.isoformat()
    from src.db._kst import today_kst  # 지연 import — 순환 회피

    return today_kst().isoformat()


def mark_rescaled_today(ticker: str, *, today: date | None = None) -> None:
    _RESCALED_TODAY.setdefault(_today_key(today), set()).add(ticker)


def is_rescaled_today(ticker: str, *, today: date | None = None) -> bool:
    return ticker in _RESCALED_TODAY.get(_today_key(today), ())


def block_buy_today(ticker: str, *, today: date | None = None) -> None:
    _BUY_BLOCKED_TODAY.setdefault(_today_key(today), set()).add(ticker)


def is_buy_blocked_today(ticker: str, *, today: date | None = None) -> bool:
    return ticker in _BUY_BLOCKED_TODAY.get(_today_key(today), ())


def reset_state_for_test() -> None:
    """테스트 전용 — 날짜 키 레지스트리를 비운다."""
    _RESCALED_TODAY.clear()
    _BUY_BLOCKED_TODAY.clear()
    _CTRGA_EMITTED_TODAY.clear()


# ---------------------------------------------------------------------------
# 관측 전용 비동기 조립 — 15분 잔고 동기화 · 21:30 정산 (쓰지 않는다)
# ---------------------------------------------------------------------------
#
# 쓰기 0 — `logger.*` 관측뿐이고 장부·보유·구독·KIS 주문을 건드리지 않는다.

_sched_logger = logging.getLogger("src.engine.scheduler")


async def observe_mid_session_sync(registry, holdings) -> None:
    """15분 잔고 동기화 — 추적 수량 ≠ KIS 수량인 종목을 관측만 한다(자문 Q4).

    장부를 줄이지도 늘리지도 지우지도 않는다(D1 안A 원칙과 정합 — 줄이는
    결정은 매도 시점의 체결통보 보유 축만 한다). 주문내역(TTTC0081R) 조회는
    Δ≠0 인 종목이 있을 때만 1회(`exchange="ALL"`).
    """
    holdings_by_ticker = {h.ticker: h for h in holdings}
    tracked_by_ticker: dict[str, int] = {}
    for strategy in registry.all():
        for ticker, pos in strategy.state.positions.items():
            tracked_by_ticker[ticker] = tracked_by_ticker.get(ticker, 0) + pos.quantity

    mismatched = [
        t for t, tracked in tracked_by_ticker.items()
        if (h := holdings_by_ticker.get(t)) is not None and h.quantity != tracked
    ]
    if not mismatched:
        return

    try:
        from src.api.balance import get_daily_orders
        orders = await get_daily_orders(exchange="ALL")
    except Exception:
        orders = None

    for ticker in mismatched:
        kis_qty = holdings_by_ticker[ticker].quantity
        tracked = tracked_by_ticker[ticker]
        delta = kis_qty - tracked
        if orders is None:
            _sched_logger.warning(
                "[corporate_action_midsync] ticker=%s tracked=%d kis=%d delta=%d result=lookup_failed",
                ticker, tracked, kis_qty, delta,
            )
            continue
        ticker_orders = [o for o in orders if o.get("pdno") == ticker]
        has_open_order = any(int(o.get("rmn_qty", "0") or 0) > 0 for o in ticker_orders)
        if has_open_order:
            _sched_logger.info(
                "[corporate_action_midsync] ticker=%s tracked=%d kis=%d delta=%d result=in_progress",
                ticker, tracked, kis_qty, delta,
            )
            continue
        net = net_qty_from_order_rows(ticker_orders)
        if net == delta:
            _sched_logger.info(
                "[corporate_action_midsync] ticker=%s tracked=%d kis=%d delta=%d "
                "result=explained_by_orders",
                ticker, tracked, kis_qty, delta,
            )
            continue
        _sched_logger.error(
            "[holding_qty_unexplained] ticker=%s tracked=%d kis=%d delta=%d phase=midsync",
            ticker, tracked, kis_qty, delta,
        )


#: CTRGA011R 사후 대사(21:30) 조회 창 — 한 권리의 `bass_dt`(기준일)가 매매정지
#: ·변경상장일보다 며칠 앞설 수 있어(액면교체는 기준일 → 매매정지 → 변경상장
#: 순) 1일 창이면 그 행을 "영원히" 못 잡는다(cycle431 follow-up Fix2, 사용자
#: 결정 2026-10-10). 영업일 수 대신 달력일을 쓴다 — 영업일 판정은 KIS 호출을
#: 더 늘리고, 창이 넓어 경계 하루 차이의 득실이 크지 않다.
CTRGA_LOOKBACK_CALENDAR_DAYS = 45

#: 수량이 바뀌는 권리 유형(14 액면분할·15 액면병합·17 감자) — 비율 계산 대상.
#: `rght_type_cd` 는 2자리 문자열이라 int 로 비교해 앞 0(예: "15")을 무시한다.
_CTRGA_QTY_RIGHT_TYPES = frozenset({14, 15, 17})

#: 합병(11)·회사분할(12) — 새 종목이 생겨 자동 반영 범위 밖(사용자 결정).
#: 존재만 ERROR 로 알린다.
_CTRGA_MERGER_SPLIT_RIGHT_TYPES = frozenset({11, 12})

#: KST 날짜(ISO) → {(ticker, bass_dt), ...} — 오늘 이미 로그를 낸 (종목, 기준일).
#: 창이 겹쳐 같은 행이 **여러 날에 걸쳐** 다시 로그되는 것은 허용한다(잔존
#: 불일치는 매일 보여야 한다) — 이 레지스트리는 "하루 안"(같은 실행) 중복만
#: 막는다.
_CTRGA_EMITTED_TODAY: dict[str, set[tuple[str, str]]] = {}


def _ctrga_mark_emitted(ticker: str, bass_dt: str, *, today: date | None = None) -> bool:
    """오늘 이미 (ticker, bass_dt) 를 로그했으면 False, 아니면 mark 하고 True."""
    key = _today_key(today)
    seen = _CTRGA_EMITTED_TODAY.setdefault(key, set())
    pair = (ticker, bass_dt)
    if pair in seen:
        return False
    seen.add(pair)
    return True


async def emit_settlement_detection(registry, holdings) -> None:
    """21:30 정산 — 보유 종목의 CTRGA011R(계좌 권리 내역)을 사후 대사한다.

    쓰지 않는다 — 반영 지점은 07:45 부팅 하나(사용자 결정 ①). CTRGA011R 은
    실전 전용(`fetch_period_rights` 가 모의에서 빈 목록을 돌려준다). 행이
    없어도 그 자체로 오류가 아니다(「행 부재는 반영을 막지 않는다」, 사용자
    결정 「둘 다 체크」).

    cycle431 follow-up Fix2(사용자 결정 2026-10-10) — 최근
    `CTRGA_LOOKBACK_CALENDAR_DAYS` 달력일 창으로 넓혀 수량 변경 권리
    (14·15·17)만 비율(`tot_alct_qty / cblc_qty`)을 계산하고, 추적 수량(전
    전략 합) 대 KIS 보유수량을 대조해 일치(`match`)·불일치(`mismatch`)를
    로그한다. 합병·회사분할(11·12)은 그 행이 있다는 사실만 ERROR(자동 반영
    없음). `holdings` 는 호출자(`scheduler._settle()`)가 이미 부른 잔고
    조회를 넘긴다 — 이 함수가 KIS 잔고를 추가로 부르지 않는다. 단수주
    (`last_ftsk_qty`)는 KIS 수량에 이미 반영됐다고 보고 비교에 넣지 않는다.
    같은 (ticker, bass_dt) 는 이 호출(하루 1회, 21:30) 안에서 1회만 로그한다
    — 창이 겹쳐 다음 날 다시 로그되는 것은 막지 않는다(잔존 불일치는 매일
    보이는 게 맞다).
    """
    tracked_by_ticker: dict[str, int] = {}
    for strategy in registry.all():
        for ticker, pos in strategy.state.positions.items():
            tracked_by_ticker[ticker] = tracked_by_ticker.get(ticker, 0) + pos.quantity

    held_tickers = sorted(tracked_by_ticker)
    if not held_tickers:
        return

    holdings_by_ticker = {h.ticker: h for h in holdings}

    from src.api import corporate_actions as _ca
    from src.db._kst import today_kst

    today = today_kst()
    start_date = (today - timedelta(days=CTRGA_LOOKBACK_CALENDAR_DAYS)).strftime("%Y%m%d")
    end_date = today.strftime("%Y%m%d")

    for ticker in held_tickers:
        try:
            rows = await _ca.fetch_period_rights(ticker, start_date=start_date, end_date=end_date)
        except Exception:
            _sched_logger.warning(
                "[corporate_action_ctrga_check_failed] ticker=%s", ticker, exc_info=True,
            )
            continue
        if not rows:
            continue

        for row in rows:
            raw_code = str(row.get("rght_type_cd", "")).strip()
            try:
                code = int(raw_code)
            except (TypeError, ValueError):
                continue
            bass_dt = str(row.get("bass_dt", "")).strip()
            dedup_key = bass_dt or raw_code

            if code in _CTRGA_MERGER_SPLIT_RIGHT_TYPES:
                if not _ctrga_mark_emitted(ticker, f"merger:{dedup_key}"):
                    continue
                _sched_logger.error(
                    "[corporate_action_ctrga_merger_held] ticker=%s bass_dt=%s rght_type_cd=%s",
                    ticker, bass_dt, raw_code,
                )
                continue

            if code not in _CTRGA_QTY_RIGHT_TYPES:
                continue

            if not _ctrga_mark_emitted(ticker, dedup_key):
                continue

            try:
                cblc_qty = float(row.get("cblc_qty") or 0)
                tot_alct_qty = float(row.get("tot_alct_qty") or 0)
            except (TypeError, ValueError):
                _sched_logger.warning(
                    "[corporate_action_ctrga_check_failed] ticker=%s reason=bad_qty bass_dt=%s",
                    ticker, bass_dt,
                )
                continue
            if cblc_qty <= 0:
                _sched_logger.warning(
                    "[corporate_action_ctrga_check_failed] ticker=%s reason=zero_cblc bass_dt=%s",
                    ticker, bass_dt,
                )
                continue
            ratio = tot_alct_qty / cblc_qty

            tracked = tracked_by_ticker.get(ticker, 0)
            kis = holdings_by_ticker.get(ticker)
            kis_qty = kis.quantity if kis is not None else None

            if kis_qty is not None and tracked == kis_qty:
                _sched_logger.info(
                    "[corporate_action_ctrga_reconciled] result=match ticker=%s bass_dt=%s "
                    "ratio=%.6f",
                    ticker, bass_dt, ratio,
                )
            else:
                _sched_logger.error(
                    "[corporate_action_ctrga_reconciled] result=mismatch ticker=%s bass_dt=%s "
                    "ratio=%.6f tracked=%s kis=%s alct=%s",
                    ticker, bass_dt, ratio, tracked, kis_qty, tot_alct_qty,
                )
