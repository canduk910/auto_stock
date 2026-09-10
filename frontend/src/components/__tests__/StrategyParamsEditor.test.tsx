/**
 * cycle278 Red — 전략 파라미터 편집기(`StrategyParamsEditor`) 행위 계약.
 *
 * 명세: `_workspace/red/cycle278_param_catalog_ui_spec.md` §3.5(C37~C44) · §6 · §7.2(F01~F20)
 * 이 파일이 작성된 시점에 `src/components/StrategyParamsEditor.tsx` 는 **없다**(Green 이 만든다).
 * 따라서 전건 RED 로 시작한다.
 *
 * ────────────────────────────────────────────────────────────────────────
 * Green 이 지켜야 하는 인터페이스 (이 파일이 그 계약의 정본이다)
 * ────────────────────────────────────────────────────────────────────────
 * ```tsx
 * interface StrategyParamsEditorProps {
 *   strategyId: string      // 편집 대상 전략 id
 *   onClose: () => void     // 닫기(×)·취소·저장 성공 시 호출
 *   now?: Date              // 장중 배너 판정의 테스트 seam. 생략 시 new Date()
 * }
 * export default function StrategyParamsEditor(props: StrategyParamsEditorProps)
 * ```
 * - 마운트 시 `useQuery({ queryKey: ['strategy-params-schema'], retry: 1, … })` 로
 *   `GET /api/strategies/params-schema` 한 번만 읽고 **그 응답만으로** 렌더한다.
 *   키 이름을 컴포넌트에 하드코딩하지 않는다(재드리프트 방지의 핵심 — `_ast_param_key_hardcode` 가 잠근다).
 * - 저장은 `updateStrategyParams(strategyId, 변경분만)` → `PUT /api/strategies/{id}/params`.
 *   **변경하지 않은 키는 보내지 않는다**(부분 dict 병합이 백엔드 계약이고, 전 키를 매번 보내면
 *   그중 한 키의 범위 위반이 전략 전체 저장을 422 로 막는다 — 구 `Settings.tsx` 패널의 HAZARD-2).
 * - `percent` 타입은 **화면만 %**, 저장은 비율(0.0~1.0). `float`+`unit="%"` 는 값 자체가 이미 퍼센트다.
 * - 포맷 분기는 **키가 아니라 `unit`/`type`** 으로 한다(`unit` 닫힌 어휘 12종).
 *
 * testid 규약(§6.3): 키·선택지 값의 밑줄은 **하이픈**으로 바꾼다
 *   (`max_positions` → `strategy-params-row-max-positions`,
 *    `tradable_boards` 의 값 `pre_nxt` → `strategy-params-choice-tradable-boards-pre-nxt`).
 *
 * 목: `frontend/src/test/fixtures/paramSchema.fixture.ts` — `param_catalog.py` 에서 **기계 생성**한
 * 골든 픽스처(손으로 쓴 요약이 아니다 — cycle266 재발 차단). MSW 기본 핸들러가 이 픽스처를 준다.
 *
 * 검증 대상 전략은 `volatility_breakout` — 7 그룹 전부 + percent/float%/원/enum/bool/list_str/
 * identity/deprecated/deprecated_for/range_src=none 을 한 전략 안에서 모두 갖는 유일한 전략이다.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'

import StrategyParamsEditor, { localBlocks } from '../StrategyParamsEditor'
import { server } from '../../test/server'
import { wrap } from '../../test/factories'
import { fixtureSpec, schemaWithCurrent } from '../../test/fixtures/paramSchema.fixture'
import type { ParamSpec } from '../../types/strategy-params'

const VB = 'volatility_breakout'
const LTV = 'long_tail_volatility'
const MOM = 'momentum'

/** KST 20:30 — 장외(경고 배너 없음). */
const OFF_HOURS = new Date('2026-09-11T11:30:00Z')
/** KST 10:00 — KRX 메인 세션(경고 배너 있음). */
const MAIN_HOURS = new Date('2026-09-11T01:00:00Z')

/** 그룹 아코디언 순서 = 스키마 `groups` 순서 (카탈로그 GROUPS 정본). */
const GROUP_IDS = [
  'entry',
  'exit',
  'sizing_risk',
  'scan_universe',
  'time_board',
  'observe_gate',
  'legacy',
] as const

