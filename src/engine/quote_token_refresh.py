"""cycle269 (2026-09-08) — 보조 시세 계정 접근토큰 **장 마감 후 고정 시각 강제 재발급** leaf.

## 무엇을 고치는가 (원인 = 메인 세션 3일치 EC2 로그 실측 확정)

보조 시세 계정(quote pool) 7개의 "토큰 발급 완료" 시각이 매일 정확히 ~10분씩
앞으로 당겨져 왔다 — 09-06(토) 15:07~15:13 → 09-07(월) 14:58~15:04 →
09-08(화) 14:48~14:54. 자기 안정화가 없는 **단조 드리프트**라 방치하면 ~5주 뒤
장 시작 전으로 빠진다.

수학적 원인은 `src/auth/token.py::TokenManager._is_valid()` 의 선제 갱신 마진이다::

    return datetime.now() < self.token_expired - timedelta(minutes=10)

보조 계정은 하루 종일 시세 REST 에 쓰이므로 "만료 10분 전" 문턱에 닿는 즉시
다음 `get_token()` 이 `issue()` 를 트리거한다. 새 토큰의 만료는 *그 발급 시점*
+24h 인데 그 시점이 이론적 24h 지점보다 10분 이르다 ⇒ 매일 10분씩 누적 전진.

## 어떻게 고치는가

`token.py` 는 **한 글자도 고치지 않는다**(cycle269/270 시점의 계약 — 아래 서술은
그 시점 기록이다. **cycle296(2026-09-17)이 `token.py::TokenManager.issue()` 를
바꿨다** — 이 leaf 가 `revoke()`→`issue()` 로 만드는 61초 공백에 REST 가 들어와
또 KIS 를 치던 것(§1-5·아래 "왜 20:45 인가")을 매니저 단위 in-flight 합류로 막는
변경이며, 이 leaf 자체의 호출 패턴·`token.py` 내부 심볼 격리(G-270-2)는 그대로다).
**cycle270 정정 (2026-09-10)**: 이
절의 원래 서술("`issue()` 를 부르면 그 시각이 새 앵커")은 09-10 실측으로
반증됐다 — 09-09/09-10 이틀 강제 발급 7/7 이 매번 같은 날 장중 자연 재발급과
**완전히 동일한 만료**를 돌려받아 앵커가 한 번도 옮겨지지 않았다. KIS
`/oauth2/tokenP` 는 유효 토큰이 살아 있으면 **같은 토큰·같은 만료**를 돌려주기
때문이다(사용자 승인 하 09-10 17:13 fire 계정 1건 수동 실측이 유일한 반증 —
`revoke` 0.20s → `issue` 0.23s 로 만료가 실제로 옮겨갔다). 그래서 이제
`issue()` 앞에 `TokenManager.revoke()` 를 **계정 단위로 먼저** 호출해 앵커를
비운 뒤 발급한다 — 매일 **고정된 장외 시각**에 활성 보조 계정 전부를 대상으로
`revoke()`→`issue()` 페어를 순차 실행하면 그 시각이 매일 새 24h 창의 앵커가
된다. 자연 재발급(위 드리프트 경로)은 그 앵커 뒤에서 다시 앵커를 덮어쓰지
못한다. `revoke()` 실패는 `issue()` 시도를 막지 않는다(무토큰 방치 금지 =
fail-open) — 다만 그 계정만 이번 회차에 앵커가 그대로 남는다.

## 왜 20:45 인가 (cycle296, 2026-09-17 — 19:00 이 왜 틀렸는가)

**19:00(cycle270-C)은 조사 결과 틀렸다.** 09-15 실제 발급 21건, 09-16 14건(설계
7건/일) — 원인은 이 절이 세운 제약 (a) "T·T−10분이 모두 KRX 장중 밖" 이 **필요
조건이었지 충분조건이 아니었던 것**이다. 보조 시세 계정은 장외에도 **종일** REST
를 쓴다(5분 주기 stale 가드·15:40 NXT 애프터 등). 19:00 앵커의 다음 날 문턱
(T−10=18:50)이 그 REST 창 한복판에 있어, `TokenManager._is_valid()` 의 자연
재발급이 **항상 강제보다 먼저** 났다(09-16 실측 7/7 산술 일치 — ISA 문턱
18:51:25 → 실발화 18:55:03). 즉 T−10 창의 진짜 요건은 "장중 밖" 이 아니라
**"보조 풀 REST 가 없는 창"** 이다.

`issue()` 자체의 **in-flight 합류**(같은 매니저의 동시 `issue()` 호출이 KIS 를
한 번만 치도록, `src/auth/token.py` 사이클 296)가 이 중복 발급을 흡수하지만,
문턱마다 자연 재발급이 강제보다 먼저 나는 구조 자체는 T 를 옮기지 않으면
남는다 — 그래서 T 도 함께 옮긴다.

강제 재발급을 매일 T 에 걸면 정상 상태에서 자연 문턱은 **T − 10분**에 온다
(어제 T 에 발급 → 만료 오늘 T → 문턱 오늘 T−10분). 그 문턱 창이 **조용해야**
자연 재발급이 강제보다 먼저 나지 않는다.

09-16 실측(§1-5) — 20:2x~21:0x 보조 풀 REST **14행 균일**(5분 주기 로그뿐),
`quote_pool` REST 마커 20:00~21:30 **0건**. 일봉 적재(`TIME_STOCK_MASTER_DAILY_LOAD`
=20:30)는 20:31:50 종료(메인 계정) → **20:35~20:55 가 비어 있다**.

제약(재확인):
(a) T 와 T−10분이 모두 KRX 장중(09:00~15:30) 밖 — 필요조건, 위 이유로 불충분.
(b) 7계정 × 61s ≈ 7분의 직렬화 창이 REST 를 많이 쓰는 예정 작업과 겹치지 않을 것 —
    실측으로 재확인(20:2x~21:0x 보조 풀 REST 14행 균일, `quote_pool` 마커 0건).
(c) **T 는 스케줄러 task 루프의 생존 창 안**이어야 한다 — `scheduler.start()` 는
    정산(21:30 — cycle283 D3, 종전 20:10) → 로그 분석 → purge → `_reset_daily_state()` 뒤 본문이 끝나고
    `finally` 가 백그라운드 task(`_quote_token_refresh_task` 포함)를 전부 cancel 하며
    `_running = False` 가 된다. 그 뒤 시각은 **매일 0회 발화**한다(로그에는 부팅 시
    "scheduled at=" 한 줄만 남아 배선이 살아 있는 것처럼 보인다). T+15분 ≤ 21:30
    이 체인 지연(09-15 실측 최악 14분 40초)에도 정산 전 종료를 보장한다.

🔴 **정정 — 종전 문장 "20:00 이후는 루프 수명 구조를 바꾸지 않는 한 불가능하다
(20:00~정산 은 REST 집중 창이라 더 나쁘다)" 는 정산 20:10 시절 잔재였다.** 이
docstring 이 cycle283 D3 로 "정산(21:30)" 값은 갱신하면서 그 결론 문장은 안
고쳤다 — T 만 옮기고 이 문장을 두면 다음 사람이 읽고 19:00 으로 되돌린다.
정산이 21:30 인 지금은 20:00~21:30 이 **루프 안**이고, 20:00 자문·20:00:05
유니버스·20:05 metrics·20:30 일봉(≈20:32 종료) 뒤 **20:35~20:55 가 비어
있으며**, 21:30 정산까지 35분 여유가 있다.

20:45 는 아래 창을 전부 피한다(비충돌 실측, `test_c9`·`test_c10` 이 잠근다):
- 15:30 마감 / 16:00 일봉 / 16:10 basics / 16:15 purge / 16:20 funnel / 16:30 마스터 /
  16:40 재무 — 전부 문턱 20:35 이전에 끝난다(무관하게 이미 일찍 끝난다)
- 20:00 자문·유니버스·NXT 종료 / 20:05 metrics / 20:30 일봉(≈20:32 종료) / 21:30 정산 —
  전부 [T−10, T+8]=[20:35, 20:53] 창 밖(`test_c9` 전수 스캔)
- NXT 애프터(15:30~20:00)는 WS 기반이라 REST 시세 풀 부하가 작고, WS `approval_key` 는 별개 경로

⚠️ **첫 실행일 예외** — T 를 19:00 → 20:45 로 옮기는 첫날은 전날 앵커(19:0x)의
자연 문턱 18:50~18:59 에 자연 재발급 7건이 먼저 나고 20:45 강제 7건이 또 난다
= 그날 총 발급 14건(둘째 날부터는 문턱이 20:35 로 옮겨져 조용하므로 7건).
결함이 아니다 — `refresh_quote_tokens_once` 의 `window_issues_total`(아래 관측
③)은 그날도 창이 [T−15분, 종료] 라 **7** 이다(18:5x 는 창 밖).

## 안전 계약

- **대상은 보조 시세 계정뿐이다.** 주계정(`label=None`, 매매용)은 건드리지
  않는다 — 그 계정의 자연 재발급은 백엔드 재기동 시각에 묶여 있고 재기동은 D6
  (보유 중 장중 재시작 금지)로 이미 장외에만 일어난다.
- **매매 행위 영향 0.** 보조 계정은 주문에 쓰이지 않는다(시세 풀 전용).
  `risk.py` / `order_engine.py` / `api/order.py` / `realtime/**` / `auth/**` /
  전략 7파일 diff 0.
- **WebSocket 무영향.** WS 세션은 `access_token` 이 아니라 별도 엔드포인트
  `/oauth2/Approval` 이 주는 `approval_key` 로 접속·구독한다
  (`src/realtime/websocket.py:213` 이 connect 시 1회 발급 → `:603` 구독 프레임
  재사용). `issue()` 는 `access_token`/`token_expired`/캐시 파일만 갱신하고
  `_approval_key` 를 건드리지 않는다. 게다가 이 드리프트 경로의 자연 재발급이
  지금도 매일 일어나고 있으나 그로 인한 WS 장애 보고는 없다(3일치 로그 실측).
- **계정 단위 예외 흡수.** 한 계정의 발급 실패가 다음 계정을 막지 않는다
  (`_preissue_all_tokens()` 의 try/except 패턴 답습). `issue()` 는 HTTP 성공
  *후*에만 필드를 대입하므로 실패해도 기존 토큰이 살아 있다.
- **61초 직렬화를 우회하지 않는다.** `issue()` 내부의 모듈 전역 lock + 61s gap
  (KIS `/oauth2/tokenP` 분당 1개)을 그대로 탄다. 7계정 ≈ 7분은 **정상**이다.
- **`immediate_first_run=False`.** 부팅 직후 즉시 실행하면 (a) `_boot()` 의
  `_preissue_all_tokens()` 가 방금 캐시로 살린 토큰을 7분에 걸쳐 버리고
  (b) 그 부팅 시각이 새 앵커가 되어 "고정 장외 시각" 이라는 설계가 무너진다.
- **`write_log`/DB 를 쓰지 않는다** — `logger` 만 쓴다(cycle264 leaf 계약).
  단 `src/main.py::_DbLogHandler` 가 INFO 이상을 `system_logs` 로 올리므로
  아래 마커는 일일 리포트(21:30)에서도 조회된다.

## 관측 마커 (`[quote_token_refresh]`)

1. `scheduled at=...` — task 기동 시 1회. "배선이 살아 있는가" 의 카나리아.
2. `label=<label> issued expired=<만료시각> revoked=<True|False>` — 계정별
   성공 1행(**cycle270** — `revoked` 필드 추가, 접두는 byte 보존).
   `revoked=False` 면 `revoke()` 가 실패해 그 계정은 이번 회차에 앵커가
   이동하지 않았다는 뜻이다(별도 WARNING 도 동반).
3. `accounts=%d issued=%d failed=%d elapsed_s=%d window_issues_total=%d` — 회차
   요약 1행(`run_periodic_task_loop`). **cycle270 에서는 3필드가 불변이었으나
   cycle296 이 관측 2키를 덧붙였다**(`revoked` 는 여전히 요약에 없다 — 계정별
   행·WARNING 이 이미 잰다):
   - `elapsed_s` — 체인 총 소요(정상 ≈420s = 7계정×61s, 09-15 실측 최악 14분 40초).
   - `window_issues_total` — 체인 시작 **−15분**부터 종료까지 그 회차 매니저들의
     `issue_history`(`src/auth/token.py`, 리더 성공만 기록)에 실제로 남은 **모든**
     발급 수(강제분 + 자연 문턱분 합산). `issued`(강제분만)와 갈리면 그 즉시
     "문턱 창이 조용하지 않다"(R6) 또는 "합류 미작동" 이 드러난다. **왜 이 관측이
     필요한가** — 종전 3필드는 `issued=7 failed=0` 로 09-15 21건·09-16 14건 앞에서도
     **참**이었다(강제분만 셌기 때문). 산출 실패(더미·미래 매니저 교체 등)는
     `_trace_failure("window_count")` 흔적만 남기고 두 값 모두 0 — 관측이 체인을
     막지 않는다.

판독법: 배포 D+1(첫 실행일 제외) 부터 `[quote_token_refresh]` 요약이 매일
20:52~20:53 대에 `issued=7 window_issues_total=7 elapsed_s≈420~450` 로 1행씩
남고, 보조 계정의 "토큰 발급 완료(label=quote-*)" 가 20:35~20:53 창 밖에서는
더 이상 나오지 않아야 한다. **첫 실행일**(T 를 19:00→20:45 로 옮기는 그 날)은
전날 앵커의 자연 문턱 18:5x 에 7건이 먼저 나고 20:45 강제 7건이 또 나 하루
총 발급이 14건이다 — 결함이 아니다(위 "왜 20:45 인가" §첫 실행일 예외).
"""
from __future__ import annotations

