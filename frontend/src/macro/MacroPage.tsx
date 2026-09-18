import { useEffect } from "react"
import { useCommodities, useCreditSpread, useCurrencies, useMacroCycle, useSp500, useYieldCurve } from "./hooks/useMacro"
import MacroCycleSection from "./components/MacroCycleSection"
import YieldCurveSection from "./components/YieldCurveSection"
import CreditSpreadSection from "./components/CreditSpreadSection"
import CurrencySection from "./components/CurrencySection"
import CommoditySection from "./components/CommoditySection"

// 원본 `macro_lite/MacroLitePage.jsx` 이식 — 5개 섹션 순서(경기사이클 → 금리차 → 하이일드 →
// 환율 → 원자재)는 원본과 동일하게 보존한다.
export default function MacroPage() {
  const cycle = useMacroCycle()
  const yieldCurve = useYieldCurve()
  const creditSpread = useCreditSpread()
  const currencies = useCurrencies()
  const commodities = useCommodities()
  // cycle310 — 금리차·하이일드 두 차트가 함께 쓰는 붉은 선. 한 번만 받아 둘에 넘긴다.
  const sp500 = useSp500()

  useEffect(() => {
    cycle.load()
    yieldCurve.load()
    creditSpread.load()
    currencies.load()
    commodities.load()
    sp500.load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-gray-900">매크로 분석</h1>
      <MacroCycleSection data={cycle.data} loading={cycle.loading} error={cycle.error} />
      <YieldCurveSection
        data={yieldCurve.data}
        loading={yieldCurve.loading}
        error={yieldCurve.error}
        sp500={sp500.data?.sp500?.history}
      />
      <CreditSpreadSection
        data={creditSpread.data}
        loading={creditSpread.loading}
        error={creditSpread.error}
        sp500={sp500.data?.sp500?.history}
      />
      <CurrencySection data={currencies.data} loading={currencies.loading} error={currencies.error} />
      <CommoditySection data={commodities.data} loading={commodities.loading} error={commodities.error} />
    </div>
  )
}
