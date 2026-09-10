/**
 * cycle278 — 전략 파라미터 편집기 (카탈로그 기반, 편집기의 **유일한** 구현).
 *
 * 명세: `_workspace/red/cycle278_param_catalog_ui_spec.md` §3.5(C37~C44) · §6
 *
 * 왜 이 컴포넌트가 키를 하나도 모르는가 —
 * 종전 화면은 24키 라벨 화이트리스트 ∩ `typeof === 'number'` 로 이중
 * 게이팅해서 99키 중 73키가 구조적으로 편집 불가였고, `bool`/`str`/`enum`/`list_str` 키는
 * **영원히** 화면에 올 수 없었다. 화면이 키를 자기 안에 적어 두면 백엔드가 키를 늘려도
 * 화면은 모른다. 그래서 이 파일은 `GET /api/strategies/params-schema` 응답만으로 렌더하고
 * 라벨·단위·범위·선택지·위험도를 전부 그 응답에서 읽는다.
 * 회귀 가드 = `__tests__/_ast_param_key_hardcode.test.ts` (키 리터럴 0건).
 *
 * 포맷 분기도 **키가 아니라 `type`/`unit`** 으로 한다 — 접미사 `_pct` 가 퍼센트와 비율
 * 두 규약에 모두 쓰이므로 이름 기반 추론은 폐기된 단위 추론 휴리스틱의 재현이다.
 *
 * 저장은 **변경분만** 보낸다. 패널이 연 키 전체를 매번 보내면 그중 한 키의 범위 위반이
 * 전략 전체 저장을 422 로 막는다(구 패널의 실제 결함).
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import ConfirmModal from './ConfirmModal'
import { getStrategyParamsSchema } from '../api/strategies'
import { ParamValidationError, updateStrategyParams } from '../api/trading'
import type {
  ParamErrorDetail,
  ParamWarningDetail,
  StrategyParamValue,
} from '../api/trading'
import type {
  ParamChoice,
  ParamForbiddenChoice,
  ParamSpec,
  ParamStrategySchema,
  ParamValue,
  ParamsSchemaData,
} from '../types/strategy-params'
import { isKrxMainSession } from '../utils/kst'

/** 편집 중 입력 상태. 숫자·문자열은 raw string, bool 은 boolean, 다중선택은 string[]. */
type Draft = string | boolean | string[]

/** testid 접미 규약 — 밑줄은 하이픈으로 (`Strategies.tsx` 요약 그리드 관례 계승). */
const dash = (value: string) => value.replace(/_/g, '-')

const NUMERIC_TYPES = ['int', 'float', 'percent']
const isNumeric = (spec: ParamSpec) => NUMERIC_TYPES.includes(spec.type)

/** 부동소수 잡음 제거 — `0.1 * 100 === 10.000000000000002` 을 화면·저장에서 모두 걷어낸다. */
const roundish = (value: number, digits = 10): number => Number(value.toFixed(digits))

/** 입력칸에 넣을 숫자 문자열. 천단위 구분자를 넣지 않는다(`Number()` 왕복이 깨진다). */
function numberToDraft(spec: ParamSpec, value: number): string {
  return String(roundish(spec.type === 'percent' ? value * 100 : value))
}

/** 사람이 읽는 숫자 — 천단위 구분자 포함. */
function humanNumber(value: number): string {
  return roundish(value, 6).toLocaleString('ko-KR', { maximumFractionDigits: 6 })
}

/** 선택지 값은 문자열이 아닐 수 있다(null·boolean 실재) — `<option value>` 용 인코딩. */
const encodeChoice = (value: ParamChoice['value']): string =>
  typeof value === 'string' ? value : JSON.stringify(value)

function findChoice(spec: ParamSpec, encoded: string): ParamChoice | undefined {
  return spec.choices.find((choice) => encodeChoice(choice.value) === encoded)
}

