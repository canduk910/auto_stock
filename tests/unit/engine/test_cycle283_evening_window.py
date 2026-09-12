"""cycle283 Red — 저녁 창 재설계 (봉 확정 20:00 · 일봉 적재 20:30 · 세션 종료 21:30).

정본 = 사용자 확정 결정 D1~D8 (2026-09-11) + `src/engine/CLAUDE.md` session.py 절(09-14 제도 변경).

## 왜 (실측)
2026-09-11(금) 16:05 배포 재기동 → 16:14 즉시 적재가 **1,005종목의 오늘 봉**을 저장 →
18:10 정기가 908종목을 `skipped_fresh` 로 건너뜀. 그 1,005종목의 금요일 **거래량이
부분값**이다(16:14 저장분 vs 18:45 재조회 40종목: 중앙값 **+0.51%**, 평균 +1.61%,
최대 **+13.97%**(현대차), 25%가 1% 이상). 일봉 OHLC 는 15:30 확정이지만 거래량·거래
대금은 **시간외 거래 동안 계속 증가**한다(6종목 전수 실측).

2026-09-14(월)부터 KRX 애프터마켓(16:00~20:00 실시간 체결)이 신설되고 시간외 단일가가
폐지된다 ⇒ 그날 거래가 **20:00** 에 끝난다 ⇒ 18:10 적재는 **매일** 부분값을 담는다.

## 순서 불변식 (이 사이클의 정체성)
    cutoff(20:00) ≤ 적재(20:30) < 정산(21:30)
`cutoff > 적재` 면 정기 적재가 오늘 봉을 **영원히 못 쓴다**(적대 검증 실증: cutoff
20:00 + 적재 18:10 이면 cycle263 스위트가 11 failed).

## 계약 (C1~C6, C10~C12)
- C1 `scanner._DAILY_LOAD_TODAY_BAR_CUTOFF = time(20, 0)` — **판정식은 byte 동일**,
  scanner 지역 상수 유지(scheduler 시각 재사용 금지 = cycle263 C5 원칙 불변).
- C2 `scheduler.TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` + 이웃 주석 3곳 정직화.
- C3 `scheduler.TIME_SETTLEMENT = time(21, 30)`.
- C4 신규 `TIME_SESSION_START_CUTOFF = time(20, 0)` — `start()` 기동 거부와 `run_daily`
  일자 전환이 **둘 다** 이 상수를 쓴다.
- C5 신규 `TIME_METRICS_SNAPSHOT = time(20, 5)` + `start()` 배선(자문 뒤 · 정산 앞).
- C6 `scheduler.py` < **3,900L**(cycle257 영구 상한 — 브리프의 `< 4,000` 은 그 시점의 오해였고 자매 가드 7곳이 3,900 을 복창한다. 두 수가 갈라지면 **더 조인 쪽**이 정본).

## 🔴 C4 의 실패 서술 정정 (도메인 자문 2026-09-11)
브리프는 "`:1081` 을 빠뜨리면 tight spin" 이라고 적었는데 **사실이 아니다**.
`run_daily` 루프 본문 끝에 `await asyncio.sleep(60)`(정산 직후 재시작 방지)이 무조건
실행되므로 그것은 **60초 주기 재시도 루프**다. 실제 피해는 CPU 가 아니라:
  20:00~21:30 = 90분 × ~90회 × {auto_start DB 조회 + `token_manager.get_token()` +
  KIS 휴장일 API(`chk-holiday`) + `start()` 즉시 거부 → `logger.warning` +
  `write_log("WARNING", "장 종료 후 시작 시도 — 거부됨")`}
⇒ **WARNING 90행이 그날 21:30 리포트의 `level_counts` 를 오염**시키고 KIS 휴장일 API 가
90회 불린다. 처방(두 지점이 같은 상수)은 그대로 유효하다 — 틀린 근거로 가드를 세우면
다음 사람이 가드를 지운다.

## Red 유효성
- C1/C2/C3 — 현행 값(15:40 / 18:10 / 20:10)이라 값 단언 FAIL.
- C4/C5 — 상수 부재 → `AttributeError` / AST 탐색 실패.
- 문서 — 현행 문서가 옛 값을 말하므로 FAIL.
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, time, timedelta
from pathlib import Path

import pytest

import src.engine.scanner as scanner
import src.engine.scheduler as sched

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHED_SRC = Path(inspect.getfile(sched)).read_text(encoding="utf-8")
_SCANNER_SRC = Path(inspect.getfile(scanner)).read_text(encoding="utf-8")

_CUTOFF = time(20, 0)
_DAILY_LOAD = time(20, 30)
_SETTLEMENT = time(21, 30)
_START_CUTOFF = time(20, 0)
_SNAPSHOT = time(20, 5)


def _fn(src: str, name: str) -> ast.AST:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"함수 `{name}` 를 찾지 못했다")


def _segment(src: str, name: str) -> str:
    return ast.get_source_segment(src, _fn(src, name)) or ""


def _line_of(src: str, needle: str) -> str:
    """`needle` 을 포함하는 첫 줄 전체(주석 포함)를 돌려준다."""
    for line in src.splitlines():
        if needle in line:
            return line
    raise AssertionError(f"`{needle}` 가 소스에 없다")


# ===========================================================================
# C1 — scanner 커트오프 20:00 (판정식 byte 동일)
# ===========================================================================

def test_c283_1_cutoff_constant_is_2000():
    """`_DAILY_LOAD_TODAY_BAR_CUTOFF = time(20, 0)` (D1)."""
    assert scanner._DAILY_LOAD_TODAY_BAR_CUTOFF == _CUTOFF, (
        f"실측 {scanner._DAILY_LOAD_TODAY_BAR_CUTOFF} — 15:40 이면 09-14 이후 "
        "**매일** 부분 거래량 봉을 확정봉으로 받아들인다"
    )


def test_c283_1b_decision_expressions_are_byte_identical():
    """C1 — 값만 바뀌고 **판정 로직은 손대지 않는다**.

    이 사이클은 "언제부터 오늘 봉을 믿을 것인가" 만 옮긴다. 판정식을 같이 건드리면
    cycle263 이 세운 세 성질(시각 단독 판정 · 시계 왜곡 방어 · 파싱 실패 fail-open)이
    한꺼번에 회귀 위험에 들어간다. 그 성질들의 회귀는
    `test_cycle263_daily_load_stub_filter.py` 가 잡지만, 여기서는 **텍스트 동일성**을
    직접 못 박아 "값 변경 사이클" 의 경계를 만든다.
    """
    for expr in (
        "drop_from_today = now_kst.time() < _DAILY_LOAD_TODAY_BAR_CUTOFF",
        "drop = bas_dd >= today_ymd if drop_from_today else bas_dd > today_ymd",
    ):
        assert expr in _SCANNER_SRC, f"판정식이 바뀌었다: {expr!r}"


def test_c283_1c_cutoff_rationale_comment_is_rewritten():
    """C1(a)(b) — 근거 주석이 09-14 애프터마켓으로 교체된다.

    현행 주석은 "KRX 마감 15:30 + 마감 동시호가 흡수 10분" 이다. 값만 20:00 으로 바꾸고
    이 근거를 남기면 다음 사람이 "왜 20:00 인데 마감 동시호가를 말하나" 로 **되돌린다**.
    """
    head = _SCANNER_SRC.split("_DAILY_LOAD_TODAY_BAR_CUTOFF = ")[0]
    tail_comment = head[head.rfind("# 사이클 263"):] if "# 사이클 263" in head else head[-800:]
    assert "마감 동시호가 흡수 10분" not in tail_comment, (
        "15:40 을 정당화하던 근거 주석이 그대로 남아 있다 — 값과 근거가 어긋나면 "
        "다음 사람이 값을 되돌린다"
    )
    assert "애프터마켓" in tail_comment, (
        "20:00 의 근거(09-14 KRX 애프터마켓 16:00~20:00 종료)가 주석에 없다"
    )


def test_c283_1d_drop_today_bars_docstring_states_the_new_rule():
    """C1(a) — `_drop_today_bars` docstring 의 규칙 2행이 값을 박아 두고 있다."""
    doc = ast.get_docstring(_fn(_SCANNER_SRC, "_drop_today_bars")) or ""
    assert "15:40" not in doc, (
        f"docstring 이 옛 커트오프 15:40 을 규칙으로 적는다 — 코드와 어긋난다\n{doc}"
    )
    assert "20:00" in doc, "docstring 이 새 규칙(20:00)을 적지 않는다"


def test_c283_1e_marker_warning_says_three_generations():
    """C1(c) — `[daily_load_today_bar_filter] mode=` 의미가 **세 번째로** 바뀐다.

    원본 / cycle263 / cycle283 — 15:40~20:00 구간 실행의 `mode` 가 keep → **drop** 으로
    뒤집힌다. 주석의 기존 "배포 전후 로그 합산 금지" 경고는 2세대 기준이라 부족하다.
    """
    idx = _SCANNER_SRC.find("[daily_load_today_bar_filter]")
    assert idx > 0
    around = _SCANNER_SRC[max(0, idx - 1200):idx]
    assert "3세대" in around or "세 세대" in around or "cycle283" in around, (
        "마커 의미 반전 경고가 여전히 2세대 기준이다 — `dropped_rows`/`tickers_affected` "
        "까지 세대 간 합산 불가라는 사실을 적어야 한다"
    )


def test_c283_1f_cutoff_is_still_scanner_local():
    """C1 — scanner 는 여전히 scheduler 시각 상수를 재사용하지 않는다(cycle263 C5)."""
    for name in ("TIME_POST_NXT_OPEN", "TIME_STOCK_MASTER_DAILY_LOAD",
                 "TIME_NXT_POST_CLOSE", "TIME_SESSION_START_CUTOFF"):
        assert name not in _SCANNER_SRC, (
            f"C5 위반 — scanner 가 scheduler 시각 상수 `{name}` 를 쓴다. 매수 보드 시각 "
            "변경이 적재 규약을 딸려 바꾼다"
        )


# ===========================================================================
# C2 — 일봉 적재 20:30 + 이웃 주석 정직화
# ===========================================================================

def test_c283_2_daily_load_is_2030():
    assert sched.TIME_STOCK_MASTER_DAILY_LOAD == _DAILY_LOAD


def test_c283_2b_daily_load_comment_no_longer_claims_1810():
    line = _line_of(_SCHED_SRC, "TIME_STOCK_MASTER_DAILY_LOAD = time(")
    assert "18:10" not in line, f"주석이 옛 18:10 을 말한다: {line}"
    assert "시간외 단일가" not in line, (
        "09-14 부터 시간외 단일가(16:00~18:00)는 **폐지**된다 — 그 근거를 남기면 "
        "다음 사람이 18:10 으로 되돌릴 논거를 준다"
    )
    assert "애프터마켓" in line, "20:30 의 근거(애프터마켓 20:00 종료)가 주석에 없다"


@pytest.mark.parametrize(
    "const,stale",
    [
        ("TIME_STOCK_MASTER_BASICS_REFRESH", "18:10"),
        ("TIME_STOCK_MASTER_DAILY_PURGE", "16:00"),
        ("TIME_EVENING_FUNNEL_CAPTURE", "18:10"),
    ],
)
def test_c283_2c_neighbour_comments_are_honest(const, stale):
    """C2 보완 — 같은 블록에서 18:10/16:00 을 전제한 주석 3곳이 거짓이 된다.

    - `:67` basics: "cycle273f 부터 일봉(18:10)보다 먼저 돈다"
    - `:70` purge: "일봉 task 16:00 적재 직후 15분 마진" — cycle273f 로 이미 거짓이었고
      이제 **4시간 15분 앞**이 된다(적재보다 앞선다는 사실 자체를 적어야 한다)
    - `:71` funnel: "일봉은 18:10 이라 이 캡처는 전일 봉 기준"

    ⚠️ 16:20 funnel 캡처의 **행위는 불변**이다 — 적재가 더 뒤로 갔을 뿐 여전히 전일 봉
    기준이고, 전략의 `prev_idx` 가 날짜 비교라 결과가 같다. 고칠 것은 서술뿐이다.
    """
    line = _line_of(_SCHED_SRC, f"{const} = time(")
    assert stale not in line, f"`{const}` 주석이 옛 값 `{stale}` 을 전제한다: {line}"


# ===========================================================================
# C3/C4 — 정산 21:30 · 기동 거부 경계 분리
# ===========================================================================

def test_c283_3_settlement_is_2130():
    assert sched.TIME_SETTLEMENT == _SETTLEMENT


def test_c283_4_session_start_cutoff_constant_exists():
    """C4 — 기동 거부 경계를 `TIME_SETTLEMENT` 에서 **분리**한다(D4).

    분리하지 않으면 정산 21:30 이 곧 기동 거부 경계가 되어 20:00~21:30 재기동이 세션을
    시작하고, `_wait_until(advance_if_passed=False)` 가 지난 시각에 즉시 반환하므로
    그날 순서를 통째로 훑으며 **20:00 AI 자문과 `auto_apply_recommendations` 를
    재실행**한다. 현재 그 창은 10분이고, 분리하지 않으면 90분이 된다.
    """
    assert hasattr(sched, "TIME_SESSION_START_CUTOFF"), (
        "신규 상수 `TIME_SESSION_START_CUTOFF` 부재 (C4)"
    )
    assert sched.TIME_SESSION_START_CUTOFF == _START_CUTOFF


def test_c283_4b_start_reject_and_run_daily_share_the_constant():
    """C4 핵심 — `start()` 기동 거부와 `run_daily` 일자 전환이 **같은 상수**를 쓴다.

    🔴 `run_daily` 쪽을 빠뜨리면: run_daily 가 "아직 장 종료 전" 으로 보고 `start()` 를
    부르는데 `start()` 는 즉시 거부한다. 루프 본문 끝 `await asyncio.sleep(60)` 때문에
    tight spin 은 아니고 **60초 주기 재시도**다 — 20:00~21:30 동안 약 90회.
    회당 비용 = auto_start DB 조회 + `token_manager.get_token()` + KIS 휴장일 API +
    WARNING 2행(logger + `write_log`). 그 WARNING 90행이 같은 날 21:30 리포트의
    `level_counts` 를 통째로 오염시킨다.
    """
    start_seg = _segment(_SCHED_SRC, "start")
    run_seg = _segment(_SCHED_SRC, "run_daily")

    assert "TIME_SESSION_START_CUTOFF" in start_seg, (
        "`start()` 의 기동 거부 비교가 새 상수를 쓰지 않는다"
    )
    assert "TIME_SESSION_START_CUTOFF" in run_seg, (
        "`run_daily` 의 '이미 장 종료면 내일로' 판정이 새 상수를 쓰지 않는다 — "
        "두 지점이 갈리면 20:00~21:30 에 60초 주기 헛 재시도 ~90회"
    )

    # 두 지점 모두에서 `>= TIME_SETTLEMENT` 형태의 기동 거부 비교가 남으면 안 된다.
    for seg, label in ((start_seg, "start()"), (run_seg, "run_daily")):
        tree = ast.parse(seg)
        bad = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.Compare)
            and any(
                isinstance(c, ast.Attribute) and c.attr == "TIME_SETTLEMENT"
                or isinstance(c, ast.Name) and c.id == "TIME_SETTLEMENT"
                for c in [n.left, *n.comparators]
            )
            and any(isinstance(op, (ast.GtE, ast.Gt)) for op in n.ops)
        ]
        assert not bad, (
            f"{label} 에 `>= TIME_SETTLEMENT` 형태의 기동 거부 비교가 남아 있다 — "
            "정산 시각이 기동 거부 경계를 겸하면 D4 분리가 무의미하다"
        )


def test_c283_4c_rejection_log_names_the_constant_and_the_cost():
    """C4 — 거부 로그가 **무엇을 잃었는지** 말한다(운영자용).

    `[account_risk_watch_loop_died]` 의 공식 복구 절차가 `POST /api/trading/restart`
    인데 그 창(20:00~21:30, 종전 10분)에서 막힌다. 조용히 거부하면 운영자는 자기가
    그날 20:30 일봉 적재를 잃었다는 사실을 모른다.
    """
    start_seg = _segment(_SCHED_SRC, "start")
    idx = start_seg.find("장 종료 후")
    assert idx > 0, "거부 로그 문구를 찾지 못했다"
    around = start_seg[max(0, idx - 400): idx + 600]
    assert "TIME_SESSION_START_CUTOFF" in around, "거부 로그가 새 상수명을 인용하지 않는다"
    # 잃는 것은 일봉만이 아니다 — `_settle()`·일일 리포트·retention 이 전부
    # `TIME_SETTLEMENT` **뒤**에 있어 `start()` 거부 한 번에 넷이 함께 사라진다.
    # '일봉' 단일 키워드만 검사하면 그 사실이 로그에서 조용히 빠져도 초록이다.
    for token in ("20:30", "일봉", "_settle", "retention"):
        assert token in around, (
            f"거부 로그가 잃는 것 `{token}` 을 말하지 않는다 — 20:00~21:30 재기동은 "
            "20:30 일봉 적재 · _settle(daily_performance) · 일일 로그 분석 · 로그 "
            "retention 을 **한꺼번에** 잃는다"
        )
    assert "recompute" in around or "refresh" in around, (
        "거부 로그에 복구 경로(daily/refresh · performance/recompute)가 없다"
    )


def test_c283_4d_start_docstring_distinguishes_two_boundaries():
    """C4 — `start()` docstring 의 단계 표가 두 경계를 구분해 쓴다.

    현행 2행("15:20~20:10: NXT 애프터 단계" / "20:10 이후: 장 종료, 시작 불가")은 D4
    분리 뒤 **거짓**이다. 기동 거부(20:00)와 정산(21:30)은 이제 다른 시각이다.
    """
    doc = ast.get_docstring(_fn(_SCHED_SRC, "start")) or ""
    assert "20:10" not in doc, f"docstring 이 옛 20:10 경계를 말한다\n{doc}"
    assert "20:00" in doc and "21:30" in doc, (
        "docstring 이 두 경계(기동 거부 20:00 / 정산 21:30)를 구분해 적지 않는다"
    )


def test_c283_4e_trading_routes_availability_window_is_documented():
    """C4 보완 — `/api/trading/start`·`/restart` 의 가용 창이 90분 좁아진다.

    두 라우트는 같은 `scheduler.start()` 를 부른다. 상수를 공유시킬 필요는 없지만
    **문서에는 반드시 적어야 한다** — `[account_risk_watch_loop_died]` 의 문서화된
    복구 절차가 그 창에서 막히고, `/restart` 는 `stop()` 을 먼저 부르므로 시스템이
    정지 상태로 남을 수 있다.
    """
    text = (_REPO_ROOT / "src" / "routes" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "20:00~21:30" in text, (
        "`src/routes/CLAUDE.md` 에 기동 거부 창(20:00~21:30) 서술이 없다 — "
        "그 창의 `POST /api/trading/start|restart` 는 거부된다"
    )


# ===========================================================================
# C5 — metrics 1차 스냅샷 20:05
# ===========================================================================

def test_c283_5_metrics_snapshot_constant_is_2005():
    """C5/D5 — `api_metrics` 와 `strategy_funnel` 은 **메모리 전용**이다.

    프로세스가 죽으면 DB 로 복구 불가이고, 정산을 21:30 으로 밀면 그 유실 노출이
    10분 → 90분이 된다. 20:05 에 한 번 저장해 5분으로 줄인다.
    """
    assert hasattr(sched, "TIME_METRICS_SNAPSHOT"), "신규 상수 `TIME_METRICS_SNAPSHOT` 부재"
    assert sched.TIME_METRICS_SNAPSHOT == _SNAPSHOT


def test_c283_5b_snapshot_wiring_sits_between_advice_and_settlement():
    """C5 — `_wait_until` 호출 순서: … NXT_POST_CLOSE → METRICS_SNAPSHOT → SETTLEMENT.

    위치가 자문/`auto_apply` 블록 **뒤**여야 자문 실행분까지 스냅샷에 담기고,
    정산 **앞**이어야 유실 창이 실제로 5분으로 줄어든다.
    """
    seg = _segment(_SCHED_SRC, "start")
    tree = ast.parse(seg)
    # ⚠️ `ast.walk` 는 BFS 라 **소스 순서를 보장하지 않는다** — 반드시 `lineno` 로 정렬한다.
    #    (정렬 없이 쓰면 이 테스트가 "배선 순서" 가 아니라 "AST 트리 모양" 을 재게 된다.)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "_wait_until" and node.args:
            a = node.args[0]
            if isinstance(a, ast.Name):
                found.append((node.lineno, a.id))
    order = [name for _ln, name in sorted(found)]
    assert "TIME_METRICS_SNAPSHOT" in order, (
        f"`start()` 에 `_wait_until(TIME_METRICS_SNAPSHOT)` 배선이 없다 (실측 {order})"
    )
    i_snap = order.index("TIME_METRICS_SNAPSHOT")
    assert "TIME_NXT_POST_CLOSE" in order and order.index("TIME_NXT_POST_CLOSE") < i_snap, (
        f"스냅샷이 20:00 자문 블록보다 앞이다 (실측 순서 {order})"
    )
    assert "TIME_SETTLEMENT" in order and i_snap < order.index("TIME_SETTLEMENT"), (
        f"스냅샷이 정산보다 뒤다 — 유실 창이 줄지 않는다 (실측 순서 {order})"
    )


def _calls_in(node: ast.AST, name: str) -> bool:
    """`node` 안에서 `name` 을 호출하는 `Call` 노드가 있는가 (Name/Attribute 양쪽)."""
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Name) and f.id == name:
            return True
        if isinstance(f, ast.Attribute) and f.attr == name:
            return True
    return False


def test_c283_5c_snapshot_call_is_graceful():
    """C5 — 스냅샷 실패가 정산을 막지 않는다 (**전용** try/except 로 감싼 호출).

    ⚠️ 후보를 `ast.walk` 로 훑어 "dump 에 snapshot 이 들어간 Try" 로 잡으면 `start()`
    전체를 감싼 **상위 try** 가 그 조건을 만족해 버린다(적대 검증 M29 ESCAPED — 전용
    try 를 통째로 지워도 초록이었다). 상위 try 로 새면 1차 저장 실패가 그날 `_settle()`
    이하 정산 블록 전체를 건너뛰게 만든다 = C5 가 막으려던 바로 그 결과.

    그래서 후보를 **"스냅샷 호출을 담되 정산 블록은 담지 않는 Try"** 로 좁힌다 —
    상위 try 는 `_settle()`·`generate_daily_log_report()` 를 같은 body 에 담고 있으므로
    이 조건에서 자동으로 탈락한다(전용 try 를 지우면 후보가 0 이 되어 붉어진다).
    """
    seg = _segment(_SCHED_SRC, "start")
    tree = ast.parse(seg)
    dedicated = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Try) and n.handlers
        and _calls_in(n, "run_daily_metrics_snapshot")
        and not _calls_in(n, "_settle")
        and not _calls_in(n, "generate_daily_log_report")
    ]
    assert dedicated, (
        "1차 스냅샷 호출을 **전용** try/except 로 감싸지 않았다 — 상위 try 가 받으면 "
        "1차 저장 실패 한 번이 그날 정산 블록(`_settle`·일일 리포트·retention) 전체를 "
        "건너뛰게 만든다(= C5 가 막으려던 결과 그 자체)"
    )


def test_c283_5d_snapshot_avoids_the_token_refresh_window_and_all_timeslots():
    """C5 제약 ① — 토큰 재발급 직렬화 창 `[18:50, 19:08]` 밖 + `TIME_*` 충돌 0.

    신규 상수 2개가 `TIME_` 접두라 `vars(sched)` 를 훑는 기존 충돌 가드 2곳
    (`test_cycle269::test_c9` 창 [18:50,19:08] · `test_cycle273::test_g273f_2`
    창 [20:30,20:40])에 **자동 편입**된다 — 20:00·20:05 는 두 창 어디에도 없다.
    """
    from src.engine.quote_token_refresh import TIME_QUOTE_TOKEN_REFRESH as T

    base = datetime(2026, 9, 14)
    t_dt = base.replace(hour=T.hour, minute=T.minute)
    lo, hi = (t_dt - timedelta(minutes=10)).time(), (t_dt + timedelta(minutes=8)).time()
    for name in ("TIME_METRICS_SNAPSHOT", "TIME_SESSION_START_CUTOFF"):
        val = getattr(sched, name, None)
        assert val is not None, f"{name} 부재"
        assert not (lo <= val <= hi), f"{name}({val}) 이 토큰 직렬화 창 {lo}~{hi} 안이다"

    assert sched.TIME_RECOMMENDATION < sched.TIME_METRICS_SNAPSHOT < sched.TIME_SETTLEMENT


def test_c283_5e_wait_until_default_is_documented_at_the_call_site():
    """C5 제약 ③ — 자문이 20:05 를 넘겨 끝나도 `advance_if_passed=False`(기본)라
    `_wait_until` 이 **즉시 반환**한다 = 실질은 "자문 블록 종료 직후, 단 20:05 전에는
    20:05 까지 대기". 유실 노출을 줄이는 목적에는 이쪽이 낫다(자문이 길수록 빨리 저장).

    누군가 `advance_if_passed=True` 로 바꾸면 **하루 통째로 건너뛴다** — 그 함정을
    호출부 주석에 남긴다.
    """
    seg = _segment(_SCHED_SRC, "start")
    idx = seg.find("TIME_METRICS_SNAPSHOT")
    assert idx > 0
    around = seg[max(0, idx - 900): idx + 300]
    assert "advance_if_passed" in around, (
        "1차 스냅샷 호출부에 `advance_if_passed` 함정 주석이 없다 — True 로 바뀌면 "
        "자문이 20:05 를 넘긴 날 스냅샷이 통째로 건너뛰어진다"
    )


# ===========================================================================
# C6 — 라인 예산
# ===========================================================================

#: `scheduler.py` 실효 라인 상한. **cycle257 이 세운 3,900 이 정본**이고 자매 가드 6곳
#: (cycle257 `test_line_count_below_3900` · 264 · 268 · 269_wiring · 272 · 273_kojiro_rank)
#: + cycle273b `_SCHEDULER_LINE_CAP` 이 같은 수를 복창한다. 브리프 C6 의 `< 4,000` 은
#: 그 시점의 오해였다 — 이 사이클의 자체 가드가 자매 가드보다 **느슨하면** cycle264 가
#: 적대 검증 HIGH 로 잡았던 상태(사이클 가드가 진짜 예산을 덮는다)의 재발이다.
_SCHEDULER_LINE_CAP = 3900


def test_c283_6_scheduler_line_budget():
    """cycle233 이후 영속 — `scheduler.py` < 3,900L (cycle257 영구 상한).

    C7 의 1차 저장 함수 본체는 **leaf 강제**(신규 leaf 또는 `log_analysis_engine.py`).
    scheduler 순증 목표 ≤ 15행 — cycle273b-F7 이 같은 이유로 27행을 밖으로 뺐다.

    척도는 자매 가드와 같은 `count("\n") + 1` 이다(`splitlines()` 보다 1 크다 —
    두 척도를 섞으면 경계에서 한쪽만 붉어진다).
    """
    n = _SCHED_SRC.count("\n") + 1
    assert n < _SCHEDULER_LINE_CAP, (
        f"scheduler.py {n}L — 상한 {_SCHEDULER_LINE_CAP:,}L (cycle257 영구 가드). "
        "4,000 은 구 상한이다; 올리려면 자매 가드 7곳(cycle257/264/268/269/272/273/273b)을 "
        "함께 올려야 한다"
    )


# ===========================================================================
# C14 ① — 순서 불변식 (이 사이클의 정체성)
# ===========================================================================

def test_c283_7_ordering_invariant():
    """`cutoff(20:00) ≤ 적재(20:30) < 정산(21:30)`.

    `cutoff > 적재` 면 정기 적재가 오늘 봉을 **영원히 못 쓴다** — 적대 검증에서
    실증됐다(cutoff 20:00 + 적재 18:10 → cycle263 스위트 11 failed).
    """
    assert scanner._DAILY_LOAD_TODAY_BAR_CUTOFF <= sched.TIME_STOCK_MASTER_DAILY_LOAD, (
        f"커트오프({scanner._DAILY_LOAD_TODAY_BAR_CUTOFF}) > 적재"
        f"({sched.TIME_STOCK_MASTER_DAILY_LOAD}) — 정기 적재가 오늘 봉을 영원히 버린다"
    )
    assert sched.TIME_STOCK_MASTER_DAILY_LOAD < sched.TIME_SETTLEMENT, (
        "적재가 정산(= 주기 task 수명 상한) 뒤면 매일 0회 발화한다(cycle270-B 재발)"
    )
    # ⚠️ 위 두 부등식만으로는 **현행 값(15:40 ≤ 18:10 < 20:10)도 통과**한다 —
    #    불변식은 세 값의 *관계* 만 재기 때문이다. 그래서 "커트오프는 그날 거래가
    #    끝나기 전일 수 없다" 는 **절대 조건**을 함께 잠근다. 이것이 이 사이클의
    #    실질적 주장이고, 09-11 사고가 증명한 것이다.
    assert scanner._DAILY_LOAD_TODAY_BAR_CUTOFF >= sched.TIME_NXT_POST_CLOSE, (
        f"커트오프({scanner._DAILY_LOAD_TODAY_BAR_CUTOFF})가 매매 종료"
        f"({sched.TIME_NXT_POST_CLOSE})보다 앞이다 — 그 사이의 모든 적재 실행이 "
        "**부분 거래량 봉**을 확정봉으로 받아들인다(09-11 사고의 직접 원인)"
    )


def test_c283_7b_start_cutoff_is_not_after_trading_close():
    """`TIME_SESSION_START_CUTOFF ≤ TIME_NXT_POST_CLOSE`.

    기동 거부 경계가 매매 종료보다 **뒤**면 그 사이 재기동이 이미 끝난 매매 단계를
    다시 훑는다(자문·`auto_apply` 재실행 = D4 가 막으려는 바로 그것).
    """
    assert sched.TIME_SESSION_START_CUTOFF <= sched.TIME_NXT_POST_CLOSE


def test_c283_7c_cutoff_equals_trading_close_by_design():
    """봉 확정 시각과 매매 종료 시각이 **값은 같지만 상수는 다르다**.

    scanner 는 지역 상수를 유지한다(cycle263 C5) — 값이 같아 보여도 한쪽을 옮길 때
    다른 쪽이 딸려 가면 안 된다. 이 테스트는 그 "우연한 일치" 를 명시적으로 기록해,
    다음 사람이 둘을 합치려는 유혹을 받을 때 왜 안 되는지 읽게 한다.
    """
    assert scanner._DAILY_LOAD_TODAY_BAR_CUTOFF == sched.TIME_NXT_POST_CLOSE, (
        "두 값이 갈라졌다면 그 자체는 결함이 아니다 — 다만 왜 갈라졌는지가 "
        "`src/engine/CLAUDE.md` 에 적혀 있어야 하고, 이 테스트를 그때 재표현한다"
    )
    assert "from src.engine.scheduler import" not in _SCANNER_SRC, (
        "scanner 가 scheduler 를 import 하면 값의 일치가 **우연**이 아니라 **커플링**이 된다"
    )


# ===========================================================================
# C10~C12 — 문서 동기화
# ===========================================================================

def test_c283_10_harness_changelog_has_a_cycle283_row():
    text = (_REPO_ROOT / "docs" / "HARNESS_CHANGELOG.md").read_text(encoding="utf-8")
    assert "cycle283" in text, "`docs/HARNESS_CHANGELOG.md` 에 cycle283 행이 없다"


def test_c283_10b_root_claude_md_table_has_cycle283():
    text = (_REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "cycle283" in text, "루트 `CLAUDE.md` 하네스 표에 cycle283 행이 없다"


def test_c283_11_engine_claude_md_states_new_times():
    text = (_REPO_ROOT / "src" / "engine" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)" in text
    assert "`_DAILY_LOAD_TODAY_BAR_CUTOFF`(= `time(20, 0)`" in text, (
        "커트오프 서술(`:172` 규칙 행)이 옛 `time(15, 40)` 을 말한다"
    )
    assert "time(15, 40)" not in text, "옛 커트오프 서술 잔존"
    assert "| `TIME_SETTLEMENT` | 21:30 |" in text, "시각 표의 정산 행이 옛 20:10 이다"
    assert "TIME_SESSION_START_CUTOFF" in text, "신규 기동 거부 상수 서술이 없다"
    assert "TIME_METRICS_SNAPSHOT" in text, "신규 1차 스냅샷 상수 서술이 없다"


def test_c283_11c_engine_claude_md_has_no_present_tense_1810():
    """C11 — 옛 적재 시각 `18:10` 이 **현재형 서술**로 남아 있으면 안 된다.

    이 프로젝트는 문서를 정본으로 쓴다. 시각 리터럴이 두 벌이면 다음 사람이 옛 값을
    되돌린다(cycle273f 주석 사건 · cycle270-B 21:30 사건이 같은 계열). 다만 역사
    인용(`종전 16:00 → 18:10 → 20:30`)은 정당한 잔존이므로, **같은 줄에 `종전` 이
    있는 경우만** 예외로 허용한다 — 예외를 쓰려면 역사임을 글로 밝혀야 한다.
    """
    text = (_REPO_ROOT / "src" / "engine" / "CLAUDE.md").read_text(encoding="utf-8")
    bad = [
        ln.strip()[:120] for ln in text.splitlines()
        if "18:10" in ln and "종전" not in ln
    ]
    assert not bad, (
        "`src/engine/CLAUDE.md` 가 옛 일봉 적재 시각 18:10 을 현재형으로 말한다 "
        f"(역사 인용이면 같은 줄에 '종전' 을 적어라):\n  " + "\n  ".join(bad)
    )


def test_c283_11d_scheduler_source_does_not_state_old_times():
    """C11 — **상수를 옮긴 파일이 스스로 옛 값을 말하지 않는다**.

    `scheduler.py` 모듈 docstring·주석이 `18:10 일봉` / `20:10 정산` 을 계속 말하고
    있었다(적대 검증 MEDIUM). 상수 한 줄만 고치고 이웃 서술을 두면, 다음 사람은 주석을
    믿고 상수를 '오타' 로 되돌린다. `20:10 → 21:30` 같은 **이동 기록**은 허용한다.
    """
    for ln in _SCHED_SRC.splitlines():
        assert "18:10" not in ln, f"scheduler.py 가 옛 적재 시각 18:10 을 말한다: {ln.strip()[:120]}"
        if "20:10 정산" in ln:
            raise AssertionError(
                f"scheduler.py 가 옛 정산 시각(20:10 정산)을 말한다: {ln.strip()[:120]}"
            )


def test_c283_11b_db_claude_md_says_upsert():
    text = (_REPO_ROOT / "src" / "db" / "CLAUDE.md").read_text(encoding="utf-8")
    assert "`insert_log_report()`" in text
    idx = text.find("`insert_log_report()`")
    row = text[idx: text.find("\n", idx)]
    assert "충돌 시 None" not in row, (
        "`insert_log_report` 서술이 아직 '충돌 시 None' 이다 — upsert 로 바뀌었다"
    )
    assert "ON CONFLICT" in row or "upsert" in row.lower()
    # upsert_external_report docstring 서술도 반증된다 (C9 ③)
    assert "그날의 `insert_log_report`(OpenAI 경로, 순수 `INSERT`)" not in text
    assert "UNIQUE 충돌로 `None` 을 반환한다**" not in text


def test_c283_12_root_claude_md_deploy_window():
    """C12/D8 — 배포 창 규약 `20:20~07:45` → `21:35~07:45`, push 금지 창 `20:00~21:35`.

    ⚠️ 이 문장은 루트 `CLAUDE.md` 에 **두 군데** 있다 — `:78`(자율 진행 구간 (b) 항)과
    `:260`(운영 가이드). 한쪽만 고치면 나머지 한쪽이 정본 행세를 한다.
    """
    text = (_REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "20:20~익일 07:45" not in text, "옛 배포 창(20:20~)이 남아 있다"
    assert text.count("21:35~익일 07:45") >= 1, "새 배포 창(21:35~) 서술이 없다"
    assert "20:00~20:15" not in text, "옛 push 금지 창(20:00~20:15)이 남아 있다"
    assert "20:00~21:35" in text, "새 push 금지 창(20:00~21:35) 서술이 없다"


def test_c283_12b_deploy_window_is_consistent_in_both_places():
    """`:78` 과 `:260` 이 **같은 창**을 말한다."""
    text = (_REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if "21:35" in ln or "20:00~21:35" in ln]
    assert len(lines) >= 2, (
        f"배포 창 서술이 한 곳에만 갱신됐다 (실측 {len(lines)}곳) — `:78` 자율 진행 "
        "구간 (b) 항과 `:260` 운영 가이드 둘 다 고친다"
    )


def test_c283_12c_architecture_evening_timeline_is_updated():
    """C10~C12 보완 — `docs/architecture.md` 저녁 타임라인 도식.

    `:341` 이 `20:10  _settle()  (TIME_SETTLEMENT)` 을 ASCII 도식으로 박아 두고 있고,
    그 도식에는 **일봉 적재가 아예 없다**(종전엔 16:00/18:10 이라 저녁 도식 밖이었다).
    20:30 으로 옮기면 이 도식이 그날 저녁 순서의 정본인데 한 칸이 비게 된다.
    """
    text = (_REPO_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    assert "20:10  _settle()" not in text, (
        "저녁 타임라인 도식이 옛 정산 시각(20:10)을 말한다"
    )
    assert "21:30" in text, "새 정산 시각(21:30)이 도식에 없다"
    assert "20:30" in text, (
        "저녁 도식에 일봉 적재(20:30)가 없다 — 이제 정산 앞의 마지막 작업이다"
    )


def test_c283_12d_leader_trading_rules_evening_table_is_updated():
    """C10~C12 보완 — `_workspace/00_leader_trading_rules.md` 시각 표.

    `:1013` 이 "settlement 20:10 까지 7분 여유", `:1015` 가 "20:10 전략별 + 합산 일일
    정산", `:1063` 이 표 행 `| TIME_SETTLEMENT | 20:10 |` 을 적고 있다.
    루트 `CLAUDE.md` 가 "매매 파라미터 변경 시 이 문서 동기화" 를 의무로 걸어 둔 곳이다.
    """
    text = (_REPO_ROOT / "_workspace" / "00_leader_trading_rules.md").read_text(
        encoding="utf-8"
    )
    assert "| `TIME_SETTLEMENT` | 20:10 |" not in text, "시각 표가 옛 정산 값을 말한다"
    assert "| `TIME_SETTLEMENT` | 21:30 |" in text
    assert "TIME_SESSION_START_CUTOFF" in text, (
        "기동 거부 경계 분리(D4)가 매매 규칙 문서에 없다 — 20:00~21:30 재기동은 "
        "그날 일봉 적재를 통째로 잃는다"
    )
