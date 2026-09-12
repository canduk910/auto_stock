/**
 * cycle285 (2026-09-13) — 장운영상태 화면 신규 섹션 A "지금 시장은".
 *
 * 실시간 VI·거래정지·서킷브레이커(추정)를 보여준다. 백엔드 신규는 0 — 기존
 * `GET /api/realtime/market-operation`(cycle186, RealtimeHealth 5번째 카드가 쓰는 것과
 * 같은 응답)을 그대로 재사용한다. 조회·상태 판정은 페이지(`MarketState.tsx`)가 하고, 이
 * 컴포넌트는 순수 표현이다 — `useQuery`·시계를 이 파일에 두지 않는다(cycle282 FE19/FE20
 * 가드가 `components/MarketState*.tsx` 이름 규약으로 이 파일도 자동으로 감시한다).
 *
 * ## 반드시 지키는 것 세 가지 (명세 §4-2/§4-3/§4-4)
 *
 * 1. **관측 커버리지를 숨기지 않는다** — `H0UNMKO0` 는 대표 종목 + 보유·익일청산 종목만
 *    구독한다(매수 후보 미배치). "VI 0건" 을 "VI 없음" 으로 읽으면 없는 안전을 믿게 된다.
 *    그래서 이벤트 수신 종목 수(`last_event_count`)를 항상 병기한다.
 * 2. **서킷브레이커는 추정이다** — KIS 전용 필드가 없어 휴리스틱(사유 키워드 OR 전 시장
 *    거래정지 비율)으로 판정한다. "추정" 표기 + 판정 근거(halted/observed·사유 표본)를
 *    평시에도 보여준다(발동 시에만 보이면 "0/11 이 얼마나 먼지" 를 알 수 없다).
 * 3. **정산 후에는 별도 상태다** — 21:30 `_reset_daily_state` 가 VI/거래정지 메모리를
 *    비우므로 그 뒤 0 은 "이상 없음" 이 아니라 "집계 자체가 없다". 20:00~21:30 은 값이
 *    마지막 관측에서 **얼어붙은 채** 남아 있어 또 다른 상태다 — 세 상태를 구분한다.
 */
import type { MarketOperationStatus } from '../types/market-operation'
import type { MarketOpsEngine } from '../types/market-ops'

/** 저녁 구간 중 엔진은 살아 있지만(`running`) VI/거래정지 집계가 마지막 관측에서 얼어붙는
 *  구간의 phase 값 — `scheduler.py` 의 엔진 단계 이름이지 market-state 표의 phase 가
 *  아니다(cycle282 FE19 금지어와 겹치지 않는다, 서로 다른 어휘 체계). */
const FROZEN_ENGINE_PHASES = new Set(['closing', 'settling', 'log_analysis'])

type SessionState = 'live' | 'frozen' | 'ended' | 'unknown'

function sessionStateOf(engine: MarketOpsEngine | undefined): SessionState {
  if (!engine) return 'unknown'
  if (!engine.running || engine.phase === 'idle') return 'ended'
  if (FROZEN_ENGINE_PHASES.has(engine.phase)) return 'frozen'
  return 'live'
}

const SESSION_BADGE: Record<SessionState, { label: string; className: string }> = {
  live: { label: '관측 중', className: 'bg-sky-100 text-sky-800 border-sky-300' },
  frozen: {
    label: '장 종료 — 마지막 관측값',
    className: 'bg-beige-100 text-brown-700 border-beige-400',
  },
  ended: {
    label: '세션 종료 — 집계 없음',
    className: 'bg-navy-100 text-navy-800 border-navy-300',
  },
  unknown: { label: '엔진 상태 확인 불가', className: 'bg-gray-100 text-gray-500 border-gray-300' },
}

// cycle285 검증(honest 렌즈 MEDIUM #5) 시정 — beige-100/gray-100 배경 sRGB 거리가
// ≈10.5 로 근접해 "VI 발생" 이 "0건" 과 거의 같은 색으로 보였다(cycle261 이 같은
// 결함을 PortfolioRiskCard 에서 beige-200/800 로 고친 것과 동일 계열). beige-200 +
// border-beige-500 로 그 수정을 그대로 반복한다(거리 ≈39).
function countBadgeClass(count: number, tone: 'amber' | 'red'): string {
  if (count === 0) return 'bg-gray-100 text-gray-600 border-gray-300'
  return tone === 'amber'
    ? 'bg-beige-200 text-brown-800 border-beige-500'
    : 'bg-red-100 text-red-800 border-red-300'
}

const STAT_BADGE_BASE =
  'inline-flex items-center rounded px-2 py-0.5 text-xs font-medium border'

function StatBadge({
  testId,
  label,
  className,
}: {
  testId: string
  label: string
  className: string
}) {
  return (
    <span data-testid={testId} className={`${STAT_BADGE_BASE} ${className}`}>
      {label}
    </span>
  )
}

// 폴링 주기(30s)의 3배 — 이보다 오래된 값이면 "수신 지연" 으로 본다. 리터럴이지만
// 시각(HH:MM) 이 아니라 지속시간(초)이라 §4-1 시각 하드코딩 가드의 대상이 아니다.
const STALE_RECEIVE_SECS = 90

