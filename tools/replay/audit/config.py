"""동결본 §0·§1 의 고정값. 바꾸지 않는다(바꾸면 「사후 발견」 절에 적고 두 판을 함께 낸다)."""
from __future__ import annotations

import os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MAIN_REPO = "/Users/koscom/Projects/auto_stock"          # 보관소(git 밖)는 본 작업 트리에만 있다
STOCK_ARCHIVE = os.path.join(MAIN_REPO, "data/archive/krx_daily/parquet")
ETF_ARCHIVE = os.path.join(MAIN_REPO, "data/archive/krx_etf_daily/parquet")
SCRATCH = ("/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
           "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/audit")
DB_EXTRACT = os.path.join(SCRATCH, "audit_db_extract.jsonl.gz")

# C7 — 전략마다 예산 풀 단독(순자산 4,955,600 × cash_usage_ratio 0.95)
NET_ASSET_20261002 = 4_955_600
CASH_USAGE_RATIO = 0.95
BUDGET_C7 = 4_707_820
assert BUDGET_C7 == int(NET_ASSET_20261002 * CASH_USAGE_RATIO)

# C1 — 비용(왕복). 판정 0.38% · 민감도 0.28% / 0.48%
COST_RT_JUDGE = 0.0038
COST_RT_SENS = (0.0028, 0.0048)

# C2 — 창
W5Y = ("2020-10-05", "2025-10-02")
W4 = ("2021-10-01", "2025-10-02")
H1Y = ("2025-10-10", "2026-10-02")

# D-9 — 씨앗
BOOT_SEED = 20261005
N_BOOT = 2000
BOOK_SEEDS = tuple(range(16))          # cycle377·405 와 같은 방식(default_rng(0..15))
BOOT_Q = 0.05                          # 「90% 하한」 = 양측 90% 구간의 아래 끝(평균회귀 T1 과 같음)

# D-4 — 실거래 판정 창 시작(첫 주 분모 비정상)
LIVE_START = "2026-04-29"

# §1.3 문턱
P1_LO = -0.002
P3_MDD = -0.35
P4_FILLS_PER_YEAR = 12
P4_UNAFF = 0.50
P6_MATCH = 0.70
P6_MIN_N = 10
P2_MIN_N = 15
L1_MIN_N = 30
L1_LO = -0.010

# 보관소 sha256 — 평균회귀 2차 동결본 §4(주식) · cycle391 메모 §2(ETF)
STOCK_PARQUET_SHA = {
    "krx_daily_2020.parquet": "1704c488510c45f016c014de443653d19ca6472c697e124239778890c90f40c7",
    "krx_daily_2021.parquet": "818fd65e2b67826860cc81e3164d066c29a6883c1566d1b87a4005ba1d2e526a",
    "krx_daily_2022.parquet": "0aa74a99d879ed1eb84b2b988f97f55aa56e9b87ad4a963fa890a167b2606cf9",
    "krx_daily_2023.parquet": "a6f9e1e5d7b2d5f7a0fb9ec3ee9eb8c87c40af44717a6712fdb01d08ffdb5a1c",
    "krx_daily_2024.parquet": "3187dbd6e7923902b10e8f0976beec29cf2cb5778d5d9828366f6ba269ee41a5",
    "krx_daily_2025.parquet": "30d81fee01a71ae9c17e45c11a8544a222d724ac0406b6451d6cb5cff969256a",
}
ETF_PARQUET_SHA = {
    "krx_daily_2020.parquet": "f1cef1bac73a38d7f560738843c6fcae1dfd1419deebec6f474972d1751aa8f1",
    "krx_daily_2021.parquet": "24d99069f19a04bace14247061e1e5b104f4d1dcc29f50129523a259a4ac3e47",
    "krx_daily_2022.parquet": "3aa09da7d32e088e036f4021bbacd8ef4778088d8e1ee676d760715a11665129",
    "krx_daily_2023.parquet": "106e688545897541683087278214222ce3c4d28605afdd8eb97fa6442de5b212",
    "krx_daily_2024.parquet": "0002009e149f25acf6ab4204521c5d85fbf3178ebd768986c53021b40a94dcdc",
    "krx_daily_2025.parquet": "ec20d217f27ac78ae851d40ac843d30142c1ef53f13e907ed2614198fca70ee6",
    "krx_daily_2026.parquet": "ffb019421722b4ccfe3ed4a53d061436be626e1ead58db06c0bca83213534a58",
}
