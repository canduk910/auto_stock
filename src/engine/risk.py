"""리스크 관리 모듈.

- 실시간 시세에 따른 손절/익일청산 신호 감시
- 전략별 포지션 비중 제한
- 전략 간 중복 매수 방지
- 전략별 매매 가능 보드(KRX 메인 / NXT 프리 / NXT 애프터) 가드 — Phase 8
- **사이클 2 (2026-05-17)**: 시장 레짐 매수 가드 (defensive/VIX>25/F&G 극단 시 매수 차단).
  매도/손절 분기는 무관 — 보유 종목 청산 정상.
- **사이클 62 → 사이클 64 (2026-06-06)**: 가격 필터 risk.on_tick 영역 전면 이전.
  scanner.subscribe_filtered_stocks 진입 직전 단일 hook (Q4 옵션 A) 으로 재배치.
  risk.py 내 가격 필터 코드 완전 제거 (G-1 AST 가드 영속).
"""

from __future__ import annotations

import logging
import time
from datetime import date as _date, datetime as _datetime, timedelta, timezone
from typing import Optional

from src.engine.daily_emit_cap import DailyEmitCap
from src.engine.order_engine import OrderEngine
from src.engine.session import MarketBoard, boards_at, session_tracker
from src.engine.strategy_base import Signal
from src.engine.strategy_registry import StrategyRegistry

logger = logging.getLogger(__name__)

# cycle238 (2026-09-02) — 프리장 청산 보류 게이트 시각 폴백 seam.
#
# `_KST`/`_now_kst()` = `session.py:25` 관례 답습(naive `datetime.now()` 금지,
# P2-6 부류). `_now_kst` 는 **모듈 함수**로 두어 테스트 주입 seam 으로 쓴다 —
# `tests/conftest.py` 의 autouse `_pin_pre_market_clock` 이 이 심볼을 MAIN
# 구간으로 핀하고, 게이트를 직접 검증하는 테스트는 뒤에 도는 monkeypatch 로
# 시각을 명시한다(픽스처보다 뒤에 적용되므로 이긴다).
_KST = timezone(timedelta(hours=9))


def _now_kst() -> _datetime:
    """KST(+09:00) 현재 시각. naive `datetime.now()` 금지(P2-6 부류)."""
    return _datetime.now(_KST)


def _pre_market_only_by_clock() -> bool | None:
    """`session.boards_at`(fresh)로 PRE_NXT 단독 구간인지 판정 (cycle238).

    `session_tracker.active` 는 `SessionTracker.tick()`(30초 주기)가 기록하는
    **stale 캐시** — 08:00:00~08:00:29 는 07:59 스냅샷(∅)이 그대로 살아남아
    프리장 청산 보류 게이트를 fail-open 으로 연다(실측: 08:00:00 청산 발화 →
    08:00:29 deferred). 이 함수는 tracker 가 쓰는 **바로 그** `_BOARD_SCHEDULE`
    표(`session.boards_at`)를 매 호출 fresh 로 읽어 그 구멍을 닫는다 — 시각
    리터럴을 새로 두지 않는다(스케줄 표 단일 소스).

    판정 불가(예외) 시 None — `_defers_pre_market_exit` fail-open 계약의
    한 축이다(두 소스 모두 None 일 때만 평가 유지 쪽으로 fail).
    """
    try:
        boards = boards_at(_now_kst().time())
        return MarketBoard.PRE_NXT in boards and MarketBoard.MAIN not in boards
    except Exception:
        return None

# NXT 프리장(08:00~09:00) 청산 **평가** 화이트리스트 (2026-08-06 사용자 결정).
#
# 여기 없는 전략은 프리장 단독 구간 동안 청산 평가(고점 갱신 포함) 자체를 보류한다.
# 근거 = 프리장의 얇은 호가는 전일 상한가 종목의 시초가가 하한가 부근에 형성되는 등
# 왜곡이 잦아(사용자 실측), 왜곡 틱으로 허깨비 손절이 발화하거나 트레일링 고점이
# 오염된다. 30일 APBK0918 매도 거부 전수(momentum 익일매도 2 + donchian 손절 3 +
# LTV 1)에서 KIS 거부가 **우연히** 이 보류를 수행해 전부 09:00 KRX 체결로 밀렸는데,
# 이 게이트가 그 우연을 정식 경로로 만든다.
#
# **평가 보류이지 주문 보류가 아니다** — 주문만 보류하면 프리장 허깨비 틱이 발화시킨
# 신호가 09:00 실제 매도로 전환된다(KRX 시가가 정상이어도 팔림). 평가를 보류하면
# 09:00 부터 정상 시세로 재평가되어 진짜 이탈만 매도된다.
#
# LTV 는 프리장 매매가 설계 의도(상한가 익일 청산 + 프리장 매수, 사이클 38)라 예외.
# ⚠️ `tradable_boards` 로 게이팅 금지 — 그 설정은 매수 전용(사이클 38 명문화)이고,
#    매수 목적의 보드 변경이 청산 규약까지 조용히 바꾸는 커플링을 차단한다(AST 가드).
_PRE_MARKET_EXIT_EVAL_STRATEGIES = frozenset({"long_tail_volatility"})

# cycle273e (2026-09-10, D2(나)) — WS 틱(`on_tick`) 매수 평가 skip 대상.
# donchian_swing = 일봉 전략이라 tick 평가가 구조적 낭비(2026-05-12, G안).
# kojiro = 갭업/갭다운/붕괴 가드가 스코프 필터 없는 통합채널 `[7] STCK_OPRC`
#   하나에 매달려 있어(09-07 실측 N=103, 갭업 탐지율 0/8) 매수 평가 자체가
#   오염된다 — "일봉이라 낭비"가 아니라 경계 판정 × 노이즈 구간 × 손절폭
#   대비 타이밍 비용이 근거다(kojiro 용은 검증된 적 없는 donchian 판단을
#   복붙하지 않는다). 매수는 `_swing_buy_poll_loop`(REST `stck_oprc`)에서만.
_TICK_BUY_EVAL_SKIP_STRATEGIES = frozenset({"donchian_swing", "kojiro"})