/** testid 접미 규약 — 밑줄 → 하이픈. */
const dash = (key: string) => key.replace(/_/g, '-')

function renderEditor(
  opts: { strategyId?: string; now?: Date; onClose?: () => void } = {},
) {
  const onClose = opts.onClose ?? vi.fn()
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
  render(
    <QueryClientProvider client={qc}>
      <StrategyParamsEditor
        strategyId={opts.strategyId ?? VB}
        now={opts.now ?? OFF_HOURS}
        onClose={onClose}
      />
    </QueryClientProvider>,
  )
  return { onClose, user: userEvent.setup() }
}

/** 편집기 로딩 완료까지 대기. */
async function waitEditor() {
  return await screen.findByTestId('strategy-params-editor', undefined, {
    timeout: 5000,
  })
}

/**
 * 그룹 본문을 연다. 기본 접힘/펼침 어느 구현이든 통과하도록 이미 열려 있으면 클릭하지 않는다
 * (아코디언의 초기 상태는 이 사이클의 계약이 아니다 — "그룹으로 나뉘고 그 그룹의 키만 담는다"가 계약).
 */
async function openGroup(user: ReturnType<typeof userEvent.setup>, groupId: string) {
  const header = await screen.findByTestId(`strategy-params-group-${groupId}`)
  if (!screen.queryByTestId(`strategy-params-group-body-${groupId}`)) {
    await user.click(header)
  }
  return await screen.findByTestId(`strategy-params-group-body-${groupId}`)
}

/** 텍스트 입력 키의 값을 바꾼다. */
async function setInput(
  user: ReturnType<typeof userEvent.setup>,
  key: string,
  value: string,
) {
  const input = await screen.findByTestId(`strategy-params-input-${dash(key)}`)
  await user.clear(input)
  await user.type(input, value)
  return input as HTMLInputElement
}

/** PUT 요청 바디를 잡아 두는 핸들러. 응답은 호출자가 정한다. */
function capturePut(respond: () => Response) {
  const seen: { body: { params?: Record<string, unknown> } | null; count: number } = {
    body: null,
    count: 0,
  }
  server.use(
    http.put('/api/strategies/:id/params', async ({ request }) => {
      seen.count += 1
      seen.body = (await request.json()) as { params?: Record<string, unknown> }
      return respond()
    }),
  )
  return seen
}

const okResponse = (applied: Record<string, unknown>, warnings: unknown[] = []) =>
  HttpResponse.json(wrap({ applied, warnings }, '파라미터 저장 완료'))

describe('cycle278 F01~F02 — 스키마만으로 그룹/키를 렌더한다', () => {
  it('F01 그룹 아코디언이 스키마 groups 순서대로 7개 렌더된다', async () => {
    renderEditor()
    await waitEditor()

    const headers = GROUP_IDS.map((g) => screen.getByTestId(`strategy-params-group-${g}`))
    expect(headers).toHaveLength(7)

    // 문서 순서가 스키마 groups 순서와 같아야 한다.
    for (let i = 1; i < headers.length; i += 1) {
      const relation = headers[i - 1].compareDocumentPosition(headers[i])
      expect(
        relation & Node.DOCUMENT_POSITION_FOLLOWING,
        `그룹 순서 위반: ${GROUP_IDS[i - 1]} 다음에 ${GROUP_IDS[i]} 가 와야 한다`,
      ).toBeTruthy()
    }

    // 한글 라벨(스키마 label_ko) 이 그대로 쓰인다.
    expect(screen.getByTestId('strategy-params-group-entry')).toHaveTextContent('진입')
    expect(screen.getByTestId('strategy-params-group-legacy')).toHaveTextContent('레거시')
  })

  it('F02 그룹을 열면 그 그룹의 키만 그 본문에 담긴다', async () => {
    const { user } = renderEditor()
    await waitEditor()

    const exitBody = await openGroup(user, 'exit')
    expect(
      within(exitBody).getByTestId('strategy-params-row-stop-loss-rate'),
    ).toBeInTheDocument()
    // entry 그룹 키가 exit 본문 안에 있으면 그룹핑이 무의미하다.
    expect(
      within(exitBody).queryByTestId('strategy-params-row-k-period'),
    ).toBeNull()
  })

  it('F02b 전략마다 applies_to 에 맞는 키만 렌더된다 (VB 에 vcp 전용 키 없음)', async () => {
    renderEditor()
    await waitEditor()

    // base_depth_pct 는 vcp_breakout 전용 — VB 화면에 나오면 저장 시 unknown_key 422 를 부른다.
    expect(screen.queryByTestId('strategy-params-row-base-depth-pct')).toBeNull()
    // k_period 는 VB 키이므로 있어야 한다.
    expect(screen.getByTestId('strategy-params-row-k-period')).toBeInTheDocument()
  })

  it('F02c momentum 은 자기 10키만 렌더한다 (VB 전용 k_period 없음)', async () => {
    renderEditor({ strategyId: MOM })
    await waitEditor()

    expect(screen.getByTestId('strategy-params-row-buy-threshold')).toBeInTheDocument()
    expect(screen.queryByTestId('strategy-params-row-k-period')).toBeNull()
  })
})

