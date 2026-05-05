// 파라미터 표시 라벨 + 비유 기반 설명 (Settings, Recommendations 공용)
export const PARAM_LABELS: Record<
  string,
  { label: string; unit: string; step: number; description: string }
> = {
  buy_threshold: {
    label: '매수 기준 등락률',
    unit: '%',
    step: 0.5,
    description:
      '🎯 이만큼 올랐을 때 매수 신호가 나옵니다.\n\n예: +29% = 상한가(+30%) 직전. "거의 끝까지 달린 종목만 잡겠다"는 의미.',
  },
  stop_loss_rate: {
    label: '손절 기준',
    unit: '%',
    step: 0.5,
    description:
      '🛑 매수가 대비 이만큼 빠지면 무조건 손절.\n\n예: -7.5% = 1만원에 산 걸 9,250원에 잘라냄. 손실 더 커지기 전에 칼같이 정리.',
  },
  gap_up_threshold: {
    label: '갭상승 기준',
    unit: '%',
    step: 1,
    description:
      '🌅 다음 날 시가가 매수가 대비 이만큼 더 떴는지 판정.\n\n예: +10% 이상이면 "좋은 출발"로 보고 트레일링 보유, 미만이면 그냥 즉시 정리.',
  },
  trailing_stop_rate: {
    label: '트레일링 스탑',
    unit: '%',
    step: 0.5,
    description:
      '📉 오늘 고점에서 이만큼 빠지면 매도.\n\n예: -2% = 오늘 1만원 찍었으면 9,800원에 매도. 이익을 지키면서 추세 끝까지 따라가는 안전장치.',
  },
  position_ratio: {
    label: '전략 내 종목당 비중',
    unit: '',
    step: 0.01,
    description:
      '🍰 전략 할당금 중 한 종목에 쓸 비율.\n\n예: 0.15 = 100만원 중 15만원씩 → 약 6~7종목에 분산. 전체 자산이 아니라 "이 전략에 배정된 돈" 기준임에 주의.',
  },
  max_positions: {
    label: '최대 보유 종목 수',
    unit: '개',
    step: 1,
    description:
      '📦 동시에 들고 있을 종목 수의 상한.\n\n너무 많으면 한 번에 살피기 어렵고, 너무 적으면 분산이 안 됩니다.',
  },
  daily_loss_limit: {
    label: '일일 최대 손실',
    unit: '%',
    step: 0.5,
    description:
      '🚨 오늘 누적 손실이 이 선에 닿으면 신규 매수 중단.\n\n예: -5% = 오늘 5% 깎이면 더 사지 않고 잠금. 손실이 폭주하는 날을 막는 비상 브레이크.',
  },
  k_period: {
    label: 'K값 산출 기간',
    unit: '일',
    step: 1,
    description:
      '📐 K값(변동성 계수)을 만들 때 쓰는 일봉 기간.\n\n예: 20 = 최근 20일치 변동폭 평균. 길수록 안정적이지만 최근 흐름 반영이 늦음.',
  },
  min_market_cap: {
    label: '최소 시가총액',
    unit: '원',
    step: 10_000_000_000,
    description:
      '🏢 이 시총 미만 회사는 후보 제외.\n\n예: 1,000억 = 너무 작은 회사는 변동성이 거칠고 작전 위험이 있어 제외.',
  },
  min_trade_amount: {
    label: '최소 거래대금',
    unit: '원',
    step: 10_000_000_000,
    description:
      '💧 이 거래대금 미만 종목 제외.\n\n예: 200억 = 거래량이 적으면 "사고 싶을 때 못 사고, 팔고 싶을 때 못 파는" 유동성 위험이 있어 제외.',
  },
  max_scan_stocks: {
    label: '최대 스캔 종목 수',
    unit: '개',
    step: 10,
    description:
      '🔍 한 번에 검토할 종목 수 상한.\n\n너무 많으면 KIS API Rate Limit에 걸리거나 처리가 느려질 수 있어요.',
  },
  min_prdy_rate: {
    label: '최소 전일대비 등락률',
    unit: '%',
    step: 0.5,
    description:
      '⚡ 전일 대비 이만큼 못 오른 종목은 매수 신호 무시.\n\n예: 5% = "오늘 5% 이상 강세인 종목만 진입 후보로 인정". 미지근한 종목 제외 필터.',
  },
  exclude_consecutive_limit: {
    label: '연속상한가 제외 기준',
    unit: '일',
    step: 1,
    description:
      '🚫 최근 N일 연속 상한가였던 종목 제외.\n\n예: 2 = 이미 2일 연속 상한가면 추격 매수 금지. 막차 타다 고점에 물리는 위험 회피.',
  },
  limit_up_threshold: {
    label: '상한가 모드 전환 기준',
    unit: '%',
    step: 0.5,
    description:
      '🎪 오늘 이만큼 오르면 "상한가 모드"로 전환.\n\n예: 29% = 상한가 직전 도달 시 다음 날까지 보유 검토. 짧게 끝내지 않고 긴 꼬리(롱테일)를 노림.',
  },
  intraday_stop_loss: {
    label: '당일 손절 기준',
    unit: '%',
    step: 0.5,
    description:
      '🛑 당일 청산 모드(상한가 미도달 종목) 손절선.\n\n예: -3% = 매수가 대비 3% 빠지면 즉시 정리. 짧게 보유하므로 손절폭도 타이트하게.',
  },
  overnight_stop_loss: {
    label: '익일 손절 기준',
    unit: '%',
    step: 0.5,
    description:
      '🛑 익일까지 들고 가는 종목의 손절선.\n\n예: -5% = 당일 손절(-3%)보다 약간 여유 있게. 밤사이 변동을 견디기 위한 폭.',
  },
  donchian_period: {
    label: '신고가 기준 기간',
    unit: '일',
    step: 1,
    description:
      '📈 최근 며칠치 일봉 중 최고가를 신고가로 볼지.\n\n예: 20 = 최근 20일 최고가 돌파. 길수록 보수적, 짧을수록 진입 잦음.',
  },
  long_ma_period: {
    label: '장기 추세 EMA 기간',
    unit: '일',
    step: 1,
    description:
      '🌊 추세 방향 판정에 쓰는 EMA 기간.\n\n예: 60 = 60일 EMA 위에 있고 우상향이어야 진입. 약세장 진입 차단용.',
  },
  atr_period: {
    label: 'ATR 산출 기간',
    unit: '일',
    step: 1,
    description:
      '📏 변동폭(ATR) 계산에 쓰는 일봉 기간.\n\n예: 14 = 최근 14일치 고가-저가 평균. 트레일링 손절 폭 결정.',
  },
  atr_trail_mult: {
    label: 'ATR 트레일링 배수',
    unit: '배',
    step: 0.1,
    description:
      '🎢 고점에서 ATR × 몇 배 빠지면 매도할지.\n\n예: 2.0 = ATR이 1,000원이면 고점 대비 2,000원 빠질 때 매도. 작을수록 빨리 던지고, 클수록 멀리 따라감.',
  },
  gap_skip_threshold: {
    label: '익일 갭 스킵 기준',
    unit: '%',
    step: 0.5,
    description:
      '🚫 다음날 시가가 이만큼 갭상승이면 진입 스킵.\n\n예: 3% = 너무 떠서 시작한 종목은 추격 매수 위험이라 건너뜀.',
  },
  volume_period: {
    label: '거래량 평균 기간',
    unit: '일',
    step: 1,
    description:
      '📊 거래대금 평균 산출 기간.\n\n예: 20 = 최근 20일 평균. 오늘 거래대금이 그 평균의 일정 배수 이상이어야 진입.',
  },
  volume_multiplier: {
    label: '거래대금 증가 배수',
    unit: '배',
    step: 0.1,
    description:
      '🔥 평소 대비 거래대금이 몇 배 이상이면 진입 신호로 볼지.\n\n예: 1.5 = 평소의 1.5배 이상 들어왔을 때만 추세 진입 인정.',
  },
}

export const formatParamValue = (key: string, value: number): string => {
  if (key === 'position_ratio') return `${(value * 100).toFixed(0)}%`
  if (key === 'min_market_cap' || key === 'min_trade_amount') return `${(value / 1e8).toLocaleString()}억`
  return `${value}`
}
