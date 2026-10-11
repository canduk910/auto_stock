"""전략별 핵심값 분포 — 주간 자문 입력 보강 (cycle448, 사용자 결정 2026-10-11).

사용자 결정: 평소 일일 보고에는 전략 핵심값 분포가 필요 없지만 주간 자문에는 필요하다.
목요일 20:00 주간 자문(`recommendation_engine.py`)의 OpenAI payload 에, 그 전략의 그날
후보·보유 종목이 들고 있는 기술 지표(`StrategyBase.llm_context(ticker)`, cycle445 B)를
모아 키별 분포로 얹는다. 일일 보고 경로(`log_metrics_collector.py` · `log_analysis_engine.py`
· `daily_metrics_snapshot.py` · `routes/log_reports.py`)는 이 모듈을 import 하지 않는다
(가드 = `tests/unit/ast/test_cycle448_ast_scope.py`).

## 설계

- **순수 함수**(`summarize_numeric` · `summarize_categorical` · `build_key_distributions`
  · `_apply_price_ratio_rules`) — 표준 라이브러리만 쓰고 `src.*` 를 import 하지 않는다.
  `await`·로깅·벽시계 0.
- **얇은 수집기**(`collect_strategy_core_metrics` · `collect_all_core_metrics`) — 호출자가
  이미 들고 있는 **전략 객체**를 받아 `getattr` 로 duck-typing 조회만 한다. 레지스트리를
  스스로 찾지 않는다(호출자가 이미 `registry.all()`/`registry.enabled()` 로 전략 객체를
  들고 있다 — `llm_buy_gate._read_strategy_llm_context` 와 달리 이 모듈은 `scheduler` 를
  import 하지 않는다. 순환 import 위험 자체가 없다).
- **never-raise** — 전략 하나의 조회 실패가 다른 전략·다른 종목의 분포를 지우지 않는다.
  읽는 자리마다 개별 `try/except`.
- **매매 경로 무접촉** — `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py`
  (8영역) · `scheduler.py` 를 import 하지 않고, 어떤 매매 상태(신호·수량·청산·`_candidates`
  등)도 쓰지 않는다. 읽기만 한다.

## 후보·보유 종목 소스

- **후보** = `strategy.get_scanned_tickers()`(callable 이면 호출). 빈 목록이고 전략에
  `FIXED_TICKER`(문자열) 속성이 있으면 그 하나를 후보로 쓴다(`ndx2x_riskoff` 처럼
  `get_scanned_tickers()` 가 항상 빈 목록인 1종목 전략을 위한 일반 규칙 — 전략명을
  하드코딩하지 않는다). 둘 다 없으면 빈 목록(예: momentum — `llm_context` 를 재정의하지
  않아 애초에 키가 안 난다).
- **보유** = `strategy.state.positions`(dict) 의 키.
- 어느 쪽이든 `llm_context(ticker)` 가 빈 dict 를 돌려주면(재정의 안 함·결측) 그 종목은
  분포 계산에서 빠진다(`n_with_context` 가 `n_tickers` 보다 작을 수 있다 — 「모름」과
  「0」을 구분).

## 숫자 키 vs 범주 키

키 하나의 모든 값이 `bool` 아닌 `int`/`float`(유한값)이면 **숫자 분포**
(`n`·`median`·`p25`·`p75`·`min`·`max` 6개 — 후보 수가 많아도 payload 크기가 고정된다).
그 밖(문자열·bool·혼합)은 **빈도표**(`n`·`counts`). 분류는 값의 실제 파이썬 타입으로만
정하고, 키 이름으로 미리 정하지 않는다(어떤 전략이 어떤 타입으로 값을 내는지는
`llm_context` 쪽 결정이다 — 이 leaf 는 받은 값을 있는 그대로 분류한다).

## 가격 무관 비율 — `_apply_price_ratio_rules` (검토 반영, 2026-10-11)

전략마다 쓰는 ATR·EMA 값은 원화 절대값이라, 가격대가 다른 종목을 모아 중앙값·사분위를
내면 해석이 안 된다(예: ATR 812원짜리 저가주와 ATR 15,000원짜리 고가주가 같은 분포에
섞인다). `llm_context` 가 이미 주는 값 안에서 — **지어내지 않고** — 이동평균을 가격
대용으로 써 비율을 만든다. 규칙은 "이 두 키가 둘 다 있으면 이 비율을 더한다"는 선언적
표(`_PRICE_RATIO_RULES`)이고, 전략 이름으로 분기하지 않는다(여러 전략이 같은 키 이름을
쓰면(예: donchian·etf_trend 둘 다 `atr`+`ema60`) 자연히 같은 규칙이 적용된다). 분모가
없거나 0 이거나 결측이면 **그 종목의 그 비율 키만** 빠진다(다른 키·다른 종목은 그대로).

- `atr / ema60 → atr_to_ema60_pct`(%) — donchian·etf_trend.
- `atr20 / ema60 → atr20_to_ema60_pct`(%) — etf_trend.
- `atr14 / ema50 → atr14_to_ema50_pct`(%) — vcp.
- `base_low / ema50 → base_low_to_ema50_ratio` — vcp(베이스 저점이 50일선 대비 어디 있나).
- `ema50 / ema150 → ema50_to_ema150_ratio`, `ema150 / ema200 → ema150_to_ema200_ratio`
  — vcp(정배열 정도).
- `ema_s / ema_m → ema_s_to_ema_m_ratio`, `ema_m / ema_l → ema_m_to_ema_l_ratio`
  — kojiro(대순환 정렬). kojiro 의 `atr_ratio`(= atr/종가, 이미 가격 무관 비율)와
  중복이라 `atr`/`ema_m` 비율은 **만들지 않는다** — `atr_ratio` 는 `_ratio` 접미사로
  `unit="ratio"` 가 그대로 붙는다.
- `pole_high / pole_start − 1 → pole_rise_pct`(%) — bull_flag(깃대 상승폭). bull_flag 의
  `atr14` 는 같은 ctx 안에 가격 대용(ema 등)이 없어 비율을 못 만든다 — `unit="won"` 절대값
  그대로 남는다(아래 「unit」 절 참조).
- VB·LTV 의 `prev_range` 도 가격 대용이 없어 `unit="won"` 그대로다.

## 보유 종목만 — 매수가 대비 ATR 비율

ATR 계열 키(`atr`·`atr14`·`atr20`)는 **보유 종목만**(매수가가 있어야 비율을 낼 수 있다)
`strategy.state.positions[ticker].buy_price` 로 `<key>_to_buy_price_pct`(매수가 대비 %)를
위 이동평균 비율과 **함께** 더한다(둘 다 유용하다 — 매수가 기준은 실제 손익 기준, 이동평균
기준은 기술적 추세 기준). 후보 종목은 매수가가 없어 이 비율은 홀딩에서만 난다.

## unit 칸 (검토 반영, 2026-10-11)

모든 분포 항목에 `unit` 칸을 붙인다 — 읽는 쪽이 절대값을 종목 간 비교에 잘못 쓰지
않게 한다. 분류는 **접미사 우선**(`_pct`→"pct", `_ratio`→"ratio") + 범주형이면
"category" + 그 밖은 `_KEY_UNITS` 조회(없으면 "won" — 미지 키는 보수적으로 "비교 금지"
쪽으로 떨어진다). `build_key_distributions` 의 반환 dict 는 **pct·ratio 단위 키가 먼저**
오도록 정렬한다(파이썬 dict 삽입 순서 = JSON 직렬화 순서).
"""