import logging
import time as _time_mod
from datetime import time

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.task_loop_helper import run_periodic_task_loop

logger = logging.getLogger(__name__)

MARKER = "[quote_token_refresh]"

# 매일 강제 재발급 시각 (KST). 상단 "왜 20:45 인가" 참조 — T·T−10분이 보조 풀
# REST 가 없는 창이고(19:00 은 이 조건을 어겼다 — 문턱이 REST 창 한복판),
# **T 가 스케줄러 루프 생존 창(~`TIME_SETTLEMENT`, 현행 21:30) 안**이어야 한다.
# 이력: 15:45(cycle269) → 21:30(cycle270-B, 루프 밖이라 무발화) → 19:00(cycle270-C,
# 2026-09-10, 문턱이 보조 풀 REST 창과 겹쳐 09-15 21건/09-16 14건 중복 발급) →
# 20:45(cycle296, 2026-09-17 — 사용자 확정값, 문턱 20:35 는 보조 풀 REST 0건).
TIME_QUOTE_TOKEN_REFRESH = time(20, 45)

# `run_periodic_task_loop` 로그 prefix. 신선도 마커(`immediate_skip_if_fresh_hours`)를
# 쓰지 않으므로 `system_config` 접근은 0건이다.
TASK_LABEL = "quote_token_refresh"