describe('cycle278 F03~F08 — 타입·단위별 위젯과 표시 규약', () => {
  it('F03 percent 키는 저장값 0.1 을 10% 로 표시하고 편집값은 비율로 되돌려 보낸다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'sizing_risk')

    const input = (await screen.findByTestId(
      'strategy-params-input-position-ratio',
    )) as HTMLInputElement
    expect(Number(input.value), '화면 표시는 % (0.1 → 10)').toBeCloseTo(10, 6)

    const seen = capturePut(() => okResponse({ position_ratio: 0.12 }))
    await setInput(user, 'position_ratio', '12')
    await user.click(screen.getByTestId('strategy-params-save'))
    await user.click(await screen.findByRole('button', { name: '확인' }))

    await waitFor(() => expect(seen.count).toBe(1))
    expect(
      seen.body?.params?.position_ratio,
      '저장은 비율 — 12% 는 0.12 로 보낸다(100 을 저장하지 않는다)',
    ).toBeCloseTo(0.12, 10)
  })

  it('F04 float+unit=% 키는 -3.0 을 그대로 -3.0% 로 보여 준다 (percent 와 혼동 금지)', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'exit')

    const input = (await screen.findByTestId(
      'strategy-params-input-stop-loss-rate',
    )) as HTMLInputElement
    expect(
      Number(input.value),
      'stop_loss_rate 는 값 자체가 퍼센트다 — ×100 하면 -300% 가 된다',
    ).toBeCloseTo(-3, 6)
    expect(
      screen.getByTestId('strategy-params-row-stop-loss-rate'),
    ).toHaveTextContent('%')
  })

  it('F05 unit=원 키는 억 보조 표기로 렌더된다 (키가 아니라 unit 으로 분기)', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'scan_universe')

    // min_market_cap 100,000,000,000원 = 1,000억
    expect(
      screen.getByTestId('strategy-params-current-min-market-cap').textContent ?? '',
    ).toMatch(/1[,]?000\s*억/)
    // min_trade_amount 20,000,000,000원 = 200억 — 같은 unit 이므로 같은 규칙을 탄다.
    expect(
      screen.getByTestId('strategy-params-current-min-trade-amount').textContent ?? '',
    ).toMatch(/200\s*억/)
  })

  it('F06 enum 키는 select + 한글 choices 라벨로 렌더된다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'time_board')

    const select = (await screen.findByTestId(
      'strategy-params-select-exchange',
    )) as HTMLSelectElement
    expect(select.value).toBe('KRX')
    expect(within(select).getByText(/KRX \(한국거래소\)/)).toBeInTheDocument()
    expect(within(select).getByText(/NXT \(넥스트레이드\)/)).toBeInTheDocument()
    expect(within(select).getByText(/SOR \(최선주문집행\)/)).toBeInTheDocument()
  })

  it('F07 bool 키는 체크박스로 렌더된다 (구 24키 화면에서 구조적으로 못 오던 타입)', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'exit')

    const box = (await screen.findByTestId(
      'strategy-params-checkbox-failed-breakout-exit-enabled',
    )) as HTMLInputElement
    expect(box.type).toBe('checkbox')
    expect(box.checked, 'VB 기본값 False').toBe(false)
    expect(box.disabled).toBe(false)
  })

  it('F08 list_str 키는 선택지 체크박스 그룹으로 렌더되고 비활성 선택지도 감춰지지 않는다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'time_board')

    const main = (await screen.findByTestId(
      'strategy-params-choice-tradable-boards-main',
    )) as HTMLInputElement
    expect(main.checked, 'VB 기본값 ["main"]').toBe(true)

    const preNxt = screen.getByTestId(
      'strategy-params-choice-tradable-boards-pre-nxt',
    ) as HTMLInputElement
    expect(preNxt.checked).toBe(false)

    // 사이클 26 에 비활성된 보드도 값 호환 보존 대상이라 목록에서 지우지 않는다 —
    // 대신 선택지 라벨이 "(비활성)" 을 달고 나온다.
    expect(
      screen.getByTestId('strategy-params-row-tradable-boards').textContent ?? '',
    ).toMatch(/KRX 동시호가 \(비활성\)/)
  })
})

