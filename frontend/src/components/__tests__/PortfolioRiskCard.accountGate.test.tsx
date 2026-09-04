/**
 * cycle251 Red — PortfolioRiskCard 계좌 SOFT 게이트 배지 (후속 F).
 *
 * 명세: `spec_cycle251_account_gate_observability.md` §1(F) · §2(F1~F5).
 *
 * ## 왜
 * `GET /api/portfolio/risk` 의 `data.account_gate` 는 **이미** 8키를 싣고 있는데
 * 프론트 타입에도 카드에도 없어서, cycle233 SOFT Σ상한 활성화 게이트의 한 축인
 * "장중 `age_secs <= 600`" 을 curl 로만 볼 수 있다. 이 배지가 그 실측 채널이다.
 *
 * ## 요구 행위
 * - F1 차단 중: `effective_gated=true` → 배지 "차단 중" + `open_risk_pct` 2자리 %
 *   + `evaluated_at` 을 **KST** HH:mm 로 (테스트 프로세스 TZ=UTC 고정 — 로컬타임
 *   추출 구현이면 "01:30" 이 나와 FAIL) + STALE 배지 부재
 * - F2 stale: `stale=true` → STALE 배지 + "25분 전"(age_secs=1500) 병기, 상태
 *   배지는 "정상"(fail-open 이라 실제로 차단 중이 아니다) + 동결 서명
 *   (`level=block ∧ stale ∧ !effective_gated`) 을 `title` 툴팁으로 설명
 * - F3 warn: `level='warn'` ∧ 미차단 → 배지 "경고"
 * - F4 부재: 키 없음 / null → `portfolio-risk-gate-absent` 한 줄, 배지 없음
 *   (기존 MSW 기본 응답이 이 경로 — 기존 4 테스트 무수정 통과가 계약)
 * - F5 error: `level='error'` → `reasons[0]` 병기
 *
 * RED 상태: `PortfolioRiskCard.tsx` 에 게이트 블록 미구현 → 전 케이스 testid 부재.
 */

import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import PortfolioRiskCard from '../PortfolioRiskCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

// `evaluated_at` 표기가 **브라우저 로컬타임이 아니라 KST** 임을 강제하기 위해
// 테스트 프로세스 TZ 를 UTC 로 고정한다(TradeHistoryGrid.test.tsx 선례).
// 로컬 개발 머신이 Asia/Seoul 이면 이 고정 없이는 잘못된 구현도 통과한다.
const ORIG_TZ = process.env.TZ
beforeAll(() => {
  process.env.TZ = 'UTC'
})
afterAll(() => {
  process.env.TZ = ORIG_TZ
})

const basePayload = {
  total_notional_won: 15_000_000,
  total_open_risk_won: 450_000,
  open_risk_pct_of_net: 3.5,
  concurrent_positions: 5,
  by_strategy: {
    momentum: { positions: 3, notional_won: 9_000_000, risk_won: 270_000 },
  },
  by_sector: {
    반도체: { positions: 3, notional_won: 9_000_000, risk_won: 270_000 },
  },
  top_sector: { sector: '반도체', risk_won: 270_000, risk_share_pct: 25.0 },
}

function serveGate(accountGate: unknown, omit = false) {
  const payload = omit ? { ...basePayload } : { ...basePayload, account_gate: accountGate }
  server.use(
    http.get('/api/portfolio/risk', () => HttpResponse.json(wrap(payload))),
  )
}

function renderCard() {
  render(
    <TestProviders>
      <PortfolioRiskCard />
    </TestProviders>,
  )
}

