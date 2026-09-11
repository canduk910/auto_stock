"""cycle282 — 장운영상태 화면이 쓰는 `GET /api/market-state` 골든 픽스처 생성기.

실행:
    python tools/test_fixtures/gen_market_state_fixture.py

산출:
    frontend/src/test/fixtures/marketState.fixture.ts   (MSW + vitest)
    e2e/fixtures/market-state.fixture.ts                (Playwright)

두 파일은 **손으로 고치지 않는다.** `src/engine/market_state.py` 의 `MARKET_TABLE`(13행)·
`ORDER_DIVISIONS`(28코드)나 `src/routes/market_state.py` 의 응답 조립이 바뀌면 이 스크립트를
다시 돌린다. 어긋난 채로 두면 백엔드 가드
`tests/unit/routes/test_cycle282_fixture_sync.py` 가 붉어진다(선언만 있고 강제가 없는 상태를
남기지 않는다 — cycle266 재발 계열).

## 왜 라우트를 직접 부르는가

픽스처 본문을 여기서 손으로 조립하면 "픽스처가 라우트를 흉내낸 것" 이 되고, 라우트가
키 하나를 바꾸거나 순서를 옮겨도 픽스처는 조용히 옛 모양을 유지한다. 그래서 이 스크립트는
`read_market_state` 를 **그대로 호출**하고 두 가지만 고정한다 —

* 시각(`datetime.now`) → 변종별 고정 시각
* 휴장일 조회(`_resolve_trading_day`) → 고정 3상태(외부 I/O 금지)

그 결과 픽스처의 바이트는 **라우트의 실제 산출물**이다.

cycle266(종목마스터 일봉 탭)은 MSW·Playwright·컴포넌트 목 세 곳이 `change_rate` 를 전부
진짜 number 로 만들어 *의도한 계약*만 담고 *실제 응답*(pydantic v2 가 `Decimal` 을 문자열로
직렬화)을 담지 않아 3개월 넘게 초록이었다. 목이 코드에서 나오면 그 괴리가 생기지 않는다.

⚠️ 이 스크립트는 `src.config` 를 import 하므로 필수 환경변수가 필요하다(값은 무엇이든
상관없다 — 표와 라우트 조립만 읽는다):
    KIS_APP_KEY=x KIS_APP_SECRET=x KIS_ACCOUNT_NO=x SUPABASE_URL=http://x SUPABASE_KEY=x \
        python tools/test_fixtures/gen_market_state_fixture.py
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine import market_state as ms  # noqa: E402
from src.routes import market_state as route  # noqa: E402

FRONT_PATH = ROOT / "frontend/src/test/fixtures/marketState.fixture.ts"
E2E_PATH = ROOT / "e2e/fixtures/market-state.fixture.ts"

_KST = _dt.timezone(_dt.timedelta(hours=9))


def _at(y: int, m: int, d: int, hh: int, mm: int, ss: int) -> _dt.datetime:
    return _dt.datetime(y, m, d, hh, mm, ss, tzinfo=_KST)


#: (export 이름, 고정 시각, on_date 인자, 휴장일 3상태, 출처)
#: 하나로는 이 화면의 계약을 못 잰다 — 중첩·합집합은 08:35 에만, `seconds_to_next=null` 은
#: 20:30 에만, `markets=null`·`rel="unknown"` 은 미리보기에만 있다.
VARIANTS: tuple = (
    ("MARKET_STATE_AT_0835", _at(2026, 9, 11, 8, 35, 10), None, True, "kis"),
    ("MARKET_STATE_AT_1305", _at(2026, 9, 11, 13, 5, 22), None, True, "kis"),
    ("MARKET_STATE_AT_2030", _at(2026, 9, 11, 20, 30, 0), None, True, "kis"),
    (
        "MARKET_STATE_PREVIEW",
        _at(2026, 9, 11, 13, 5, 22),
        _dt.date(2026, 9, 14),
        True,
        "kis",
    ),
)


class _FrozenClock(_dt.datetime):
    """`route.datetime.now(tz)` 만 고정한다 — 그 외 동작은 표준 datetime 그대로."""

    _fixed: "_dt.datetime | None" = None

    @classmethod
    def now(cls, tz=None):  # noqa: D102 — 표준 시그니처
        assert cls._fixed is not None, "고정 시각 미설정"
        return cls._fixed if tz is None else cls._fixed.astimezone(tz)


def build_variant(as_of, on_date, trading_day, source) -> dict:
    """라우트를 **그대로** 불러 응답 `data` 를 얻는다(시각·휴장일만 고정)."""
    real_datetime = route.datetime
    real_resolver = route._resolve_trading_day

    async def _fixed_resolver(target):
        return trading_day, source

    _FrozenClock._fixed = as_of
    route.datetime = _FrozenClock
    route._resolve_trading_day = _fixed_resolver
    try:
        response = asyncio.run(route.read_market_state(on_date))
    finally:
        route.datetime = real_datetime
        route._resolve_trading_day = real_resolver
        _FrozenClock._fixed = None
    return response.data


def build_forbidden() -> dict:
    """`_ast_market_state_hardcode.test.ts` 가 읽는 **금지어 목록** — 표에서 생성한다.

    손으로 적으면 표에 행이 늘어도 금지어가 늘지 않아 가드가 조용히 비켜난다.
    """
    row_names = sorted({row.name_ko for row in ms.MARKET_TABLE})
    division_names = sorted(
        {spec.name_ko for spec in ms.ORDER_DIVISIONS}
        | {spec.group_ko for spec in ms.ORDER_DIVISIONS if spec.group_ko}
    )
    return {
        "rowIds": [row.row_id for row in ms.MARKET_TABLE],
        "divisionCodes": [spec.code for spec in ms.ORDER_DIVISIONS],
        "rowNames": row_names,
        "divisionNames": division_names,
        "phases": [phase.value for phase in ms.MarketPhase],
        "markets": list(ms.EXCHANGE_ORDER),
    }


def _body(name: str, type_name: str, value: dict) -> str:
    return (
        f"export const {name}: {type_name} = "
        + json.dumps(value, ensure_ascii=False, indent=2)
        + "\n"
    )


TAIL_TS = """
/** MSW 기본 핸들러가 쓰는 변종 — 평범한 정규장(13:05). */
export const MARKET_STATE_FIXTURE: MarketStateData = MARKET_STATE_AT_1305
"""

TYPES_TS = r"""export interface MarketStateWindow {
  start: string
  end: string
}

