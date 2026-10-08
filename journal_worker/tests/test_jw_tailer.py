"""cycle412 Red — 로그 꼬리 읽기(설계 관찰자안 3절 W1 · 8절 한계 9).

운영 로그는 `TimedRotatingFileHandler` 가 자정에 **이름을 바꿔** 회전한다(압축 없음, `src/main.py`).
하루 235~376MB 라 한 번에 다 읽지 않는다(1회 상한 4MiB — 보완2 N5). 커서(파일·inode·offset)는 DB 에 둔다.

| # | 계약 |
|---|---|
| T1 | 커서 없음 → 현재 파일 0 부터 · 반환 줄은 개행 없이 · 새 커서 = (파일명, inode, 읽은 끝) |
| T2 | 끝의 미완성 줄은 소비하지 않는다(다음 호출에서 완결되면 읽는다) |
| T3 | 한 번에 `max_bytes` 이하 · 기본값 = `MAX_READ_BYTES`(4MiB — 보완2 N5) |
| T4 | 회전: 커서 inode 가 바뀐 파일(`auto_stock.log.YYYY-MM-DD`)에 남은 꼬리를 먼저 끝까지 읽고 새 파일 0 으로 |
| T5 | 옛 파일이 없어졌으면 새 파일 0 부터 · 같은 inode 인데 잘렸으면 0 부터 |
| T6 | 깨진 바이트는 대체 문자로(예외 없음) |
"""
from __future__ import annotations

import inspect
import os

import pytest

from jw_testkit import jw

pytestmark = pytest.mark.unit


def _write(path, text, mode="w"):
    with open(path, mode, encoding="utf-8") as f:
        f.write(text)


def _read(log_dir, cursor, **kw):
    return jw("tailer").read_chunk(log_dir, cursor, **kw)


def test_t1_first_read_from_start(tmp_path):
    _write(tmp_path / "auto_stock.log", "a\nb\n")
    lines, cur = _read(tmp_path, None)
    assert lines == ["a", "b"]
    st = os.stat(tmp_path / "auto_stock.log")
    assert cur == {"file_name": "auto_stock.log", "inode": st.st_ino, "byte_offset": st.st_size}
    lines2, cur2 = _read(tmp_path, cur)
    assert lines2 == [] and cur2 == cur


def test_t2_partial_last_line_waits(tmp_path):
    _write(tmp_path / "auto_stock.log", "a\nb-부분")
    lines, cur = _read(tmp_path, None)
    assert lines == ["a"] and cur["byte_offset"] == 2
    _write(tmp_path / "auto_stock.log", "완결\nc\n", mode="a")
    lines, cur = _read(tmp_path, cur)
    assert lines == ["b-부분완결", "c"]


def test_t3_read_cap(tmp_path):
    _write(tmp_path / "auto_stock.log", "".join(f"line{i:03d}\n" for i in range(100)))  # 8바이트씩
    lines, cur = _read(tmp_path, None, max_bytes=50)
    assert lines == [f"line{i:03d}" for i in range(6)] and cur["byte_offset"] == 48
    total = list(lines)
    while True:
        more, cur = _read(tmp_path, cur, max_bytes=50)
        if not more:
            break
        total += more
    assert total == [f"line{i:03d}" for i in range(100)]


def test_t3b_default_cap_is_4_mib():
    """보완2 N5 — 20MiB 창이면 따라잡을 때 순간 메모리 ≈100MB(상한 160m 의 80%). 4MiB 로 줄인다."""
    assert jw("config").MAX_READ_BYTES == 4 * 1024 * 1024
    sig = inspect.signature(jw("tailer").read_chunk)
    assert sig.parameters["max_bytes"].default == 4 * 1024 * 1024


def test_t4_rotation_reads_old_tail_then_new_file(tmp_path):
    live = tmp_path / "auto_stock.log"
    _write(live, "d1-a\n")
    _, cur = _read(tmp_path, None)
    _write(live, "d1-b\n", mode="a")                          # 회전 직전에 더 써짐
    os.rename(live, tmp_path / "auto_stock.log.2026-10-13")  # 자정 회전(이름 바꾸기)
    _write(live, "d2-a\n")
    got = []
    for _ in range(4):
        lines, cur = _read(tmp_path, cur)
        got += lines
    assert got == ["d1-b", "d2-a"]
    assert cur["inode"] == os.stat(live).st_ino and cur["file_name"] == "auto_stock.log"


def test_t5_old_file_gone_restarts_new_file(tmp_path):
    live = tmp_path / "auto_stock.log"
    _write(live, "d1-a\n")
    _, cur = _read(tmp_path, None)
    # 옛 파일을 비켜 둔 채 새 파일을 만들고 나서 지운다 — 지운 inode 번호를 새 파일이 다시 받는
    # 파일시스템(ext4)에서도 새 파일 inode 가 옛 것과 달라 이 테스트가 흔들리지 않는다.
    os.rename(live, tmp_path / "gone.bak")
    _write(live, "d2-a\n")
    os.remove(tmp_path / "gone.bak")
    lines, cur = _read(tmp_path, cur)
    assert lines == ["d2-a"]


def test_t5b_truncated_same_inode_restarts(tmp_path):
    live = tmp_path / "auto_stock.log"
    _write(live, "aaaa\nbbbb\n")
    _, cur = _read(tmp_path, None)
    with open(live, "r+", encoding="utf-8") as f:
        f.truncate(0)
    _write(live, "c\n", mode="a")
    lines, _ = _read(tmp_path, cur)
    assert lines == ["c"]


def test_t6_invalid_utf8_is_replaced(tmp_path):
    (tmp_path / "auto_stock.log").write_bytes(b"ok\n\xff\xfe broken\n")
    lines, _ = _read(tmp_path, None)
    assert lines[0] == "ok" and "�" in lines[1]