export function MarketStateNow({
  marketOp,
  marketOpLoading,
  marketOpError,
  marketOpUpdatedAt,
  engine,
  engineError,
}: {
  marketOp: MarketOperationStatus | undefined
  marketOpLoading: boolean
  marketOpError: boolean
  /** react-query `dataUpdatedAt`(epoch ms) — `Date.now()` 와의 차만 쓴다(§4-1 준수,
   *  절대 시각 파싱 아님). 부모(`MarketState.tsx`)의 1초 하트비트가 이 컴포넌트도
   *  함께 재렌더하므로 별도 타이머 없이 매초 갱신된다. */
  marketOpUpdatedAt?: number
  engine: MarketOpsEngine | undefined
  engineError: boolean
}) {
  const receivedAgoSecs =
    marketOp && marketOpUpdatedAt ? Math.max(0, Math.floor((Date.now() - marketOpUpdatedAt) / 1000)) : null
  const isStaleReceive = receivedAgoSecs !== null && receivedAgoSecs > STALE_RECEIVE_SECS

  return (
    <section
      data-testid="market-state-now-section"
      className="rounded-lg bg-white p-4 shadow"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-gray-900">지금 시장은</h2>
        {!engineError ? (
          <span
            data-testid="market-state-now-session-badge"
            data-state={sessionStateOf(engine)}
            className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium ${
              SESSION_BADGE[sessionStateOf(engine)].className
            }`}
          >
            {SESSION_BADGE[sessionStateOf(engine)].label}
          </span>
        ) : (
          <span
            data-testid="market-state-now-session-badge"
            data-state="error"
            className="inline-flex items-center rounded border border-gray-300 bg-gray-50 px-1.5 py-0.5 text-xs text-gray-500"
          >
            엔진 상태 조회 실패
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-gray-500">
        실시간 VI·거래정지·서킷브레이커(추정) — KIS 장운영정보 채널의 실측이다. 표(아래)는 코드
        상수이고, 이 섹션만 실제 수신값이다.
      </p>

      {marketOpLoading ? (
        <div
          data-testid="market-state-now-loading"
          className="mt-3 h-16 animate-pulse rounded bg-gray-100"
        />
      ) : marketOpError || !marketOp ? (
        <div
          data-testid="market-state-now-error"
          className="mt-3 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800"
        >
          장운영 실시간 조회 실패 — 이 섹션만 비어 있다(아래 야간작업·시간표는 정상일 수 있다).
        </div>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StatBadge
              testId="market-state-now-vi"
              label={`VI ${marketOp.vi_active_count}건`}
              className={countBadgeClass(marketOp.vi_active_count, 'amber')}
            />
            <StatBadge
              testId="market-state-now-halt"
              label={`거래정지 ${marketOp.halt_active_count}건`}
              className={countBadgeClass(marketOp.halt_active_count, 'red')}
            />
            <StatBadge
              testId="market-state-now-cb"
              label={`서킷브레이커(추정) ${marketOp.circuit_breaker.suspected ? '의심' : '정상'}`}
              // cycle285 검증(honest #5) — CB 의심은 이 화면에서 가장 무거운 경보인데
              // beige 계열은 정상(gray-100)과 배경 거리 ≈10.5 로 거의 같은 색이었다.
              // red 계열(= 옆의 "거래정지" 배지와 같은 채도)로 올려 실제 위험도에
              // 맞는 대비를 준다 — "추정" 문구는 라벨에 그대로 남아 확정처럼 보이지
              // 않는다.
              className={
                marketOp.circuit_breaker.suspected
                  ? 'bg-red-200 text-red-900 border-red-400'
                  : 'bg-gray-100 text-gray-600 border-gray-300'
              }
            />
            <span
              data-testid="market-state-now-representative"
              className="inline-flex items-center rounded border border-gray-200 bg-gray-50 px-2 py-0.5 font-mono text-xs text-gray-600"
              title="대표 종목의 마지막 장운영 코드 — 그 종목 이벤트가 아직 없으면 비어 있다"
            >
              대표 장운영코드{' '}
              {marketOp.circuit_breaker.representative_mkop_cls_code || '—'}
            </span>
          </div>

          <p
            data-testid="market-state-now-coverage-note"
            className="mt-2 rounded bg-gray-50 px-2 py-1.5 text-[0.7rem] leading-snug text-gray-500"
          >
            이벤트 수신 {marketOp.last_event_count}종목 기준 — 대표 종목과 보유·익일청산
            종목만 관측한다(매수 후보는 구독 대상이 아니다). 부팅 시 REST 로 미리 채운
            VI 값이 섞여 있을 수도 있다(그 종목은 이벤트 수신 집계에 없다). 그래서 "0건"
            은 "없다" 가 아니라 "관측 대상 안에 없다" 는 뜻이다.
          </p>

          {receivedAgoSecs !== null ? (
            <p
              data-testid="market-state-now-received-ago"
              data-stale={isStaleReceive}
              className={`mt-1 text-[0.65rem] ${isStaleReceive ? 'font-medium text-brown-700' : 'text-gray-400'}`}
            >
              {isStaleReceive
                ? `⚠️ 이 값은 ${receivedAgoSecs}초 전 수신 — 갱신이 지연되고 있다(값이 얼어붙었을 수 있다)`
                : `${receivedAgoSecs}초 전 수신`}
            </p>
          ) : null}

          <div
            data-testid="market-state-now-cb-basis"
            className="mt-2 rounded border border-gray-100 bg-gray-50 px-2 py-1.5 text-[0.7rem] leading-snug text-gray-600"
          >
            추정 근거 — 거래정지 {marketOp.circuit_breaker.halted}/관측{' '}
            {marketOp.circuit_breaker.observed}종목
            {marketOp.circuit_breaker.observed > 0
              ? ` (${Math.round(marketOp.circuit_breaker.halt_ratio * 100)}%)`
              : ''}
            . 사유 키워드 또는 거래정지 비율 임계로 판정하며 실제 CB 확인은 아니다.
            {marketOp.circuit_breaker.halt_reasons_sample.length > 0 ? (
              <span className="ml-1">
                사유 표본: {marketOp.circuit_breaker.halt_reasons_sample.join(', ')}
              </span>
            ) : null}
          </div>
        </>
      )}
    </section>
  )
}

export default MarketStateNow
