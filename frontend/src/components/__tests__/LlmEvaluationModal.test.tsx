/**
 * cycle276 Red — AI 매수평가 팝업 `LlmEvaluationModal`.
 *
 * 명세 = `_workspace/red/cycle276_order_time_llm_eval_spec.md` §10.4 / §10.5 / §11.2(F1~F12).
 * 사용자 지시(2026-09-11) = "UI의 거래기록(체결, 매매손익)에서 각 행에 AI매매자문 버튼을 달고
 * 버튼 선택 시 팝업형태로 확인가능하도록 함."
 *
 * ## 계약
 * - props `{ orderNos: string[]; tradeDate?: string; onClose: () => void }`
 * - 본문은 `GET /api/llm-evaluations/{order_no}?trade_date=…` 1건을 조회한다.
 * - 404 = **회색 안내**(`llm-eval-notice`), 그 외(500·네트워크) = **빨강 오류**(`llm-eval-error`)
 *   — cycle266 이 종목마스터 일봉 탭에서 확정한 분기다(미적재 404 를 "조회 실패"로 오인 금지).
 * - `result === 'failed'` 인 **기록**은 오류가 아니다 — 평가가 실패했다는 사실을 담은 정상 기록이며
 *   실패 사유를 크게 보여준다(`llm-eval-failed`). "평가 안 함" 과 "평가 실패" 는 구별돼야 한다.
 * - 계좌번호는 **마스킹된 값만** 화면에 오른다(`account_no_masked`, 앞 4자리 + `****`).
 * - 접근성 = `role="dialog"` + `aria-modal="true"` + ESC 닫기 + 오버레이 클릭 닫기.
 *
 * ## RED 상태 (구현 전)
 * `frontend/src/components/LlmEvaluationModal.tsx` 부재 → 전 케이스 RED.
 * 정적 import 는 `tsc -b` 까지 깨므로(TS2307) 경로를 상수 변수에 담아 **동적 import** 로 싣는다.
 * Green 이후에도 그대로 동작하므로 이 파일은 구현이 들어와도 수정 대상이 아니다.
 */

import type { ComponentType } from 'react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { failed, makeLlmEvaluation, wrap } from '../../test/factories'
import { TestProviders } from '../../test/providers'
import type { LlmEvaluation } from '../../types/llm-evaluation'

interface LlmEvaluationModalProps {
  orderNos: string[]
  tradeDate?: string
  onClose: () => void
}

// 구현 전에는 모듈이 없다 — 변수 지정자 동적 import 는 TS 가 정적으로 해석하지 않아
// `tsc -b` 를 깨지 않으면서 런타임에는(구현 후) 정상 로드된다.
const MODAL_MODULE = '../LlmEvaluationModal'

let LlmEvaluationModal: ComponentType<LlmEvaluationModalProps> | null = null
let loadError: unknown = null

beforeAll(async () => {
  try {
    const mod = (await import(/* @vite-ignore */ MODAL_MODULE)) as {
      default: ComponentType<LlmEvaluationModalProps>
    }
    LlmEvaluationModal = mod.default
  } catch (e) {
    loadError = e
  }
})

function renderModal(props: Partial<LlmEvaluationModalProps> = {}) {
  if (!LlmEvaluationModal) {
    throw new Error(
      `LlmEvaluationModal 미구현 — ${MODAL_MODULE} 로드 실패: ${String(loadError)}`,
    )
  }
  const onClose = props.onClose ?? vi.fn()
  const Modal = LlmEvaluationModal
  render(
    <TestProviders>
      <Modal
        orderNos={props.orderNos ?? ['0000123456']}
        tradeDate={props.tradeDate ?? '2026-09-11'}
        onClose={onClose}
      />
    </TestProviders>,
  )
  return { onClose }
}

function serveDetail(records: Record<string, Partial<LlmEvaluation>>) {
  server.use(
    http.get('/api/llm-evaluations/:orderNo', ({ params }) => {
      const orderNo = String(params.orderNo)
      const rec = records[orderNo]
      if (!rec) {
        return HttpResponse.json(failed(`order_no=${orderNo} 평가 기록 없음`), {
          status: 404,
        })
      }
      return HttpResponse.json(wrap(makeLlmEvaluation({ ...rec, order_no: orderNo })))
    }),
  )
}