_SUMMARY_KEYS = ("accounts", "issued", "failed", "elapsed_s", "window_issues_total")
_SUMMARY_LOG_FORMAT = (
    MARKER + " accounts=%d issued=%d failed=%d elapsed_s=%d window_issues_total=%d"
)

# cycle296 — `window_issues_total` 창 하한 = 체인 시작(`t0`) − 15분. 첫 실행일의
# 문턱(T−10)과 정상일 문턱(T−10=20:35)을 둘 다 덮는다. `_ISSUE_JOIN_TIMEOUT_SECS`
# 류의 리스크 다이얼이 아니라 관측 창 폭이라 system_config 편입 없음.
_WINDOW_LOOKBACK_SECS = 900.0

# 관측기 자기 실패 흔적 cap — WARNING 1회/(marker, label)/일 (cycle258 카드 #5).
_emit_cap: KstDailyEmitCap = KstDailyEmitCap()


def _trace_failure(key: str) -> None:
    """관측 emit 자신의 실패 흔적. never-raise (무흔적 `pass` 금지)."""
    try:
        from src.engine.observer_trace import trace_observer_failure

        trace_observer_failure(MARKER, key, _emit_cap, dest_logger=logger)
    except Exception:  # pragma: no cover — 2차 예외도 흡수
        pass


