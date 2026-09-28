/**
 * cycle387 — `klinecharts` 가짜 모듈(테스트 전용).
 *
 * jsdom 에는 canvas 가 없어 실제 라이브러리를 돌릴 수 없다(`getContext` 가 null). 그래서
 * `init`·`dispose`·`registerLocale` 만 가짜로 두고, `init` 이 돌려주는 차트는 **어떤 메서드를
 * 불러도 기록만 하는** Proxy 다 — 모달이 `setSymbol`·`setPeriod`·`setDataLoader`·
 * `createIndicator`·`resetData`·`resize` 등을 부른 순서와 인자를 테스트가 읽는다.
 *
 * 쓰는 법(각 테스트 파일 — `vi.mock` 은 파일마다 호이스트된다):
 * ```ts
 * vi.mock('klinecharts', async () => (await import('../../test/fakeKlinecharts')).klinechartsModule)
 * import { fakeKline, resetFakeKline } from '../../test/fakeKlinecharts'
 * beforeEach(() => resetFakeKline())
 * ```
 * 팩토리 안의 동적 import 와 테스트의 정적 import 는 같은 모듈 인스턴스를 본다.
 *
 * ⚠️ `klinecharts` 의 타입을 import 하지 않는다 — 이 헬퍼가 라이브러리 설치 여부와 무관하게
 * 타입 검사를 통과해야 한다.
 */
import { vi } from 'vitest'

type AnyFn = ReturnType<typeof vi.fn>

/** `init` 옵션 중 테스트가 읽는 부분(v10 `Options` 의 부분 모양). */
export interface FakeInitOptions {
  locale?: unknown
  timezone?: unknown
  formatter?: { formatDate?: (params: Record<string, unknown>) => string }
  styles?: {
    candle?: { bar?: Record<string, unknown> }
    indicator?: { bars?: Array<Record<string, unknown>> }
  }
}

export interface FakeChartRecord {
  /** `init` 의 첫 인자(차트를 그릴 요소). */
  el: unknown
  /** `init` 의 둘째 인자(옵션). */
  options: FakeInitOptions | undefined
  /** 모달이 받는 차트 객체(Proxy). */
  chart: Record<string, AnyFn>
  /** 메서드 이름 → 기록 함수. `fn(name)` 으로 읽는다(없으면 만들어 돌려준다). */
  fn: (name: string) => AnyFn
}

function makeFakeChart(): Pick<FakeChartRecord, 'chart' | 'fn'> {
  const fns = new Map<string, AnyFn>()
  const fn = (name: string): AnyFn => {
    let f = fns.get(name)
    if (!f) {
      f = vi.fn()
      fns.set(name, f)
    }
    return f
  }
  const chart = new Proxy({} as Record<string, AnyFn>, {
    get(_target, prop) {
      if (typeof prop !== 'string') return undefined
      // thenable 로 오인되지 않게 — `await chart` 같은 코드가 멈추지 않도록.
      if (prop === 'then' || prop === 'toJSON') return undefined
      return fn(prop)
    },
  })
  return { chart, fn }
}

export const fakeKline = {
  charts: [] as FakeChartRecord[],
  init: vi.fn(),
  dispose: vi.fn(),
  registerLocale: vi.fn(),
}

function installInit(): void {
  fakeKline.init.mockImplementation((el: unknown, options?: FakeInitOptions) => {
    const { chart, fn } = makeFakeChart()
    fakeKline.charts.push({ el, options, chart, fn })
    return chart
  })
}
installInit()

/** 테스트마다 기록을 비운다(`registerLocale` 은 모듈 최상위 1회라 여기서 비우면 다시 안 채워진다 —
 *  필요하면 첫 import 직후에 `fakeKline.registerLocale.mock.calls` 를 복사해 둔다). */
export function resetFakeKline(): void {
  fakeKline.charts.length = 0
  fakeKline.init.mockClear()
  fakeKline.dispose.mockClear()
  installInit()
}

/** 가장 최근에 만든 차트. */
export function lastChart(): FakeChartRecord {
  const rec = fakeKline.charts[fakeKline.charts.length - 1]
  if (!rec) throw new Error('klinecharts.init 이 한 번도 불리지 않았다')
  return rec
}

/** `vi.mock('klinecharts', …)` 팩토리가 돌려줄 모듈 모양. */
export const klinechartsModule = {
  init: fakeKline.init,
  dispose: fakeKline.dispose,
  registerLocale: fakeKline.registerLocale,
}

export interface CollectedBars {
  data: unknown[]
  more: unknown
}

/**
 * 모달이 등록한 **마지막** 데이터 로더의 `getBars` 를 한 번 불러 콜백이 받은 값을 돌려준다.
 * v10 `DataLoaderGetBarsParams` 모양(type·timestamp·symbol·period·callback)으로 부른다.
 */
export async function collectBars(
  rec: FakeChartRecord,
  type: 'init' | 'forward' | 'backward' | 'update',
  period: { type: string; span: number } = { type: 'day', span: 1 },
): Promise<CollectedBars> {
  const calls = rec.fn('setDataLoader').mock.calls
  if (calls.length === 0) throw new Error('setDataLoader 가 불리지 않았다')
  const loader = calls[calls.length - 1][0] as {
    getBars: (p: Record<string, unknown>) => void | Promise<void>
  }
  let got: CollectedBars | null = null
  await loader.getBars({
    type,
    timestamp: null,
    symbol: { ticker: 'TEST', pricePrecision: 0, volumePrecision: 0 },
    period,
    callback: (data: unknown[], more?: unknown) => {
      got = { data, more }
    },
  })
  if (got === null) throw new Error(`getBars(${type}) 가 callback 을 부르지 않았다`)
  return got
}