/** 숫자를 `unit` 으로만 분기해 사람 말로 — 키를 보지 않는다. */
function formatNumberWithUnit(spec: ParamSpec, value: number): string {
  if (spec.unit === '원') {
    const abs = Math.abs(value)
    if (abs >= 100_000_000) return `${humanNumber(value / 100_000_000)}억원`
    if (abs >= 10_000) return `${humanNumber(value / 10_000)}만원`
    return `${humanNumber(value)}원`
  }
  return `${humanNumber(value)}${spec.unit}`
}

/** 저장값 → 화면 표기. `percent` 는 표시만 %, 저장은 비율이다. */
function displayValue(spec: ParamSpec, value: ParamValue | undefined): string {
  if (value === undefined) return '—'
  if (spec.type === 'bool') return value ? '사용' : '미사용'
  if (spec.type === 'enum') {
    const choice = findChoice(spec, encodeChoice(value as ParamChoice['value']))
    return choice ? choice.label_ko : String(value)
  }
  if (spec.type === 'list_str') {
    if (!Array.isArray(value) || value.length === 0) return '(없음)'
    return value
      .map((item) => findChoice(spec, item)?.label_ko ?? item)
      .join(', ')
  }
  if (value === null) return '—'
  if (isNumeric(spec) && typeof value === 'number') {
    if (spec.type === 'percent') return `${humanNumber(roundish(value * 100))}%`
    return formatNumberWithUnit(spec, value)
  }
  const text = String(value)
  return text === '' ? '(없음)' : text
}

/** 저장값 → 편집 입력 초기 상태. */
function toDraft(spec: ParamSpec, value: ParamValue | undefined): Draft {
  if (spec.type === 'bool') return value === true
  if (spec.type === 'enum') return encodeChoice((value ?? null) as ParamChoice['value'])
  if (spec.type === 'list_str') {
    const items = Array.isArray(value) ? value.map((item) => String(item)) : []
    return spec.choices.length > 0 ? items : items.join(', ')
  }
  if (isNumeric(spec)) {
    return typeof value === 'number' ? numberToDraft(spec, value) : ''
  }
  return value === null || value === undefined ? '' : String(value)
}

/** 편집 입력 → 저장값. 해석 불가면 `ok:false` (그 키는 변경분에서 빠진다). */
function fromDraft(spec: ParamSpec, draft: Draft): { ok: boolean; value: ParamValue } {
  if (spec.type === 'bool') return { ok: true, value: draft === true }
  if (spec.type === 'enum') {
    const choice = findChoice(spec, String(draft))
    return choice ? { ok: true, value: choice.value as ParamValue } : { ok: false, value: null }
  }
  if (spec.type === 'list_str') {
    if (Array.isArray(draft)) return { ok: true, value: [...draft] }
    const items = String(draft)
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
    return { ok: true, value: items }
  }
  if (isNumeric(spec)) {
    const raw = String(draft).trim()
    if (raw === '') return { ok: false, value: null }
    const parsed = Number(raw)
    if (!Number.isFinite(parsed)) return { ok: false, value: null }
    return { ok: true, value: spec.type === 'percent' ? roundish(parsed / 100, 12) : parsed }
  }
  return { ok: true, value: String(draft) }
}

const sameValue = (a: ParamValue | undefined, b: ParamValue | undefined): boolean =>
  JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

export interface ChangeRow {
  spec: ParamSpec
  before: ParamValue | undefined
  after: ParamValue
}

/** 그 전략에서 이 키에 금지된 선택지들. */
const forbiddenFor = (spec: ParamSpec, strategyId: string): ParamForbiddenChoice[] =>
  spec.forbidden_choices.filter((item) => item.strategy_id === strategyId)

const isForbiddenValue = (
  spec: ParamSpec,
  strategyId: string,
  value: ParamChoice['value'],
): ParamForbiddenChoice | undefined =>
  forbiddenFor(spec, strategyId).find((item) => item.value === value)

export interface LocalBlock {
  key: string
  msg: string
}