describe('cycle278 F09~F12 — 현재값/기본값·diff·정체성 2단계 확인', () => {
  it('F09 현재값과 기본값이 병기되고 다를 때만 되돌리기가 보인다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    // 픽스처: VB k_period 현재 25 / 기본 20
    expect(screen.getByTestId('strategy-params-current-k-period')).toHaveTextContent('25')
    expect(screen.getByTestId('strategy-params-default-k-period')).toHaveTextContent('20')
    expect(screen.getByTestId('strategy-params-reset-k-period')).toBeInTheDocument()

    // k_value_krx_main 은 현재값 = 기본값 → 되돌리기 불필요
    expect(screen.queryByTestId('strategy-params-reset-k-value-krx-main')).toBeNull()
  })

  it('F09b 되돌리기를 누르면 입력이 기본값으로 돌아간다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    await user.click(screen.getByTestId('strategy-params-reset-k-period'))
    const input = screen.getByTestId('strategy-params-input-k-period') as HTMLInputElement
    await waitFor(() => expect(Number(input.value)).toBe(20))
  })

  it('F10 변경 전에는 diff 가 비어 있고 변경 후 그 키만 나타난다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    expect(
      screen.queryAllByTestId(/^strategy-params-diff-row-/),
      '아무것도 안 고쳤는데 diff 가 있으면 운영자가 자기 변경을 못 가려낸다',
    ).toHaveLength(0)

    await setInput(user, 'k_period', '30')

    await waitFor(() =>
      expect(screen.queryAllByTestId(/^strategy-params-diff-row-/)).toHaveLength(1),
    )
    const row = screen.getByTestId('strategy-params-diff-row-k-period')
    expect(row).toHaveTextContent('25')
    expect(row).toHaveTextContent('30')
  })

  it('F11 identity 키를 바꾸면 확인 체크박스가 나타나고 켜기 전에는 저장이 막힌다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'sizing_risk')

    await setInput(user, 'max_positions', '8')

    const ack = (await screen.findByTestId(
      'strategy-params-identity-ack',
    )) as HTMLInputElement
    expect(ack.checked).toBe(false)
    expect(
      screen.getByTestId('strategy-params-save'),
      '리스크 정체성 상수가 클릭 한 번에 바뀌면 안 된다',
    ).toBeDisabled()

    await user.click(ack)
    await waitFor(() => expect(screen.getByTestId('strategy-params-save')).toBeEnabled())
  })

  it('F12 identity 아닌 키만 바꾸면 확인 체크박스가 없고 저장이 바로 가능하다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    await setInput(user, 'k_period', '30')

    await waitFor(() => expect(screen.getByTestId('strategy-params-save')).toBeEnabled())
    expect(screen.queryByTestId('strategy-params-identity-ack')).toBeNull()
  })

  it('F11b identity 키에는 정체성 배지가, 일반 키에는 붙지 않는다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'sizing_risk')

    expect(
      screen.getByTestId('strategy-params-badge-identity-max-positions'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('strategy-params-badge-identity-k-period')).toBeNull()
    // auto_tunable 배지는 PARAM_RANGES 반영 — k_period=true / max_positions=false
    await openGroup(user, 'entry')
    expect(
      screen.getByTestId('strategy-params-badge-autotune-k-period'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('strategy-params-badge-autotune-max-positions')).toBeNull()
  })
})

