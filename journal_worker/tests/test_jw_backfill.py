"""cycle412 Red — 과거분 1회 적재(사용자 결정 D3, 설계 관찰자안 3절 「과거분(D3)」).

로컬 사본(09-17~10-07)은 로컬에서 파싱해 결과를 만들고 장외 창에 1회 적재한다. EC2 분(10-08~배포일)은
`docker compose run --rm journal_worker backfill` 로 1회 돌린다. **컨테이너 기동 경로에서는 뺀다**
(하루 235~376MB 로그를 기동마다 다시 읽으면 2GB 박스가 마른다).

| # | 계약 |
|---|---|
| K1 | 기동 경로(`jw/main.py`·`jw/__main__.py` 최상단·Dockerfile CMD)는 backfill 을 import·호출하지 않는다 |
| K2 | `jw/__main__.py` 는 `backfill` 인자일 때만 그 분기 안에서 `jw.backfill` 을 import 한다 |
| K3 | `'log_restore'` 문자열은 jw/ 에서 `backfill.py` 에만 · 실시간 기본 source 는 `log_harvest` |
| K4 | `restore_rows` = 골든 로그 → 매도 70·매수 75 행, 전부 `source="log_restore"` |
| K5 | `iter_log_lines` 는 `.gz`·평문을 읽고, 읽기 속도 상한을 넘으면 sleep 한다 |
"""
from __future__ import annotations

import ast
import gzip
import inspect

import pytest

from jw_testkit import GOLDEN_LOG, golden_lines, jw, jw_sources

pytestmark = pytest.mark.unit


def _imports(tree: ast.AST, *, top_level_only: bool) -> set[str]:
    nodes = tree.body if top_level_only else list(ast.walk(tree))
    out = set()
    for n in nodes:
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            out |= {f"{mod}.{a.name}" if mod else a.name for a in n.names} | {mod}
    return out


def test_k1_main_loop_never_touches_backfill():
    srcs = jw_sources()
    assert "jw/main.py" in srcs, "jw/main.py 가 없다"
    assert "backfill" not in srcs["jw/main.py"], "루프 모듈이 backfill 을 안다"
    for rel, text in srcs.items():
        if rel in ("jw/backfill.py", "jw/__main__.py"):
            continue
        assert not any("backfill" in m for m in _imports(ast.parse(text), top_level_only=False)), rel


def test_k2_dunder_main_imports_backfill_only_in_its_branch():
    srcs = jw_sources()
    assert "jw/__main__.py" in srcs, "jw/__main__.py 가 없다"
    tree = ast.parse(srcs["jw/__main__.py"])
    assert not any("backfill" in m for m in _imports(tree, top_level_only=True)), "최상단 import 금지"
    assert any("backfill" in m for m in _imports(tree, top_level_only=False)), "backfill 분기가 없다"
    assert "'backfill'" in srcs["jw/__main__.py"] or '"backfill"' in srcs["jw/__main__.py"]


def test_k3_log_restore_literal_only_in_backfill():
    srcs = jw_sources()
    assert "jw/backfill.py" in srcs, "jw/backfill.py 가 없다"
    holders = []
    for rel, text in srcs.items():
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Constant) and node.value == "log_restore":
                holders.append(rel)
    assert set(holders) == {"jw/backfill.py"}, holders
    sig = inspect.signature(jw("pairing").Pairer)
    assert sig.parameters["source"].default == "log_harvest"


def test_k4_restore_rows_over_golden():
    rows = jw("backfill").restore_rows(golden_lines())
    assert len(rows) == 145
    assert {r["source"] for r in rows} == {"log_restore"}
    assert sum(1 for r in rows if r["side"] == "SELL") == 70


def test_k5_iter_log_lines_reads_gz_and_plain(tmp_path):
    gz = tmp_path / "auto_stock.log.2026-09-29.gz"
    with gzip.open(gz, "wt", encoding="utf-8") as f:
        f.write(GOLDEN_LOG.read_text(encoding="utf-8"))
    plain = tmp_path / "auto_stock.log.2026-10-08"
    plain.write_text("a\nb\n", encoding="utf-8")
    lines = list(jw("backfill").iter_log_lines([gz, plain], max_bytes_per_sec=10**12, sleep=lambda s: None))
    assert lines[:2] == golden_lines()[:2] and lines[-2:] == ["a", "b"]
    assert len(lines) == len(golden_lines()) + 2


def test_k5b_iter_log_lines_throttles(tmp_path):
    p = tmp_path / "auto_stock.log.2026-10-08"
    p.write_text("x" * 99 + "\n" + "y" * 99 + "\n" + "z" * 99 + "\n", encoding="utf-8")
    slept: list[float] = []
    list(jw("backfill").iter_log_lines([p], max_bytes_per_sec=100, sleep=slept.append))
    assert slept and all(s > 0 for s in slept)
    assert jw("config").BACKFILL_MAX_BYTES_PER_SEC == 5 * 1024 * 1024
