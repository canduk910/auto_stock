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


# ── cycle412 보완 Red — 결함 8(낮음): backfill 이 안내 문구만 찍고 exit 1 ────────────
#
# D3(과거 로그 1회 적재)는 승인 사항이라 실제로 동작하게 한다. 운영 적재는 10-13 배포와 분리한다.
#
# | # | 계약 |
# |---|---|
# | K6 | `async run_backfill(paths, db, *, max_bytes_per_sec=BACKFILL_MAX_BYTES_PER_SEC, sleep=time.sleep) -> dict` — 읽은 줄 수 `lines`·만든 행 수 `rows` · 행은 `db.insert_order` 로(=ON CONFLICT DO NOTHING) · 전부 `source="log_restore"` · 손절선 사건은 쓰지 않는다(스냅샷이 없다) |
# | K7 | 멱등 — 같은 파일을 두 번 적재해도 행이 늘지 않는다 |
# | K8 | 읽기 속도 상한 — 상한을 넘는 만큼 sleep(1초 단위) 한다 |
# | K9 | `.gz` 사본도 같은 행 |
# (CLI `python -m jw backfill <경로…>` 의 종료 코드·풀 크기 = test_jw_worker_ops W9b·W9c)

import asyncio  # noqa: E402

from jw_testkit import FakeJournalDB  # noqa: E402


def _golden_file(tmp_path, *, gz=False):
    if gz:
        p = tmp_path / "auto_stock.log.2026-10-07.gz"
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write(GOLDEN_LOG.read_text(encoding="utf-8"))
        return p
    p = tmp_path / "auto_stock.log.2026-10-07"
    p.write_text(GOLDEN_LOG.read_text(encoding="utf-8"), encoding="utf-8")
    return p


def _backfill(paths, db, **kw):
    kw.setdefault("max_bytes_per_sec", 10**12)
    kw.setdefault("sleep", lambda s: None)
    return asyncio.run(jw("backfill").run_backfill(paths, db, **kw))


def test_k6_run_backfill_writes_restore_rows(tmp_path):
    db = FakeJournalDB()
    res = _backfill([_golden_file(tmp_path)], db)
    assert res["rows"] == 145 and res["lines"] == len(golden_lines())
    assert len(db.orders) == 145
    assert {r["source"] for r in db.orders.values()} == {"log_restore"}
    assert db.stops == []
    assert not [c for c in db.calls if c[0] in ("save_cursor", "load_cursor")], "backfill 은 실시간 커서를 건드리지 않는다"


def test_k7_backfill_twice_does_not_add_rows(tmp_path):
    db = FakeJournalDB()
    f = _golden_file(tmp_path)
    _backfill([f], db)
    before = {k: dict(v) for k, v in db.orders.items()}
    res = _backfill([f], db)
    assert res["rows"] == 145
    assert db.orders == before


def test_k8_backfill_respects_read_rate_cap(tmp_path):
    f = _golden_file(tmp_path)
    cap = 16 * 1024
    slept: list[float] = []
    _backfill([f], FakeJournalDB(), max_bytes_per_sec=cap, sleep=slept.append)
    assert sum(slept) >= f.stat().st_size // cap - 1, (sum(slept), f.stat().st_size // cap)


def test_k9_gz_copy_restores_same_rows(tmp_path):
    a, b = FakeJournalDB(), FakeJournalDB()
    _backfill([_golden_file(tmp_path)], a)
    _backfill([_golden_file(tmp_path, gz=True)], b)
    assert set(a.orders) == set(b.orders) and len(b.orders) == 145