/**
 * 저장 전 화면 단계 차단 — **정본은 서버의 422 다.** 여기서 막는 것은 사전 안내이고,
 * curl·구버전 화면·자동화가 같은 조합에 도달할 수 있으므로 서버 검증을 대신하지 않는다.
 *
 * 두 규칙만 본다(둘 다 무증상 사고라서다):
 *  1) 최소 항목 수 미달 — 빈 목록의 효과가 전략마다 정반대다(한쪽은 코드 기본값 폴백으로
 *     아무 일도 안 일어나고, 다른 쪽은 매수 전면 중단). 구 화면(`Settings.tsx` 의
 *     거래소·보드 행)이 막고 있던 규칙이라, 새 편집기가 주 경로가 되면서 사라지면 후퇴다.
 *  2) 전략별 금지 선택지 — 체크박스 한 번으로 명문화된 절대 규칙에 도달하면 규칙이 아니다.
 *     ⚠️ 이 갈래의 UI 경로는 체크박스 `disabled` 가 이미 닫아 두었다(끌 수는 있고 켤 수는
 *     없다). 그래도 남기는 이유 = `disabled` 가 회귀하면 이 갈래가 두 번째 선이 되고,
 *     선택지 목록이 늘거나 `enum` 키에 금지 항목이 생기면 여기가 먼저 잡는다. 그래서
 *     **직접 단위 테스트**로 계약을 잠근다(그 경로가 UI 로 닫혀 있어 화면 조작으로는
 *     붉힐 수 없다 — 그것이 곧 이 export 의 이유다).
 */
export function localBlocks(rows: ChangeRow[], strategyId: string): LocalBlock[] {
  const out: LocalBlock[] = []
  for (const { spec, after } of rows) {
    const selected: ParamChoice['value'][] = Array.isArray(after)
      ? after
      : [after as ParamChoice['value']]
    for (const value of selected) {
      const hit = isForbiddenValue(spec, strategyId, value)
      if (hit) {
        const label = spec.choices.find((c) => c.value === value)?.label_ko ?? String(value)
        out.push({
          key: spec.key,
          msg: `${spec.label_ko}에 '${label}' 은(는) 이 전략에서 선택할 수 없습니다 — ${hit.reason}`,
        })
      }
    }
    if (Array.isArray(after) && after.length < spec.min_items) {
      out.push({
        key: spec.key,
        msg:
          `${spec.label_ko}은(는) 최소 ${spec.min_items}개를 선택해야 합니다.` +
          ' 비우면 전략에 따라 코드 기본값으로 되돌아가거나(저장했는데 아무 일도 일어나지' +
          ' 않는다) 매수가 전면 중단됩니다.' +
          ' 매수를 멈추려면 목록을 비우지 말고 전략을 비활성화하세요.',
      })
    }
  }
  return out
}

const BADGE_BASE = 'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium'

export interface StrategyParamsEditorProps {
  strategyId: string
  onClose: () => void
  /** 장중 배너 판정의 테스트 seam. 생략 시 현재 시각. */
  now?: Date
}

