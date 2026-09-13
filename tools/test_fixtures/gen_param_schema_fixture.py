"""cycle278 — 프론트/E2E 목이 쓰는 `params-schema` 골든 픽스처 생성기.

실행:
    python tools/test_fixtures/gen_param_schema_fixture.py

산출:
    frontend/src/test/fixtures/paramSchema.fixture.ts   (MSW + vitest)
    e2e/fixtures/param-schema.fixture.ts                (Playwright)

두 파일은 **손으로 고치지 않는다.** `src/engine/param_catalog.py` 나 7 전략의
`DEFAULT_PARAMS` 가 바뀌면 이 스크립트를 다시 돌린다.

왜 생성인가 — cycle266(종목마스터 일봉 탭)은 MSW·Playwright·컴포넌트 목 세 곳이
`change_rate` 를 전부 진짜 number 로 만들어 *의도한 계약*만 담고 *실제 응답*(pydantic v2 가
`Decimal` 을 문자열로 직렬화)을 담지 않아 3개월 넘게 초록이었다. 목이 코드에서 나오면
그 형태의 괴리가 생기지 않는다.

⚠️ 이 스크립트는 전략 모듈을 import 하므로 `src/config.py` 의 필수 환경변수가 필요하다
(값은 무엇이든 상관없다 — 카탈로그·DEFAULT_PARAMS 만 읽는다):
    KIS_APP_KEY=x KIS_APP_SECRET=x KIS_ACCOUNT_NO=x SUPABASE_URL=http://x SUPABASE_KEY=x \
        python tools/test_fixtures/gen_param_schema_fixture.py
"""

import importlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.engine import param_catalog as pc  # noqa: E402

STRAT_CLASSES = {
    "momentum": ("momentum", "MomentumStrategy", "상한가 모멘텀"),
    "volatility_breakout": ("volatility_breakout", "VolatilityBreakoutStrategy", "변동성 돌파"),
    "long_tail_volatility": ("long_tail_volatility", "LongTailVolatilityStrategy", "롱테일 변동성"),
    "donchian_swing": ("donchian_swing", "DonchianSwingStrategy", "돈치안 스윙"),
    "bull_flag_breakout": ("bull_flag_breakout", "BullFlagBreakoutStrategy", "불플래그 돌파"),
    "vcp_breakout": ("vcp_breakout", "VcpBreakoutStrategy", "VCP 돌파"),
    "kojiro": ("kojiro", "KojiroStrategy", "고지로 대순환"),
}

# 현재값(params)이 기본값(defaults)과 **다른** 키를 전략마다 1개씩 심는다 —
# "현재값/기본값 병기 + 되돌리기" 계약(F09)의 Red 가 성립하려면 차이가 실재해야 한다.
CURRENT_OVERRIDES = {
    "momentum": {"buy_threshold": 27.0},
    "volatility_breakout": {"k_period": 25},
}


def defaults_for(sid: str) -> dict:
    mod_name, cls_name, _ = STRAT_CLASSES[sid]
    mod = importlib.import_module(f"src.engine.strategies.{mod_name}")
    return dict(getattr(mod, cls_name).DEFAULT_PARAMS)


def spec_to_json(s) -> dict:
    return {
        "key": s.key,
        "label_ko": s.label_ko,
        "group": s.group,
        "type": s.type,
        "min": s.min,
        "max": s.max,
        "step": s.step,
        "unit": s.unit,
        "editable": s.editable,
        "risk": s.risk,
        "auto_tunable": s.auto_tunable,
        "deprecated": s.deprecated,
        "deprecated_for": list(s.deprecated_for),
        "range_src": s.range_src,
        "pattern": s.pattern,
        "min_items": s.min_items,
        "forbidden_choices": [
            {"strategy_id": f.strategy_id, "value": f.value, "reason": f.reason}
            for f in s.forbidden_choices
        ],
        "choices": [
            {
                "value": c.value,
                "label_ko": c.label_ko,
                "deprecated": c.deprecated,
                "help": c.help,
            }
            for c in s.choices
        ],
        "applies_to": list(s.applies_to),
        "help": s.help,
    }


