import type { LlmEvaluationSummary } from '../types/llm-evaluation'

/**
 * cycle337 — AI 매수평가 **점수**를 거래 목록에서 바로 보여 준다.
 *
 * 전에는 점수를 보려면 「AI 자문」 버튼을 눌러 팝업을 열어야 했다. 한 화면에 20~30행이
 * 있는데 행마다 팝업을 여닫는 것은 **훑어보기가 불가능**하다는 뜻이다 — 어느 매수가
 * 낮은 점수를 받고도 나갔는지 한눈에 비교할 수 없었다.
 *
 * 🔴 **추가 조회가 없다.** 점수는 이미 배치 요약 응답(`LlmEvaluationSummary.score`)에
 * 실려 온다. 버튼의 활성/비활성을 정하려고 이미 받아 둔 그 값을 화면에 그리는 것뿐이라
 * 네트워크 비용이 0 이다. 팝업은 근거·위험·토큰 같은 **상세**를 계속 담당한다.
 *
 * ## 판정의 출처 — `would_block` 이 정본이고 점수 비교는 폴백이다
 *
 * 「이 평가가 매수를 막았을 것인가」는 서버가 평가 시점에 기록한 `would_block` 이 정본이다.
 * 화면에서 `score >= min_score` 를 다시 계산하면 그 시점의 임계와 지금 임계가 다를 때
 * **화면이 과거를 거짓으로 말한다**(임계는 전략 파라미터라 바뀐다). 그래서 `would_block` 이
 * 있으면 그것을 쓰고, `null`(구 기록·평가 실패)일 때만 점수 비교로 폴백한다.
 *
 * ⚠️ 평가가 실패한 행은 `result='failed'` · `score=null` 이다(마이그레이션 043 — 실패도
 * 1행을 남긴다). 그 경우 숫자 자리에 `–` 를 그리고 사유를 `title` 로 준다. 빈칸으로 두면
 * 「평가를 안 했다」와 「평가가 실패했다」가 같은 모양이 되는데, 둘은 다른 사실이다.
 */

/** 점수 자리에 아무것도 없을 때 쓰는 너비 유지용 자리표. */
const EMPTY_MARK = '·'

export interface LlmScoreBadgeProps {
  /** 배치 요약에서 찾은 그 주문의 평가. 없으면 `null`/`undefined`. */
  summary?: LlmEvaluationSummary | null
  /**
   * 같은 행에 평가가 여럿일 때(매매손익의 피라미딩 페어) 총 개수.
   * 2 이상이면 «첫 매수 기준» 임을 `title` 로 알린다.
   */
  matchedCount?: number
  /** 테스트·E2E 가 잡을 고정 식별자. */
  testId?: string
}

/** 점수 배지의 표시 상태 — 테스트가 문자열이 아니라 **이 값**을 단언한다. */
export type LlmScoreTone = 'pass' | 'block' | 'failed' | 'none'

/**
 * 화면에 그릴 것을 **순수 함수로** 뽑는다.
 *
 * 🔴 렌더와 분리한 이유 = 이 판정(통과/차단/실패/없음)이 이 컴포넌트의 **계약**이고,
 * 색 클래스 문자열은 계약이 아니다. 테스트가 `bg-red-50` 같은 것을 단언하면 디자인을
 * 손볼 때마다 붉어져 결국 무시당한다(이 저장소가 cycle318 에서 겪은 그 실패다).
 */
export function resolveLlmScoreTone(
  summary?: LlmEvaluationSummary | null,
): { tone: LlmScoreTone; text: string } {
  if (!summary) return { tone: 'none', text: EMPTY_MARK }
  const score = summary.score
  if (summary.result === 'failed' || score === null || score === undefined) {
    return { tone: 'failed', text: '–' }
  }
  // `would_block` 이 정본 — 없을 때만 임계 비교로 폴백한다(위 docstring).
  const blocked =
    summary.would_block === null || summary.would_block === undefined
      ? score < summary.min_score
      : summary.would_block
  return { tone: blocked ? 'block' : 'pass', text: String(score) }
}

const TONE_CLASS: Record<LlmScoreTone, string> = {
  // 통과 — 눈에 띄지 않아야 한다. 대부분의 행이 여기 속하므로 강조하면 화면이 시끄럽다.
  pass: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  // 🔴 차단 판정 — 「점수가 기준에 못 미쳤는데 주문은 나갔다」는 뜻이라 눈에 띄어야 한다.
  //    현재 AI 평가는 shadow(관측 전용)라 실제로 막지는 않는다.
  block: 'text-red-700 bg-red-50 border-red-200',
  failed: 'text-gray-400 bg-gray-50 border-gray-200',
  none: 'text-gray-300 border-transparent',
}

export default function LlmScoreBadge({
  summary,
  matchedCount,
  testId,
}: LlmScoreBadgeProps) {
  const { tone, text } = resolveLlmScoreTone(summary)

  const title = (() => {
    if (tone === 'none') return '평가 기록 없음'
    if (tone === 'failed') {
      const why = summary?.reason ? `: ${summary.reason}` : ''
      return `평가 실패${why} — 점수 없음`
    }
    const base = `AI 매수평가 ${summary!.score}점 (기준 ${summary!.min_score}점)`
    const verdict = tone === 'block' ? ' — 기준 미달' : ''
    // 🔴 평가가 여럿인 행은 «어느 것을 보고 있는지» 를 반드시 밝힌다. 안 밝히면
    //    운영자가 그 숫자를 페어 전체의 대표값으로 읽는다(회고 정본은 «첫 매수» 다).
    const multi =
      matchedCount && matchedCount > 1
        ? ` · 이 행의 평가 ${matchedCount}건 중 첫 매수 기준`
        : ''
    return `${base}${verdict}${multi}`
  })()

  return (
    <span
      data-testid={testId ?? 'llm-score-badge'}
      data-tone={tone}
      title={title}
      // `tabular-nums` — 자릿수가 달라도 세로로 줄이 맞아 훑어보기가 된다.
      className={`inline-block min-w-[2.25rem] px-1.5 py-0.5 rounded border text-xs text-center tabular-nums ${TONE_CLASS[tone]}`}
    >
      {text}
      {matchedCount && matchedCount > 1 ? (
        <span className="ml-0.5 text-[0.65rem] align-super">+{matchedCount - 1}</span>
      ) : null}
    </span>
  )
}
