"""cycle398 PR0 — 전략 배선 골든(`tests/fixtures/strategy_wiring_golden.json`) 생성기.

실행:
    python tools/test_fixtures/gen_strategy_wiring_golden.py

골든을 만드는 코드는 테스트 모듈 `tests/unit/engine/test_cycle398_strategy_wiring_golden.py` 안에 있다.
이 스크립트는 그 모듈을 `STRATEGY_WIRING_GOLDEN_REGEN=1` 로 돌릴 뿐이다 — tests/conftest.py 의
환경변수·autouse 픽스처가 비교 때와 **같은 환경**을 만들어야 골든과 비교 값이 같은 조건에서 나온다.

🔴 행위 동일 리팩토링(카드 #2·#3 의 PR1·PR2)에서는 돌리지 않는다. 골든을 다시 만드는 것은
배선 행위를 일부러 바꾸는 사이클에서만 하고, 그 diff 가 곧 리뷰 지점이다.
"""

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEST = "tests/unit/engine/test_cycle398_strategy_wiring_golden.py"


def main() -> int:
    env = dict(os.environ, STRATEGY_WIRING_GOLDEN_REGEN="1")
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST, "-k", "regenerate"]
    return subprocess.call(cmd, cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