export interface MarketStateDivisionsByRow {
  row_id: string
  codes: string[]
}

/** `markets[<market>]` — 서버가 판정한 **커서 1개**. 프론트는 이 값을 그릴 뿐 다시 계산하지 않는다. */
export interface MarketStateCursor {
  market: string
  market_label_ko: string
  row_id: string | null
  phase: string
  name_ko: string
  tone: string
  window: MarketStateWindow | null
  match_kind: string
  match_ko: string
  is_open: boolean
  can_order: boolean
  market_order_ok: boolean
  order_divisions: string[]
  order_divisions_by_row: MarketStateDivisionsByRow[]
  concurrent_row_ids: string[]
  quote_channel: string | null
  quote_channel_evidence: string
  decided_by: string
  code_seen: string | null
  confidence: string
  confidence_notes: string[]
  seconds_to_next: number | null
  next_boundary: string | null
  next_row_id: string | null
  next_phase: string | null
}

export interface MarketStateTableRow {
  row_id: string
  market: string
  start: string
  end: string
  phase: string
  name_ko: string
  tone: string
  match_kind: string
  match_ko: string
  order_divisions: string[]
  order_divisions_pending: string[]
  order_divisions_expired: string[]
  can_order: boolean
  market_order_ok: boolean
  quote_channel: string | null
  quote_channel_evidence: string
  overlap_ok: boolean
  priority: number
  effective_from: string | null
  effective_to: string | null
  confidence: string
  note: string
  /** 서버 판정 — `past`/`current`/`concurrent`/`upcoming`/`unknown`. 프론트가 시각으로 다시 재지 않는다. */
  rel: string
}

export interface OrderDivisionRow {
  code: string
  name_ko: string
  group_ko: string | null
  /** 거래소별 3상태 — `yes`(●) / `unknown`(?) / `no`(빈칸). "미지원"과 "미확인"은 다르다. */
  exchange_support: Record<string, string>
  effective_from: string | null
  effective_to: string | null
  confidence: string
  note: string
}

export interface MarketPhaseSpec {
  id: string
  label_ko: string
  tone: string
}

export interface MarketStateVocab {
  tones: string[]
  rels: string[]
  support_levels: string[]
  confidences: string[]
  division_confidences: string[]
}

export interface MarketStateData {
  table_version: string
  as_of_kst: string
  on_date: string
  preview: boolean
  cursor_disabled_reason: string | null
  /** `true` 개장 · `false` 휴장 · `null` **확인 불가**(임의 True/False 금지 — M10). */
  is_trading_day: boolean | null
  trading_day_source: string
  market_order: string[]
  exchange_order: string[]
  /** preview(다른 날짜 조회)면 `null` — 커서는 "지금" 에만 의미가 있다. */
  markets: Record<string, MarketStateCursor> | null
  table: MarketStateTableRow[]
  order_divisions: OrderDivisionRow[]
  phases: MarketPhaseSpec[]
  vocab: MarketStateVocab
  findings: string[]
  board_note: string
  unconfirmed_note: string
}