def _tick_buy_eval_blocked_by_channel(ticker: str) -> bool:
    """cycle294 §6 — **코호트 축** WS 틱 매수 평가 skip 판정.

    ## 왜 술어가 「채널」이 아니라 「코호트」인가 (🔴 절대 규칙 5)

    cycle293 은 술어를 「이 종목이 **전용 채널**에 구독돼 있는가」
    (`applied in DEDICATED_TICK_TR_IDS`)로 두었다. 3단계는 통합 채널을 없애고
    **모든** 종목을 전용 채널로 보내므로 그 술어는 **전 종목 참**이 되어
    momentum·volatility_breakout·long_tail_volatility·bull_flag_breakout·
    vcp_breakout **5전략의 틱 매수가 통째로 죽는다** — 그 5전략은 틱이 **유일**
    매수 경로다(donchian/kojiro 는 `_TICK_BUY_EVAL_SKIP_STRATEGIES` 로 이미
    skip 이고 `_swing_buy_poll_loop` REST 폴이 매수를 담당한다).

    술어의 **원래 의도**는 채널이 아니라 코호트였다 — 「오늘까지 통합 채널에서
    프레임이 **0건**이던 종목(`nxt_tradable=False` ∧ 출처 권위)에 프레임이 새로
    들어와 5전략의 매수 평가가 시총 1,000억↑ 유니버스의 **64%** 를 새로 잡는
    것」. `nxt_true` 종목은 **어제도 통합 채널에서 프레임을 받았고** 매수 평가를
    이미 받고 있었다 ⇒ 3단계는 그들에게 **채널만 바꾼다** ⇒ 매수 평가가
    계속돼야 한다.

    ## 🔴 모드를 **보지 않는다** (금기 9)

    킬스위치 `off` 는 이미 전용 채널에 올라간 구독을 **되돌리지 않는다**(§9-B).
    모드를 보면 「사고 중에 누르는 안전 조치가 5전략의 매수를 그 코호트에 열어
    준다」 = cycle293 적대 검증 CRITICAL 의 재현이다. 스탬프는 모드와 무관하게
    **구독 사실**을 따른다(구독을 발사하는 `tick_tr_id_for` 안에서 심긴다).

    ## 스탬프 부재 = 열어 둔다 (§6-D 비대칭)

    닫힘 오류는 **레지스트리 전체 실패 한 번**으로 전 종목에 동시에 일어나고
    (상관된 실패 = 그날 5전략 매수 0), 열림 오류는 종목별로 독립이다. 절대 규칙
    5 가 이 사이클 최대 위험으로 지목한 것이 전자다. 그 상태는 조용하지 않다 —
    `scanner` 의 `[tick_buy_gate] ... unstamped=` 가 하루 1행 WARNING 으로
    규모를 남긴다.

    ## 🔴 B-2(매수 개방)는 **끝났다** — 이 값은 더 이상 매수를 막지 않는다 (cycle336)

    `on_tick` 매수 분기의 `if chan_buy_blocked: continue` 는 **걷혔다**(사용자 결정
    2026-09-21 + `domain-consult`). 그러니 **그 `continue` 를 되살리지 마라** — 되살리면
    사이클 156 Q0 가 폐기한 기준(「`nxt_tradable` 은 주문 시점 분기용으로만」)을 다시
    매수 판정에 들이는 것이고, 그것이 정확히 cycle293 이 저지른 일이다.

    선행 조건으로 적혀 있던 `ACML_VOL` 스코프 대조는 **해소됐다** — 이 코호트는
    `_classify_channel` 이 항상 KRX 를 내므로 08:00~20:00 `H0STCNT0` 고정(하루 전환 0회)
    이고, 비교 대상 `avg_volume_20` 의 원천도 `api/condition.py` 의 `FID_COND_MRKT_DIV_CODE="J"`
    = KRX 일봉이다. **KRX↔KRX 정합**이라 걱정이 오히려 뒤집혀 있었다.

    이 함수는 계속 산다 — 호출자가 `:620` 하나로 줄었고 그 값은
    `_note_pre_window_krx_frame` 게이팅과 `[tick_buy_gate]` 계측에 쓰인다.
    즉 술어의 역할이 **「매수를 막는 장치」에서 「코호트를 세는 계측기」**로 바뀌었다.
    """
    try:
        from src.engine.scanner import tick_buy_cohort_blocked

        return bool(tick_buy_cohort_blocked(ticker))
    except Exception:  # pragma: no cover — never-raise, fail-open
        return False


def _note_pre_window_krx_frame(ticker: str) -> None:
    """cycle294 §2-D — 프리 창에 **무송출 코호트** 틱이 들어온 사실을 센다(관측만).

    호출자는 코호트 판정이 **참**인 자리에서만 부른다. 그 코호트는 프리 창에
    `H0STCNT0`(KRX 전용)로 구독되므로(§2-C 선택지 (가)) 그때 들어오는 프레임은
    곧 「KRX 가 시가 단일가 구간에 프레임을 보냈다」는 뜻이다.

    그 일이 일어나는가에 대한 우리 답은 **[추론, 확신 ≈80%] 보내지 않는다**
    (`H0STCNT0` 은 체결가 채널이고 단일가 구간에는 체결이 없다). 이 함수가 그
    추론을 D+1 실측으로 바꾼다. 🔴 **행위는 바꾸지 않는다** — 프레임을 막는
    게이트를 더하는 것은 매매 행위 변경이라 별도 승인 대상이다.

    노출 자체가 이미 좁다 — 08:00~09:00 은 `PRE_NXT ∈ active ∧ MAIN ∉ active`
    라 `_defers_pre_market_exit` 가 LTV 외 6전략의 청산 평가를 이미 보류한다.

    never-raise · 창 밖이면 leaf 안에서 즉시 반환한다(hot path).
    """
    try:
        from src.engine import tick_channel_clock

        tick_channel_clock.note_pre_window_frame(ticker, _now_kst())
    except Exception:  # pragma: no cover — never-raise
        return


