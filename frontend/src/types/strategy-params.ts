/**
 * cycle278 — 전략 파라미터 카탈로그 스키마 타입 (`GET /api/strategies/params-schema`).
 *
 * 백엔드 `src/engine/param_catalog.py` 가 **단일 진실원**이다. 화면은 이 응답만으로
 * 렌더하고 키 이름을 소스에 적지 않는다 — 적는 순간 카탈로그가 둘이 되고, 백엔드가
 * 키를 늘려도 화면은 모르는 드리프트가 다시 시작된다(회귀 가드
 * `components/__tests__/_ast_param_key_hardcode.test.ts`).
 *
 * 포맷 분기도 **키가 아니라 `type`/`unit`** 으로 한다. 접미사 `_pct` 가 퍼센트와
 * 비율 두 규약에 모두 쓰이므로 이름 기반 추론은 폐기된
 * `v / 100 if v > 1 else v` 휴리스틱의 재현이다(루트 CLAUDE.md "비중 단위 추론 변환 금지").
 */

/** 저장 단위 그대로의 파라미터 값. `percent` 타입도 저장은 비율(0.0~1.0)이다. */
export type ParamValue = number | string | string[] | boolean | null

/** `type="enum"` / choices 있는 `list_str` 의 선택지. 값 집합에 null·boolean 이 실재한다. */
export interface ParamChoice {
  value: string | number | boolean | null
  label_ko: string
  /** 값 호환을 위해 목록에는 남기되 "이제 효력이 없다" 를 화면에 밝힌다. */
  deprecated: boolean
  help: string
}

/**
 * 그 전략에서만 금지된 선택지. 값 자체는 어휘 안에 있지만 그 전략에 넣으면 명문화된
 * 절대 규칙을 깬다(유일한 실재 사례 = 변동성돌파 + NXT 애프터마켓).
 * 화면은 해당 체크박스를 비활성으로 그리고 `reason` 을 툴팁으로 보여준다 —
 * **정본은 서버의 422 다**(화면 비활성은 사전 안내일 뿐이다).
 */
export interface ParamForbiddenChoice {
  strategy_id: string
  value: string | number | boolean | null
  reason: string
}

/** 카탈로그 1 키의 스펙. 닫힌 어휘(`types`/`units`/`risks`)는 응답이 함께 준다. */
export interface ParamSpec {
  key: string
  label_ko: string
  group: string
  /** `int|float|percent|bool|enum|list_str|str` */
  type: string
  min: number | null
  max: number | null
  step: number | null
  unit: string
  /** false = 값이 매매를 바꾸지 않는다(레거시). 입력 비활성 + 저장 시 422. */
  editable: boolean
  /** `normal|high|identity` — identity 는 저장 전 2단계 확인 대상. */
  risk: string
  /** AI 자동 튜너(`PARAM_RANGES`) 대상 여부. 화면 편집 가능성과는 별개다. */
  auto_tunable: boolean
  deprecated: boolean
  /** 그 전략에서만 현재 설정상 효력 없음(예: VB 의 야간 K값). */
  deprecated_for: string[]
  /** `param_ranges|structural|sign|enum|none` — `none` 은 범위 근거 없음. */
  range_src: string
  pattern: string | null
  /**
   * `list_str` 최소 항목 수. 0 = 빈 목록 허용.
   * 빈 목록의 뜻이 키마다 정반대라(제외 종목코드는 "제외 없음" 이 정상,
   * 매매 허용 보드는 전략 절반에서 매수 전면 중단 / 나머지 절반에서 기본 보드 폴백)
   * 화면이 추론하지 않고 이 값을 읽는다.
   */
  min_items: number
  forbidden_choices: ParamForbiddenChoice[]
  choices: ParamChoice[]
  applies_to: string[]
  help: string
}

export interface ParamGroup {
  id: string
  label_ko: string
  description: string
}

export interface ParamStrategySchema {
  strategy_id: string
  name: string
  enabled: boolean
  /** 이 전략의 `DEFAULT_PARAMS` 키 목록. 화면은 이 목록으로만 행을 만든다. */
  keys: string[]
  /** 현재 저장값 — 스키마 응답이 정본이다(별도 쿼리와 섞으면 diff 기준이 낡는다). */
  params: Record<string, ParamValue>
  /** 코드 기본값(`DEFAULT_PARAMS`) 깊은 복사본. */
  defaults: Record<string, ParamValue>
  deprecated_for_keys: string[]
}

export interface ParamBudgetInvariant {
  expr: string
  keys: string[]
  enforced: boolean
  description: string
}

export interface ParamOrderInvariant {
  lo_key: string
  hi_key: string
  strategies: string[]
  enforced: boolean
  consequence: string
}

export interface ParamsSchemaData {
  catalog_version: string
  groups: ParamGroup[]
  types: string[]
  risks: string[]
  units: string[]
  params: ParamSpec[]
  strategies: ParamStrategySchema[]
  invariants: {
    budget: ParamBudgetInvariant
    order: ParamOrderInvariant[]
  }
}
