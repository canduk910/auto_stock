import { useCallback, useState } from "react"

/**
 * 비동기 데이터 fetch 공통 상태 관리 (원본 `macro_lite/hooks/useAsyncState.js` 이식).
 *
 * `run(asyncFn)` 호출 시 loading/error/data 를 자동 관리한다.
 * 에러 시 항상 throw — 호출측(`useMacro.ts`)에서 `.catch(() => {})` 로 삼킨다
 * (화면은 `error` state 로만 실패를 본다).
 *
 * ⚠️ TanStack Query 로 갈아엎지 않는다 — cycle303 은 이식이다(팀장 명세 §6).
 * 그래서 `frontend/CLAUDE.md` 「테스트 규약 1」의 `useQuery retry:1` 명시 의무는
 * 이 훅 계열에는 해당하지 않는다(그 의무는 `useQuery` 를 쓸 때만 발동한다).
 */
export function useAsyncState<T>(initialData: T | null = null) {
  const [data, setData] = useState<T | null>(initialData)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = useCallback(async (fn: () => Promise<T>): Promise<T> => {
    setLoading(true)
    setError(null)
    try {
      const result = await fn()
      setData(result)
      return result
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      throw e
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, setData, loading, error, setError, run }
}
