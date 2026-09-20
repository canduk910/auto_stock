"""실시간 메시지 파싱/디스패치.

- 실시간 체결가 (H0STCNT0/H0UNCNT0/H0NXCNT0): 현재가, 시가, 등락률 등 추출
  - H0STCNT0(KRX) / H0UNCNT0(KRX+NXT 통합) / H0NXCNT0(NXT) — 메시지 포맷 동일
- 체결통보 (H0STCNI0/H0STCNI9): AES-256-CBC 복호화 후 체결 정보 추출
- NXT 장운영정보 (H0NXMKO0): 보드 전환 이벤트 (Phase 3 SessionTracker에서 활용)
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Callable, Awaitable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

from src.config import settings
# cycle264 — 관측 cap 표준(사이클 258). `daily_emit_cap` 은 stdlib 만 쓰는 leaf 라
# 모듈 최상단 import 로도 순환이 없다(`src/realtime/websocket.py` 선례).
from src.engine.daily_emit_cap import KstDailyEmitCap

logger = logging.getLogger(__name__)

# 콜백 타입
# cycle222-a (2026-08-21) — `day_high`(당일 고가, STCK_HGPR) 키워드 인자 추가.
# cycle227 (2026-08-25) — `acml_vol`(누적거래량, ACML_VOL) 키워드 인자 추가.
# 키워드 + 기본값이라 기존 4-positional 호출자는 무해하다.
TickHandler = Callable[..., Awaitable[None]]
# ticker, current_price, open_price, change_rate, *, day_high, acml_vol

ExecutionHandler = Callable[[str, str, str, int, int], Awaitable[None]]
# ticker, order_no, side, price, quantity

BoardHandler = Callable[[str, str, str], Awaitable[None]]
# tr_key, mkop_cls_code, raw_payload — Phase 3 SessionTracker가 소비

_on_tick: TickHandler | None = None
_on_execution: ExecutionHandler | None = None
_on_board: BoardHandler | None = None


def register_tick_handler(handler: TickHandler) -> None:
    global _on_tick
    _on_tick = handler


def register_execution_handler(handler: ExecutionHandler) -> None:
    global _on_execution
    _on_execution = handler


def register_board_handler(handler: BoardHandler) -> None:
    """NXT 장운영정보(H0NXMKO0) 보드 전환 콜백 등록."""
    global _on_board
    _on_board = handler


_aes_iv: str = ""
_aes_key: str = ""

# cycle222-a2 (2026-08-21) — 당일고가(`[8] STCK_HGPR`) 스코프 필터 창 (HHMMSS 정수).
#
# 통합 시세 채널(H0UNCNT0)의 일-스코프 필드는 **09:00 에 리셋되지 않는다**.
# 라이브 실측(000250 삼천당제약, 2026-08-21): MAIN 구간 통합 틱의 일-스코프 시가가
# 182,800 인데 같은 날 KRX 일봉 O/H/L/C 는 177,500/177,500/166,000/168,700 —
# 182,800 은 KRX 당일고가를 +3.0% 초과하고 전일 종가와 정확히 일치하는
# 08:00~09:00 NXT 프리장 기준가 체결이다. 그 값을 트레일링 앵커에 먹이면
# 없던 고점 기준으로 샹들리에가 조기 발화한다.
#
# 그래서 방어를 **소스로 내린다** — payload 안에 결정적 판별자가 이미 있다:
# `[27] HGPR_HOUR`(최고가 시간, HHMMSS). 이 시각이 KRX 정규장 창 밖이면 고가를
# 0(미관측)으로 강등한다.
#
# cycle222-a3 (2026-08-21, F-A) — 상한을 **KRX 정규장 종료 15:30** 으로 내린다.
#
# 1차 상한 154000 은 `src/engine/session.py::_BOARD_SCHEDULE` 의 MAIN 구간
# (09:00~15:40)에서 가져온 값이었는데, 그 15:40 은 **보드 전환 갭 마진**이지
# 거래시간이 아니다(같은 파일 주석이 "15:30~15:40 갭 마진 포함" 이라고 자백한다).
# KRX 정규장은 **15:30 에 끝난다** — `scanner._TIME_KRX_MAIN_END = 15:30`,
# `scheduler.TIME_KRX_MAIN_CLOSE = 15:30`, `sell_rejection.is_nxt_session_hours`
# 가 15:30~20:00 을 NXT 시간대로 본다. 따라서 15:30:00~15:39:59 사이에 **새
# 당일고가가 생기려면 NXT 애프터 체결뿐**인데 구 상한은 그걸 10분간 통과시켰다
# (실증: `_parse_day_high(hgpr_hour=153100, high=95000) -> 95000`).
#
# 상한을 **포함(<=)** 으로 두는 이유 = 장마감 동시호가(15:20~15:30) 체결이
# `15:30:00` 으로 프린트되면 그 값은 정당한 KRX 당일고가이기 때문이다.
#
# ⚠️ cycle222-a3 G-3 — "종가 체결은 15:30:00 에 프린트된다" 는 **단정은 사실이
#    아니다**. KRX 는 시가·종가 단일가매매에 **30초 이내 임의 연장(랜덤엔드)** 을
#    적용하므로 종가 체결 프린트는 **15:30:00~15:30:30** 범위에서 발생한다.
#    실측: `hgpr_hour=153007 -> 0`, `153030 -> 0` — 둘 다 강등된다.
#    즉 당일고가가 종가에 찍힌 종목은 랜덤엔드 구간만큼 `day_high` 를 놓친다.
#
#    그럼에도 상한을 15:30:30 으로 넓히지 **않는다** — 15:30:01~15:30:30 을 열면
#    같은 시각에 시작하는 **NXT 애프터 체결이 함께 들어온다**(둘은 시각으로
#    구분되지 않는다). 잘못 채택하면 없던 고점 기준 조기 청산(돌이킬 수 없는
#    실현손실)이고 잘못 버리면 현상 유지라는 비대칭이 여기서도 그대로다.
#
#    **누락은 영구적이지 않다** — 익일 07:55 부팅의
#    `StrategyBase._apply_high_since_buy_from_candles` 가 **완결된 일봉**(종가
#    체결까지 반영된 당일 고가)으로 앵커를 복구한다. 따라서 랜덤엔드 손실은
#    **당일 15:30 ~ 익일 부팅** 구간에 한정된다.
#    ⚠️ 단 그 복구는 `buy_date < 영업일 < today` **양쪽 strict** 라
#       **매수 당일 봉은 배제**한다 — 매수 당일 종가에 찍힌 고가는 이 경로로도
#       복구되지 않는다(cycle222-a 가 이미 명시한 매수당일 blind 사각과 동일 축).
#
# ⚠️ 이 상한은 `_BOARD_SCHEDULE` 의 MAIN 종료(15:40)와 **의도적으로 다르다**.
#    보드 스케줄은 "구독/보드 전환" 축이고 여기는 "체결이 어느 시장에서 났나" 축이다.
#    커플링 가드가 (a) 하한/상한이 KRX 정규장(09:00/15:30)과 일치하고
#    (b) 상한이 _BOARD_SCHEDULE MAIN 종료와 **다르다**는 것을 함께 못박는다.
_HGPR_HOUR_MAIN_START = 90000    # 09:00:00 — 포함 (KRX 정규장 개장)
_HGPR_HOUR_MAIN_END = 153000     # 15:30:00 — **포함** (KRX 정규장 종료 = 장마감 동시호가 체결)

# 사이클 102 (2026-06-11) — dispatch silent drop 가시화 (사이클 88 G-REJECT-2 종목별 영속 답습)
# `_handle_tick` graceful drop (len<10 / parsed is None) 분기 ticker별 누적 카운터.
# 5분 주기 `flush_silent_drop_count()` 가 `[dispatch_drop_summary]` 1행 emit + clear.
_silent_drop_count: dict[str, int] = {}

# cycle222-a3 (2026-08-21, F-C) — `[day_high_scope_skip]` 1회/ticker/일 emit cap.
#
# 스코프 강등 경로에 로그가 0건이면 배포 후 라이브 실측이 불가능하다 — D+1 에
# 조기/지연 청산이 나도 그것이 "당일고가 채택" 탓인지 "정상 트레일링" 인지 구분할
# 근거가 없다(CLAUDE.md "비활성화 시 심층 검증 의무"는 소비처 산출물의 실측을
# 요구한다). 이 로그가 F-E 의 **"종일 0" 코호트**(프리장/애프터 고가가 당일
# 최고여서 `HGPR_HOUR` 가 종일 창 밖에 머무는 종목) **후보**를 세는 유일한 수단이다.
# ⚠️ '후보' 다 — 확정 판별자는 risk 계층의 `[day_high_adopted]` 인데 그쪽은
#    보유 포지션에만 존재한다. 한계는 `_maybe_log_day_high_scope_skip` docstring.
#
# ⚠️ cycle222-a3 G-1 — cap 이 `1회/ticker/일` 이므로 **어떤 강등에서 그 1회를
#    쓰느냐**가 로그의 의미를 결정한다. 게이트가 없으면 08:00~09:00 프리장의
#    **정상** 강등에서 먼저 소진되고, 그러면 "종일 0 인 종목" 과 "09:00 이후
#    정상 채택되는 종목" 의 로그가 **완전히 동일**해져 F-E 규모를 못 센다.
#    그래서 `[1] STCK_CNTG_HOUR`(체결 시각)가 MAIN 창 안일 때만 남긴다 —
#    상세는 `_maybe_log_day_high_scope_skip` docstring.
#
# ⚠️ 리셋 방식이 `_silent_drop_count` 와 다른 이유 — 그쪽은 scheduler 가 5분마다
#    `flush_silent_drop_count()` 로 emit+clear 하는 **윈도우 카운터**라 외부 훅에
#    의존한다. 여기는 **일일 1회 cap** 이라 5분 flush 에 얹으면 cap 이 아니라
#    5분 cap 이 되고, 그렇다고 scheduler 에 새 훅을 다는 것은 이번 사이클 범위
#    (8영역 = handler.py·risk.py 둘뿐) 밖이다. 그래서 **KST 일자 인덱스 자기 리셋**
#    으로 외부 의존 없이 일일 경계를 만든다. `time.time()` 정수 연산 1회 =
#    hot path 비용 무시 가능(`datetime` 객체 생성 없음).
_day_high_scope_skip_logged: set[str] = set()
_day_high_scope_skip_day: int = -1

_KST_OFFSET_SECS = 9 * 3600
_SECS_PER_DAY = 86400


def _kst_day_index() -> int:
    """KST 기준 일자 인덱스 (epoch day). `datetime` 생성 없이 정수 연산만."""
    return int((time.time() + _KST_OFFSET_SECS) // _SECS_PER_DAY)


def reset_day_high_scope_skip() -> None:
    """`[day_high_scope_skip]` cap 강제 초기화 (테스트·운영 훅용)."""
    global _day_high_scope_skip_day
    _day_high_scope_skip_logged.clear()
    _day_high_scope_skip_day = -1


def _maybe_log_day_high_scope_skip(
    ticker: str, hgpr_hour: str, cntg_hour: str,
) -> None:
    """**MAIN 체결 틱인데** 당일고가 시각이 창 밖이면 1회/ticker/일 INFO 로 남긴다.

    ## 왜 틱 자신의 시각으로 게이팅하나 (cycle222-a3 G-1)

    이 로그의 **유일한 목적**은 F-E 잔여 사각(= 프리장/애프터 고가가 당일 최고여서
    `day_high` 가 **종일 0** 인 코호트)의 규모를 실측하는 것이다. 그런데 cap 이
    `1회/ticker/일` 이라, 게이트가 없으면 08:00~09:00 **프리장의 정상 강등**에서
    그 1회가 먼저 소진된다. 프리장 체결이 있는 종목은 거의 전부 08:xx 에 1행을
    남기므로 두 코호트의 로그가 **완전히 동일**해진다 — 실측 프로브:

        (a) 09:00 첫 틱만 강등, 이후 200틱 정상 → skip 1행, day_high>0 이 200/201
        (b) 종일 강등(F-E 코호트)            → skip 1행, day_high>0 이 0/201

    두 줄이 구분되지 않으니 "종일 반복되면 F-E" 라는 안내는 성립할 수 없었다.
    cap 이 반복 자체를 불가능하게 만들기 때문이다.

    그래서 판별자를 하나 더 쓴다 — `[1] STCK_CNTG_HOUR`(주식 체결 시간, HHMMSS).
    KIS 정본 `ccnl_total`(H0UNCNT0) 46 컬럼의 **index 1** 이고, `[27] HGPR_HOUR`
    와 같은 payload 에 실려 온다. 이 값이 KRX 정규장 창 안인데 `[27]` 이 창 밖이면
    그것이 정확히 F-E 신호다. 프리장/애프터 틱은 `[1]` 도 창 밖이라 cap 을
    소모하지 않는다.

    ⇒ **이 행이 존재한다 = 그 종목은 MAIN 중에도 당일고가 시각이 창 밖이었다
       = F-E 코호트 후보.** "종일 반복되는지" 를 세는 것이 아니라(cap 이 반복을
       불가능하게 한다) **한 행의 존재**가 신호다. 다만 그것은 **확정이 아니라
       후보**다 — 아래 세 한계를 함께 읽어야 한다.
       (cap 은 그대로 1회/ticker/일 — 폭주 차단 목적은 변하지 않는다.)

    ## ⚠️ 한계 1 — 잔여 노이즈 구간은 "몇 초" 가 아니다 (cycle222-a "H-3" 정정)

    09:00 개장 후 **MAIN 고가가 프리장 고가를 넘을 때까지**는 "MAIN 틱인데
    `[27]` 은 창 밖" 이 정당하게 성립하므로 1행이 남는다. 한때 이 구간을
    "09:00 직후 몇 초" 라고 적었으나 **과소 서술**이다 — 갭다운으로 열려 그날
    프리장 고가를 끝내 못 넘는 종목이면 수 시간, 심하면 **종일**이다.
    (그런 날은 결과적으로 `day_high` 도 종일 0 이라 F-E 와 관측이 같아진다.)

    ## ⚠️ 한계 2 — 교차 판별자가 **보유 포지션에만** 있다

    확정 판별자는 같은 날 그 종목의 `[day_high_adopted]`(risk 계층) 동반 여부이고,
    진성 F-E 는 그 행이 **끝내 나타나지 않는다**. 그런데 그 로그는
    `RiskManager.on_tick` 의 `if pos and ...` 안에 있어 **보유 포지션에만** 찍힌다.
    반면 이 로그는 `_parse_day_high` 에서 나오므로 **보유 여부와 무관하게 전 구독
    종목**에 찍힌다(구독 슬롯 ≈287 vs 보유는 통상 한 자릿수).
    ⇒ skip 행의 **대다수는 교차 판별이 구조적으로 불가능**하다. 미보유 종목은
      판별자가 애초에 존재하지 않는다. 교차 판별이 성립하는 것은 **보유 종목뿐**이다.

    ## ⚠️ 한계 3 — 보유 한정 정밀 측정은 이번 사이클 범위 밖 (유보)

    보유 종목만 정확히 세려면 handler 가 "미관측 0"(payload 가 고가를 안 줬다)과
    "스코프 강등 0"(창 밖이라 버렸다)을 **구분하는 별도 신호**를 `on_tick` 에
    넘겨야 한다. 그건 `_on_tick` **시그니처 변경**이고 REST 폴 경로
    (`scheduler._run_swing_rest_poll_once`)까지 함께 움직이므로 이번 범위
    (8영역 = handler.py·risk.py 둘뿐) 밖이다. **별도 사이클로 유보한다.**

    (G-1 정정 전에는 프리장 틱 전수가 cap 을 태워 이 교차 판별 자체가 불가능했다.)

    `[1]` 파싱 실패는 **미발화**다. 코호트 판정을 못 하는 행을 남기면 그 종목의
    1회 cap 을 근거 없이 태워 진짜 신호를 가린다.

    hot path — `logger` 만 쓴다(`write_log`/DB/`await` 금지, AST A-1/A-1b 동형).
    """
    global _day_high_scope_skip_day
    try:
        cntg = int(cntg_hour)
    except Exception:
        return
    if not (_HGPR_HOUR_MAIN_START <= cntg <= _HGPR_HOUR_MAIN_END):
        # 프리장/애프터 틱의 **정상** 강등 — F-E 신호가 아니므로 cap 을 쓰지 않는다.
        return
    day = _kst_day_index()
    if day != _day_high_scope_skip_day:
        _day_high_scope_skip_day = day
        _day_high_scope_skip_logged.clear()
    if ticker in _day_high_scope_skip_logged:
        return
    _day_high_scope_skip_logged.add(ticker)
    logger.info(
        "[day_high_scope_skip] ticker=%s hgpr_hour=%s cntg_hour=%s — MAIN 체결 "
        "틱인데 당일고가 시각이 KRX 정규장 창(%d~%d) 밖이다. F-E 코호트"
        "(프리장/애프터 고가가 당일 최고 → day_high 종일 0) **후보** 신호이며 "
        "확정이 아니다 — 같은 날 이 종목에 [day_high_adopted] 가 동반됐는지로 "
        "교차 판별하라(동반되면 F-E 아님). ⚠️ 그 판별자는 **보유 포지션에만** "
        "찍히므로 미보유 종목은 교차 판별 수단이 애초에 없다",
        ticker, hgpr_hour, cntg_hour,
        _HGPR_HOUR_MAIN_START, _HGPR_HOUR_MAIN_END,
    )


# ---------------------------------------------------------------------------
# cycle264 (2026-09-06) — `[7] STCK_OPRC` 스코프 shadow 관측. **행위 변경 0.**
#
# `[8] 고가` 에서 실측된 성질(통합 채널의 일-스코프 필드는 09:00 에 리셋되지 않는다,
# cycle222-a2)은 `[7] 시가` 에도 그대로 적용된다. 그 시가가 VB/LTV 의 목표가 기준가가
# 되므로, MAIN 구간 틱이 08:00~09:00 NXT 프리장 기준가를 실어 오면 목표가가 통째로
# 어긋난다(포렌식 `_workspace/analysis/entry_price_0900_20260906/`).
#
# ## 왜 이번 사이클은 **관측만** 하고 고치지 않는가 (자문 §8.1)
#
# 1. 판별자 `[24] OPRC_HOUR` 를 **한 번도 찍어 본 적이 없다** — `grep fields[24]` 가
#    전 소스 0건이고, KIS 로컬 캐시·MCP 정본 모두 컬럼 **이름**만 준다. "프리장 체결이
#    없던 종목에 이 필드가 무엇을 주는가" 는 지금으로선 **추론**이다. 미검증 필드 위에
#    기준가 시정을 세우면 시정의 성패가 그 추론에 걸린다.
# 2. 시정의 행위 영향이 크다 — 과거 VB 매수 116건 재계산상 진입의 **27.6%** 가 사라진다.
# 3. 오늘 이미 두 사이클(cycle262 진입 보류·cycle263 일봉)이 배포됐고 월요일 09:00 이
#    그 둘의 첫 실전 검증이다. 여기에 기준가 시정을 얹으면 진입 감소가 (a) 90초 보류
#    (b) 기준가 상향 (c) 그날 장세 중 무엇 때문인지 **분리 불가능**해진다.
#
# ⇒ 월요일에는 하루치 코호트만 재고(행위 0이라 판독을 오염시키지 않는다), 시정은
#    다음 주말(cycle265)에 3자 대조 결과를 읽은 뒤에 한다.
#
# ⚠️ 볼륨 = 구독 종목당 1행/일. 이 사이클이 쓰는 "~290행/일" 은 **추정**(동시 구독 슬롯
#    41×세션 기준)이고, 운영 `system_logs` 실측 `[tick_coverage] subscribed=` 는 09-03/09-04
#    기준 **107~148** 이다. 반대로 `_scan_loop` 5분 delta 가 구독을 회전시키므로 하루 동안
#    관측된 서로 다른 ticker 수는 슬롯 수보다 클 수도 있다 ⇒ D+1 판독에서 실제 행 수를
#    반드시 세고(분모이자 볼륨 근거), ~300행을 크게 넘으면 재평가한다. 이 수를 다음
#    사이클이 "실측" 으로 인용하지 않게 한다.
#
# ⚠️ `_parse_tick_prices` 는 **byte 동일**이다(소스 세그먼트 sha 핀). 마커는 그 함수
#    밖(`_handle_tick` 의 `parsed` 성공 뒤)에 두고, 어떤 실패도 밖으로 내보내지 않는다 —
#    이 경로에서 예외가 새면 `_on_tick` 재-raise 와 같은 자리로 전파돼 **틱마다 WS
#    재연결**이 일어나고(사이클 88 G-REJECT-1) 그게 곧 손절 사각이다.
_open_scope_observe_cap: KstDailyEmitCap[str] = KstDailyEmitCap()


def reset_open_scope_observe() -> None:
    """`[open_scope_observe]` cap 강제 초기화 (`reset_day_high_scope_skip` 대칭 훅)."""
    global _open_scope_observe_cap
    _open_scope_observe_cap = KstDailyEmitCap()


def _tick_field_raw(fields: list[str], idx: int) -> str:
    """payload 선택 필드를 **원문 그대로** 읽는다. 부재/접근 실패는 `"?"`.

    정규화(0 치환·zero-pad·trim)를 하지 않는 것이 계약이다 — 지금 우리는 이 필드들이
    무엇을 주는지 모르고, 정규화는 바로 그 미지를 지워 관측의 목적을 없앤다.
    `"?"`(부재)와 `""`(빈 문자열 수신)는 서로 다른 사실이므로 구분해서 남긴다.
    """
    try:
        return fields[idx]
    except Exception:
        return "?"


def _maybe_log_open_scope_observe(fields: list[str], open_price: int) -> None:
    """MAIN 체결 틱 1개당 시가 스코프 판별자를 1회/ticker/일 INFO 로 남긴다.

    형식:
        [open_scope_observe] ticker=%s oprc_hour=%s tick_open=%d cntg_hour=%s
                             hgpr_hour=%s mkop=%s hour_cls=%s in_main_window=%s

    - `oprc_hour` = `[24] OPRC_HOUR`(시가가 찍힌 시각). `[27] HGPR_HOUR` 와 같은
      3-형제 서식(HHMMSS)이라 `_parse_day_high` 의 창 판정을 그대로 쓸 수 있다.
    - `tick_open` = `_parse_tick_prices` 가 이미 만든 `[7]` 파싱값을 **그대로** 받는다.
      여기서 `[7]` 을 다시 파싱하면 두 수가 갈라질 수 있고, 그 순간 이 관측은
      "목표가가 실제로 쓴 값" 을 재는 것이 아니게 된다.
    - `mkop`/`hour_cls` = `[34] NEW_MKOP_CLS_CODE` / `[43] HOUR_CLS_CODE`. **틱 자신의**
      장운영/시간 구분이라 `[7]` 의 스코프를 말해 주지는 않지만, 판독 시
      "프리장 틱 / 시가단일가 틱 / 장중 틱" 라벨이 붙어 코호트를 가르기 쉬워진다.

    ## 게이트와 라벨은 **다른 축**이다

    - **게이트** = `[1] STCK_CNTG_HOUR`(틱 자신의 체결 시각)가 MAIN 창 안일 때만
      cap 을 태운다(`_maybe_log_day_high_scope_skip` 과 동일 설계). 프리장 틱이 1회
      cap 을 먹으면 코호트 **분모**가 통째로 죽는다.
    - **라벨** `in_main_window` = `[24]` 가 MAIN 창 안인가. 창 안/밖을 **모두** 남겨야
      오염 **비율**이 나온다. `[day_high_scope_skip]` 은 skip 만 남겨 분모가 없었고
      그래서 지금 "93/287" 이 추정에 머문다.

    hot path — `logger` 만 쓴다(`write_log`/DB/`await` 금지, AST A-1 동형).
    이 함수는 **never-raise** 다(호출자 `_handle_tick` 도 한 겹 더 감싼다).
    """
    ticker = "?"
    try:
        ticker = fields[0]
        cntg_hour = fields[1]
        try:
            cntg = int(cntg_hour)
        except Exception:
            # 코호트 판정 불가 — 근거 없이 그 종목의 1회 cap 을 태우지 않는다.
            return
        if not (_HGPR_HOUR_MAIN_START <= cntg <= _HGPR_HOUR_MAIN_END):
            # 프리장/애프터 틱 — 관측 대상이 아니다(분모 오염 차단). cap 미소모.
            return
        if not _open_scope_observe_cap.should_emit(ticker):
            # cap 소진 — 아래 필드 읽기·문자열 인자 구성 전체가 버려질 작업이다.
            # `_maybe_log_day_high_scope_skip` 과 같은 순서(창 게이트 → cap → 인자).
            # 종목당 1행/일 계약이라 그날 첫 틱 이후의 모든 MAIN 틱이 이 자리로 온다.
            # `should_emit` 은 비소모 peek 이고 `_sync_day`(KST 롤오버 리셋)도 그대로 탄다.
            return

        oprc_hour = _tick_field_raw(fields, 24)
        hgpr_hour = _tick_field_raw(fields, 27)
        mkop = _tick_field_raw(fields, 34)
        hour_cls = _tick_field_raw(fields, 43)
        try:
            _oprc = int(oprc_hour)
            in_main_window = (
                "true" if _HGPR_HOUR_MAIN_START <= _oprc <= _HGPR_HOUR_MAIN_END else "false"
            )
        except Exception:
            # 파싱 불가 = "창 안" 이라고 단정할 수 없다 → false (원문은 위에 그대로 남는다)
            in_main_window = "false"

        _open_scope_observe_cap.emit_once(
            ticker,
            logger.info,
            "[open_scope_observe] ticker=%s oprc_hour=%s tick_open=%d cntg_hour=%s "
            "hgpr_hour=%s mkop=%s hour_cls=%s in_main_window=%s",
            ticker, oprc_hour, open_price, cntg_hour,
            hgpr_hour, mkop, hour_cls, in_main_window,
        )
    except Exception:
        # 관측기 자기 실패 흔적 — 무흔적 `pass` 금지(사이클 258 카드 #5 규약).
        try:
            from src.engine.observer_trace import trace_observer_failure
            trace_observer_failure(
                "[open_scope_observe]", ticker, _open_scope_observe_cap,
                dest_logger=logger,
            )
        except Exception:  # pragma: no cover — 2차 예외도 흡수
            pass


def set_aes_keys(iv: str, key: str) -> None:
    """WebSocket 접속 시 수신한 AES 키를 저장한다."""
    global _aes_iv, _aes_key
    _aes_iv = iv
    _aes_key = key


async def dispatch_message(tr_id: str, tr_key: str, payload: str, encrypted: bool = False) -> None:
    """실시간 메시지를 TR_ID에 따라 적절한 핸들러로 전달한다."""
    # KRX(H0STCNT0) / KRX+NXT 통합(H0UNCNT0) / NXT 단독(H0NXCNT0) 모두 동일 메시지 포맷
    if tr_id in ("H0STCNT0", "H0UNCNT0", "H0NXCNT0"):
        await _handle_tick(payload)
    elif tr_id in ("H0STCNI0", "H0STCNI9"):
        await _handle_execution(payload, encrypted=encrypted)
    # 장운영정보 — 통합(H0UNMKO0) / KRX 단독(H0STMKO0) / NXT 단독(H0NXMKO0). 동일 메시지 포맷
    elif tr_id in ("H0UNMKO0", "H0STMKO0", "H0NXMKO0"):
        await _handle_market_op(tr_id, tr_key, payload)
    else:
        logger.debug("미처리 TR: %s", tr_id)


def _parse_tick_prices(fields: list[str]) -> tuple[int, int] | None:
    """실시간 체결가 payload fields 에서 현재가/시가를 안전 파싱.

    malformed payload 는 None 반환해 상위에서 조용히 스킵한다.
    """
    try:
        return int(fields[2]), int(fields[7])
    except (TypeError, ValueError):
        return None


def _parse_day_high(fields: list[str]) -> int:
    """payload `[8] 고가(STCK_HGPR)` 를 **KRX 정규장(09:00~15:30) 스코프로 필터**해 반환.

    cycle222-a (2026-08-21) — 앵커 blind 내성.
    cycle222-a2 (2026-08-21) — 소스 스코프 필터 신설.

    계약:
      1. `[27] HGPR_HOUR`(최고가 시간, HHMMSS 6자리) 를 int 파싱.
         실패(짧은 payload=IndexError / 빈 문자열 / 비숫자) → **0(fail-closed)**
      2. `_HGPR_HOUR_MAIN_START <= hour <= _HGPR_HOUR_MAIN_END` 가 아니면 → **0**
         (09:00:00 포함 ~ 15:30:00 **포함** = KRX 정규장. cycle222-a3 F-A)
      3. 통과 시에만 `[8]` 을 파싱해 반환. `[8]` 파싱 실패 → 0

    방향이 비대칭인 이유: 잘못 채택하면 **없던 고점 기준 조기 청산**(돌이킬 수 없는
    실현손실)이고, 잘못 버리면 앵커가 기존과 동일한 "러닝 max" 로 남는다(현상 유지).
    판별이 안 되면 무조건 버린다.

    ⚠️ 고가 파싱/판별 실패는 **틱을 버리지 않는다**. 가격(현재가/시가) 파싱 실패만
       기존대로 silent drop 이고, 고가는 부가 관측이라 0 폴백으로 강등한다.
       예외를 던지면 사이클 88 G-REJECT-1 재연결 trigger 가 오발화하고 그 사이
       손절 평가가 통째로 멈춘다.

    ⚠️ 호출자는 반드시 `len(fields) < 10` 가드 **이후** 에서만 호출한다
       (기존 silent-drop 계약 byte 보존). `[27]` 부재는 IndexError → 0 이다.

    KIS 정본(`ccnl_total`, H0UNCNT0) 46 컬럼 0-index 배치:
      [7]STCK_OPRC [8]STCK_HGPR [9]STCK_LWPR ... [24]OPRC_HOUR
      [25]OPRC_VRSS_PRPR_SIGN [26]OPRC_VRSS_PRPR **[27]HGPR_HOUR**
      [28]HGPR_VRSS_PRPR_SIGN ... [33]BSOP_DATE

    ## 잔여 사각 — 프리장 고가가 당일 최고면 그 종목은 **종일** 꺼진다 (cycle222-a3 F-E)

    `[27]` 은 당일 최고가가 찍힌 시각 **하나**뿐이다. 프리장(08:00~09:00) 고가가
    그날 MAIN 고가보다 높으면 `HGPR_HOUR` 는 **종일 프리장 시각에 머문다** — 그
    결과 이 함수는 그 종목의 `day_high` 를 하루 종일 0 으로 강등하고, 앵커는
    cycle222-a 이전과 동일한 "수신된 틱들의 러닝 max" 로 되돌아간다.
    하필 **갭업 코호트**(이 기능이 가장 필요한 군)에서 통째로 무효화되는 셈이다.

    고칠 수단이 payload 안에 없다 — 통합 채널이 주는 대안 판별자(MAIN 구간 고가,
    시장별 분리 고가)가 존재하지 않는다. `[8]` 을 MAIN 창 안에서 자체 러닝 max 로
    재구성하는 것은 곧 "수신된 틱들의 러닝 max" 라 blind 복구라는 목적 자체가
    사라진다. 그래서 **고치지 않고 명시적으로 남긴다**.

    방향은 fail-closed(안전)다 — 잘못 버리면 현상 유지, 잘못 채택하면 없던 고점
    기준 조기 청산이다. 문제는 그것이 **조용하다**는 점이고, 그 침묵을
    `[day_high_scope_skip]`(1회/ticker/일 INFO, F-C)이 깬다.

    ### 측정 계약 (cycle222-a3 G-1 → cycle222-a "H-3" 로 재정정)

    그 로그는 **틱 자신이 MAIN 시각(`[1] STCK_CNTG_HOUR` 가 창 안)일 때만**
    남는다. 따라서 판정 단위는 "종일 반복되는가" 가 아니라 **행의 존재**다 —
    단 그것은 **확정이 아니라 후보 신호**다:

        `[day_high_scope_skip]` 1행이 있다
          = 그 종목은 MAIN 중에도 당일고가 시각이 창 밖이었다
          = 이 잔여 사각의 **후보**다 (확정 아님).

    확정하려면 같은 날 그 종목에 `[day_high_adopted]`(risk 계층)가 동반됐는지를
    본다 — 진성 F-E 는 그 행이 **끝내 나타나지 않는다**.

    ⚠️ 그런데 그 판별자는 `RiskManager.on_tick` 의 `if pos and ...` 안이라
       **보유 포지션에만** 존재하는 반면, 이 로그는 **보유 여부와 무관하게 전
       구독 종목**에 찍힌다(구독 슬롯 ≈287 vs 보유 통상 한 자릿수).
       ⇒ skip 행의 **대다수는 교차 판별이 구조적으로 불가능**하다.
    ⚠️ 잔여 노이즈 구간도 "09:00 직후 몇 초" 가 아니라 **MAIN 고가가 프리장
       고가를 넘을 때까지**이며, 갭다운 종목이면 수 시간~종일이다.
    ⚠️ 보유 한정 정밀 측정은 별도 신호(= `_on_tick` 시그니처 변경)가 필요해
       **이번 범위 밖**으로 유보한다.
    세 한계의 상세는 `_maybe_log_day_high_scope_skip` docstring.

    (G-1 정정 전 계약은 성립조차 하지 않았다: cap 이 1회/ticker/일 이라 프리장의
     **정상** 강등이 그 1회를 먼저 태웠고, 그러면 "종일 0" 종목과 "09:00 이후
     정상 채택" 종목의 로그가 완전히 같아진다. cap 이 '반복' 자체를 불가능하게
     만든다.)

    ## 잔여 사각 2 — 이 창은 **시각 필터이지 시장 필터가 아니다** (cycle222-a3 G-7)

    `[27] HGPR_HOUR` 가 09:00~15:30 안이기만 하면 그 고가가 **어느 시장에서
    났는지는 가리지 않는다**. NXT 주간 세션은 이 창과 겹치므로(우리 보드 스케줄
    기준 MAIN 구간과 동시간대), NXT 주간 체결이 만든 고가는 그대로 통과한다.

    실효 영향은 작다 — 차익거래로 두 시장 가격대가 붙어 있고, NXT 체결가 역시
    그 시각에 **실제로 체결 가능했던 가격**이라 "없던 고점" 이 아니다. 통합 채널
    (`H0UNCNT0`)을 구독하는 한 payload 에 시장 구분 판별자도 없다.

    그래도 F-E 를 "고치지 않고 명시적으로 문서화" 로 처리한 기준을 같은 축에
    적용하지 않으면 비일관이므로 여기 적어 둔다. 넓히려면 KRX 단독 채널
    (`H0STCNT0`)로 내려가야 하는데 그건 구독 축의 재설계다.

    ## 잔여 사각 3 — 장마감 랜덤엔드 (cycle222-a3 G-3)

    상한이 `153000` 포함이라 **15:30:00~15:30:30 랜덤엔드 구간의 종가 체결**은
    강등된다(실측 `153007 -> 0`, `153030 -> 0`). 상한을 넓히지 않는 이유와 그
    누락이 익일 부팅 일봉 복구로 회수되는 범위는 `_HGPR_HOUR_MAIN_END` 상수 주석
    참조.
    """
    try:
        hgpr_hour = int(fields[27])
    except Exception:
        return 0
    if not (_HGPR_HOUR_MAIN_START <= hgpr_hour <= _HGPR_HOUR_MAIN_END):
        # F-C 관측성 (cycle222-a3 G-1 로 게이트 정정) — **틱 자신이 MAIN 시각일
        # 때만** 1회/ticker/일 남긴다. `fields[0]`(종목코드)·`fields[1]`(체결시간)
        # 은 호출자의 `len(fields) < 10` 가드를 이미 통과했으므로 항상 존재한다.
        try:
            _maybe_log_day_high_scope_skip(fields[0], fields[27], fields[1])
        except Exception:
            pass  # 관측 로그 실패가 틱 처리를 막지 않는다 (fail-open)
        return 0
    try:
        return int(fields[8])
    except Exception:
        return 0


def _parse_acml_vol(fields: list[str]) -> int:
    """payload `[13] 누적거래량(ACML_VOL)` 을 파싱한다.

    cycle227 (2026-08-25) — P0-1 시정 Stage 0. `bull_flag_breakout`/`vcp_breakout`
    의 매수 최종 관문이 `scanner.ticker_prices[t]["acml_vol"]` 를 읽는데 그 키를
    쓰는 코드가 전체 소스에 없어 두 전략이 구조적으로 매수 불가였다. 누적거래량은
    이 payload 에 이미 실려 있었다 — `_parse_day_high`(cycle222-a) 가 정확히 같은
    결함("문서화만 해두고 버림")을 시정한 바로 그 자리다.

    계약:
      1. `len(fields) < 14` / 파싱 실패 → **`-1`**(sentinel). **`0` 금지** —
         `0` 이 바로 P0 결함의 그 값이고 "미수신"과 "진짜 거래량 0"을 구별
         불가능하게 만든다.
      2. 음수 응답도 `-1` 로 통일 (미수신과 동일 취급 — 소비처가 `>= 0` 한 번으로 판정).

    ⚠️ 호출자는 반드시 `len(fields) < 10` 가드 **이후**에서만 호출한다
       (`_parse_day_high` 와 동일 계약). `[13]` 부재는 IndexError → `-1`.
    """
    try:
        value = int(fields[13])
    except Exception:
        return -1
    if value < 0:
        return -1
    return value


async def _handle_tick(payload: str) -> None:
    """실시간 체결가 메시지를 파싱한다.

    TR_ID: H0STCNT0 (KRX 단독) / H0NXCNT0 (NXT 단독) / H0UNCNT0 (KRX+NXT 통합) — 동일 포맷.
    KIS MCP 정본 (`ccnl_total`/`H0UNCNT0` 46 컬럼) — 본 함수는 fields[0]~[9],
    스코프 판별자 [27], 누적거래량 [13] 을 사용.

    payload 형식 (^ 구분, fields[0]~[9] + [13] + [27]):
      [0] 종목코드(MKSC_SHRN_ISCD) / [1] 체결시간(STCK_CNTG_HOUR, HHMMSS)
      [2] 현재가(STCK_PRPR) / [3] 전일대비구분 / [4] 전일대비
      [5] 등락률(PRDY_CTRT) / [6] 가중평균(WGHN_AVRG_STCK_PRC) / [7] 시가(STCK_OPRC)
      [8] 고가(STCK_HGPR) / [9] 저가(STCK_LWPR) / [13] 누적거래량(ACML_VOL)
      [27] 최고가시간(HGPR_HOUR)
    호출자 (`RiskManager.on_tick`): current_price + open_price + change_rate +
    day_high(cycle222-a, 키워드) + acml_vol(cycle227, 키워드) 전달.

    cycle222-a (2026-08-21) — `[8] 고가` 를 문서화만 해 두고 버리던 결함 시정.
    당일 고가를 넘기지 않으면 트레일링 앵커가 "수신된 틱들의 러닝 max" 로 퇴화해
    tick 미수신(blind) 구간의 고점이 영구 유실된다.

    cycle222-a2 (2026-08-21) — `[27] HGPR_HOUR` 로 그 고가를 **KRX 정규장 창으로
    스코프 필터**한다(`_parse_day_high`). 통합 채널의 일-스코프 필드는 09:00 에
    리셋되지 않아 NXT 프리장 체결이 누적된 채 MAIN 구간 틱에 계속 실려 오기
    때문이다(000250 실측). 창 밖 고가는 0(미관측)으로 강등하되 **틱은 살린다**.

    cycle227 (2026-08-25) — `[13] 누적거래량` 도 같은 부류의 결함이었다: BFB/VCP
    매수 게이트가 읽는 `ticker_prices["acml_vol"]` 에 대입하는 코드가 전체 소스에
    없어(P0-1) 두 전략이 구조적으로 매수 불가였다. `_parse_acml_vol` 로 파싱해
    `RiskManager.on_tick` → `tick_volume` 관측 모듈까지만 흘린다(`ticker_prices`
    주입은 donchian `ext_pct` 커플링 때문에 금지 — AST-1 가드).
    """
    fields = payload.split("^")
    if len(fields) < 10:
        # 사이클 102 (2026-06-11) — dispatch silent drop 가시화
        ticker = fields[0] if len(fields) >= 1 else "_unknown"
        _silent_drop_count[ticker] = _silent_drop_count.get(ticker, 0) + 1
        return

    ticker = fields[0]
    parsed = _parse_tick_prices(fields)
    if parsed is None:
        # 사이클 102 (2026-06-11) — 파싱 실패도 silent drop 누적
        _silent_drop_count[ticker] = _silent_drop_count.get(ticker, 0) + 1
        logger.debug("실시간 체결가 파싱 실패: payload=%s", payload[:140])
        return
    current_price, open_price = parsed
    # cycle222-a/a2 — 부가 관측. 파싱/스코프 판별 실패해도 틱은 버리지 않는다(0 폴백).
    day_high = _parse_day_high(fields)
    # cycle227 — 부가 관측(P0-1 시정 Stage 0). 파싱 실패해도 틱은 버리지 않는다
    # (-1 sentinel, fail-open — day_high 와 동일 원칙).
    acml_vol = _parse_acml_vol(fields)
    # cycle264 — 시가 스코프 shadow 관측. **행위 변경 0** (아래 어떤 값도 읽지 않고
    # 바꾸지 않는다). `_parse_tick_prices` 밖(= parsed 성공 뒤)이 배치 계약이고,
    # 헬퍼 자체가 never-raise 지만 monkeypatch·재정의 사고까지 막으려 한 겹 더 감싼다 —
    # 여기서 예외가 새면 `_on_tick` 과 같은 자리로 전파돼 **틱마다 WS 재연결**이다.
    try:
        _maybe_log_open_scope_observe(fields, open_price)
    except Exception:
        pass

    if open_price > 0:
        change_rate = (current_price - open_price) / open_price * 100
    else:
        change_rate = 0.0

    if _on_tick:
        try:
            await _on_tick(
                ticker, current_price, open_price, change_rate,
                day_high=day_high, acml_vol=acml_vol,
            )
        except Exception:
            logger.exception(
                "[callback_exception] handler=_on_tick ticker=%s", ticker,
            )
            raise  # 재연결 trigger 영속 (사이클 88 G-REJECT-1 영속)


async def _handle_execution(payload: str, *, encrypted: bool = False) -> None:
    """체결통보 메시지를 파싱한다.

    payload가 암호화된 경우 AES-256-CBC로 복호화 후 ^ 구분 필드를 파싱한다.
    """
    if encrypted and _aes_key and _aes_iv:
        try:
            payload = decrypt_aes_cbc(payload, _aes_key, _aes_iv)
        except Exception:
            logger.exception("체결통보 AES 복호화 실패")
            return

    # 체결통보 필드 파싱 (^ 구분)
    fields = payload.split("^")
    if len(fields) < 15:
        return

    # 필드 매핑 (KIS 체결통보 H0STCNI0/H0STCNI9 — KIS MCP 정본 `ccnl_notice` 26 컬럼,
    # cycle235 재검증으로 [9]/[16] 정정)
    # [0] CUST_ID(HTS ID), [1] ACNT_NO 계좌번호(8)+상품코드(2), [2] ODER_NO 주문번호,
    # [3] OODER_NO 원주문번호, [4] SELN_BYOV_CLS(02:매수, 01:매도), [5] RCTF_CLS 정정구분,
    # [6] ODER_KIND, [7] ODER_COND, [8] STCK_SHRN_ISCD 종목코드,
    # [9] **CNTG_QTY 체결수량(통보 건별 증분)**, [10] CNTG_UNPR 체결단가(사이클 161 정합),
    # [11] STCK_CNTG_HOUR, [12] RFUS_YN, [13] CNTG_YN(1:접수, 2:체결), [14] ACPT_YN,
    # [15] BRNC_NO, [16] **ODER_QTY 주문수량**, [17] ACNT_NAME, [18] ORD_COND_PRC ...
    # ⚠️ cycle235 (2026-08-29): 종전 주석이 [9]/[16] 를 정본과 반대로 적었고 코드가
    # 주석을 따라 fields[16](주문수량)을 체결수량으로 오독 — 단일 전량 체결에선
    # CNTG_QTY == ODER_QTY 라 잠복, 부분/분할 체결에서 positions 과대(257720 실사고:
    # 2주 주문·실체결 2주가 3주로 등록 → 익일 매도 전량 APBK0400). AST 가드가
    # fields[9] 소스를 봉인한다 (`test_cycle235_ast_execution_qty.py`).
    # 호출자 (`OrderEngine._handle_buy_fill`/`_handle_sell_fill`) 가 trade_history.price = CNTG_UNPR
    # 영구 정합 (사이클 161 영속 — 005940 6/16 BUY 50원 차이 시정).

    # 실전 환경에서 동일 HTS ID에 묶인 다른 계좌의 체결통보가 함께 푸시됨 → 대상 계좌만 처리
    target_account = (settings.kis_account_no or "").strip()
    recv_account = fields[1].strip() if fields[1] else ""
    if target_account and recv_account and not recv_account.startswith(target_account):
        logger.debug("체결통보 계좌 불일치 - 무시: 수신=%s, 대상=%s", recv_account, target_account)
        return

    order_no = fields[2]
    side = "BUY" if fields[4] == "02" else "SELL"
    exec_type = fields[13]  # 1:접수, 2:체결
    ticker = fields[8]
    price = int(fields[10]) if fields[10] else 0       # 체결단가
    quantity = int(fields[9]) if fields[9] else 0      # CNTG_QTY 체결수량 (정본, cycle235)

    # cycle329 — [16] ODER_QTY **주문수량**. 🔴 체결수량으로 쓰지 않는다
    # (그 오독이 257720 실사고이고 `test_cycle235_ast_execution_qty.py` 가 봉인한다).
    # 이 값이 필요한 이유 = `await place_order` 가 걸려 있는 동안 착지한 통보에는
    # `order_no` 매핑이 아직 없어 주문수량을 알 길이 **이 필드뿐**이다. 없으면
    # `ordered_qty` 가 증분 체결량으로 폴백돼 부분 체결이 전량으로 읽힌다.
    # 파싱 실패·필드 부재는 0(= 미제공)으로 두고 소비처가 현행 폴백을 탄다.
    try:
        ordered_qty_payload = int(fields[16]) if len(fields) > 16 and fields[16] else 0
    except (TypeError, ValueError):
        ordered_qty_payload = 0

    # 접수 통보(1)는 무시, 체결 통보(2)만 처리
    if exec_type != "2":
        logger.debug("체결통보 접수(미체결): order_no=%s, ticker=%s", order_no, ticker)
        return

    if not ticker or len(ticker) != 6 or not ticker.isalnum():
        logger.warning("체결통보 종목코드 이상(6자리 영숫자 아님): %s (fields=%s)", ticker, fields[:20])
        return

    if _on_execution:
        try:
            await _on_execution(
                ticker, order_no, side, price, quantity,
                ordered_qty_payload=ordered_qty_payload,
            )
        except Exception:
            logger.exception(
                "[callback_exception] handler=_on_execution ticker=%s order_no=%s",
                ticker, order_no,
            )
            raise


async def _handle_market_op(tr_id: str, tr_key: str, payload: str) -> None:
    """장운영정보(H0UNMKO0/H0STMKO0/H0NXMKO0) 메시지 — 보드 전환 + 종목별 VI/거래정지 이벤트.

    KIS 명세 기준 응답 필드(공통 — 통합/KRX/NXT 동일 구조):
      [0] TRHT_YN — 거래정지 여부
      [1] TR_SUSP_REAS_CNTT — 거래 정지 사유
      [2] MKOP_CLS_CODE — 장운영 구분 코드 (110/112/121/129...)
      [3] ANTC_MKOP_CLS_CODE — 예상 장운영 구분 코드
      [4] MRKT_TRTM_CLS_CODE — 임의연장구분코드
      [5] DIVI_APP_CLS_CODE — 동시호가배분처리구분코드
      [6] ISCD_STAT_CLS_CODE — 종목상태구분코드
      [7] VI_CLS_CODE — VI적용구분코드
      [8] OVTM_VI_CLS_CODE — 시간외단일가VI적용구분코드
      [9] EXCH_CLS_CODE — 거래소 구분코드 (KRX/NXT)

    사이클 26 영속 (대표 종목 005930 보드 전환 SessionTracker 호출) +
    사이클 149 (2026-06-16) 종목별 H0UNMKO0 구독 확장 시 record_market_op_event 호출.
    domain-expert 자문 산출물 `_workspace/domain_consult/cycle149_h0unmko0_per_ticker_subscription.md`.

    SessionTracker `_on_board` 콜백 분기 + 종목별 monitor record_market_op_event 분기
    모두 try/except 4중 영속 (사이클 102 G-REJECT-1 callback 예외 raise 영속).
    """
    fields = payload.split("^")
    mkop_cls_code = fields[2] if len(fields) > 2 else ""
    logger.info(
        "[%s] tr_key=%s, mkop_cls_code=%s, payload=%s",
        tr_id, tr_key, mkop_cls_code, payload[:140],
    )

    # 사이클 149 (2026-06-16) — 종목별 VI/거래정지 state 갱신.
    # 사이클 26 영속 = 005930 대표 구독 보드 전환 영역 보존 + 종목별 영역 확장.
    # 자문 의제 5 채택 = VI/거래정지/종목상태 이상 3 영역 통합.
    try:
        from src.api.market_operation import parse_market_op_payload
        from src.engine.market_operation_monitor import record_market_op_event

        event = parse_market_op_payload(tr_key, payload)
        record_market_op_event(event)
    except Exception:
        # graceful 영속 (사이클 88 G-REJECT 답습) — record 실패 시 보드 전환 영역 보호
        logger.exception(
            "[market_op_record_failed] tr_id=%s tr_key=%s graceful",
            tr_id, tr_key,
        )

    if _on_board:
        try:
            await _on_board(tr_key, mkop_cls_code, payload)
        except Exception:
            logger.exception(
                "[callback_exception] handler=_on_board tr_id=%s tr_key=%s",
                tr_id, tr_key,
            )
            raise


def flush_silent_drop_count() -> None:
    """5분 주기 collector flush — `[dispatch_drop_summary]` 1행 emit (사이클 74 답습).

    `_api_recovered_collector_loop` (scheduler.py) 에서 5분 주기 호출.
    empty collector 진입 시 emit 0 (no-op, Q2 빈 윈도우 skip 영속).
    """
    global _silent_drop_count
    if not _silent_drop_count:
        return
    drops_total = sum(_silent_drop_count.values())
    by_ticker = dict(_silent_drop_count)
    logger.info(
        "[dispatch_drop_summary] window=300s drops_total=%d by_ticker=%s",
        drops_total, by_ticker,
    )
    _silent_drop_count.clear()


def decrypt_aes_cbc(encrypted_text: str, key: str, iv: str) -> str:
    """AES-256-CBC 복호화."""
    cipher = Cipher(
        algorithms.AES(key.encode("utf-8")),
        modes.CBC(iv.encode("utf-8")),
    )
    decryptor = cipher.decryptor()
    decoded = base64.b64decode(encrypted_text)
    decrypted_padded = decryptor.update(decoded) + decryptor.finalize()

    unpadder = sym_padding.PKCS7(128).unpadder()
    decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
    return decrypted.decode("utf-8")
