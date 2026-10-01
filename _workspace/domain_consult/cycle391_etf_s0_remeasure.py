#!/usr/bin/env python3
"""ETF 추세 전략(etf_trend) S0 재측정 — KRX ETF 5년 보관소(상장폐지 포함)로 사전 등록 문턱 T1~T6 판정.

설계서 = _workspace/design/2026-09-27_etf_trend_strategy.md (§2·§3·§4·§5·§6·§8)
명세 추출 = spec_extract.md (같은 폴더). 문턱 값은 설계서 §8.3 그대로 — 이 스크립트가 바꾸지 않는다.

연구 전용: 운영 DB/KIS/KRX 호출 0(입력 파일만 읽는다). src/ 무접촉. 결과 = results.json · results.md · runs.log(추가 기록).
실행: python3 etf_s0_replay.py  (입력·출력 폴더 = 환경변수 ETF_S0_DIR, 기본 = 세션 스크래치패드 etf_s0/)
입력: data/archive/krx_etf_daily/parquet/krx_daily_{2020..2026}.parquet · raw_2020_2026.jsonl(cycle383 보관소) ·
      $ETF_S0_DIR/input/stock_master_etf_fields.json(운영 DB 읽기 전용 추출 = $ETF_S0_DIR/q_etf_fields_ro.py 출력)

v2 (cycle391 — 감사 지적 반영, 2026-10-02). v1 원본 = v1_orig/ (sha256 d57f0e35…, 판정 = donchian형 채택).
  판정판 규칙 변경은 1건이다(감사 지적 1):
    - 판정판 유니버스 = 「라이브가 닿는 유니버스」 — 종목코드 6자리 숫자만(`live_code`). 운영 적재 경로
      (scanner)가 숫자가 아닌 코드를 건너뛰고 진입 규칙도 「6자리 숫자만」 이라, 라이브 etf_trend 는 영숫자
      코드 ETF 를 보지 못한다. v1 은 DB 미적재 현재 상장 312종(전부 영숫자 코드)을 §8.2 이름 규칙으로
      분류해 넣었다 — §8.2 는 상장폐지 ETF 전용 규칙이다. v1 판정판은 민감도 S0 으로 그대로 보고한다.
  나머지는 판정 정의를 바꾸지 않는 보고 추가다:
    지적 2 — 2안이 검증한 묶음을 결과에 명시 + S8(donchian M12·M13 을 라이브 쪽으로 읽은 판)
    지적 3 — A 구간 실제 시작(가장 이른 신호·첫 진입) 출력 + S5(보관소 시작 전 상장 종목의 100봉 조건 완화)
    지적 4 — runs.log(실행마다 스크립트 sha · 결과 핵심 sha 추가 기록) · T2 두 해석 병기
    지적 5 — 블록 부트스트랩(월 · 보유 겹침 구간) 병기
    지적 6 — 일별 평가손 포함 MDD 병기
    지적 7 — §8.2 일치율을 「표본 안」 으로 표기 + S6(v1 글자 그대로 규칙)
    지적 8 — S7(시총 대신 순자산총액 INVSTASST_NETASST_TOTAMT) — 판정판은 시총 유지(라이브 = hts_avls_eok 시가총액)
    지적 9 — 통합 슬리브(중복 제거와 슬롯을 함께) 병기
    교차계산 차이 해소(reconcile_cross_check.py) — 차이 대부분이 M8(그날 청산된 거래의 묶음 보유) 해석에서 와서
      S9(그날 청산된 다른 종목은 묶음 보유 아님, 같은 종목 당일 재매수만 막음)를 병기
  판정판 해석 M1~M20 은 v1 그대로다. 문턱 T1~T6 은 바꾸지 않았다.
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

T0 = time.time()
# 입력·출력 폴더. 리포 사본(_workspace/domain_consult/cycle391_etf_s0_remeasure.py)을 그 자리에서 돌려도 여기를 쓴다.
HERE = os.environ.get("ETF_S0_DIR", "/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/"
                      "1177b759-a6e8-4448-8205-8c5f1396a3a3/scratchpad/etf_s0")
ARCH = "/Users/koscom/Projects/auto_stock/data/archive/krx_etf_daily"
RAW_JSONL = os.path.join(ARCH, "raw_2020_2026.jsonl")
PARQUETS = sorted(glob.glob(os.path.join(ARCH, "parquet", "krx_daily_*.parquet")))
DB_FIELDS = os.path.join(HERE, "input", "stock_master_etf_fields.json")
DB_QUERY = os.path.join(HERE, "q_etf_fields_ro.py")
RUNS_LOG = os.path.join(HERE, "runs.log")
SCRIPT_VERSION = "v2-cycle391"

SEED = 20261002
N_BOOT = 2000
N_SLEEVE = 40

# ── 사전 등록 문턱 (설계서 §8.3 — 고정, 수정 금지) ──
T1_MIN_R = 0.15
T2_MIN_R = -0.20
T5_MIN_MDD = -20.0
T6_MIN_RATIO = 0.5

# ── 유니버스·사이징 상수 (§2.3 · §5.1) ──
TV20_MIN = 2_000_000_000          # 20억
MCAP_MIN = 50_000_000_000         # 500억
PX_MIN, PX_MAX = 1_000, 500_000
ATR_LO, ATR_HI = 0.01, 0.06
MIN_BARS = 100
QUAL_WIN = 60
CORR_WIN, CORR_MIN_OBS, CORR_TH = 120, 60, 0.9
RISK_PCT, POS_RATIO, SLOTS = 0.01, 0.25, 4
REP_BUDGET = 750_000              # S3 = 순자산 500만 × 0.15 (대표 선택 켠 판·정수 랏 참고)
REP_MIN_LOT = 3
COST_LIQ, COST_ILLIQ = 0.0006, 0.0011   # 왕복: 수수료 0.03% + 슬리피지 0.03%/0.08%
COST_LIQ_TV = 10_000_000_000      # 20일 거래대금 100억

PERIODS = {
    "A": ("2021-01-01", "2022-12-31"),
    "B": ("2023-01-01", "2025-10-02"),
    "H": ("2025-10-10", "2026-09-23"),
}
FULL_START, FULL_END = "2021-01-01", "2026-09-23"


def sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def years_between(a, b):
    return (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25


def live_code(t):
    """라이브가 닿는 종목코드 = 6자리 숫자 (루트 CLAUDE.md 「진입은 6자리 숫자만」 · scanner 적재 경로)."""
    return t.isdigit() and len(t) == 6


# ════════════════════════════════════════════════════════════════════
# 1. 메타 (raw jsonl) — 이름·기초지수명·마지막 상장 목록
# ════════════════════════════════════════════════════════════════════
def load_meta():
    meta = {}
    last_list, last_date = set(), None
    with open(RAW_JSONL, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            d = p["bas_dd"]
            cur = set()
            for r in p["rows"]:
                t = r.get("ISU_CD")
                if not t:
                    continue
                cur.add(t)
                m = meta.setdefault(t, {"name_last": "", "idx_last": ""})
                m["name_last"] = r.get("ISU_NM") or m["name_last"]
                m["idx_last"] = r.get("IDX_IND_NM") or m["idx_last"]
            if cur:
                last_list, last_date = cur, d
    for t, m in meta.items():
        m["listed_at_end"] = t in last_list
    return meta, last_date, len(last_list)


# ════════════════════════════════════════════════════════════════════
# 2. §8.2 상장폐지 ETF 분류 규칙 — v1(설계서 글자 그대로) · v3(일치율 미달로 고친 판)
# ════════════════════════════════════════════════════════════════════
V1_DOM_IDX = re.compile(r"(코스피|코스닥|KOSPI|KOSDAQ|KRX|FnGuide|에프앤가이드|MKF|\bMK\b|WISE|iSelect|KEDI|DeepSearch|KTOP)", re.I)
V1_NAME_EX = re.compile(r"(TR\b|TR$|합성|커버드콜|액티브|레버리지|인버스|선물|채권)")

V3_DOM_IDX = re.compile(r"(코스피|코스닥|KOSPI|KOSDAQ|KRX|FnGuide|에프앤가이드|MKF|\bMK\b|WISE|iSelect|KEDI|DeepSearch|KTOP|Korea|코리아|한국|\bK-)", re.I)
V3_IDX_EX = re.compile(
    r"(미국|(?<!코스닥 )(?<!코스닥)글로벌|차이나|중국|일본|인도|베트남|유럽|선진|신흥|국고채|통안채|국채|채권|머니마켓|MMF|금현물|원유|TRF|혼합|리츠|부동산|총수익|선물|레버리지|인버스|커버드콜|Bond|Treasury|\(TR\)|TDF|Target Date)",
    re.I)
V3_NAME_EX = re.compile(
    r"(TR\b|TR$|합성|커버드콜|액티브|레버리지|인버스|선물|채권|국고채|통안채|국채|미국|(?<!코스닥)글로벌|단기자금|머니마켓|금현물|리츠|부동산|TRF|혼합|TDF)")

RULE_V3_CHANGES = [
    "기초지수명 국내 판정에 한국 시장 표지(Korea·코리아·한국·K-) 추가 — MSCI Korea·S&P Korea·Solactive K-·코리아 밸류업 지수(과세 01)가 v1 에서 빠졌다(FN 20 중 13)",
    "기초지수명 제외어 추가: 해외(미국·글로벌·차이나·중국·일본·인도·베트남·유럽·선진·신흥) · 채권/현금(국고채·통안채·국채·채권·머니마켓·MMF·Bond·Treasury) · 원자재(금현물·원유) · 혼합/TRF/TDF · 리츠/부동산 · 총수익·(TR) · 선물·레버리지·인버스·커버드콜 — v1 FP 26 은 전부 국내 산출기관이 낸 해외·채권·금·리츠·혼합 지수였다",
    "단, 코스닥 글로벌 지수(KRX 산출 코스닥 지수, 과세 01)는 '글로벌' 제외에서 뺀다",
    "이름 제외어 추가: 국고채·통안채·국채·미국·글로벌(코스닥글로벌 제외)·단기자금·머니마켓·금현물·리츠·부동산·TRF·혼합·TDF",
]


def rule_v1(m):
    return bool(V1_DOM_IDX.search(m["idx_last"])) and not V1_NAME_EX.search(m["name_last"])


def rule_v3(m):
    ix, nm = m["idx_last"], m["name_last"]
    return bool(V3_DOM_IDX.search(ix)) and not V3_IDX_EX.search(ix) and not V3_NAME_EX.search(nm)


def agreement(meta, db, fn):
    tp = fp = fnn = tn = 0
    fps, fns = [], []
    for t, r in db.items():
        y = r["txtn"] == "01"
        p = fn(meta[t])
        if p and y:
            tp += 1
        elif p and not y:
            fp += 1
            fps.append([t, meta[t]["name_last"], meta[t]["idx_last"], r["txtn"]])
        elif (not p) and y:
            fnn += 1
            fns.append([t, meta[t]["name_last"], meta[t]["idx_last"]])
        else:
            tn += 1
    n = tp + fp + fnn + tn
    return {
        "n": n, "tp": tp, "fp": fp, "fn": fnn, "tn": tn,
        "accuracy": (tp + tn) / n, "precision": tp / (tp + fp) if tp + fp else float("nan"),
        "recall": tp / (tp + fnn) if tp + fnn else float("nan"),
        "false_positives": fps, "false_negatives": fns,
    }


# ════════════════════════════════════════════════════════════════════
# 3. 지표
# ════════════════════════════════════════════════════════════════════
_STAGE_MAP = {("s", "m", "l"): 1, ("m", "s", "l"): 2, ("m", "l", "s"): 3,
              ("l", "m", "s"): 4, ("l", "s", "m"): 5, ("s", "l", "m"): 6}


def stages_of(es, em, el):
    out = np.zeros(len(es), dtype=np.int8)  # 0 = None
    prev = 0
    for i in range(len(es)):
        s, m, l = es[i], em[i], el[i]
        if s == m or m == l or s == l:
            st = prev
        else:
            trio = sorted((("s", s), ("m", m), ("l", l)), key=lambda x: -x[1])
            st = _STAGE_MAP.get(tuple(n for n, _ in trio), prev)
        out[i] = st
        prev = st
    return out


def fresh_61(stages, j, within=5):
    lo = max(0, j - within)
    for a in range(lo, j):
        if stages[a] == 6 and stages[a + 1] == 1:
            return True
    return False


# ════════════════════════════════════════════════════════════════════
# 4. 시장 유닛 (cycle376 계단형) — 069500 close_adj, 신호일 t 봉
# ════════════════════════════════════════════════════════════════════
def market_unit_series(k200, ncal):
    m = np.full(ncal, np.nan)
    c = pd.Series(k200["c"])
    sma = c.rolling(60, min_periods=60).mean().to_numpy()
    for j in range(len(c)):
        if j < 79 or np.isnan(sma[j]) or np.isnan(sma[j - 20]):
            continue
        above = c.iloc[j] > sma[j]
        rising = sma[j] > sma[j - 20]
        m[k200["ci"][j]] = 1.0 if (above and rising) else 0.75 if above else 0.5 if rising else 0.0
    return m


# ════════════════════════════════════════════════════════════════════
# 5. 신호 + 거래 시뮬레이션
# ════════════════════════════════════════════════════════════════════
def sim_kojiro(d, j):
    """신호봉 j, 진입봉 j+1(시가). 반환 = (exit_idx, exit_px, reason)."""
    E = d["o"][j + 1]
    A = d["atr20"][j]
    hard = max(E - 2.0 * A, E * 0.92)
    lines = {"hard": hard, "breakeven": -np.inf, "trail": -np.inf}
    stop, hsb = hard, -np.inf
    n = len(d["c"])
    stage3_pending = False
    for k in range(j + 1, n):
        if stage3_pending:
            return k, d["o"][k], "stage3"
        if d["o"][k] <= stop:
            return k, d["o"][k], "stop_gap"
        if d["l"][k] <= stop:
            return k, stop, max(lines, key=lambda x: (lines[x], ("hard", "breakeven", "trail").index(x)))
        hsb = max(hsb, d["h"][k])
        if hsb >= E + 1.5 * A:
            lines["breakeven"] = E
        lines["trail"] = hsb - 2.5 * A
        stop = max(lines.values())
        if d["stage"][k] == 3:
            stage3_pending = True
    return n - 1, d["c"][n - 1], "end"


def sim_donchian(d, j, intraday_line=False):
    """intraday_line=True = 민감도 S8(M12 를 라이브 쪽으로): D+2 부터 돌파선 이탈을 장중에(시가·저가) 본다."""
    E = d["o"][j + 1]
    N = d["n14"][j]
    line = d["hi_prev20"][j]
    hard = max(E - 2.0 * N, E * 0.91)
    stop, hsb = hard, -np.inf
    n = len(d["c"])
    D = j + 1
    for k in range(D, n):
        ch = np.min(d["l"][max(0, k - 10):k]) if k >= D + 1 else -np.inf
        ln = line if (intraday_line and k >= D + 2) else -np.inf
        if d["o"][k] <= stop or d["o"][k] < ch or d["o"][k] < ln:
            return k, d["o"][k], ("stop_gap" if d["o"][k] <= stop else "chan10_gap" if d["o"][k] < ch else "below_line_gap")
        trig = []
        if d["l"][k] <= stop:
            trig.append((stop, "stop"))
        if d["l"][k] < ch:
            trig.append((ch, "chan10"))
        if d["l"][k] < ln:
            trig.append((ln, "below_line"))
        if trig:
            px, why = max(trig)
            return k, px, why
        if (not intraday_line) and k >= D + 2 and d["c"][k] < line:
            return k, d["c"][k], "below_line"
        hsb = max(hsb, d["h"][k])
        be = E if hsb >= E + 1.5 * N else -np.inf
        stop = max(hard, be, hsb - 1.8 * N)
    return n - 1, d["c"][n - 1], "end"


def gen_trades(rule, data, cls, mu, cal, meta, last_ci, pre_listed_start=None, don_live=False):
    """pre_listed_start = 민감도 S5: 보관소 첫날(ci=0)부터 봉이 있는 종목(보관소 시작 전 상장)은 이 봉 번호부터
    신호를 허용한다(라이브라면 100봉 조건을 이미 넘는다). don_live = 민감도 S8(M12 장중 돌파선 이탈 · M13 60봉 창 EMA60)."""
    trades = []
    for t, d in data.items():
        if not cls.get(t):
            continue
        n = len(d["c"])
        j0 = MIN_BARS - 1
        if pre_listed_start is not None and d["ci"][0] == 0:
            j0 = pre_listed_start
        e60 = d["e60w"] if don_live else d["e60"]
        for j in range(j0, n - 1):
            ci = d["ci"][j]
            if d["ci"][j + 1] != ci + 1:      # 다음 거래일 봉이 없으면 진입 불가
                continue
            c = d["c"][j]
            craw = d["craw"][j]
            a20 = d["atr20"][j]
            atr_pct = a20 / c
            if not (d["tv20"][j] >= TV20_MIN and craw >= PX_MIN and atr_pct >= ATR_LO):
                continue
            if rule == "kojiro":
                if atr_pct > ATR_HI:
                    continue
                st = d["stage"]
                if st[j] != 1:
                    continue
                if not (d["es"][j] > d["es"][j - 1] and d["em"][j] > d["em"][j - 1] and d["el"][j] > d["el"][j - 1]):
                    continue
                if not c > d["es"][j]:
                    continue
                if not fresh_61(st, j, 5):
                    continue
                gap = d["o"][j + 1] / c - 1
                if gap >= 0.05 or gap <= -0.04:
                    continue
                k, px, why = sim_kojiro(d, j)
                size_atr = a20
            else:
                hp = d["hi_prev20"][j]
                if not (hp > 0 and c > hp):
                    continue
                if not (e60[j] > e60[j - 1] and c > e60[j]):
                    continue
                tvp = d["tvprev20"][j]
                if not (tvp > 0 and d["tv"][j] >= 1.5 * tvp):
                    continue
                N = d["n14"][j]
                if not (N > 0):
                    continue
                o1 = d["o"][j + 1]
                if o1 >= c * 1.03 or o1 > hp * 1.04:
                    continue
                k, px, why = sim_donchian(d, j, intraday_line=don_live)
                size_atr = N
            m = mu[ci]
            E = d["o"][j + 1]
            rw = 2.0 * size_atr
            cost = COST_LIQ if d["tv20"][j] >= COST_LIQ_TV else COST_ILLIQ
            if why == "end":
                why = "open_end" if d["ci"][k] == last_ci else "delist"
            R = (px - E) / rw
            Rnet = (px - E - cost * E) / rw
            f = min(1.0, POS_RATIO * (size_atr / c) / RISK_PCT)
            # 정수 랏(예산 75만, 폴백 금지 참고): 원가 기준
            scale = craw / c
            lot = 0
            if m == m and m > 0:
                b = REP_BUDGET * m
                lot = int(math.floor(min(b * RISK_PCT / (size_atr * scale), POS_RATIO * b / craw)))
            trades.append({
                "ticker": t, "sig_ci": int(ci), "entry_ci": int(ci + 1), "exit_ci": int(d["ci"][k]),
                "entry_date": str(pd.Timestamp(cal[ci + 1]).date()), "exit_date": str(pd.Timestamp(cal[d["ci"][k]]).date()),
                "E": float(E), "exit_px": float(px), "reason": why, "R": float(R), "Rnet": float(Rnet),
                "m": float(m) if m == m else None, "f": float(f), "tv20": float(d["tv20"][j]),
                "atr_pct": float(atr_pct), "size_atr_pct": float(size_atr / c), "hold": int(k - j - 1),
                "lot75": lot, "listed_at_end": bool(meta[t]["listed_at_end"]),
                # 넓은 유니버스 판(§3.1 U1) 과 §2.3 전체판을 가르는 플래그
                "f_mcap": bool(d["mc"][j] >= MCAP_MIN), "f_pxhi": bool(craw <= PX_MAX),
                "f_atrhi": bool(atr_pct <= ATR_HI), "f_qual": bool(d["qual60"][j]),
                # 민감도 S7: 시총 대신 순자산총액(KRX INVSTASST_NETASST_TOTAMT). 값이 없으면 False
                "f_nav": bool(np.isfinite(d["nav"][j]) and d["nav"][j] >= MCAP_MIN) if "nav" in d else None,
                # 일별 평가 MDD(감사 지적 6)용: 종목 배열 위치·R폭·비용
                "j": int(j), "k": int(k), "rw": float(rw), "cost": float(cost),
            })
    return trades


# ════════════════════════════════════════════════════════════════════
# 6. 중복 제거 (묶음당 1개)
# ════════════════════════════════════════════════════════════════════
class Corr:
    def __init__(self, ret, col):
        self.ret, self.col, self.cache = ret, col, {}

    def __call__(self, a, b, ci):
        if a == b:
            return 1.0
        key = (min(a, b), max(a, b), ci)
        if key in self.cache:
            return self.cache[key]
        lo = max(0, ci - CORR_WIN + 1)
        x = self.ret[lo:ci + 1, self.col[a]]
        y = self.ret[lo:ci + 1, self.col[b]]
        mk = np.isfinite(x) & np.isfinite(y)
        if mk.sum() < CORR_MIN_OBS:
            v = None
        else:
            xx, yy = x[mk], y[mk]
            if xx.std() == 0 or yy.std() == 0:
                v = None
            else:
                v = float(np.corrcoef(xx, yy)[0, 1])
        self.cache[key] = v
        return v


def same_cluster(corr, a, b, ci):
    v = corr(a, b, ci)
    return v is not None and v > CORR_TH


def dedup(trades, corr, rep_select=False, exit_day_holds=True):
    """exit_day_holds=False = 민감도 S9(M8 반대 해석): 그날 청산되는 거래는 그날 다른 종목의 묶음 보유로 치지 않는다.
    같은 종목 당일 재매수는 그래도 막는다(라이브 registry.is_ticker_blocked_for_buy 의 당일매도 차단)."""
    by_day = defaultdict(list)
    for tr in trades:
        by_day[tr["entry_ci"]].append(tr)
    held, out, n_sub = [], [], 0
    for day in sorted(by_day):
        held = [h for h in held if h["exit_ci"] >= day]
        sold_today = set() if exit_day_holds else {h["ticker"] for h in held if h["exit_ci"] == day}
        held_c = held if exit_day_holds else [h for h in held if h["exit_ci"] > day]
        cands = sorted(by_day[day], key=lambda x: -x["tv20"])
        taken_today, skip = [], set()
        for i, c in enumerate(cands):
            if id(c) in skip:
                continue
            if c["ticker"] in sold_today:
                continue
            pool = held_c + taken_today
            if any(same_cluster(corr, c["ticker"], h["ticker"], c["sig_ci"]) for h in pool):
                continue
            pick = c
            if rep_select and c["lot75"] < REP_MIN_LOT:
                for d2 in cands[i + 1:]:
                    if id(d2) in skip or d2["lot75"] < REP_MIN_LOT:
                        continue
                    if not same_cluster(corr, c["ticker"], d2["ticker"], c["sig_ci"]):
                        continue
                    if any(same_cluster(corr, d2["ticker"], h["ticker"], d2["sig_ci"]) for h in pool):
                        continue
                    pick = d2
                    skip.add(id(d2))
                    n_sub += 1
                    break
            taken_today.append(pick)
            out.append(pick)
        held.extend(taken_today)
    return out, n_sub


# ════════════════════════════════════════════════════════════════════
# 7. 지표 계산
# ════════════════════════════════════════════════════════════════════
def wmean(ts):
    w = np.array([t["m"] for t in ts])
    r = np.array([t["Rnet"] for t in ts])
    return float((w * r).sum() / w.sum()) if len(ts) and w.sum() > 0 else float("nan")


def boot_ci(ts, rng=None, keyf=None):
    """묶음 부트스트랩 — 기본 묶음 = 진입일(§3.1·§8.3 판정 정의). keyf 를 주면 그 키로 묶는다(감사 지적 5 병기용).
    호출마다 같은 씨앗(SEED)이라 계산 순서와 무관하게 재현된다."""
    rng = np.random.default_rng(SEED)
    if len(ts) < 2:
        return [float("nan"), float("nan")]
    keyf = keyf or (lambda t: t["entry_ci"])
    cl = defaultdict(lambda: [0.0, 0.0])
    for t in ts:
        cl[keyf(t)][0] += t["m"] * t["Rnet"]
        cl[keyf(t)][1] += t["m"]
    if len(cl) < 2:
        return [float("nan"), float("nan")]
    s1 = np.array([v[0] for v in cl.values()])
    s0 = np.array([v[1] for v in cl.values()])
    K = len(s1)
    cnt = rng.multinomial(K, np.full(K, 1.0 / K), size=N_BOOT).astype(float)
    # einsum: macOS Accelerate matmul 의 허위 FP 경고를 피한다(값은 matmul 과 1e-15 안에서 같다 — 검증함)
    stat = np.einsum("ij,j->i", cnt, s1) / np.einsum("ij,j->i", cnt, s0)
    return [float(np.percentile(stat, 2.5)), float(np.percentile(stat, 97.5))]


def in_period(t, p):
    a, b = PERIODS[p]
    return a <= t["entry_date"] <= b


def key_month(t):
    return t["entry_date"][:7]


def key_overlap(ts):
    """보유 겹침 구간: 진입~청산이 이어지는 거래를 한 덩어리로(연결 성분). 동시 보유 상관을 묶는다."""
    srt = sorted(ts, key=lambda t: (t["entry_ci"], t["exit_ci"]))
    lab, cid, cur_end = {}, -1, -1
    for t in srt:
        if t["entry_ci"] > cur_end:
            cid += 1
        cur_end = max(cur_end, t["exit_ci"])
        lab[id(t)] = cid
    return lambda t: lab[id(t)]


def block_cis(ts):
    """감사 지적 5 — 판정 정의(진입일 묶음) 옆에 월·보유 겹침 구간 묶음을 병기한다. 판정에는 쓰지 않는다."""
    A = [t for t in ts if in_period(t, "A")]
    ko, koA = key_overlap(ts), key_overlap(A)
    return {
        "full_day": boot_ci(ts), "full_month": boot_ci(ts, keyf=key_month), "full_overlap": boot_ci(ts, keyf=ko),
        "A_day": boot_ci(A), "A_month": boot_ci(A, keyf=key_month), "A_overlap": boot_ci(A, keyf=koA),
        "n_clusters": {"day": len({t["entry_ci"] for t in ts}), "month": len({key_month(t) for t in ts}),
                       "overlap": len({ko(t) for t in ts})},
    }


def r_stats(ts, rng):
    """ts = m>0 중복 제거 거래."""
    n = len(ts)
    res = {"n": n, "wR": wmean(ts), "ci95": boot_ci(ts, rng)}
    for p in PERIODS:
        sub = [t for t in ts if in_period(t, p)]
        res[f"wR_{p}"] = wmean(sub)
        res[f"n_{p}"] = len(sub)
        res[f"ci95_{p}"] = boot_ci(sub, rng)
    ex25 = [t for t in ts if not t["entry_date"].startswith("2025")]
    res["wR_ex2025"], res["n_ex2025"] = wmean(ex25), len(ex25)
    k = math.ceil(0.01 * n)
    srt = sorted(ts, key=lambda x: -x["Rnet"])
    res["top1pct_k"] = k
    res["wR_ex_top1pct"] = wmean(srt[k:])
    years = sorted({t["entry_date"][:4] for t in ts})
    res["wR_by_year"] = {y: [wmean([t for t in ts if t["entry_date"][:4] == y]),
                             sum(1 for t in ts if t["entry_date"][:4] == y)] for y in years}
    res["by_m"] = {str(mv): [wmean([t for t in ts if t["m"] == mv]), sum(1 for t in ts if t["m"] == mv)]
                   for mv in (0.5, 0.75, 1.0)}
    rn = np.array([t["Rnet"] for t in ts]) if n else np.array([])
    res["win_rate"] = float((rn > 0).mean()) if n else float("nan")
    res["avg_win"] = float(rn[rn > 0].mean()) if (rn > 0).any() else float("nan")
    res["avg_loss"] = float(rn[rn <= 0].mean()) if (rn <= 0).any() else float("nan")
    res["payoff"] = res["avg_win"] / abs(res["avg_loss"]) if res["avg_loss"] == res["avg_loss"] and res["avg_loss"] else float("nan")
    res["max_R"] = float(rn.max()) if n else float("nan")
    res["hold_median"] = float(np.median([t["hold"] for t in ts])) if n else float("nan")
    res["exit_reasons"] = {k2: round(v / n, 3) for k2, v in Counter(t["reason"] for t in ts).most_common()} if n else {}
    res["n_delisted_ticker_trades"] = sum(1 for t in ts if not t["listed_at_end"])
    res["wR_delisted_ticker_trades"] = wmean([t for t in ts if not t["listed_at_end"]])
    res["n_tickers"] = len({t["ticker"] for t in ts})
    res["lot75_zero"] = sum(1 for t in ts if t["lot75"] == 0)
    res["wR_excl_lot75_zero"] = wmean([t for t in ts if t["lot75"] > 0])
    res["size_atr_pct_median"] = float(np.median([t["size_atr_pct"] for t in ts])) if n else float("nan")
    res["f_median"] = float(np.median([t["f"] for t in ts])) if n else float("nan")
    res["earliest_entry"] = min((t["entry_date"] for t in ts), default=None)
    return res


def _approx_mdd(taken, pnl):
    ex_order = sorted(range(len(taken)), key=lambda i: (taken[i]["exit_ci"], taken[i]["entry_ci"]))
    cum = np.concatenate([[0.0], np.cumsum(pnl[ex_order])]) * 100
    return float((cum - np.maximum.accumulate(cum)).min())


def _mtm_mdd(taken, data, ncal):
    """감사 지적 6 — 일별 평가손 포함 MDD(%p). 진입일 시가 E 부터 매일 종가로 평가하고 청산일에 청산가·비용을 반영한다.
    합계는 근사 MDD 와 같은 손익(Σ Rnet·f·m·2·risk_pct)이다."""
    daily = np.zeros(ncal)
    for t in taken:
        d = data[t["ticker"]]
        w = t["f"] * t["m"] * 2 * RISK_PCT / t["rw"]
        D, k = t["j"] + 1, t["k"]
        prev = t["E"]
        for i in range(D, k):
            daily[d["ci"][i]] += (d["c"][i] - prev) * w
            prev = d["c"][i]
        daily[d["ci"][k]] += (t["exit_px"] - prev - t["cost"] * t["E"]) * w
    eq = np.cumsum(daily) * 100
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    return float(min(0.0, (eq - peak).min()))


def sleeve(ts, seed_base, data=None, ncal=None):
    """T5 판정 정의(§8.3 · M10 · M11): 중복 제거된 거래 목록 위에서 슬롯 4, 같은 날 순서 무작위 40회.
    data 를 주면 같은 선택으로 일별 평가 MDD 도 잰다(보고만, 판정에 쓰지 않는다)."""
    yrs_full = years_between(FULL_START, FULL_END)
    yrs_p = {p: years_between(a, b) for p, (a, b) in PERIODS.items()}
    runs = []
    for r in range(N_SLEEVE):
        rng = np.random.default_rng(seed_base + r)
        keys = rng.random(len(ts))
        order = sorted(range(len(ts)), key=lambda i: (ts[i]["entry_ci"], keys[i]))
        open_exit, taken = [], []
        for i in order:
            t = ts[i]
            open_exit = [x for x in open_exit if x >= t["entry_ci"]]
            if len(open_exit) < SLOTS:
                open_exit.append(t["exit_ci"])
                taken.append(t)
        pnl = np.array([t["Rnet"] * t["f"] * t["m"] * 2 * RISK_PCT for t in taken])
        ann = pnl.sum() / yrs_full * 100
        mdd = _approx_mdd(taken, pnl)
        mdd_mtm = _mtm_mdd(taken, data, ncal) if data is not None else float("nan")
        per = {}
        for p in PERIODS:
            idx = [k for k, t in enumerate(taken) if in_period(t, p)]
            per[p] = (float(pnl[idx].sum() / yrs_p[p] * 100) if idx else 0.0, len(idx) / yrs_p[p])
        runs.append({"ann": ann, "mdd": mdd, "mdd_mtm": mdd_mtm, "per": per, "n": len(taken)})
    anns = np.array([x["ann"] for x in runs])
    mdds = np.array([x["mdd"] for x in runs])
    out = {
        "ann_mean": float(anns.mean()), "ann_min": float(anns.min()), "ann_max": float(anns.max()),
        "mdd_median": float(np.median(mdds)), "mdd_worst": float(mdds.min()), "mdd_best": float(mdds.max()),
        "trades_per_run_mean": float(np.mean([x["n"] for x in runs])),
    }
    for p in PERIODS:
        out[f"ann_{p}"] = float(np.mean([x["per"][p][0] for x in runs]))
        out[f"tpy_{p}"] = float(np.mean([x["per"][p][1] for x in runs]))
    out["ret_over_mdd"] = out["ann_mean"] / abs(out["mdd_median"]) if out["mdd_median"] < 0 else float("inf")
    if data is not None:
        mm = np.array([x["mdd_mtm"] for x in runs])
        out["mtm_mdd_median"] = float(np.median(mm))
        out["mtm_mdd_worst"] = float(mm.min())
        out["ret_over_mtm_mdd"] = out["ann_mean"] / abs(out["mtm_mdd_median"]) if out["mtm_mdd_median"] < 0 else float("inf")
    return out


def sleeve_integrated(buy, corr, order_mode, seed_base):
    """감사 지적 9 — 묶음 중복 제거를 「실제 슬리브 보유」 기준으로 슬롯 4 와 함께 한 번에 적용한 판(보고만).
    order_mode: "rand"(같은 날 무작위 40회) | "tv"(20일 거래대금 내림차순 = 라이브 매수 폴 순서, 1회)."""
    yrs = years_between(FULL_START, FULL_END)
    by = defaultdict(list)
    for t in buy:
        by[t["entry_ci"]].append(t)
    days = sorted(by)
    runs = []
    for r in range(N_SLEEVE if order_mode == "rand" else 1):
        rng = np.random.default_rng(seed_base + r)
        held, taken = [], []
        for day in days:
            held = [h for h in held if h["exit_ci"] >= day]
            c = by[day]
            if order_mode == "tv":
                c = sorted(c, key=lambda x: -x["tv20"])
            else:
                kk = rng.random(len(c))
                c = [c[i] for i in np.argsort(kk, kind="stable")]
            for t in c:
                if len(held) >= SLOTS:
                    break
                if any(same_cluster(corr, t["ticker"], h["ticker"], t["sig_ci"]) for h in held):
                    continue
                held.append(t)
                taken.append(t)
        pnl = np.array([t["Rnet"] * t["f"] * t["m"] * 2 * RISK_PCT for t in taken])
        runs.append((pnl.sum() / yrs * 100, _approx_mdd(taken, pnl), len(taken)))
    ann = float(np.mean([x[0] for x in runs]))
    mdd = float(np.median([x[1] for x in runs]))
    return {"ann_mean": ann, "mdd_median": mdd, "ret_over_mdd": ann / abs(mdd) if mdd < 0 else float("inf"),
            "trades_per_run_mean": float(np.mean([x[2] for x in runs]))}


def judge(st, sl):
    t = {}
    t["T1"] = bool(st["wR"] >= T1_MIN_R and st["ci95"][0] > 0)
    t["T2"] = bool(st["wR_A"] >= T2_MIN_R)
    t["T3"] = bool(st["wR_ex2025"] > 0)
    t["T4"] = bool(st["wR_ex_top1pct"] > 0)
    t["T5"] = bool(sl["ann_mean"] > 0 and sl["mdd_median"] >= T5_MIN_MDD)
    t["pass_T1_T5"] = all(t[k] for k in ("T1", "T2", "T3", "T4", "T5"))
    return t


# ════════════════════════════════════════════════════════════════════
# main
# ════════════════════════════════════════════════════════════════════
def load_nav(tickers):
    """민감도 S7 — KRX 순자산총액(INVSTASST_NETASST_TOTAMT, 원). {ticker: {Timestamp: float}}."""
    nav = defaultdict(dict)
    with open(RAW_JSONL, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            dt = pd.Timestamp(p["bas_dd"])
            for r in p["rows"]:
                t = r.get("ISU_CD")
                if t in tickers:
                    v = (r.get("INVSTASST_NETASST_TOTAMT") or "").replace(",", "")
                    try:
                        nav[t][dt] = float(v)
                    except ValueError:
                        pass
    return nav


def full_u(t, mcap_key="f_mcap"):
    return t[mcap_key] and t["f_pxhi"] and t["f_atrhi"] and t["f_qual"]


def main():
    print("[s0] hashing inputs ...", flush=True)
    hashes = {os.path.relpath(p, "/Users/koscom/Projects/auto_stock"): sha256_file(p) for p in PARQUETS}
    hashes["data/archive/krx_etf_daily/raw_2020_2026.jsonl"] = sha256_file(RAW_JSONL)
    hashes["scratchpad/etf_s0/input/stock_master_etf_fields.json"] = sha256_file(DB_FIELDS)
    hashes["scratchpad/etf_s0/q_etf_fields_ro.py"] = sha256_file(DB_QUERY)
    script_sha = sha256_file(os.path.abspath(__file__))

    print("[s0] meta ...", flush=True)
    meta, last_date, n_last = load_meta()
    dbj = json.load(open(DB_FIELDS))
    db = {r["ticker"]: r for r in dbj["rows"]}

    agr_v1 = agreement(meta, db, rule_v1)
    agr_v3 = agreement(meta, db, rule_v3)
    v1_ok = agr_v1["precision"] >= 0.9 and agr_v1["recall"] >= 0.9
    rule_used = "v1" if v1_ok else "v3"
    rule_fn = rule_v1 if v1_ok else rule_v3

    def classify(fn, numeric_only):
        out, src = {}, {}
        for t, m in meta.items():
            if t in db:
                r = db[t]
                v = (r["grp"] == "EF" and r["txtn"] == "01" and r["mult"] == "1" and (r["heed"] or "N") != "Y")
                src[t] = "db"
            else:
                v = fn(m)
                src[t] = "rule"
            out[t] = bool(v and (live_code(t) or not numeric_only))
        return out, src

    cls, cls_src = classify(rule_fn, True)          # 판정판(v2): 라이브가 닿는 6자리 숫자 코드만
    cls_v1run, _ = classify(rule_fn, False)         # 민감도 S0 = v1 판정판(영숫자 코드 포함)
    cls_rule_v1, _ = classify(rule_v1, True)        # 민감도 S6 = §8.2 글자 그대로(v1) 규칙 + 숫자 코드

    alnum = [t for t in meta if not live_code(t)]
    cls_summary = {
        "total_tickers": len(meta), "listed_at_end": n_last, "last_list_date": last_date,
        "delisted": sum(1 for m in meta.values() if not m["listed_at_end"]),
        "db_rows": len(db), "db_listed_at_end": sum(1 for t in db if meta[t]["listed_at_end"]),
        "rule_classified": sum(1 for s in cls_src.values() if s == "rule"),
        "U1_class_total": sum(cls.values()),
        "U1_class_db": sum(1 for t in cls if cls[t] and cls_src[t] == "db"),
        "U1_class_rule_listed": sum(1 for t in cls if cls[t] and cls_src[t] == "rule" and meta[t]["listed_at_end"]),
        "U1_class_rule_delisted": sum(1 for t in cls if cls[t] and cls_src[t] == "rule" and not meta[t]["listed_at_end"]),
        "U1_class_db_delisted": sum(1 for t in cls if cls[t] and cls_src[t] == "db" and not meta[t]["listed_at_end"]),
        # 감사 지적 1 — 영숫자 코드
        "alnum_total": len(alnum),
        "alnum_in_db": sum(1 for t in alnum if t in db),
        "alnum_listed_not_db": sum(1 for t in alnum if meta[t]["listed_at_end"] and t not in db),
        "alnum_delisted": sum(1 for t in alnum if not meta[t]["listed_at_end"]),
        "listed_not_db": sum(1 for t in meta if meta[t]["listed_at_end"] and t not in db),
        "numeric_listed_not_db": sum(1 for t in meta if live_code(t) and meta[t]["listed_at_end"] and t not in db),
        "U1_class_total_v1run": sum(cls_v1run.values()),
        "U1_alnum_excluded": sum(1 for t in meta if cls_v1run[t] and not live_code(t)),
        "U1_class_total_rule_v1": sum(cls_rule_v1.values()),
    }

    print("[s0] load parquet ...", flush=True)
    df = pd.concat([pd.read_parquet(p) for p in PARQUETS], ignore_index=True)
    cal = np.array(sorted(df["bas_dd"].unique()))
    cal_index = pd.Series(np.arange(len(cal)), index=pd.DatetimeIndex(cal))
    k200 = df[df["ticker"] == "069500"]
    assert len(k200) == len(cal), "069500 달력이 전체 달력과 다르다"
    cal_map = cal_index

    def cmap(vals):
        return cal_map.loc[pd.DatetimeIndex(vals)].to_numpy()

    need = ({t for t, v in cls_v1run.items() if v} | {t for t, v in cls_rule_v1.items() if v} | {"069500"})
    print("[s0] net asset (S7) ...", flush=True)
    nav = load_nav(need)

    print("[s0] indicators ...", flush=True)
    data = {}
    for t, g in df[df["ticker"].isin(need)].groupby("ticker"):
        d = build_ticker_cal(g, cmap, nav.get(t))
        if d is not None:
            data[t] = d
    mu = market_unit_series(data["069500"], len(cal))
    last_ci = len(cal) - 1
    ncal = len(cal)
    mu_dist = Counter(str(v) for v in mu[~np.isnan(mu)])
    first_mu = str(pd.Timestamp(cal[np.where(~np.isnan(mu))[0][0]]).date())
    k200_bar100 = str(pd.Timestamp(cal[data["069500"]["ci"][MIN_BARS - 1]]).date())

    # 수익률 행렬 (상관용) — 모든 후보 종목. 상관값은 다른 열과 무관하다
    tick_list = sorted(data)
    col = {t: i for i, t in enumerate(tick_list)}
    ret = np.full((len(cal), len(tick_list)), np.nan)
    for t, d in data.items():
        cc = np.full(len(cal), np.nan)
        cc[d["ci"]] = d["c"]
        r = cc[1:] / cc[:-1] - 1
        ret[1:, col[t]] = r
    corr = Corr(ret, col)

    data_cls = {t: d for t, d in data.items() if cls.get(t)}
    # 상장폐지 U1 부류가 유동성·시총 하한에 닿은 적이 있나
    dl = [t for t in data_cls if not meta[t]["listed_at_end"]]
    both = 0
    for t in dl:
        d = data_cls[t]
        if np.any((d["tv20"] >= TV20_MIN) & (d["mc"] >= MCAP_MIN)):
            both += 1
    cls_summary["delisted_U1_class_with_bars"] = len(dl)
    cls_summary["delisted_U1_class_ever_tv20_ge_20eok"] = int(sum(np.nanmax(data_cls[t]["tv20"]) >= TV20_MIN for t in dl if np.isfinite(data_cls[t]["tv20"]).any()))
    cls_summary["delisted_U1_class_ever_mcap_ge_500eok"] = int(sum(np.max(data_cls[t]["mc"]) >= MCAP_MIN for t in dl))
    cls_summary["delisted_U1_class_ever_both_same_day"] = both
    cls_summary["delisted_U1_class_top_tv20"] = sorted(
        [[t, meta[t]["name_last"], round(float(np.nanmax(data_cls[t]["tv20"])) / 1e8, 1) if np.isfinite(data_cls[t]["tv20"]).any() else None,
          round(float(np.max(data_cls[t]["mc"])) / 1e8, 1)] for t in dl], key=lambda x: -(x[2] or 0))[:8]

    def pipeline(rule, cls_x, **gk):
        dcls = {t: d for t, d in data.items() if cls_x.get(t)}
        allt = gen_trades(rule, dcls, cls_x, mu, cal, meta, last_ci, **gk)
        return [t for t in allt if t["entry_date"] >= FULL_START and t["m"] is not None]

    rng = np.random.default_rng(SEED)
    results = {"rules": {}}
    for rule in ("kojiro", "donchian"):
        print(f"[s0] {rule}: signals ...", flush=True)
        ridx = 1 if rule == "kojiro" else 2
        roff = 0 if rule == "kojiro" else 50000
        allt = pipeline(rule, cls)
        base = [t for t in allt if full_u(t)]
        buy = [t for t in base if t["m"] > 0]

        # 판정판: 중복 제거(m>0 만 보유로 친다 — M20), 대표 선택 끈 판
        ded, _ = dedup(buy, corr, rep_select=False)
        st = r_stats(ded, rng)
        sl = sleeve(ded, SEED + 1000 * ridx, data, ncal)
        jd = judge(st, sl)
        bc = block_cis(ded)
        integ = {"rand": sleeve_integrated(buy, corr, "rand", SEED + 20000 + roff),
                 "tv": sleeve_integrated(buy, corr, "tv", SEED)}

        # T6: 현재 상장분만 (중복 제거 재실행)
        ded_live, _ = dedup([t for t in buy if t["listed_at_end"]], corr, rep_select=False)
        st_live = r_stats(ded_live, rng)
        ratio = st["wR"] / st_live["wR"] if st_live["wR"] > 0 else float("nan")
        t6 = {"wR_all": st["wR"], "wR_listed_only": st_live["wR"], "n_all": st["n"], "n_listed_only": st_live["n"],
              "ratio": ratio, "ok": bool(ratio == ratio and ratio >= T6_MIN_RATIO),
              "ci95_listed_only": st_live["ci95"]}
        jd["T6_warning_ok"] = t6["ok"]

        # A 구간 실제 시작(감사 지적 3)
        a_start = {
            "earliest_signal_any_filter": str(pd.Timestamp(cal[min(t["sig_ci"] for t in allt)]).date()) if allt else None,
            "earliest_signal_full_universe": str(pd.Timestamp(cal[min(t["sig_ci"] for t in base)]).date()) if base else None,
            "first_entry_judged": st["earliest_entry"],
        }

        # ── 민감도 변형 (판정에 쓰지 않는다) ──
        variants = {}

        def run_variant(name, ded_v, seed_off):
            stv = r_stats(ded_v, rng)
            slv = sleeve(ded_v, SEED + seed_off, data, ncal)
            variants[name] = {"stats": stv, "sleeve": slv, "judge": judge(stv, slv)}

        # S0 v1 판정판(영숫자 코드 포함) — 감사 지적 1
        allt0 = pipeline(rule, cls_v1run)
        buy0 = [t for t in allt0 if full_u(t) and t["m"] > 0]
        ded0, _ = dedup(buy0, corr, rep_select=False)
        run_variant("S0_v1_incl_alnum", ded0, 1000 * ridx)   # v1 판정판과 같은 슬리브 씨앗 → v1 results.md 를 그대로 재현
        alnum_tr = [t for t in ded0 if not live_code(t["ticker"])]
        variants["S0_v1_incl_alnum"]["alnum_trades"] = len(alnum_tr)
        variants["S0_v1_incl_alnum"]["alnum_wR"] = wmean(alnum_tr)
        variants["S0_v1_incl_alnum"]["alnum_tickers"] = sorted({(t["ticker"], meta[t["ticker"]]["name_last"]) for t in alnum_tr})
        # S1 대표 선택 켬 (§2.4 선택 규칙 — §8.3 이 켠 판·끈 판 따로 보고를 요구)
        ded_rep, n_sub = dedup(buy, corr, rep_select=True)
        run_variant("S1_rep_select_on", ded_rep, roff + 3000)
        variants["S1_rep_select_on"]["n_substituted"] = n_sub
        # S2 m=0 신호도 묶음 보유로 치는 중복 제거(설계서 재현 방식) 뒤 m>0 가중 — 모호점 M20
        ded_all, _ = dedup(base, corr, rep_select=False)
        run_variant("S2_dedup_incl_m0", [t for t in ded_all if t["m"] > 0], roff + 4000)
        # S3 §3.1 좁은 U1 (시총·가격상한·일봉품질 미적용; kojiro 는 ATR 상한 유지 — 신호 정의) — 모호점 M3
        nar_all = [t for t in allt if (t["f_atrhi"] if rule == "kojiro" else True)]
        ded_nar, _ = dedup([t for t in nar_all if t["m"] > 0], corr, rep_select=False)
        run_variant("S3_narrow_U1", ded_nar, roff + 5000)
        # S4 = S2 + S3 (설계서 「지금 값」 의 측정 방식에 가장 가까운 판)
        ded_nar_all, _ = dedup(nar_all, corr, rep_select=False)
        run_variant("S4_narrow_dedup_incl_m0", [t for t in ded_nar_all if t["m"] > 0], roff + 6000)
        # S5 보관소 시작 전 상장 종목은 m 산출 봉(80번째)부터 신호 허용 — 감사 지적 3
        allt5 = pipeline(rule, cls, pre_listed_start=79)
        ded5, _ = dedup([t for t in allt5 if full_u(t) and t["m"] > 0], corr, rep_select=False)
        run_variant("S5_prelisted_min_bars", ded5, roff + 7000)
        variants["S5_prelisted_min_bars"]["added_early"] = [
            (t["ticker"], meta[t["ticker"]]["name_last"], t["entry_date"], round(t["Rnet"], 3), t["m"])
            for t in ded5 if t["sig_ci"] < min((x["sig_ci"] for x in ded), default=10 ** 9)]
        # S6 §8.2 v1(글자 그대로) 규칙 + 숫자 코드 — 감사 지적 7
        allt6 = pipeline(rule, cls_rule_v1)
        ded6, _ = dedup([t for t in allt6 if full_u(t) and t["m"] > 0], corr, rep_select=False)
        run_variant("S6_rule_v1", ded6, roff + 8000)
        key = lambda t: (t["ticker"], t["entry_ci"])
        variants["S6_rule_v1"]["same_trade_set_as_judged"] = sorted(map(key, ded6)) == sorted(map(key, ded))
        # S7 시총 대신 순자산총액 — 감사 지적 8
        ded7, _ = dedup([t for t in allt if full_u(t, "f_nav") and t["m"] > 0], corr, rep_select=False)
        run_variant("S7_net_asset", ded7, roff + 9000)
        b_mc = {key(t) for t in allt if full_u(t) and t["m"] > 0}
        b_nv = {key(t) for t in allt if full_u(t, "f_nav") and t["m"] > 0}
        variants["S7_net_asset"]["signals_in_only_nav"] = len(b_nv - b_mc)
        variants["S7_net_asset"]["signals_in_only_mcap"] = len(b_mc - b_nv)
        # S8 donchian M12(장중 돌파선 이탈)·M13(60봉 창 EMA60) 라이브 쪽 — 감사 지적 2. kojiro 는 판정판 그대로
        if rule == "donchian":
            allt8 = pipeline(rule, cls, don_live=True)
            ded8, _ = dedup([t for t in allt8 if full_u(t) and t["m"] > 0], corr, rep_select=False)
            run_variant("S8_donchian_live_m12_m13", ded8, roff + 10000)
        else:
            variants["S8_donchian_live_m12_m13"] = {"stats": st, "sleeve": sl, "judge": jd, "same_as_judged": True}

        # S9 M8 반대 해석 — 교차계산과의 차이 대부분이 여기서 왔다(reconcile_cross_check.py C7)
        ded9, _ = dedup(buy, corr, rep_select=False, exit_day_holds=False)
        run_variant("S9_exit_day_not_held", ded9, roff + 11000)

        # 참고: 균등(m=0 포함) — m=0 거래의 R (설계서 「계단형이 거르는 거래」 행과 같은 정의)
        eq = {"n": len(ded_all), "R_equal": float(np.mean([t["Rnet"] for t in ded_all])) if ded_all else float("nan")}
        z = [t for t in ded_all if t["m"] == 0]
        eq["n_m0"] = len(z)
        eq["R_m0"] = float(np.mean([t["Rnet"] for t in z])) if z else float("nan")
        eq["ci95_m0_equal"] = boot_ci([dict(t, m=1.0) for t in z]) if z else [float("nan")] * 2

        results["rules"][rule] = {
            "signals_pre_universe_filters": len(allt), "signals_full_universe": len(base),
            "signals_m_pos": len(buy), "dedup_m_pos": len(ded),
            "stats": st, "sleeve": sl, "judge": jd, "T6": t6, "block_ci": bc, "integrated_sleeve": integ,
            "A_start": a_start,
            "variants": variants,
            "equal_weight_reference": eq,
            "trades_by_class_source": dict(Counter(cls_src[t["ticker"]] for t in ded)),
            "delisted_tickers_traded": sorted({(t["ticker"], meta[t["ticker"]]["name_last"]) for t in ded if not t["listed_at_end"]}),
            "delisted_U1_class_signals_any_filter": sum(1 for t in allt if not t["listed_at_end"]),
        }
        print(f"[s0] {rule}: n={st['n']} wR={st['wR']:+.3f} ci={st['ci95']} A={st['wR_A']:+.3f} pass={jd['pass_T1_T5']}", flush=True)

    # §3.1 판정
    kj, dc = results["rules"]["kojiro"], results["rules"]["donchian"]
    adopted, verdict, pk, pd_ = decide(kj, dc)
    sens = {}
    for vn in kj["variants"]:
        a2, v2, p2k, p2d = decide(kj["variants"][vn], dc["variants"][vn])
        sens[vn] = {"adopted": a2, "text": v2, "kojiro_pass": p2k, "donchian_pass": p2d}
    results["sensitivity_verdicts"] = sens

    out = {
        "script_version": SCRIPT_VERSION,
        "generated_at_kst": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "runtime_sec": round(time.time() - T0, 1),
        "seed": SEED, "n_boot": N_BOOT, "n_sleeve_runs": N_SLEEVE,
        "script_sha256": script_sha, "input_sha256": hashes,
        "thresholds_fixed": {"T1": f"wR >= {T1_MIN_R} and ci95_low > 0", "T2": f"wR_A >= {T2_MIN_R}",
                             "T3": "wR_ex2025 > 0", "T4": "wR_ex_top1pct > 0",
                             "T5": f"sleeve ann_mean > 0 and mdd_median >= {T5_MIN_MDD}",
                             "T6": f"ratio >= {T6_MIN_RATIO} (warning only)"},
        "classification": {"rule_used": rule_used, "v1_literal": agr_v1, "v3_revised": agr_v3,
                           "v3_changes": RULE_V3_CHANGES if rule_used == "v3" else [], "summary": cls_summary},
        "market_unit": {"first_available": first_mu, "dist_days": dict(mu_dist), "k200_bar_100": k200_bar100},
        "calendar": {"days": len(cal), "first": str(pd.Timestamp(cal[0]).date()), "last": str(pd.Timestamp(cal[-1]).date())},
        "verdict": {"adopted": adopted, "text": verdict, "kojiro_pass": pk, "donchian_pass": pd_},
        **results,
    }
    core = {k: v for k, v in clean(out).items() if k not in ("generated_at_kst", "runtime_sec")}
    out["result_core_sha256"] = hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with open(os.path.join(HERE, "results.json"), "w") as fh:
        json.dump(clean(out), fh, ensure_ascii=False, indent=1, allow_nan=False)
    write_md(out)
    # 실행 대장(감사 지적 4): 실행마다 한 줄 추가. 결과 핵심 sha 는 생성 시각·실행 시간을 뺀 결과의 sha 라 재실행이 같으면 같다
    with open(RUNS_LOG, "a") as fh:
        fh.write("\t".join([out["generated_at_kst"], SCRIPT_VERSION, f"script={script_sha}",
                            f"result_core={out['result_core_sha256']}",
                            f"results_json={sha256_file(os.path.join(HERE, 'results.json'))}",
                            f"results_md={sha256_file(os.path.join(HERE, 'results.md'))}",
                            f"verdict={adopted}"]) + "\n")
    print(f"[s0] verdict: {verdict} · core sha {out['result_core_sha256'][:16]} · runtime {out['runtime_sec']}s", flush=True)


def decide(k, d):
    """§3.1 끝 문단: 둘 다 통과 → 연 수익÷|근사 MDD| 큰 쪽 · 하나만 → 그것 · 둘 다 탈락 → 닫는다."""
    pk, pd_ = k["judge"]["pass_T1_T5"], d["judge"]["pass_T1_T5"]
    if pk and pd_:
        a = "kojiro" if k["sleeve"]["ret_over_mdd"] >= d["sleeve"]["ret_over_mdd"] else "donchian"
        return a, f"둘 다 통과 → 연 수익÷|근사 MDD| 가 큰 {a}형 채택", pk, pd_
    if pk:
        return "kojiro", "kojiro형(1안)만 통과 → 1안 채택", pk, pd_
    if pd_:
        return "donchian", "donchian형(2안)만 통과 → 2안 채택", pk, pd_
    return None, "둘 다 탈락 → 전략을 만들지 않고 닫는다(§3.1)", pk, pd_


def build_ticker_cal(g, cmap, nav=None):
    g = g.sort_values("bas_dd")
    g = g[(g["open"] > 0) & (g["high"] > 0) & (g["low"] > 0) & (g["close"] > 0)]
    if len(g) < 2:
        return None
    ci = cmap(g["bas_dd"].values)
    d = build_ticker(g, ci)
    # 민감도 S7 용 순자산총액(없으면 NaN → f_nav=False)
    d["nav"] = (np.array([nav.get(pd.Timestamp(x), np.nan) for x in g["bas_dd"].values], dtype=float)
                if nav is not None else np.full(len(ci), np.nan))
    return d


_A61 = 2.0 / 61.0
_W60 = np.array([(1 - _A61) ** 59] + [_A61 * (1 - _A61) ** (59 - i) for i in range(1, 60)])  # 오래된 → 최근


def ema60_window(c):
    """민감도 S8(M13 라이브 쪽): 최근 60봉 창 안에서 첫 값으로 시작하는 EMA(span 60) — 라이브 donchian `_ema(closes[:60])`."""
    out = np.full(len(c), np.nan)
    if len(c) >= 60:
        out[59:] = np.convolve(c, _W60[::-1], mode="valid")
    return out


def build_ticker(g, ci):
    """종목 하나(open>0 인 봉만, 날짜순)의 지표 배열. ci = 069500 달력 인덱스."""
    d = {"ci": ci}
    o, h, l, c = (g[k].to_numpy(float) for k in ("open_adj", "high_adj", "low_adj", "close_adj"))
    d["o"], d["h"], d["l"], d["c"] = o, h, l, c
    d["craw"] = g["close"].to_numpy(float)
    d["tv"] = g["trade_value"].to_numpy(float)
    d["mc"] = g["mktcap"].to_numpy(float)
    cs = pd.Series(c)
    d["es"] = cs.ewm(span=5, adjust=False).mean().to_numpy()
    d["em"] = cs.ewm(span=20, adjust=False).mean().to_numpy()
    d["el"] = cs.ewm(span=40, adjust=False).mean().to_numpy()
    d["e60"] = cs.ewm(span=60, adjust=False).mean().to_numpy()
    d["e60w"] = ema60_window(c)
    prev_c = np.concatenate([[np.nan], c[:-1]])
    tr = np.nanmax(np.vstack([h - l, np.abs(h - prev_c), np.abs(l - prev_c)]), axis=0)
    d["atr20"] = pd.Series(tr).ewm(alpha=1 / 20, adjust=False).mean().to_numpy()
    tr_sma = np.where(np.isnan(prev_c), np.nan, tr)
    d["n14"] = pd.Series(tr_sma).rolling(14, min_periods=14).mean().to_numpy()
    tvs = pd.Series(d["tv"])
    d["tv20"] = tvs.rolling(20, min_periods=20).mean().to_numpy()
    d["tvprev20"] = tvs.shift(1).rolling(20, min_periods=20).mean().to_numpy()
    d["hi_prev20"] = pd.Series(h).shift(1).rolling(20, min_periods=20).max().to_numpy()
    d["stage"] = stages_of(d["es"], d["em"], d["el"])
    start = np.searchsorted(ci, ci - (QUAL_WIN - 1), side="left")
    d["qual60"] = (np.arange(len(ci)) - start + 1) == QUAL_WIN
    return d


# ════════════════════════════════════════════════════════════════════
# 8. results.md
# ════════════════════════════════════════════════════════════════════
def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def fmt(v, p=3, sign=True):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "—"
    return f"{v:+.{p}f}" if sign else f"{v:.{p}f}"


VLABELS = {
    "S0_v1_incl_alnum": "S0 v1 판정판(영숫자 코드 ETF 포함 — 지적 1 이전)",
    "S1_rep_select_on": "S1 대표 선택 켬(랏≥3, 예산 75만)",
    "S2_dedup_incl_m0": "S2 m=0 신호도 묶음 보유로(설계서 재현 방식, M20)",
    "S3_narrow_U1": "S3 §3.1 좁은 U1(시총·가격상한·품질 미적용, M3)",
    "S4_narrow_dedup_incl_m0": "S4 = S2+S3 (설계서 「지금 값」 방식)",
    "S5_prelisted_min_bars": "S5 보관소 시작 전 상장 종목 100봉 조건 완화(지적 3)",
    "S6_rule_v1": "S6 §8.2 v1 글자 그대로 규칙(지적 7)",
    "S7_net_asset": "S7 시총 대신 순자산총액(지적 8)",
    "S8_donchian_live_m12_m13": "S8 donchian M12 장중 돌파선 이탈·M13 60봉 창 EMA60(지적 2, kojiro 는 판정판 그대로)",
    "S9_exit_day_not_held": "S9 M8 반대 해석: 그날 청산된 거래는 그날 묶음 보유 아님(같은 종목 당일 재매수만 막음 — 교차계산 차이의 주원인)",
}

DESIGN_NOW = {  # 설계서 §8.3 「지금 값」(생존 편향 · 네이버 데이터 · 비교용)
    "kojiro": {"T1": "+0.506 [+0.193]", "T2": "−0.115", "T3": "+0.172 (10억 판)", "T4": "+0.153 (균등·10억 판)", "T5": "+11.1% · −6.4"},
    "donchian": {"T1": "+0.308 [+0.186]", "T2": "−0.081", "T3": "+0.141 (10억 판)", "T4": "+0.144 (균등·10억 판)", "T5": "+16.5% · −16.0"},
}


def write_md(o):
    L = []
    a = L.append
    kj, dc = o["rules"]["kojiro"], o["rules"]["donchian"]
    ox = lambda b: "O" if b else "X"
    a("# ETF 추세 전략 S0 재측정 결과 v2 (KRX ETF 5년 · 상장폐지 포함 · cycle391 감사 반영)")
    a("")
    a(f"- 생성 {o['generated_at_kst']} · 실행 {o['runtime_sec']}초 · 씨앗 {o['seed']} · 부트스트랩 {o['n_boot']}회 · 슬리브 {o['n_sleeve_runs']}회 · 스크립트 {o['script_version']}")
    a(f"- 결과 핵심 sha256(생성 시각·실행 시간 제외, 재실행이 같으면 같다): `{o['result_core_sha256']}` — 실행마다 `runs.log` 에 한 줄 추가")
    a(f"- 달력 {o['calendar']['first']}~{o['calendar']['last']} ({o['calendar']['days']}거래일) · 시장 유닛 첫 산출일 {o['market_unit']['first_available']} · "
      f"069500 의 100번째 봉 {o['market_unit']['k200_bar_100']}")
    a("- 명세·모호점 = `spec_extract.md`. 문턱은 설계서 §8.3 값 그대로(돌리기 전 고정, 이번에도 바꾸지 않았다).")
    a("- v1 → v2 판정판 변경은 하나: 유니버스를 **라이브가 닿는 6자리 숫자 코드**로 한정(감사 지적 1). v1 판정판은 민감도 S0 으로 그대로 보고한다.")
    a("")
    a("## 판정")
    a("")
    a(f"**{o['verdict']['text']}**")
    a("")
    a("| 문턱 | 기준 | kojiro형 (1안) | 통과 | donchian형 (2안) | 통과 | 설계서 「지금 값」 kojiro / donchian |")
    a("|---|---|---|---|---|---|---|")
    ks, ds = kj["stats"], dc["stats"]
    kl, dl = kj["sleeve"], dc["sleeve"]
    kjd, djd = kj["judge"], dc["judge"]

    def row(name, crit, kv, kp, dv, dp, now):
        a(f"| {name} | {crit} | {kv} | {ox(kp)} | {dv} | {ox(dp)} | {now} |")

    dn = DESIGN_NOW
    row("T1", "건당 R ≥ +0.15 ∧ 95% 하한 > 0",
        f"{fmt(ks['wR'])} [{fmt(ks['ci95'][0])}, {fmt(ks['ci95'][1])}] (n={ks['n']})", kjd["T1"],
        f"{fmt(ds['wR'])} [{fmt(ds['ci95'][0])}, {fmt(ds['ci95'][1])}] (n={ds['n']})", djd["T1"],
        f"{dn['kojiro']['T1']} / {dn['donchian']['T1']}")
    row("T2", "A(2021~22) ≥ −0.20", f"{fmt(ks['wR_A'])} (n={ks['n_A']})", kjd["T2"], f"{fmt(ds['wR_A'])} (n={ds['n_A']})", djd["T2"],
        f"{dn['kojiro']['T2']} / {dn['donchian']['T2']}")
    row("T3", "2025 제외 > 0", f"{fmt(ks['wR_ex2025'])} (n={ks['n_ex2025']})", kjd["T3"], f"{fmt(ds['wR_ex2025'])} (n={ds['n_ex2025']})", djd["T3"],
        f"{dn['kojiro']['T3']} / {dn['donchian']['T3']}")
    row("T4", "상위 1% 제외 > 0", f"{fmt(ks['wR_ex_top1pct'])} (상위 {ks['top1pct_k']}건 제외)", kjd["T4"],
        f"{fmt(ds['wR_ex_top1pct'])} (상위 {ds['top1pct_k']}건 제외)", djd["T4"], f"{dn['kojiro']['T4']} / {dn['donchian']['T4']}")
    row("T5", "연 수익 > 0 ∧ 근사 MDD ≥ −20%p",
        f"{fmt(kl['ann_mean'], 1)}%/년 · MDD {fmt(kl['mdd_median'], 1)}%p", kjd["T5"],
        f"{fmt(dl['ann_mean'], 1)}%/년 · MDD {fmt(dl['mdd_median'], 1)}%p", djd["T5"], f"{dn['kojiro']['T5']} / {dn['donchian']['T5']}")
    k6, d6 = kj["T6"], dc["T6"]
    row("T6 (경고)", "폐지 포함 ÷ 현재 상장분 ≥ 0.5",
        f"{fmt(k6['wR_all'])} ÷ {fmt(k6['wR_listed_only'])} = {fmt(k6['ratio'], 2, False)}", k6["ok"],
        f"{fmt(d6['wR_all'])} ÷ {fmt(d6['wR_listed_only'])} = {fmt(d6['ratio'], 2, False)}", d6["ok"], "— / —")
    a(f"| **T1~T5** | 전부 | | **{'통과' if kjd['pass_T1_T5'] else '탈락'}** | | **{'통과' if djd['pass_T1_T5'] else '탈락'}** | |")
    a("")
    a(f"- 연 수익 ÷ |근사 MDD|: kojiro형 {fmt(kl['ret_over_mdd'], 2, False)} · donchian형 {fmt(dl['ret_over_mdd'], 2, False)}")
    v = kj["variants"]
    a(f"- **kojiro형 T2 는 해석에 달려 있다(감사 지적 4)**: 판정판(M20, m=0 신호는 묶음 보유로 치지 않음) {fmt(ks['wR_A'])} → 탈락 · "
      f"S2(설계서 재현 방식) {fmt(v['S2_dedup_incl_m0']['stats']['wR_A'])} · S4(설계서 「지금 값」 방식) {fmt(v['S4_narrow_dedup_incl_m0']['stats']['wR_A'])}. "
      "문턱 −0.20 대비 판정판은 아래, S2·S4 는 위다.")
    sv = o["sensitivity_verdicts"]
    a("- 민감도 판들의 §3.1 결과: " + " · ".join(f"{k.split('_')[0]} {v_['adopted'] or '없음'}" for k, v_ in sv.items()))
    a("")
    a("## 상세 — 판정판 (U1 §2 전체 · 6자리 숫자 코드 · 20억 · 중복 제거 · 비용 · 계단형 가중 · 상장폐지 포함 · 대표 선택 끔)")
    a("")
    a("| 항목 | kojiro형 | donchian형 |")
    a("|---|---|---|")
    for p in ("A", "B", "H"):
        a(f"| 기간 {p} 건당 R [95%] | {fmt(ks['wR_'+p])} [{fmt(ks['ci95_'+p][0])}, {fmt(ks['ci95_'+p][1])}] (n={ks['n_'+p]}) | "
          f"{fmt(ds['wR_'+p])} [{fmt(ds['ci95_'+p][0])}, {fmt(ds['ci95_'+p][1])}] (n={ds['n_'+p]}) |")
    ka, da = kj["A_start"], dc["A_start"]
    a(f"| A 구간 실제 시작(가장 이른 신호: 필터 전 / §2 전체 · 첫 진입) | {ka['earliest_signal_any_filter']} / {ka['earliest_signal_full_universe']} · {ka['first_entry_judged']} | "
      f"{da['earliest_signal_any_filter']} / {da['earliest_signal_full_universe']} · {da['first_entry_judged']} |")
    yk = " · ".join(f"{y} {fmt(v_[0], 2)}({v_[1]})" for y, v_ in ks["wR_by_year"].items())
    yd = " · ".join(f"{y} {fmt(v_[0], 2)}({v_[1]})" for y, v_ in ds["wR_by_year"].items())
    a(f"| 연도별 건당 R(건수) | {yk} | {yd} |")
    mk = " · ".join(f"m={m} {fmt(v_[0], 2)}({v_[1]})" for m, v_ in ks["by_m"].items())
    md = " · ".join(f"m={m} {fmt(v_[0], 2)}({v_[1]})" for m, v_ in ds["by_m"].items())
    a(f"| m 상태별 R(건수) | {mk} | {md} |")
    a(f"| 승률 · 평균 이익/손실 · 손익비 | {ks['win_rate']*100:.0f}% · {fmt(ks['avg_win'],2)}/{fmt(ks['avg_loss'],2)} · {fmt(ks['payoff'],2,False)} | "
      f"{ds['win_rate']*100:.0f}% · {fmt(ds['avg_win'],2)}/{fmt(ds['avg_loss'],2)} · {fmt(ds['payoff'],2,False)} |")
    a(f"| 최대 R · 보유 중앙 | {fmt(ks['max_R'],2)} · {ks['hold_median']:.0f}봉 | {fmt(ds['max_R'],2)} · {ds['hold_median']:.0f}봉 |")
    a(f"| 청산 사유 | {ks['exit_reasons']} | {ds['exit_reasons']} |")
    a(f"| 거래 종목 수 · 폐지 종목 거래(건당 R) | {ks['n_tickers']} · {ks['n_delisted_ticker_trades']}({fmt(ks['wR_delisted_ticker_trades'],2)}) | "
      f"{ds['n_tickers']} · {ds['n_delisted_ticker_trades']}({fmt(ds['wR_delisted_ticker_trades'],2)}) |")
    a(f"| 분류 출처별 거래(db/rule) | {kj['trades_by_class_source']} | {dc['trades_by_class_source']} |")
    a(f"| 사이징 ATR/종가 중앙 · f 중앙 | {ks['size_atr_pct_median']*100:.2f}% · {ks['f_median']:.2f} | {ds['size_atr_pct_median']*100:.2f}% · {ds['f_median']:.2f} |")
    a(f"| 슬리브 A / B / H (%/년) | {fmt(kl['ann_A'],1)} / {fmt(kl['ann_B'],1)} / {fmt(kl['ann_H'],1)} | {fmt(dl['ann_A'],1)} / {fmt(dl['ann_B'],1)} / {fmt(dl['ann_H'],1)} |")
    a(f"| 슬리브 연 체결 A / B / H | {kl['tpy_A']:.0f} / {kl['tpy_B']:.0f} / {kl['tpy_H']:.0f} | {dl['tpy_A']:.0f} / {dl['tpy_B']:.0f} / {dl['tpy_H']:.0f} |")
    a(f"| 슬리브 연 수익 범위(40회) · 근사 MDD 최악/최선 | {fmt(kl['ann_min'],1)}~{fmt(kl['ann_max'],1)}% · {fmt(kl['mdd_worst'],1)}/{fmt(kl['mdd_best'],1)}%p | "
      f"{fmt(dl['ann_min'],1)}~{fmt(dl['ann_max'],1)}% · {fmt(dl['mdd_worst'],1)}/{fmt(dl['mdd_best'],1)}%p |")
    a(f"| 정수 랏 0주(예산 75만) 건수 · 뺀 건당 R | {ks['lot75_zero']} · {fmt(ks['wR_excl_lot75_zero'])} | {ds['lot75_zero']} · {fmt(ds['wR_excl_lot75_zero'])} |")
    a(f"| 신호 수: 필터 전 / §2 전체 / m>0 / 중복 제거 | {kj['signals_pre_universe_filters']} / {kj['signals_full_universe']} / {kj['signals_m_pos']} / {kj['dedup_m_pos']} | "
      f"{dc['signals_pre_universe_filters']} / {dc['signals_full_universe']} / {dc['signals_m_pos']} / {dc['dedup_m_pos']} |")
    a("")
    a("### 판정 정의 옆에 병기하는 값 (판정에 쓰지 않는다)")
    a("")
    a("| 항목 | kojiro형 | donchian형 |")
    a("|---|---|---|")
    kb, db_ = kj["block_ci"], dc["block_ci"]
    for lab, key in (("T1 95% — 진입일 묶음(판정 정의)", "full_day"), ("T1 95% — 월 묶음", "full_month"), ("T1 95% — 보유 겹침 구간 묶음", "full_overlap"),
                     ("A 95% — 진입일 묶음", "A_day"), ("A 95% — 월 묶음", "A_month"), ("A 95% — 보유 겹침 구간 묶음", "A_overlap")):
        a(f"| {lab} | [{fmt(kb[key][0])}, {fmt(kb[key][1])}] | [{fmt(db_[key][0])}, {fmt(db_[key][1])}] |")
    a(f"| 묶음 수 (진입일 / 월 / 겹침 구간) | {kb['n_clusters']['day']} / {kb['n_clusters']['month']} / {kb['n_clusters']['overlap']} | "
      f"{db_['n_clusters']['day']} / {db_['n_clusters']['month']} / {db_['n_clusters']['overlap']} |")
    a(f"| 일별 평가손 포함 MDD 중앙(최악) · 연 수익 ÷ \\|그 MDD\\| | {fmt(kl['mtm_mdd_median'],1)}({fmt(kl['mtm_mdd_worst'],1)})%p · {fmt(kl['ret_over_mtm_mdd'],2,False)} | "
      f"{fmt(dl['mtm_mdd_median'],1)}({fmt(dl['mtm_mdd_worst'],1)})%p · {fmt(dl['ret_over_mtm_mdd'],2,False)} |")
    ki, di = kj["integrated_sleeve"], dc["integrated_sleeve"]
    a(f"| 통합 슬리브(중복 제거+슬롯 함께) 무작위 40회: 연 수익 · 근사 MDD · 비 | {fmt(ki['rand']['ann_mean'],1)}% · {fmt(ki['rand']['mdd_median'],1)}%p · {fmt(ki['rand']['ret_over_mdd'],2,False)} | "
      f"{fmt(di['rand']['ann_mean'],1)}% · {fmt(di['rand']['mdd_median'],1)}%p · {fmt(di['rand']['ret_over_mdd'],2,False)} |")
    a(f"| 통합 슬리브 거래대금 순서 1회: 연 수익 · 근사 MDD · 비 | {fmt(ki['tv']['ann_mean'],1)}% · {fmt(ki['tv']['mdd_median'],1)}%p · {fmt(ki['tv']['ret_over_mdd'],2,False)} | "
      f"{fmt(di['tv']['ann_mean'],1)}% · {fmt(di['tv']['mdd_median'],1)}%p · {fmt(di['tv']['ret_over_mdd'],2,False)} |")
    a("")
    a("## 민감도 — 해석을 바꾼 판 (판정에 쓰지 않는다)")
    a("")
    a("| 판 | 규칙 | T1 R [95% 하한] (n) | T2 A | T3 ex2025 | T4 ex top1% | T5 연수익 · MDD | T1~T5 | 이 판의 §3.1 결과 |")
    a("|---|---|---|---|---|---|---|---|---|")
    for vn, lab in VLABELS.items():
        for rule in ("kojiro", "donchian"):
            v_ = o["rules"][rule]["variants"][vn]
            st_, sl_, j_ = v_["stats"], v_["sleeve"], v_["judge"]
            res = o["sensitivity_verdicts"][vn]["text"] if rule == "kojiro" else ""
            a(f"| {lab if rule == 'kojiro' else ''} | {rule} | {fmt(st_['wR'])} [{fmt(st_['ci95'][0])}] ({st_['n']}) {ox(j_['T1'])} | "
              f"{fmt(st_['wR_A'])} {ox(j_['T2'])} | {fmt(st_['wR_ex2025'])} {ox(j_['T3'])} | {fmt(st_['wR_ex_top1pct'])} {ox(j_['T4'])} | "
              f"{fmt(sl_['ann_mean'],1)}% · {fmt(sl_['mdd_median'],1)}%p {ox(j_['T5'])} (비 {fmt(sl_['ret_over_mdd'],2,False)}) | "
              f"{'통과' if j_['pass_T1_T5'] else '탈락'} | {res} |")
    a("- 각 판의 연 수익 ÷ |일별 평가 MDD| (kojiro / donchian): " + " · ".join(
        f"{vn.split('_')[0]} {fmt(o['rules']['kojiro']['variants'][vn]['sleeve'].get('ret_over_mtm_mdd'),2,False)} / "
        f"{fmt(o['rules']['donchian']['variants'][vn]['sleeve'].get('ret_over_mtm_mdd'),2,False)}" for vn in VLABELS))
    s0k, s0d = kj["variants"]["S0_v1_incl_alnum"], dc["variants"]["S0_v1_incl_alnum"]
    a(f"- S0 에 든 영숫자 코드 ETF 거래: kojiro {s0k['alnum_trades']}건(건당 {fmt(s0k['alnum_wR'],2)}) · donchian {s0d['alnum_trades']}건(건당 {fmt(s0d['alnum_wR'],2)})")
    a(f"- S1 에서 대표를 바꾼 건수: kojiro {kj['variants']['S1_rep_select_on']['n_substituted']} · donchian {dc['variants']['S1_rep_select_on']['n_substituted']}")
    a(f"- S5 가 더한 이른 거래: kojiro {kj['variants']['S5_prelisted_min_bars']['added_early']} · donchian {dc['variants']['S5_prelisted_min_bars']['added_early']}")
    a(f"- S6 거래 집합이 판정판과 같은가: kojiro {kj['variants']['S6_rule_v1']['same_trade_set_as_judged']} · donchian {dc['variants']['S6_rule_v1']['same_trade_set_as_judged']}")
    a(f"- S7 에서 바뀐 m>0 신호(순자산만 통과 / 시총만 통과): kojiro {kj['variants']['S7_net_asset']['signals_in_only_nav']} / {kj['variants']['S7_net_asset']['signals_in_only_mcap']} · "
      f"donchian {dc['variants']['S7_net_asset']['signals_in_only_nav']} / {dc['variants']['S7_net_asset']['signals_in_only_mcap']}")
    ke, de = kj["equal_weight_reference"], dc["equal_weight_reference"]
    a(f"- 균등(m=0 포함, S2 중복 제거) 건당 R: kojiro {fmt(ke['R_equal'])} (n={ke['n']}) · donchian {fmt(de['R_equal'])} (n={de['n']})")
    a(f"- 계단형이 거르는 거래(m=0)의 균등 R [95%]: kojiro {fmt(ke['R_m0'])} [{fmt(ke['ci95_m0_equal'][0])}, {fmt(ke['ci95_m0_equal'][1])}] (n={ke['n_m0']}) · "
      f"donchian {fmt(de['R_m0'])} [{fmt(de['ci95_m0_equal'][0])}, {fmt(de['ci95_m0_equal'][1])}] (n={de['n_m0']})")
    a("")
    a("## 2안(donchian형)이 검증한 묶음 (감사 지적 2)")
    a("")
    a("cycle378 §3.1 donchian 대리 규칙 **묶음 전체**다. 진입 규칙만 떼어 설계서 §3.3·§4·§5(1안 기준)의 청산·사이징과 합치면 측정되지 않은 조합이다.")
    a("- 신호(t): 종가 > 직전 20봉 고가 ∧ EMA60(전체 이력 ewm span 60) 상승 ∧ 종가 > EMA60 ∧ 거래대금 ≥ 1.5 × 직전 20봉 평균")
    a("- 집행(D 시가): 시가 ≥ 종가[t]×1.03 또는 시가 > 돌파선×1.04 이면 건너뜀. m=0 건너뜀")
    a("- N = TR 14봉 단순평균(Wilder ATR20 아님). R폭 = 사이징 ATR = 2N")
    a("- 청산: 손절 max(E−2N, 0.91E) · 1.5N 본전 · 트레일링 고가−1.8N(진입 N 고정) · 10일 저가 채널(D+1부터) · 돌파선 아래 종가(D+2부터, 종가 청산). 고가로 올린 선은 다음 봉부터")
    a("")
    a("## §8.2 상장폐지 ETF 분류 — 현재 상장분에서 과세 01 **표본 안** 일치율")
    a("")
    c = o["classification"]
    for key, lab in (("v1_literal", "v1 (설계서 §8.2 글자 그대로)"), ("v3_revised", "v3 (873종 오분류를 보고 고친 판 — 같은 873종에서 잰 값이라 표본 밖 성능이 아니다)")):
        g = c[key]
        a(f"- {lab}: 873종 정확도 {g['accuracy']*100:.1f}% · 정밀도 {g['precision']*100:.1f}% · 재현율 {g['recall']*100:.1f}% (TP {g['tp']} · FP {g['fp']} · FN {g['fn']} · TN {g['tn']})")
    a(f"- 사용한 규칙: **{c['rule_used']}** (M1: 과세 01 의 정밀도·재현율 둘 다 ≥ 90%. 「일치율」 을 정확도로 읽으면 v1 도 통과 — 그 판이 S6)")
    if c["v3_changes"]:
        a("- 수정 내역:")
        for x in c["v3_changes"]:
            a(f"  - {x}")
    a(f"- v3 남은 오분류: FP {[x[1] for x in c['v3_revised']['false_positives']]} · FN {[x[1] for x in c['v3_revised']['false_negatives']]}")
    s = c["summary"]
    a(f"- 분류 결과(판정판): 전체 {s['total_tickers']}종(현재 상장 {s['listed_at_end']} · 폐지 {s['delisted']}) · DB 필드 {s['db_rows']}종 · 규칙 {s['rule_classified']}종 → "
      f"U1 부류 {s['U1_class_total']}종 (DB {s['U1_class_db']} — 그중 폐지 {s['U1_class_db_delisted']} · 규칙·현재상장 {s['U1_class_rule_listed']} · 규칙·폐지 {s['U1_class_rule_delisted']})")
    a("")
    a("## 영숫자 코드 ETF (감사 지적 1)")
    a("")
    a(f"- 영숫자 코드 전체 {s['alnum_total']}종: DB 적재 {s['alnum_in_db']} · 현재 상장·DB 미적재 {s['alnum_listed_not_db']} · 상장폐지 {s['alnum_delisted']}")
    a(f"- 현재 상장·DB 미적재 {s['listed_not_db']}종 중 6자리 숫자 코드 {s['numeric_listed_not_db']}종")
    a(f"- v1 판정판 U1 부류 {s['U1_class_total_v1run']}종 → v2 {s['U1_class_total']}종 (영숫자 코드 {s['U1_alnum_excluded']}종 제외)")
    a("")
    a("## 상장폐지 ETF 가 결과에 들어왔나")
    a("")
    for rule in ("kojiro", "donchian"):
        lst = o["rules"][rule]["delisted_tickers_traded"]
        a(f"- {rule}: 판정판 거래에 든 상장폐지 ETF {len(lst)}종" + (" — " + ", ".join(f"{t}({n})" for t, n in lst) if lst else "") +
          f" · 시총·가격상한·일봉품질 필터 전(20억·1,000원·ATR≥1% 통과) 신호 중 상장폐지 종목 신호 {o['rules'][rule]['delisted_U1_class_signals_any_filter']}건")
    a(f"- 상장폐지 U1 부류 {s['delisted_U1_class_with_bars']}종 중 20일 거래대금 ≥ 20억에 닿은 적이 있는 것 {s['delisted_U1_class_ever_tv20_ge_20eok']}종 · "
      f"시총 ≥ 500억 {s['delisted_U1_class_ever_mcap_ge_500eok']}종 · 같은 날 둘 다 {s['delisted_U1_class_ever_both_same_day']}종")
    a(f"- 거래대금 상위: " + ", ".join(f"{x[0]} {x[1]}(최대 tv20 {x[2]}억 · 최대 시총 {x[3]}억)" for x in s["delisted_U1_class_top_tv20"]))
    a("")
    a("## 시장 유닛 분포 (m 산출 가능일)")
    a("")
    a(f"- {o['market_unit']['dist_days']}")
    a("")
    a("## 모호점 (spec_extract.md §10 요약)")
    a("")
    a("M1 일치율 = 정밀도·재현율 둘 다 · M2 순자산 → KRX 시총(라이브 판정 칸 hts_avls_eok 도 시가총액) · M3 U1 = §2.3 전체 · M4 투자유의 과거값 없음 · M5 과세유형 현재값 고정 · "
      "M6 집행가 = D 시가, 장중 붕괴 스킵 미적용 · M7 같은 봉 고가로 올린 손절선은 다음 봉부터 · M8 묶음 보유 = 슬롯 무관 채택 거래 · "
      "M9 상관 최소 60관측 · M10 슬롯은 청산일까지 점유 · M11 T5 = 40회 평균 연수익·중앙 MDD · M12 2안 돌파선 이탈은 종가 · "
      "M13 2안 EMA60 전체 이력 · M14 2안 채널 D+1·시간 D+2 부터 · M15 대표 대체는 자기 신호 있는 ETF 만 · M16 판정판 분수 사이징(0주 참고 보고) · "
      "M17 m 산출 불가 구간 진입 없음 · M18 폐지 중 보유는 마지막 종가 · M19 끝까지 열린 거래는 마지막 종가 · "
      "M20 m=0 신호는 매수되지 않으므로 판정판 중복 제거의 보유로 치지 않는다(설계서 재현은 m 무관 중복 제거 뒤 가중) · "
      "M21(v2) 유니버스 = 라이브가 닿는 6자리 숫자 코드 · §8.2 규칙은 DB 에 없는 상장폐지 ETF 에만 쓴다")
    a("")
    a("## sha256")
    a("")
    a(f"- 스크립트 `etf_s0_replay.py` ({o['script_version']}): `{o['script_sha256']}`")
    a("- v1 원본(감사 대상): `v1_orig/etf_s0_replay.py` `d57f0e35da2e9979897c64c639cc992d0ddb138195fb4cd29d45216b8b65f9a4`")
    for k, v_ in o["input_sha256"].items():
        a(f"- `{k}`: `{v_}`")
    a("")
    with open(os.path.join(HERE, "results.md"), "w") as fh:
        fh.write("\n".join(L))


if __name__ == "__main__":
    main()
