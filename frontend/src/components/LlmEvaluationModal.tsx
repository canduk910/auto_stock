/**
 * cycle276 — AI 매수평가(LLM shadow) 상세 팝업.
 *
 * 사용자 지시(2026-09-11) = "UI의 거래기록(체결, 매매손익)에서 각 행에 AI매매자문 버튼을 달고
 * 버튼 선택 시 팝업형태로 확인가능하도록 함."
 * 정본 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §10.4 / §10.5.
 *
 * ## 이 화면이 지키는 계약
 * - **404 는 오류가 아니다.** 평가 기록이 없는 주문은 회색 안내(`llm-eval-notice`), 500·네트워크는
 *   빨강 오류(`llm-eval-error`). cycle266 이 종목마스터 일봉 탭에서 확정한 분기다 — 둘을 섞으면
 *   "기록이 없다" 와 "서버가 죽었다" 가 같은 화면이 되어 운영자가 원인을 못 가른다.
 * - **`result === 'failed'` 인 기록도 오류가 아니다.** LLM 이 타임아웃·파싱 실패로 점수를 못 냈다는
 *   사실을 담은 정상 기록이며, 실패 사유를 크게 보여 준다(`llm-eval-failed`). "평가 안 함" 과
 *   "평가 실패" 는 반드시 구별돼야 한다(명세 §3 결정 4).
 * - **계좌번호는 마스킹된 값만** 화면에 오른다(`account_no_masked`). 라우트가 원문을 안 보내고
 *   타입에도 원문 키가 없다(C39/C40) — 이 표면은 리포터 키로도 읽힌다(cycle249).
 * - **모든 숫자는 방어 변환**을 거친다. `NUMERIC` 이 문자열로 오는 경로가 다시 생기면
 *   `toFixed` 가 터져 트리 전체가 언마운트된다(cycle266 흰 화면).
 * - **모든 시각은 KST 명시**(`Intl.DateTimeFormat(timeZone:'Asia/Seoul')`).
 *   `new Date(iso).getHours()` 같은 브라우저 로컬타임 추출 금지.
 * - 신규 프론트 의존성 0. 마크다운 렌더러·UI 킷을 들이지 않고, 원문은 `<pre>` 로만 그린다
 *   (`dangerouslySetInnerHTML` 금지 — 모델 출력이 곧 HTML 이 되면 안 된다).
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

import { getLlmEvaluation } from '../api/llm-evaluations'
import type { LlmEvaluation } from '../types/llm-evaluation'

const TITLE_ID = 'llm-eval-modal-title'

// ────────────────────────────────────────────────────────────────────────
// 방어 변환 (cycle266 계열 — 숫자가 문자열로 와도 화면이 죽지 않는다)
// ────────────────────────────────────────────────────────────────────────

function toSafeNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** 정수(원·주·ms·토큰) — 천단위 구분. 변환 실패는 '—'. */
function fmtInt(value: unknown, suffix = ''): string {
  const n = toSafeNumber(value)
  return n === null ? '—' : `${n.toLocaleString('ko-KR')}${suffix}`
}

/** 소수 — 자릿수 명시. 변환 실패는 '—'. */
function fmtFixed(value: unknown, digits: number, suffix = ''): string {
  const n = toSafeNumber(value)
  return n === null ? '—' : `${n.toFixed(digits)}${suffix}`
}

function fmtText(value: unknown): string {
  if (value === null || value === undefined) return '—'
  const s = String(value)
  return s.trim() === '' ? '—' : s
}

/** `key_risks`/`invalidations` 는 타입이 `unknown` — 배열/문자열/그 외를 전부 받아 낸다. */
function toStringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((v) => (typeof v === 'string' ? v : JSON.stringify(v)))
  }
  if (typeof value === 'string') return value.trim() === '' ? [] : [value]
  if (value === null || value === undefined) return []
  return [JSON.stringify(value)]
}

/** `input_payload.tech` 의 지표를 (키, 표시값) 목록으로. 모양이 다르면 빈 목록. */
function extractTech(payload: unknown): Array<[string, string]> {
  if (!payload || typeof payload !== 'object') return []
  const tech = (payload as Record<string, unknown>).tech
  if (!tech || typeof tech !== 'object' || Array.isArray(tech)) return []
  return Object.entries(tech as Record<string, unknown>).map(([k, v]) => {
    const n = toSafeNumber(v)
    return [k, n === null ? fmtText(v) : String(Number(n.toFixed(4)))] as [string, string]
  })
}