# cycle222-a3 (2026-08-21, F-B / G-4 로 근거 정정) — 당일고가 앵커 채택 **제외** 전략.
#
# 여기 있는 전략은 `day_high` 를 앵커(`high_since_buy`)에 절대 채택하지 않는다.
# 멤버십 기준은 "앵커에 **외부 소유자가 있고 그 소유자가 절대 대입을 한다**" 이다
# — `max()` 갱신이 아니라 값을 **덮어쓰는** 코드가 있는 전략(= 두 번째 writer 를
# 넣으면 누가 이길지가 호출 순서에 좌우된다). AST 가드
# `tests/unit/ast/test_cycle222a3_ast_anchor_owner_coupling.py` 가 그 커플링을
# 강제한다 — 새 절대 대입이 생기면 이 집합과 함께 재검토하라고 FAIL 한다.
#
# ## 사실관계 — 유일한 외부 소유자는 사이클 142 의 LTV 익일청산 경로
#
# `scheduler._execute_next_day_clear` 는 갭업 LTV 종목에 대해
#     pos.high_since_buy = today_open        # ← max() 가 아니라 절대 대입
# 을 한다. 목적은 **개장 즉시 매도 방지**다 — 전일 상한가의 stale 고점을 그대로
# 두면 D+1 시가에 `drop_rate` 가 이미 트레일링 임계를 넘어 개장하자마자 매도가
# 난다(2026-06-15 후성 093370: 6/12 매수 17,150 → 6/15 고점 23,700 → 마감 22,300,
# −5.91%). 그래서 기준점을 **오늘 시가로 내리는 것이 의도**다.
#
# 이 대입이 실행되는 시각은 **08:00:30 근방**이다 — `_next_day_task` 가
# `TIME_PRE_NXT_OPEN`(08:00) 직후 생성되고, `_execute_next_day_clear` 가
# `NEXT_DAY_STABILIZE_SECS`(30초) 를 자고 나서 대입한다. 09:00:30 이 아니다.
#
# ## ⚠️ 정정 (G-4) — 앞선 서술 두 개가 코드·타임라인 사실과 어긋났다
#
# (1) "LTV 앵커는 러닝 max 가 아니라 익일 시가 기준점이라 blind 복구가 의미 없다"
#     → **거짓**. `strategies/long_tail_volatility.py` 의 익일 트레일링 분기는 매 틱
#       `pos.high_since_buy = max(pos.high_since_buy, current_price)` 로 **러닝 max**
#       를 돌린다. 08:00:30 대입은 그 러닝 max 의 **시작점을 리셋**할 뿐이다.
# (2) 절대 대입 시각이 09:00:30 이라는 서술 → **거짓**(위 08:00:30).
#
# ## 그래서 제외의 진짜 근거는 무엇인가 — **귀인(attribution)**
#
# LTV 를 제외하는 이유는 사이클 142 가 깨져서가 아니다. `day_high` 는 **오늘
# 스코프** 라 사이클 142 가 버리려던 stale **멀티데이** 고점을 되살리지 않는다.
# 실제로 일어나는 일은 **LTV 가 blind 내성을 얻어 놓치던 (오늘의) 고점을 보게 되고
# −2% 트레일링이 더 일찍 발화**하는 것이다 — 규칙대로면 오히려 정확하다.
#
# 그럼에도 제외하는 이유는 **귀인**이다. 이번 사이클의 동기는 kojiro/donchian 의
# ATR 트레일링이고 LTV 는 아니다. 근거 없이 두 전략의 청산 타이밍을 동시에 바꾸면
# D+1 관측에서 무엇이 무엇을 바꿨는지 가릴 수 없다(cycle223 이 S2·S3 만 고치고
# 파라미터 **값**은 건드리지 않은 것과 같은 논리).
#
# **재검토 조건 = kojiro/donchian 의 `[day_high_adopted]` 실측이 쌓인 뒤.**
#
# ⚠️ `tradable_boards` 로 게이팅 **금지** — 그 설정은 매수 진입 전용이고(사이클 38
#    명문화), 매수 목적의 보드 변경이 청산 규약을 조용히 바꾸는 커플링을 차단한다.
#    판정은 이 **명시 상수**로만 한다(AST 가드).
#
# 전수 조사(2026-08-21, `high_since_buy` 대입 AST 전수) 결과 메모리 앵커에
# **절대 대입**을 하는 외부 소유자는 `scheduler` 의 LTV 익일청산 경로 하나뿐이다:
#   - `strategies/long_tail_volatility.py` / `strategies/momentum.py` → `max(...)` (올리기 전용)
#   - `strategy_base._apply_high_since_buy_from_candles` → `candidate <= high` 면 return
#     (실질 올리기 전용)
#   - `strategy.py` / `strategy_base.py` 의 `= buy_price` → 생성 시 초기화(외부 소유자 아님)
#   - `db/positions.py` → DB 컬럼 write (메모리 앵커 아님)
_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES = frozenset({"long_tail_volatility"})

# cycle222-a (2026-08-21) — 트레일링 앵커 blind 내성 롤백 스위치.
#
# True 면 `on_tick` 이 관측된 당일 고가(WS payload `[8]` 필드 / REST 단건시세의
# 동일 필드)를 앵커(`high_since_buy`)에 반영한다. 기존 동작은 "수신된 틱들의
# 러닝 max" 라서 tick 미수신(blind, 08-19 실측 최장 58분) 구간의 고점이 **존재
# 자체로 기록되지 않았다** — 매수 당일 봉은 `_apply_high_since_buy_from_candles`
# 의 `buy_date < 영업일 < today` 양쪽 strict 경계가 의도적으로 배제하므로
# 매수일 blind 고점은 영원히 복구되지 않았다.
#
# 채택 대상은 **매수 이후 고가뿐**이다 — `_day_high_since_entry` 의 진입 시점
# baseline 초과분만 통과한다(F1). 이 경계가 없으면 매수 전 스파이크가 앵커에
# 박혀 진입 순간 브레이크이븐 승격/샹들리에가 오발화한다.
#
# ⚠️ 롤백 계약 (F6) — False 로 바꾸면 **앵커 갱신 규칙**만 구 동작으로 돌아간다.
#    이미 오염된 앵커로 승격된 kojiro `_stop_floor` 는 **tighten-only 래칫**이라
#    같은 프로세스 안에서는 되돌아가지 않는다. 즉 이 스위치는 "구 동작 완전
#    복원" 이 아니다 — **플래그 변경 + 컨테이너 재시작이 함께 필요**하다
#    (재시작해야 `recompute_held_atr` 가 일봉으로 손절선을 재도출한다).
TICK_DAY_HIGH_ANCHOR = True


