// 세후(net)/세전(gross) 토글 — 실적 화면 공통 (cycle411).
//
// 명세 = `_workspace/design/2026-10-08_cycle411_cost_overlay.md` (사용자 결정 10-08 Q3).
// 기본 = 세후(net), localStorage `autostock.costBasis` 영속(try/catch — 사생활 모드 등
// 예외 환경에서도 화면은 그려진다). 토글은 "화면 공통" 이라 여러 컴포넌트가 동시에
// 켜져 있어도 함께 바뀐다 — Context Provider 를 새로 추가하는 대신(기존 테스트가
// Provider 로 감싸지 않는다) 커스텀 이벤트로 같은 창의 다른 훅 인스턴스에 알린다.
import { useCallback, useEffect, useState } from 'react'

export const COST_BASIS_STORAGE_KEY = 'autostock.costBasis'
export type CostBasis = 'net' | 'gross'

const COST_BASIS_EVENT = 'autostock:cost-basis-change'

function readStoredCostBasis(): CostBasis {
  try {
    const raw = window.localStorage.getItem(COST_BASIS_STORAGE_KEY)
    return raw === 'gross' ? 'gross' : 'net'
  } catch {
    return 'net'
  }
}

export function useCostBasis(): [CostBasis, (next: CostBasis) => void] {
  const [basis, setBasis] = useState<CostBasis>(() => readStoredCostBasis())

  useEffect(() => {
    const onChange = (e: Event) => {
      const detail = (e as CustomEvent<CostBasis>).detail
      if (detail === 'net' || detail === 'gross') setBasis(detail)
    }
    window.addEventListener(COST_BASIS_EVENT, onChange)
    return () => window.removeEventListener(COST_BASIS_EVENT, onChange)
  }, [])

  const setCostBasis = useCallback((next: CostBasis) => {
    setBasis(next)
    try {
      window.localStorage.setItem(COST_BASIS_STORAGE_KEY, next)
    } catch {
      // 사생활 모드·차단 환경 — 메모리 상태는 이미 갱신됨(PN4)
    }
    window.dispatchEvent(new CustomEvent(COST_BASIS_EVENT, { detail: next }))
  }, [])

  return [basis, setCostBasis]
}
