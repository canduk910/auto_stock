// 파라미터 표시 라벨 (Settings, Recommendations 공용)
export const PARAM_LABELS: Record<string, { label: string; unit: string; step: number }> = {
  buy_threshold: { label: '매수 기준 등락률', unit: '%', step: 0.5 },
  stop_loss_rate: { label: '손절 기준', unit: '%', step: 0.5 },
  gap_up_threshold: { label: '갭상승 기준', unit: '%', step: 1 },
  trailing_stop_rate: { label: '트레일링 스탑', unit: '%', step: 0.5 },
  position_ratio: { label: '전략 내 종목당 비중', unit: '', step: 0.01 },
  max_positions: { label: '최대 보유 종목 수', unit: '개', step: 1 },
  daily_loss_limit: { label: '일일 최대 손실', unit: '%', step: 0.5 },
  k_period: { label: 'K값 산출 기간', unit: '일', step: 1 },
  min_market_cap: { label: '최소 시가총액', unit: '원', step: 10_000_000_000 },
  min_trade_amount: { label: '최소 거래대금', unit: '원', step: 10_000_000_000 },
  max_scan_stocks: { label: '최대 스캔 종목 수', unit: '개', step: 10 },
  min_prdy_rate: { label: '최소 전일대비 등락률', unit: '%', step: 0.5 },
  exclude_consecutive_limit: { label: '연속상한가 제외 기준', unit: '일', step: 1 },
  limit_up_threshold: { label: '상한가 모드 전환 기준', unit: '%', step: 0.5 },
  intraday_stop_loss: { label: '당일 손절 기준', unit: '%', step: 0.5 },
  overnight_stop_loss: { label: '익일 손절 기준', unit: '%', step: 0.5 },
}

export const formatParamValue = (key: string, value: number): string => {
  if (key === 'position_ratio') return `${(value * 100).toFixed(0)}%`
  if (key === 'min_market_cap' || key === 'min_trade_amount') return `${(value / 1e8).toLocaleString()}억`
  return `${value}`
}
