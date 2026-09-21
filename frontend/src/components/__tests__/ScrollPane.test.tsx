import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import ScrollPane from '../ScrollPane'

/**
 * cycle338 — 표를 창 크기에 맞춰 가로·세로 스크롤한다.
 *
 * 🔴 이 그물은 **값**을 잰다. 「래퍼가 렌더됐다」나 「클래스 문자열이 있다」만 보면
 * 높이 상한이 통째로 빠져도 전부 초록이다 — 그리고 상한이 빠진 상태가 바로 이
 * 컴포넌트가 고치려는 결함 그 자체다(가로 스크롤바가 표 맨 아래로 밀려난다).
 * 그래서 단언 대상은 **실제 `maxHeight` 픽셀값**과 **두 축 overflow** 다.
 */

const VIEWPORT_H = 900

function stubRectTop(top: number) {
  // jsdom 은 getBoundingClientRect 가 전부 0 이라 top 을 직접 심는다.
  return vi
    .spyOn(Element.prototype, 'getBoundingClientRect')
    .mockReturnValue({
      top,
      bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: top,
      toJSON: () => ({}),
    } as DOMRect)
}

beforeEach(() => {
  Object.defineProperty(window, 'innerHeight', {
    value: VIEWPORT_H, writable: true, configurable: true,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ScrollPane — 높이 상한 (값 검사)', () => {
  it('🔴 창 높이에서 자기 위치와 여백을 뺀 픽셀을 maxHeight 로 건다', () => {
    // 표가 화면 200px 지점에서 시작하면 남는 것은 900 − 200 − 24 = 676.
    stubRectTop(200)
    render(<ScrollPane><table /></ScrollPane>)
    const pane = screen.getByTestId('scroll-pane')
    expect(pane.style.maxHeight).toBe('676px')
    expect(pane.dataset.measured).toBe('px')
  })

  it('🔴 상한이 반드시 존재한다 — 이것이 빠지면 결함이 그대로 재현된다', () => {
    stubRectTop(100)
    render(<ScrollPane><table /></ScrollPane>)
    const pane = screen.getByTestId('scroll-pane')
    // 빈 문자열/none/auto 는 전부 "상한 없음" = 고치려는 그 상태다.
    expect(pane.style.maxHeight).not.toBe('')
    expect(pane.style.maxHeight).not.toBe('none')
  })

  it('창이 커지면 상한도 따라 커진다 — 고정 픽셀이 아니다', () => {
    stubRectTop(150)
    render(<ScrollPane><table /></ScrollPane>)
    const pane = screen.getByTestId('scroll-pane')
    expect(pane.style.maxHeight).toBe(`${900 - 150 - 24}px`)

    act(() => {
      Object.defineProperty(window, 'innerHeight', {
        value: 1400, writable: true, configurable: true,
      })
      window.dispatchEvent(new Event('resize'))
    })
    expect(pane.style.maxHeight).toBe(`${1400 - 150 - 24}px`)
  })

  it('🔴 좁은 자리에서도 최소 높이 아래로 줄지 않는다', () => {
    // top 이 890 이면 화면 안(900)이고 남는 것은 900 − 890 − 24 = −14px.
    stubRectTop(890)
    render(<ScrollPane><table /></ScrollPane>)
    expect(screen.getByTestId('scroll-pane').style.maxHeight).toBe('220px')
  })

  it('🔴 아직 화면 아래에 있는 표는 220px 에 갇히지 않는다', () => {
    // 대시보드 하단 카드 실측 = top 1387 · 창 800. 그대로 빼면 음수라 floor 로
    // 떨어져, 스크롤해서 도달해도 220px 짜리 표만 보인다.
    stubRectTop(1387)
    render(<ScrollPane><table /></ScrollPane>)
    expect(screen.getByTestId('scroll-pane').style.maxHeight).toBe('876px')
  })

  it('🔴 페이지가 스크롤돼 top 이 음수여도 창 높이를 넘지 않는다', () => {
    // 이 케이스가 CI 에서 실제로 터졌다 — 클릭 자동 스크롤로 top 이 −600 이 되자
    // `900 − (−600) − 24 = 1476` 이 되어 pane 바닥이 화면 밖으로 나갔다.
    // 그 상태가 바로 이 컴포넌트가 고치려던 결함(가로 스크롤바가 안 보인다)이다.
    stubRectTop(-600)
    render(<ScrollPane><table /></ScrollPane>)
    const pane = screen.getByTestId('scroll-pane')
    expect(pane.style.maxHeight).toBe('876px')   // 900 − 0 − 24, 1476 이 아니다
    expect(parseInt(pane.style.maxHeight, 10)).toBeLessThanOrEqual(900)
  })

  it('top 이 0 이면 창 높이에서 여백만 뺀다', () => {
    stubRectTop(0)
    render(<ScrollPane><table /></ScrollPane>)
    expect(screen.getByTestId('scroll-pane').style.maxHeight).toBe('876px')
  })

  it('minHeight·bottomGutter 를 실제로 계산에 쓴다', () => {
    stubRectTop(100)
    render(<ScrollPane minHeight={300} bottomGutter={60}><table /></ScrollPane>)
    // 900 − 100 − 60 = 740 (최소 300 위)
    expect(screen.getByTestId('scroll-pane').style.maxHeight).toBe('740px')
  })

  it('측정이 불가능하면 vh 로 물러서되 상한은 유지한다', () => {
    vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(() => {
      throw new Error('측정 불가')
    })
    render(<ScrollPane><table /></ScrollPane>)
    const pane = screen.getByTestId('scroll-pane')
    expect(pane.style.maxHeight).toBe('70vh')
    expect(pane.dataset.measured).toBe('vh')
  })
})

describe('ScrollPane — 스크롤 축과 머리글 고정', () => {
  it('🔴 두 축 모두 스크롤한다 — overflow-x-auto 단독은 결함 상태다', () => {
    stubRectTop(100)
    render(<ScrollPane><table /></ScrollPane>)
    const cls = screen.getByTestId('scroll-pane').className
    expect(cls).toContain('overflow-auto')
    // 가로 전용으로 되돌리는 회귀를 잡는다.
    expect(cls).not.toContain('overflow-x-auto')
  })

  it('표 머리글을 기본으로 고정한다', () => {
    stubRectTop(100)
    render(<ScrollPane><table /></ScrollPane>)
    const pane = screen.getByTestId('scroll-pane')
    expect(pane.dataset.stickyHeader).toBe('on')
    expect(pane.className).toContain('[&_thead_th]:sticky')
    expect(pane.className).toContain('[&_thead_th]:top-0')
  })

  it('머리글 고정을 끌 수 있다 (표가 아닌 콘텐츠용)', () => {
    stubRectTop(100)
    render(<ScrollPane stickyHeader={false}><div /></ScrollPane>)
    const pane = screen.getByTestId('scroll-pane')
    expect(pane.dataset.stickyHeader).toBe('off')
    expect(pane.className).not.toContain('[&_thead_th]:sticky')
  })

  it('testId 를 바꿔 한 화면에 여럿 둘 수 있다', () => {
    stubRectTop(100)
    render(
      <>
        <ScrollPane testId="pane-a"><table /></ScrollPane>
        <ScrollPane testId="pane-b"><table /></ScrollPane>
      </>,
    )
    expect(screen.getByTestId('pane-a')).toBeInTheDocument()
    expect(screen.getByTestId('pane-b')).toBeInTheDocument()
  })

  it('자식을 그대로 렌더한다', () => {
    stubRectTop(100)
    render(<ScrollPane><div data-testid="child">내용</div></ScrollPane>)
    expect(screen.getByTestId('child')).toHaveTextContent('내용')
  })
})