from __future__ import annotations

import math
from typing import Any, Iterable

#: 보유 종목에서만 매수가 대비 비율을 더하는 ATR 계열 키 이름(전략마다 다르다).
_ATR_LIKE_KEYS: tuple[str, ...] = ("atr", "atr14", "atr20")

#: (분자 키, 분모 키, 결과 키, 변환) — 전략 이름과 무관하게 두 키가 둘 다 있으면 적용한다.
#: 변환 = "pct"(분자/분모×100) · "ratio"(분자/분모) · "pct_change"((분자/분모−1)×100).
_PRICE_RATIO_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("atr", "ema60", "atr_to_ema60_pct", "pct"),
    ("atr20", "ema60", "atr20_to_ema60_pct", "pct"),
    ("atr14", "ema50", "atr14_to_ema50_pct", "pct"),
    ("base_low", "ema50", "base_low_to_ema50_ratio", "ratio"),
    ("ema50", "ema150", "ema50_to_ema150_ratio", "ratio"),
    ("ema150", "ema200", "ema150_to_ema200_ratio", "ratio"),
    ("ema_s", "ema_m", "ema_s_to_ema_m_ratio", "ratio"),
    ("ema_m", "ema_l", "ema_m_to_ema_l_ratio", "ratio"),
    ("pole_high", "pole_start", "pole_rise_pct", "pct_change"),
)

#: 접미사(`_pct`/`_ratio`)로 못 가르는 키의 단위. 그 밖(원시 가격·EMA·ATR 등)은 "won" 기본값.
_KEY_UNITS: dict[str, str] = {
    "avg_volume_20": "count",
    "flag_avg_volume": "count",
    "stage": "count",
    "t7": "ratio",
    "r4": "ratio",
}

