// cycle413 — 거래일지 카드 (명세 `_workspace/red/cycle413/journal_view_spec.md` 8-2 와이어).
//
// 서버가 만든 문장(`reason.text`·`target.text`·`stop_row.cause`)은 그대로 보이고, 이 파일은
// 코드(`division`·`source`·`judge.src`·`stop_kind`·`event`·`na`)만 `utils/journalLabels.ts` 로
// 바꾼다. 테이블을 쓰지 않는다(400px 요건 — 명세 8-3) · 메모는 글자 그대로 보인다(HTML 해석 없음, textarea 값으로만 노출).
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { putJournalNote } from '../api/history'
import { strategyLabel } from '../utils/strategyMeta'
import { formatKstDateTime } from '../utils/kst'
import type { CostBasis } from '../utils/costBasis'
import type {
  Costs, Excursion, ExitLine, ExPoint, JournalCard as JournalCardType, OrderLine, Reason,
  StopPoint, StopTrack, Target,
} from '../types/journal'
import type { NaKind } from '../types/journal'
import {
  costStatusLabel, divisionLabel, naLabel, reasonCodeLabel, sourceLabel, stopEventLabel,
  stopKindLabel, valSrcLabel,
} from '../utils/journalLabels'

const NOTE_MAX = 4000

