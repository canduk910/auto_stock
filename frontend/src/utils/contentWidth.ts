// 나브바 화면 폭 슬라이더 — 콘텐츠 max-width 사용자 조정 (localStorage 영속, 2026-07-24)
// cycle288: App.tsx 와 components/NavBar.tsx 양쪽이 이 모듈을 공유한다 — main 만 이
// 값으로 동적 확장되고, 나브 자체는 고정폭을 쓴다(App.tsx 주석 참고).
import { useState } from 'react'

export const CONTENT_WIDTH_STORAGE_KEY = 'autostock.contentWidth'
export const CONTENT_WIDTH_DEFAULT_LEVEL = 100

export function clampContentWidthLevel(value: number): number {
  return Math.min(100, Math.max(0, value))
}

export function readStoredContentWidthLevel(): number {
  try {
    const raw = window.localStorage.getItem(CONTENT_WIDTH_STORAGE_KEY)
    if (raw === null) return CONTENT_WIDTH_DEFAULT_LEVEL
    const parsed = parseInt(raw, 10)
    if (Number.isNaN(parsed)) return CONTENT_WIDTH_DEFAULT_LEVEL
    return clampContentWidthLevel(parsed)
  } catch {
    return CONTENT_WIDTH_DEFAULT_LEVEL
  }
}

export function contentMaxWidth(level: number): string {
  return `max(1024px, ${60 + level * 0.4}%)`
}

export function useContentWidth() {
  // SSR 없음(vite CSR) — lazy 초기화 함수가 최초 렌더 시 localStorage 를 직접 읽어 복원한다.
  const [level, setLevelState] = useState<number>(() => readStoredContentWidthLevel())

  const setLevel = (next: number) => {
    const clamped = clampContentWidthLevel(next)
    setLevelState(clamped)
    try {
      window.localStorage.setItem(CONTENT_WIDTH_STORAGE_KEY, String(clamped))
    } catch {
      // localStorage 접근 불가 환경(예: 프라이빗 모드) — graceful, state 는 이미 갱신됨
    }
  }

  return { level, setLevel }
}
