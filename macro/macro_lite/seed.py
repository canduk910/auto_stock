"""OAS 누적 시계열 seed 적재 엔트리.

    python -m macro_lite.seed [--path data/oas_history_seed.json]

원 프로젝트 `scripts/export_oas_history.py` 로 추출한 seed JSON 을
파일 캐시(`macro:oas_history_persist:{series_id}`)에 merge_and_persist 한다.
멱등 — 두 번 실행해도 total 불변. 앱 기동 시 자동 실행되지 않는다.
"""
from __future__ import annotations

import argparse
import sys

from .oas_history_store import SEED_PATH_DEFAULT, load_seed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m macro_lite.seed",
        description="FRED OAS 누적 시계열 seed JSON → macro_lite 파일 캐시 적재",
    )
    parser.add_argument(
        "--path",
        default=str(SEED_PATH_DEFAULT),
        help=f"seed JSON 경로 (기본: {SEED_PATH_DEFAULT})",
    )
    args = parser.parse_args(argv)

    results = load_seed(args.path)
    if not results:
        print("seed 에 시리즈가 없습니다.", file=sys.stderr)
        return 0

    print(f"seed: {args.path}")
    for series_id, stats in results.items():
        print(
            f"  {series_id}: added={stats['added']} removed={stats['removed']} "
            f"total={stats['total']} range={stats['first_date']} ~ {stats['last_date']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