describe('cycle278 F13~F15 — 숨기지 않고 사실대로 보여 준다', () => {
  it('F13 deprecated 키는 숨기지 않고 "미사용" 배지 + 입력 비활성으로 렌더된다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    const legacyBody = await openGroup(user, 'legacy')

    expect(
      within(legacyBody).getByTestId('strategy-params-row-quant-filter-enabled'),
      '숨기면 그 키가 왜 없는지 아무도 모른다',
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('strategy-params-badge-deprecated-quant-filter-enabled'),
    ).toBeInTheDocument()
    const box = screen.getByTestId(
      'strategy-params-checkbox-quant-filter-enabled',
    ) as HTMLInputElement
    expect(box.disabled, '값이 매매를 안 바꾸는 입력란은 운영자를 속인다').toBe(true)
  })

  it('F14 VB 의 k_value_nxt_pre 는 "이 전략에선 무효" 배지를 단다', async () => {
    const { user } = renderEditor({ strategyId: VB })
    await waitEditor()
    await openGroup(user, 'entry')

    expect(
      screen.getByTestId('strategy-params-badge-inactive-k-value-nxt-pre'),
    ).toBeInTheDocument()
  })

  it('F14b LTV 의 같은 키에는 무효 배지가 없다 (전역 deprecated 로 승격 금지)', async () => {
    const { user } = renderEditor({ strategyId: LTV })
    await waitEditor()
    await openGroup(user, 'entry')

    expect(screen.getByTestId('strategy-params-row-k-value-nxt-pre')).toBeInTheDocument()
    expect(
      screen.queryByTestId('strategy-params-badge-inactive-k-value-nxt-pre'),
      'LTV 는 야간 목표가에 이 K값을 실제로 곱한다 — 무효 배지는 거짓말이다',
    ).toBeNull()
  })

  it('F15 range_src=none 키는 "범위 근거 없음" 배지를 단다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'scan_universe')

    expect(
      screen.getByTestId('strategy-params-badge-unbounded-max-scan-stocks'),
    ).toBeInTheDocument()
    // 범위 근거가 없다고 편집을 막지는 않는다(AI 는 바꿀 수 있는 키다 — 명세 D5).
    expect(screen.getByTestId('strategy-params-input-max-scan-stocks')).toBeEnabled()
  })
})

