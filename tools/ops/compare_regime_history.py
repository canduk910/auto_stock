#!/usr/bin/env python3
"""우리 `macro_lite` 레짐 판정을 원 프로젝트 산출값과 날짜별로 대조한다.

## 왜 있는가

매크로 레짐 출처를 외부 `dkstock.cloud` 에서 우리 `macro` 컨테이너로 옮길 때(cycle315),
「두 출처가 같은 값을 내는가」를 확인하는 것이 이관 2단계였다. 그런데 그 외부 서버가
2026-08-18 철거돼 **비교할 상대가 사라졌다**.

대체 경로가 이 스크립트다 — `macro/data/macro_regime_history_seed.json` 은 원 프로젝트의
`macro_regime_history` 테이블 추출본(147행, 2026-04-25~09-18)이고, 날짜마다 그날의
**입력 3종**(buffett_ratio·vix·fear_greed_score)과 **그 입력으로 원 프로젝트가 낸 regime** 을
함께 담고 있다. 즉 정답지다.

🔴 **그 파일은 macro_lite 가 읽지 않는다.** 판정이 무상태라 입력으로 연결하면 원본과 결과가
갈린다(`project-macro-lite-migration` 메모리의 제약). 순수하게 대조용으로만 쓴다.

## 쓰는 때

- vendor 재이식(`macro/macro_lite/` 를 원 패키지로 다시 덮은) 직후 — 판정이 그대로인지
- `regime.py` 의 매트릭스·임계를 건드린 뒤

## 한계

seed 에는 **신용 스프레드(HY OAS)가 없다**. `determine_regime` 의 Phase 1·2 보정은
그 값이 있을 때만 발동하므로 이 대조는 **보정 없는 기본 경로**만 검증한다.
그 경로가 판정의 대부분이지만 전부는 아니다.

## 실행

    python3 tools/ops/compare_regime_history.py

일치율 100% 가 정상이다. 불일치가 나오면 어느 (seed regime → ours) 조합인지와
그날 입력값이 함께 출력된다.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "macro/data/macro_regime_history_seed.json"

sys.path.insert(0, str(ROOT / "macro"))
from macro_lite.regime import determine_regime  # noqa: E402


def main() -> int:
    rows = json.loads(SEED.read_text(encoding="utf-8"))["rows"]

    match = mismatch = skipped = 0
    diffs: collections.Counter = collections.Counter()
    examples: list[tuple[str, str, str]] = []
    skipped_dates: list[str] = []

    for r in rows:
        bf, vix, fg = r.get("buffett_ratio"), r.get("vix"), r.get("fear_greed_score")
        if bf is None or vix is None or fg is None:
            skipped += 1
            skipped_dates.append(r.get("date", "?"))
            continue

        sentiment = {
            "fear_greed": {"score": fg},
            "vix": {"value": vix},
            "buffett_indicator": {"ratio": bf},
        }
        try:
            # 🔴 previous_regime 을 넘기지 않는다 — 판정은 무상태다.
            ours = determine_regime(sentiment).get("regime")
        except Exception as e:  # noqa: BLE001
            skipped += 1
            examples.append((r.get("date", "?"), "ERR", str(e)[:60]))
            continue

        theirs = r.get("regime")
        if ours == theirs:
            match += 1
        else:
            mismatch += 1
            diffs[(theirs, ours)] += 1
            if len(examples) < 10:
                examples.append(
                    (r.get("date", "?"), f"seed={theirs}", f"ours={ours}  bf={bf} vix={vix} fg={fg}")
                )

    total = match + mismatch
    print(f"대조 {total}행 (건너뜀 {skipped} — 입력 결측)")
    if total:
        print(f"  일치   {match}  ({match / total * 100:.1f}%)")
        print(f"  불일치 {mismatch}")

    if skipped_dates:
        print(f"\n건너뛴 날짜(원본에 입력이 없다): {', '.join(skipped_dates[:10])}")

    if diffs:
        print("\n불일치 유형 (seed → ours):")
        for (a, b), n in diffs.most_common():
            print(f"  {a} → {b} : {n}건")
    if examples:
        print("\n샘플:")
        for e in examples:
            print("  ", *e)

    return 0 if mismatch == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
