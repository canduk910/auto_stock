"""운영 DB 값 ↔ 코드 기본값 드리프트 관측 (cycle326).

`_load_strategy_config` 는 DB `params` 를 **키별로 덮어쓴다**. 그래서 한 번 DB 에 박힌 값은
계속 살고, 코드 기본값은 그 키에 대해 **장식**이 된다. 그 차이를 알리는 것이 아무것도 없었다.

2026-09-20 전수 실측 = **39개 키**가 달랐다. 그 무지가 실제 오판을 만들었다 —
롱테일 상한가 모드를 코드 기본값으로 읽어 「손절이 −3% → −5% 로 느슨해진다」고 보고했는데
운영 DB 는 정반대(**−5% → −3.5%**)였다. VB 손절도 코드 −3% 로 계산했지만 DB 는 −5% 였다.

🔴 **이 모듈은 값을 바꾸지 않는다.** DB 가 정본이라는 계약은 그대로다 —
바뀌는 것은 **보인다**는 것뿐이다. 차이를 「고쳐서」 없애려 하면 안 된다:
운영자가 의도로 넣은 값이 대부분이고(VCP 완화·kojiro 슬롯 등) 코드값으로 되돌리는 것이 곧 사고다.

🔴 **절대 예외를 올리지 않는다.** 이 관측이 부팅을 끊으면 그날 매매가 통째로 없다.
"""
from __future__ import annotations

from typing import Any, Iterable

__all__ = ["collect_param_drift"]


def _same(a: Any, b: Any) -> bool:
    """값이 같은가 — `4` 와 `4.0` 은 같다.

    실측에서 DB 는 정수로, 코드는 float 로 적힌 키가 많다
    (`limit_up_threshold` 29 vs 29.0 은 차이가 아니고 `max_positions` 4 vs 6 은 차이다).
    구별 못 하면 가짜 경고가 진짜를 덮는다.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def collect_param_drift(strategies: Iterable[Any] | None) -> list[dict]:
    """실행 params 와 코드 `DEFAULT_PARAMS` 의 차이를 모은다 (관찰 전용).

    Returns:
        `{"strategy_id", "key", "live", "code"}` 목록. 판정 불가·예외는 **조용히 건너뛴다**.

    ⚠️ **코드에 없는 키는 차이가 아니다** — 운영 전용 키를 드리프트로 세면 정상 운영이
    매일 경고를 내고, 사람이 그 경고를 배경 소음으로 학습한다.
    """
    out: list[dict] = []
    if not strategies:
        return out
    try:
        items = list(strategies)
    except Exception:
        return out

    for s in items:
        try:
            live = getattr(getattr(s, "config", None), "params", None)
            code = getattr(s, "DEFAULT_PARAMS", None)
            sid = getattr(getattr(s, "config", None), "strategy_id", None) or getattr(
                s, "strategy_id", "?"
            )
            if not isinstance(live, dict) or not isinstance(code, dict):
                continue
            for k, lv in live.items():
                if k not in code:
                    continue  # 운영 전용 키 — 차이가 아니다
                cv = code[k]
                if not _same(lv, cv):
                    out.append(
                        {"strategy_id": str(sid), "key": str(k), "live": lv, "code": cv}
                    )
        except Exception:
            continue
    return out