// ────────────────────────────────────────────────────────────────────────
// KST 시각 (백엔드 `_to_kst` 와 동일 컨벤션)
// ────────────────────────────────────────────────────────────────────────

const KST_FMT = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: '2-digit',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

function fmtKst(iso: unknown): string {
  if (typeof iso !== 'string' || iso.trim() === '') return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const p = KST_FMT.formatToParts(d)
  const get = (t: string) => p.find((x) => x.type === t)?.value.padStart(2, '0') ?? '--'
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}:${get('second')}`
}

// ────────────────────────────────────────────────────────────────────────
// 작은 표시 조각
// ────────────────────────────────────────────────────────────────────────

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-xs text-gray-500 shrink-0">{label}</span>
      <span className="text-sm text-gray-800 font-medium break-all">{value}</span>
    </div>
  )
}

function Section({
  title,
  testId,
  children,
}: {
  title: string
  testId: string
  children: React.ReactNode
}) {
  return (
    <section className="border-t border-gray-100 pt-3 mt-3 first:border-t-0 first:pt-0 first:mt-0">
      <h3 className="text-xs font-semibold text-gray-500 mb-1.5">{title}</h3>
      <div data-testid={testId}>{children}</div>
    </section>
  )
}

function JsonToggle({
  label,
  toggleTestId,
  contentTestId,
  value,
}: {
  label: string
  toggleTestId: string
  contentTestId: string
  value: unknown
}) {
  const [open, setOpen] = useState(false)
  const text = useMemo(() => {
    try {
      return JSON.stringify(value ?? null, null, 2)
    } catch {
      return String(value)
    }
  }, [value])

  return (
    <div className="border-t border-gray-100 pt-3 mt-3">
      <button
        type="button"
        data-testid={toggleTestId}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="text-xs font-medium text-gray-600 hover:text-gray-900 underline underline-offset-2"
      >
        {open ? `${label} 접기` : `${label} 펼치기`}
      </button>
      {open && (
        <pre
          data-testid={contentTestId}
          className="whitespace-pre-wrap break-all text-xs text-gray-700 bg-gray-50 rounded p-2 mt-2 max-h-64 overflow-auto"
        >
          {text}
        </pre>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────
// 본체
// ────────────────────────────────────────────────────────────────────────

interface Props {
  /** 이 팝업이 보여 줄 매수 주문번호들. 손익 페어는 매수 주문 2건 이상을 품을 수 있다(명세 §8). */
  orderNos: string[]
  /** KST 영업일(`YYYY-MM-DD`). KIS 주문번호는 하루 단위로만 유일해 날짜가 함께 있어야 안전하다. */
  tradeDate?: string
  onClose: () => void
}

export default function LlmEvaluationModal({ orderNos, tradeDate, onClose }: Props) {
  const first = orderNos[0] ?? ''
  const [activeOrderNo, setActiveOrderNo] = useState(first)

  // 페어의 주문 목록이 바뀌면(다른 행을 열었다면) 첫 매수 주문으로 되돌린다.
  useEffect(() => {
    if (!orderNos.includes(activeOrderNo)) setActiveOrderNo(first)
  }, [orderNos, activeOrderNo, first])

  // ESC 닫기 — `InfoTooltip.tsx` 의 관용구 그대로.
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [onClose])

  // 닫을 때 트리거 버튼으로 포커스 복귀(포커스 트랩은 이번 범위 밖).
  const openerRef = useRef<Element | null>(null)
  useEffect(() => {
    openerRef.current = document.activeElement
    return () => {
      const el = openerRef.current
      if (el instanceof HTMLElement && document.contains(el)) el.focus()
    }
  }, [])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['llmEvaluation', activeOrderNo, tradeDate],
    retry: 1,
    enabled: !!activeOrderNo,
    queryFn: () => getLlmEvaluation(activeOrderNo, tradeDate),
  })

  // cycle266 분기 — 404(기록 없음, 회색) ↔ 그 외(500·네트워크, 빨강).
  const is404 = isError && axios.isAxiosError(error) && error.response?.status === 404

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      data-testid="llm-eval-modal"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={TITLE_ID}
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
          <h2 id={TITLE_ID} className="text-lg font-semibold text-gray-900">
            AI 매수평가 — 주문 {activeOrderNo || '—'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-500 hover:text-gray-700 text-xl font-bold"
            aria-label="닫기"
          >
            ×
          </button>
        </div>

        {orderNos.length > 1 && (
          <div className="shrink-0 px-6 pt-3 border-b border-gray-200">
            <p className="text-xs text-gray-500 mb-2">
              이 손익 행은 매수 주문 {orderNos.length}건이 뭉쳐 있습니다 — 첫 매수 주문
              기준으로 정렬했습니다. 주문별 평가를 탭으로 확인하세요.
            </p>
            <div className="flex flex-wrap gap-1">
              {orderNos.map((no) => (
                <button
                  key={no}
                  type="button"
                  data-testid={`llm-eval-order-tab-${no}`}
                  onClick={() => setActiveOrderNo(no)}
                  className={`text-xs px-3 py-1.5 font-medium border-b-2 transition-colors ${
                    no === activeOrderNo
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {no}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="px-6 py-4 overflow-y-auto flex-1">
          {isLoading && (
            <p className="text-sm text-gray-500 animate-pulse py-4">평가 기록 로딩 중...</p>
          )}

          {is404 && (
            <p className="text-sm text-gray-500 py-4" data-testid="llm-eval-notice">
              평가 기록 없음 — 이 주문에는 AI 매수평가가 남아 있지 않습니다.
              (평가는 전략 설정의 `llm_gate_mode` 가 `shadow` 일 때만 기록됩니다.)
            </p>
          )}

          {isError && !is404 && (
            <p className="text-sm text-red-600 py-4" data-testid="llm-eval-error">
              평가 기록 조회 실패 — 잠시 후 다시 시도해 주세요.
            </p>
          )}

          {!isLoading && !isError && data && <EvaluationBody evaluation={data} />}
        </div>
      </div>
    </div>
  )
}