_EMPTY_BUCKET: dict[str, Any] = {"n_tickers": 0, "n_with_context": 0, "keys": {}}


def _is_finite_number(v: Any) -> bool:
    """bool 이 아닌 유한 int/float 인가 (`True`/`False` 는 숫자로 세지 않는다)."""
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    if isinstance(v, float):
        return math.isfinite(v)
    return False


def _percentile(sorted_values: list[float], pct: float) -> float:
    """선형보간 백분위수(numpy 기본값과 동일한 식). `sorted_values` 는 오름차순·비어있지 않음."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    k = (n - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    d0 = sorted_values[f] * (c - k)
    d1 = sorted_values[c] * (k - f)
    return d0 + d1


def summarize_numeric(values: Iterable[Any]) -> "dict | None":
    """숫자 분포 6개 — `n`·`median`·`p25`·`p75`·`min`·`max`. 유효값 0 이면 `None`."""
    vals = sorted(float(v) for v in values if _is_finite_number(v))
    n = len(vals)
    if n == 0:
        return None
    return {
        "kind": "numeric",
        "n": n,
        "median": round(_percentile(vals, 0.5), 6),
        "p25": round(_percentile(vals, 0.25), 6),
        "p75": round(_percentile(vals, 0.75), 6),
        "min": round(vals[0], 6),
        "max": round(vals[-1], 6),
    }


def summarize_categorical(values: Iterable[Any]) -> "dict | None":
    """빈도표 — `n`·`counts`(값을 `str()` 로 바꾼 JSON 키). `None` 값은 세지 않는다."""
    counts: dict[str, int] = {}
    n = 0
    for v in values:
        if v is None:
            continue
        key = str(v)
        counts[key] = counts.get(key, 0) + 1
        n += 1
    if n == 0:
        return None
    return {"kind": "categorical", "n": n, "counts": counts}


def _unit_for_key(key: str, kind: str) -> str:
    """`pct`·`ratio`·`won`·`count`·`category` 중 하나. 미지 키는 보수적으로 `won`."""
    if kind == "categorical":
        return "category"
    if key.endswith("_pct"):
        return "pct"
    if key.endswith("_ratio"):
        return "ratio"
    return _KEY_UNITS.get(key, "won")


def build_key_distributions(rows: list[dict]) -> dict[str, dict]:
    """`llm_context`(+비율 보강) 값 dict 들을 모아 키별 분포로.

    숫자만 모인 키는 숫자 분포, 그 밖은 빈도표. 각 항목에 `unit` 을 붙이고,
    `pct`·`ratio` 단위 키가 먼저 오도록 정렬한다(종목 간 비교 가능한 키를 앞에 둔다).
    """
    raw_by_key: dict[str, list[Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for k, v in row.items():
            if not isinstance(k, str) or not k or v is None:
                continue
            raw_by_key.setdefault(k, []).append(v)

    items: list[tuple[str, dict]] = []
    for key, values in raw_by_key.items():
        if all(_is_finite_number(v) for v in values):
            summary = summarize_numeric(values)
        else:
            summary = summarize_categorical(values)
        if summary is None:
            continue
        summary["unit"] = _unit_for_key(key, summary["kind"])
        items.append((key, summary))

    items.sort(key=lambda kv: 0 if kv[1]["unit"] in ("pct", "ratio") else 1)
    return dict(items)


def _apply_price_ratio_rules(ctx: dict) -> dict:
    """`_PRICE_RATIO_RULES` 를 ctx 에 적용해 가격 무관 비율 키를 더한다(순수, never-raise)."""
    if not ctx:
        return ctx
    out = dict(ctx)
    for num_key, den_key, out_key, transform in _PRICE_RATIO_RULES:
        num = ctx.get(num_key)
        den = ctx.get(den_key)
        if not (_is_finite_number(num) and _is_finite_number(den)):
            continue
        den_f = float(den)
        if den_f == 0:
            continue
        try:
            num_f = float(num)
            if transform == "pct":
                out[out_key] = round(num_f / den_f * 100.0, 4)
            elif transform == "ratio":
                out[out_key] = round(num_f / den_f, 6)
            elif transform == "pct_change":
                out[out_key] = round((num_f / den_f - 1.0) * 100.0, 4)
        except Exception:
            continue
    return out


def _candidate_tickers(strategy: Any) -> list[str]:
    try:
        fn = getattr(strategy, "get_scanned_tickers", None)
        tickers = fn() if callable(fn) else None
        if isinstance(tickers, (list, tuple, set)):
            seen: set[str] = set()
            out: list[str] = []
            for t in tickers:
                if isinstance(t, str) and t and t not in seen:
                    seen.add(t)
                    out.append(t)
            if out:
                return out
    except Exception:
        pass
    try:
        fixed = getattr(strategy, "FIXED_TICKER", None)
        if isinstance(fixed, str) and fixed:
            return [fixed]
    except Exception:
        pass
    return []


def _holding_tickers(strategy: Any) -> list[str]:
    try:
        positions = getattr(getattr(strategy, "state", None), "positions", None)
        if isinstance(positions, dict):
            return [t for t in positions.keys() if isinstance(t, str) and t]
    except Exception:
        pass
    return []


def _buy_price(strategy: Any, ticker: str) -> "float | None":
    try:
        positions = getattr(getattr(strategy, "state", None), "positions", None)
        if not isinstance(positions, dict):
            return None
        pos = positions.get(ticker)
        bp = getattr(pos, "buy_price", None)
        if _is_finite_number(bp) and float(bp) > 0:
            return float(bp)
    except Exception:
        pass
    return None


def _llm_context_for(strategy: Any, ticker: str) -> dict:
    try:
        fn = getattr(strategy, "llm_context", None)
        if not callable(fn):
            return {}
        ctx = fn(ticker)
        if isinstance(ctx, dict):
            return dict(ctx)
    except Exception:
        pass
    return {}


def _augment_with_atr_ratio(ctx: dict, buy_price: "float | None") -> dict:
    """보유 종목만 — ATR 계열 키에 매수가 대비 비율(`<key>_to_buy_price_pct`)을 더한다."""
    if not ctx or buy_price is None or buy_price <= 0:
        return ctx
    out = dict(ctx)
    for key in _ATR_LIKE_KEYS:
        v = ctx.get(key)
        if _is_finite_number(v):
            try:
                out[f"{key}_to_buy_price_pct"] = round(float(v) / buy_price * 100.0, 4)
            except Exception:
                pass
    return out


def collect_strategy_core_metrics(strategy: Any) -> dict:
    """전략 하나의 후보·보유 핵심값 분포. never-raise — 실패하면 빈 버킷 둘을 돌려준다.

    반환 = `{"candidates": {n_tickers, n_with_context, keys}, "holdings": {...}}`.
    `keys` 의 각 항목은 가격 무관 비율(`_apply_price_ratio_rules`)과 `unit` 칸이 붙은
    원값을 함께 담는다(보유만 매수가 대비 비율도 추가).
    """
    try:
        candidate_tickers = _candidate_tickers(strategy)
        holding_tickers = _holding_tickers(strategy)

        cand_rows: list[dict] = []
        for t in candidate_tickers:
            ctx = _llm_context_for(strategy, t)
            if not ctx:
                continue
            cand_rows.append(_apply_price_ratio_rules(ctx))

        hold_rows: list[dict] = []
        for t in holding_tickers:
            ctx = _llm_context_for(strategy, t)
            if not ctx:
                continue
            ctx = _apply_price_ratio_rules(ctx)
            ctx = _augment_with_atr_ratio(ctx, _buy_price(strategy, t))
            hold_rows.append(ctx)

        return {
            "candidates": {
                "n_tickers": len(candidate_tickers),
                "n_with_context": len(cand_rows),
                "keys": build_key_distributions(cand_rows),
            },
            "holdings": {
                "n_tickers": len(holding_tickers),
                "n_with_context": len(hold_rows),
                "keys": build_key_distributions(hold_rows),
            },
        }
    except Exception:
        return {"candidates": dict(_EMPTY_BUCKET), "holdings": dict(_EMPTY_BUCKET)}


def collect_all_core_metrics(strategies: Iterable[Any]) -> dict[str, dict]:
    """전략 목록 → `{strategy_id: collect_strategy_core_metrics(...)}`. never-raise."""
    out: dict[str, dict] = {}
    try:
        for s in strategies:
            sid = getattr(s, "strategy_id", None)
            if not isinstance(sid, str) or not sid:
                continue
            out[sid] = collect_strategy_core_metrics(s)
    except Exception:
        pass
    return out


def has_any_keys(core_metrics: "dict | None") -> bool:
    """`collect_strategy_core_metrics` 결과에 실제로 분포 키가 하나라도 있는가.

    20:00 자문 payload 에 빈 분포(둘 다 `keys={}`)를 실어 토큰을 낭비하지 않으려고
    호출부(`recommendation_engine.py`)가 포함 여부를 정할 때 쓴다.
    """
    if not isinstance(core_metrics, dict):
        return False
    for bucket in ("candidates", "holdings"):
        b = core_metrics.get(bucket)
        if isinstance(b, dict) and b.get("keys"):
            return True
    return False
