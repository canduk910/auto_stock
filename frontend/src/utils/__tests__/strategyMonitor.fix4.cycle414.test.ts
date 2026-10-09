/**
 * cycle414 보완 4차 — N3-1: 사다리(`Ladder`) 라벨 x 범위 순수 함수 경계값 테스트.
 *
 * 3차 판정(verdict3.md) — `components/StrategyMonitor.tsx` `Ladder` 가 합친 그룹의 글자를
 * `<text x={g.x} textAnchor="middle">` 로 그려 좌우 보정이 없어, 긴 라벨이 그림 폭(W=220) 밖으로
 * 잘렸다(돈키언 무장 뒤 「손절 100,000」 통째로 소실 · VCP 매수 직후 「매수 400,0」 에서 끊김).
 * playwright 실측(2건): 36자 라벨 폭 141.2px(센터 x=26 → clip [-44.6, 96.6]), 23자 라벨 폭
 * 94.6px(센터 x=183.5 → clip [136.2, 230.8]). jsdom 에는 실제 글자폭이 없어(getBBox=0) 여기서는
 * 추정 폭 함수(`estimateLadderLabelWidth`)·클램프 함수(`clampLadderLabelCenter`)·같은 줄 겹침
 * 해소(`resolveLadderRowOverlaps`)만 순수 함수 단위로 경계값을 본다. 실제 렌더 좌표는 playwright
 * (`scratchpad/c414/fix4/tester/measure.ts`)로 따로 확인한다.
 */
import { describe, expect, it } from 'vitest'

import {
  LADDER_LABEL_CHAR_WIDTH_PX,
  estimateLadderLabelWidth,
  clampLadderLabelCenter,
  resolveLadderRowOverlaps,
} from '../strategyMonitor'

describe('estimateLadderLabelWidth — 글자수 × 글자당 폭', () => {
  it('빈 문자열 → 0', () => {
    expect(estimateLadderLabelWidth('')).toBe(0)
  })
  it('실측 보정값(자당 4.3px)과 일치', () => {
    const text = '손절 100,000 / 매수 100,000 / 무장 100,000' // 36자, 실측 141.2px
    expect(estimateLadderLabelWidth(text)).toBeCloseTo(36 * LADDER_LABEL_CHAR_WIDTH_PX, 5)
    // 과대추정(안전마진) — 실측보다 넓게 잡아 잘림보다 클램프 쪽으로 기운다.
    expect(estimateLadderLabelWidth(text)).toBeGreaterThan(141.2)
  })
})

describe('clampLadderLabelCenter — 라벨 중심 x 를 [0, boardWidth] 안으로', () => {
  const W = 220

  it('짧은 라벨 · 가운데(x=110) → 그대로(클램프 불필요)', () => {
    const r = clampLadderLabelCenter(110, 20, W)
    expect(r.anchor).toBe('middle')
    expect(r.x).toBe(110)
  })

  it('왼쪽 경계 — 3차 실측 사례(폭 141.2, 센터 x=26) → 글자폭/2(≈70.6)로 당겨져 왼쪽이 0 이상', () => {
    const labelWidth = 141.2
    const r = clampLadderLabelCenter(26, labelWidth, W)
    expect(r.anchor).toBe('middle')
    expect(r.x).toBeCloseTo(labelWidth / 2, 5)
    expect(r.x - labelWidth / 2).toBeGreaterThanOrEqual(-1e-9) // 왼쪽 가장자리 ≥ 0
  })

  it('오른쪽 경계 — 3차 실측 사례(폭 94.6, 센터 x=183.5) → W-글자폭/2(≈172.7)로 당겨져 오른쪽이 W 이하', () => {
    const labelWidth = 94.6
    const r = clampLadderLabelCenter(183.5, labelWidth, W)
    expect(r.anchor).toBe('middle')
    expect(r.x).toBeCloseTo(W - labelWidth / 2, 5)
    expect(r.x + labelWidth / 2).toBeLessThanOrEqual(W + 1e-9) // 오른쪽 가장자리 ≤ W
  })

  it('경계값 — centerX 가 정확히 half 일 때 클램프 no-op', () => {
    const r = clampLadderLabelCenter(50, 100, W) // half=50
    expect(r.x).toBe(50)
  })

  it('경계값 — centerX 가 정확히 boardWidth-half 일 때 클램프 no-op', () => {
    const r = clampLadderLabelCenter(170, 100, W) // W-half=170
    expect(r.x).toBe(170)
  })

  it('글자폭 ≥ 보드폭(기형적으로 긴 합친 라벨) → 왼쪽 경계(x=0, anchor=start)', () => {
    const r = clampLadderLabelCenter(110, 300, W)
    expect(r).toEqual({ x: 0, anchor: 'start' })
  })

  it('글자폭 == 보드폭 정확히(경계) → 왼쪽 경계', () => {
    const r = clampLadderLabelCenter(110, W, W)
    expect(r).toEqual({ x: 0, anchor: 'start' })
  })
})

