import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import LlmScoreBadge, { resolveLlmScoreTone } from '../LlmScoreBadge'
import type { LlmEvaluationSummary } from '../../types/llm-evaluation'

/**
 * cycle337 — 거래 목록에서 AI 매수평가 **점수**를 팝업 없이 본다.
 *
 * 🔴 이 그물은 **값**을 잰다. 「배지가 렌더됐다」나 「클래스 문자열이 있다」만 보면
 * 점수를 임계와 뒤바꾸거나 통과/차단 판정을 뒤집어도 전부 초록이다 — 이 저장소가
 * 최근 세 번 밟은 함정이다(헬퍼 인자 값 · 라우트 배선 · 로그 마커 필드).
 * 그래서 단언 대상은 **화면에 보이는 숫자**와 **`data-tone` 판정값**이다.
 */

const base = (over: Partial<LlmEvaluationSummary> = {}): LlmEvaluationSummary => ({
  order_no: '0000123456',
  trade_date: '2026-09-21',
  ticker: '005930',
  strategy_id: 'vcp_breakout',
  result: 'ok',
  reason: null,
  score: 82,
  min_score: 70,
  would_block: false,
  evaluated_at: '2026-09-21T09:20:00+09:00',
  ...over,
})

describe('resolveLlmScoreTone — 판정 (순수 함수)', () => {
  it('기록이 없으면 none — 숫자를 지어내지 않는다', () => {
    expect(resolveLlmScoreTone(null)).toEqual({ tone: 'none', text: '·' })
    expect(resolveLlmScoreTone(undefined)).toEqual({ tone: 'none', text: '·' })
  })

  it('평가 실패는 failed — "평가 안 함"과 다른 사실이다', () => {
    // 🔴 마이그레이션 043 계약 = 실패도 1행을 남기고 `score` 가 NULL 이다.
    //    이것을 none 으로 접으면 "평가를 안 했다"와 구별이 사라진다.
    expect(resolveLlmScoreTone(base({ result: 'failed', score: null }))).toEqual({
      tone: 'failed',
      text: '–',
    })
  })

  it('점수가 기준 이상이면 pass, 미만이면 block', () => {
    expect(resolveLlmScoreTone(base({ score: 82, would_block: false }))).toEqual({
      tone: 'pass',
      text: '82',
    })
    expect(resolveLlmScoreTone(base({ score: 41, would_block: true }))).toEqual({
      tone: 'block',
      text: '41',
    })
  })

  it('🔴 판정의 정본은 `would_block` 이고 점수 비교가 아니다', () => {
    // 임계는 전략 파라미터라 나중에 바뀐다. 화면이 `score >= min_score` 를 **다시**
    // 계산하면, 평가 당시엔 통과였던 기록이 오늘 임계로 재판정돼 **과거를 거짓으로**
    // 말한다. 그래서 서버가 그때 기록한 `would_block` 이 이긴다.
    const 서버는_차단이라_기록했다 = base({ score: 90, min_score: 70, would_block: true })
    expect(resolveLlmScoreTone(서버는_차단이라_기록했다).tone).toBe('block')

    const 서버는_통과라_기록했다 = base({ score: 50, min_score: 70, would_block: false })
    expect(resolveLlmScoreTone(서버는_통과라_기록했다).tone).toBe('pass')
  })

  it('`would_block` 이 없는 기록만 점수 비교로 폴백한다', () => {
    expect(resolveLlmScoreTone(base({ score: 50, min_score: 70, would_block: null })).tone)
      .toBe('block')
    expect(resolveLlmScoreTone(base({ score: 90, min_score: 70, would_block: null })).tone)
      .toBe('pass')
  })

  it('점수 0 을 결측으로 접지 않는다 (falsy 함정)', () => {
    // `if (!score)` 로 짜면 0점이 "기록 없음"이 된다 — 0점은 **가장 나쁜 평가**이지
    // 평가 부재가 아니다.
    expect(resolveLlmScoreTone(base({ score: 0, would_block: true }))).toEqual({
      tone: 'block',
      text: '0',
    })
  })
})

describe('LlmScoreBadge — 렌더', () => {
  it('점수를 화면에 숫자로 드러낸다 — 팝업을 열 필요가 없다', () => {
    render(<LlmScoreBadge summary={base({ score: 82 })} testId="s" />)
    const el = screen.getByTestId('s')
    expect(el).toHaveTextContent('82')
    expect(el).toHaveAttribute('data-tone', 'pass')
  })

  it('🔴 title 에 점수와 기준을 **둘 다** 담는다 — 맞바꿈이 드러나야 한다', () => {
    render(<LlmScoreBadge summary={base({ score: 41, min_score: 70, would_block: true })} testId="s" />)
    const title = screen.getByTestId('s').getAttribute('title') ?? ''
    // 두 수가 서로 달라야 맞바꿈을 잡는다(같으면 이 단언이 공허하다).
    expect(title).toContain('41점')
    expect(title).toContain('기준 70점')
    expect(title).toContain('기준 미달')
  })

  it('평가 실패는 사유를 title 로 알린다', () => {
    render(
      <LlmScoreBadge summary={base({ result: 'failed', score: null, reason: 'timeout' })} testId="s" />,
    )
    const el = screen.getByTestId('s')
    expect(el).toHaveTextContent('–')
    expect(el.getAttribute('title')).toContain('timeout')
  })

  it('한 행에 평가가 여럿이면 「첫 매수 기준」임을 밝힌다', () => {
    // 🔴 안 밝히면 운영자가 그 숫자를 페어 전체의 대표값으로 읽는다.
    render(<LlmScoreBadge summary={base({ score: 77 })} matchedCount={3} testId="s" />)
    const el = screen.getByTestId('s')
    expect(el).toHaveTextContent('77')
    expect(el).toHaveTextContent('+2') // 나머지 건수
    expect(el.getAttribute('title')).toContain('첫 매수 기준')
  })

  it('평가가 하나면 개수 표시를 붙이지 않는다', () => {
    render(<LlmScoreBadge summary={base({ score: 77 })} matchedCount={1} testId="s" />)
    expect(screen.getByTestId('s')).not.toHaveTextContent('+')
  })

  it('기록이 없으면 조용히 자리만 지킨다', () => {
    render(<LlmScoreBadge summary={null} testId="s" />)
    const el = screen.getByTestId('s')
    expect(el).toHaveAttribute('data-tone', 'none')
    expect(el.getAttribute('title')).toBe('평가 기록 없음')
  })
})