class RiskManager:
    """실시간 시세를 감시하며 전략별 매매 신호에 따라 주문을 실행한다."""

    def __init__(self, registry: StrategyRegistry, order_engine: OrderEngine) -> None:
        self.registry = registry
        self.order_engine = order_engine
        # 가설 D (2026-05-12): tradable=False skip 카운터. 1분 1회 INFO 로그 + reset.
        self._tradable_skip_count: dict[str, int] = {}
        self._last_tradable_emit_ts: float = 0.0
        # 사이클 31 (R6, 2026-05-21): `risk.py:152` 사전 가드 침묵 가시화.
        # `current_price > state.total_investment` skip 분기에서 1회/(ticker, strategy)/일
        # INFO emit cap. 매 틱 폭주 차단 + scheduler `_reset_daily_state` 동행 clear.
        # 2026-05-21 09:13 VB 미매수 사고 디버깅 곤란의 근본 원인 (skip 침묵).
        # 사이클 56-D: DailyEmitCap[tuple[str, str]] 마이그레이션. tuple key 호환 보장.
        # scheduler 외부 직접 clear → reset_daily_state() 캡슐화 위임 (사이클 52 OrderEngine 패턴 답습).
        self._risk_silent_skip_logged_today: DailyEmitCap[tuple[str, str]] = DailyEmitCap[tuple[str, str]]()
        # 사이클 62 → 사이클 64 (2026-06-06): 가격 필터 필드 전면 제거 (scanner 이전)
        # 프리장 청산 보류 관찰 로그 1회/전략/일 cap (2026-08-06)
        self._pre_market_defer_logged: set[str] = set()
        # cycle222-a — 포지션 진입 시점 당일고가 baseline (**매수 당일 한정**).
        # {(strategy_id, ticker): (관측일자, 진입서명, baseline)}
        # cycle222-a2: `buy_date < today` 인 멀티데이 보유는 이 맵을 쓰지 않는다
        # (하루 전체가 진입 이후 구간이라 가릴 것이 없다).
        # 순수 메모리(DB write 0). 상세 계약은 `_day_high_since_entry` docstring.
        self._day_high_baseline: dict[tuple[str, str], tuple] = {}
        # cycle222-a3 (F-C) — `[day_high_adopted]` 1회/(strategy_id, ticker)/일 emit cap.
        # 채택이 **실제로 앵커를 올렸을 때만** 발화한다. 이 신호가 없으면 D+1 에
        # 조기 청산이 나도 원인이 day_high 채택인지 정상 트레일링인지 구분 불가라
        # 롤백 스위치(`TICK_DAY_HIGH_ANCHOR`)를 켤지 끌지 판단할 근거가 없다.
        self._day_high_adopted_logged: DailyEmitCap[tuple[str, str]] = DailyEmitCap[tuple[str, str]]()
        # cycle238 (2026-09-02) — 08:00 정각 ~30초 구멍 시정. `by_active`(30초
        # stale) 와 `by_clock`(fresh 시각 폴백)이 갈릴 때만 1회/(전략,사유)/일.
        self._pre_market_divergence_logged: DailyEmitCap[tuple[str, str]] = DailyEmitCap[tuple[str, str]]()
        self._pre_market_divergence_day: str = ""

    def _defers_pre_market_exit(self, strategy_id: str) -> bool:
        """NXT 프리장 단독 구간이면 청산 평가를 보류할지 판정 (cycle238 갱신).

        판정 소스는 **두 축의 OR** 이다:

        - `by_active` = `session_tracker.active`(스케줄러 이벤트 구동) membership.
          `SessionTracker.tick()` 이 30초 주기로만 갱신하는 **stale 캐시**라
          08:00:00~08:00:29 는 07:59 스냅샷(∅)이 그대로 살아 있다.
        - `by_clock` = `_pre_market_only_by_clock()` — tracker 가 쓰는 바로 그
          `session.boards_at` 표를 **fresh 로** 읽는다. 08:00 정각 구멍을 시각이
          닫는다(cycle238, 실측: 08:00:00 청산 발화 → 08:00:29 deferred → 매도
          거부 APBK0918).

        조건은 매수측 PR-F 와 동일한 membership(`PRE_NXT ∈ active AND MAIN ∉ active`).
        두 소스가 **갈릴 때만** `[pre_market_exit_gate_divergence]` 로 계량한다
        (`reason=clock_fallback` = 시각이 구멍을 닫음 / `reason=active_stale_hold`
        = 09:00 정각 stale 보류 유지, team-leader 결정 — 이 방향은 바꾸지 않는다).
        두 소스 모두 판정 불가(예외)일 때만 **fail-open**(평가 유지) — 손절 정지가
        더 위험하다. 화이트리스트 검사가 항상 최상단(LTV 는 두 소스 무관 False).
        """
        if strategy_id in _PRE_MARKET_EXIT_EVAL_STRATEGIES:
            return False
        try:
            active = session_tracker.active
            by_active: bool | None = (
                MarketBoard.PRE_NXT in active and MarketBoard.MAIN not in active
            )
        except Exception:
            active = None
            by_active = None
        by_clock = _pre_market_only_by_clock()
        if by_active is not None and by_clock is not None and by_active != by_clock:
            self._maybe_emit_pre_market_gate_divergence(
                strategy_id, by_clock=by_clock, active=active,
            )
        return bool(by_active) or bool(by_clock)

    def _maybe_emit_pre_market_gate_divergence(
        self, strategy_id: str, *, by_clock: bool, active,
    ) -> None:
        """`[pre_market_exit_gate_divergence]` 두 소스가 갈릴 때만 1회/(전략,사유)/일.

        cap 키 = `(strategy_id, reason)`. 날짜 키는 `_now_kst().date()` 에서
        나온다(cycle237 `_emit_breakeven_promote` 패턴 — seam 정합).
        peek → 로그 → mark(mark-before-log 금지) + 전체 예외 흡수(관측 실패가
        판정을 바꾸지 않는다). hot path — `logger` 만(`write_log`/DB/`await` 금지).
        """
        try:
            reason = "clock_fallback" if by_clock else "active_stale_hold"
            today_key = _now_kst().date().isoformat()
            if self._pre_market_divergence_day != today_key:
                self._pre_market_divergence_day = today_key
                self._pre_market_divergence_logged.reset_daily()
            key = (strategy_id, reason)
            if not self._pre_market_divergence_logged.should_emit(key):
                return
            active_boards = sorted(b.value for b in active) if active else []
            logger.info(
                "[pre_market_exit_gate_divergence] strategy=%s reason=%s "
                "active=%s clock_kst=%s",
                strategy_id, reason, active_boards,
                _now_kst().isoformat(timespec="seconds"),
            )
            self._pre_market_divergence_logged.mark_emitted(key)
        except Exception:
            pass

    def _adopts_day_high(self) -> bool:
        """관측된 당일 고가를 앵커에 채택할 수 있는 구간인지 판정 (cycle222-a).

        MAIN 보드가 활성일 때만 True. 판정 소스는 `session_tracker.active` **단독**
        (이벤트 구동). cycle238 이 프리장 청산 보류 게이트에는 시각 폴백을 OR 로
        얹었지만 이 판정에는 얹지 않았다 — `active` 의 30초 stale 이 여기서는
        fail-closed 방향(09:00:00~29 채택 지연 ≤30초, 08:00 창은 어차피 미채택)이라
        행위 결함이 아니다(cycle238 적대 검증 F6).

        프리장(PRE_NXT 단독) 고가는 얇은 호가의 왜곡이 잦아 앵커에 박히면
        **과대복구 → 허깨비 샹들리에 청산**으로 뒤집힌다. 그래서 프리장 청산 평가
        화이트리스트(LTV)조차 `day_high` 는 쓰지 않는다.

        ⚠️ 이 게이트는 **수신 시각**만 본다 — 통합 채널(`H0UNCNT0`)의 일-스코프
           고가는 09:00 에 리셋되지 않아 MAIN 구간 틱에도 프리장 누적치가 실려
           온다(000250 실측). 그 축의 방어는 `realtime/handler.py` 의
           `[27] HGPR_HOUR` MAIN 창 필터가 **소스에서** 담당한다(cycle222-a2).

        판정 불가 시 **fail-closed(미채택)** — 보류 게이트의 fail-open 과 방향이
        반대인 이유는, 여기서 실패하면 최악이 "구 동작(러닝 max) 유지"인 반면
        잘못 채택하면 앵커가 과대복구돼 조기 청산이 나기 때문이다.
        """
        try:
            from src.engine.session import MarketBoard
            return MarketBoard.MAIN in session_tracker.active
        except Exception:
            return False

    def _day_high_since_entry(
        self, strategy_id: str, ticker: str, pos, day_high: int, today,
    ) -> int:
        """**매수 이후** 고가만 돌려준다 (cycle222-a F1 / cycle222-a2). 미채택이면 0.

        판정 축은 **매수일 대비 오늘**이다:

        - `buy_date < today` (멀티데이 보유) → **하루 전체가 이미 진입 이후**다.
          가릴 '매수 전 구간' 이 존재하지 않으므로 `day_high` 를 **그대로** 돌려준다
          (첫 관측부터 즉시 채택).
        - `buy_date == today` (매수 당일) → **진입 시점 baseline 게이트** 유지.
        - `buy_date > today` / `buy_date` 가 `date` 가 아님 / `today` 가 None
          → **미채택(fail-closed)**.

        ## 매수 당일에 baseline 이 필요한 이유 (F1)

        관측된 당일 고가에는 **매수 전 구간**이 섞여 있다. 09:00 갭상승 스파이크
        → 눌림 → 09:12 눌림 매수 라면, 매수 직후 첫 관측의 고가는 전부 매수 전
        값이다. 그걸 그대로 앵커에 넣으면
          - donchian: `high >= buy + 1.5×entry_atr`(라이브) 즉시 성립 → 손절선이
            진입 순간 매수가로 승격 → 한 틱만 내려가면 STOP_LOSS
          - kojiro: 앵커를 부풀린 **그 틱에서** 2.5ATR 샹들리에 발화 → 즉시 전량 청산
        이 오염은 `_apply_high_since_buy_from_candles` 의 `buy_date < 영업일 <
        today` 양쪽 strict 경계가 정확히 막으려고 존재하는 것과 같은 종류다.

        해법 = **진입 시점 baseline**. 그 포지션 진입 후 첫 관측을 baseline 으로
        기록만 하고 채택하지 않는다. 이후 baseline 을 **초과한** 값만 채택하므로
        초과분은 정의상 매수 이후 고가다 → 과대복구가 구조적으로 불가능하다.

        ## 왜 D+1 이후에는 baseline 을 걷어내는가 (cycle222-a2, 사용자 재설계 지시)

        1차 구현은 baseline 을 **매일** 다시 잡았다. 그러면 그날 첫 관측이 통째로
        버려지는데, 그게 버리는 것은 정확히 **오늘의 blind 고점**이다 — 전일까지의
        고점은 매일 아침 `_apply_high_since_buy_from_candles` 가 일봉으로 복구하지만
        **오늘 봉은 미확정이라 그 경로가 구조적으로 배제**하고, on_tick 이 올린 값은
        DB 에 쓰이지 않는다. 즉 오늘의 blind 고점은 아무도 복구하지 않는다.
        사용자 지적 그대로 "기간중 최고점에서 야금야금 하락했을 때 익절을 못한다".

        D+1 이후에는 가릴 매수 전 구간이 애초에 없으므로 baseline 은 순손실이다.

        ## 프리장 오염(F2) 방어는 어디로 갔나

        통합 채널(`H0UNCNT0`)의 일-스코프 필드는 09:00 에 리셋되지 않아 프리장
        체결이 누적된다(000250 실측). 그 방어는 **소스로 이관**됐다 —
        `realtime/handler.py` 가 `[27] HGPR_HOUR` 로 KRX MAIN 창 밖 고가를
        0(미관측)으로 강등한다. 매수 당일에는 baseline 이 한 겹 더 흡수한다.

        불변식:
        - **per-position-entry**: 진입 서명(매수일/매수가/주문번호)이 바뀌면
          재스냅샷. 포지션 소멸 시 호출부가 baseline 을 pop 한다(두 겹 방어) —
          청산 후 재진입에 구 baseline 이 살아남으면 안 된다. 멀티데이 보유 →
          청산 → 당일 재매수 시 `buy_date == today` 가 되어 baseline 모드로 복귀한다.
        - **날짜 키**: baseline 레코드는 관측일자를 함께 들고 있어 날짜가 바뀌면
          무효화된다. `reset_daily_state()` 도 동행 clear.
        - **판정 불가는 미채택**: 최악이 "구 동작(러닝 max) 유지" 인 방향으로만
          실패한다. 잘못 채택하면 앵커 과대복구 → 허깨비 조기 청산이다.
        - hot path — `await`/DB write **금지**. 예외는 전부 흡수해 0(미채택).

        ## 앵커 소유자 제외 (cycle222-a3 F-B, G-4 로 근거 정정)

        `_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES` 멤버는 **다른 어떤 판정보다 먼저**
        0 이다. 멤버십 기준은 "앵커에 외부 소유자의 **절대 대입**이 있다" 이고,
        현재 유일한 그런 소유자는 `scheduler._execute_next_day_clear` 의
        `pos.high_since_buy = today_open`(LTV 한정, 08:00:30 근방)이다.

        ⚠️ LTV 제외의 결정적 근거는 "사이클 142 가 깨진다" 가 **아니다** —
           `day_high` 는 오늘 스코프라 사이클 142 가 버리려던 stale 멀티데이 고점을
           되살리지 않는다. 실제로 바뀌는 것은 **LTV 가 놓치던 오늘 고점을 보게 되어
           −2% 트레일링이 더 일찍 발화**하는 것뿐이고, 규칙대로면 오히려 정확하다.
           제외하는 이유는 **귀인**이다: 이번 사이클의 동기는 kojiro/donchian 이라
           LTV 청산 타이밍까지 같이 움직이면 D+1 관측을 가를 수 없다.
           재검토 조건 = kojiro/donchian 의 `[day_high_adopted]` 실측 축적 후.
           상세는 상수 주석 참조.
        """
        try:
            if strategy_id in _DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES:
                return 0
            if today is None:
                return 0
            buy_date = getattr(pos, "buy_date", None)
            # `datetime` 은 `date` 의 서브클래스라 isinstance 만으로는 통과한다.
            # Position.buy_date 계약은 순수 `date` 이고(`is_next_day` 도 동일 전제),
            # datetime 을 today(date) 와 비교하면 TypeError 다 → 명시 배제해 둔다.
            if not isinstance(buy_date, _date) or isinstance(buy_date, _datetime):
                return 0
            if buy_date > today:
                # 미래 매수일 = 시계/DB 오염 → 근거 없는 앵커 상승 금지
                return 0
            if buy_date < today:
                # 멀티데이 보유 — 하루 전체가 진입 이후 구간이므로 즉시 채택
                return day_high

            key = (strategy_id, ticker)
            entry = (
                str(buy_date),
                int(getattr(pos, "buy_price", 0) or 0),
                str(getattr(pos, "order_no", "") or ""),
            )
            rec = self._day_high_baseline.get(key)
            if rec is None or rec[0] != today or rec[1] != entry:
                # 진입 후 첫 관측(또는 재진입) = baseline 설정만, 채택 없음
                self._day_high_baseline[key] = (today, entry, day_high)
                return 0
            return day_high if day_high > rec[2] else 0
        except Exception:
            return 0

    def _maybe_emit_pre_market_defer(self, strategy_id: str) -> None:
        """보류 발생 1회/전략/일 관찰 로그 — 매 틱 폭주 금지."""
        if strategy_id in self._pre_market_defer_logged:
            return
        self._pre_market_defer_logged.add(strategy_id)
        logger.info(
            "[pre_market_exit_deferred] strategy=%s — NXT 프리장 청산 평가 보류, "
            "09:00 KRX 시세로 재개", strategy_id,
        )

    def _maybe_emit_day_high_adopted(
        self, strategy_id: str, ticker: str, prev_anchor: int, new_anchor: int,
        observed: int,
    ) -> None:
        """당일고가 채택이 앵커를 올린 사실을 1회/(전략, 종목)/일 관찰 로그로 남긴다.

        hot path — `logger` 만 쓴다(`write_log`/DB/`await` 금지, AST A-1/A-1b).
        선례 = `_maybe_emit_pre_market_defer`(logger.info) + `_risk_silent_skip_logged_today`
        (DailyEmitCap). `reset_daily_state()` 가 동행 clear 한다.
        """
        key = (strategy_id, ticker)
        if not self._day_high_adopted_logged.should_emit(key):
            return
        self._day_high_adopted_logged.mark_emitted(key)
        logger.info(
            "[day_high_adopted] strategy=%s ticker=%s prev_anchor=%d "
            "new_anchor=%d observed=%d — blind 구간 고점 복구로 트레일링 기준점 상승",
            strategy_id, ticker, prev_anchor, new_anchor, observed,
        )

    def reset_daily_state(self) -> None:
        """사이클 56-D — 일일 RiskManager 상태 초기화 (scheduler 위임).

        사이클 31 R6 _risk_silent_skip_logged_today 일괄 clear.
        사이클 52 OrderEngine.reset_daily_state() 패턴 답습 (캡슐화).
        사이클 64 — 가격 필터 필드 scanner 이전으로 본 영역에서 제거.
        """
        self._risk_silent_skip_logged_today.clear()
        self._pre_market_defer_logged.clear()
        # cycle222-a — 진입 시점 당일고가 baseline 동행 clear (정산 후 잔류 금지).
        self._day_high_baseline.clear()
        # cycle222-a3 (F-C) — `[day_high_adopted]` emit cap 동행 clear.
        self._day_high_adopted_logged.clear()
        # cycle238 — `[pre_market_exit_gate_divergence]` emit cap 동행 clear.
        self._pre_market_divergence_logged.clear()

    async def on_tick(
        self,
        ticker: str,
        current_price: int,
        open_price: int,
        change_rate: float,
        *,
        day_high: int = 0,
        acml_vol: int = -1,
    ) -> None:
        """실시간 체결가 수신 시 호출된다.

        cycle227 (2026-08-25) — `acml_vol`(관측된 누적거래량, 키워드 전용·기본 -1
        = 미수신). `acml_vol >= 0` 일 때만 `tick_volume.record_acml_vol` 에 기록한다.
        **`ticker_prices` 에는 절대 주입하지 않는다** — donchian 이 그 dict 의 고가
        키로 `ext_pct` 과열 가드를 계산하므로 키가 늘면 매수 행위가 바뀐다(AST-1).
        그 외 on_tick 행위 변경 0 — 이번 사이클은 배관 + 관측(Stage 0)뿐이고
        BFB/VCP 거래량 게이트는 여전히 유령 키를 읽는다(전환은 별도 사이클).

        cycle222-a (2026-08-21) — `day_high`(관측된 당일 고가, 키워드 전용·기본 0).
        앵커는 "수신된 틱들의 러닝 max" 가 아니라 **"관측된 매수 이후 고가의 max"**
        다. blind 구간 고점이 도착한 **단 하나의 관측**으로 복구된다. 갱신은
        **올리기 전용**이며 `day_high >= current_price` 정합 가드 + MAIN 활성 +
        **매수 이후 판정**(`_day_high_since_entry`) 을 모두 통과해야 채택한다.
        기본값 0 = 미관측 → 구 동작 그대로.

        cycle222-a2 (2026-08-21) — 매수 이후 판정을 **매수일 대비 오늘**로 한다.
        `buy_date < today`(멀티데이 보유)면 첫 관측부터 즉시 채택하고,
        `buy_date == today` 일 때만 진입 시점 baseline 게이트를 건다(F1).
        프리장 오염(F2) 방어는 `realtime/handler.py` 의 `[27] HGPR_HOUR`
        MAIN 창 필터로 **소스에 이관**됐다.

        가드 평가 순서 (사이클 165 명문화 — 변경 0):
          L0. 매도/손절/Trailing/익일청산: 보드 가드 *전* 평가 (사이클 38 명문화 영속).
              `check_exit_signal` 분기는 PRE/MAIN/POST 무관 항상 작동 — `tradable_boards`
              는 매수 진입 전용.
          L1. 보드 가드 (사이클 38): `session_tracker.is_tradable(strategy_id, params)`.
              매수 신호 평가 진입 전 차단.
          L2. (사이클 I 제거) 시장 레짐 매수 가드 폐지 — 레짐은 매수를 차단/축소하지
              않는다 (관찰 전용 전환). 레짐 대응은 cash_usage_ratio 로만.
          L3. 중복 가드: `registry.is_ticker_blocked_for_buy()`.
              보유 OR 주문중 OR 당일매도 통합 차단.
          L4. 자금 사전 가드: `state.is_low_funds_blocked(ticker)` 또는
              `current_price > state.total_investment` skip (사이클 31 R6 가시화).

        매도/손절/Trailing/익일청산은 L1·L3·L4 *전* 평가 → tradable_boards 무관 항상 작동.
        """
        from datetime import datetime as _dt
        from src.engine.scanner import KST_TZ, ticker_last_tick, ticker_prev_close, ticker_prices

        # 1. 공용 시세 갱신 (1회)
        prev_close = ticker_prev_close.get(ticker, 0)
        prdy_ctrt = round((current_price - prev_close) / prev_close * 100, 2) if prev_close > 0 else 0.0
        ticker_prices[ticker] = {
            "current_price": current_price,
            "open_price": open_price,
            "change_rate": round(change_rate, 2),
            "prdy_ctrt": prdy_ctrt,
        }
        # Phase D: 마지막 tick 수신 시각 추적 (5분 주기 _report_tick_coverage 가 사용)
        # dict assign 1회 비용 — on_tick은 초당 수십~수백 호출 가능하므로 추가 연산 금지
        now_kst = _dt.now(KST_TZ)
        ticker_last_tick[ticker] = now_kst

        # cycle227 — 실측 누적거래량 관측 배관(P0-1 시정 Stage 0). `acml_vol >= 0`
        # (관측 있음)일 때만 기록 — 기본값 -1(미수신)은 무시한다(dict assign 1회,
        # ticker_last_tick 선례 비용). **`ticker_prices` 는 절대 건드리지 않는다.**
        if acml_vol >= 0:
            from src.engine import tick_volume
            tick_volume.record_acml_vol(ticker, acml_vol)

        # cycle222-a — 앵커 blind 내성. 관측된 당일 고가의 **구간 자격**만 1회 판정한다.
        # ⚠️ `ticker_prices` 에 절대 주입하지 않는다 — donchian 이 그 dict 의 고가 키를
        #    읽어 `ext_pct` 를 계산하므로 값이 채워지면 **매수 행위가 바뀐다**.
        #    `day_high` 는 함수 인자로만 흐른다.
        # ⚠️ 여기 통과 = 채택 확정이 아니다. 포지션별 **매수 이후 baseline** 비교가
        #    전략 루프 안에서 한 번 더 걸린다(`_day_high_since_entry`, F1/F2).
        #    `day_high > 0` 은 미관측(0) 이 baseline 으로 굳는 것을 막는다.
        adopt_day_high = bool(
            TICK_DAY_HIGH_ANCHOR
            and day_high > 0
            and day_high >= current_price
            and self._adopts_day_high()
        )
        day_high_date = now_kst.date() if adopt_day_high else None

        # PR7(동일가 연속 틱 신호 평가 skip) 롤백 — 회귀 발견:
        # VB/LTV 시가 확정 직후 첫 on_tick에서 _prev_price=0 → check_buy_signal first-tick skip.
        # 이후 같은 가격이 반복되면 PR7 가드로 skip → _prev_price=0 유지 → 가격 변화가 와도
        # prev=0이라 돌파 가드("prev<target AND current>=target") 통과 못 해 매수 신호가
        # 끝까지 발생하지 않는 결함. 2026-05-11 운영 중 13종목 중 5종목 돌파 상태인데
        # VB 매수 신호 로그 0건 확인. 이벤트 루프 부담보다 매수 기회 누락이 큰 손실이라 즉시 롤백.

        # cycle293 §3-E B-1 — 종목 축 매수 평가 skip 판정을 **틱당 1회** 계산한다
        # (전략 루프 안에서 부르면 전략 수만큼 반복된다 — 위 `ticker_last_tick`
        # 주석의 "추가 연산 금지" 규약). 값은 **매수 분기에서만** 소비되므로
        # 청산·트레일링·익일청산 평가에는 어떤 영향도 없다.
        chan_buy_blocked = _tick_buy_eval_blocked_by_channel(ticker)
        if chan_buy_blocked:
            # cycle294 §2-D — 관측 전용(행위 0). 코호트가 참일 때만 부르므로
            # 비용이 그 코호트에 한정되고, 창 밖이면 leaf 가 즉시 반환한다.
            _note_pre_window_krx_frame(ticker)

        # 2. 활성화된 전략별 순회
        for strategy in self.registry.enabled():
            state = strategy.state

            # 일일 손실 한도 초과 시 신규 매수 중단
            if strategy.is_daily_loss_exceeded() and not state.buy_disabled:
                state.buy_disabled = True
                logger.warning("일일 최대 손실 한도 도달: %s, 신규 매수 중단", strategy.strategy_id)

            # NXT 프리장 청산 평가 보류 게이트 (2026-08-06 사용자 결정) —
            # 프리장 왜곡 틱의 허깨비 손절·트레일링 고점 오염 차단. LTV 만 예외
            # (`_PRE_MARKET_EXIT_EVAL_STRATEGIES`). 09:00 MAIN 진입 시 자동 재개.
            pos = state.positions.get(ticker)
            defer_exit = pos is not None and self._defers_pre_market_exit(
                strategy.strategy_id
            )
            if defer_exit:
                self._maybe_emit_pre_market_defer(strategy.strategy_id)

            # 보유 중이면 고가 갱신 (프리장 보류 중엔 왜곡 고가 앵커 오염 금지)
            # cycle222-a/a2 — 관측 고가는 **매수 이후 구간분만** 병합해 blind
            # 구간 고점을 복구한다(멀티데이=즉시 / 매수당일=baseline 초과분, F1).
            # 갱신은 올리기 전용.
            if pos and not defer_exit:
                eff_day_high = (
                    self._day_high_since_entry(
                        strategy.strategy_id, ticker, pos, day_high, day_high_date,
                    )
                    if adopt_day_high
                    else 0
                )
                prev_anchor = pos.high_since_buy
                pos.high_since_buy = max(
                    prev_anchor, current_price, eff_day_high,
                )
                # cycle222-a3 (F-C) — 채택이 **실제로 앵커를 올렸을 때만** 관찰 로그.
                # `eff_day_high` 는 `day_high >= current_price` 게이트를 통과한 값이라
                # 여기서 크면 새 앵커가 곧 그 값이다(= 상승분이 채택 기여).
                if eff_day_high > prev_anchor:
                    self._maybe_emit_day_high_adopted(
                        strategy.strategy_id, ticker, prev_anchor,
                        pos.high_since_buy, eff_day_high,
                    )
            elif pos is None and self._day_high_baseline:
                # 청산으로 포지션이 사라지면 baseline 폐기 — 당일 재진입 시 반드시
                # 재스냅샷된다(진입 서명 비교와 함께 두 겹 방어). 맵이 비어 있으면
                # 아무 것도 하지 않는다(hot path 비용 0).
                self._day_high_baseline.pop((strategy.strategy_id, ticker), None)

            # 3. 청산 신호 확인 (보유 중인 경우)
            # 사이클 38 (2026-05-22) — `tradable_boards` 는 **매수 진입 전용** 정책 명문화.
            # 매도/손절/Trailing/익일청산/15:20 강제청산은 PRE/MAIN/POST 무관 항상 평가 —
            # 본 분기는 보드 가드 *없이* 진입 (line 102 `is_tradable` 검사 *전*).
            # 유일한 예외 = 위 프리장 평가 보류 게이트(명시 화이트리스트, 보드 설정 무관).
            if state.has_position(ticker) and not defer_exit:
                # 사이클 19 (2026-05-20) — 매도 발사 후 체결통보 도착 전까지 check_exit_signal 호출 skip.
                # `_selling` 은 execute_sell 진입 직후 add, 체결통보 _handle_sell_fill 시 discard.
                # 매도 1회 보존 + 손절 로그 폭주 차단 (운영 결함: 042700 7초 18+ 행). 6 전략 공통.
                if ticker in self.order_engine._selling:
                    continue
                signal = strategy.check_exit_signal(ticker, current_price, open_price)
                if signal != Signal.NONE:
                    await self.order_engine.execute_sell(ticker, signal, strategy.strategy_id)
                    continue  # 청산 주문 후 매수 신호 확인 불필요

            # 4. 매수 신호 확인
            # 사이클 38 명문화 — 본 분기 *부터* `tradable_boards` 가드 적용 (매수 전용).
            # 보드 가드 — 전략의 tradable_boards에 현재 활성 보드 포함 여부 (Phase 8)
            if not session_tracker.is_tradable(strategy.strategy_id, strategy.config.params):
                # 가설 D (2026-05-12): skip 카운트 누적 + 1분 주기 [tradable_skip] emit
                self._tradable_skip_count[strategy.strategy_id] = (
                    self._tradable_skip_count.get(strategy.strategy_id, 0) + 1
                )
                self._maybe_emit_tradable_skip()
                continue

            # 사이클 I (2026-08-03) — 레짐 매수 게이트 제거 (관찰 전용 전환).
            # 마켓레짐은 더 이상 매수를 차단/축소하지 않는다. 레짐 대응은
            # cash_usage_ratio(운영자 수동 / auto_regime_adjust)로만 수행.
            # 손절/매도/익일청산은 위 check_exit_signal 분기(레짐 게이트보다 앞)에서 정상.

            # 전략 간 중복 매수 방지: 보유/주문 중/당일 매도 모두 가로질러 차단
            if self.registry.is_ticker_blocked_for_buy(ticker):
                continue

            # 자금 부족 사전 가드 — calc_buy_quantity 1주 fallback 조건과 동일.
            # OrderEngine cooldown 등록(매 틱 경고 5건/일)을 줄이기 위해 신호 평가 자체 skip.
            now_ts = time.time()
            if state.is_low_funds_blocked(ticker, now_ts):
                continue
            if state.total_investment > 0 and current_price > state.total_investment:
                # 사이클 31 (R6, 2026-05-21) — 사전 가드 침묵 가시화.
                # 1회/(ticker, strategy)/일 emit cap — 매 틱 폭주 차단 + scheduler
                # `_reset_daily_state` 동행 clear. 2026-05-21 09:13 VB 미매수 사고
                # 디버깅 곤란의 근본 원인 (skip 침묵) 대응.
                emit_key = (ticker, strategy.strategy_id)
                if emit_key not in self._risk_silent_skip_logged_today:
                    self._risk_silent_skip_logged_today.add(emit_key)
                    logger.info(
                        "[risk_silent_skip] ticker=%s strategy=%s "
                        "reason=price_gt_total_investment price=%d total=%d",
                        ticker, strategy.strategy_id, current_price, state.total_investment,
                    )
                continue

            # 사이클 64 (2026-06-06) — 가격 필터 분기 scanner 이전 (G-1 AST 가드 영속).
            # 본 위치(on_tick)에 가격 필터 코드 없음 — scanner.subscribe_filtered_stocks 에서만 적용.

            # cycle273e — WS 틱 매수 평가 skip. 근거는 전략마다 다르다(:79 근처
            # `_TICK_BUY_EVAL_SKIP_STRATEGIES` 주석). 청산(check_exit_signal)은 위
            # 분기에서 이미 평가됐다 — 이 skip 은 매수에만 영향, 무접촉.
            if strategy.strategy_id in _TICK_BUY_EVAL_SKIP_STRATEGIES:
                continue
            # cycle336 — 🔴 **코호트 매수 게이트를 걷었다**(사용자 결정 2026-09-21).
            # 여기 있던 `if chan_buy_blocked: continue` 가 `nxt_tradable=False` 코호트의
            # 매수 평가를 통째로 막았다(실측 구독 158 중 **77, 49%**).
            #
            # 걷은 근거 = **이미 폐기된 기준을 되살린 것이었다.** 사이클 156 Q0 가
            # 「`nxt_tradable` 강제 필터 제거 — **주문 시점 분기용으로만** 활용」을
            # 정했고(`strategies/volatility_breakout.py:450` · `long_tail_volatility.py:501`
            # · `bull_flag_breakout.py:709`), 5전략 전부 `list_by_filter(nxt_tradable=None)`
            # 로 후보를 뽑는다. cycle293 게이트는 그 결정을 **다른 계층에서** 뒤집고 있었다.
            # 즉 이 변경은 완화가 아니라 **원복**이다 — 품질 관문(거래정지·관리종목·
            # 정리매매·시장경고·ETF/리츠/SPAC·저유동)은 한 겹도 줄지 않는다.
            #
            # 🔴 **판정 자체는 살아 있다**(`chan_buy_blocked`, :620). 역할만
            # 「매수를 막는 장치」에서 **「코호트를 세는 계측기」**로 바뀌었다 —
            # `_note_pre_window_krx_frame`(:621~624) 게이팅과 `[tick_buy_gate]` 가
            # 그 값을 계속 쓴다. 되살리려면 이 자리에 `continue` 를 넣으면 된다(1커밋 revert).
            signal = strategy.check_buy_signal(ticker, current_price, open_price)
            if signal == Signal.BUY:
                state.signal_count_today += 1
                await self.order_engine.execute_buy(
                    ticker, current_price, strategy,
                )

    # ---------------------------------------------------------------------------
    # 사이클 64 (2026-06-06) — 가격 필터 헬퍼 메서드 전면 제거 (scanner 이전)
    # G-1 AST 가드: risk.py 에 price_filter 관련 문자열 0건 의무
    # (scanner.py::_apply_price_filter 가 단일 책임 — Q4 옵션 A)
    # ---------------------------------------------------------------------------

    def _maybe_emit_tradable_skip(self) -> None:
        """가설 D (2026-05-12) — 분당 1회 [tradable_skip] INFO 로그 + 카운터 reset.

        - 60s 미만 경과면 카운터만 누적
        - 60s 경과 시: 누적 카운트 + 활성 보드를 1행 INFO 로그로 노출 후 카운터/ts 초기화
        - active_boards 는 `session_tracker.active` 프로퍼티의 정렬된 board.value 리스트

        Codex 추가검토 2 (2026-05-12): `_last_tradable_emit_ts=0.0` 초기화로
        신규 RiskManager 의 첫 tick 에서 `now - 0.0 > 60` 즉시 emit 되던 결함 차단.
        첫 호출 시점을 기준점으로 등록만 하고 emit 보류 — 이후 60s 누적 후 첫 emit.
        """
        now_ts = time.time()
        # 첫 호출 가드 — 기준점만 등록하고 reset 없이 카운터는 누적 유지(다음 emit 으로 노출).
        if self._last_tradable_emit_ts == 0.0:
            self._last_tradable_emit_ts = now_ts
            return
        if now_ts - self._last_tradable_emit_ts < 60.0:
            return
        if not self._tradable_skip_count:
            self._last_tradable_emit_ts = now_ts
            return
        try:
            # Copilot P3 (2026-05-12): private `_active` 직접 접근 대신 `active` 프로퍼티 사용
            active = sorted(b.value for b in session_tracker.active)
        except Exception:
            active = []
        # 형식: [tradable_skip] momentum=X breakout=Y ltv=Z swing=W active_boards=[...]
        # 누적된 strategy_id 알파벳 순으로 노출 (테스트 가시성)
        parts = " ".join(
            f"{sid}={cnt}" for sid, cnt in sorted(self._tradable_skip_count.items())
        )
        logger.info("[tradable_skip] %s active_boards=%s", parts, active)
        self._tradable_skip_count.clear()
        self._last_tradable_emit_ts = now_ts

