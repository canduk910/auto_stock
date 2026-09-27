"""ETF/ETN(류) 판정 단일 헬퍼 (cycle380, 사용자 결정 2026-09-27 「운영db 조회 허용 및
판정 변경 채택」).

명세 = `_workspace/red/cycle380_etf_group_code.md`.

이름 키워드 판정(`ETF_KEYWORDS`)은 개명 ETF(KIWOOM/TIME/1Q/…)를 놓치고 이름에 우연히
키워드가 들어간 주식(YG PLUS·BNK금융지주)을 잘못 막았다. 정본 판정은 KIS CTPF1002R #7
`scty_grp_id_cd`(EF=ETF·EN=ETN·FE=해외ETF)다 — 코드가 있으면 이름은 보지 않는다.
코드가 없을 때만(구 데이터·원천 행에 코드가 없는 경우) 기존 이름 규칙으로 폴백한다.

표준 라이브러리만 import 한다 — `src/db/stock_master.py`(SQL 빌더)가 같은 상수를 읽어야
하고, `scanner.py`(8영역·무거운 import)에 두면 그 무게가 SQL 빌더까지 끌려온다.
"""
from __future__ import annotations

from typing import Any, Mapping

#: KIS CTPF1002R #7 `scty_grp_id_cd` — ETF 류로 보는 코드 3종.
#: EF=ETF · EN=ETN · FE=해외ETF. `order_engine._observe_after_exit_etp` 와 같은 집합
#: (그 관측 함수는 이번 사이클에 무접촉 — 값만 여기와 같아야 한다).
ETF_GROUP_CODES: frozenset[str] = frozenset({"EF", "EN", "FE"})

#: 코드가 없을 때만 쓰는 폴백 — `scanner.py:494-497` 의 25개를 순서까지 그대로 옮긴다.
#: 이번 사이클은 이 폴백 규칙을 한 글자도 바꾸지 않는다.
ETF_KEYWORDS: tuple[str, ...] = (
    "KODEX", "TIGER", "KBSTAR", "KOSEF", "ARIRANG", "SOL", "ACE",
    "RISE", "KoAct", "PLUS", "TIMEFOLIO", "WOORI", "FOCUS",
    "HANARO", "히어로즈", "마이티", "BNK", "MASTER", "WON",
    "ETN", "선물", "인버스", "레버리지", "채권", "혼합",
)


def is_etf_like(raw: Any, name: str | None) -> bool:
    """ETF/ETN(류) 여부를 판정한다.

    - `raw` 가 Mapping 이고 `scty_grp_id_cd` 가 있으며(strip 후 비어 있지 않으면)
      → 그 값(strip+upper)이 `ETF_GROUP_CODES` 에 속하는지로만 판정한다. 이름은 보지
      않는다(코드 > 이름).
    - 그 밖(raw 가 None·Mapping 아님·키 없음·None·빈 문자열·공백) → 기존 이름 규칙
      `any(kw in (name or "") for kw in ETF_KEYWORDS)`(대소문자 구분 부분일치, 현행 그대로).

    `raw` 를 변경하지 않는다.
    """
    if isinstance(raw, Mapping):
        code = raw.get("scty_grp_id_cd")
        if code is not None:
            stripped = str(code).strip()
            if stripped:
                return stripped.upper() in ETF_GROUP_CODES

    return any(kw in (name or "") for kw in ETF_KEYWORDS)
