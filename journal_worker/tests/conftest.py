"""cycle412 — 거래일지 워커(`journal_worker/`) 테스트 설정.

- `journal_worker/` 와 이 디렉터리를 sys.path 앞에 넣는다 — `import jw`(워커 패키지)와
  `import jw_testkit`(도우미)가 되게 한다. 워커는 `src` 를 모른다.
- 이 디렉터리에는 `__init__.py` 를 두지 않는다 — 두면 모듈 이름이 `tests.test_jw_*` 가 되어
  루트 `tests` 패키지와 부딪친다. 그래서 파일 이름은 리포 전체에서 유일한 `test_jw_*.py` 다.
- 루트 `tests/conftest.py` 의 autouse 픽스처(네트워크 차단 등)는 여기 닿지 않는다. 이 테스트들은
  네트워크·DB·KIS 에 닿지 않는다(httpx MockTransport · 가짜 연결 · tmp_path 만).

계약 = `_workspace/red/cycle412/journal_contract.md` 3절.
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
