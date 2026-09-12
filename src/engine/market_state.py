"""장운영상태(거래소 실제 장 상태) 표 — **순수 데이터·함수 leaf**.

사이클 282. 브리프 `cycle282_brief.md` §1 표 + Red 명세
`_workspace/red/cycle282_market_state_spec.md` §1 이 정본이다.

이 모듈은 `param_catalog.py` 와 같은 규약을 따른다.

* ``src.*`` import **0** · I/O **0** · 로깅 **0** · 모듈 로드 시 부작용 **0**.
* 어떤 전략도 아직 이 함수를 부르지 않는다. **읽기 전용 조회 기능**이고
  매매 행위는 어느 방향으로도 바뀌지 않는다(소비는 후속 주문 사이클이 한다).
* 휴장일 결합 같은 외부 조회는 **라우트**가 한다. leaf 는 시각과 표만 본다.

────────────────────────────────────────────────────────────────────────────
이 표가 드러낸 두 가지 (브리프 §1 말미 — 화면에도 ``FINDINGS`` 로 그대로 띄운다)
────────────────────────────────────────────────────────────────────────────
1. **NXT 에 시장가(``01``)가 없다.** 우리 주문의 1차 유형이 시장가다. 프리장에서
   지정가로 사전 변환해 온 것은 우회가 아니라 **구조적 필연**이었다. NXT 구간의
   대안은 ``13``(IOC시장가) / ``14``(FOK시장가)뿐이다.
2. **SOR 에 시간외 코드(``05``·``06``·``07``)가 없다.** cycle287 이전에는 전 주문이 SOR 이라
   시간외 구간에 주문 수단 자체가 **없었다**. cycle287(2026-09-12)부터는 시각이 거래소를
   정하므로(정규장·애프터 = KRX) 09:00 이후 주문이 SOR 로 나가지 않는다 — 이 사실 표의
   SOR 열은 KIS 지원 여부만 표시한다.

두 사실은 데이터(``ORDER_DIVISIONS``)에서 그대로 읽히고, A10·A11 가드가 봉인한다.

────────────────────────────────────────────────────────────────────────────
계약 요약
────────────────────────────────────────────────────────────────────────────
``[start, end)``
    모든 창은 **반개구간**이다. 09:00:00 은 K1(시가 단일가)이 아니라 K3(정규장)다.
    끝을 포함하면 두 행이 같은 순간에 살아 있어 커서가 모호해지고, 화면이
    "단일가인데 시장가 주문 가능" 이라는 모순을 띄운다.
``날짜 차원``
    ``effective_from`` / ``effective_to``(inclusive)가 행과 주문유형 **양쪽**에
    독립으로 걸린다. K6 은 2026-09-14 부터, K7 은 2026-09-12 까지다. 그래서
    ``get_market_table`` 은 날짜 인자를 받고, 날짜 없이 표를 내보내면 거짓이 된다.
    두 행이 공존하는 날은 **하루도 없다**(B3). 그 사이 09-13(일)의 16:00~20:00 은
    행이 0 인 공백으로 남는다 — **데이터를 넓혀 메우지 않는다**(정정-2).
``중첩과 커서``
    실제 동시 중첩은 K1 ⊃ K2 하나뿐이다. 커서는 ``(priority, start, row_id)`` 최소
    **한 행**이고, 나머지 동시 행은 ``concurrent_row_ids`` 로 남는다. 그 순간 쓸 수
    있는 주문유형은 **동시 행 전부의 합집합**이다(08:35 = ``00·01·05``).
``미확인은 숨기지 않는다``
    K1 시작(08:20) · N3 시작(09:00:30) · N5 주문유형 · SOR 의 27~29·41~47 지원 여부는
    정본이 없다. 추측으로 채우지 않고 ``confidence`` / ``exchanges_unknown`` /
    ``note`` 로 드러낸다. 화면이 그 배지를 그대로 띄운다.
``decided_by``
    지금은 항상 시각 판정이다. ``MARKET_CLS_CODE`` 실측 판정은 09-14 이후 데이터가
    쌓인 뒤의 별도 사이클이다(지금 만들면 검증할 수 없는 분기가 생긴다).

``src/engine/session.py`` 의 **보드**(PRE_NXT/MAIN/POST_NXT)와 혼동하지 말 것.
보드는 우리 매매 규약이고 이 표는 거래소 사실이다 — 경계가 다르다
(우리 MAIN 은 15:39:59 까지, KRX 정규장은 15:20 에 끝난다). ``BOARD_VS_MARKET_NOTE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum

# ---------------------------------------------------------------------------
# 닫힌 어휘 (프론트 가드가 이 목록을 읽는다 — 명세 §1.1)
# ---------------------------------------------------------------------------
#: 화면 렌더 순서. 프론트는 이 배열을 map 한다(시장명 리터럴 금지).
MARKET_ORDER: tuple[str, ...] = ("KRX", "NXT")

#: 주문유형 카탈로그의 거래소 열 순서.
EXCHANGE_ORDER: tuple[str, ...] = ("KRX", "NXT", "SOR")

#: 표가 바뀌면 올린다(골든 픽스처가 이 값을 핀한다).
TABLE_VERSION: str = "2026-09-11"

#: KST — 이 리포의 모든 시각 판정 기준(루트 CLAUDE.md KST 강제 규약).
_KST = timezone(timedelta(hours=9))


class MarketPhase(str, Enum):
    """거래소 장 상태의 **기계 분류**. 화면 문구는 행의 ``name_ko`` 다."""

    PRE_AUCTION = "PRE_AUCTION"              # 시가 단일가
    PRE_MARKET = "PRE_MARKET"                # 프리마켓(연속)
    REGULAR = "REGULAR"                      # 정규장(연속)
    CLOSE_AUCTION = "CLOSE_AUCTION"          # 종가 단일가
    PRE_CLOSE_FIXED = "PRE_CLOSE_FIXED"      # 장전 시간외 종가(전일 종가 고정)
    AFTER_CLOSE_FIXED = "AFTER_CLOSE_FIXED"  # 장후 시간외 종가(당일 종가 고정)
    AFTER_SINGLE = "AFTER_SINGLE"            # 시간외/애프터 단일가
    AFTER_MARKET = "AFTER_MARKET"            # 애프터마켓(연속)
    BREAK = "BREAK"                          # 장중 휴장
    CLOSED = "CLOSED"                        # 장 종료(행 없음)


MATCH_KINDS: tuple[str, ...] = (
    "continuous", "single_auction", "periodic_auction", "fixed_price", "none",
)
#: 화면 톤(표현 어휘 — 프론트가 스타일 키로 쓰는 것은 허용된다).
TONES: tuple[str, ...] = ("active", "auction", "fixed", "break", "closed", "unknown")
#: 표 행의 위치(서버가 판정한다 — 프론트가 시각 비교로 다시 계산하지 않는다).
RELS: tuple[str, ...] = ("past", "current", "concurrent", "upcoming", "unknown")
#: 카탈로그 셀 3상태 — ``yes`` ● / ``unknown`` ? / ``no`` 빈칸.
SUPPORT_LEVELS: tuple[str, ...] = ("yes", "unknown", "no")
#: 행의 확신도.
CONFIDENCE_LEVELS: tuple[str, ...] = ("confirmed", "unconfirmed", "ambiguous")
#: 주문유형 카탈로그의 확신도 — 행과 성질이 다르다(**존재는 확정, 이름만 모른다**).
DIVISION_CONFIDENCE: tuple[str, ...] = ("confirmed", "name_unconfirmed", "unconfirmed")
#: 필드 근거 수준. ``quote_channel`` 은 이 표에서 증거가 가장 약한 필드라 ``assumed`` 다.
EVIDENCE_LEVELS: tuple[str, ...] = ("confirmed", "assumed")

#: 판정 방식 — 이 사이클은 시각 단독이다(§1.8 · M12).
DECIDED_BY_TIME: str = "time"

_EVIDENCE_ASSUMED = "assumed"
_CONFIRMED = "confirmed"
_UNCONFIRMED = "unconfirmed"
_AMBIGUOUS = "ambiguous"

#: 커서 우선순위 — **행마다 리터럴로 적는다**(창 길이·목록 순서에서 파생 금지).
_PRIORITY_CHAIN = 10     # 그 시장·그 날짜의 시간축을 나누는 행
_PRIORITY_OVERLAY = 20   # 체인 행 안에 얹히는 행

#: 시장 라벨(화면 문구).
MARKET_LABELS_KO: dict[str, str] = {
    "KRX": "KRX(한국거래소)",
    "NXT": "NXT(넥스트레이드)",
}

#: 시세 채널 — 증거 ``assumed``(시장별 상수 가정). 실측 대조는 시세 전환 사이클의 몫이다.
_CH_KRX = "H0STCNT0"
_CH_NXT = "H0NXCNT0"

PHASE_LABELS_KO: dict[MarketPhase, str] = {
    MarketPhase.PRE_AUCTION: "시가 단일가",
    MarketPhase.PRE_MARKET: "프리마켓",
    MarketPhase.REGULAR: "정규장",
    MarketPhase.CLOSE_AUCTION: "종가 단일가",
    MarketPhase.PRE_CLOSE_FIXED: "장전 시간외 종가",
    MarketPhase.AFTER_CLOSE_FIXED: "장후 시간외 종가",
    MarketPhase.AFTER_SINGLE: "단일가(시간외·애프터)",
    MarketPhase.AFTER_MARKET: "애프터마켓",
    MarketPhase.BREAK: "휴장",
    MarketPhase.CLOSED: "장 종료",
}

PHASE_TONES: dict[MarketPhase, str] = {
    MarketPhase.PRE_AUCTION: "auction",
    MarketPhase.PRE_MARKET: "active",
    MarketPhase.REGULAR: "active",
    MarketPhase.CLOSE_AUCTION: "auction",
    MarketPhase.PRE_CLOSE_FIXED: "fixed",
    MarketPhase.AFTER_CLOSE_FIXED: "fixed",
    MarketPhase.AFTER_SINGLE: "auction",
    MarketPhase.AFTER_MARKET: "active",
    MarketPhase.BREAK: "break",
    MarketPhase.CLOSED: "closed",
}

#: 행이 없을 때의 체결 설명(휴장 행과 같은 문자열).
_MATCH_NONE_KO = "—"


# ---------------------------------------------------------------------------
# 자료구조 (명세 §1.2)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class MarketRow:
    """표의 한 행 — **선언값**이다(날짜 해석 전)."""

    row_id: str
    market: str
    start: time                       # 반개구간 [start, end) — 끝은 포함하지 않는다
    end: time
    phase: MarketPhase
    name_ko: str
    match_kind: str
    match_ko: str
    order_divisions: tuple[str, ...]  # 날짜 해석 전 상위집합, 오름차순
    quote_channel: str | None
    quote_channel_evidence: str
    priority: int
    overlap_ok: bool
    effective_from: date | None       # None = 상시
    effective_to: date | None         # None = 상시, 그 날짜까지 **포함**
    confidence: str
    note: str


@dataclass(frozen=True, slots=True)
class OrderDivisionSpec:
    """주문유형 1건. ``exchanges``=확정 가용 / ``exchanges_unknown``=**미확인**.

    둘을 한 집합으로 합치면 "미지원" 과 "미확인" 이 같은 칸이 되어, 브리프가 못박은
    "숨기지 않는다" 가 그 자리에서 깨진다(SOR 의 27~29·41~47 이 조용히 사라진다).
    """

    code: str
    name_ko: str
    group_ko: str | None
    exchanges: frozenset[str]
    exchanges_unknown: frozenset[str]
    effective_from: date | None
    effective_to: date | None
    confidence: str
    note: str


@dataclass(frozen=True, slots=True)
class ResolvedRow:
    """``on_date`` 로 해석을 마친 행. 빠진 코드는 삭제가 아니라 **보인다**."""

    row_id: str
    market: str
    start: time
    end: time
    phase: MarketPhase
    name_ko: str
    tone: str
    match_kind: str
    match_ko: str
    order_divisions: tuple[str, ...]          # 그 날짜에 유효한 코드만
    order_divisions_pending: tuple[str, ...]  # 아직 유효하지 않은 코드
    order_divisions_expired: tuple[str, ...]  # 이미 만료된 코드
    can_order: bool
    market_order_ok: bool
    quote_channel: str | None
    quote_channel_evidence: str
    overlap_ok: bool
    priority: int
    effective_from: date | None
    effective_to: date | None
    confidence: str
    note: str
    rel: str                                   # 커서 결합 전에는 "unknown"


@dataclass(frozen=True, slots=True)
class MarketState:
    """한 시장의 **지금** — 커서 1개 + 동시에 열린 창."""

    market: str
    market_label_ko: str
    as_of: datetime                            # 판정에 쓴 그 순간(KST aware)
    on_date: date                              # as_of 의 KST 날짜 = 표 유효일
    row_id: str | None                         # 커서. 행이 없으면 None
    phase: MarketPhase
    name_ko: str
    tone: str
    window: tuple[time, time] | None
    match_kind: str
    match_ko: str
    is_open: bool                              # phase 기반
    can_order: bool                            # divisions 기반 — 둘은 다를 수 있다(N5)
    market_order_ok: bool
    order_divisions: tuple[str, ...]           # 동시 유효 행 **합집합**
    order_divisions_by_row: tuple[tuple[str, tuple[str, ...]], ...]
    concurrent_row_ids: tuple[str, ...]
    quote_channel: str | None
    quote_channel_evidence: str
    decided_by: str
    code_seen: str | None
    confidence: str
    confidence_notes: tuple[str, ...]
    seconds_to_next: int | None                # 다음 경계까지 **올림** 초
    next_boundary: time | None
    next_row_id: str | None
    next_phase: MarketPhase | None


# ---------------------------------------------------------------------------
# 전환 날짜 (2026-09-14 KRX·NXT 개편 · 2026-09-12 시간외 단일가 폐지)
# ---------------------------------------------------------------------------
_REFORM_DAY = date(2026, 9, 14)
_AFTER_SINGLE_LAST_DAY = date(2026, 9, 12)

_KRX_REGULAR_DIVISIONS: tuple[str, ...] = (
    "00", "01", "02", "03", "04",
    "11", "12", "13", "14", "15", "16",
    "21", "22", "23", "24",
)
_NXT_CONTINUOUS_DIVISIONS: tuple[str, ...] = (
    "00", "03", "04",
    "11", "12", "13", "14", "15", "16",
    "21", "22", "23", "24",
)
_NXT_PRE_DIVISIONS: tuple[str, ...] = _NXT_CONTINUOUS_DIVISIONS + ("27", "28", "29")
_KRX_AFTER_DIVISIONS: tuple[str, ...] = ("41", "42", "43", "44", "45", "46", "47")


# ---------------------------------------------------------------------------
# MARKET_TABLE — 13행 (브리프 §1 그대로)
# ---------------------------------------------------------------------------
MARKET_TABLE: tuple[MarketRow, ...] = (
    MarketRow(
        row_id="K1", market="KRX",
        start=time(8, 20), end=time(9, 0),
        phase=MarketPhase.PRE_AUCTION, name_ko="시가 단일가",
        match_kind="single_auction", match_ko="단일가(09:00 일괄)",
        order_divisions=("00", "01"),
        quote_channel=_CH_KRX, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_UNCONFIRMED,
        note=(
            "시작 08:20 이 2026-09-14 개편분인지 미확인(종전 08:30). "
            "09-14 이전 날짜에서는 08:20~08:30 을 과다 표시할 수 있다."
        ),
    ),
    MarketRow(
        row_id="K2", market="KRX",
        start=time(8, 30), end=time(8, 40),
        phase=MarketPhase.PRE_CLOSE_FIXED, name_ko="장전 시간외 종가",
        match_kind="fixed_price", match_ko="전일 종가 고정",
        order_divisions=("05",),
        quote_channel=_CH_KRX, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_OVERLAY, overlap_ok=True,
        effective_from=None, effective_to=None,
        confidence=_CONFIRMED,
        note=(
            "K1(시가 단일가) 안에 들어 있는 의도된 중첩. "
            "08:30~08:40 에는 00·01·05 가 동시에 쓸 수 있다."
        ),
    ),
    MarketRow(
        row_id="K3", market="KRX",
        start=time(9, 0), end=time(15, 20),
        phase=MarketPhase.REGULAR, name_ko="정규장",
        match_kind="continuous", match_ko="실시간 접속매매",
        order_divisions=_KRX_REGULAR_DIVISIONS,
        quote_channel=_CH_KRX, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_CONFIRMED, note="",
    ),
    MarketRow(
        row_id="K4", market="KRX",
        start=time(15, 20), end=time(15, 30),
        phase=MarketPhase.CLOSE_AUCTION, name_ko="종가 단일가",
        match_kind="single_auction", match_ko="단일가(15:30 일괄)",
        order_divisions=("00", "01"),
        quote_channel=_CH_KRX, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_CONFIRMED, note="",
    ),
    MarketRow(
        row_id="K5", market="KRX",
        start=time(15, 30), end=time(16, 0),
        phase=MarketPhase.AFTER_CLOSE_FIXED, name_ko="장후 시간외 종가",
        match_kind="fixed_price", match_ko="당일 종가 고정",
        order_divisions=("06",),
        quote_channel=_CH_KRX, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_CONFIRMED, note="",
    ),
    MarketRow(
        row_id="K6", market="KRX",
        start=time(16, 0), end=time(20, 0),
        phase=MarketPhase.AFTER_MARKET, name_ko="애프터마켓",
        match_kind="continuous", match_ko="실시간",
        order_divisions=_KRX_AFTER_DIVISIONS,
        quote_channel=_CH_KRX, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=_REFORM_DAY, effective_to=None,
        confidence=_CONFIRMED,
        note="2026-09-14 신설(공지). 시장가 없음 — 41~47 만.",
    ),
    MarketRow(
        row_id="K7", market="KRX",
        start=time(16, 0), end=time(18, 0),
        phase=MarketPhase.AFTER_SINGLE, name_ko="시간외 단일가",
        match_kind="periodic_auction", match_ko="10분 주기",
        order_divisions=("07",),
        quote_channel=_CH_KRX, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=True,
        effective_from=None, effective_to=_AFTER_SINGLE_LAST_DAY,
        confidence=_CONFIRMED,
        note=(
            "2026-09-12 폐지. K6 과는 유효기간이 갈려 어떤 날짜에도 공존하지 않는다(B3)."
        ),
    ),
    MarketRow(
        row_id="N1", market="NXT",
        start=time(8, 0), end=time(8, 50),
        phase=MarketPhase.PRE_MARKET, name_ko="프리마켓",
        match_kind="continuous", match_ko="실시간",
        order_divisions=_NXT_PRE_DIVISIONS,
        quote_channel=_CH_NXT, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_CONFIRMED,
        note=(
            "27~29(GTP)는 2026-09-14 부터 유효 — 그 이전 날짜에는 "
            "order_divisions_pending 으로 빠진다."
        ),
    ),
    MarketRow(
        row_id="N2", market="NXT",
        start=time(8, 50), end=time(9, 0),
        phase=MarketPhase.BREAK, name_ko="휴장",
        match_kind="none", match_ko=_MATCH_NONE_KO,
        order_divisions=(),
        quote_channel=_CH_NXT, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_CONFIRMED,
        note="휴장 — 주문 접수 불가.",
    ),
    MarketRow(
        row_id="N3", market="NXT",
        start=time(9, 0, 30), end=time(15, 20),
        phase=MarketPhase.REGULAR, name_ko="정규장",
        match_kind="continuous", match_ko="실시간",
        order_divisions=_NXT_CONTINUOUS_DIVISIONS,
        quote_channel=_CH_NXT, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_UNCONFIRMED,
        note=(
            "시작 09:00:30 미확인. 09:00:00~09:00:29 은 N2(휴장)로 남는다 — "
            "표대로 옮겼을 뿐 실측 근거는 없다."
        ),
    ),
    MarketRow(
        row_id="N4", market="NXT",
        start=time(15, 20), end=time(15, 30),
        phase=MarketPhase.BREAK, name_ko="휴장",
        match_kind="none", match_ko=_MATCH_NONE_KO,
        order_divisions=(),
        quote_channel=_CH_NXT, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_CONFIRMED,
        note="휴장 — 주문 접수 불가.",
    ),
    MarketRow(
        row_id="N5", market="NXT",
        start=time(15, 30), end=time(15, 40),
        phase=MarketPhase.AFTER_SINGLE, name_ko="애프터 단일가",
        match_kind="single_auction", match_ko="단일가",
        order_divisions=(),
        quote_channel=_CH_NXT, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_UNCONFIRMED,
        note=(
            "단일가 구간인 것은 확정이나 쓸 수 있는 주문유형이 미확인이다. "
            "NXT 코드 목록에 단일가 전용 코드가 없다. is_open=True 이지만 "
            "can_order=False 다 — 이 구간의 주문 가능 여부를 이 표로 판단하지 말 것."
        ),
    ),
    MarketRow(
        row_id="N6", market="NXT",
        start=time(15, 40), end=time(20, 0),
        phase=MarketPhase.AFTER_MARKET, name_ko="애프터마켓",
        match_kind="continuous", match_ko="실시간",
        order_divisions=_NXT_CONTINUOUS_DIVISIONS,
        quote_channel=_CH_NXT, quote_channel_evidence=_EVIDENCE_ASSUMED,
        priority=_PRIORITY_CHAIN, overlap_ok=False,
        effective_from=None, effective_to=None,
        confidence=_CONFIRMED, note="",
    ),
)


# ---------------------------------------------------------------------------
# ORDER_DIVISIONS — 28 코드 (브리프 §1 카탈로그)
# ---------------------------------------------------------------------------
_ALL_THREE = frozenset(EXCHANGE_ORDER)
_KRX_NXT = frozenset(("KRX", "NXT"))
_KRX_SOR = frozenset(("KRX", "SOR"))
_ONLY_KRX = frozenset(("KRX",))
_ONLY_NXT = frozenset(("NXT",))
_UNKNOWN_SOR = frozenset(("SOR",))
_NONE_UNKNOWN: frozenset[str] = frozenset()

_GROUP_IOC_FOK = "IOC/FOK"
_GROUP_MID_STOP = "중간가/스톱"
_GROUP_NXT_GTP = "NXT GTP(27~29)"
_GROUP_KRX_AFTER = "KRX 애프터마켓(41~47)"

_NAME_UNCONFIRMED = "name_unconfirmed"
_NOTE_NO_SOR = "SOR 에 없다(발견 2)."

#: cycle289 (2026-09-13) — 27~29·41~47 의 개별 명칭이 **확정**됐다.
#: 출처 = KIS Open API 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에
#: 따른 안내」(시행 2026-09-14). 공지 원문의 표기를 그대로 옮긴다 — 지어내거나 다듬지
#: 않는다(`docs/kis/domestic-stock-order.md` 의 `ORD_DVSN` 필드 칸과 같은 값이어야 한다).
#: 종전에는 명칭이 정본에 없어 그룹명만 표시하고 `confidence=_NAME_UNCONFIRMED` 였다 —
#: 화면에 10개 코드가 전부 "확인필요" 로 떴다(사용자 지적 2026-09-12).
_NOTE_NAME_CONFIRMED = "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문."


def _gtp(value: str, name_ko: str) -> OrderDivisionSpec:
    """27~29 — NXT 프리마켓 전용호가 GTP(Good Till Pre-Market).

    미체결잔량은 프리마켓 종료(08:50)에 일괄 취소된다 — 그 취소 규약이 GTP 의
    정체성이라 `note` 에 남긴다(코드값만 보고는 알 수 없다).
    """
    return OrderDivisionSpec(
        code=value, name_ko=name_ko, group_ko=_GROUP_NXT_GTP,
        exchanges=_ONLY_NXT, exchanges_unknown=_UNKNOWN_SOR,
        effective_from=_REFORM_DAY, effective_to=None,
        confidence=_CONFIRMED,
        note=_NOTE_NAME_CONFIRMED + " 미체결잔량은 프리마켓 종료(08:50) 일괄 취소.",
    )


def _krx_after(value: str, name_ko: str) -> OrderDivisionSpec:
    """41~47 — KRX 애프터마켓(16:00~20:00) 전용 호가유형.

    정규장과 **분리된 시장**이라 호가유형 선택이 필수이고, **시장가(01)가 없다**.
    ETP(ETF/ETN) 거래 불가. 가격제한은 전일 KRX 정규장 종가 ±30%.
    우리가 청산에 쓰는 것은 44(1차)·41(폴백) 둘뿐이다(cycle287) — IOC/FOK(42·43·45·46)는
    잔량을 자동취소해 손절 잔여를 잃고, 47(최우선지정가)은 자기 방향 최우선호가라
    크로스하지 않아 체결 보장이 없다.
    """
    return OrderDivisionSpec(
        code=value, name_ko=name_ko, group_ko=_GROUP_KRX_AFTER,
        exchanges=_ONLY_KRX, exchanges_unknown=_UNKNOWN_SOR,
        effective_from=_REFORM_DAY, effective_to=None,
        confidence=_CONFIRMED,
        note=_NOTE_NAME_CONFIRMED + " 애프터마켓은 시장가 불가·ETP 불가.",
    )


ORDER_DIVISIONS: tuple[OrderDivisionSpec, ...] = (
    OrderDivisionSpec("00", "지정가", None, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    # 발견 1 — NXT 에는 시장가가 **없다**(미확인이 아니라 미지원이다).
    OrderDivisionSpec("01", "시장가", None, _KRX_SOR, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, "NXT 에는 시장가가 없다(발견 1)."),
    OrderDivisionSpec("02", "조건부지정가", None, _ONLY_KRX, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("03", "최유리지정가", None, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("04", "최우선지정가", None, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    # 발견 2 — SOR 에 시간외 코드가 없다. 전 주문이 SOR 이면 시간외 주문 수단이 없다.
    OrderDivisionSpec("05", "장전시간외", None, _ONLY_KRX, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, _NOTE_NO_SOR),
    OrderDivisionSpec("06", "장후시간외", None, _ONLY_KRX, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, _NOTE_NO_SOR),
    OrderDivisionSpec("07", "시간외단일가", None, _ONLY_KRX, _NONE_UNKNOWN,
                      None, _AFTER_SINGLE_LAST_DAY, _CONFIRMED,
                      "2026-09-12 폐지. " + _NOTE_NO_SOR),
    OrderDivisionSpec("11", "IOC지정가", _GROUP_IOC_FOK, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("12", "FOK지정가", _GROUP_IOC_FOK, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("13", "IOC시장가", _GROUP_IOC_FOK, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("14", "FOK시장가", _GROUP_IOC_FOK, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("15", "IOC최유리", _GROUP_IOC_FOK, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("16", "FOK최유리", _GROUP_IOC_FOK, _ALL_THREE, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("21", "중간가", _GROUP_MID_STOP, _KRX_NXT, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("22", "스톱지정가", _GROUP_MID_STOP, _KRX_NXT, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("23", "중간가IOC", _GROUP_MID_STOP, _KRX_NXT, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    OrderDivisionSpec("24", "중간가FOK", _GROUP_MID_STOP, _KRX_NXT, _NONE_UNKNOWN,
                      None, None, _CONFIRMED, ""),
    # 공지 원문 표기 그대로 (2026-09-09 · 시행 09-14)
    _gtp("27", "NXT GTP지정가"),
    _gtp("28", "NXT GTP최유리"),
    _gtp("29", "NXT GTP최우선"),
    _krx_after("41", "KRX애프터마켓지정가"),
    _krx_after("42", "KRX애프터마켓지정가IOC"),
    _krx_after("43", "KRX애프터마켓지정가FOK"),
    _krx_after("44", "KRX애프터마켓최유리지정가"),
    _krx_after("45", "KRX애프터마켓최유리지정가IOC"),
    _krx_after("46", "KRX애프터마켓최유리지정가FOK"),
    _krx_after("47", "KRX애프터마켓최우선지정가"),
)


# ---------------------------------------------------------------------------
# 표가 드러낸 것 — 응답 `findings` 로 화면에 그대로 띄운다
# ---------------------------------------------------------------------------
FINDINGS: tuple[str, ...] = (
    "NXT 에 시장가(01)가 없다. 우리 주문의 1차 유형이 시장가다. 프리장 지정가 사전 변환은 "
    "우회가 아니라 구조적 필연이었다. 대안은 13 IOC시장가 / 14 FOK시장가다.",
    # cycle287b (2026-09-13) — 이 문장은 cycle287 배포로 **거짓이 됐다.** 종전 문구는
    # "현재 전 주문이 SOR 이므로 시간외 구간에는 주문 수단이 없다" 였는데, 09:00 이후
    # 주문은 더 이상 SOR 로 나가지 않는다. 관측 사실(SOR 에 시간외 코드가 없다)은 남기고
    # 우리 경로에 대한 서술만 현재로 고친다 — 화면이 옛 세계를 말하게 두지 않는다.
    "SOR 에 시간외 코드(05·06·07)가 없다. 다만 cycle287(2026-09-12)부터 "
    "**시각이 거래소를 정하므로**(정규장·애프터 = KRX, 프리장만 전략 설정값) 우리 주문은 "
    "09:00 이후 SOR 로 나가지 않는다. 이 열은 KIS 지원 사실만 표시한다.",
    # 아래 각주가 cycle287 의 인계 사항이다(test_n4 — "우리가 안 쓰기로 한 사실은 열 삭제가
    # 아니라 각주로 적는다"). SOR 열을 지우면 41~47 의 SOR 지원이 미확인이라는 사실까지
    # 화면에서 사라져 "미확인을 미지원으로 접지 않는다"(cycle282)를 정면으로 깬다.
    "SOR 은 주문 경로에서 **폐기**됐다(사용자 결정 2026-09-12). 전략 설정의 SOR 선택지는 "
    "폐기 표시로 남아 있고 프리장 밖에서는 값이 무엇이든 KRX 로 나간다. "
    "이 표의 SOR 열은 삭제하지 않는다 — 41~47 의 SOR 지원 여부가 아직 **확인 필요**이고, "
    "그 미확인을 화면에서 지우면 44 의 단가 규약이 미검증이라는 사실도 함께 사라진다.",
)

BOARD_VS_MARKET_NOTE: str = (
    "이 화면은 거래소의 실제 장 운영 상태다. 우리 시스템의 매매 보드(PRE_NXT/MAIN/POST_NXT)와는 "
    "경계가 다르다 — 우리 MAIN 보드는 15:39:59 까지지만 KRX 정규장은 15:20 에 끝난다. "
    "보드는 우리 매매 규약이고 이 표는 거래소 사실이다. 둘을 같은 것으로 읽지 말 것."
)

UNCONFIRMED_NOTE: str = (
    "⚠️ 표시 항목은 아직 KIS 정본으로 확인하지 못했다. 이 사이클은 추측으로 채우지 않고 "
    "그대로 드러낸다. 확인 경로 = KIS MCP 스펙 조회 + 2026-09-14 이후 실측."
)

_AMBIGUOUS_NOTE: str = (
    "같은 우선순위의 행이 둘 이상 동시에 살아 있다 — 표 데이터 결함이다. "
    "커서는 결정론적으로 골랐지만 이 순간의 장 상태는 신뢰할 수 없다."
)


# ---------------------------------------------------------------------------
# 시각·날짜 판정
# ---------------------------------------------------------------------------
def _coerce_kst(now: datetime | None) -> datetime:
    """KST 강제 — ``None``=지금, naive=KST 간주, 다른 tz=변환.

    ``datetime.now()``(naive 로컬)를 쓰면 컨테이너 TZ 가 바뀌는 날 표 판정이
    통째로 조용히 틀린다. 그래서 tz 를 항상 명시한다.
    """
    if now is None:
        return datetime.now(_KST)
    if now.tzinfo is None:
        return now.replace(tzinfo=_KST)
    return now.astimezone(_KST)


def _normalize_market(market: str) -> str:
    """미지 시장은 조용히 빈 표를 주지 않고 ``ValueError`` 다."""
    key = str(market or "").upper()
    if key not in MARKET_ORDER:
        raise ValueError(
            f"미지 시장 {market!r} — 이 표가 아는 시장은 {list(MARKET_ORDER)} 뿐이다"
        )
    return key


def _is_effective(row_or_spec, on_date: date) -> bool:
    """``effective_to`` 는 **그 날짜까지 포함**(inclusive)이다."""
    start = row_or_spec.effective_from
    if start is not None and on_date < start:
        return False
    stop = row_or_spec.effective_to
    if stop is not None and on_date > stop:
        return False
    return True


def _division_index() -> dict[str, OrderDivisionSpec]:
    """호출 시점의 ``ORDER_DIVISIONS`` 로 색인을 만든다(굳은 파생 금지)."""
    return {spec.code: spec for spec in ORDER_DIVISIONS}


def _resolve_divisions(
    row: MarketRow, on_date: date, index: dict[str, OrderDivisionSpec]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """(유효, pending, expired) — 셋의 합집합은 언제나 ``row.order_divisions`` 다.

    행의 유효기간과 주문유형의 유효기간은 **별개의 두 필터이고 둘 다 적용된다.**
    빠진 코드를 지우지 않고 pending/expired 로 남기는 이유는 화면이 "곧 생긴다"
    와 "이미 없어졌다" 를 말할 수 있어야 하기 때문이다.
    """
    live: list[str] = []
    pending: list[str] = []
    expired: list[str] = []
    for value in row.order_divisions:
        spec = index.get(value)
        if spec is None:
            live.append(value)
            continue
        if spec.effective_from is not None and on_date < spec.effective_from:
            pending.append(value)
        elif spec.effective_to is not None and on_date > spec.effective_to:
            expired.append(value)
        else:
            live.append(value)
    return tuple(live), tuple(pending), tuple(expired)


def support_level(spec: OrderDivisionSpec, exchange: str) -> str:
    """카탈로그 셀 3상태 — ``yes`` / ``unknown``(확인 필요) / ``no``.

    미확인을 미지원과 같은 칸에 그리면 "숨기지 않는다" 가 깨진다.
    """
    if exchange in spec.exchanges:
        return "yes"
    if exchange in spec.exchanges_unknown:
        return "unknown"
    return "no"


def _rows_for(market: str, on_date: date) -> list[MarketRow]:
    """그 시장·그 날짜에 유효한 행. ``MARKET_TABLE`` 을 **호출 시점**에 읽는다."""
    return [r for r in MARKET_TABLE if r.market == market and _is_effective(r, on_date)]


def _sort_key(row: MarketRow) -> tuple[int, time, str]:
    """커서 정렬 키 — ``priority`` 가 먼저다(시작 시각 순서가 아니다)."""
    return (row.priority, row.start, row.row_id)


def _live_rows(rows: list[MarketRow], moment: time) -> list[MarketRow]:
    """``[start, end)`` — 끝은 포함하지 않는다."""
    return sorted(
        (r for r in rows if r.start <= moment < r.end), key=_sort_key
    )


def _resolve_at(rows: list[MarketRow], moment: time) -> MarketRow | None:
    """그 시각의 커서 행 1개(없으면 None). ``get_market_state`` 재귀를 대신한다."""
    live = _live_rows(rows, moment)
    return live[0] if live else None


def _boundaries(rows: list[MarketRow]) -> list[time]:
    return sorted({r.start for r in rows} | {r.end for r in rows})


def _ceil_seconds(target: datetime, origin: datetime) -> int:
    """남은 시간은 **올림**이다. 19:59:59.5 는 1 이지 0 이 아니다."""
    total = (target - origin).total_seconds()
    whole = int(total)
    if total > whole:
        whole += 1
    return max(0, whole)


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------
def get_market_table(on_date: date | None = None) -> tuple[ResolvedRow, ...]:
    """그 날짜에 **유효한 행만** 날짜 해석을 마쳐 돌려준다(두 시장 전부).

    ``on_date=None`` 이면 KST 오늘이다. 날짜 없이 표를 내보내면 09-12 화면에
    27~29 가 떠서 거짓이 된다 — **날짜는 이 표의 계약이다.**

    ``rel`` 은 여기서 항상 ``"unknown"`` 이다. 커서와의 결합은 라우트의 일이다
    (표와 커서가 **하나의 as_of** 에서 나와야 갈라지지 않는다).
    """
    target = on_date if on_date is not None else _coerce_kst(None).date()
    index = _division_index()
    resolved: list[ResolvedRow] = []
    for row in MARKET_TABLE:
        if not _is_effective(row, target):
            continue
        live, pending, expired = _resolve_divisions(row, target, index)
        resolved.append(
            ResolvedRow(
                row_id=row.row_id,
                market=row.market,
                start=row.start,
                end=row.end,
                phase=row.phase,
                name_ko=row.name_ko,
                tone=PHASE_TONES.get(row.phase, "unknown"),
                match_kind=row.match_kind,
                match_ko=row.match_ko,
                order_divisions=live,
                order_divisions_pending=pending,
                order_divisions_expired=expired,
                can_order=bool(live),
                market_order_ok="01" in live,
                quote_channel=row.quote_channel,
                quote_channel_evidence=row.quote_channel_evidence,
                overlap_ok=row.overlap_ok,
                priority=row.priority,
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                confidence=row.confidence,
                note=row.note,
                rel="unknown",
            )
        )
    resolved.sort(
        key=lambda r: (MARKET_ORDER.index(r.market), r.start, r.priority, r.row_id)
    )
    return tuple(resolved)


def get_market_state(now: datetime | None = None, *, market: str = "KRX") -> MarketState:
    """한 시장의 **지금** 을 판정한다 — 커서 1개 + 동시에 열린 창.

    답은 커서 행 단독이 아니다. 08:35 의 "지금 무엇을 쓸 수 있나" 는 K1(00·01)과
    K2(05)의 **합집합**이다. 행별 내역은 ``order_divisions_by_row`` 에 남는다.

    20:00 이후에는 ``seconds_to_next=None`` 이다 — 내일이 거래일인지 모르는 순수
    함수가 "10시간 뒤 프리마켓" 이라고 말하면 금요일 밤에 거짓이 된다.
    """
    as_of = _coerce_kst(now)
    key = _normalize_market(market)
    on_date = as_of.date()
    moment = as_of.time()

    index = _division_index()
    rows = _rows_for(key, on_date)
    live = _live_rows(rows, moment)
    cursor = live[0] if live else None

    by_row: list[tuple[str, tuple[str, ...]]] = []
    union: set[str] = set()
    for row in live:
        codes, _pending, _expired = _resolve_divisions(row, on_date, index)
        by_row.append((row.row_id, codes))
        union |= set(codes)
    divisions = tuple(sorted(union))

    notes: list[str] = [r.note for r in live if r.confidence != _CONFIRMED and r.note]
    if len(live) >= 2 and live[0].priority == live[1].priority:
        confidence = _AMBIGUOUS
        notes = [_AMBIGUOUS_NOTE] + notes
    elif any(r.confidence != _CONFIRMED for r in live):
        confidence = _UNCONFIRMED
    else:
        confidence = _CONFIRMED

    phase = cursor.phase if cursor is not None else MarketPhase.CLOSED

    next_boundary: time | None = None
    for bound in _boundaries(rows):
        if bound > moment:
            next_boundary = bound
            break

    seconds_to_next: int | None = None
    next_row_id: str | None = None
    next_phase: MarketPhase | None = None
    if next_boundary is not None:
        seconds_to_next = _ceil_seconds(
            datetime.combine(on_date, next_boundary, tzinfo=_KST), as_of
        )
        upcoming = _resolve_at(rows, next_boundary)
        next_row_id = upcoming.row_id if upcoming is not None else None
        next_phase = upcoming.phase if upcoming is not None else MarketPhase.CLOSED

    return MarketState(
        market=key,
        market_label_ko=MARKET_LABELS_KO.get(key, key),
        as_of=as_of,
        on_date=on_date,
        row_id=cursor.row_id if cursor is not None else None,
        phase=phase,
        name_ko=cursor.name_ko if cursor is not None else PHASE_LABELS_KO[MarketPhase.CLOSED],
        tone=PHASE_TONES.get(phase, "unknown"),
        window=(cursor.start, cursor.end) if cursor is not None else None,
        match_kind=cursor.match_kind if cursor is not None else "none",
        match_ko=cursor.match_ko if cursor is not None else _MATCH_NONE_KO,
        is_open=phase not in (MarketPhase.BREAK, MarketPhase.CLOSED),
        can_order=bool(divisions),
        market_order_ok="01" in divisions,
        order_divisions=divisions,
        order_divisions_by_row=tuple(by_row),
        concurrent_row_ids=tuple(r.row_id for r in live[1:]),
        quote_channel=cursor.quote_channel if cursor is not None else None,
        quote_channel_evidence=(
            cursor.quote_channel_evidence if cursor is not None else _EVIDENCE_ASSUMED
        ),
        decided_by=DECIDED_BY_TIME,
        code_seen=None,
        confidence=confidence,
        confidence_notes=tuple(notes),
        seconds_to_next=seconds_to_next,
        next_boundary=next_boundary,
        next_row_id=next_row_id,
        next_phase=next_phase,
    )
