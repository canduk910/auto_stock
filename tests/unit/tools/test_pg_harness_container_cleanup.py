"""통합 테스트 Postgres 컨테이너 누수 방지 (2026-10-03 사용자 지시 「테스트가 완료된 도커컨테이너는 삭제」).

`tests/integration/pg_harness.py` 가 띄우는 컨테이너는 라벨로 소유 pytest 프로세스를 기록하고,
다음 세션 시작 때 소유 프로세스가 죽은 것만 지운다(동시에 도는 다른 pytest 의 것은 지우지 않는다).
"""

from __future__ import annotations

import os
import subprocess
from types import SimpleNamespace

from tests.integration import pg_harness as h


def _fake_run(ps_stdout: str, calls: list):
    def run(args, **kw):
        calls.append(list(args))
        if args[:2] == ["docker", "ps"]:
            return SimpleNamespace(stdout=ps_stdout, returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    return run


def test_sweep_removes_only_containers_whose_owner_is_dead(monkeypatch):
    live, dead = os.getpid(), 999_999_999
    ps = f"aaa {dead} auto_stock_pg_test_dead\nbbb {live} auto_stock_pg_test_live\n"
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_run(ps, calls))
    monkeypatch.setattr(h, "_pid_alive", lambda pid: pid == live)

    removed = h._sweep_orphan_containers()

    assert removed == ["auto_stock_pg_test_dead"]
    rm_calls = [c for c in calls if c[:3] == ["docker", "rm", "-f"]]
    assert rm_calls == [["docker", "rm", "-f", "aaa"]]


def test_sweep_filters_by_label_and_never_raises(monkeypatch):
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_run("", calls))
    assert h._sweep_orphan_containers() == []
    ps_call = next(c for c in calls if c[:2] == ["docker", "ps"])
    assert f"label={h._LABEL}" in ps_call

    def boom(*a, **k):
        raise OSError("docker gone")

    monkeypatch.setattr(subprocess, "run", boom)
    assert h._sweep_orphan_containers() == []


def test_unparseable_owner_is_treated_as_dead(monkeypatch):
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_run("ccc notapid auto_stock_pg_test_x\n", calls))
    assert h._sweep_orphan_containers() == ["auto_stock_pg_test_x"]


def test_start_labels_container_with_owner_pid_and_sweeps_first(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(h, "_sweep_orphan_containers", lambda: seen.setdefault("swept", True))

    def check_output(args, **kw):
        if args[:2] == ["docker", "run"]:
            seen["run"] = list(args)
            return "cid123\n"
        return "0.0.0.0:54321\n"

    monkeypatch.setattr(subprocess, "check_output", check_output)
    cid, dsn = h._start_pg_container()

    assert seen.get("swept") is True
    assert cid == "cid123" and dsn.endswith(":54321/" + h._PG_DB)
    run = seen["run"]
    assert "--rm" in run
    assert h._LABEL in run
    assert f"{h._OWNER_KEY}={os.getpid()}" in run