def build() -> dict:
    strategies = []
    for sid in pc.STRATEGY_IDS:
        d = defaults_for(sid)
        cur = dict(d)
        cur.update(CURRENT_OVERRIDES.get(sid, {}))
        keys = list(pc.keys_for_strategy(sid))
        strategies.append(
            {
                "strategy_id": sid,
                "name": STRAT_CLASSES[sid][2],
                "enabled": True,
                "keys": keys,
                "params": {k: cur[k] for k in keys},
                "defaults": {k: d[k] for k in keys},
                "deprecated_for_keys": [
                    s.key for s in pc.PARAM_SPECS if sid in s.deprecated_for
                ],
            }
        )

    return {
        "catalog_version": pc.CATALOG_VERSION,
        "groups": [{"id": g[0], "label_ko": g[1], "description": g[2]} for g in pc.GROUPS],
        "types": list(pc.TYPES),
        "risks": list(pc.RISKS),
        "units": list(pc.UNITS),
        "params": [spec_to_json(s) for s in pc.PARAM_SPECS],
        "strategies": strategies,
        "invariants": {
            "budget": {
                "expr": "position_ratio * max_positions <= 1.0",
                "keys": ["position_ratio", "max_positions"],
                "enforced": True,
                "description": pc.BUDGET_INVARIANT,
            },
            "order": [
                {
                    "lo_key": inv.lo_key,
                    "hi_key": inv.hi_key,
                    "strategies": list(inv.strategies),
                    "enforced": inv.enforced,
                    "consequence": inv.consequence,
                }
                for inv in pc.ORDER_INVARIANTS
            ],
        },
    }


TYPES_TS = """export interface ParamSchemaGroup {
  id: string
  label_ko: string
  description: string
}

export interface ParamSchemaChoice {
  /** `nxt_tradable` 처럼 값 집합이 null/boolean 인 enum 이 실재한다 — string 으로 좁히지 않는다. */
  value: string | number | boolean | null
  label_ko: string
  deprecated: boolean
  help: string
}

export interface ParamSchemaForbiddenChoice {
  strategy_id: string
  value: string | number | boolean | null
  reason: string
}

export type ParamSchemaValue = number | string | string[] | boolean | null

export interface ParamSchemaSpec {
  key: string
  label_ko: string
  group: string
  type: string
  min: number | null
  max: number | null
  step: number | null
  unit: string
  editable: boolean
  risk: string
  auto_tunable: boolean
  deprecated: boolean
  deprecated_for: string[]
  range_src: string
  pattern: string | null
  min_items: number
  forbidden_choices: ParamSchemaForbiddenChoice[]
  choices: ParamSchemaChoice[]
  applies_to: string[]
  help: string
}

export interface ParamSchemaStrategy {
  strategy_id: string
  name: string
  enabled: boolean
  keys: string[]
  params: Record<string, ParamSchemaValue>
  defaults: Record<string, ParamSchemaValue>
  deprecated_for_keys: string[]
}

export interface ParamSchemaOrderInvariant {
  lo_key: string
  hi_key: string
  strategies: string[]
  enforced: boolean
  consequence: string
}

export interface ParamSchemaData {
  catalog_version: string
  groups: ParamSchemaGroup[]
  types: string[]
  risks: string[]
  units: string[]
  params: ParamSchemaSpec[]
  strategies: ParamSchemaStrategy[]
  invariants: {
    budget: {
      expr: string
      keys: string[]
      enforced: boolean
      description: string
    }
    order: ParamSchemaOrderInvariant[]
  }
}
"""