function EvaluationBody({ evaluation }: { evaluation: LlmEvaluation }) {
  const score = toSafeNumber(evaluation.score)
  const minScore = toSafeNumber(evaluation.min_score)
  const wouldBlock = evaluation.would_block
  const risks = toStringList(evaluation.key_risks)
  const invalidations = toStringList(evaluation.invalidations)
  const tech = extractTech(evaluation.input_payload)
  const isFailed = evaluation.result === 'failed'

  const blockLabel =
    wouldBlock === null || wouldBlock === undefined
      ? '차단 판정 없음'
      : wouldBlock
        ? '차단 대상(임계 미만)'
        : '차단 아님(임계 이상)'

  return (
    <div>
      {isFailed && (
        <div
          data-testid="llm-eval-failed"
          className="mb-4 rounded border border-red-200 bg-red-50 px-4 py-3"
        >
          <p className="text-xs text-red-700 font-semibold">평가 실패</p>
          <p className="text-lg font-bold text-red-700 break-all">
            {fmtText(evaluation.reason)}
          </p>
          <p className="text-xs text-red-700 mt-1">
            평가를 시도했으나 점수를 얻지 못한 기록입니다 — "평가하지 않음" 과 다릅니다.
          </p>
        </div>
      )}

      <Section title="점수" testId="llm-eval-score">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-2xl font-bold text-gray-900">
            {score === null ? '—' : score.toLocaleString('ko-KR')}
          </span>
          <span className="text-sm text-gray-500">
            / 임계 {minScore === null ? '—' : minScore.toLocaleString('ko-KR')}
          </span>
          <span className="text-sm font-medium text-gray-700">{blockLabel}</span>
          <span className="text-xs text-gray-400">
            모드 {fmtText(evaluation.mode)} · 관측 전용(주문을 막지 않습니다)
          </span>
        </div>
      </Section>

      <Section title="사유" testId="llm-eval-rationale">
        <p className="text-sm text-gray-800 whitespace-pre-wrap break-words">
          {fmtText(evaluation.rationale)}
        </p>
      </Section>

      <Section title="핵심 위험" testId="llm-eval-risks">
        {risks.length === 0 ? (
          <p className="text-sm text-gray-400">—</p>
        ) : (
          <ul className="list-disc list-inside text-sm text-gray-800 space-y-0.5">
            {risks.map((r, i) => (
              <li key={`${i}-${r}`} className="break-words">
                {r}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="무효화 조건" testId="llm-eval-invalidations">
        {invalidations.length === 0 ? (
          <p className="text-sm text-gray-400">—</p>
        ) : (
          <ul className="list-disc list-inside text-sm text-gray-800 space-y-0.5">
            {invalidations.map((v, i) => (
              <li key={`${i}-${v}`} className="break-words">
                {v}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="지표 요약" testId="llm-eval-features">
        {tech.length === 0 ? (
          <p className="text-sm text-gray-400">지표 없음 (프롬프트 조립 전 실패 가능)</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
            {tech.map(([k, v]) => (
              <Field key={k} label={k} value={v} />
            ))}
          </div>
        )}
      </Section>

      <Section title="주문 스냅샷" testId="llm-eval-order">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
          <Field
            label="종목"
            value={
              evaluation.ticker_name
                ? `${fmtText(evaluation.ticker)} ${evaluation.ticker_name}`
                : fmtText(evaluation.ticker)
            }
          />
          <Field label="주문가" value={fmtInt(evaluation.order_price_won, '원')} />
          <Field label="주문수량" value={fmtInt(evaluation.ordered_qty, '주')} />
          <Field label="주문금액" value={fmtInt(evaluation.order_notional_won, '원')} />
          <Field label="주문구분" value={fmtText(evaluation.order_division)} />
          <Field label="주문경로" value={fmtText(evaluation.order_path)} />
          <Field label="거래소" value={fmtText(evaluation.exchange)} />
          <Field label="보드" value={fmtText(evaluation.board)} />
          <Field label="목표가" value={fmtInt(evaluation.target_won, '원')} />
          <Field
            label="돌파폭"
            value={
              toSafeNumber(evaluation.breakout_excess_bp) === null
                ? '—'
                : fmtFixed(evaluation.breakout_excess_bp, 1, 'bp')
            }
          />
          <Field label="주문 시 현재가" value={fmtInt(evaluation.current_price_won, '원')} />
          <Field
            label="주문 후 표류"
            value={
              toSafeNumber(evaluation.post_order_drift_bp) === null
                ? '—'
                : fmtFixed(evaluation.post_order_drift_bp, 1, 'bp')
            }
          />
          {/* 시각은 서버 로컬 시각 문자열이다(KST 보장 없음) — 라벨에 KST 를 쓰지 않는다. */}
          <Field
            label="신호 역참조"
            value={
              evaluation.signal_matched
                ? `있음 ${fmtText(evaluation.signal_time_local)} (서버 시각)`
                : '없음'
            }
          />
          <Field label="전략" value={fmtText(evaluation.strategy_id)} />
          <Field label="잔여 예산" value={fmtInt(evaluation.budget_remaining_after_won, '원')} />
        </div>
      </Section>

      <Section title="모델 · 비용 · 버전" testId="llm-eval-meta">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1">
          <Field label="모델" value={fmtText(evaluation.model)} />
          <Field label="입력 토큰" value={fmtInt(evaluation.tokens_in)} />
          <Field label="출력 토큰" value={fmtInt(evaluation.tokens_out)} />
          <Field label="비용(USD)" value={fmtFixed(evaluation.cost_usd, 6)} />
          <Field label="LLM 지연" value={fmtInt(evaluation.latency_ms, 'ms')} />
          <Field label="판정 지연" value={fmtInt(evaluation.verdict_lag_ms, 'ms')} />
          <Field label="주문→판정" value={fmtInt(evaluation.eval_to_order_lag_ms, 'ms')} />
          <Field label="프롬프트 버전" value={fmtText(evaluation.prompt_version)} />
          <Field label="지표 버전" value={fmtText(evaluation.feature_version)} />
          <Field label="일봉 수" value={fmtInt(evaluation.bars_count)} />
          <Field label="주문 시각(KST)" value={fmtKst(evaluation.order_kst)} />
          <Field label="평가 시각(KST)" value={fmtKst(evaluation.evaluated_at)} />
          <Field label="계좌" value={fmtText(evaluation.account_no_masked)} />
          <Field label="영업일" value={fmtText(evaluation.trade_date)} />
        </div>
      </Section>

      <JsonToggle
        label="입력 payload 원문"
        toggleTestId="llm-eval-payload-toggle"
        contentTestId="llm-eval-payload-content"
        value={evaluation.input_payload}
      />
      <JsonToggle
        label="모델 응답 원문"
        toggleTestId="llm-eval-raw-toggle"
        contentTestId="llm-eval-raw-content"
        value={evaluation.raw_response}
      />
    </div>
  )
}