def _emit_issued(label: str, expired, revoked: bool) -> None:
    """계정별 성공 1행. 로그 실패가 다음 계정 발급을 막으면 안 된다."""
    try:
        logger.info(
            "%s label=%s issued expired=%s revoked=%s", MARKER, label, expired, revoked
        )
    except Exception:
        _trace_failure(label)


async def refresh_quote_tokens_once() -> dict:
    """활성 보조 시세 계정 전부의 접근토큰을 **강제** 재발급한다.

    `get_token()`(유효하면 캐시 반환)이 아니라 `issue()` 를 부른다 — 이 호출의
    목적이 "토큰을 쓸 수 있게 하는 것" 이 아니라 **만료 앵커를 이 시각으로
    옮기는 것**이기 때문이다.

    cycle296 — 반환 dict 에 관측 2키(`elapsed_s`/`window_issues_total`)가
    늘었다. 계정 목록 조회 실패·활성 계정 0건 조기 return 경로도 **항상 5키**를
    돌려준다 — 3키만 돌려주면 `run_periodic_task_loop._build_log_args` 의
    `summary.get(key, 0)` 폴백에 가려져 "측정했더니 0" 과 "측정조차 안 함" 이
    구별되지 않는다.

    Returns:
        `{"accounts": 조회된 활성 계정 수, "issued": 성공 수, "failed": 실패 수,
        "elapsed_s": 체인 총 소요(초, monotonic), "window_issues_total": 체인
        시작 −15분부터의 그 라벨들 전체 발급 수}`.
        계정 목록 조회 자체가 실패하면 전부 0 인 dict (회차 skip, 예외 미전파).
    """
    # cycle296 — `token.py` 는 naive `datetime.now()`(컨테이너 TZ=KST)를 쓰고 이
    # leaf 는 KST aware 를 쓸 수 있어 섞이면 9시간이 어긋난다. 창 산술만
    # 필요하므로 tz 개념이 없는 monotonic 을 쓴다.
    t0 = _time_mod.monotonic()
    summary = {
        "accounts": 0, "issued": 0, "failed": 0,
        "elapsed_s": 0, "window_issues_total": 0,
    }

    try:
        from src.db import kis_quote_accounts as kqa

        accounts = await kqa.list_accounts(active_only=True)
    except Exception:
        logger.exception("%s 보조 계정 목록 조회 실패 — 이번 회차 skip", MARKER)
        return summary

    summary["accounts"] = len(accounts)
    if not accounts:
        logger.info("%s 활성 보조 계정 0건 — 재발급 대상 없음", MARKER)
        return summary

    from src.auth.token import get_token_manager

    # cycle296 — 회차 매니저를 모아 뒀다가 종료 시 `issue_history`(공개 속성,
    # 리더 성공만 기록)를 읽어 `window_issues_total` 을 산출한다. 계정 처리
    # 도중 revoke/issue 가 실패해도 매니저 자체는 이미 확보돼 있으므로 그대로
    # 집계 대상에 남는다.
    managers_used: list = []

    for account in accounts:
        label = getattr(account, "label", None)
        # 주계정 무접촉 계약의 **코드 레벨** 방어. `get_token_manager(None)` 은 매매용
        # 메인 매니저를 돌려주므로, label 이 비어 오면(스키마상 NOT NULL 이지만 조회
        # 계층이 바뀔 수 있다) 그 계정을 건너뛴다 — 조용히 넘기지 않고 WARNING 을 남긴다.
        if not label:
            summary["failed"] += 1
            logger.warning("%s label 이 비어 있어 skip — 주계정 무접촉 계약", MARKER)
            continue
        try:
            manager = await get_token_manager(label)
            managers_used.append(manager)

            # KIS `/oauth2/tokenP` 는 유효 토큰이 있으면 같은 토큰·같은 만료를
            # 돌려준다(cycle270, 09-10 실측) — issue() 단독으로는 앵커가 안
            # 옮겨진다. revoke() 로 먼저 비운다. 실패해도 issue() 는 시도한다
            # (무토큰 방치 금지 = fail-open 방향) — 그 계정만 앵커가 그대로 남는다.
            revoked = True
            try:
                await manager.revoke()
            except Exception:
                revoked = False
                logger.warning(
                    "%s label=%s 토큰 폐기 실패 — 발급은 계속 시도, "
                    "이번 회차 앵커는 이동하지 않음",
                    MARKER, label,
                )

            # 강제 발급. 내부 전역 lock + 61s gap 직렬화(+ cycle296 in-flight
            # 합류)를 그대로 탄다.
            await manager.issue()
            summary["issued"] += 1
            _emit_issued(str(label), getattr(manager, "token_expired", None), revoked)
        except Exception:
            summary["failed"] += 1
            logger.exception(
                "%s label=%s 강제 재발급 실패 — 다음 계정으로 진행", MARKER, label
            )

    # cycle296 — 관측 2키 산출. 실패해도 체인 결과(`issued`/`failed`)는 이미
    # 확정돼 있으므로 흔적만 남기고 두 값을 0 으로 내린다(관측은 hot path 밖).
    try:
        elapsed_s = int(_time_mod.monotonic() - t0)
        since = t0 - _WINDOW_LOOKBACK_SECS
        window_issues_total = sum(
            1
            for mgr in managers_used
            for ts in getattr(mgr, "issue_history", ())
            if ts >= since
        )
    except Exception:
        _trace_failure("window_count")
        elapsed_s = 0
        window_issues_total = 0

    summary["elapsed_s"] = elapsed_s
    summary["window_issues_total"] = window_issues_total
    return summary


async def task_loop(sched) -> None:
    """매일 `TIME_QUOTE_TOKEN_REFRESH` 에 1회 발화하는 lifecycle 루프.

    `run_periodic_task_loop`(사이클 134) 재사용 — `advance_if_passed=True` 폭주
    차단 · `CancelledError` break · 예외 후 60s 재시도가 이미 검증돼 있다.
    metrics collector 가 없는 task 이므로 `record_fn`/`flush_fn` 은 no-op 이다.
    """
    try:
        logger.info(
            "%s scheduled at=%02d:%02d (KST) — 보조 시세 계정 접근토큰 강제 재발급",
            MARKER, TIME_QUOTE_TOKEN_REFRESH.hour, TIME_QUOTE_TOKEN_REFRESH.minute,
        )
    except Exception:
        _trace_failure("scheduled")

    await run_periodic_task_loop(
        scheduler=sched,
        task_label=TASK_LABEL,
        wait_time=TIME_QUOTE_TOKEN_REFRESH,
        once_callable=refresh_quote_tokens_once,
        record_fn=lambda _summary: None,
        flush_fn=lambda: None,
        summary_log_format=_SUMMARY_LOG_FORMAT,
        summary_keys=_SUMMARY_KEYS,
        immediate_first_run=False,
    )