/** M7 가드가 읽는 **금지어 목록**. 손으로 적지 않는다 — 표에서 생성된다. */
export interface MarketStateForbidden {
  rowIds: string[]
  divisionCodes: string[]
  rowNames: string[]
  divisionNames: string[]
  phases: string[]
  markets: string[]
}
"""

FRONT_HEADER = r"""/**
 * cycle282 Red — `GET /api/market-state` 응답 **골든 픽스처**.
 *
 * ⚠️ 손으로 쓰지 않는다. `src/engine/market_state.py` 의 `MARKET_TABLE`(13행)·
 * `ORDER_DIVISIONS`(28코드)에서 **기계 생성**한다
 * (생성기: `tools/test_fixtures/gen_market_state_fixture.py`).
 *
 * 왜 생성인가 — cycle266(종목마스터 일봉 탭)은 MSW·Playwright·컴포넌트 목 세 곳이
 * `change_rate` 를 전부 진짜 number 로 만들어 *의도한 계약*만 담고 *실제 응답*
 * (pydantic v2 가 `Decimal` 을 문자열로 직렬화)을 담지 않아 3개월 넘게 초록이었다.
 * 목이 코드에서 나오면 그 괴리가 생기지 않는다.
 *
 * 변종 4개 — 하나로는 이 화면의 계약을 못 잰다:
 *   - `MARKET_STATE_AT_0835` 08:35:10 · K1 ⊃ K2 **동시 중첩**(커서 K1 + concurrent K2,
 *     주문유형은 두 행의 **합집합** 00·01·05). 우선순위 규칙이 뒤집히면 여기가 먼저 깨진다.
 *   - `MARKET_STATE_AT_1305` 13:05:22 · 평범한 정규장. MSW 기본 응답.
 *   - `MARKET_STATE_AT_2030` 20:30:00 · **장 종료** — `seconds_to_next=null`,
 *     `row_id=null`, 표의 모든 행이 `rel="past"`.
 *   - `MARKET_STATE_PREVIEW`   09-14 미리보기 · `markets=null`, 모든 `rel="unknown"`,
 *     K6 등장·K7 소멸, N1 이 27~29 를 포함한 16코드. 날짜 차원이 계약임을 화면에서 잰다.
 *
 * ⚠️ **이 파일의 바이트는 생성기 산출이 정본이다.** 표나 라우트가 바뀌면 생성기를 다시
 * 돌려 두 픽스처를 함께 덮어쓴다. `tests/unit/routes/test_cycle282_fixture_sync.py` 가
 * 생성기 산출과 이 파일을 byte 비교하고 두 픽스처가 서로 같은지도 잠그므로, 재생성을
 * 빠뜨리면 백엔드 스위트가 붉어진다. 다만 **export 이름과 구조는 계약**이라 바꾸지
 * 않는다 — 프론트 테스트 3파일과 MSW·Playwright 목이 그 이름으로 붙어 있다.
 */
"""

E2E_HEADER = r"""/**
 * cycle282 Red — Playwright 용 `GET /api/market-state` 골든 픽스처.
 *
 * `frontend/src/test/fixtures/marketState.fixture.ts` 와 **같은 생성기 산출물**이다
 * (e2e 는 frontend tsconfig 밖이라 교차 import 대신 같은 내용을 각자 보유한다).
 * 손으로 고치지 않는다 — 표가 바뀌면 생성기
 * `tools/test_fixtures/gen_market_state_fixture.py` 로 두 파일을 함께 재생성한다.
 */
"""


def render(header: str) -> str:
    """`header`(주석 블록) + 타입 + 변종 4개 + 금지어 + 꼬리."""
    parts = [header, "\n", TYPES_TS, "\n"]
    for name, as_of, on_date, trading_day, source in VARIANTS:
        parts.append(_body(name, "MarketStateData", build_variant(as_of, on_date, trading_day, source)))
        parts.append("\n")
    parts.append(_body("MARKET_STATE_FORBIDDEN", "MarketStateForbidden", build_forbidden()))
    parts.append(TAIL_TS)
    return "".join(parts)


def render_front() -> str:
    return render(FRONT_HEADER)


def render_e2e() -> str:
    return render(E2E_HEADER)


def main() -> None:
    front = render_front()
    e2e = render_e2e()
    FRONT_PATH.parent.mkdir(parents=True, exist_ok=True)
    E2E_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRONT_PATH.write_text(front, encoding="utf-8")
    E2E_PATH.write_text(e2e, encoding="utf-8")
    print("variants:", len(VARIANTS), "rows:", len(ms.MARKET_TABLE), "codes:", len(ms.ORDER_DIVISIONS))
    print(FRONT_PATH, len(front.encode("utf-8")))
    print(E2E_PATH, len(e2e.encode("utf-8")))


if __name__ == "__main__":
    main()