describe('cycle278 F16~F20 — 저장·오류·경고', () => {
  it('F16 422 detail 의 각 원소가 key 로 그 행에 붙는다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    capturePut(() =>
      HttpResponse.json(
        {
          detail: [
            {
              key: 'k_period',
              code: 'out_of_range',
              msg: '변동성 산출 기간은 5 ~ 60 이어야 합니다 — 받은 값 999',
              strategy_id: VB,
              given: 999,
              expected: { min: 5, max: 60, type: 'int', range_src: 'param_ranges' },
            },
          ],
        },
        { status: 422 },
      ),
    )

    await setInput(user, 'k_period', '999')
    await user.click(screen.getByTestId('strategy-params-save'))
    await user.click(await screen.findByRole('button', { name: '확인' }))

    const err = await screen.findByTestId('strategy-params-error-k-period')
    expect(err).toHaveTextContent('5 ~ 60')
  })

  it('F17 key 가 null 인 422(불변식)는 폼 레벨에 표시된다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'sizing_risk')

    capturePut(() =>
      HttpResponse.json(
        {
          detail: [
            {
              key: null,
              code: 'budget_invariant',
              msg: '종목당 비중 × 동시 보유 종목수 = 0.3 × 10 = 3.00 으로 1.0 을 넘습니다',
              strategy_id: VB,
              given: { position_ratio: 0.3, max_positions: 10, product: 3.0 },
              expected: { max_product: 1.0 },
            },
          ],
        },
        { status: 422 },
      ),
    )

    await setInput(user, 'position_ratio', '30')
    await user.click(screen.getByTestId('strategy-params-save'))
    await user.click(await screen.findByRole('button', { name: '확인' }))

    const formError = await screen.findByTestId('strategy-params-form-error')
    expect(formError).toHaveTextContent('1.0 을 넘습니다')
  })

  it('F18 422 를 받아도 패널이 닫히지 않고 onClose 도 불리지 않는다', async () => {
    const { user, onClose } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    capturePut(() =>
      HttpResponse.json(
        {
          detail: [
            { key: 'k_period', code: 'out_of_range', msg: '범위를 벗어났습니다', strategy_id: VB },
          ],
        },
        { status: 422 },
      ),
    )

    await setInput(user, 'k_period', '999')
    await user.click(screen.getByTestId('strategy-params-save'))
    await user.click(await screen.findByRole('button', { name: '확인' }))

    await screen.findByTestId('strategy-params-error-k-period')
    expect(screen.getByTestId('strategy-params-editor')).toBeInTheDocument()
    expect(onClose, '오류를 띄운 채 패널을 닫으면 고칠 화면이 사라진다').not.toHaveBeenCalled()
  })

  it('F19 200+warnings 는 성공으로 처리하되 경고 목록을 보여 준다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'scan_universe')

    capturePut(() =>
      okResponse(
        { max_scan_stocks: 300 },
        [
          {
            key: 'max_scan_stocks',
            code: 'range_unbounded',
            msg: '최대 스캔 종목수는 범위 근거가 없어 자료형만 검사했습니다',
            strategy_id: VB,
          },
        ],
      ),
    )

    await setInput(user, 'max_scan_stocks', '300')
    await user.click(screen.getByTestId('strategy-params-save'))
    await user.click(await screen.findByRole('button', { name: '확인' }))

    const warnings = await screen.findByTestId('strategy-params-warnings')
    expect(warnings).toBeInTheDocument()
    expect(
      screen.getByTestId('strategy-params-warning-range_unbounded'),
    ).toHaveTextContent('범위 근거가 없어')
    expect(screen.queryByTestId('strategy-params-form-error')).toBeNull()
  })

  it('F20 저장은 ConfirmModal 을 거치고 취소하면 PUT 이 나가지 않는다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    const seen = capturePut(() => okResponse({ k_period: 30 }))
    await setInput(user, 'k_period', '30')
    await user.click(screen.getByTestId('strategy-params-save'))

    // 공용 ConfirmModal (message: string 단일 props — 확장 금지)
    const confirm = await screen.findByRole('button', { name: '확인' })
    expect(confirm).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '취소' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: '확인' })).toBeNull())
    expect(seen.count, '확인 없이 매매 파라미터가 바뀌면 안 된다').toBe(0)
  })

  it('F20b 저장 성공 시 변경분만 PUT 되고 패널이 닫힌다', async () => {
    const { user, onClose } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    const seen = capturePut(() => okResponse({ k_period: 30 }))
    await setInput(user, 'k_period', '30')
    await user.click(screen.getByTestId('strategy-params-save'))
    await user.click(await screen.findByRole('button', { name: '확인' }))

    await waitFor(() => expect(seen.count).toBe(1))
    expect(
      Object.keys(seen.body?.params ?? {}),
      '전 키를 매번 보내면 한 키의 범위 위반이 전략 전체 저장을 막는다(HAZARD-2)',
    ).toEqual(['k_period'])
    expect(seen.body?.params?.k_period).toBe(30)
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('F20c 취소 버튼은 저장 없이 onClose 를 부른다', async () => {
    const { user, onClose } = renderEditor()
    await waitEditor()

    const seen = capturePut(() => okResponse({}))
    await user.click(screen.getByTestId('strategy-params-cancel'))

    expect(seen.count).toBe(0)
    expect(onClose).toHaveBeenCalled()
  })
})

