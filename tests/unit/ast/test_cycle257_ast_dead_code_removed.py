"""cycle257 — 사이클 26 시간대별 채널 전환 죽은 코드 삭제 가드 (D11, 사용자 승인 2026-09-05).

명세: `_workspace/.../spec_cycle257_dead_code_cycle26.md` §3 / 리팩토링 리뷰 2026-09-05 카드 #8.

배경 — `scanner.get_active_tick_tr_ids` 와 `scheduler._board_transition_loop` /
`_atomic_board_transition` 은 단일 커밋 f7f0766(2026-05-20)에서 **정의만** 추가되고
108일간 `src/` 호출자가 0 이었다(자기 주석·자기 호출 제외). 그런데 문서 4곳이 그것을
"동작 중"으로 서술해 포렌식(`stale_candidates_0904.md` ③ · `krx_channel_probe_design.md`
§3)을 두 번 오도했다. 코드의 실제 시세 채널은 `TICK_TR_ID = "H0UNCNT0"` 단일이고,
`websocket_pool.get_subscribed_tickers` 가 그 상수 하나만 소비한다.

| 가드 | 내용 | 수명 |
|---|---|---|
| A1 | 삭제 대상 심볼 되살림 차단 (scanner·scheduler AST + 원문) | **영구** |
| A2 | `TICK_TR_ID` 3 상수 보존 (P1-7 B 리졸버 반환값 자리) | **영구** |
| A3 | scanner `from datetime import time as _time` 별칭 제거 | **영구** |
| A4 | `scheduler.py` 라인 수 < 3,900 (감소 실증) + 기존 상한 4,000 | 영구(상한) |
| A5 | realtime TICK 필터 리터럴 집합 불변 (경계면 1건, 나머지는 tester) | **영구** |
| A6 | 현행 문서 4곳에 죽은 심볼 문자열 0 + 대체 문구 존재 | **영구** |

⚠️ A1 은 **영구 가드다** — "지웠다 되살리는" churn 차단이 존재 이유이므로 사이클 한정
diff 비교(bare `git diff HEAD`)를 쓰지 않는다(cycle240 A11b·cycle252 G-252-5b 선례:
사이클 한정 HEAD 비교 가드가 수명을 넘겨 후속 사이클을 무조건 붉혔다).

⚠️ A6 의 스캔 대상은 **현행 정본 문서만**이다. `docs/HARNESS_CHANGELOG.md` 와
`_workspace/**`(설계 카드·포렌식·red 로그·리뷰)는 verbatim 역사 기록이라 스캔하지
않는다 — 과거에 그렇게 서술했다는 사실 자체는 참이다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]

_SCANNER_REL = "src/engine/scanner.py"
_SCHEDULER_REL = "src/engine/scheduler.py"
_HANDLER_REL = "src/realtime/handler.py"
_WS_POOL_REL = "src/realtime/websocket_pool.py"

# 삭제 대상 심볼 (되살림 차단)
_DEAD_FUNCS_SCANNER = ("get_active_tick_tr_ids",)
_DEAD_FUNCS_SCHEDULER = ("_atomic_board_transition", "_board_transition_loop")
_DEAD_CONSTS_SCANNER = (
    "_TIME_PRE_NXT_START",
    "_TIME_KRX_PRESUBSCRIBE",
    "_TIME_KRX_MAIN_START",
    "_TIME_KRX_MAIN_END",
    "_TIME_NXT_PRESUBSCRIBE",
    "_TIME_POST_NXT_START",
    "_TIME_POST_NXT_END",
)
_DEAD_CONSTS_SCHEDULER = (
    "TIME_KRX_MAIN_OPEN_PRESUBSCRIBE",
    "TIME_POST_NXT_OPEN_PRESUBSCRIBE",
)

# 보존 대상 (삭제 금지) — TICK_TR_ID 는 websocket_pool 실소비, KRX/NXT 2줄은 P1-7 B 자리
_PRESERVED_TICK_CONSTS = {
    "TICK_TR_ID": "H0UNCNT0",
    "TICK_TR_ID_KRX": "H0STCNT0",
    "TICK_TR_ID_NXT": "H0NXCNT0",
}

_TICK_FILTER_LITERALS = {"H0STCNT0", "H0UNCNT0", "H0NXCNT0"}


def _read(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def _tree(rel: str) -> ast.Module:
    return ast.parse(_read(rel))


def _defined_func_names(rel: str) -> set[str]:
    """모듈 전체(중첩·메서드 포함)에서 정의된 함수 이름 집합."""
    out: set[str] = set()
    for node in ast.walk(_tree(rel)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(node.name)
    return out


def _module_assigned_names(rel: str) -> set[str]:
    """모듈 최상위 대입 이름 집합 (`X = ...` / `X: T = ...`)."""
    out: set[str] = set()
    for node in _tree(rel).body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    out.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
    return out


def _module_const_value(rel: str, name: str):
    """모듈 최상위 `name = <literal>` 의 값 (없으면 KeyError)."""
    for node in _tree(rel).body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    return ast.literal_eval(node.value)
    raise KeyError(name)


# ===========================================================================
# A1 — 삭제 대상 심볼 되살림 차단 (영구)
# ===========================================================================
class TestA1DeadSymbolsRemoved:
    """사이클 26 시간대별 전환 심볼이 두 파일 어디에도 없다.

    행위 영향 0(호출자 0)이므로 "되살릴 이유가 생겼다" 면 그것은 P1-7 B
    (속성 기반 `tick_tr_id_for(ticker)` 리졸버)이지 시각 기반 전환이 아니다.
    """

    def test_scanner_has_no_get_active_tick_tr_ids_def(self):
        defined = _defined_func_names(_SCANNER_REL)
        for name in _DEAD_FUNCS_SCANNER:
            assert name not in defined, (
                f"{_SCANNER_REL} 에 `{name}` 정의 재유입 — 시각 기반 채널 전환은 "
                "108일 미배선으로 cycle257 에서 삭제됐다. 채널 분기가 다시 필요하면 "
                "P1-7 B 속성 기반 리졸버로 간다."
            )

    def test_scanner_has_no_time_boundary_constants(self):
        assigned = _module_assigned_names(_SCANNER_REL)
        leftover = sorted(n for n in _DEAD_CONSTS_SCANNER if n in assigned)
        assert leftover == [], (
            f"{_SCANNER_REL} 에 시간 경계 상수 잔존: {leftover} — "
            "`get_active_tick_tr_ids` 내부 전용이었으므로 함께 삭제한다."
        )

    def test_scheduler_has_no_board_transition_methods(self):
        defined = _defined_func_names(_SCHEDULER_REL)
        leftover = sorted(n for n in _DEAD_FUNCS_SCHEDULER if n in defined)
        assert leftover == [], (
            f"{_SCHEDULER_REL} 에 보드 전환 메서드 재유입: {leftover} — "
            "`_board_transition_loop` 는 `create_task` 0 건, "
            "`_atomic_board_transition` 은 그 루프가 유일 호출자였다(전이적 dead)."
        )

    def test_scheduler_has_no_presubscribe_constants(self):
        assigned = _module_assigned_names(_SCHEDULER_REL)
        leftover = sorted(n for n in _DEAD_CONSTS_SCHEDULER if n in assigned)
        assert leftover == [], (
            f"{_SCHEDULER_REL} 에 사전 구독 마진 상수 잔존: {leftover} — "
            "두 상수의 유일한 소비자였던 보드 전환 루프가 사라졌다."
        )

    @pytest.mark.parametrize(
        "rel",
        [_SCANNER_REL, _SCHEDULER_REL],
        ids=["scanner", "scheduler"],
    )
    def test_no_dead_identifier_text_anywhere(self, rel: str):
        """원문 검사 — 주석·docstring 에 남은 서술도 다음 포렌식을 오도한다."""
        text = _read(rel)
        dead = (
            _DEAD_FUNCS_SCANNER
            + _DEAD_FUNCS_SCHEDULER
            + _DEAD_CONSTS_SCANNER
            + _DEAD_CONSTS_SCHEDULER
        )
        found = sorted({name for name in dead if name in text})
        assert found == [], (
            f"{rel} 원문에 죽은 심볼 문자열 잔존: {found} — 정의뿐 아니라 "
            "이를 '현행 동작' 으로 서술하는 주석/docstring 도 함께 제거한다."
        )

    def test_scanner_tick_tr_id_comment_corrected(self):
        """`TICK_TR_ID` 주석 방향 오류 정정 — 유일 활성 채널이 deprecated 로 표기돼 있었다."""
        lines = [
            ln for ln in _read(_SCANNER_REL).splitlines()
            if ln.startswith("TICK_TR_ID ")
        ]
        assert len(lines) == 1, f"`TICK_TR_ID` 대입 행 {len(lines)}건 (1건 기대)"
        assert "deprecated" not in lines[0].lower(), (
            f"`TICK_TR_ID` 행이 여전히 deprecated 로 표기됨: {lines[0]!r} — "
            "실제로는 현행 유일 활성 시세 채널(통합)이고 "
            "`websocket_pool.get_subscribed_tickers` 가 이 상수만 소비한다."
        )
        assert "cycle257" in _read(_SCANNER_REL), (
            f"{_SCANNER_REL} 에 cycle257 삭제 근거 주석 부재 — "
            "'시간대별 전환(사이클 26)은 배선된 적 없어 cycle257 에서 삭제, "
            "속성 기반 리졸버는 P1-7 B' 를 남긴다."
        )


# ===========================================================================
# A2 — TICK TR_ID 3 상수 보존 (영구)
# ===========================================================================
class TestA2TickTrIdConstantsPreserved:
    """죽은 코드 삭제가 상수 3줄을 함께 쓸어가면 안 된다.

    - `TICK_TR_ID` — `websocket_pool.get_subscribed_tickers` / `get_acked_tickers`
      의 실소비 상수(삭제 시 TICK 구독 집합 계산이 즉시 깨진다)
    - `TICK_TR_ID_KRX` / `TICK_TR_ID_NXT` — P1-7 B `tick_tr_id_for(ticker)` 리졸버의
      반환값 자리. 상수 2줄은 추상화가 아니므로 지웠다 되살리는 churn 을 피한다.
    """

    @pytest.mark.parametrize(
        ("name", "expected"), sorted(_PRESERVED_TICK_CONSTS.items()),
    )
    def test_constant_preserved_with_value(self, name: str, expected: str):
        try:
            value = _module_const_value(_SCANNER_REL, name)
        except KeyError:
            pytest.fail(
                f"{_SCANNER_REL} 에서 `{name}` 소실 — cycle257 삭제 범위 밖이다 "
                "(보존 계약)."
            )
        assert value == expected, f"`{name}` = {value!r} (기대 {expected!r})"

    def test_websocket_pool_still_consumes_tick_tr_id(self):
        """실소비 증거 — 이 import 가 있는 한 `TICK_TR_ID` 는 죽은 상수가 아니다."""
        text = _read(_WS_POOL_REL)
        assert "from src.engine.scanner import TICK_TR_ID" in text, (
            f"{_WS_POOL_REL} 의 `TICK_TR_ID` 소비가 사라졌다 — 상수 보존 근거가 "
            "바뀐 것이므로 A2 계약을 먼저 재검토한다(가드를 지우지 마라)."
        )


# ===========================================================================
# A3 — `_time` 별칭 import 제거 (영구)
# ===========================================================================
class TestA3TimeAliasImportRemoved:
    """`from datetime import time as _time` 은 삭제 대상 전용이었다.

    착수 전 실측: scanner.py 의 `_time` 사용처는 `_TIME_*` 7 상수 정의와
    `get_active_tick_tr_ids` 시그니처 주석뿐이었다(`_monotonic_time` /
    `_last_scan_time` 은 다른 이름). 잔존하면 미사용 import 다.
    """

    def test_no_time_alias_import(self):
        for node in _tree(_SCANNER_REL).body:
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.asname != "_time", (
                        f"{_SCANNER_REL}:{node.lineno} `import ... as _time` 잔존 — "
                        "사용처(`_TIME_*` 상수 + get_active_tick_tr_ids)가 함께 "
                        "삭제됐으므로 미사용 import 다."
                    )

    def test_no_bare_time_alias_usage(self):
        hits = [
            node.lineno for node in ast.walk(_tree(_SCANNER_REL))
            if isinstance(node, ast.Name) and node.id == "_time"
        ]
        assert hits == [], (
            f"{_SCANNER_REL} 에 `_time` 이름 사용 잔존 (lines={hits}) — "
            "`_monotonic_time`/`_last_scan_time` 과 혼동하지 말 것(정확 일치 검사)."
        )


# ===========================================================================
# A4 — scheduler 라인 수 감소 실증
# ===========================================================================
class TestA4SchedulerLineCount:
    """삭제 −130L 실증 + 기존 상한 4,000L 재확인.

    ⚠️ 이 삭제는 `test_cycle241_ast_silent_inactive_relative.py::
    TestG241_6SchedulerUntouched::test_scheduler_line_count_unchanged`(== 3999)를
    필연적으로 붉힌다. 그 가드는 docstring 에 "scheduler.py 를 의도적으로 편집하는
    후속 사이클이 이 단언을 갱신하거나 제거한다" 는 자기소멸 조건을 명시하고 있고,
    cycle257 이 바로 그 후속 사이클이다.
    """

    def test_line_count_below_3900(self):
        count = len(_read(_SCHEDULER_REL).splitlines())
        assert count < 3900, (
            f"{_SCHEDULER_REL} {count}L — 보드 전환 2 메서드(≈130L) 삭제 후 "
            "3,900L 미만이어야 한다(삭제 실증)."
        )

    def test_line_count_still_under_existing_cap(self):
        count = len(_read(_SCHEDULER_REL).splitlines())
        assert count < 4000, f"{_SCHEDULER_REL} {count}L — 기존 상한 4,000L 초과"


# ===========================================================================
# A5 — realtime TICK 필터 리터럴 집합 불변 (경계면 1건)
# ===========================================================================
class TestA5RealtimeTickFilterIntact:
    """realtime 측 TICK 필터는 scanner 상수와 **무관한 독립 리터럴**이다.

    scanner 의 `TICK_TR_ID_KRX/NXT` 를 삭제 대상으로 오인해 이 집합까지 손대면
    H0STCNT0/H0NXCNT0 로 들어오는 체결가 메시지가 파싱 분기에서 통째로 탈락한다.
    (전체 realtime diff 0 검증은 tester 경계면 — 여기서는 존재 가드 1건만.)
    """

    def test_handler_tick_tr_id_membership_tuple_intact(self):
        found = []
        for node in ast.walk(_tree(_HANDLER_REL)):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, ast.In) for op in node.ops):
                continue
            for comparator in node.comparators:
                if isinstance(comparator, (ast.Tuple, ast.Set, ast.List)):
                    values = {
                        el.value for el in comparator.elts
                        if isinstance(el, ast.Constant) and isinstance(el.value, str)
                    }
                    if values == _TICK_FILTER_LITERALS:
                        found.append(node.lineno)
        assert found, (
            f"{_HANDLER_REL} 에서 TICK 필터 집합 {sorted(_TICK_FILTER_LITERALS)} 의 "
            "멤버십 비교가 사라졌다 — cycle257 은 realtime 무접촉이 계약이다."
        )


# ===========================================================================
# A6 — 현행 문서에서 죽은 심볼 서술 소멸
# ===========================================================================
_DEAD_DOC_TOKENS = (
    "get_active_tick_tr_ids",
    "_board_transition_loop",
    "_atomic_board_transition",
    "TIME_KRX_MAIN_OPEN_PRESUBSCRIBE",
    "TIME_POST_NXT_OPEN_PRESUBSCRIBE",
)

# 명세 §0 이 지목한 현행 정본 문서. 역사 기록(docs/HARNESS_CHANGELOG.md, _workspace/**)은
# verbatim 이므로 스캔 대상이 아니다.
_LIVE_DOCS = [
    "src/realtime/CLAUDE.md",
    "src/engine/CLAUDE.md",
    "docs/architecture.md",
]


class TestA6DocsCorrected:
    @pytest.mark.parametrize("rel", _LIVE_DOCS)
    def test_live_doc_has_no_dead_symbol(self, rel: str):
        text = _read(rel)
        found = sorted(
            {tok for tok in _DEAD_DOC_TOKENS if tok in text}
        )
        assert found == [], (
            f"{rel} 이 삭제된 심볼을 여전히 서술: {found} — 이 거짓 서술이 "
            "포렌식을 두 번 오도했다(stale_candidates_0904 ③ · krx_channel_probe_design §3)."
        )

    def test_readme_has_no_dead_symbol(self):
        """⚠️ 명세 §0 '문서 4곳' 목록 밖 — 착수 전 실측으로 추가 확인된 5번째 지점.

        `README.md:330,337,512,518` 이 6 구간 분기표·원자 전환 절차·08:59:10/15:39:10
        스케줄 행을 **현행 동작**으로 서술한다. 같은 거짓 서술이므로 같은 처분이
        맞지만, 명세 범위 확장이라 team-leader 확인 대상이다(거부되면 이 케이스만 제거).
        """
        text = _read("README.md")
        found = sorted({tok for tok in _DEAD_DOC_TOKENS if tok in text})
        assert found == [], f"README.md 이 삭제된 심볼을 여전히 서술: {found}"

    def test_realtime_claude_md_records_removal(self):
        """삭제로 문단이 그냥 비면 다음 포렌식이 같은 질문을 다시 판다.

        단언(`cycle257` 존재)은 그대로 유지한다 — 남아야 하는 것은 **삭제됐다는
        사실 한 줄**이고 그건 값의 출처 사이클 번호 표기(`K=2.0(cycle242)` 계열)라
        정본에 허용된다(루트 `CLAUDE.md` 「문서 규약」 절).

        🔄 **2026-09-17 반전** — 종전에는 이 단언을 "문단을 대체하라"(= 삭제 경위를
        정본에 풀어 쓰라)로 읽었다. 그 경위는 이제
        `docs/history/src-realtime-CLAUDE.history.md` 로 간다. 정본에는 시간대별
        전환이 미배선·삭제(cycle257)라는 사실과 속성 기반 리졸버가 그 자리를 맡는다는
        **현재 규칙**만 남기고, "왜 그 판단이었나" 는 history 링크로 줄인다.
        """
        text = _read("src/realtime/CLAUDE.md")
        assert "cycle257" in text, (
            "src/realtime/CLAUDE.md 에 cycle257 표기 부재 — 시간대별 전환이 "
            "미배선·삭제(cycle257)라는 **사실 한 줄**은 정본에 남긴다. 경위는 "
            "`docs/history/src-realtime-CLAUDE.history.md` 로 옮기되 "
            "사실까지 지우면 다음 포렌식이 같은 질문을 다시 판다."
        )
