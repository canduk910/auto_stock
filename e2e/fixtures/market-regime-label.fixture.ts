/**
 * cycle410 — Playwright 용 `GET /api/market-regime-label` 응답 `data` 실측 픽스처.
 *
 * `frontend/src/test/fixtures/marketRegimeLabel.fixture.ts` 와 같은 내용이다
 * (e2e 는 frontend tsconfig 밖이라 교차 import 대신 같은 내용을 각자 보유한다).
 * 출처 = `src/routes/market_regime_label.py` 를 실제로 태운 응답(오늘 = 2026-10-05, modes = 코드 기본값).
 */
export const MARKET_REGIME_LABEL_FIXTURE = {
  "today": {
    "date": "2026-10-05",
    "label": "volatile_down",
    "direction": "down",
    "volatility": "volatile",
    "slope_pct": -7.542634244722701,
    "vol_pct": 32.245990745872064,
    "basis_date": "2026-10-02"
  },
  "history": [
    {
      "date": "2026-07-08",
      "label": "volatile_up",
      "m": 1.0
    },
    {
      "date": "2026-07-09",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-10",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-13",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-14",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-15",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-16",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-20",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-21",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-22",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-23",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-24",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-27",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-28",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-29",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-30",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-07-31",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-08-03",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-08-04",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-08-05",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-08-06",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-08-07",
      "label": "volatile_up",
      "m": 0.5
    },
    {
      "date": "2026-08-10",
      "label": "volatile_flat",
      "m": 0.5
    },
    {
      "date": "2026-08-11",
      "label": "volatile_flat",
      "m": 0.5
    },
    {
      "date": "2026-08-12",
      "label": "volatile_flat",
      "m": 0.0
    },
    {
      "date": "2026-08-13",
      "label": "volatile_flat",
      "m": 0.0
    },
    {
      "date": "2026-08-14",
      "label": "volatile_flat",
      "m": 0.0
    },
    {
      "date": "2026-08-18",
      "label": "volatile_flat",
      "m": 0.0
    },
    {
      "date": "2026-08-19",
      "label": "volatile_flat",
      "m": 0.0
    },
    {
      "date": "2026-08-20",
      "label": "volatile_flat",
      "m": 0.0
    },
    {
      "date": "2026-08-21",
      "label": "volatile_flat",
      "m": 0.0
    },
    {
      "date": "2026-08-24",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-08-25",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-08-26",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-08-27",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-08-28",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-08-31",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-01",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-02",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-03",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-04",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-07",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-08",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-09",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-10",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-11",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-14",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-15",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-16",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-17",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-18",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-21",
      "label": "volatile_down",
      "m": 0.0
    },
    {
      "date": "2026-09-22",
      "label": "volatile_down",
      "m": 0.75
    },
    {
      "date": "2026-09-23",
      "label": "volatile_down",
      "m": 0.75
    },
    {
      "date": "2026-09-28",
      "label": "volatile_down",
      "m": 0.75
    },
    {
      "date": "2026-09-29",
      "label": "volatile_down",
      "m": 0.75
    },
    {
      "date": "2026-09-30",
      "label": "volatile_down",
      "m": 0.75
    },
    {
      "date": "2026-10-01",
      "label": "volatile_down",
      "m": 0.75
    },
    {
      "date": "2026-10-02",
      "label": "volatile_down",
      "m": 0.75
    },
    {
      "date": "2026-10-05",
      "label": "volatile_down",
      "m": 0.75
    }
  ],
  "market_unit": {
    "m": 0.75,
    "state": "up_falling",
    "above_sma60": true,
    "sma60_rising": false,
    "close": 112060.0,
    "sma60": 107287.865,
    "basis_date": "2026-10-02",
    "source": "db_recompute",
    "modes": {
      "donchian_swing": "shadow",
      "bull_flag_breakout": "shadow",
      "vcp_breakout": "shadow",
      "kojiro": "shadow",
      "etf_trend": "shadow"
    }
  },
  "since": "2026-08-24",
  "since_truncated": false,
  "warmup_from": "2025-02-13",
  "thresholds": {
    "ma_window": 60,
    "slope_lookback": 20,
    "vol_window": 20,
    "dir_enter_pct": 3.0,
    "dir_exit_pct": 1.0,
    "vol_high_pct": 20.0,
    "vol_low_pct": 16.0
  }
}
