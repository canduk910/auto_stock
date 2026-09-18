/**
 * 이벤트 라벨 stagger 계산 — 시간 도메인에서 글로벌 충돌 검사로 row 할당
 * (원본 `macro_lite/components/EventLabelsOverlay.jsx` 이식, 로직 무수정).
 *
 * ReferenceArea 의 label 콜백(viewBox 수신)에서 사용. Customized 우회로 100% 렌더 보장.
 *
 * 가정: 차트 X축이 균일 시간 매핑이라고 가정하여 라벨 픽셀 폭 → 시간 폭으로 환산.
 * kind(rec/bear)별 독립 적층. 같은 kind 내에서 cx 가 가까우면 다음 row 로 밀어낸다.
 *
 * 🔴 표시 규약(cycle303 spec §6 도메인 제약) — 침체(rec)/약세장(bear) 의 색·레이어
 * 순서는 각 섹션(YieldCurveSection/CreditSpreadSection)이 정한다. 이 파일은 라벨
 * 배치(stagger)만 계산하고 색은 건드리지 않는다.
 */
import type { CSSProperties } from "react"

export interface EventRowInput {
  kind: "rec" | "bear"
  x1: string
  x2: string
  label: string
}

interface EventRowItem extends EventRowInput {
  displayLabel: string
  cMs: number
  widthMs: number
  row: number
}

export interface EventRowMap {
  rowFor: (kind: "rec" | "bear", x1: string, x2: string) => number
  rowDisplayFor: (kind: "rec" | "bear", x1: string, x2: string) => { row: number; displayLabel: string }
}

const _CHAR_PX = 6.2
const _CHART_PX_FALLBACK = 600 // ResponsiveContainer 기본 폭 추정

function _shortLabel(label: string, x1: string, x2: string): string {
  const days = (new Date(x2).getTime() - new Date(x1).getTime()) / 86400000
  if (days < 365 && label.length > 5) {
    return label.replace("약세장", "").replace("침체", "").trim() || label
  }
  return label
}

function _estimateLabelChars(text: string): number {
  // 원본은 `/[\x00-\x7f]/` 정규식으로 ASCII(반각) 여부를 판정했다 — ESLint `no-control-regex`
  // 가 제어문자 범위 포함 정규식을 금지해, 같은 판정을 charCode 비교로 대체한다(로직 무변경).
  let n = 0
  for (const ch of text) {
    n += ch.charCodeAt(0) <= 0x7f ? 0.6 : 1
  }
  return n
}

const _EMPTY_ROW_MAP: EventRowMap = {
  rowFor: () => 0,
  rowDisplayFor: () => ({ row: 0, displayLabel: "" }),
}

// events: [{kind, x1, x2, label}] - 정렬 안 됨
// 반환: rowFor/rowDisplayFor 조회 헬퍼 — row=0/1/2/...
export function computeEventRows(
  events: EventRowInput[],
  chartPxWidth = _CHART_PX_FALLBACK,
): EventRowMap {
  if (!events?.length) return _EMPTY_ROW_MAP

  // 전체 시간 범위
  const allDates = events.flatMap((e) => [e.x1, e.x2])
  const minMs = Math.min(...allDates.map((d) => new Date(d).getTime()))
  const maxMs = Math.max(...allDates.map((d) => new Date(d).getTime()))
  const spanMs = Math.max(1, maxMs - minMs)
  const msPerPx = spanMs / chartPxWidth

  const items: EventRowItem[] = events.map((e) => {
    const cMs = (new Date(e.x1).getTime() + new Date(e.x2).getTime()) / 2
    const displayLabel = _shortLabel(e.label, e.x1, e.x2)
    const prefix = e.kind === "rec" ? "■ " : "▼ "
    const fullText = prefix + displayLabel
    const widthPx = _estimateLabelChars(fullText) * _CHAR_PX + 8
    const widthMs = widthPx * msPerPx
    return { ...e, displayLabel, cMs, widthMs, row: 0 }
  })

  const place = (kindItems: EventRowItem[]): EventRowItem[] => {
    const sorted = [...kindItems].sort((a, b) => a.cMs - b.cMs)
    const rowEnds: number[] = [] // 각 row 의 마지막 라벨의 right ms
    return sorted.map((it) => {
      const left = it.cMs - it.widthMs / 2
      const right = it.cMs + it.widthMs / 2
      let row = 0
      while (row < rowEnds.length && rowEnds[row] > left) row++
      if (row === rowEnds.length) rowEnds.push(right)
      else rowEnds[row] = right
      return { ...it, row }
    })
  }

  const recItems = place(items.filter((i) => i.kind === "rec"))
  const bearItems = place(items.filter((i) => i.kind === "bear"))
  // events 원래 순서로 묶어 반환할 필요 없음 — kind 별 lookup 맵 제공
  const map = new Map<string, number>()
  for (const it of [...recItems, ...bearItems]) {
    map.set(`${it.kind}|${it.x1}|${it.x2}`, it.row)
  }
  return {
    rowFor: (kind, x1, x2) => map.get(`${kind}|${x1}|${x2}`) ?? 0,
    rowDisplayFor: (kind, x1, x2) => {
      const it = [...recItems, ...bearItems].find(
        (x) => x.kind === kind && x.x1 === x1 && x.x2 === x2,
      )
      return it ? { row: it.row, displayLabel: it.displayLabel } : { row: 0, displayLabel: "" }
    },
  }
}

interface LabelRendererArgs {
  kind: "rec" | "bear"
  displayLabel: string
  row: number
  fill: string
  fontSize?: number
  step?: number
}

interface RechartsLabelViewBox {
  x?: number
  y?: number
  width?: number
  height?: number
}

// ReferenceArea label 콜백 헬퍼 — viewBox 받아 row*step 만큼 dy 적용 후 SVG <text> 반환.
// kind: 'rec'(아래) | 'bear'(위)
export function makeLabelRenderer({
  kind,
  displayLabel,
  row,
  fill,
  fontSize = 9,
  step = 13,
}: LabelRendererArgs) {
  const prefix = kind === "rec" ? "■" : "▼"
  return (props: { viewBox?: RechartsLabelViewBox }) => {
    const vb = props?.viewBox || {}
    const x = (vb.x ?? 0) + (vb.width ?? 0) / 2
    const yBase =
      kind === "rec" ? (vb.y ?? 0) + (vb.height ?? 0) - 4 : (vb.y ?? 0) + fontSize + 2
    const dy = kind === "rec" ? -row * step : row * step
    const style: CSSProperties = { pointerEvents: "none" }
    return (
      <text x={x} y={yBase + dy} textAnchor="middle" fontSize={fontSize} fill={fill} style={style}>
        {prefix} {displayLabel}
      </text>
    )
  }
}
