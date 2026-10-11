"""cycle446 — 청산 AI 섀도 워커(`llm_worker/`) 테스트 설정. `journal_worker/tests/conftest.py` 와 같은 꼴.

- `llm_worker/` 와 이 디렉터리를 sys.path 앞에 넣는다 — `import lw`(워커 패키지)와
  `import lw_testkit`(도우미)가 되게 한다. 워커는 `src` 를 모른다.
- 이 디렉터리에는 `__init__.py` 를 두지 않는다 — 두면 모듈 이름이 `tests.test_lw_*` 가 되어
  루트 `tests` 패키지와 부딪친다. 파일 이름은 리포 전체에서 유일한 `test_lw_*.py` 다.
- 루트 `tests/conftest.py` 의 autouse 픽스처(네트워크 차단 등)는 여기 닿지 않는다. 이 테스트들은
  네트워크·DB·KIS·OpenAI 에 닿지 않는다(httpx MockTransport · 가짜 연결 · 가짜 openai 클라이언트만).
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent, _HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