describe('cycle278 F23~F24 — 장중 경고 배너는 KST 로만 판정한다', () => {
  it('F23 KST 10:00 이면 "즉시 반영" 경고 배너가 보인다', async () => {
    renderEditor({ now: MAIN_HOURS })
    await waitEditor()

    const banner = screen.getByTestId('strategy-params-market-warning')
    expect(banner).toHaveTextContent(/즉시 반영/)
  })

  it('F24 KST 20:30 이면 경고 배너가 없다', async () => {
    renderEditor({ now: OFF_HOURS })
    await waitEditor()

    expect(screen.queryByTestId('strategy-params-market-warning')).toBeNull()
  })
})

describe('cycle278 — 스키마 응답이 현재값의 정본이다', () => {
  it('스키마의 현재값이 바뀌면 화면 입력값도 그 값으로 렌더된다 (별도 쿼리와 섞지 않는다)', async () => {
    server.use(
      http.get('/api/strategies/params-schema', () =>
        HttpResponse.json(wrap(schemaWithCurrent(VB, { k_period: 41 }))),
      ),
    )
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'entry')

    const input = screen.getByTestId('strategy-params-input-k-period') as HTMLInputElement
    expect(Number(input.value)).toBe(41)
    expect(screen.getByTestId('strategy-params-default-k-period')).toHaveTextContent('20')
  })
})

describe('cycle278 후속 시정 1 — 빈 매매 보드는 저장할 수 없다', () => {
  it('마지막 보드를 끄면 저장이 잠기고 대안 조작(전략 비활성화)을 안내한다', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'time_board')

    // VB 기본값은 ["main"] 뿐이므로 이 한 번의 클릭이 목록을 비운다.
    const main = screen.getByTestId(
      'strategy-params-choice-tradable-boards-main',
    ) as HTMLInputElement
    expect(main.checked).toBe(true)
    await user.click(main)

    const block = await screen.findByTestId('strategy-params-local-block')
    expect(block).toHaveTextContent(/최소 1개/)
    expect(block, '대안 조작을 가리켜야 한다').toHaveTextContent(/비활성화/)

    // ⚠️ 매매 허용 보드는 identity 키다 — 2단계 확인을 **먼저 켜서** 그 게이트를 걷어내야
    // 저장 잠금이 빈 목록 때문임을 잰다(안 켜면 identity 게이트가 결과를 가린다).
    await user.click(screen.getByTestId('strategy-params-identity-ack'))
    expect(
      (screen.getByTestId('strategy-params-save') as HTMLButtonElement).disabled,
      '2단계 확인을 켠 뒤에도 빈 목록이면 저장은 잠겨 있어야 한다',
    ).toBe(true)
  })

  it('빈 목록이면 저장 요청 자체가 나가지 않는다 (서버 422 가 정본이지만 왕복을 아낀다)', async () => {
    const seen = capturePut(() => okResponse({}))
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'time_board')

    await user.click(screen.getByTestId('strategy-params-choice-tradable-boards-main'))
    await screen.findByTestId('strategy-params-local-block')
    // identity 2단계 확인까지 켠 상태 = 빈 목록 외의 게이트가 모두 열린 상태.
    await user.click(screen.getByTestId('strategy-params-identity-ack'))
    await user.click(screen.getByTestId('strategy-params-save'))

    expect(screen.queryByRole('button', { name: '확인' }), '확인 모달도 뜨지 않는다').toBeNull()
    expect(seen.count).toBe(0)
  })

  it('보드를 다시 켜면 잠금이 풀린다 (되돌릴 수 없는 잠금이 아니다)', async () => {
    const { user } = renderEditor()
    await waitEditor()
    await openGroup(user, 'time_board')

    const main = screen.getByTestId('strategy-params-choice-tradable-boards-main')
    await user.click(main)
    await screen.findByTestId('strategy-params-local-block')

    await user.click(main)
    await waitFor(() =>
      expect(screen.queryByTestId('strategy-params-local-block')).toBeNull(),
    )
  })
})