describe('PortfolioRiskCard — 계좌 SOFT 게이트 배지 (cycle251)', () => {
  it('F1: effective_gated=true → "차단 중" 배지 + 오픈리스크% + KST HH:mm, STALE 부재', async () => {
    serveGate({
      level: 'block',
      reasons: ['open_risk_pct=6.42 >= block_pct=6.00'],
      open_risk_pct: 6.42,
      evaluated_at: '2026-09-07T10:30:00+09:00',
      age_secs: 120,
      stale: false,
      stale_max_secs: 900,
      effective_gated: true,
    })
    renderCard()

    const block = await screen.findByTestId('portfolio-risk-account-gate')

    const badge = screen.getByTestId('portfolio-risk-gate-badge')
    expect(badge.textContent).toContain('차단 중')

    // 오픈 리스크 — 소수 2자리 %
    expect(block.textContent).toContain('6.42%')

    // 평가 시각 — KST 표기. TZ=UTC 프로세스에서 로컬타임 추출이면 "01:30" 이 나온다.
    expect(block.textContent).toContain('10:30')
    expect(block.textContent).not.toContain('01:30')

    // 신선(stale=false) → STALE 배지 없음
    expect(screen.queryByTestId('portfolio-risk-gate-stale')).toBeNull()
    // 부재 안내도 없음
    expect(screen.queryByTestId('portfolio-risk-gate-absent')).toBeNull()
  })

  it('F1-b: 오후 평가 시각은 24시제 HH:mm — "13:05"(ko-KR 기본 12시제 "오후 01:05" 금지)', async () => {
    // tester 보강(cycle251 Verify) — ko-KR Intl 은 hour12 기본이 true 라 F1 의 10:30 표본은
    // "오전 10:30" 으로도 통과한다. 오후 표본으로 24시제(HH:mm) 계약을 못박는다
    // (RefreshProgressBanner/TradeHistoryGrid 등 기존 6곳 전부 hour12:false).
    serveGate({
      level: 'ok',
      reasons: [],
      open_risk_pct: 1.25,
      evaluated_at: '2026-09-07T13:05:00+09:00',
      age_secs: 30,
      stale: false,
      stale_max_secs: 900,
      effective_gated: false,
    })
    renderCard()

    const block = await screen.findByTestId('portfolio-risk-account-gate')
    expect(block.textContent).toContain('13:05')
    expect(block.textContent).not.toContain('01:05')
    expect(block.textContent).not.toMatch(/오전|오후/)
  })

  it('F2: stale=true → STALE 배지 + "25분 전" + 상태 배지 "정상"(fail-open) + 동결 서명 툴팁', async () => {
    serveGate({
      level: 'block',
      reasons: ['open_risk_pct=6.42 >= block_pct=6.00'],
      open_risk_pct: 6.42,
      evaluated_at: '2026-09-07T10:30:00+09:00',
      age_secs: 1500,
      stale: true,
      stale_max_secs: 900,
      effective_gated: false,
    })
    renderCard()

    const block = await screen.findByTestId('portfolio-risk-account-gate')

    const stale = screen.getByTestId('portfolio-risk-gate-stale')
    expect(stale.textContent).toContain('STALE')

    // age_secs=1500 → 25분
    expect(block.textContent).toContain('25분 전')

    // 실효 차단이 아니므로 상태 배지는 "정상" — `level=block` 을 그대로 보여주면
    // 운영자가 "지금 매수가 막혀 있다"고 오독한다(실제로는 fail-open 으로 풀렸다).
    const badge = screen.getByTestId('portfolio-risk-gate-badge')
    expect(badge.textContent).toContain('정상')
    expect(badge.textContent).not.toContain('차단 중')

    // 동결 서명 설명 — `title` 툴팁 (level=block ∧ stale ∧ !effective_gated)
    const titled = Array.from(block.querySelectorAll('[title]')).map(
      (el) => el.getAttribute('title') ?? '',
    )
    const titles = [block.getAttribute('title') ?? '', ...titled]
    expect(titles.some((t) => /fail-open/.test(t) && /stale/i.test(t))).toBe(true)
  })

  it('F2-b: age_secs 분 환산은 내림 — 1590s → "26분 전"(반올림/올림 27 금지)', async () => {
    // tester 보강(cycle251 Verify) — 뮤테이션 F7m(Math.floor→Math.ceil) 이 1500s 표본에서
    // 탈출했다(25 로 동일). "N분 전" 은 경과 시간이라 내림이 계약이다.
    serveGate({
      level: 'ok',
      reasons: [],
      open_risk_pct: 0.5,
      evaluated_at: '2026-09-07T09:00:00+09:00',
      age_secs: 1590,
      stale: true,
      stale_max_secs: 900,
      effective_gated: false,
    })
    renderCard()

    const block = await screen.findByTestId('portfolio-risk-account-gate')
    expect(block.textContent).toContain('26분 전')
    expect(block.textContent).not.toContain('27분 전')
  })

  it('F3: level=warn ∧ 미차단 → 배지 "경고"', async () => {
    serveGate({
      level: 'warn',
      reasons: ['open_risk_pct=5.10 >= warn_pct=5.00'],
      open_risk_pct: 5.1,
      evaluated_at: '2026-09-07T13:05:00+09:00',
      age_secs: 60,
      stale: false,
      stale_max_secs: 900,
      effective_gated: false,
    })
    renderCard()

    await screen.findByTestId('portfolio-risk-account-gate')
    const badge = screen.getByTestId('portfolio-risk-gate-badge')
    expect(badge.textContent).toContain('경고')
    expect(badge.textContent).not.toContain('차단 중')
    expect(screen.queryByTestId('portfolio-risk-gate-stale')).toBeNull()
  })

  it('F4-a: account_gate 키 부재(기본 MSW 형태) → 게이트 정보 없음 한 줄', async () => {
    serveGate(undefined, true)
    renderCard()

    const absent = await screen.findByTestId('portfolio-risk-gate-absent')
    expect(absent.textContent).toContain('게이트 정보 없음')
    expect(screen.queryByTestId('portfolio-risk-gate-badge')).toBeNull()
    expect(screen.queryByTestId('portfolio-risk-gate-stale')).toBeNull()
  })

  it('F4-b: account_gate=null → 동일 부재 경로', async () => {
    serveGate(null)
    renderCard()

    const absent = await screen.findByTestId('portfolio-risk-gate-absent')
    expect(absent.textContent).toContain('게이트 정보 없음')
    expect(screen.queryByTestId('portfolio-risk-gate-badge')).toBeNull()
  })

  it('F4-c: MSW 기본 핸들러(오버라이드 없음)도 부재 경로 — 기존 4 테스트 무수정 통과 계약', async () => {
    renderCard()

    await waitFor(() => {
      expect(screen.getByTestId('portfolio-risk-gate-absent')).toBeTruthy()
    })
    expect(screen.queryByTestId('portfolio-risk-gate-badge')).toBeNull()
    // 기존 카드 본체는 그대로 렌더된다
    expect(screen.getByTestId('portfolio-risk-card')).toBeTruthy()
    expect(screen.getByTestId('portfolio-risk-open-pct')).toBeTruthy()
  })

  it('F5: level=error → reasons[0] 병기', async () => {
    serveGate({
      level: 'error',
      reasons: ['timeout'],
      open_risk_pct: null,
      evaluated_at: null,
      age_secs: null,
      stale: false,
      stale_max_secs: 900,
      effective_gated: false,
    })
    renderCard()

    const block = await screen.findByTestId('portfolio-risk-account-gate')
    expect(block.textContent).toContain('timeout')
    // open_risk_pct=null → "—"
    expect(block.textContent).toContain('—')
  })
})
