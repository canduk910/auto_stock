"""문서 규약 가드 — 정본의 **덧칠 0** 을 기계로 잰다 (2026-09-17).

규약의 출처 = 루트 `CLAUDE.md` 「문서 규약」 절 + `docs/history/README.md`
(2026-09-17 사용자 결정). 패턴 표의 출처 = `.claude/commands/sync-docs.md`
「덧칠 패턴 검사」 절.

## 왜 pytest 로 한 벌 더 두나

「덧칠 패턴 검사」는 `/sync-docs` 안의 bash 루프였다. 그 루프는 **사람이 그 명령을
실행할 때만** 돈다 — 즉 문서 커밋이 규약을 깨도 CI 는 침묵한다. 이 리포에는 같은
계열의 선례가 있다: 설정 토글은 CI/Deploy 를 타지 않아 자동 검증이 없었고,
`krx_open_api_enabled` 오판이 `full_universe_load` 를 3,577→60 으로 degrade 시킨
뒤 **D+1 에야** 발견됐다. 규약을 지키게 하려면 규약을 재는 것이 자동으로 돌아야 한다.

## 정본 목록과 패턴을 **하드코딩하지 않는다**

둘 다 다른 문서가 정본이므로 여기서 다시 적으면 그 순간 세 번째 사본이 생긴다
(「같은 사실을 두 문서에 적지 않는다」 위반). 그래서

* 패턴 9종 → `.claude/commands/sync-docs.md` 「덧칠 패턴 검사」 **표**에서 읽는다.
* 검사 대상 15파일 → 루트 `CLAUDE.md` 「문서 규약」 절 **첫 항**의 정본 열거에서
  읽는다(`CLAUDE.md` 전부 = glob).

그리고 그 둘이 서로 어긋나지 않는지도 함께 잰다 — `/sync-docs` 의 bash 루프가
열거한 파일 집합이 규약에서 파생한 집합과 같아야 한다. 새 `CLAUDE.md` 가 생기면
파생 집합이 먼저 커지고, 운영자용 체크리스트가 그 모듈을 빠뜨린 사실이 여기서
붉어진다(`/sync-docs` 「모듈 누락 자가 점검」 과 같은 취지).

## 🔵 공허 가드 금지

부재(0건) 단언은 스캐너가 아무것도 못 읽어도 참이다(cycle292 실측 교훈). 그래서
같은 스캐너로 **잡혀야 하는 텍스트** — `docs/history/**` 로 이관된 원문 — 를 긁어
9종 전부가 실제로 발화하는지 확인한다. 검사기가 죽으면 그쪽이 먼저 붉어진다.

## 스코프 밖

`docs/history/**` · `docs/HARNESS_CHANGELOG.md` · `docs/kis/**` ·
`_workspace/{red,analysis,domain_consult,reports,forensics}/**` — 시점 문서이거나
이력 그 자체다. 여기는 옛 문장이 남아 있는 것이 **정상**이라 검사 대상이 아니다
(`docs/history/README.md` 규칙 6). 그 제외 목록이 `/sync-docs` 에 여전히 적혀
있는지도 함께 잰다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SYNC_DOCS = _ROOT / ".claude" / "commands" / "sync-docs.md"
_ROOT_CLAUDE = _ROOT / "CLAUDE.md"
_HISTORY_DIR = _ROOT / "docs" / "history"

_SECTION_HEADING = "### 덧칠 패턴 검사"
_SECTION_END = "**검사 대상이 아닌 곳**"
_CONVENTION_HEADING = "### 문서 규약"

#: 표 셀의 첫 백틱 구간 = 정규식. `|` 는 마크다운 표에서 `\|` 로 탈출되므로 셀 원문만
#: 보면 "정규식의 리터럴 파이프" 와 "표 탈출된 교대(alternation)" 가 구별되지 않는다.
#: 실제로 두 용법이 섞여 있다 — 8번 패턴(정본 안 이력 표 행)은 `\|` 가 **리터럴
#: 파이프**고 나머지는 교대다. 그래서 아래 `_unescape_table_pipes` 가 가린다.
_TABLE_PATTERN_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def _section(text: str, heading: str, end: str | None = None) -> str:
    start = text.index(heading)
    stop = text.index(end, start) if end else len(text)
    return text[start:stop]


def _unescape_table_pipes(raw: str) -> str:
    """마크다운 표 셀의 `\\|` 를 정규식으로 되돌린다.

    규칙 = `\\|` → `|` 로 되돌려 보고, 그 결과가 **빈 문자열에 매치되면** 그 `\\|`
    들은 애초에 정규식의 리터럴 파이프였다는 뜻이므로 원문을 그대로 쓴다. 8번 패턴
    `\\|\\s*20\\d\\d-…\\|` 이 그 경우다 — 되돌리면 첫 교대가 빈 대안이 되어 **모든
    줄**에 매치하고 검사가 통째로 무의미해진다(반대로 되돌리지 않으면 1·3~7·9 번이
    literal `에는|엔|…` 을 찾아 영원히 0건 = 공허). 컴파일 실패도 같은 처분이다.
    """
    candidate = raw.replace("\\|", "|")
    try:
        if re.compile(candidate).search("") is None:
            return candidate
    except re.error:
        pass
    return raw


def _overpaint_patterns() -> list[tuple[str, re.Pattern[str]]]:
    sec = _section(_SYNC_DOCS.read_text(encoding="utf-8"), _SECTION_HEADING, _SECTION_END)
    out: list[tuple[str, re.Pattern[str]]] = []
    for line in sec.splitlines():
        m = _TABLE_PATTERN_RE.match(line.strip())
        if m:
            out.append((m.group(1), re.compile(_unescape_table_pipes(m.group(1)))))
    return out


def _canonical_docs() -> list[str]:
    """루트 `CLAUDE.md` 「문서 규약」 첫 항의 정본 열거 → 리포 상대 경로 목록."""
    sec = _section(_ROOT_CLAUDE.read_text(encoding="utf-8"), _CONVENTION_HEADING, "### 기본 진입점")
    bullet = next(ln for ln in sec.splitlines() if ln.startswith("- 정본("))
    enumerated = bullet[bullet.index("(") + 1: bullet.index(")")]
    rels: list[str] = []
    for token in re.findall(r"`([^`]+)`", enumerated):
        if token == "CLAUDE.md":
            # 「`CLAUDE.md` 전부」 — 이름을 열거하지 않고 리포에서 찾는다.
            rels.extend(
                p.relative_to(_ROOT).as_posix()
                for p in _ROOT.rglob("CLAUDE.md")
                if not any(part.startswith(".") or part == "node_modules" for part in p.parts)
            )
        else:
            rels.append(token)
    return sorted(set(rels))


def _sync_docs_bash_targets() -> list[str]:
    """`/sync-docs` bash 루프가 실제로 도는 파일 목록.

    ⚠️ 루프는 「검사 대상이 아닌 곳」 문단 **뒤**의 코드 펜스에 있다 — 그래서 절을
    `_SECTION_END` 로 자르지 않고 표제 이후 전체에서 찾는다.
    """
    text = _SYNC_DOCS.read_text(encoding="utf-8")
    tail = text[text.index(_SECTION_HEADING):]
    body = tail[tail.index("for f in") + len("for f in"): tail.index("; do")]
    return sorted(tok for tok in body.replace("\\", " ").split() if tok.endswith(".md"))


_PATTERNS = _overpaint_patterns()
_CANONICAL = _canonical_docs()


# ===========================================================================
# 메타 — 스캐너가 살아 있는가 (이 셋이 먼저 붉어져야 아래 0건 단언이 의미를 갖는다)
# ===========================================================================
def test_nine_patterns_are_parsed_from_sync_docs() -> None:
    """패턴 표에서 **9종**이 읽혔다.

    표가 리팩터되어 셀 형식이 바뀌면 `_TABLE_PATTERN_RE` 가 0개를 돌려주고 아래
    0건 단언이 통째로 공허해진다. 수를 고정해 그 사고를 막는다. 패턴을 늘리거나
    줄이는 것은 규약 변경이므로 이 수도 같이 고친다.
    """
    assert len(_PATTERNS) == 9, (
        f"`.claude/commands/sync-docs.md` 「덧칠 패턴 검사」 표에서 정규식 "
        f"{len(_PATTERNS)}종을 읽었다 — 9종이어야 한다. 표 형식이 바뀌었거나 "
        f"패턴이 추가·삭제됐다: {[raw for raw, _ in _PATTERNS]}"
    )


@pytest.mark.parametrize("raw", [raw for raw, _ in _PATTERNS], ids=range(1, len(_PATTERNS) + 1))
def test_every_pattern_actually_fires_on_history(raw: str) -> None:
    """🔵 양성 대조군 — 9종 **전부**가 `docs/history/**` 에서 실제로 잡힌다.

    history 는 정본에서 걷어낸 원문의 verbatim 이관본이므로, 걷어낸 그 덧칠들이
    거기 있다. 어느 패턴이 아무것도 못 잡으면 (a) 마크다운 탈출 처리가 틀렸거나
    (b) 이관이 안 됐거나 (c) 패턴이 낡았다 — 세 경우 모두 그 패턴의 0건 단언은
    공허하다.
    """
    assert _HISTORY_DIR.is_dir(), "docs/history/ 가 없다 — 양성 대조군의 원천이 사라졌다"
    compiled = re.compile(_unescape_table_pipes(raw))
    hits = {
        p.name: sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if compiled.search(ln))
        for p in sorted(_HISTORY_DIR.glob("*.history.md"))
    }
    assert any(hits.values()), (
        f"🔵 양성 대조군 실패 — 패턴 `{raw}` 이 `docs/history/*.history.md` "
        f"{len(hits)}파일에서 한 줄도 잡지 못했다. 이 패턴의 정본 0건 단언은 지금 "
        f"공허하다(탈출 처리 `_unescape_table_pipes` 를 먼저 의심하라)"
    )


def test_canonical_list_is_derived_and_non_empty() -> None:
    """검사 대상이 규약에서 파생됐고, 전부 실재하며 비어 있지 않다."""
    assert len(_CANONICAL) >= 5, f"정본 목록이 너무 짧다: {_CANONICAL}"
    for rel in _CANONICAL:
        path = _ROOT / rel
        assert path.is_file(), f"루트 `CLAUDE.md` 「문서 규약」 이 없는 파일을 정본으로 적었다: {rel}"
        assert len(path.read_text(encoding="utf-8")) > 200, f"🔵 양성 대조군 실패 — {rel} 이 비었다"


def test_history_is_out_of_scope() -> None:
    """`docs/history/**` 는 검사 대상이 **아니다**(`docs/history/README.md` 규칙 6).

    이력은 옛 문장이 남아 있는 것이 정상이다. 여기가 검사 대상이 되면 이관 자체가
    규약 위반이 되어 다음 사람이 이력을 지우는 쪽으로 움직인다.
    """
    leaked = [rel for rel in _CANONICAL if rel.startswith("docs/history/")]
    assert not leaked, f"history 파일이 덧칠 검사 대상에 들어왔다: {leaked}"
    sec = _SYNC_DOCS.read_text(encoding="utf-8")
    assert "`docs/history/**`" in sec[sec.index(_SECTION_END):], (
        "`/sync-docs` 「검사 대상이 아닌 곳」 에서 `docs/history/**` 가 빠졌다 — "
        "그 제외가 사라지면 이관본이 스스로를 붉힌다"
    )


def test_sync_docs_bash_loop_covers_every_canonical_doc() -> None:
    """운영자용 bash 루프의 파일 목록 == 규약에서 파생한 정본 집합.

    두 곳이 갈리면 사람이 손으로 돌리는 검사가 조용히 일부 파일을 빼먹는다. 새
    `CLAUDE.md` 를 만들었으면 `/sync-docs` 의 루프에도 넣어라(전용 `CLAUDE.md` 가
    없는 디렉터리가 누락 반복 지점이라는 경고가 루트 `CLAUDE.md` 에 이미 있다).
    """
    bash = _sync_docs_bash_targets()
    assert bash, "`/sync-docs` 의 bash 루프에서 파일 목록을 읽지 못했다"
    missing = sorted(set(_CANONICAL) - set(bash))
    extra = sorted(set(bash) - set(_CANONICAL))
    assert not missing and not extra, (
        f"`/sync-docs` bash 루프와 규약 파생 정본 목록이 갈렸다 — "
        f"루프에 없는 정본 {missing} / 루프에만 있는 항목 {extra}"
    )


# ===========================================================================
# 본 검사 — 정본 15파일 × 패턴 9종 = 0건
# ===========================================================================
@pytest.mark.parametrize("rel", _CANONICAL)
def test_canonical_doc_has_zero_overpaint(rel: str) -> None:
    """정본에 덧칠 0 — 시점 주석·취소선·신구 병존·정정 각주·이력 표 행·검증 수치.

    0 이 아닌 줄은 정본에서 걷어내 `docs/history/<정본 이름>.history.md` 에 **원문
    그대로** append 하고, 정본에는 새 값만 남긴다(루트 `CLAUDE.md` 「문서 규약」 절).

    ⚠️ 이 단언을 통과시키려고 **금기 문장을 지우지 않는다** — 정본에 남기는 것은
    값의 출처 사이클 번호(`K=2.0(cycle242)`)와 금기 + 그 이유 **한 문장**이다.
    그 한 문장이 패턴에 걸린다면 문장을 시점 서술 없이 다시 쓰는 것이 답이고,
    이유가 한 문단을 넘으면 history 링크로 줄인다.
    """
    text = (_ROOT / rel).read_text(encoding="utf-8")
    hits = [
        (i, raw, line.strip()[:110])
        for i, line in enumerate(text.splitlines(), 1)
        for raw, compiled in _PATTERNS
        if compiled.search(line)
    ]
    assert not hits, (
        f"{rel} 에 덧칠 {len(hits)}건 — 0 이어야 통과한다. 해당 줄을 "
        f"`docs/history/` 로 옮기고 정본에는 현재 규칙만 남겨라:\n  "
        + "\n  ".join(f"L{i} [{raw}] {s}" for i, raw, s in hits)
    )