export default function StrategyParamsEditor({
  strategyId,
  onClose,
  now,
}: StrategyParamsEditorProps) {
  const queryClient = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['strategy-params-schema'],
    queryFn: getStrategyParamsSchema,
    retry: 1, // 사이클 65 H3 영속 — 미명시 시 백엔드 부재 환경에서 패널이 뜨지 않는다
    staleTime: 60_000,
  })

  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [identityAck, setIdentityAck] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [errors, setErrors] = useState<ParamErrorDetail[]>([])
  const [warnings, setWarnings] = useState<ParamWarningDetail[]>([])

  const schema: ParamsSchemaData | undefined = data
  const strategy: ParamStrategySchema | undefined = useMemo(
    () => schema?.strategies.find((item) => item.strategy_id === strategyId),
    [schema, strategyId],
  )

  /** 이 전략에 적용되는 스펙만, `data.params` 순서 그대로. */
  const specs: ParamSpec[] = useMemo(() => {
    if (!schema || !strategy) return []
    const owned = new Set(strategy.keys)
    return schema.params.filter((spec) => owned.has(spec.key))
  }, [schema, strategy])

  const draftOf = (spec: ParamSpec): Draft =>
    spec.key in drafts ? drafts[spec.key] : toDraft(spec, strategy?.params[spec.key])

  const setDraft = (key: string, value: Draft) => {
    setDrafts((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => prev.filter((item) => item.key !== key))
    setWarnings([])
  }

  /** 변경분 — 요청에 실리는 것은 이것뿐이다. */
  const changes: ChangeRow[] = useMemo(() => {
    if (!strategy) return []
    const rows: ChangeRow[] = []
    for (const spec of specs) {
      if (!spec.editable) continue
      if (!(spec.key in drafts)) continue
      const parsed = fromDraft(spec, drafts[spec.key])
      if (!parsed.ok) continue
      const before = strategy.params[spec.key]
      if (sameValue(before, parsed.value)) continue
      rows.push({ spec, before, after: parsed.value })
    }
    return rows
  }, [specs, drafts, strategy])

  const identityChanges = changes.filter((row) => row.spec.risk === 'identity')
  const needsAck = identityChanges.length > 0

  /** 서버에 보내기 전에 잡는 두 규칙(최소 항목 수 · 전략별 금지 선택지). */
  const blocks = useMemo(() => localBlocks(changes, strategyId), [changes, strategyId])

  const mutation = useMutation({
    mutationFn: (params: Record<string, StrategyParamValue>) =>
      updateStrategyParams(strategyId, params),
    onSuccess: (result) => {
      setShowConfirm(false)
      setErrors([])
      const nextWarnings = result.warnings ?? []
      setWarnings(nextWarnings)
      setDrafts({})
      setIdentityAck(false)
      queryClient.invalidateQueries({ queryKey: ['strategies'] })
      queryClient.invalidateQueries({ queryKey: ['strategy-params-schema'] })
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      // 경고가 있으면 패널을 열어 둔다 — 닫으면 "저장은 됐지만 이런 사정이 있다" 가 사라진다.
      if (nextWarnings.length === 0) onClose()
    },
    onError: (err: Error) => {
      setShowConfirm(false)
      setWarnings([])
      if (err instanceof ParamValidationError && err.details.length > 0) {
        setErrors(err.details)
      } else {
        setErrors([{ key: null, code: 'request_failed', msg: err.message }])
      }
    },
  })

  const submit = () => {
    const params: Record<string, StrategyParamValue> = {}
    for (const row of changes) params[row.spec.key] = row.after as StrategyParamValue
    mutation.mutate(params)
  }

  const fieldErrors = (key: string) => errors.filter((item) => item.key === key)
  const formErrors = errors.filter((item) => !item.key)

  const marketOpen = isKrxMainSession(now)
  const saveDisabled =
    changes.length === 0 ||
    blocks.length > 0 ||
    (needsAck && !identityAck) ||
    mutation.isPending

  const confirmMessage = (() => {
    const head = `${strategy?.name ?? strategyId} 파라미터 ${changes.length}개를 변경합니다.`
    const identityNote = needsAck
      ? ` 리스크 정체성 상수 ${identityChanges.length}개가 포함됩니다.`
      : ''
    const timing = marketOpen
      ? ' 지금은 장중이라 저장 즉시 다음 판정부터 적용됩니다.'
      : ' 저장 즉시 반영되며 다음 판정부터 사용됩니다.'
    return `${head}${identityNote}${timing}`
  })()

  return (
    <div className="fixed inset-0 z-40 flex items-start justify-center bg-black/40 overflow-y-auto p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl my-4">
        {isLoading && (
          <div data-testid="strategy-params-loading" className="p-6 text-sm text-gray-500">
            파라미터 스키마 로딩 중...
          </div>
        )}

        {!isLoading && isError && (
          <div className="p-6">
            <p data-testid="strategy-params-load-error" className="text-sm text-red-600">
              서버 연결 끊김 — 파라미터 스키마를 불러오지 못했습니다.
            </p>
            <button
              onClick={onClose}
              className="mt-4 px-3 py-1.5 text-sm text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            >
              닫기
            </button>
          </div>
        )}

        {!isLoading && !isError && schema && !strategy && (
          <div className="p-6">
            <p data-testid="strategy-params-empty" className="text-sm text-gray-500">
              이 전략의 파라미터 정보가 없습니다 — 등록된 전략인지 확인하세요.
            </p>
            <button
              onClick={onClose}
              className="mt-4 px-3 py-1.5 text-sm text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            >
              닫기
            </button>
          </div>
        )}

        {!isLoading && !isError && schema && strategy && (
          <div data-testid="strategy-params-editor">
            {/* 헤더 */}
            <div className="flex items-start justify-between p-4 border-b border-gray-200">
              <div>
                <h2
                  data-testid="strategy-params-title"
                  className="text-base font-semibold text-gray-900"
                >
                  {strategy.name} 파라미터
                </h2>
                <p className="text-xs text-gray-500">
                  설정 가능한 {specs.length}개 항목 · 카탈로그{' '}
                  <span data-testid="strategy-params-version">{schema.catalog_version}</span>
                </p>
              </div>
              <button
                data-testid="strategy-params-close"
                aria-label="닫기"
                onClick={onClose}
                className="px-2 py-1 text-gray-400 hover:text-gray-700 rounded"
              >
                ×
              </button>
            </div>

            {/* 장중 경고 */}
            {marketOpen && (
              <div
                data-testid="strategy-params-market-warning"
                className="mx-4 mt-4 p-3 bg-amber-50 border border-amber-300 rounded-lg text-xs text-amber-800"
              >
                지금은 KRX 정규장(09:00~15:30) 중입니다 — 저장하면 <strong>즉시 반영</strong>되어
                다음 판정부터 새 값이 쓰입니다. NXT 프리(08:00~09:00)·애프터(15:40~20:00)
                시간대에도 즉시 반영됩니다.
              </div>
            )}

            {/* 그룹 아코디언 */}
            <div className="p-4 space-y-3">
              {schema.groups.map((group) => {
                const groupSpecs = specs.filter((spec) => spec.group === group.id)
                if (groupSpecs.length === 0) return null
                const isOpen = !collapsed[group.id]
                return (
                  <div key={group.id} className="border border-gray-200 rounded-lg">
                    <button
                      data-testid={`strategy-params-group-${group.id}`}
                      onClick={() =>
                        setCollapsed((prev) => ({ ...prev, [group.id]: !prev[group.id] }))
                      }
                      className="w-full flex items-center justify-between px-3 py-2 text-left bg-gray-50 rounded-t-lg hover:bg-gray-100"
                    >
                      <span className="text-sm font-semibold text-gray-800">
                        {group.label_ko}{' '}
                        <span className="text-xs font-normal text-gray-400">
                          {groupSpecs.length}
                        </span>
                      </span>
                      <span className="text-xs text-gray-400">{isOpen ? '▲' : '▼'}</span>
                    </button>
                    {isOpen && (
                      <div
                        data-testid={`strategy-params-group-body-${group.id}`}
                        className="divide-y divide-gray-100"
                      >
                        <p className="px-3 py-1.5 text-[11px] text-gray-400">
                          {group.description}
                        </p>
                        {groupSpecs.map((spec) => (
                          <ParamRow
                            key={spec.key}
                            spec={spec}
                            strategyId={strategyId}
                            current={strategy.params[spec.key]}
                            fallback={strategy.defaults[spec.key]}
                            draft={draftOf(spec)}
                            onChange={(value) => setDraft(spec.key, value)}
                            errors={fieldErrors(spec.key)}
                            blocks={blocks.filter((item) => item.key === spec.key)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>

            {/* 변경분 미리보기 */}
            <div data-testid="strategy-params-diff" className="mx-4 mb-3 p-3 bg-gray-50 rounded-lg">
              <p className="text-xs font-semibold text-gray-700 mb-1">
                변경분 {changes.length}건
              </p>
              {changes.length === 0 ? (
                <p className="text-xs text-gray-400">아직 바꾼 값이 없습니다.</p>
              ) : (
                <ul className="space-y-0.5">
                  {changes.map((row) => (
                    <li
                      key={row.spec.key}
                      data-testid={`strategy-params-diff-row-${dash(row.spec.key)}`}
                      className="text-xs text-gray-700"
                    >
                      <span className="font-medium">{row.spec.label_ko}</span>{' '}
                      <span className="text-gray-400">
                        {displayValue(row.spec, row.before)} →
                      </span>{' '}
                      <span className="font-semibold">{displayValue(row.spec, row.after)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* 저장 전 차단 — 서버 422 를 미리 알려 준다(정본은 서버) */}
            {blocks.length > 0 && (
              <div
                data-testid="strategy-params-local-block"
                className="mx-4 mb-3 p-3 bg-red-50 border border-red-300 rounded-lg space-y-1"
              >
                <p className="text-xs font-semibold text-red-900">
                  저장할 수 없습니다 — {blocks.length}건
                </p>
                {blocks.map((item, idx) => (
                  <p key={`${item.key}-${idx}`} className="text-xs text-red-700">
                    {item.msg}
                  </p>
                ))}
              </div>
            )}

            {/* 정체성 상수 2단계 확인 */}
            {needsAck && (
              <div className="mx-4 mb-3 p-3 bg-red-50 border border-red-200 rounded-lg">
                <label className="flex items-start gap-2 text-xs text-red-700">
                  <input
                    data-testid="strategy-params-identity-ack"
                    type="checkbox"
                    checked={identityAck}
                    onChange={(e) => setIdentityAck(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    리스크 정체성 상수 {identityChanges.length}개(
                    {identityChanges.map((row) => row.spec.label_ko).join(', ')})를 바꿉니다.
                    이 값들은 전략의 위험 크기 자체를 정의합니다 — 확인했습니다.
                  </span>
                </label>
              </div>
            )}

            {/* 폼 레벨 오류 (불변식 등 특정 칸에 못 붙는 것) */}
            {formErrors.length > 0 && (
              <div
                data-testid="strategy-params-form-error"
                className="mx-4 mb-3 p-3 bg-red-50 border border-red-200 rounded-lg space-y-1"
              >
                {formErrors.map((item, idx) => (
                  <p key={`${item.code}-${idx}`} className="text-xs text-red-700">
                    {item.msg}
                  </p>
                ))}
              </div>
            )}

            {/* 저장은 됐지만 알아야 하는 것 */}
            {warnings.length > 0 && (
              <div
                data-testid="strategy-params-warnings"
                className="mx-4 mb-3 p-3 bg-amber-50 border border-amber-200 rounded-lg space-y-1"
              >
                <p className="text-xs font-semibold text-amber-900">
                  저장했습니다 — 확인할 사항 {warnings.length}건
                </p>
                {warnings.map((item, idx) => (
                  <p
                    key={`${item.code}-${idx}`}
                    data-testid={`strategy-params-warning-${item.code}`}
                    className="text-xs text-amber-800"
                  >
                    {item.msg}
                  </p>
                ))}
              </div>
            )}

            {/* 액션 */}
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200">
              <button
                data-testid="strategy-params-cancel"
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
              >
                변경 취소
              </button>
              <button
                data-testid="strategy-params-save"
                onClick={() => setShowConfirm(true)}
                disabled={saveDisabled}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                저장
              </button>
            </div>
          </div>
        )}
      </div>

      <ConfirmModal
        open={showConfirm}
        title="전략 파라미터 변경"
        message={confirmMessage}
        onConfirm={submit}
        onCancel={() => setShowConfirm(false)}
        loading={mutation.isPending}
      />
    </div>
  )
}

// ── 키 1개 행 ───────────────────────────────────────────────────────────────

function ParamRow({
  spec,
  strategyId,
  current,
  fallback,
  draft,
  onChange,
  errors,
  blocks,
}: {
  spec: ParamSpec
  strategyId: string
  current: ParamValue | undefined
  fallback: ParamValue | undefined
  draft: Draft
  onChange: (value: Draft) => void
  errors: ParamErrorDetail[]
  blocks: LocalBlock[]
}) {
  const id = dash(spec.key)
  const disabled = !spec.editable
  const inactiveHere = spec.deprecated_for.includes(strategyId)
  const modified = !sameValue(current, fallback)
  const parsed = fromDraft(spec, draft)
  const unparsable = spec.editable && !parsed.ok

  return (
    <div
      data-testid={`strategy-params-row-${id}`}
      className={`px-3 py-2 ${spec.deprecated ? 'bg-gray-50' : ''}`}
    >
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span
          className={`text-sm font-medium ${spec.deprecated ? 'text-gray-400' : 'text-gray-800'}`}
        >
          {spec.label_ko}
        </span>
        {spec.risk === 'identity' && (
          <span
            data-testid={`strategy-params-badge-identity-${id}`}
            className={`${BADGE_BASE} bg-red-50 text-red-700`}
          >
            정체성 상수
          </span>
        )}
        {spec.auto_tunable && (
          <span
            data-testid={`strategy-params-badge-autotune-${id}`}
            className={`${BADGE_BASE} bg-blue-50 text-blue-700`}
          >
            AI 자동조정
          </span>
        )}
        {spec.deprecated && (
          <span
            data-testid={`strategy-params-badge-deprecated-${id}`}
            className={`${BADGE_BASE} bg-gray-200 text-gray-500`}
          >
            미사용
          </span>
        )}
        {inactiveHere && (
          <span
            data-testid={`strategy-params-badge-inactive-${id}`}
            className={`${BADGE_BASE} bg-amber-100 text-amber-800`}
          >
            이 전략에선 무효
          </span>
        )}
        {spec.range_src === 'none' && (
          <span
            data-testid={`strategy-params-badge-unbounded-${id}`}
            className={`${BADGE_BASE} bg-amber-50 text-amber-700`}
          >
            범위 근거 없음
          </span>
        )}
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-2">
        <ParamInput
          spec={spec}
          strategyId={strategyId}
          draft={draft}
          disabled={disabled}
          onChange={onChange}
        />

        <span className="text-xs text-gray-500">
          현재{' '}
          <span data-testid={`strategy-params-current-${id}`} className="font-medium text-gray-700">
            {displayValue(spec, current)}
          </span>
        </span>
        <span className="text-xs text-gray-400">
          기본{' '}
          <span data-testid={`strategy-params-default-${id}`}>{displayValue(spec, fallback)}</span>
        </span>
        {modified && !disabled && (
          <button
            data-testid={`strategy-params-reset-${id}`}
            onClick={() => onChange(toDraft(spec, fallback))}
            className="text-xs text-blue-600 hover:underline"
          >
            기본값으로 되돌리기
          </button>
        )}
      </div>

      {spec.min !== null || spec.max !== null ? (
        <p className="mt-0.5 text-[11px] text-gray-400">
          허용 범위 {spec.min === null ? '제한 없음' : humanNumber(spec.min)} ~{' '}
          {spec.max === null ? '제한 없음' : humanNumber(spec.max)}
        </p>
      ) : null}

      {unparsable && (
        <p
          data-testid={`strategy-params-invalid-${id}`}
          className="mt-0.5 text-[11px] text-amber-700"
        >
          값을 해석할 수 없어 변경분에서 제외했습니다.
        </p>
      )}

      {blocks.map((item, idx) => (
        <p
          key={`block-${idx}`}
          data-testid={`strategy-params-block-${id}`}
          className="mt-0.5 text-[11px] text-red-600"
        >
          {item.msg}
        </p>
      ))}

      {errors.map((item, idx) => (
        <p
          key={`${item.code}-${idx}`}
          data-testid={`strategy-params-error-${id}`}
          className="mt-0.5 text-[11px] text-red-600"
        >
          {item.msg}
        </p>
      ))}

      {spec.help && (
        <details className="mt-1">
          <summary className="text-[11px] text-gray-400 cursor-pointer">설명</summary>
          <p
            data-testid={`strategy-params-help-${id}`}
            className="mt-0.5 text-[11px] text-gray-500 whitespace-pre-line"
          >
            {spec.help}
          </p>
        </details>
      )}
    </div>
  )
}

// ── 타입별 입력 위젯 ────────────────────────────────────────────────────────

function ParamInput({
  spec,
  strategyId,
  draft,
  disabled,
  onChange,
}: {
  spec: ParamSpec
  strategyId: string
  draft: Draft
  disabled: boolean
  onChange: (value: Draft) => void
}) {
  const id = dash(spec.key)
  const inputClass =
    'px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-400'

  if (spec.type === 'bool') {
    return (
      <input
        data-testid={`strategy-params-checkbox-${id}`}
        type="checkbox"
        checked={draft === true}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        aria-label={spec.label_ko}
      />
    )
  }

  if (spec.type === 'enum') {
    return (
      <select
        data-testid={`strategy-params-select-${id}`}
        value={String(draft)}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        aria-label={spec.label_ko}
        className={inputClass}
      >
        {spec.choices.map((choice) => {
          const forbidden = isForbiddenValue(spec, strategyId, choice.value)
          return (
            <option
              key={encodeChoice(choice.value)}
              value={encodeChoice(choice.value)}
              disabled={forbidden !== undefined}
              title={forbidden?.reason}
            >
              {choice.label_ko}
              {forbidden ? ' (이 전략에서 금지)' : ''}
            </option>
          )
        })}
      </select>
    )
  }

  if (spec.type === 'list_str' && spec.choices.length > 0) {
    const selected = Array.isArray(draft) ? draft : []
    return (
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {spec.choices.map((choice) => {
          const value = String(choice.value)
          // 전략별 금지 선택지는 **끌 수는 있고 켤 수는 없다** — 이미 켜진 위반 상태를
          // 화면에서 되돌릴 길이 막히면 복구 수단이 DB 직접 UPDATE 뿐이 된다.
          const forbidden = isForbiddenValue(spec, strategyId, choice.value)
          const checked = selected.includes(value)
          const lock = forbidden !== undefined && !checked
          return (
            <label
              key={value}
              title={forbidden?.reason}
              className={`inline-flex items-center gap-1 text-xs ${
                lock ? 'text-gray-400 cursor-not-allowed' : 'text-gray-700'
              }`}
            >
              <input
                data-testid={`strategy-params-choice-${id}-${dash(value)}`}
                type="checkbox"
                checked={checked}
                disabled={disabled || lock}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...selected, value]
                      : selected.filter((item) => item !== value),
                  )
                }
              />
              <span className={choice.deprecated || lock ? 'text-gray-400' : ''}>
                {choice.label_ko}
                {forbidden ? ' (이 전략에서 금지)' : ''}
              </span>
            </label>
          )
        })}
      </div>
    )
  }

  // list_str(자유 입력) · str · int · float · percent — 전부 텍스트 입력.
  // 숫자에 `type="number"` 를 쓰지 않는다(브라우저별 스피너·로케일 파싱 편차).
  const isNumberish = isNumeric(spec)
  return (
    <input
      data-testid={`strategy-params-input-${id}`}
      type="text"
      inputMode={isNumberish ? 'decimal' : 'text'}
      value={typeof draft === 'string' ? draft : ''}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      aria-label={spec.label_ko}
      className={`${inputClass} ${isNumberish ? 'w-28' : 'w-56'}`}
      placeholder={spec.pattern ?? ''}
    />
  )
}