describe('cycle278 후속 시정 2 — 변동성 돌파에 NXT 애프터마켓은 선택할 수 없다', () => {
  it('금지 선택지는 비활성으로 렌더되고 사유가 툴팁에 붙는다', async () => {
    const { user } = renderEditor({ strategyId: VB })
    await waitEditor()
    await openGroup(user, 'time_board')

    const postNxt = (await screen.findByTestId(
      'strategy-params-choice-tradable-boards-post-nxt',
    )) as HTMLInputElement
    expect(postNxt.disabled, 'VB + post_nxt 는 체크할 수 없어야 한다').toBe(true)

    // 사유는 근거(루트 CLAUDE.md 의 VB 조항)를 담은 스키마 응답 문장이다.
    const label = postNxt.closest('label')
    expect(label?.getAttribute('title') ?? '').toMatch(/POST_NXT 추가 금지/)
    expect(
      screen.getByTestId('strategy-params-row-tradable-boards').textContent ?? '',
    ).toMatch(/이 전략에서 금지/)
  })

  it('롱테일 변동성에서는 같은 선택지가 정상 활성이다 (금지는 전략별이다)', async () => {
    const { user } = renderEditor({ strategyId: LTV })
    await waitEditor()
    await openGroup(user, 'time_board')

    const postNxt = (await screen.findByTestId(
      'strategy-params-choice-tradable-boards-post-nxt',
    )) as HTMLInputElement
    expect(postNxt.disabled).toBe(false)
    expect(postNxt.checked, 'LTV 기본값에 post_nxt 가 있다').toBe(true)
  })

  it('현재값이 이미 금지 조합이면 끌 수는 있다 (복구 경로 보존)', async () => {
    server.use(
      http.get('/api/strategies/params-schema', () =>
        HttpResponse.json(
          wrap(schemaWithCurrent(VB, { tradable_boards: ['main', 'post_nxt'] })),
        ),
      ),
    )
    const seen = capturePut(() => okResponse({ tradable_boards: ['main'] }))
    const { user } = renderEditor({ strategyId: VB })
    await waitEditor()
    await openGroup(user, 'time_board')

    const postNxt = screen.getByTestId(
      'strategy-params-choice-tradable-boards-post-nxt',
    ) as HTMLInputElement
    expect(postNxt.checked).toBe(true)
    expect(postNxt.disabled, '켜진 위반은 끌 수 있어야 한다').toBe(false)

    await user.click(postNxt)
    await user.click(screen.getByTestId('strategy-params-identity-ack'))
    await user.click(screen.getByTestId('strategy-params-save'))
    await user.click(await screen.findByRole('button', { name: '확인' }))

    await waitFor(() => expect(seen.count).toBe(1))
    expect(seen.body?.params).toEqual({ tradable_boards: ['main'] })
  })
})

describe('cycle278 후속 시정 2 — localBlocks 의 금지 선택지 갈래 (UI 로 닫힌 두 번째 선)', () => {
  it('금지 값이 변경분에 들어오면 사유를 담은 차단 항목을 낸다', () => {
    const spec = fixtureSpec('tradable_boards') as unknown as ParamSpec
    expect(
      spec.forbidden_choices.some((f) => f.strategy_id === VB),
      '픽스처에 금지 조합이 없으면 이 테스트는 공허하다',
    ).toBe(true)

    const rows = [{ spec, before: ['main'], after: ['main', 'post_nxt'] }]
    const blocks = localBlocks(rows, VB)

    expect(blocks).toHaveLength(1)
    expect(blocks[0].key).toBe('tradable_boards')
    expect(blocks[0].msg).toMatch(/선택할 수 없습니다/)
    expect(blocks[0].msg, '근거(루트 CLAUDE.md VB 조항)를 담아야 한다').toMatch(
      /POST_NXT 추가 금지/,
    )
  })

  it('같은 값이라도 다른 전략이면 차단하지 않는다', () => {
    const spec = fixtureSpec('tradable_boards') as unknown as ParamSpec
    const rows = [{ spec, before: ['main'], after: ['main', 'post_nxt'] }]

    expect(localBlocks(rows, LTV)).toEqual([])
  })

  it('최소 항목 수 갈래는 금지 갈래와 독립으로 동작한다', () => {
    const spec = fixtureSpec('tradable_boards') as unknown as ParamSpec
    const rows = [{ spec, before: ['main'], after: [] }]
    const blocks = localBlocks(rows, LTV)

    expect(blocks).toHaveLength(1)
    expect(blocks[0].msg).toMatch(/최소 1개/)
  })
})
