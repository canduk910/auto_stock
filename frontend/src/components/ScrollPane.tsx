import {
  useCallback, useEffect, useRef, useState,
  type HTMLAttributes, type ReactNode,
} from 'react'

/**
 * cycle338 — 표를 **브라우저 창 크기에 맞춰** 가로·세로로 스크롤한다.
 *
 * 고치는 것 = 「가로 스크롤바를 보려면 세로로 끝까지 내려가야 하는」 결함이다.
 * `overflow-x-auto` 래퍼에 **높이 상한이 없으면** 그 래퍼의 높이는 표 전체 높이가
 * 되고, 브라우저는 가로 스크롤바를 래퍼 **바닥**에 붙인다. 표가 500행이면 그
 * 바닥은 화면 밖 저 아래다. 상한을 씌우면 래퍼 바닥이 곧 화면 안이라 가로
 * 스크롤바가 항상 보인다.
 *
 * 🔴 **`maxHeight` 는 창 높이에서 이 요소의 화면상 위치를 뺀 값이다** — 고정
 * 픽셀이나 고정 `vh` 가 아니다. 화면 위쪽에 무엇이 얼마나 쌓여 있든(나브 · 환경
 * 배너 · 필터 바 · 요약 바) 남은 공간을 정확히 쓴다. 측정은 `resize` 와 문서
 * 크기 변화에만 반응하고 **`scroll` 은 듣지 않는다** — 스크롤마다 다시 재면
 * 「pane 이 커짐 → 문서가 길어짐 → 다시 잼」 되먹임이 생긴다.
 *
 * ⚠️ 갱신에 `_TOLERANCE_PX` 문턱을 둔다. 문턱이 없으면 1px 진동이
 * `ResizeObserver` 를 다시 깨워 무한 루프가 된다(브라우저가 루프를 끊으면
 * 콘솔에 `ResizeObserver loop` 오류만 남고 화면은 조용히 떤다).
 */

/** 창 아래쪽에 남기는 여백(px) — 가로 스크롤바 자체와 페이지 하단 숨통. */
const BOTTOM_GUTTER_PX = 24

/** 이 아래로는 줄이지 않는다 — 좁은 화면에서 표가 한 줄만 보이면 못 쓴다. */
const MIN_HEIGHT_PX = 220

/** 이 픽셀 미만 변화는 무시한다(되먹임 진동 차단). */
const TOLERANCE_PX = 8

export interface ScrollPaneProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  /** 표 머리글을 세로 스크롤 중에도 고정한다. 기본 true. */
  stickyHeader?: boolean
  /** 최소 높이(px). 기본 220. */
  minHeight?: number
  /** 창 아래 여백(px). 기본 24. */
  bottomGutter?: number
  className?: string
  testId?: string
}

/**
 * 창 높이에서 이 요소의 top 을 뺀 사용 가능 높이를 잰다.
 *
 * 측정 불가 환경(jsdom·SSR·`ResizeObserver` 부재)에서는 `null` 을 돌려주고
 * 호출자가 `vh` 폴백을 쓴다 — **높이 상한이 아예 없는 상태로 돌아가지 않는다**
 * (그러면 이 컴포넌트가 고치려는 결함이 그대로 재현된다).
 */
export function useViewportBoundedHeight(
  minHeight: number = MIN_HEIGHT_PX,
  bottomGutter: number = BOTTOM_GUTTER_PX,
) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [maxHeight, setMaxHeight] = useState<number | null>(null)

  const measure = useCallback(() => {
    const el = ref.current
    if (!el || typeof window === 'undefined') return
    let top = 0
    try {
      top = el.getBoundingClientRect().top
    } catch {
      return
    }
    const viewport = window.innerHeight
    if (!Number.isFinite(viewport) || viewport <= 0) return
    const available = viewport - top - bottomGutter
    const next = Math.max(minHeight, Math.round(available))
    setMaxHeight((prev) => (prev !== null && Math.abs(prev - next) < TOLERANCE_PX ? prev : next))
  }, [minHeight, bottomGutter])

  useEffect(() => {
    measure()
    if (typeof window === 'undefined') return
    window.addEventListener('resize', measure)

    // 위쪽 콘텐츠(필터 펼침·배너)가 커지면 top 이 바뀐다. 스크롤이 아니라
    // **레이아웃 변화**만 듣는다.
    let observer: ResizeObserver | null = null
    if (typeof ResizeObserver !== 'undefined' && document.body) {
      try {
        observer = new ResizeObserver(() => measure())
        observer.observe(document.body)
      } catch {
        observer = null
      }
    }
    return () => {
      window.removeEventListener('resize', measure)
      if (observer) observer.disconnect()
    }
  }, [measure])

  return { ref, maxHeight }
}

/**
 * 표(또는 넓은 콘텐츠)를 감싸 창 크기에 맞는 가로·세로 스크롤 영역으로 만든다.
 *
 * 쓰는 법 — 기존 `<div className="overflow-x-auto">` 를 그대로 대체한다.
 * 그 안의 `<table>` 은 손대지 않는다.
 */
export default function ScrollPane({
  children,
  stickyHeader = true,
  minHeight = MIN_HEIGHT_PX,
  bottomGutter = BOTTOM_GUTTER_PX,
  className = '',
  testId = 'scroll-pane',
  ...rest
}: ScrollPaneProps) {
  const { ref, maxHeight } = useViewportBoundedHeight(minHeight, bottomGutter)

  // 🔴 측정 전·측정 불가에도 **상한은 반드시 걸린다** — `vh` 폴백.
  const style = maxHeight !== null ? { maxHeight: `${maxHeight}px` } : { maxHeight: '70vh' }

  // Tailwind v4 arbitrary variant 로 자식 thead 를 고정한다. 표마다 thead 클래스를
  // 고쳐 다니지 않으려는 것이고, 배경은 각 표가 이미 가진 `bg-gray-50` 을 쓴다.
  const sticky = stickyHeader
    ? '[&_thead_th]:sticky [&_thead_th]:top-0 [&_thead_th]:z-10 [&_thead_th]:bg-gray-50'
    : ''

  return (
    // 🔴 `{...rest}` 가 `data-testid` **뒤**에 온다 — 교체된 자리가 이미 갖고 있던
    // `data-testid`(예: `stock-master-daily-table`)가 이기게 하려는 것이다. 앞에
    // 두면 그 자리의 기존 회귀 가드가 조용히 `scroll-pane` 을 보게 된다.
    <div
      ref={ref}
      data-testid={testId}
      {...rest}
      data-sticky-header={stickyHeader ? 'on' : 'off'}
      data-measured={maxHeight !== null ? 'px' : 'vh'}
      className={`overflow-auto overscroll-contain ${sticky} ${className}`.trim()}
      style={style}
    >
      {children}
    </div>
  )
}