/** 접힘 상태 = 미렌더(조건부) 또는 비가시(hidden). 두 구현 모두 허용한다. */
function expectCollapsed(testId: string) {
  const el = screen.queryByTestId(testId)
  if (el === null) return
  expect(el).not.toBeVisible()
}

async function modalText(): Promise<string> {
  const modal = await screen.findByTestId('llm-eval-modal', {}, { timeout: 5000 })
  return modal.textContent ?? ''
}

describe('cycle276 — LlmEvaluationModal (Red)', () => {
  // -------------------------------------------------------------------
  // F1 — 점수 / 임계 / 차단여부
  // -------------------------------------------------------------------
  it('F1 점수·임계·would_block 을 llm-eval-score 에 렌더한다', async () => {
    serveDetail({ '0000123456': { score: 62, min_score: 70, would_block: true } })
    renderModal()

    const score = await screen.findByTestId('llm-eval-score', {}, { timeout: 5000 })
    const text = score.textContent ?? ''
    expect(text).toMatch(/62/)
    expect(text).toMatch(/70/)
    // 차단 여부가 문면으로 드러나야 한다(점수만 보여 주면 임계 검증이 불가능하다).
    expect(text).toMatch(/차단/)
    expect(text).not.toMatch(/NaN/)
  })

  // -------------------------------------------------------------------
  // F2 — 사유 / 핵심 위험 / 무효화 조건
  // -------------------------------------------------------------------
  it('F2 사유·핵심 위험·무효화 조건 3 섹션을 렌더한다', async () => {
    serveDetail({
      '0000123456': {
        rationale: '거래량 동반 돌파이나 지수 약세',
        key_risks: ['지수 약세', '돌파 폭 과소'],
        invalidations: ['목표가 하회 마감'],
      },
    })
    renderModal()

    const rationale = await screen.findByTestId('llm-eval-rationale', {}, { timeout: 5000 })
    expect(rationale.textContent).toContain('거래량 동반 돌파이나 지수 약세')

    const risks = screen.getByTestId('llm-eval-risks')
    expect(risks.textContent).toContain('지수 약세')
    expect(risks.textContent).toContain('돌파 폭 과소')

    const invalidations = screen.getByTestId('llm-eval-invalidations')
    expect(invalidations.textContent).toContain('목표가 하회 마감')
  })

  // -------------------------------------------------------------------
  // F3 — 주문 스냅샷
  // -------------------------------------------------------------------
  it('F3 주문 스냅샷(주문가·수량·구분·경로·보드·목표가·돌파폭)을 렌더한다', async () => {
    serveDetail({
      '0000123456': {
        order_price_won: 71800,
        ordered_qty: 3,
        order_division: 'MARKET',
        order_path: 'market',
        board: 'main',
        target_won: 71650,
        breakout_excess_bp: 20.9,
      },
    })
    renderModal()

    const order = await screen.findByTestId('llm-eval-order', {}, { timeout: 5000 })
    const text = order.textContent ?? ''
    expect(text).toMatch(/71,?800/)
    expect(text).toMatch(/3/)
    expect(text).toMatch(/MARKET/)
    expect(text).toMatch(/market/)
    expect(text).toMatch(/main/)
    expect(text).toMatch(/71,?650/)
    expect(text).toMatch(/20\.9/)
    expect(text).not.toMatch(/NaN/)
  })

  // -------------------------------------------------------------------
  // F4 — 모델 / 토큰 / 비용 / 지연 / 버전
  // -------------------------------------------------------------------
  it('F4 모델·토큰·비용·지연·버전을 llm-eval-meta 에 렌더한다', async () => {
    serveDetail({
      '0000123456': {
        model: 'gpt-5.6-luna',
        tokens_in: 3120,
        tokens_out: 210,
        cost_usd: 0.00438,
        latency_ms: 3120,
        prompt_version: 'a1b2c3d4e5f6',
        feature_version: '0f1e2d3c4b5a',
      },
    })
    renderModal()

    const meta = await screen.findByTestId('llm-eval-meta', {}, { timeout: 5000 })
    const text = meta.textContent ?? ''
    expect(text).toContain('gpt-5.6-luna')
    expect(text).toMatch(/3,?120/)
    expect(text).toMatch(/210/)
    expect(text).toMatch(/0\.0043/)
    // 버전 2종 — 프롬프트·지표가 바뀐 뒤의 행과 그 전의 행을 섞어 회귀하면 안 된다(명세 §7.1).
    expect(text).toContain('a1b2c3d4e5f6')
    expect(text).toContain('0f1e2d3c4b5a')
    expect(text).not.toMatch(/NaN/)
  })

  // -------------------------------------------------------------------
  // F4b — 계좌번호 마스킹 (C39/C40)
  // -------------------------------------------------------------------
  it('F4b 계좌번호는 마스킹된 값만 보여 준다', async () => {
    serveDetail({ '0000123456': { account_no_masked: '5011****' } })
    renderModal()

    // ⚠️ Green(cycle276) 정정 — `modalText()` 는 모달 **루트**가 서는 순간 해소되는데,
    // 계좌 마스킹 값은 상세 응답이 도착한 뒤에야 본문에 실린다. 원안은 로딩 중 문면을
    // 읽고 실패하는 경합이었다(구현과 무관). 본문이 설 때까지 기다리는 한 줄만 추가한다 —
    // 단언(마스킹 값은 보이고 원문은 안 보인다)은 원안 그대로다.
    await screen.findByTestId('llm-eval-meta', {}, { timeout: 5000 })
    const text = await modalText()
    expect(text).toContain('5011****')
    // 원문 계좌번호(앞 4자리 + 뒤 4자리)가 화면에 오르면 안 된다.
    expect(text).not.toMatch(/5011\d{4}/)
  })

  // -------------------------------------------------------------------
  // F5 — 입력 payload 접기
  // -------------------------------------------------------------------
  it('F5 입력 payload 는 기본 접힘이고 토글하면 펼쳐진다', async () => {
    serveDetail({
      '0000123456': {
        input_payload: { payload: { ticker: '005930' }, tech: { rsi14: 58.2 }, bars30: [] },
      },
    })
    renderModal()

    const toggle = await screen.findByTestId('llm-eval-payload-toggle', {}, { timeout: 5000 })
    expectCollapsed('llm-eval-payload-content')

    await userEvent.click(toggle)

    const content = await screen.findByTestId('llm-eval-payload-content', {}, { timeout: 5000 })
    expect(content).toBeVisible()
    expect(content.textContent).toContain('005930')
    expect(content.textContent).toContain('rsi14')
  })

  // -------------------------------------------------------------------
  // F6 — 모델 응답 원문 접기
  // -------------------------------------------------------------------
  it('F6 모델 응답 원문 토글이 동작한다', async () => {
    serveDetail({
      '0000123456': { raw_response: { content: '{"score":62,"rationale":"원문"}' } },
    })
    renderModal()

    const toggle = await screen.findByTestId('llm-eval-raw-toggle', {}, { timeout: 5000 })
    expectCollapsed('llm-eval-raw-content')

    await userEvent.click(toggle)

    const content = await screen.findByTestId('llm-eval-raw-content', {}, { timeout: 5000 })
    expect(content).toBeVisible()
    expect(content.textContent).toContain('score')
  })

  // -------------------------------------------------------------------
  // F7 — 실패 기록
  // -------------------------------------------------------------------
  it('F7 실패 기록은 실패 사유를 크게 보여 준다', async () => {
    serveDetail({
      '0000123456': {
        result: 'failed',
        reason: 'timeout',
        score: null,
        would_block: null,
        rationale: null,
      },
    })
    renderModal()

    const failedBox = await screen.findByTestId('llm-eval-failed', {}, { timeout: 5000 })
    expect(failedBox.textContent).toContain('timeout')
    // 실패 "기록" 은 조회 오류가 아니다 — 빨강 오류 분기로 새면 안 된다.
    expect(screen.queryByTestId('llm-eval-error')).toBeNull()
    expect(failedBox.textContent).not.toMatch(/NaN/)
  })

  // -------------------------------------------------------------------
  // F8 — 404 = 회색 안내
  // -------------------------------------------------------------------
  it('F8 404 는 회색 안내(llm-eval-notice)이고 빨강 오류가 아니다', async () => {
    serveDetail({}) // 어떤 order_no 도 없음 → 404
    renderModal()

    const notice = await screen.findByTestId('llm-eval-notice', {}, { timeout: 10000 })
    expect(notice.textContent).toMatch(/평가 기록 없음/)
    expect(screen.queryByTestId('llm-eval-error')).toBeNull()
  }, 20000)

  // -------------------------------------------------------------------
  // F9 — 500 = 빨강 오류
  // -------------------------------------------------------------------
  it('F9 500 은 빨강 오류(llm-eval-error)로 렌더한다', async () => {
    server.use(
      http.get('/api/llm-evaluations/:orderNo', () =>
        HttpResponse.json(failed('내부 오류'), { status: 500 }),
      ),
    )
    renderModal()

    const err = await screen.findByTestId('llm-eval-error', {}, { timeout: 10000 })
    expect(err.className).toMatch(/text-red|bg-red/)
    expect(screen.queryByTestId('llm-eval-notice')).toBeNull()
  }, 20000)

  // -------------------------------------------------------------------
  // F10 — ESC 닫기
  // -------------------------------------------------------------------
  it('F10 ESC 를 누르면 onClose 가 호출된다', async () => {
    serveDetail({ '0000123456': {} })
    const { onClose } = renderModal()

    await screen.findByTestId('llm-eval-modal', {}, { timeout: 5000 })
    await userEvent.keyboard('{Escape}')

    await waitFor(() => expect(onClose).toHaveBeenCalled(), { timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // F11 — 오버레이 클릭은 닫고, 패널 클릭은 닫지 않는다
  // -------------------------------------------------------------------
  it('F11 오버레이 클릭은 닫고 패널 내부 클릭은 닫지 않는다', async () => {
    serveDetail({ '0000123456': {} })
    const { onClose } = renderModal()

    const score = await screen.findByTestId('llm-eval-score', {}, { timeout: 5000 })
    await userEvent.click(score)
    expect(onClose).not.toHaveBeenCalled()

    // `llm-eval-modal` 이 오버레이 그 자체일 수도(권장), 패널일 수도 있다 —
    // 패널이면 그 바깥(부모)이 오버레이다. 두 배치 모두에서 계약을 잰다.
    const root = screen.getByTestId('llm-eval-modal')
    const panel = screen.getByRole('dialog')
    const overlay = root === panel ? (root.parentElement as HTMLElement) : root
    expect(overlay).not.toBeNull()
    await userEvent.click(overlay)
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1), { timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // F11b — 접근성 (role/aria/닫기 버튼)
  // -------------------------------------------------------------------
  it('F11b role=dialog · aria-modal · 닫기 버튼을 갖는다', async () => {
    serveDetail({ '0000123456': {} })
    const { onClose } = renderModal()

    const dialog = await screen.findByRole('dialog', {}, { timeout: 5000 })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog.getAttribute('aria-labelledby')).toBeTruthy()

    await userEvent.click(screen.getByRole('button', { name: '닫기' }))
    await waitFor(() => expect(onClose).toHaveBeenCalled(), { timeout: 5000 })
  })

  // -------------------------------------------------------------------
  // F12 — 다중 주문번호 = 탭 + 첫 매수 주문 고지
  // -------------------------------------------------------------------
  it('F12 매수 주문 2건이면 주문별 탭과 첫 매수 주문 고지를 렌더한다', async () => {
    serveDetail({
      '0000123456': { score: 62, ticker: '005930' },
      '0000123999': { score: 81, ticker: '005930' },
    })
    renderModal({ orderNos: ['0000123456', '0000123999'] })

    await screen.findByTestId('llm-eval-order-tab-0000123456', {}, { timeout: 5000 })
    expect(screen.getByTestId('llm-eval-order-tab-0000123999')).toBeInTheDocument()

    const text = await modalText()
    expect(text).toContain('2건')
    expect(text).toContain('첫 매수 주문')

    // 첫 주문의 점수가 먼저 보이고, 두 번째 탭을 누르면 그 주문의 점수로 바뀐다.
    await waitFor(
      () => expect(screen.getByTestId('llm-eval-score').textContent).toMatch(/62/),
      { timeout: 5000 },
    )
    await userEvent.click(screen.getByTestId('llm-eval-order-tab-0000123999'))
    await waitFor(
      () => expect(screen.getByTestId('llm-eval-score').textContent).toMatch(/81/),
      { timeout: 5000 },
    )
  }, 20000)

  // -------------------------------------------------------------------
  // F12b — 단일 주문에는 탭이 없다
  // -------------------------------------------------------------------
  it('F12b 매수 주문 1건이면 탭을 렌더하지 않는다', async () => {
    serveDetail({ '0000123456': {} })
    renderModal({ orderNos: ['0000123456'] })

    await screen.findByTestId('llm-eval-score', {}, { timeout: 5000 })
    expect(screen.queryByTestId('llm-eval-order-tab-0000123456')).toBeNull()
  })
})
