import { useEffect, useState } from 'react'
import { formatKstDateTime } from '../utils/kst'

// cycle (2026-10-06) — 30년 전략 성적표 연구 보고서를 대시보드에 추가(사용자 승인).
// 보고서 자체는 frontend/public/backtest/scoreboard_30y.html 로 게시된 독립 HTML(갱신
// 절차 = tools/replay/scoreboard_page/publish_to_frontend.py). 이 페이지는 그 보고서를
// iframe 으로 감싸고, 생성 시각만 보고서 본문에서 뽑아 보여준다 — 숫자·판정은 전부
// 보고서 쪽 정본이고 이 페이지는 틀만 제공한다.
const REPORT_PATH = '/backtest/scoreboard_30y.html'

// 보고서 안의 `"generated_kst":"2026-10-06 11:41"` 꼴 문자열에서 생성 시각만 뽑는다.
// 보고서 포맷이 바뀌어 못 찾으면 null — 화면은 생성 시각 줄만 숨기고 나머지는 그대로 보인다.
function extractGeneratedKst(html: string): string | null {
  const m = html.match(/"generated_kst"\s*:\s*"([^"]+)"/)
  return m ? m[1] : null
}

type LoadState = 'loading' | 'error' | 'empty' | 'ready'

export default function Backtest() {
  const [state, setState] = useState<LoadState>('loading')
  const [generatedKst, setGeneratedKst] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setState('loading')
    fetch(REPORT_PATH)
      .then((res) => {
        if (!res.ok) throw new Error(`status ${res.status}`)
        return res.text()
      })
      .then((html) => {
        if (cancelled) return
        if (!html || html.trim().length === 0) {
          setState('empty')
          return
        }
        setGeneratedKst(extractGeneratedKst(html))
        setState('ready')
      })
      .catch(() => {
        if (!cancelled) setState('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">백테스팅</h1>
          <p className="text-sm text-gray-500 mt-1">
            30년 전략 성적표 — 연구 결과 보고서입니다. 실제 매매 설정과 무관합니다.
            {generatedKst && (
              <span className="ml-2 text-gray-400">
                (생성 {formatKstDateTime(`${generatedKst.replace(' ', 'T')}:00+09:00`)})
              </span>
            )}
          </p>
        </div>
        <a
          href={REPORT_PATH}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-medium text-blue-600 hover:text-blue-800 whitespace-nowrap shrink-0"
        >
          새 창에서 열기 ↗
        </a>
      </div>

      {state === 'loading' && (
        <div className="bg-white rounded-lg shadow p-8 animate-pulse" data-testid="backtest-loading">
          <div className="h-6 bg-gray-200 rounded w-1/3 mb-4" />
          <div className="space-y-2">
            <div className="h-4 bg-gray-100 rounded" />
            <div className="h-4 bg-gray-100 rounded w-5/6" />
          </div>
        </div>
      )}

      {state === 'error' && (
        <div className="bg-white rounded-lg shadow p-6 text-red-500" data-testid="backtest-error">
          서버 연결 끊김 — 성적표 보고서를 불러오지 못했습니다.
        </div>
      )}

      {state === 'empty' && (
        <div className="bg-white rounded-lg shadow p-6 text-gray-500" data-testid="backtest-empty">
          아직 게시된 성적표 보고서가 없습니다.
        </div>
      )}

      {state === 'ready' && (
        <div className="bg-white rounded-lg shadow overflow-hidden" style={{ height: 'calc(100vh - 220px)' }}>
          <iframe
            src={REPORT_PATH}
            title="30년 전략 성적표"
            data-testid="backtest-iframe"
            className="w-full h-full border-0"
          />
        </div>
      )}
    </div>
  )
}