describe('resolveLadderRowOverlaps — 같은 줄 라벨끼리 겹침 해소 + 보드 경계 우선', () => {
  const W = 220

  it('입력 0개 → 빈 배열', () => {
    expect(resolveLadderRowOverlaps([], W)).toEqual([])
  })

  it('입력 1개, 보드 안 → 그대로(겹칠 상대가 없다)', () => {
    expect(resolveLadderRowOverlaps([{ center: 50, width: 40 }], W)).toEqual([50])
  })

  it('입력 1개, 왼쪽 경계 밖 → 안쪽으로(겹침 해소와 별개로 경계는 항상 지킨다)', () => {
    const [c] = resolveLadderRowOverlaps([{ center: 5, width: 40 }], W)
    expect(c - 20).toBeGreaterThanOrEqual(-1e-9)
  })

  it('겹치지 않는 두 라벨 → 변화 없음', () => {
    const items = [{ center: 30, width: 20 }, { center: 150, width: 20 }]
    expect(resolveLadderRowOverlaps(items, W)).toEqual([30, 150])
  })

  it('겹치는 두 라벨 → 오른쪽을 밀어 간격을 벌린다(왼쪽은 고정)', () => {
    const items = [{ center: 50, width: 40 }, { center: 60, width: 40 }] // 겹침: 50±20=[30,70], 60±20=[40,80]
    const [c0, c1] = resolveLadderRowOverlaps(items, W)
    expect(c0).toBe(50)
    // 오른쪽 라벨의 왼쪽 가장자리가 왼쪽 라벨의 오른쪽 가장자리 + gap 이상이어야 한다.
    expect(c1 - 20).toBeGreaterThanOrEqual(c0 + 20 + 2 - 1e-9)
  })

  it('오른쪽으로 밀려 보드를 넘으면 전체를 안쪽으로 되민다(오른쪽 경계 우선)', () => {
    const items = [{ center: 190, width: 40 }, { center: 200, width: 40 }]
    const result = resolveLadderRowOverlaps(items, W)
    for (const c of result) {
      expect(c + 20).toBeLessThanOrEqual(W + 1e-9)
      expect(c - 20).toBeGreaterThanOrEqual(-1e-9)
    }
    // 서로 겹치지 않아야 한다.
    const sorted = [...result].sort((a, b) => a - b)
    expect(sorted[1] - 20).toBeGreaterThanOrEqual(sorted[0] + 20 - 1e-6)
  })

  it('세 라벨이 전부 겹쳐 있어도 좌→우 순서를 지키며 보드 안에 들어온다', () => {
    const items = [{ center: 20, width: 30 }, { center: 25, width: 30 }, { center: 30, width: 30 }]
    const result = resolveLadderRowOverlaps(items, W)
    expect(result[0]).toBeLessThanOrEqual(result[1])
    expect(result[1]).toBeLessThanOrEqual(result[2])
    expect(result[0] - 15).toBeGreaterThanOrEqual(-1e-9)
    expect(result[2] + 15).toBeLessThanOrEqual(W + 1e-9)
  })
})
