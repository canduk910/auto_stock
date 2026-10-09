/**
 * cycle414 보완 1차 (L2) — `extractDailyFinalCounts`·`computeZeroStreak` 를
 * `pages/StrategyFunnel`(지연 로딩 대상 페이지)에서 떼어 둔 공용 유틸.
 *
 * `StrategyMonitor`·`Dashboard` 는 14일 추이 선 그래프 하나 때문에 이 두 함수만 필요했는데,
 * 지금껏 `pages/StrategyFunnel`(전체 페이지)을 정적 import 해서 vite 의 `lazy(() => import(...))`
 * 지연 로딩 청크가 메인 번들에 합쳐지고 있었다(§2.10 L2). `pages/StrategyFunnel.tsx` 는 이 파일을
 * 재수출해 기존 테스트 import 경로(`../StrategyFunnel`)를 그대로 보존한다.
 */
import type { FunnelSnapshot } from '../api/strategy-funnel'

export interface DailyFinalCount {
  date: string
  count: number
}

/**
 * getRecentFunnel 응답(여러 날짜×여러 단계 혼재)에서 날짜별 "최종 단계" 통과 수만 추출.
 * 최종 단계 = step_no===99 우선(수동 trigger/자동 09:30 캡처 공통 계약), 없으면 그 날짜의 최대 step_no.
 */
export function extractDailyFinalCounts(snapshots: FunnelSnapshot[]): DailyFinalCount[] {
  const byDate = new Map<string, FunnelSnapshot[]>()
  for (const snap of snapshots) {
    const list = byDate.get(snap.target_date)
    if (list) {
      list.push(snap)
    } else {
      byDate.set(snap.target_date, [snap])
    }
  }
  const result: DailyFinalCount[] = []
  for (const [date, rows] of byDate.entries()) {
    const finalRow =
      rows.find((r) => r.step_no === 99) ??
      rows.reduce((a, b) => (b.step_no > a.step_no ? b : a))
    result.push({ date, count: finalRow.survived_count })
  }
  result.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
  return result
}

/** daily 배열 끝(최근일)부터 역순으로 count===0 이 연속되는 길이. */
export function computeZeroStreak(daily: DailyFinalCount[]): number {
  let streak = 0
  for (let i = daily.length - 1; i >= 0; i--) {
    if (daily[i].count !== 0) break
    streak++
  }
  return streak
}