// ── 숫자 서식 — 이 카드 전용(다른 화면 사본과 독립, 산식은 같다) ────────────────
function fmtInt(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  return Math.round(n).toLocaleString()
}
function fmtSignedKRW(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${Math.round(n).toLocaleString()}원`
}
function fmtSignedPct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(digits)}%`
}
function fmtBpSigned(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(1)}bp`
}
function pnlClass(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v) || v === 0) return 'text-gray-700'
  return v > 0 ? 'text-red-600' : 'text-blue-600'
}

// ── 빈칸 배지 ───────────────────────────────────────────────────────────────
function NaBadge({ na }: { na: NaKind }) {
  return (
    <span
      data-testid={`journal-na-${na}`}
      className={na === 'lookup_failed' ? 'text-amber-600 text-xs' : 'text-gray-400 text-xs'}
    >
      {naLabel(na)}
    </span>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block px-1 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-600 mr-1">
      {children}
    </span>
  )
}

function kst(iso: string | null | undefined): string {
  // 명세 8-2 — `MM-DD HH:mm:ss` = formatKstDateTime(iso).slice(5). 날짜 포맷터를 이 파일에서 새로 만들지 않는다.
  return formatKstDateTime(iso).slice(5)
}

// ── 주문 1줄 (매수·매도 공통) ────────────────────────────────────────────────
function OrderLineRow({ line }: { line: OrderLine | ExitLine }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
      <span className="text-gray-500 tabular-nums">{kst(line.at)}</span>
      <span className="font-medium tabular-nums">
        {fmtInt(line.price)} × {line.qty}
      </span>
      {line.division ? <Chip>{divisionLabel(line.division)}</Chip> : line.division_na && <NaBadge na={line.division_na} />}
      {line.source ? <Chip>{sourceLabel(line.source)}</Chip> : line.source_na && <NaBadge na={line.source_na} />}
      {line.slip_order ? (
        <span className="text-xs text-gray-500">
          체결오차 {fmtBpSigned(line.slip_order.bp)} (주문가)
        </span>
      ) : (
        line.slip_order_na && <NaBadge na={line.slip_order_na} />
      )}
      {line.judge.price !== null && (
        <span className="text-xs text-gray-500">판단가 {fmtInt(line.judge.price)}</span>
      )}
      {line.judge.price === null && line.judge.upper !== null && (
        <span className="text-xs text-gray-500">판단가 ≤{fmtInt(line.judge.upper)}</span>
      )}
      {line.slip_judge && (
        <span className="text-xs text-gray-500">
          {line.slip_judge.bound === 'upper' ? '≤' : ''}
          {fmtBpSigned(line.slip_judge.bp)}
        </span>
      )}
    </div>
  )
}

// ── 진입 이유 / 청산 이유 (서버 문장 + 출처 배지) ───────────────────────────
function ReasonBlock({ reason, testId }: { reason: Reason; testId: string }) {
  const srcLabel = valSrcLabel(reason.src)
  return (
    <div data-testid={testId} className="text-sm text-gray-700">
      {reason.text ? <span>{reason.text}</span> : reason.na && <NaBadge na={reason.na} />}
      {srcLabel && <Chip>{srcLabel}</Chip>}
      {reason.renamed_from && (
        <span className="text-xs text-gray-400"> (접수 이름 {reason.renamed_from} — 사유 줄로 보정)</span>
      )}
    </div>
  )
}

// ── 최초 손절 ────────────────────────────────────────────────────────────────
function InitialStopBlock({ stop }: { stop: StopPoint }) {
  if (stop.na) {
    return (
      <div data-testid="journal-initial-stop" className="text-sm text-gray-500">
        최초 손절 <NaBadge na={stop.na} />
        {stop.first_seen && (
          <span className="text-xs text-gray-400">
            {' '}
            (첫 관측 {kst(stop.first_seen.observed_at)} {fmtInt(stop.first_seen.price)})
          </span>
        )}
      </div>
    )
  }
  return (
    <div data-testid="journal-initial-stop" className="text-sm text-gray-700">
      최초 손절 {fmtInt(stop.price)}
      {stop.pct_from_entry !== null && <span> ({fmtSignedPct(stop.pct_from_entry)})</span>}
      {stop.kind === 'hard_pct' && <span className="text-xs text-amber-600"> [근사]</span>}
      {stop.kind && stop.kind !== 'effective' && stop.kind !== 'hard_pct' && (
        <Chip>{stopKindLabel(stop.kind)}</Chip>
      )}
      {stop.delay_s !== null && stop.delay_s > 300 && (
        <span className="text-xs text-gray-400"> ({Math.round(stop.delay_s / 60)}분 뒤 관측)</span>
      )}
    </div>
  )
}

// ── 익절 목표 ────────────────────────────────────────────────────────────────
function TargetBlock({ target }: { target: Target }) {
  return (
    <div data-testid="journal-target" className="text-sm text-gray-700">
      {target.text && <span>{target.text}</span>}
      {target.na && <NaBadge na={target.na} />}
    </div>
  )
}

// ── 청산 줄의 손절/목표선 정보 ───────────────────────────────────────────────
function exitLineInfo(exit: ExitLine, entryTargetPrice: number | null): { text: string; na: NaKind | null } {
  const parts: string[] = []
  const tail = exit.snapshot_age_s !== null ? ` (${exit.snapshot_age_s}초 전)` : ''
  if (exit.line_role === 'target') {
    if (entryTargetPrice !== null) parts.push(`목표 ${fmtInt(entryTargetPrice)}`)
    if (exit.effective_line !== null) parts.push(`참고 손절선 ${fmtInt(exit.effective_line)}${tail}`)
    if (parts.length === 0) return { text: '', na: exit.line_na ?? 'unknown' }
    return { text: parts.join(' · '), na: null }
  }
  if (exit.line_role === 'fired') {
    if (exit.fired_line !== null) parts.push(`발동선 ${fmtInt(exit.fired_line)}`)
    if (exit.effective_line !== null && exit.effective_line !== exit.fired_line) {
      parts.push(`유효선 ${fmtInt(exit.effective_line)}${tail}`)
    }
    if (parts.length === 0) return { text: '', na: exit.line_na ?? 'unknown' }
    return { text: parts.join(' · '), na: null }
  }
  // reference(가격 무관 청산) 또는 null
  parts.push('손절 미발동')
  if (exit.effective_line !== null) {
    parts.push(`참고 손절선 ${fmtInt(exit.effective_line)}${tail}`)
    return { text: parts.join(' · '), na: null }
  }
  return { text: '손절 미발동', na: exit.line_na ?? 'unknown' }
}

function ExitLineInfoBlock({ exit, entryTargetPrice }: { exit: ExitLine; entryTargetPrice: number | null }) {
  const info = exitLineInfo(exit, entryTargetPrice)
  return (
    <div data-testid="journal-exit-line" className="text-sm text-gray-600">
      {info.text && <span>{info.text}</span>}
      {info.na && <NaBadge na={info.na} />}
    </div>
  )
}

// ── 손절선 변화 (접힘 기본) ──────────────────────────────────────────────────
function rowClass(direction: string | null, event: string): string {
  const parts = ['text-xs', 'py-1']
  if (direction === 'down' || event === 'paused') parts.push('text-red-600', 'bg-red-50')
  if (event === 'boot') parts.push('bg-yellow-50')
  return parts.join(' ')
}

function StopTrackBlock({ track }: { track: StopTrack }) {
  const [open, setOpen] = useState(false)
  if (track.na) {
    return (
      <div className="text-sm">
        <NaBadge na={track.na} />
      </div>
    )
  }
  return (
    <div>
      <button
        type="button"
        data-testid="journal-stop-toggle"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="text-sm text-left w-full flex items-center gap-2"
      >
        <span>▸ 손절선 변화</span>
        <span className="tabular-nums">
          {fmtInt(track.first)} → {fmtInt(track.last)}
        </span>
        <span className="text-gray-500">↑{track.ups}</span>
        <span className={track.downs > 0 ? 'text-red-600' : 'text-gray-500'}>↓{track.downs}</span>
      </button>
      {open && (
        <div className="mt-1 space-y-0.5">
          {track.rows.map((row, i) => (
            <div
              key={`${row.at}-${i}`}
              data-testid="journal-stop-row"
              data-event={row.event}
              data-direction={row.direction ?? ''}
              className={rowClass(row.direction, row.event)}
            >
              {kst(row.at)} {stopEventLabel(row.event)} {row.price !== null ? fmtInt(row.price) : '—'}
              {row.direction && row.direction !== 'flat' && (
                <span>
                  {' '}
                  {row.direction === 'up' ? '↑' : '↓'}
                  {row.delta_won !== null ? fmtSignedKRW(row.delta_won).replace('원', '') : ''}
                </span>
              )}
              {' · '}
              {row.cause}
            </div>
          ))}
          {track.hidden_eod > 0 && (
            <div className="text-xs text-gray-400">(값 그대로인 장마감 {track.hidden_eod}건 숨김)</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── 비용 ─────────────────────────────────────────────────────────────────────
function CostsBlock({ costs }: { costs: Costs }) {
  if (costs.na) {
    return (
      <div data-testid="journal-cost-total" className="text-sm">
        비용 <NaBadge na={costs.na} />
      </div>
    )
  }
  return (
    <div data-testid="journal-cost-total" className="text-sm text-gray-700 space-y-0.5">
      <div className="flex flex-wrap gap-x-2 text-xs text-gray-500">
        {costs.entry_fee !== null && <span>진입 수수료 {fmtInt(costs.entry_fee)}</span>}
        {costs.exits.map((e, i) => (
          <span key={`${e.order_no ?? i}`}>
            {e.fee !== null && <>청산 수수료 {fmtInt(e.fee)}</>}
            {e.tax !== null && <> · 세금 {fmtInt(e.tax)}</>}
          </span>
        ))}
      </div>
      <div>
        합계 {costs.paid_total !== null ? fmtInt(costs.paid_total) : <NaBadge na="unknown" />}
        {costs.status && <Chip>{costStatusLabel(costs.status)}</Chip>}
        {costs.allocated && <Chip>배분</Chip>}
        {costs.expected_exit !== null ? (
          <span className="text-xs text-gray-500"> · 예상 청산비용 {fmtInt(costs.expected_exit)}</span>
        ) : (
          costs.expected_exit_na && (
            <span className="text-xs text-gray-500">
              {' '}
              · 예상 청산비용 <NaBadge na={costs.expected_exit_na} />
            </span>
          )
        )}
      </div>
    </div>
  )
}

// ── 보유 중 평가 (MFE/MAE) ───────────────────────────────────────────────────
function renderExPoint(p: ExPoint, isMfe: boolean): React.ReactNode {
  if (isMfe && p.pct <= 0) {
    return <>이익 구간 없음 (최고 {fmtSignedPct(p.pct)})</>
  }
  if (!isMfe && p.pct >= 0) {
    return <>손실 구간 없음 (최저 {fmtSignedPct(p.pct)})</>
  }
  return (
    <>
      {fmtSignedPct(p.pct)} {fmtInt(p.krw)}원 {p.date}
      {p.provisional && <Chip>잠정</Chip>}
    </>
  )
}

function ExcursionBlock({ excursion }: { excursion: Excursion }) {
  return (
    <div className="text-sm text-gray-700 space-y-0.5">
      <div data-testid="journal-mfe">
        최대 이익{' '}
        {excursion.na ? <NaBadge na={excursion.na} /> : excursion.mfe ? renderExPoint(excursion.mfe, true) : <NaBadge na="unknown" />}
      </div>
      <div data-testid="journal-mae">
        최대 손실{' '}
        {excursion.na ? <NaBadge na={excursion.na} /> : excursion.mae ? renderExPoint(excursion.mae, false) : <NaBadge na="unknown" />}
      </div>
      {!excursion.na && (
        <div className="text-xs text-gray-400">
          종가 {excursion.closes_k}/{excursion.closes_n}일
          {excursion.lock_dates.length > 0 && <Chip>락</Chip>}
        </div>
      )}
    </div>
  )
}

// ── 메모 ─────────────────────────────────────────────────────────────────────
function NoteBlock({ anchorTradeId, note }: { anchorTradeId: string; note: { body: string; updated_at: string } | null }) {
  const savedBody = note?.body ?? ''
  const [draft, setDraft] = useState(savedBody)
  const [lastSaved, setLastSaved] = useState(savedBody)
  const [status, setStatus] = useState<'idle' | 'saved' | 'error'>('idle')

  const mutation = useMutation({
    mutationFn: (body: string) => putJournalNote(anchorTradeId, body),
    onSuccess: () => {
      setLastSaved(draft)
      setStatus('saved')
    },
    onError: () => {
      setStatus('error')
    },
  })

  const dirty = draft !== lastSaved
  const tooLong = draft.length > NOTE_MAX

  return (
    <div className="space-y-1">
      <textarea
        data-testid="journal-note-input"
        className="w-full border border-gray-200 rounded p-1.5 text-sm"
        rows={3}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value)
          setStatus('idle')
        }}
      />
      <div className="flex items-center justify-between text-xs">
        <span className={tooLong ? 'text-red-600' : 'text-gray-400'}>
          {draft.length.toLocaleString()} / {NOTE_MAX.toLocaleString()}
        </span>
        <span className="flex items-center gap-2">
          {dirty && status !== 'error' && <span className="text-gray-400">저장 안 됨</span>}
          {!dirty && status === 'saved' && <span className="text-emerald-600">저장됨</span>}
          {status === 'error' && <span className="text-red-600">저장 실패</span>}
          <button
            type="button"
            data-testid="journal-note-save"
            disabled={tooLong || mutation.isPending}
            onClick={() => mutation.mutate(draft)}
            className="px-2 py-1 border rounded text-gray-700 disabled:opacity-50"
          >
            저장
          </button>
        </span>
      </div>
    </div>
  )
}

// ── 머리 손익 ────────────────────────────────────────────────────────────────
function HeadPnl({ card, basis }: { card: JournalCardType; basis: CostBasis }) {
  const { pnl } = card
  const primary = basis === 'net'
    ? { label: '세후', amt: pnl.net_krw, pct: pnl.net_rate_pct, na: pnl.net_na }
    : { label: '세전', amt: pnl.gross_krw, pct: pnl.gross_rate_pct, na: pnl.gross_na }
  const secondary = basis === 'net'
    ? { label: '세전', amt: pnl.gross_krw, na: pnl.gross_na }
    : { label: '세후', amt: pnl.net_krw, na: pnl.net_na }
  return (
    <div data-testid="journal-head-pnl" className="flex flex-wrap items-baseline gap-x-2">
      <span className="text-xs text-gray-400">{primary.label}</span>
      {primary.amt !== null ? (
        <span className={`text-lg font-semibold ${pnlClass(primary.amt)}`}>{fmtSignedKRW(primary.amt)}</span>
      ) : (
        <NaBadge na={primary.na ?? 'unknown'} />
      )}
      {primary.pct !== null && <span className={`text-sm ${pnlClass(primary.pct)}`}>{fmtSignedPct(primary.pct)}</span>}
      <span className="text-xs text-gray-400 ml-2">{secondary.label}</span>
      {secondary.amt !== null ? (
        <span className="text-sm text-gray-400">{fmtSignedKRW(secondary.amt)}</span>
      ) : (
        <NaBadge na={secondary.na ?? 'unknown'} />
      )}
      {pnl.unrealized && (
        <span className="text-xs text-gray-400">(미실현{primary.amt === null ? ' 시세 대기' : ''})</span>
      )}
    </div>
  )
}

// ── 카드 ─────────────────────────────────────────────────────────────────────
interface Props {
  card: JournalCardType
  basis: CostBasis
  stopsRecordStart: string | null
}

export default function JournalCard({ card, basis, stopsRecordStart }: Props) {
  const heldLabel = `보유 ${card.held_days}일`
  return (
    <div
      data-testid={`journal-card-${card.anchor_trade_id}`}
      className="bg-white border border-gray-200 rounded-lg p-3 space-y-2"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-2">
        <div className="flex items-baseline gap-2">
          <span className="font-semibold">{card.ticker_name}</span>
          <span className="text-xs text-gray-400">{card.ticker}</span>
          <span className="text-xs text-gray-400">{card.status === 'open' ? '보유 중' : '청산'}</span>
          <span className="text-xs text-gray-400">{heldLabel}</span>
        </div>
        <span className="text-xs text-gray-400">{strategyLabel(card.strategy)}</span>
      </div>
      <div className="text-xs text-gray-400">
        {kst(card.opened_at)} → {card.closed_at ? kst(card.closed_at) : '보유 중'}
      </div>

      <HeadPnl card={card} basis={basis} />

      {card.stop_track.paused && (
        <div data-testid="journal-paused-warning" className="text-xs text-red-600">
          ⚠ 손절 평가 정지 구간 있음
        </div>
      )}
      {card.record_notice && (
        <div data-testid="journal-record-notice" className="text-xs text-gray-400">
          {card.record_notice === 'before_orders'
            ? '기록 시작 전 거래 — 일자·가격·비용·평가손익만'
            : `손절선 기록 시작(${stopsRecordStart ?? '—'}) 전 진입 — 최초 손절·익절 목표는 기록 전`}
        </div>
      )}

      <div className="border-t pt-2 space-y-1">
        <div className="text-xs font-medium text-gray-500">진입</div>
        {card.entry.orders.map((o, i) => <OrderLineRow key={o.order_no ?? i} line={o} />)}
        <ReasonBlock reason={card.entry.reason} testId="journal-entry-reason" />
        <InitialStopBlock stop={card.entry.initial_stop} />
        <TargetBlock target={card.entry.target} />
      </div>

      <div className="border-t pt-2">
        <StopTrackBlock track={card.stop_track} />
      </div>

      {card.exits.length > 0 && (
        <div className="border-t pt-2 space-y-2">
          <div className="text-xs font-medium text-gray-500">청산</div>
          {card.exits.map((ex, i) => (
            <div key={ex.order_no ?? i} data-testid={`journal-exit-${ex.order_no ?? i}`} className="space-y-1">
              <OrderLineRow line={ex} />
              <div className="flex items-center gap-1">
                <span className="inline-block px-1 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-700">
                  {reasonCodeLabel(ex.reason.code)}
                </span>
                {ex.path === 'reorder' && ex.parent_order_no && (
                  <span className="text-xs text-gray-400">· 잔여 재주문(원주문 {ex.parent_order_no})</span>
                )}
                {ex.path === 'fallback' && <span className="text-xs text-gray-400">· 5호가 폴백</span>}
              </div>
              <ReasonBlock reason={ex.reason} testId="journal-exit-reason" />
              <ExitLineInfoBlock exit={ex} entryTargetPrice={card.entry.target.price} />
            </div>
          ))}
        </div>
      )}
      {card.status === 'open' && (
        <div className="border-t pt-2 text-sm text-gray-600">
          보유 중 · 지금 손절선 {fmtInt(card.stop_track.last)}
          {card.entry.initial_stop.kind && <Chip>{stopKindLabel(card.entry.initial_stop.kind)}</Chip>}
        </div>
      )}

      <div className="border-t pt-2">
        <CostsBlock costs={card.costs} />
      </div>

      <div className="border-t pt-2">
        <ExcursionBlock excursion={card.excursion} />
      </div>

      <div className="border-t pt-2">
        <NoteBlock anchorTradeId={card.anchor_trade_id} note={card.note} />
      </div>
    </div>
  )
}