HELPERS_TS = """
/** 깊은 복사 — 테스트가 픽스처를 변형해도 원본이 오염되지 않는다. */
export function cloneParamSchema(): ParamSchemaData {
  return JSON.parse(JSON.stringify(PARAM_SCHEMA_FIXTURE)) as ParamSchemaData
}

/** 한 키의 스펙 조회 (없으면 throw — 픽스처 드리프트를 조용히 넘기지 않는다). */
export function fixtureSpec(key: string): ParamSchemaSpec {
  const spec = PARAM_SCHEMA_FIXTURE.params.find((p) => p.key === key)
  if (!spec) throw new Error(`픽스처에 없는 키: ${key}`)
  return spec
}

/** 한 전략의 스키마 조회 (없으면 throw). */
export function fixtureStrategy(strategyId: string): ParamSchemaStrategy {
  const s = PARAM_SCHEMA_FIXTURE.strategies.find((x) => x.strategy_id === strategyId)
  if (!s) throw new Error(`픽스처에 없는 전략: ${strategyId}`)
  return s
}

/** 전략의 현재값(params)만 덮어쓴 스키마 사본. */
export function schemaWithCurrent(
  strategyId: string,
  overrides: Record<string, ParamSchemaValue>,
): ParamSchemaData {
  const clone = cloneParamSchema()
  const target = clone.strategies.find((s) => s.strategy_id === strategyId)
  if (!target) throw new Error(`픽스처에 없는 전략: ${strategyId}`)
  target.params = { ...target.params, ...overrides }
  return clone
}
"""


def render(header: str, data: dict) -> str:
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        header
        + "\n"
        + TYPES_TS
        + "\nexport const PARAM_SCHEMA_FIXTURE: ParamSchemaData = "
        + body
        + "\n"
        + HELPERS_TS
    )


FRONT_HEADER = '''/**
 * cycle278 Red — `GET /api/strategies/params-schema` 응답 **골든 픽스처**.
 *
 * ⚠️ 손으로 쓰지 않는다. `src/engine/param_catalog.py` 의 {n_specs} 스펙과 7 전략
 * `DEFAULT_PARAMS` 에서 **기계 생성**했다 (생성기:
 * `_workspace/red/cycle278_param_catalog_ui_spec.md` §7.4 · 생성 스크립트는 사이클 산출물).
 *
 * 왜 생성인가 — cycle266(종목마스터 일봉 탭) 은 MSW/Playwright/컴포넌트 목 세 곳이
 * `change_rate` 를 전부 진짜 number 로 만들어 *의도한 계약*만 담고 *실제 응답*(pydantic
 * v2 가 `Decimal` 을 문자열로 직렬화)을 담지 않아 3개월 넘게 초록이었다. 그 재발을
 * 막으려면 목이 코드에서 나와야 한다.
 *
 * 현재값(`params`)은 기본값(`defaults`)과 **전략마다 1키씩 일부러 다르다**
 * (momentum `buy_threshold` · volatility_breakout `k_period`) — "현재값/기본값 병기 +
 * 되돌리기" 계약이 차이 없는 픽스처에서는 검증되지 않기 때문이다.
 *
 * Green 이 `frontend/src/types/strategy-params.ts` 를 만들면 여기 로컬 인터페이스를
 * 그 타입의 재수출로 바꿔도 된다(구조는 동일해야 한다).
 */
'''

E2E_HEADER = '''/**
 * cycle278 Red — Playwright 용 `GET /api/strategies/params-schema` 골든 픽스처.
 *
 * `frontend/src/test/fixtures/paramSchema.fixture.ts` 와 **같은 생성기 산출물**이다
 * (e2e 는 frontend tsconfig 밖이라 교차 import 대신 같은 내용을 각자 보유한다).
 * 손으로 고치지 않는다 — 카탈로그가 바뀌면 두 파일을 함께 재생성한다.
 */
'''


def main() -> None:
    data = build()
    front = ROOT / "frontend/src/test/fixtures/paramSchema.fixture.ts"
    e2e = ROOT / "e2e/fixtures/param-schema.fixture.ts"
    front.parent.mkdir(parents=True, exist_ok=True)
    front_header = FRONT_HEADER.format(n_specs=len(data["params"]))
    front.write_text(render(front_header, data), encoding="utf-8")
    e2e.write_text(render(E2E_HEADER, data), encoding="utf-8")
    print("params:", len(data["params"]), "strategies:", len(data["strategies"]))
    print(front, front.stat().st_size)
    print(e2e, e2e.stat().st_size)


main()
