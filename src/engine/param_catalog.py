"""전략 파라미터 카탈로그 — 7 전략 `DEFAULT_PARAMS` 합집합 101 키의 **단일 진실원**.

사이클 278. 이 모듈은 **순수 데이터**다.

* `src.*` import 0 · I/O 0 · 로깅 0 · 모듈 로드 시 부작용 0.
* 값을 바꾸지 않는다 — 이 사이클은 사람이 화면에서 값을 고칠 **수단**을 만드는 것이지
  매매 파라미터의 값을 바꾸는 것이 아니다. 전략 7파일 · `strategy_base.py` ·
  `recommendation_engine.py` 의 `PARAM_RANGES`/`INT_PARAMS` 는 무접촉이다.
* 라우트 배선은 이 사이클의 Green 단계에서 한다. 이 파일은 아무 것도 import 하지 않고
  아무 곳에서도 import 되지 않아도 자기 자신으로 완결된다.

────────────────────────────────────────────────────────────────────────────
범위(min/max)의 출처 — `range_src`
────────────────────────────────────────────────────────────────────────────
범위를 **지어내지 않는다.** 아래 6 출처 중 하나가 없으면 `min=max=None` 이고
`range_src="none"` 이며, 그 키의 검증은 자료형·부호·enum 까지만 한다.

``clamp``
    읽는 쪽 코드의 하드 클램프 상수. 6 키
    (`max_lot_units`·`max_lot_ratio_mult` = `strategy_base.py` `_MAX_LOT_*` /
     `open_entry_hold_secs` = `volatility_breakout.py` `_OPEN_HOLD_*` /
     `llm_gate_min_score`·`llm_gate_daily_call_cap`·`llm_gate_timeout_secs`
     = `llm_buy_gate.py` `_read_*`).
    ⚠️ 카탈로그가 생겼다고 그 클램프를 제거하면 안 된다 — DB 직접 UPDATE·구버전 행·
    부팅 로드 경로는 라우트를 거치지 않는다(`strategy_base.py:944-947` 주석).
``param_ranges``
    `recommendation_engine.PARAM_RANGES` 의 값을 **그대로** 옮긴 것. 단 그 범위가
    7 전략 기본값 전부를 포함할 때만 쓴다(포함하지 않는 유일한 키 = `max_scan_stocks`).
    PARAM_RANGES 는 원래 *AI 튜너가 밤새 흔들어도 되는 좁은 안전대*이지 사람의 편집
    한계가 아니다. 그래도 근거 있는 유일한 숫자라 그대로 쓰고, 넓히지 않는다.
``sign``
    코드의 부호 규약. 두 갈래가 있다 —
    (가) 부호 게이트: `if min_stop_pct < 0` / `if backstop < 0` / `return tv if tv < 0
    else 0.0` 처럼 부호가 맞지 않으면 **조용히 비활성**된다.
    (나) 부호 필연: `hard_stop_pct` 는 게이트가 없어(`loss_rate <= hard_stop_pct`)
    양수를 넣으면 **모든 포지션이 즉시 손절**된다.
``structural``
    자료형·구조상 필연. 기간/봉수 ≥ 1(길이 0 은 빈 window), 비율 키 0.0~1.0
    (코드가 `×100` 으로 표시), 퍼센트-of-가격 키 ±100, 등락률 키 ±30
    (KRX 일일 가격제한).
``enum``
    값 집합이 곧 범위인 키. `choices` 참조.
``none``
    근거 없음. `min=max=None`. `help` 에 사유를 남긴다.

────────────────────────────────────────────────────────────────────────────
`type`
────────────────────────────────────────────────────────────────────────────
``int``       정수. 저장·표시 동일.
``float``     실수. 저장·표시 동일(`unit` 이 "%" 면 그 숫자 자체가 이미 퍼센트다).
``percent``   **저장은 비율(0.0~1.0), 표시만 %** (코드가 `×100` 해서 보여주는 키).
              `position_ratio=0.25` → 화면 "25%". 저장값을 100 으로 바꾸지 않는다.
``bool``      참/거짓.
``enum``      `choices` 중 하나.
``list_str``  문자열 목록. `choices` 가 있으면 그 안에서만, 없으면 `pattern` 으로 검증.
``str``       문자열. `pattern` 으로 형식 검증.

⚠️ 접미사로 단위를 추측하지 않는다. `_pct` 는 퍼센트(`hard_stop_pct=-8.0`)와
비율(`base_depth_pct=0.3`) 양쪽에 쓰인다. 이름 기반 추론은 폐기된
`v / 100 if v > 1 else v` 휴리스틱의 재현이다(루트 CLAUDE.md "비중 단위 추론 변환 금지").

────────────────────────────────────────────────────────────────────────────
`risk`
────────────────────────────────────────────────────────────────────────────
``normal``    일반.
``high``      코드/문서가 "정체성 상수"라 부르거나, 청산 임계이거나, 잘못된 값이
              **무증상**으로 매매를 바꾸는 키. 화면에서 강조한다.
``identity``  리스크 정체성 상수 15 키. 화면 저장 시 **2단계 확인**을 요구한다.
              (`max_positions` · `max_lot_units` · `max_lot_ratio_mult` · `risk_pct` ·
               `max_open_risk_pct` · `sizing_mode` · `tradable_boards` ·
               `open_entry_hold_secs` · `open_price_scope_mode` · `llm_gate_*` 4키 ·
               `order_exchange_clock_mode`(cycle290) · `after_market_exit_division`(cycle290))

────────────────────────────────────────────────────────────────────────────
`deprecated` / `deprecated_for`
────────────────────────────────────────────────────────────────────────────
``deprecated=True``
    **어느 전략에서도** 행위에 영향이 없는 잔존 키(8 키). 숨기지 않는다 — 회색 +
    "미사용" 배지로 보여 주되 `editable=False`. 값이 바뀌어도 매매가 안 바뀌는 입력란은
    운영자를 속인다.
``deprecated_for=(전략id, ...)``
    **그 전략에서만** 현재 기본 설정상 효력이 없는 키. `k_value_nxt_pre`/`_nxt_post` 가
    유일한 사례로, VB 는 `DEFAULT_TRADABLE_BOARDS=("main",)` 라 곱해지는 경로가 없고
    LTV 는 `("pre_nxt","main","post_nxt")` 라 야간 목표가에 **실제로 곱해진다**.
    키 단위 전역 플래그로 두면 LTV 화면에 거짓말을 한다. 조건부라는 점에 주의 —
    VB 의 `tradable_boards` 에 보드를 추가하면 그 키는 되살아난다.

────────────────────────────────────────────────────────────────────────────
`applies_to` 는 화면의 범위이고 PUT 의 관문이 아니다 (의도된 비대칭)
────────────────────────────────────────────────────────────────────────────
`GET /api/strategies/params-schema` 는 `applies_to` 로 전략별 행을 만들지만,
`PUT /{id}/params` 의 미지 키 판정은 `key in strategy.config.params`(런타임 상태)로
한다. 그래서 DB 드리프트로 어떤 전략의 `params` 에 소관 밖 키가 들어와 있으면 PUT 은
그 키의 저장을 **받아들인다**. 이 비대칭은 **조이지 않는다** — 그 전략이 읽지 않는 키라
매매 영향이 0 이고, `applies_to` 로 조이면 운영자의 비상 curl 롤백 경로가 함께 좁아진다
(장중 실효 수단이 PUT 뿐이라는 cycle232 D6 와 정면충돌). fail-open 을 택한 판단이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "Choice",
    "ForbiddenChoice",
    "ParamSpec",
    "CATALOG_VERSION",
    "STRATEGY_IDS",
    "GROUPS",
    "GROUP_IDS",
    "TYPES",
    "RISKS",
    "UNITS",
    "RANGE_SOURCES",
    "PARAM_SPECS",
    "SPEC_BY_KEY",
    "BUDGET_INVARIANT",
    "ORDER_INVARIANTS",
    "OrderInvariant",
    "get_spec",
    "keys_for_strategy",
    "specs_for_strategy",
    "specs_in_group",
    "all_keys",
    "identity_keys",
    "deprecated_keys",
    "auto_tunable_keys",
    "editable_keys",
    "forbidden_choices_for",
]

CATALOG_VERSION = "cycle290.1"

#: 전략 id 의 정본 순서(레지스트리 등록 순서).
STRATEGY_IDS: tuple[str, ...] = (
    "momentum",
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
    "bull_flag_breakout",
    "vcp_breakout",
    "kojiro",
)

#: 화면 아코디언 순서 — (group_id, 한글 라벨, 한 줄 설명)
GROUPS: tuple[tuple[str, str, str], ...] = (
    ("entry", "진입", "무엇을 언제 사는가 — 후보 조건·돌파 판정·재진입 쿨다운"),
    ("exit", "청산", "언제 파는가 — 손절·트레일링·보유일수·ATR 청산"),
    ("sizing_risk", "사이징·리스크", "얼마나 사는가 — 비중·유닛·랏 상한·동시보유"),
    ("scan_universe", "스캔·유니버스", "어떤 종목을 후보로 보는가 — 시총·거래대금·제외"),
    ("time_board", "시간·보드", "언제·어느 시장에서 주문하는가"),
    ("observe_gate", "관측·게이트", "진입 직전 관문 — 시가 출처·보류 창·LLM 게이트"),
    ("legacy", "레거시", "정의만 남고 행위에 쓰이지 않는 잔존 키 (읽기 전용)"),
)
GROUP_IDS: tuple[str, ...] = tuple(g[0] for g in GROUPS)

TYPES: tuple[str, ...] = ("int", "float", "percent", "bool", "enum", "list_str", "str")
RISKS: tuple[str, ...] = ("normal", "high", "identity")
#: `unit` 의 닫힌 어휘. 화면 포맷터는 **키가 아니라 이 단위**로 분기한다
#: (키별 하드코딩 0건 가드의 전제).
UNITS: tuple[str, ...] = ("", "%", "배", "유닛", "원", "일", "봉", "분", "초", "개", "회", "점")
RANGE_SOURCES: tuple[str, ...] = (
    "clamp",
    "param_ranges",
    "sign",
    "structural",
    "enum",
    "none",
)


@dataclass(frozen=True)
class Choice:
    """enum / list_str 의 선택지 하나."""

    value: Any
    label_ko: str
    deprecated: bool = False
    help: str = ""


@dataclass(frozen=True)
class ForbiddenChoice:
    """**그 전략에서만** 금지된 선택지 하나 (사이클 278 후속 시정 2).

    `choices` 가 값 집합의 상한이라면 이것은 전략별 하한이다 — 값 자체는 어휘 안에
    있지만 그 전략에 넣으면 **명문화된 절대 규칙**을 깬다. 유일한 실재 사례는
    VB(`volatility_breakout`) + `post_nxt` 로, 루트 `CLAUDE.md` 의
    "VB 당일 15:20 일괄매도 — `DEFAULT_TRADABLE_BOARDS=("main",)`, POST_NXT 추가 금지"
    조항이 근거다. 화면 체크박스 한 번으로 그 규칙에 도달할 수 있으면 규칙이 아니다.

    `reason` 은 **화면과 422 본문에 그대로 실린다** — 운영자가 왜 막혔는지 코드를 열지
    않고 알 수 있어야 한다.
    """

    strategy_id: str
    value: Any
    reason: str


@dataclass(frozen=True)
class ParamSpec:
    """파라미터 한 키의 메타데이터."""

    key: str
    label_ko: str
    group: str
    type: str
    min: Any
    max: Any
    step: Any
    unit: str
    editable: bool
    risk: str
    auto_tunable: bool
    deprecated: bool
    help: str
    applies_to: tuple[str, ...]
    range_src: str
    choices: tuple[Choice, ...] = ()
    pattern: str | None = None
    deprecated_for: tuple[str, ...] = ()
    #: `list_str` 최소 항목 수. 0 = 빈 목록 허용(기본).
    #: ⚠️ **빈 목록의 뜻이 키마다 정반대**라 일괄 규칙을 둘 수 없다 —
    #: `exclude_tickers=[]` 는 "제외 없음" 이라는 7 전략의 정상 기본값이고,
    #: `tradable_boards=[]` 는 전략의 절반에서 매수 전면 중단, 나머지 절반에서
    #: 기본 보드 폴백(= 아무 일도 안 일어남)이다. 그 비대칭을 화면·서버 양쪽이
    #: 추론하지 않도록 **데이터로** 적는다.
    min_items: int = 0
    #: 전략별 금지 선택지. `enum`·`list_str` 양쪽에 적용된다.
    forbidden_choices: tuple[ForbiddenChoice, ...] = ()


@dataclass(frozen=True)
class OrderInvariant:
    """`lo_key <= hi_key` 여야 하는 키 쌍."""

    lo_key: str
    hi_key: str
    strategies: tuple[str, ...]
    consequence: str
    enforced: bool  # True=422, False=경고만


#: 하드 불변식 — 라우트가 422 로 강제한다.
BUDGET_INVARIANT = (
    "position_ratio × max_positions <= 1.0 — 한 전략이 배정 자금의 100% 를 넘게"
    " 청약하지 못한다. 7 전략 중 6 전략의 기본값이 정확히 1.0 이라 한쪽만 올리면"
    " 반드시 위반한다(두 키를 같은 요청에 함께 보내야 한다)."
)

#: 소프트 불변식 — 위반해도 코드가 막지 않지만 **무증상으로** 후보가 0 이 되거나
#: 설계 의도가 죽는다. 라우트는 422 대신 `warnings` 로 알린다.
ORDER_INVARIANTS: tuple[OrderInvariant, ...] = (
    OrderInvariant(
        "base_min_days", "base_max_days", ("vcp_breakout",),
        "역전 시 `range(base_max, base_min-1, -1)` 이 빈 range 가 되어 후보 0(무증상)",
        False,
    ),
    OrderInvariant(
        "pullback_count_min", "pullback_count_max", ("vcp_breakout",),
        "역전 시 Pullback 개수 조건을 만족할 수 없어 후보 0",
        False,
    ),
    OrderInvariant(
        "pole_lookback_min", "pole_lookback_max", ("bull_flag_breakout",),
        "역전 시 Pole 탐색 창이 비어 후보 0",
        False,
    ),
    OrderInvariant(
        "flag_lookback_min", "flag_lookback_max", ("bull_flag_breakout",),
        "역전 시 Flag 탐색 창이 비어 후보 0",
        False,
    ),
    OrderInvariant(
        "atr_ratio_min", "atr_ratio_max", ("kojiro",),
        "역전 시 변동성 밴드가 공집합이라 후보 0",
        False,
    ),
    OrderInvariant(
        "entry_start", "entry_end", ("bull_flag_breakout", "vcp_breakout"),
        "역전 시 `now < start or now > end` 가 항상 참이라 하루 종일 매수 차단",
        False,
    ),
    OrderInvariant(
        "ema_short", "ema_mid", ("vcp_breakout", "kojiro"),
        "역전 시 EMA 정렬/대순환 판정의 전제가 깨진다",
        False,
    ),
    OrderInvariant(
        "ema_mid", "ema_long", ("vcp_breakout", "kojiro"),
        "역전 시 EMA 정렬/대순환 판정의 전제가 깨진다",
        False,
    ),
    OrderInvariant(
        "turtle_backstop_pct", "turtle_min_stop_pct",
        ("bull_flag_breakout", "vcp_breakout"),
        "backstop 이 min_stop 보다 얕으면 최소폭 밴드가 死코드가 된다"
        " (둘 다 음수이므로 backstop <= min_stop 이어야 한다)",
        False,
    ),
    OrderInvariant(
        "channel_exit_period", "donchian_period", ("donchian_swing",),
        "청산 채널이 진입 채널보다 길면 추세추종이 성립하지 않는다",
        False,
    ),
    OrderInvariant(
        "max_positions_per_sector", "max_positions", ("kojiro",),
        "섹터 상한이 전체 상한보다 크면 섹터 게이트가 死코드가 된다",
        False,
    ),
    OrderInvariant(
        "max_units_per_stock", "max_units_total", ("kojiro",),
        "둘 다 레거시(소비처 0건) — 관측 목적으로만 남긴다",
        False,
    ),
)


# ── 자주 쓰는 choices ──────────────────────────────────────────────────────
_BOARD_CHOICES: tuple[Choice, ...] = (
    Choice("pre_nxt", "NXT 프리마켓 (08:00~09:00)"),
    Choice(
        "krx_open", "KRX 동시호가 (비활성)", True,
        "사이클 26(2026-05-20)에 비활성 — 값은 호환 보존. 선택해도 매매 시각이 생기지 않는다",
    ),
    Choice("main", "KRX 메인 (09:00~15:39:59)"),
    Choice(
        "krx_after", "KRX 시간외 (비활성)", True,
        "사이클 26(2026-05-20)에 비활성 — 값은 호환 보존. 선택해도 매매 시각이 생기지 않는다",
    ),
    Choice("post_nxt", "NXT 애프터마켓 (15:40~20:00)"),
)

#: 전략별 금지 조합 — 루트 `CLAUDE.md` 의 절대 규칙을 **데이터로** 옮긴 것.
#: "VB 당일 15:20 일괄매도 — `DEFAULT_TRADABLE_BOARDS=("main",)`, POST_NXT 추가 금지".
#: VB 는 `_force_clear_main_only` 가 15:20 에 전량 청산하는 전제로 설계돼 있어,
#: `post_nxt` 를 추가하면 15:40~20:00 에 신규 매수가 열리면서 그 종목이 청산 없이
#: 다음 날로 넘어간다(사이클 26 이 없앤 OVERNIGHT 결함의 부활).
_VB_POST_NXT_FORBIDDEN: tuple[ForbiddenChoice, ...] = (
    ForbiddenChoice(
        "volatility_breakout", "post_nxt",
        "루트 CLAUDE.md 의 VB 조항(‘VB 당일 15:20 일괄매도 —"
        " DEFAULT_TRADABLE_BOARDS=(\"main\",), POST_NXT 추가 금지’)이 금지한다."
        " VB 는 15:20 KRX 일괄 청산을 전제로 설계돼 있어, NXT 애프터(15:40~20:00)에"
        " 매수가 열리면 그 종목이 청산되지 않은 채 다음 날로 넘어간다"
        " (사이클 26 이 없앤 OVERNIGHT 결함의 부활).",
    ),
)

#: cycle287b (2026-09-13) — **SOR 폐기 표시.** 사용자 결정(2026-09-12, 여러 차례):
#: "내가 SOR 하지 말자고 한두번 이야기한게 아닌데? SOR 내용들 UI에서 일단 걷어내자." +
#: "정규장에서는 NXT 필요없어. SOR이 최적호가라는 보장도 없고."
#: cycle287 부터 **시각이 거래소를 정한다**(`order_engine._route_exchange_by_clock`) —
#: 09:00~15:30 정규장과 16:00~20:00 애프터는 KRX, 프리장(08:00~09:00)만 이 값을 본다.
#: ⚠️ **어휘에서 지우지 않고 `deprecated=True` 로 남긴다.** 운영 DB 7 전략이 전부 `SOR`
#: 이고 그 값의 마이그레이션은 별도 승인 대상이라, 어휘를 먼저 좁히면 그 값을 명시 저장하는
#: 경로가 422 가 된다(현재 두 PUT 클라이언트가 변경분만 보내 실害는 없지만, 어휘를 좁히는
#: 것은 DB 값을 옮긴 **뒤**가 순서다 — `test_cycle287_sor_retired.py::test_n3b` 가 그
#: 순서를 강제한다). 폐기 파라미터는 **숨기지 않고 회색 배지로 보여 준다** — 값이 바뀌어도
#: 매매가 안 바뀌는 입력란은 운영자를 속인다(리포 관례, `deprecated` 8키와 동일).
#: 프론트 Settings 의 거래소 선택 UI 에서는 cycle287 이 이미 SOR 을 **선택지에서 제거**했다.
_EXCHANGE_CHOICES: tuple[Choice, ...] = (
    Choice("KRX", "KRX (한국거래소)"),
    Choice("NXT", "NXT (넥스트레이드)", False, "모의투자(VTS) 환경에서는 KIS 가 거부한다"),
    Choice(
        "SOR", "SOR (폐기 — 주문에 쓰이지 않음)", True,
        "cycle287(2026-09-12)부터 시각이 거래소를 정한다 — 정규장·애프터는 KRX, 프리장만 "
        "이 값을 본다. 저장돼 있어도 09:00 이후 주문에는 반영되지 않는다. "
        "새로 선택하지 말 것. 모의투자(VTS)에서는 KIS 가 거부한다",
    ),
)

#: cycle290 — 값 집합의 정본은 코드다. mode = `order_engine._route_exchange_by_clock`
#: 의 `mode` 비교 리터럴("off"·"sell_only") ∪ `_ORDER_EXCHANGE_CLOCK_MODE_DEFAULT`
#: ("enforce"). ⚠️ 손으로 베끼지 않는다 — 가드 G-290-4 가 AST 로 추출해 대조한다.
_CLOCK_MODE_CHOICES: tuple[Choice, ...] = (
    Choice("enforce", "강제 (권장 — 정규장·애프터는 KRX)", False,
           "현행 기본. 09:00~15:30 정규장과 16:00~20:00 KRX 애프터마켓은 KRX 로, "
           "프리장 08:00~09:00 은 저장된 거래소로 나간다"),
    Choice("sell_only", "매도만 라우팅 (애프터 청산 유지)", False,
           "매도·취소만 KRX 로 — 애프터 44/41 청산이 살아 있고 매수만 저장된 "
           "거래소로 돌아간다. 16:00 이후 야간 매수가 전량 거부될 때 쓴다"),
    Choice("off", "끄기 (⚠️ 애프터 청산도 함께 꺼진다)", False,
           "라우팅 전면 정지. 안전한 후퇴가 아니다 — 16:00~20:00 손절이 KRX 44/41 "
           "을 못 타고, 정규장 손절도 거부 한 왕복을 더 탄다. 4단계 뒤의 마지막 수단"),
)

#: `order_engine._AFTER_EXIT_DIVISION_ALLOWED` 와 **정확히** 같은 집합.
#: 값은 **문자열**이다(`"44"`, `44` 아님) — 정수는 `not_in_choices` 422.
_AFTER_EXIT_DIVISION_CHOICES: tuple[Choice, ...] = (
    Choice("44", "최유리지정가 (권장 — 현재가 불필요)", False,
           "반대편 최우선호가에 즉시 붙는다(ORD_UNPR=0). 거부되면 41 로 성격이 "
           "다른 폴백을 한 번 탄다"),
    Choice("41", "지정가 5호가 아래 (⚠️ 현재가 있는 종목만)", False,
           "가격을 우리가 통제한다. 현재가를 못 받는 종목에서는 변환이 취소되고 "
           "시장가가 그대로 나가며 거부 관측·TTL·포기 래치가 전부 꺼진다"),
)

_SIZING_MODE_CHOICES: tuple[Choice, ...] = (
    Choice("position_ratio", "비중 기준 (예산 × position_ratio)"),
    Choice("turtle", "터틀 유닛 (ATR 기반)", False, "손절이 ATR 기반인 전략에만 쓴다"),
)

_NXT_TRADABLE_CHOICES: tuple[Choice, ...] = (
    Choice(None, "전체 (필터 없음)"),
    Choice(True, "NXT 거래가능 종목만"),
    Choice(False, "NXT 불가 종목만"),
)

_HHMM = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"
_TICKER6 = r"^[0-9]{6}$"

_ALL7 = STRATEGY_IDS
_TURTLE4 = ("donchian_swing", "bull_flag_breakout", "vcp_breakout", "kojiro")
_VBLTV = ("volatility_breakout", "long_tail_volatility")
_SCAN6 = (
    "volatility_breakout",
    "long_tail_volatility",
    "donchian_swing",
    "bull_flag_breakout",
    "vcp_breakout",
    "kojiro",
)


def _s(**kw: Any) -> ParamSpec:
    return ParamSpec(**kw)


# ═══════════════════════════════════════════════════════════════════════════
# 101 키
# ═══════════════════════════════════════════════════════════════════════════
PARAM_SPECS: tuple[ParamSpec, ...] = (
    # ── 진입 (47) ───────────────────────────────────────────────────────────
    _s(
        key="buy_threshold", label_ko="매수 등락률 임계", group="entry",
        type="float", min=-30.0, max=30.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("momentum",), range_src="structural",
        help="당일 등락률이 이 값 이상이면 매수. 기본 29.0 = 상한가 근접 매수를 뜻한다."
             " 범위는 KRX 일일 가격제한 ±30% 에서 온 구조적 한계로, 30 초과는 영원히"
             " 도달 불가·−30 미만은 항상 참이다. 사이클 212 에서 '진입 정체성'으로"
             " PARAM_RANGES 에서 제외됐다(AI 자동 튜닝 대상 아님).",
    ),
    _s(
        key="donchian_period", label_ko="돈치안 채널 기간", group="entry",
        type="int", min=2, max=150, step=1, unit="일",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing",), range_src="structural",
        help="N일 신고가 돌파 판정의 N. 일봉 fetch 일수(`max(long_ma+5, donchian+5)`)도"
             " 이 값이 정한다 — 보유 일봉이 retention 230일(≈154 영업일)뿐이라 그보다"
             " 크면 후보가 조용히 0 이 된다(상한 150 의 근거). 사이클 212 에서"
             " '진입 정체성'으로 PARAM_RANGES 에서 제외됐다.",
    ),
    _s(
        key="volume_period", label_ko="거래량 평균 기간", group="entry",
        type="int", min=1, max=150, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing",), range_src="structural",
        help="돌파일 거래량을 비교할 이동평균 기간. 상한은 일봉 retention(≈154 영업일).",
    ),
    _s(
        key="volume_multiplier", label_ko="거래량 증가 배수", group="entry",
        type="float", min=1.0, max=5.0, step=0.1, unit="배",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("donchian_swing",), range_src="param_ranges",
        help="돌파일 거래량이 평균의 몇 배 이상이어야 하는가.",
    ),
    _s(
        key="long_ma_period", label_ko="장기 추세 EMA 기간", group="entry",
        type="int", min=20, max=120, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("donchian_swing",), range_src="param_ranges",
        help="이 EMA 위에 있을 때만 매수. 일봉 fetch 일수 계산에도 함께 쓰인다.",
    ),
    _s(
        key="gap_skip_threshold", label_ko="갭 상승 스킵 임계", group="entry",
        type="float", min=0.0, max=30.0, step=0.1, unit="%",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing",), range_src="structural",
        help="시가가 전일 종가 대비 이 값 이상 갭업이면 그날 그 종목 매수를 건너뛴다."
             " 범위는 KRX 일일 가격제한.",
    ),
    _s(
        key="ema_short", label_ko="단기 EMA 기간", group="entry",
        type="int", min=1, max=300, step=1, unit="봉",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout", "kojiro"), range_src="structural",
        help="VCP 는 50, 고지로 대순환은 5. `ema_short < ema_mid < ema_long` 정렬이"
             " 두 전략 진입 판정의 전제다(역전은 경고).",
    ),
    _s(
        key="ema_mid", label_ko="중기 EMA 기간", group="entry",
        type="int", min=1, max=300, step=1, unit="봉",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout", "kojiro"), range_src="structural",
        help="VCP 60 / 고지로 20. `ema_short < ema_mid < ema_long` 전제.",
    ),
    _s(
        key="ema_long", label_ko="장기 EMA 기간", group="entry",
        type="int", min=1, max=300, step=1, unit="봉",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout", "kojiro"), range_src="structural",
        help="VCP 120 / 고지로 40. `ema_short < ema_mid < ema_long` 전제.",
    ),
    _s(
        key="long_ema_uptrend_days", label_ko="장기 EMA 상승 지속일", group="entry",
        type="int", min=1, max=150, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout",), range_src="structural",
        help="장기 EMA 가 며칠 연속 우상향이어야 추세로 인정하는가.",
    ),
    _s(
        key="base_min_days", label_ko="베이스 최소 길이", group="entry",
        type="int", min=1, max=150, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout",), range_src="structural",
        help="VCP 베이스(횡보 구간) 탐색 최소 길이. `base_min_days <= base_max_days`"
             " 를 어기면 탐색 range 가 비어 후보가 0 이 된다(무증상).",
    ),
    _s(
        key="base_max_days", label_ko="베이스 최대 길이", group="entry",
        type="int", min=1, max=150, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout",), range_src="structural",
        help="VCP prepare 가 실제로 보는 일봉은 100 개 상한이라 그보다 크면 잘린다.",
    ),
    _s(
        key="base_depth_pct", label_ko="베이스 최대 깊이", group="entry",
        type="percent", min=0.10, max=0.50, step=0.01, unit="",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("vcp_breakout",), range_src="param_ranges",
        help="베이스 고점 대비 저점까지 허용 낙폭. **비율 저장**(0.3 = 30%).",
    ),
    _s(
        key="pullback_count_min", label_ko="Pullback 최소 개수", group="entry",
        type="int", min=0, max=20, step=1, unit="회",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout",), range_src="structural",
        help="베이스 안에서 관측돼야 하는 수축(Pullback) 최소 횟수.",
    ),
    _s(
        key="pullback_count_max", label_ko="Pullback 최대 개수", group="entry",
        type="int", min=0, max=20, step=1, unit="회",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout",), range_src="structural",
        help="`pullback_count_min <= pullback_count_max` 를 어기면 후보 0(무증상).",
    ),
    _s(
        key="last_pullback_max", label_ko="마지막 수축 최대폭", group="entry",
        type="percent", min=0.03, max=0.15, step=0.01, unit="",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("vcp_breakout",), range_src="param_ranges",
        help="마지막 수축이 이보다 깊으면 VCP 로 인정하지 않는다. **비율 저장**"
             "(0.12 = 12%).",
    ),
    _s(
        key="min_swing_atr_mult", label_ko="스윙 최소 ATR 배수", group="entry",
        type="float", min=0.0, max=None, step=0.1, unit="배",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("vcp_breakout",), range_src="structural",
        help="이 배수보다 작은 스윙은 노이즈로 보고 수축으로 세지 않는다. 상한 근거 없음"
             "(과도하게 크면 수축이 하나도 안 세져 후보 0).",
    ),
    _s(
        key="volume_contraction_ratio", label_ko="거래량 수축 비율", group="entry",
        type="percent", min=0.30, max=1.00, step=0.01, unit="",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("vcp_breakout",), range_src="param_ranges",
        help="베이스 후반 거래량이 전반의 몇 배 이하로 줄어야 하는가. **비율 저장**"
             "(0.7 = 70%). 1.0 = 사실상 필터 해제.",
    ),
    _s(
        key="breakout_volume_mult", label_ko="돌파 거래량 배수", group="entry",
        type="float", min=1.0, max=5.0, step=0.1, unit="배",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("bull_flag_breakout", "vcp_breakout"), range_src="param_ranges",
        help="돌파 시점 거래량이 기준 평균의 몇 배 이상이어야 하는가. **VCP·BFB 공용 키** —"
             " 한 전략에서 바꿔도 다른 전략의 값은 그대로다(전략별로 저장된다).",
    ),
    _s(
        key="pole_lookback_min", label_ko="Pole 탐색 최소 기간", group="entry",
        type="int", min=1, max=150, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="깃대(Pole) 를 찾을 최소 일수. `pole_lookback_min <= pole_lookback_max` 전제.",
    ),
    _s(
        key="pole_lookback_max", label_ko="Pole 탐색 최대 기간", group="entry",
        type="int", min=1, max=150, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="깃대를 찾을 최대 일수.",
    ),
    _s(
        key="pole_min_return", label_ko="Pole 최소 상승률", group="entry",
        type="float", min=0.0, max=None, step=0.5, unit="%",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="깃대 구간의 누적 상승률 하한. 누적이라 ±30%(일일 가격제한) 를 넘을 수 있어"
             " 상한 근거가 없다.",
    ),
    _s(
        key="pole_max_red_ratio", label_ko="Pole 최대 음봉 비율", group="entry",
        type="percent", min=0.0, max=1.0, step=0.01, unit="",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="깃대 구간에서 허용하는 음봉 비중. **비율 저장**(0.45 = 45%)."
             " 1.0 = 필터 해제 상당.",
    ),
    _s(
        key="flag_lookback_min", label_ko="Flag 탐색 최소 기간", group="entry",
        type="int", min=1, max=150, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="깃발(Flag) 눌림 구간 최소 일수. `flag_lookback_min <= flag_lookback_max` 전제.",
    ),
    _s(
        key="flag_lookback_max", label_ko="Flag 탐색 최대 기간", group="entry",
        type="int", min=1, max=150, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="깃발 눌림 구간 최대 일수.",
    ),
    _s(
        key="flag_retracement_max", label_ko="Flag 최대 되돌림", group="entry",
        type="percent", min=0.0, max=1.0, step=0.01, unit="",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="깃대 상승분 중 되돌려도 되는 최대 비중. **비율 저장**(0.5 = 50%)."
             " 1.0 = 깃대 전부를 반납해도 통과 = 필터 해제 상당.",
    ),
    _s(
        key="flag_volume_ratio", label_ko="Flag 거래량 비율", group="entry",
        type="percent", min=0.0, max=1.0, step=0.01, unit="",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="깃발 구간 거래량이 깃대 구간의 몇 배 이하여야 하는가(수축 확인)."
             " **비율 저장**(0.6 = 60%). 1.0 = 필터 해제 상당.",
    ),
    _s(
        key="macd_signal", label_ko="MACD 시그널 기간", group="entry",
        type="int", min=1, max=100, step=1, unit="봉",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="고지로 대순환의 MACD 시그널선 기간. 지표 모듈에 그대로 전달된다.",
    ),
    _s(
        key="slope_lookback", label_ko="기울기 산출 봉수", group="entry",
        type="int", min=1, max=50, step=1, unit="봉",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="MACD3 기울기를 몇 봉 차이로 재는가.",
    ),
    _s(
        key="stage1_freshness", label_ko="1국면 신선도", group="entry",
        type="int", min=1, max=50, step=1, unit="봉",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="6국면 → 1국면 전환 후 몇 봉 안쪽이어야 '갓 전환'으로 보는가."
             " 백테스트 근거로 3 → 5 로 넓혔다(PF 1.60 → 1.75,"
             " `_workspace/00_leader_trading_rules.md`). 진입 후보 수에 직접 영향.",
    ),
    _s(
        key="atr_ratio_min", label_ko="변동성 밴드 하한", group="entry",
        type="percent", min=0.0, max=1.0, step=0.005, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="ATR / 가격 비율의 하한. 이보다 조용한 종목은 후보에서 뺀다."
             " **비율 저장**(0.01 = 1%). `atr_ratio_min <= atr_ratio_max` 전제.",
    ),
    _s(
        key="atr_ratio_max", label_ko="변동성 밴드 상한", group="entry",
        type="percent", min=0.0, max=1.0, step=0.005, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="ATR / 가격 비율의 상한. 이보다 거친 종목은 후보에서 뺀다."
             " **비율 저장**(0.06 = 6%).",
    ),
    _s(
        key="gap_up_skip_pct", label_ko="갭업 스킵 임계", group="entry",
        type="float", min=0.0, max=100.0, step=0.5, unit="%",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="시가 갭이 이 값 이상이면 그날 그 종목을 영구 스킵."
             " **음수를 넣으면 거의 모든 종목이 스킵된다**(비교가 `gap_rate >= 값`).",
    ),
    _s(
        key="gap_down_skip_pct", label_ko="갭다운 스킵 임계", group="entry",
        type="float", min=-100.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="sign",
        help="시가 갭이 이 값 이하면 그날 그 종목을 영구 스킵. **음수여야 한다** —"
             " 양수를 넣으면 비교가 `gap_rate <= 양수` 라 거의 모든 종목이 스킵된다.",
    ),
    _s(
        key="rank_w_macd3", label_ko="순위 가중치 · MACD3 기울기", group="entry",
        type="percent", min=0.0, max=1.0, step=0.05, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="매수 후보 **순위**의 성분 가중치. 세 가중치는 합으로 자동 정규화되므로"
             " 합이 1 이 아니어도 무해하지만, **셋을 모두 0 으로 두면 전 후보 점수가 0**"
             " 이라 순위가 무의미해진다. 후보 집합 자체는 바뀌지 않는다(순서만).",
    ),
    _s(
        key="rank_w_band", label_ko="순위 가중치 · 띠폭 확장률", group="entry",
        type="percent", min=0.0, max=1.0, step=0.05, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="순위 성분 가중치(자동 정규화). 세 가중치 동시 0 금지.",
    ),
    _s(
        key="rank_w_fresh", label_ko="순위 가중치 · 신선도", group="entry",
        type="percent", min=0.0, max=1.0, step=0.05, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="순위 성분 가중치(자동 정규화). 세 가중치 동시 0 금지.",
    ),
    _s(
        key="max_positions_per_sector", label_ko="섹터당 최대 보유", group="entry",
        type="int", min=0, max=None, step=1, unit="개",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="같은 섹터에서 동시에 들 수 있는 종목 수. **매수 게이트 전용**(청산 무관)이고"
             " 0 이면 비활성. 섹터 조회 실패는 fail-open(통과).",
    ),
    _s(
        key="k_period", label_ko="변동성 산출 기간", group="entry",
        type="int", min=5, max=60, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=_VBLTV, range_src="param_ranges",
        help="변동성 돌파 목표가 계산에 쓸 과거 일수(레인지 평균).",
    ),
    _s(
        key="k_value_krx_main", label_ko="K값 · KRX 메인", group="entry",
        type="float", min=0.5, max=2.0, step=0.1, unit="배",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=_VBLTV, range_src="param_ranges",
        help="KRX 메인 보드 목표가 = 기준시가 + K × 레인지. 기준시가는 사이클 272 이후"
             " **KRX REST 시가 단독**이다(통합 WS 채널의 세션 시가를 쓰지 않는다).",
    ),
    _s(
        key="k_value_nxt_pre", label_ko="K값 · NXT 프리마켓", group="entry",
        type="float", min=0.5, max=2.0, step=0.1, unit="배",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=_VBLTV, range_src="param_ranges",
        deprecated_for=("volatility_breakout",),
        help="NXT 프리마켓(08:00~09:00) 목표가 배수. VB 는 기본 `tradable_boards=['main']`"
             " 이라 곱해지는 경로가 없다(보드를 추가하면 되살아난다). LTV 는 프리장을"
             " 실제로 매매하므로 **살아 있는 값**이다.",
    ),
    _s(
        key="k_value_nxt_post", label_ko="K값 · NXT 애프터마켓", group="entry",
        type="float", min=0.5, max=2.0, step=0.1, unit="배",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=_VBLTV, range_src="param_ranges",
        deprecated_for=("volatility_breakout",),
        help="NXT 애프터마켓(15:40~20:00) 목표가 배수. VB 는 기본 보드가 main 단독이라"
             " 효력이 없고, **LTV 는 야간 목표가에 실제로 곱한다** — 문서의 '호환 보존'"
             " 표현은 VB 한정이다. 보수적 운용 권장값 1.2~1.5"
             "(`_workspace/00_leader_trading_rules.md`).",
    ),
    _s(
        key="min_prdy_rate", label_ko="전일 대비 최소 등락률", group="entry",
        type="float", min=0.0, max=30.0, step=0.5, unit="%",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("long_tail_volatility",), range_src="param_ranges",
        help="후보가 되기 위한 전일 대비 최소 상승률.",
    ),
    _s(
        key="exclude_consecutive_limit", label_ko="연속 상한가 제외 일수", group="entry",
        type="int", min=0, max=5, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("long_tail_volatility",), range_src="param_ranges",
        help="연속 상한가가 이 일수 이상인 종목은 후보에서 제외. 0 = 제외 안 함.",
    ),
    _s(
        key="reentry_cooldown_days", label_ko="재진입 쿨다운", group="entry",
        type="int", min=0, max=60, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("volatility_breakout", "long_tail_volatility",
                    "bull_flag_breakout", "vcp_breakout"),
        range_src="structural",
        help="손절 후 같은 종목을 다시 사기까지 기다리는 일수. 0 = 즉시 재진입 허용."
             " 권장값 VB 2 / BFB 3 / VCP 7(`_workspace/00_leader_trading_rules.md`).",
    ),
    _s(
        key="max_breakout_extension_pct", label_ko="돌파 추격 상한", group="entry",
        type="float", min=0.0, max=100.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing", "bull_flag_breakout", "vcp_breakout"),
        range_src="structural",
        help="돌파 기준선에서 이 비율 넘게 뜬 가격은 추격 매수하지 않는다."
             " 사이클 209 에서 AI 튜너가 3.0 → 하한 0.5 로 과튜닝한 사고 뒤"
             " PARAM_RANGES 에서 제외됐다. 작게 두면 매수가 사실상 멈춘다.",
    ),
    _s(
        key="breakout_retention_minutes", label_ko="돌파 유지 시간", group="entry",
        type="int", min=1, max=30, step=1, unit="분",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="param_ranges",
        help="돌파가가 이 시간만큼 유지돼야 진짜 돌파로 인정(가짜 돌파 흡수).",
    ),

    # ── 청산 (21) ───────────────────────────────────────────────────────────
    _s(
        key="stop_loss_rate", label_ko="손절률", group="exit",
        type="float", min=-15.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=True, deprecated=False,
        applies_to=("momentum", "volatility_breakout", "donchian_swing",
                    "bull_flag_breakout", "vcp_breakout"),
        range_src="param_ranges",
        help="매수가 대비 이 비율 이하로 떨어지면 손절. **음수여야 한다** — VB 는"
             " `return tv if tv < 0 else 0.0` 로 양수/0 을 조용히 '손절 없음'으로 바꾼다."
             " 터틀 전략에서는 `_entry_atr` 스탬프가 있는 포지션이 ATR 손절을 타므로"
             " 이 값이 적용되지 않을 수 있다.",
    ),
    _s(
        key="trailing_stop_rate", label_ko="트레일링 스탑", group="exit",
        type="float", min=-10.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=True, deprecated=False,
        applies_to=("momentum", "long_tail_volatility"), range_src="param_ranges",
        help="매수 후 최고가 대비 이 비율만큼 밀리면 청산. **음수여야 한다.**",
    ),
    _s(
        key="daily_loss_limit", label_ko="일일 손실 한도", group="exit",
        type="float", min=-20.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=True, deprecated=False,
        applies_to=_ALL7, range_src="param_ranges",
        help="그날 전략 손익이 이 비율 이하가 되면 그 전략의 신규 매수를 멈춘다."
             " 판정은 전략 파일이 아니라 공통 관문 `strategy_base` 한 곳에서 한다."
             " **음수여야 한다.**",
    ),
    _s(
        key="gap_up_threshold", label_ko="갭업 청산 임계", group="exit",
        type="float", min=0.0, max=30.0, step=0.5, unit="%",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("momentum", "long_tail_volatility"), range_src="param_ranges",
        help="시가가 이만큼 갭업하면 익일 청산 경로에서 즉시 이익 실현한다."
             " 익일 청산 판정(scheduler)과 LLM 게이트 피처에도 함께 읽힌다.",
    ),
    _s(
        key="atr_period", label_ko="ATR 기간", group="exit",
        type="int", min=1, max=300, step=1, unit="봉",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=_TURTLE4, range_src="structural",
        help="ATR 산출 기간. 이 값 하나가 **청산(샹들리에·ATR 손절)·사이징(터틀 유닛)·"
             "고지로 변동성 밴드** 세 곳에 동시에 영향을 준다.",
    ),
    _s(
        key="atr_trail_mult", label_ko="샹들리에 트레일 배수", group="exit",
        type="float", min=0.0, max=None, step=0.1, unit="배",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing", "bull_flag_breakout", "vcp_breakout"),
        range_src="structural",
        help="최고가 − 배수 × ATR 로 트레일링 손절선을 잡는다. 사이클 223 에서"
             " '보유기간 정체성 상수'로 PARAM_RANGES 에서 제거됐다 — 단기 손실을"
             " 목적함수로 삼는 튜너는 구조적으로 청산을 조여 추세추종을 데이트레이딩으로"
             " 변태시킨다. **3 전략 공유 키**(전략별로 따로 저장된다).",
    ),
    _s(
        key="stop_atr", label_ko="ATR 손절 배수", group="exit",
        type="float", min=0.0, max=None, step=0.1, unit="배",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=_TURTLE4, range_src="structural",
        help="매수가 − 배수 × 진입 ATR 이 손절선. **`_entry_atr` 스탬프가 있는 포지션만**"
             " 이 경로를 탄다(스탬프 없는 포지션은 고정% 손절). 상한 근거 없음.",
    ),
    _s(
        key="trail_atr", label_ko="ATR 트레일 배수 (고지로)", group="exit",
        type="float", min=0.0, max=None, step=0.1, unit="배",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="고지로 전용 트레일 배수. `atr_trail_mult` 재사용을 금지하고 고유명을 쓴다.",
    ),
    _s(
        key="breakeven_promote_atr", label_ko="본전 승격 배수", group="exit",
        type="float", min=0.0, max=None, step=0.1, unit="배",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=_TURTLE4, range_src="sign",
        help="최고가가 매수가 + 배수 × ATR 을 넘으면 손절선을 매수가(본전)로 올린다."
             " **0 = 비활성**(코드가 `> 0` 으로 게이팅). 활성 권장값 1.5"
             "(`_workspace/00_leader_trading_rules.md`). 손절선은 조이는 방향으로만 움직인다.",
    ),
    _s(
        key="turtle_backstop_pct", label_ko="터틀 손절 최대폭", group="exit",
        type="float", min=-100.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing", "bull_flag_breakout", "vcp_breakout"),
        range_src="sign",
        help="고ATR 종목에서 ATR 손절선이 너무 멀어질 때 씌우는 % 상한."
             " **음수여야 한다** — 코드가 `if backstop < 0` 으로 게이팅하므로 0/양수는"
             " 조용히 비활성된다(무증상).",
    ),
    _s(
        key="turtle_min_stop_pct", label_ko="터틀 손절 최소폭", group="exit",
        type="float", min=-100.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout", "vcp_breakout"), range_src="sign",
        help="저ATR 종목에서 ATR 손절선이 과도하게 조여지는 것을 막는 최소폭."
             " **음수여야 한다**(`if min_stop_pct < 0` 게이트)."
             " `turtle_backstop_pct <= turtle_min_stop_pct` 여야 최소폭 밴드가 살아 있다.",
    ),
    _s(
        key="hard_stop_pct", label_ko="고정 하드 손절", group="exit",
        type="float", min=-100.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="sign",
        help="ATR 과 무관한 고정% 손절(재시작·ATR=0 무손절 차단용 backstop)."
             " ⚠️ **부호 게이트가 없다** — `loss_rate <= hard_stop_pct` 뿐이라"
             " 양수를 넣으면 **모든 보유 포지션이 즉시 손절**된다.",
    ),
    _s(
        key="channel_exit_period", label_ko="청산 채널 기간", group="exit",
        type="int", min=0, max=150, step=1, unit="일",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing",), range_src="structural",
        help="N일 신저가로 떨어지면 청산. **0 = 비활성.** 진입 채널"
             "(`donchian_period`)보다 짧아야 추세추종이 성립한다.",
    ),
    _s(
        key="breakout_fail_n_days", label_ko="돌파 실패 판정일", group="exit",
        type="int", min=1, max=60, step=1, unit="일",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing",), range_src="structural",
        help="돌파 후 이 일수 안에 진전이 없으면 실패로 보고 정리한다. 사이클 223 에서"
             " '보유기간 정체성 상수'로 PARAM_RANGES 에서 제거됐다(하한으로 밀면 20일"
             " 신고가 추세추종이 1~2일 데이트레이딩이 된다).",
    ),
    _s(
        key="max_hold_days", label_ko="최대 보유일수", group="exit",
        type="int", min=1, max=365, step=1, unit="일",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout",), range_src="structural",
        help="이 일수를 넘기면 정리. 실제 판정은 캘린더 +2일 보정이 들어간다"
             "(주말·공휴일 흡수).",
    ),
    _s(
        key="intraday_stop_loss", label_ko="당일 손절률", group="exit",
        type="float", min=-15.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=True, deprecated=False,
        applies_to=("long_tail_volatility",), range_src="param_ranges",
        help="당일 모드(상한가 미도달)의 손절률. **음수여야 한다.**"
             " 통상 `intraday_stop_loss >= overnight_stop_loss`"
             "(익일 보유 쪽이 더 넓다).",
    ),
    _s(
        key="overnight_stop_loss", label_ko="익일 보유 손절률", group="exit",
        type="float", min=-15.0, max=0.0, step=0.5, unit="%",
        editable=True, risk="high", auto_tunable=True, deprecated=False,
        applies_to=("long_tail_volatility",), range_src="param_ranges",
        help="상한가 모드로 전환해 익일까지 들고 갈 때의 손절률. **음수여야 한다.**",
    ),
    _s(
        key="limit_up_threshold", label_ko="상한가 판정 임계", group="exit",
        type="float", min=15.0, max=30.0, step=0.5, unit="%",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=("long_tail_volatility",), range_src="param_ranges",
        help="당일 등락률이 이 값 이상이면 '상한가 모드'로 전환해 익일 청산 경로를 탄다"
             "(청산 규약 자체가 바뀌는 스위치).",
    ),
    _s(
        key="failed_breakout_exit_enabled", label_ko="가짜 돌파 조기청산 사용", group="exit",
        type="bool", min=None, max=None, step=None, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("volatility_breakout",), range_src="enum",
        help="목표가를 뚫었다가 되밀리면 조기 청산한다. **기본 꺼짐** — 꺼져 있을 뿐"
             " 코드는 살아 있다(레거시 死키와 다르다). 켜면 청산이 실제로 빨라진다.",
    ),
    _s(
        key="failed_breakout_buffer_pct", label_ko="가짜 돌파 버퍼", group="exit",
        type="float", min=-100.0, max=0.0, step=0.1, unit="%",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("volatility_breakout",), range_src="sign",
        help="목표가 × (1 + 버퍼/100) 아래로 되밀리면 실패로 본다. **음수여야 한다**"
             "(양수면 목표가 위에서 청산 판정이 걸린다).",
    ),
    _s(
        key="failed_breakout_confirm_ticks", label_ko="가짜 돌파 확인 틱수", group="exit",
        type="int", min=1, max=100, step=1, unit="회",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("volatility_breakout",), range_src="structural",
        help="연속 몇 틱 동안 조건이 유지돼야 실패로 확정하는가(노이즈 흡수).",
    ),

    # ── 사이징·리스크 (8) ───────────────────────────────────────────────────
    _s(
        key="position_ratio", label_ko="종목당 비중", group="sizing_risk",
        type="percent", min=0.01, max=1.0, step=0.01, unit="",
        editable=True, risk="high", auto_tunable=True, deprecated=False,
        applies_to=_ALL7, range_src="param_ranges",
        help="종목당 매수금액 = 순자산 × 현금사용비율 × (전략비중 / Σ비중) × 이 값."
             " **비율 저장**(0.25 = 25%). ⚠️ `position_ratio × max_positions <= 1.0`"
             " 불변식이 있고 7 전략 중 6 전략이 정확히 1.0 이라, 이 값을 올리려면"
             " `max_positions` 를 **같은 요청에서 함께** 내려야 한다.",
    ),
    _s(
        key="max_positions", label_ko="동시 보유 종목수", group="sizing_risk",
        type="int", min=1, max=None, step=1, unit="개",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_ALL7, range_src="structural",
        help="이 전략이 동시에 들 수 있는 종목 수. **리스크 정체성 상수**라 AI 자동 튜닝"
             " 대상이 아니다(사이클 208 이전에 kojiro 10×0.20 = 예산 200% 사고)."
             " `position_ratio` 와 곱이 1.0 이하여야 한다.",
    ),
    _s(
        key="sizing_mode", label_ko="사이징 방식", group="sizing_risk",
        type="enum", min=None, max=None, step=None, unit="",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_TURTLE4, range_src="enum", choices=_SIZING_MODE_CHOICES,
        help="`turtle` 만 특별 취급하고 그 밖의 값은 전부 `position_ratio` 로 낙하한다."
             " ⚠️ 이 값을 바꿔도 **이미 보유 중인 포지션의 손절 규약은 바뀌지 않는다**"
             " — 청산 분기는 `sizing_mode` 가 아니라 매수 시 찍힌 `_entry_atr` 스탬프로"
             " 갈린다.",
    ),
    _s(
        key="risk_pct", label_ko="유닛당 리스크 비율", group="sizing_risk",
        type="percent", min=0.0, max=1.0, step=0.001, unit="",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_TURTLE4, range_src="structural",
        help="터틀 유닛 = floor(전략예산 × 이 비율 ÷ ATR). **비율 저장**"
             "(0.005 = 0.5%). 0 이하면 터틀 사이징이 꺼지고 비중 경로로 낙하한다."
             " 랏 상한 `max_lot_units` 계산에도 같은 값이 쓰인다.",
    ),
    _s(
        key="min_vol_floor_pct", label_ko="최소 변동성 바닥", group="sizing_risk",
        type="float", min=0.0, max=100.0, step=0.1, unit="%",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=_TURTLE4, range_src="structural",
        help="ATR / 가격 이 이 퍼센트 미만이면 터틀 유닛을 포기하고 비중 경로로 낙하한다"
             "(저변동 종목의 유닛 폭발 차단). **퍼센트 저장**(1.0 = 1%) — 이름이 `_pct`"
             " 라도 비율이 아니다. 0 = 비활성.",
    ),
    _s(
        key="max_lot_units", label_ko="랏당 최대 유닛 (K)", group="sizing_risk",
        type="float", min=1.0, max=20.0, step=0.5, unit="유닛",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_TURTLE4, range_src="clamp",
        help="터틀 전략의 **모든** 매수 랏(유닛·비중 낙하·1주 폴백)을 이 유닛 수 이하로"
             " 자른다. 캡이 0 이면 그 종목을 사지 않는다. **하한 1.0 은 정상 터틀 랏이"
             " 캡에 걸리지 않는다는 수학적 전제**이고 상한 20.0 은 롤백 다이얼이다."
             " 읽는 쪽 클램프가 같은 범위를 강제한다(라우트 검증과 이중)."
             " ⚠️ 당일 캡 0 으로 이미 소진된 종목은 값을 되돌려도 다음 세션부터 되살아난다.",
    ),
    _s(
        key="max_lot_ratio_mult", label_ko="랏 명목 상한 배수 (Kρ)", group="sizing_risk",
        type="float", min=1.0, max=20.0, step=0.5, unit="배",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_ALL7, range_src="clamp",
        help="랏 명목을 `배수 × position_ratio × 전략예산` 이하로 자른다. 1주도 못 사면"
             " 매수하지 않는다. **키를 지우면 OFF**(`max_lot_units` 와 규약이 반대)."
             " 하한 1.0 은 정상 비중 랏 무접촉의 전제, 상한 20.0 은 롤백 다이얼."
             " 실효는 대부분 1주 폴백 랏이다.",
    ),
    _s(
        key="max_open_risk_pct", label_ko="총 오픈리스크 상한", group="sizing_risk",
        type="float", min=0.0, max=100.0, step=0.5, unit="%",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=("kojiro",), range_src="structural",
        help="보유 포지션들의 합산 오픈리스크가 전략 예산의 이 퍼센트를 넘으면 신규 매수를"
             " 멈춘다. **퍼센트 저장**(4.5 = 4.5%). **0 = 비활성.**"
             " 계산 예외는 전부 흡수하고 통과시킨다(fail-open).",
    ),

    # ── 스캔·유니버스 (5) ───────────────────────────────────────────────────
    _s(
        key="min_market_cap", label_ko="최소 시가총액", group="scan_universe",
        type="int", min=10_000_000_000, max=10_000_000_000_000, step=100_000_000,
        unit="원",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=_SCAN6, range_src="param_ranges",
        help="유니버스 필터 하한. **원 단위 저장**(100000000000 = 1,000억).",
    ),
    _s(
        key="min_trade_amount", label_ko="최소 거래대금", group="scan_universe",
        type="int", min=1_000_000_000, max=1_000_000_000_000, step=100_000_000,
        unit="원",
        editable=True, risk="normal", auto_tunable=True, deprecated=False,
        applies_to=_SCAN6, range_src="param_ranges",
        help="유니버스 필터 하한. **원 단위 저장**(20000000000 = 200억).",
    ),
    _s(
        key="max_scan_stocks", label_ko="최대 스캔 종목수", group="scan_universe",
        type="int", min=None, max=None, step=1, unit="개",
        editable=True, risk="high", auto_tunable=True, deprecated=False,
        applies_to=_SCAN6, range_src="none",
        help="⚠️ **범위 미정.** `PARAM_RANGES` 는 (10, 500) 이지만 BFB·VCP·고지로의"
             " 현재 기본값이 **4000** 이라 그 범위를 사람의 편집 한계로 쓰면 아무것도"
             " 안 고치고 저장만 눌러도 거부된다. 두 숫자 중 어느 쪽이 옳은지에 대한"
             " 근거 문서가 없어 범위를 **지어내지 않았다** — 자료형(정수)과 양수만 본다."
             " (AI 튜너는 종전대로 PARAM_RANGES 안에서만 움직인다.)",
    ),
    _s(
        key="exclude_tickers", label_ko="제외 종목코드", group="scan_universe",
        type="list_str", min=None, max=None, step=None, unit="",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing", "kojiro"), range_src="structural",
        pattern=_TICKER6,
        help="유니버스에서 영구 제외할 6자리 종목코드 목록. 빈 목록 = 제외 없음.",
    ),
    _s(
        key="nxt_tradable", label_ko="NXT 거래가능 필터", group="scan_universe",
        type="enum", min=None, max=None, step=None, unit="",
        editable=True, risk="normal", auto_tunable=False, deprecated=False,
        applies_to=("donchian_swing", "kojiro"), range_src="enum",
        choices=_NXT_TRADABLE_CHOICES,
        help="종목마스터의 NXT 거래가능 여부로 유니버스를 거른다. **비움(null) 은"
             " '필터 안 함'이지 '거래 불가'가 아니다.** 같은 이름의 종목마스터 컬럼과"
             " 혼동하지 말 것.",
    ),

    # ── 시간·보드 (6) ───────────────────────────────────────────────────────
    _s(
        key="tradable_boards", label_ko="매매 허용 보드", group="time_board",
        type="list_str", min=None, max=None, step=None, unit="",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_ALL7, range_src="enum", choices=_BOARD_CHOICES,
        min_items=1, forbidden_choices=_VB_POST_NXT_FORBIDDEN,
        help="**매수 진입 전용**이다 — 매도·손절·트레일링·익일청산·15:20 강제청산은"
             " 보드와 무관하게 항상 작동한다. ⚠️ 알 수 없는 값은 코드가 경고 후 조용히"
             " 무시하고, 전부 무시되면 기본 보드로 폴백한다(오타가 무증상)."
             " 그래서 화면·서버 양쪽이 값 집합을 강제한다."
             " ⚠️ **빈 목록은 거부한다**(`min_items=1`) — 효과가 전략마다 정반대이기"
             " 때문이다. momentum·VB·LTV·donchian 은 `session._DEFAULT_TRADABLE_BOARDS`"
             " 로 폴백해 매수가 그대로 이어지고(= 저장했는데 아무 일도 안 일어난다),"
             " BFB·VCP·kojiro 는 폴백 항목이 없어 공집합 = **매수 전면 중단**이다."
             " 매수를 멈추려면 이 목록을 비우지 말고 전략을 비활성화한다.",
    ),
    _s(
        key="exchange", label_ko="주문 거래소", group="time_board",
        type="enum", min=None, max=None, step=None, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=_ALL7, range_src="enum", choices=_EXCHANGE_CHOICES,
        help="주문 전송 시 KIS 에 넘기는 거래소 코드. ⚠️ cycle287(2026-09-12)부터 이 값이"
             " 실제로 쓰이는 구간은 **프리장(08:00~09:00)뿐**이다 — 09:00~15:30 정규장과"
             " 16:00~20:00 애프터마켓은 시각이 KRX 를 강제한다"
             " (`order_engine._route_exchange_by_clock`, 킬스위치"
             " `order_exchange_clock_mode`). SOR 은 폐기됐다(사용자 결정). 모의투자(VTS)"
             " 환경에서 NXT/SOR 는 거부된다. 종목이 NXT 비대상이면 코드가 KRX 로 자동"
             " 다운그레이드한다.",
    ),
    _s(
        key="entry_start", label_ko="매수 시작 시각", group="time_board",
        type="str", min=None, max=None, step=None, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout", "vcp_breakout"), range_src="structural",
        pattern=_HHMM,
        help="`HH:MM`(KST). 이 시각 전에는 신규 매수를 하지 않는다. ⚠️ 파서가"
             " `int()` 캐스트만 하므로 `9시5분`·`25:00` 같은 값은 매매 루프 안에서"
             " 예외를 던진다 — 형식 검증은 선택이 아니라 필수다."
             " `entry_start < entry_end` 를 어기면 하루 종일 매수가 막힌다.",
    ),
    _s(
        key="entry_end", label_ko="매수 종료 시각", group="time_board",
        type="str", min=None, max=None, step=None, unit="",
        editable=True, risk="high", auto_tunable=False, deprecated=False,
        applies_to=("bull_flag_breakout", "vcp_breakout"), range_src="structural",
        pattern=_HHMM,
        help="`HH:MM`(KST). 이 시각 후에는 신규 매수를 하지 않는다(청산은 계속).",
    ),
    _s(
        key="order_exchange_clock_mode", label_ko="시각 기반 거래소 라우팅",
        group="time_board",
        type="enum", min=None, max=None, step=None, unit="",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_ALL7, range_src="enum", choices=_CLOCK_MODE_CHOICES,
        help="cycle287 **규칙 1 킬스위치**. `enforce`(기본)면 정규장(09:00~15:30)과"
             " KRX 애프터마켓(16:00~20:00, 2026-09-14 신설)의 주문이 저장된 `exchange`"
             " 값과 무관하게 KRX 로 나간다. 프리장(08:00~09:00)은 세 값 모두에서"
             " 무접촉이다.\n"
             "**사고 중 조작 순서** — 스위치를 만지기 전에 ① `[order_channel_config]`"
             " 로 살아 있는 값 ② `[after_exit_division]` 의 `cur=` ③"
             " `[after_exit_rejected]`/`[after_exit_giveup]` 을 읽어 **거부 / 미체결"
             " / 악체결**을 먼저 가른다. 처방이 반대다. ⑴ **매도 거부**면 이 키는"
             " 만지지 않고 `after_market_exit_division` 을 본다. ⑵ **매수만"
             " 거부**(LTV 야간)면 `sell_only` — 애프터 청산이 살아 있는 유일한"
             " 정당 용도다. ⑶ 그래도 안 되면 `off` 가 아니라"
             " `PUT {\"exchange\":\"KRX\"}` — clause 1 이 mode 검사보다 앞서"
             " 발화해 KRX 로 고정되면서 **44/41 전환이 보존된다**(부작용은 프리장"
             " 주문도 KRX 로 가는 것 하나). ⑷ `off` 는 라우터 자체가 엉뚱한"
             " 시장으로 보낸다는 증거가 있을 때만.\n"
             "⚠️ **`off` 는 애프터마켓 청산도 함께 끈다** — 44/41 변환의 게이트가"
             " \"거래소가 KRX 인가\"라서, 라우팅을 끄면 거래소가 저장값으로 남아"
             " 변환 분기에 도달하지 않고 16:00~20:00 청산이 NXT 애프터로 시장가를"
             " 발사한다(NXT 는 시장가를 받지 않는다). 09:00~15:30 손절도 같은"
             " 이유로 거부 한 왕복을 더 탄 뒤 5호가 지정가로 떨어진다. 게다가"
             " **NXT 비대상 종목(`nxt_tradable=False`)에는 `off` 가 듣지 않는다**"
             " — 이미 KRX 로 다운그레이드돼 계속 44/41 을 탄다. 절반만 꺼지는"
             " 스위치다.\n"
             "⚠️ `sell_only` 는 **16:00~19:50 LTV 야간 매수를 다시 켠다** —"
             " `enforce` 에서는 그 매수가 KRX 로 라우팅돼 시장가를 받지 않는"
             " 창에서 전량 거부되고 있다. 순수 방어 다이얼이 아니다.\n"
             "⚠️ 오타·대소문자(`OFF`)는 이 선택지 목록이 422 로 막지만, DB 를 직접"
             " UPDATE 해 들어온 미지 값은 읽는 쪽이 **`enforce`** 로 해석한다"
             "(라우터에 mode 화이트리스트가 없다). 그래서 오타를 막는 관문은 이"
             " enum **하나**다.\n"
             "PUT 은 **즉시** 반영되고 `strategy_config` SQL 은 다음 재시작에서만"
             " 반영된다 — 보유 중 장중 재시작은 금지(D6)이므로 장중 실효 수단은"
             " PUT 뿐이다. ⚠️ **이 키는 전략별이다** — 전역 스위치가 없으므로 보유"
             " 중인 전략 각각에 PUT 한다. 반영의 즉시 증거는 PUT 200 응답의"
             " `data.applied`다. `[order_channel_config] strategy= mode="
             " division=` 카나리아는 **그 전략이 실제로 주문을 낼 때만** 1행"
             " 찍히므로 부재가 실패의 증거는 아니다(`off` 는 `[order_channel]`"
             " 을 아예 남기지 않는다). ⚠️ **이 스위치는 그 전략의 `exchange` 가"
             " `NXT`/`SOR` 일 때만 효력이 있다** — clause 1 이 mode 검사보다 앞서"
             " `exchange=\"KRX\"` 면 세 값 모두 무동작이다(`reason=base_krx` 가"
             " 그 증거). AI 자동 튜닝 대상이 아니다(`PARAM_RANGES` 편입 금지).",
    ),
    _s(
        key="after_market_exit_division", label_ko="KRX 애프터 청산 호가유형",
        group="time_board",
        type="enum", min=None, max=None, step=None, unit="",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_ALL7, range_src="enum", choices=_AFTER_EXIT_DIVISION_CHOICES,
        help="cycle287 **규칙 2 다이얼**. KRX 애프터마켓(16:00~20:00)에서 시장가"
             " 청산을 어떤 호가유형으로 바꿔 보낼지 고른다 — 그 창의 KRX 는"
             " 시장가(`01`)도 지정가(`00`)도 받지 않고 `41~47` 만 받는다.\n"
             "`\"44\"`(기본, 최유리지정가 `ORD_UNPR=0`) = 반대편 최우선호가에 즉시"
             " 붙는다. **현재가가 없어도 주문이 성립**하고, 거부되면 `41` 로"
             " 성격이 다른 폴백을 한 번 탄다.\n"
             "`\"41\"`(지정가 `현재가 5호가 아래`) = 우리가 가격을 통제한다."
             " **언제 쓰는가** = 주문은 접수됐는데 **미체결이거나 최유리가 얇은"
             " 호가를 크로스해 악체결**될 때. 코드 재배포 없이 쓸 수 있는 유일한"
             " 완화책이다.\n"
             "🔴 **`41` 로 바꾸기 전에 `[after_exit_division]` 의 `cur=` 을"
             " 확인하라.** 현재가를 못 받는 종목(WS 무송출 등)에서는 변환이"
             " 취소되고 **시장가가 그대로 나가 100% 거부되는데, 그때는 거부"
             " 관측(`[after_exit_rejected]`)·30초 TTL·그날 밤 포기 래치가 전부"
             " 작동하지 않는다** — 애프터마켓은 실시간 연속체결이라 브레이크 없는"
             " 반복 발사가 된다. `44` 에는 이 창이 아예 없다(`unpr=0` 이라 현재가가"
             " 불필요). `cur=0` 이면 44 로 두고 포기 래치가 다음 09:00 청산으로"
             " 착지시키게 두는 것이 옳다.\n"
             "⚠️ `41` 의 폴백도 `41` 이라 **호가유형이 다변화되지 않는다**(가격만"
             " 다시 계산한 재발사).\n"
             "⚠️ **문자열로 보낸다** — `44`(정수)는 선택지 밖으로 거부된다. 허용"
             " 집합 밖·부재·예외는 읽는 쪽이 `\"44\"` 로 폴백한다(클램프가 아니라"
             " 화이트리스트). IOC/FOK(42/43/45/46)는 잔량 자동취소로 손절 잔여를"
             " 잃고 47(최우선지정가)은 체결 보장이 없어 제외됐다.\n"
             "이 값은 **청산 판정을 바꾸지 않는다**(팔지 말지·언제 팔지는 그대로)"
             " — 이미 결정된 매도 주문의 호가 표현만 고른다. 정규장·프리장·"
             "15:30~16:00 은 무관하고, `order_exchange_clock_mode=\"off\"` 에서는"
             " 애프터 청산이 KRX 로 가지 않아 이 값이 읽히지 않는다. 이 변환은"
             " 실전(`is_production=True`) 계정에서만 발화한다(모의투자는 무접촉)."
             " AI 자동 튜닝 대상이 아니다.",
    ),

    # ── 관측·게이트 (6) ─────────────────────────────────────────────────────
    _s(
        key="open_entry_hold_secs", label_ko="개장 직후 진입 보류", group="observe_gate",
        type="int", min=0, max=600, step=10, unit="초",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_VBLTV, range_src="clamp",
        help="09:00 부터 이 초 동안 **신규 매수만** 보류한다(청산·손절·트레일링·"
             "익일청산·15:20 강제청산은 무접촉). **0 = 끄기.** 보류 중에도 돌파 기준선"
             " 갱신은 계속된다. 값 해석 실패는 0(끄기)으로 fail-open 한다.",
    ),
    _s(
        key="open_price_scope_mode", label_ko="시가 출처 강제", group="observe_gate",
        type="enum", min=None, max=None, step=None, unit="",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_VBLTV, range_src="enum",
        choices=(
            Choice("enforce", "강제 (KRX REST 시가만 신뢰)"),
            Choice("off", "끄기 (롤백 — WS 시가 허용)"),
        ),
        help="메인 보드 목표가의 기준 시가를 KRX REST 시가로 **단일화**한다."
             " `off` 만 롤백이고, 부재·오타·비움은 전부 `enforce` 로 해석된다"
             "(오염된 통합 채널 시가로 되돌아가지 않기 위해).",
    ),
    _s(
        key="llm_gate_mode", label_ko="LLM 매수 게이트 모드", group="observe_gate",
        type="enum", min=None, max=None, step=None, unit="",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_VBLTV, range_src="enum",
        choices=(
            Choice("shadow", "관측 전용 (매수를 막지 않음)"),
            Choice("off", "끄기 (호출 안 함)"),
        ),
        help="`shadow` 는 판단을 기록만 하고 매수를 막지 않는다. 알 수 없는 값은 `off`"
             " 로 해석한다 — **돈을 쓰는 기능은 설정이 불확실하면 하지 않는다**"
             "(`open_price_scope_mode` 와 정반대 규약).",
    ),
    _s(
        key="llm_gate_min_score", label_ko="LLM 게이트 통과 점수", group="observe_gate",
        type="int", min=1, max=100, step=1, unit="점",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_VBLTV, range_src="clamp",
        help="이 점수 이상이면 통과로 기록한다(shadow 모드에서는 기록만)."
             " 범위 밖이면 읽는 쪽이 기본값 70 으로 되돌린다.",
    ),
    _s(
        key="llm_gate_daily_call_cap", label_ko="LLM 일일 호출 상한", group="observe_gate",
        type="int", min=0, max=200, step=1, unit="회",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_VBLTV, range_src="clamp",
        help="하루 호출 횟수 상한. **0 = 호출 안 함**이고, 키가 없어도 0 이다"
             "(비용이 드는 기능의 기본은 '안 함').",
    ),
    _s(
        key="llm_gate_timeout_secs", label_ko="LLM 게이트 타임아웃", group="observe_gate",
        type="int", min=1, max=60, step=1, unit="초",
        editable=True, risk="identity", auto_tunable=False, deprecated=False,
        applies_to=_VBLTV, range_src="clamp",
        help="응답을 기다리는 최대 초. 초과하면 게이트를 건너뛴다(매수를 막지 않는다).",
    ),

    # ── 레거시 (8) — 전부 소비처 0건, 읽기 전용 ─────────────────────────────
    _s(
        key="max_units_per_stock", label_ko="종목당 최대 유닛 (미사용)", group="legacy",
        type="int", min=None, max=None, step=1, unit="유닛",
        editable=False, risk="normal", auto_tunable=False, deprecated=True,
        applies_to=("kojiro",), range_src="none",
        help="**행위 참조 0건.** 소스 주석도 '소비처 0건 = 미사용 상태이며 현재 어떤 것도"
             " 강제하지 않는다(안전장치 아님)'라고 못 박는다. 피라미딩(사다리 증량)"
             " 도입 시 배선 예정. **이 키를 리스크 한도로 오인하지 말 것.**",
    ),
    _s(
        key="max_units_total", label_ko="전체 최대 유닛 (미사용)", group="legacy",
        type="int", min=None, max=None, step=1, unit="유닛",
        editable=False, risk="normal", auto_tunable=False, deprecated=True,
        applies_to=("kojiro",), range_src="none",
        help="**행위 참조 0건.** `max_units_per_stock` 과 같은 사유. 실제로 총 리스크를"
             " 통제하는 것은 `max_open_risk_pct` 와 `max_positions` 다.",
    ),
    _s(
        key="quant_filter_enabled", label_ko="퀀트 필터 사용 (미사용)", group="legacy",
        type="bool", min=None, max=None, step=None, unit="",
        editable=False, risk="normal", auto_tunable=False, deprecated=True,
        applies_to=("volatility_breakout",), range_src="none",
        help="**배제 로직 미구현.** 이 값은 퍼널 화면의 조건 *문자열* 에만 등장하고"
             " 어떤 종목도 거르지 않는다. 켜도 매수 후보가 달라지지 않는다.",
    ),
    _s(
        key="quant_min_f_score", label_ko="F-Score 하한 (미사용)", group="legacy",
        type="int", min=None, max=None, step=1, unit="점",
        editable=False, risk="normal", auto_tunable=False, deprecated=True,
        applies_to=("volatility_breakout",), range_src="none",
        help="**참조 0건.** 정의만 있고 읽는 코드가 없다(Phase 2 인계).",
    ),
    _s(
        key="quant_max_mf_rank", label_ko="마법공식 순위 상한 (미사용)", group="legacy",
        type="int", min=None, max=None, step=1, unit="개",
        editable=False, risk="normal", auto_tunable=False, deprecated=True,
        applies_to=("volatility_breakout",), range_src="none",
        help="**참조 0건.** 정의만 있고 읽는 코드가 없다(Phase 2 인계).",
    ),
    _s(
        key="rs_filter_enabled", label_ko="상대강도 필터 사용 (미사용)", group="legacy",
        type="bool", min=None, max=None, step=None, unit="",
        editable=False, risk="normal", auto_tunable=False, deprecated=True,
        applies_to=("volatility_breakout",), range_src="none",
        help="**배제 로직 미구현.** 퍼널 표시 문자열에서만 읽힌다. 관찰 훅 검정 결과"
             " 상대강도는 역방향 신호였고 실배제는 무기한 보류됐다.",
    ),
    _s(
        key="rsi_filter_enabled", label_ko="RSI 필터 사용 (미사용)", group="legacy",
        type="bool", min=None, max=None, step=None, unit="",
        editable=False, risk="normal", auto_tunable=False, deprecated=True,
        applies_to=("volatility_breakout",), range_src="none",
        help="**배제 로직 미구현.** 퍼널 표시 문자열에서만 읽힌다.",
    ),
    _s(
        key="rsi_extreme_max", label_ko="RSI 과열 상한 (미사용)", group="legacy",
        type="int", min=None, max=None, step=1, unit="점",
        editable=False, risk="normal", auto_tunable=False, deprecated=True,
        applies_to=("volatility_breakout",), range_src="none",
        help="**배제 로직 미구현.** 값이 퍼널 조건 문자열에 찍히기만 하고 어떤 종목도"
             " 거르지 않는다.",
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# 조회 헬퍼 — 전부 순수 함수
# ═══════════════════════════════════════════════════════════════════════════
SPEC_BY_KEY: dict[str, ParamSpec] = {s.key: s for s in PARAM_SPECS}


def get_spec(key: str) -> ParamSpec | None:
    """키의 스펙. 카탈로그에 없으면 None."""
    return SPEC_BY_KEY.get(key)


def all_keys() -> tuple[str, ...]:
    """카탈로그의 전 키(정의 순서)."""
    return tuple(s.key for s in PARAM_SPECS)


def keys_for_strategy(strategy_id: str) -> tuple[str, ...]:
    """그 전략의 `DEFAULT_PARAMS` 에 존재하는 키(정의 순서)."""
    return tuple(s.key for s in PARAM_SPECS if strategy_id in s.applies_to)


def specs_for_strategy(strategy_id: str) -> tuple[ParamSpec, ...]:
    return tuple(s for s in PARAM_SPECS if strategy_id in s.applies_to)


def specs_in_group(group: str) -> tuple[ParamSpec, ...]:
    return tuple(s for s in PARAM_SPECS if s.group == group)


def identity_keys() -> tuple[str, ...]:
    return tuple(s.key for s in PARAM_SPECS if s.risk == "identity")


def deprecated_keys() -> tuple[str, ...]:
    return tuple(s.key for s in PARAM_SPECS if s.deprecated)


def auto_tunable_keys() -> tuple[str, ...]:
    return tuple(s.key for s in PARAM_SPECS if s.auto_tunable)


def editable_keys() -> tuple[str, ...]:
    return tuple(s.key for s in PARAM_SPECS if s.editable)


def forbidden_choices_for(key: str, strategy_id: str) -> tuple[ForbiddenChoice, ...]:
    """그 전략에서 이 키에 넣을 수 없는 선택지들(없으면 빈 튜플)."""
    spec = SPEC_BY_KEY.get(key)
    if spec is None:
        return ()
    return tuple(f for f in spec.forbidden_choices if f.strategy_id == strategy_id)
