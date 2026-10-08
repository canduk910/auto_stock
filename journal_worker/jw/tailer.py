"""로그 꼬리 읽기(cycle412 계약 3.8절). 커서 = {file_name, inode, byte_offset}."""
from __future__ import annotations

import os
import re
from pathlib import Path

from jw.config import LOG_FILE, MAX_READ_BYTES

_ROTATED_RE = re.compile(r"^" + re.escape(LOG_FILE) + r"\.\d{4}-\d{2}-\d{2}$")


def _find_by_inode(log_dir: Path, inode: int):
    try:
        names = os.listdir(log_dir)
    except OSError:
        return None
    for name in names:
        if not _ROTATED_RE.match(name):
            continue
        p = log_dir / name
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_ino == inode:
            return p
    return None


def _read_window(path: Path, offset: int, max_bytes: int):
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read(max_bytes)
    lines = chunk.split(b"\n")
    complete = lines[:-1]
    consumed = sum(len(ln) + 1 for ln in complete)
    text_lines = [ln.decode("utf-8", errors="replace") for ln in complete]
    return text_lines, offset + consumed


def read_chunk(log_dir, cursor, *, max_bytes: int = MAX_READ_BYTES, file_name: str = LOG_FILE):
    log_dir = Path(log_dir)
    live_path = log_dir / file_name

    if cursor is None:
        st = os.stat(live_path)
        lines, new_offset = _read_window(live_path, 0, max_bytes)
        return lines, {"file_name": file_name, "inode": st.st_ino, "byte_offset": new_offset}

    try:
        live_st = os.stat(live_path)
    except OSError:
        live_st = None

    if live_st is not None and live_st.st_ino == cursor["inode"]:
        if live_st.st_size < cursor["byte_offset"]:
            # 잘림 — 처음부터
            lines, new_offset = _read_window(live_path, 0, max_bytes)
            return lines, {"file_name": file_name, "inode": live_st.st_ino, "byte_offset": new_offset}
        lines, new_offset = _read_window(live_path, cursor["byte_offset"], max_bytes)
        return lines, {"file_name": file_name, "inode": live_st.st_ino, "byte_offset": new_offset}

    # 커서의 inode 가 현재 파일과 다르다 — 회전되었거나 옛 파일이 사라졌다.
    old_path = _find_by_inode(log_dir, cursor["inode"])
    if old_path is not None:
        try:
            old_st = os.stat(old_path)
        except OSError:
            old_st = None
        if old_st is not None:
            offset = cursor["byte_offset"] if old_st.st_size >= cursor["byte_offset"] else 0
            lines, new_offset = _read_window(old_path, offset, max_bytes)
            if new_offset >= old_st.st_size and live_st is not None:
                # 옛 파일 꼬리를 다 읽었다 — 새 파일 0 으로 넘어간다.
                new_cursor = {"file_name": file_name, "inode": live_st.st_ino, "byte_offset": 0}
            else:
                new_cursor = {"file_name": cursor["file_name"], "inode": old_st.st_ino,
                              "byte_offset": new_offset}
            return lines, new_cursor

    # 옛 파일이 없다 — 새(현재) 파일 0 부터.
    if live_st is None:
        return [], cursor
    lines, new_offset = _read_window(live_path, 0, max_bytes)
    return lines, {"file_name": file_name, "inode": live_st.st_ino, "byte_offset": new_offset}
