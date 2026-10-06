"""섹터 RS 배제 — 순수 층(사전 등록 ``_workspace/analysis/sector_rs_20261006/prereg.md``).

- 업종명 → 섹터 버킷(ETF 묶음에 맞춘 19개) · ETF 이름 → 버킷
- 하위 개수 규칙 ``n_bottom`` · RS 계산 ``rs_values`` · 하위 버킷 ``bottom_set``
- 분류 스냅숏 조회 ``Classifier`` (그날보다 **앞선** 스냅숏만 — 미래 정보 없음)
- 관문 ``SectorGate`` — 30년 계좌 함수의 「그날 신호 목록 섞기」 줄 뒤에 거르는 한 줄을 끼운다(원 파일 무수정)
- 거래 꺼내기 ``trade_rows`` · 빠진 거래 대조 ``match_dropped``
"""
from __future__ import annotations

import inspect
import math
import re
import textwrap
from bisect import bisect_left

import numpy as np
import pandas as pd

COST_RT = 0.0038
FRAC = 0.30
N_MIN_SECTORS = 5
MIN_MEMBERS = 3
RET_CAP = 0.35

# ═════════════════════════════════ 섹터 버킷 ═════════════════════════════════

BUCKETS = ("반도체", "IT하드웨어", "소프트웨어·인터넷", "미디어·통신", "헬스케어", "자동차", "기계·장비",
           "화학·에너지", "철강·소재", "건설", "은행", "증권", "보험", "기타금융", "필수소비재", "경기소비재",
           "운송", "유틸리티", "일반서비스")

# KRX 업종분류 현황(MDCSTAT03901) 의 IDX_IND_NM → 버킷. 공백·가운뎃점 차이는 _norm 으로 흡수한다.
LABEL_TO_BUCKET = {
    "반도체": "반도체",
    "전기·전자": "IT하드웨어", "IT부품": "IT하드웨어", "정보기기": "IT하드웨어", "통신장비": "IT하드웨어",
    "소프트웨어": "소프트웨어·인터넷", "컴퓨터서비스": "소프트웨어·인터넷", "인터넷": "소프트웨어·인터넷",
    "IT서비스": "소프트웨어·인터넷", "디지털컨텐츠": "소프트웨어·인터넷",
    "통신": "미디어·통신", "통신서비스": "미디어·통신", "방송서비스": "미디어·통신", "출판·매체복제": "미디어·통신",
    "오락·문화": "미디어·통신",
    "제약": "헬스케어", "의료·정밀기기": "헬스케어",
    "운송장비·부품": "자동차",
    "기계·장비": "기계·장비",
    "화학": "화학·에너지", "광업": "화학·에너지",
    "금속": "철강·소재", "비금속": "철강·소재", "종이·목재": "철강·소재",
    "건설": "건설", "부동산": "건설",
    "은행": "은행", "증권": "증권", "보험": "보험",
    "기타금융": "기타금융", "금융": "기타금융",
    "음식료·담배": "필수소비재", "농업,임업및어업": "필수소비재",
    "유통": "경기소비재", "섬유·의류": "경기소비재", "기타제조": "경기소비재",
    "운송·창고": "운송",
    "전기·가스": "유틸리티", "전기·가스·수도": "유틸리티",
    "일반서비스": "일반서비스", "기타": "일반서비스",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).replace("ㆍ", "·").replace("‧", "·")


_LABEL_N = {_norm(k): v for k, v in LABEL_TO_BUCKET.items()}


def label_bucket(label: str) -> "str | None":
    """업종명 → 버킷. 표에 없으면 None(= 미분류 → 통과)."""
    return _LABEL_N.get(_norm(label))


# ETF 이름 → 버킷(etf_trend 전용). 해외·인버스는 통과(None). 먼저 맞는 규칙이 이긴다.
ETF_PASS_WORDS = ("미국", "중국", "차이나", "글로벌", "일본", "인도", "베트남", "유럽", "S&P", "나스닥", "선진", "신흥",
                  "한중", "대만", "홍콩", "인버스", "선물인버스", "독일", "China", "MSCI World", "아시아")
ETF_RULES = (
    ("반도체", "반도체"), ("소프트웨어", "소프트웨어·인터넷"), ("인터넷", "소프트웨어·인터넷"), ("게임", "소프트웨어·인터넷"),
    ("미디어", "미디어·통신"), ("엔터", "미디어·통신"), ("컨텐츠", "미디어·통신"), ("콘텐츠", "미디어·통신"),
    ("커뮤니케이션", "미디어·통신"), ("통신", "미디어·통신"),
    ("헬스케어", "헬스케어"), ("바이오", "헬스케어"), ("제약", "헬스케어"),
    ("자동차", "자동차"), ("조선", "기계·장비"), ("중공업", "기계·장비"), ("기계", "기계·장비"),
    ("에너지화학", "화학·에너지"), ("화학", "화학·에너지"), ("2차전지", "화학·에너지"), ("배터리", "화학·에너지"),
    ("철강", "철강·소재"), ("소재", "철강·소재"), ("건설", "건설"),
    ("은행", "은행"), ("증권", "증권"), ("보험", "보험"), ("금융", "기타금융"),
    ("필수소비재", "필수소비재"), ("생활소비재", "필수소비재"), ("경기소비재", "경기소비재"), ("소비재", "경기소비재"),
    ("운송", "운송"), ("해운", "운송"), ("유틸리티", "유틸리티"),
)


def etf_bucket(name: str) -> "str | None":
    n = str(name or "")
    if any(w in n for w in ETF_PASS_WORDS):
        return None
    if re.search(r"(^|[\s\d])IT($|[\s+])", n) or "전기전자" in n:
        return "IT하드웨어"
    for kw, b in ETF_RULES:
        if kw in n:
            return b
    return None


# 보조판(ETF 실가격) — 버킷마다 대표 섹터 ETF 하나(현재 상장분 중 가장 먼저 상장한 KODEX/TIGER 섹터 ETF)
ETF_PROXY = {
    "반도체": "091160", "IT하드웨어": "139260", "소프트웨어·인터넷": "157490", "미디어·통신": "228810",
    "헬스케어": "143860", "자동차": "091180", "기계·장비": "102960", "화학·에너지": "117460", "철강·소재": "117680",
    "건설": "117700", "은행": "091170", "증권": "102970", "보험": "140700", "기타금융": "139270",
    "필수소비재": "227560", "경기소비재": "139290", "운송": "140710",
}


# ═════════════════════════════════ 하위 개수 · RS · 순위 ═════════════════════════════════

def n_bottom(n: int, frac: float = FRAC, n_min: int = N_MIN_SECTORS) -> int:
    """하위 개수 = floor(frac·n + 0.5)(반올림, .5 는 올림). 순위에 든 섹터가 n_min 미만이면 0."""
    if n < n_min:
        return 0
    return int(math.floor(frac * n + 0.5 + 1e-12))


IBD_W = ((63, 0.4), (126, 0.2), (189, 0.2), (252, 0.2))


def roc(level: np.ndarray, p: int, n: int) -> float:
    if p - n < 0:
        return float("nan")
    a, b = level[p - n], level[p]
    if not (np.isfinite(a) and np.isfinite(b)) or a <= 0:
        return float("nan")
    return float(b / a - 1.0)


def rs_value(level: np.ndarray, bench: np.ndarray, p: int, kind) -> float:
    """p 날 종가 기준 RS. kind = 정수 N(최근 N 영업일 수익 − 지수 수익) 또는 "ibd"(가중 합 − 지수 같은 가중 합)."""
    if kind == "ibd":
        s = 0.0
        for n, w in IBD_W:
            a, b = roc(level, p, n), roc(bench, p, n)
            if not (math.isfinite(a) and math.isfinite(b)):
                return float("nan")
            s += w * (a - b)
        return s
    a, b = roc(level, p, int(kind)), roc(bench, p, int(kind))
    return a - b if (math.isfinite(a) and math.isfinite(b)) else float("nan")


def bottom_set(rs: dict, frac: float = FRAC, n_min: int = N_MIN_SECTORS) -> frozenset:
    """{버킷: RS(NaN = 순위 밖)} → 하위 버킷 집합. 동순위 = BUCKETS 순서가 앞선 쪽이 더 아래."""
    pos = {b: i for i, b in enumerate(BUCKETS)}
    ok = [(v, pos.get(b, 99), b) for b, v in rs.items() if v is not None and math.isfinite(v)]
    k = n_bottom(len(ok), frac, n_min)
    ok.sort()
    return frozenset(b for _, _, b in ok[:k])


def excl_table(levels: "dict[str, np.ndarray]", members: "dict[str, np.ndarray]", bench: np.ndarray, kind,
               frac: float = FRAC, n_min: int = N_MIN_SECTORS, min_members: int = MIN_MEMBERS,
               start: "dict[str, int] | None" = None) -> list:
    """날마다(p = 색인) p 종가로 정한 하위 버킷 집합. levels·members·bench 는 같은 달력 길이.

    버킷은 p 날 구성 종목 수 ≥ min_members 이고 RS 가 정의될 때(그 버킷 지수 시작 ≥ 되돌아볼 날) 순위에 든다.
    start[b] = 버킷 지수의 시작 색인(그 전 수준은 NaN 으로 둬도 된다).
    """
    n = len(bench)
    out = []
    for p in range(n):
        rs = {}
        for b, lv in levels.items():
            if members[b][p] < min_members:
                continue
            if start is not None:
                need = 252 if kind == "ibd" else int(kind)
                if p - need < start.get(b, 0):
                    continue
            rs[b] = rs_value(lv, bench, p, kind)
        out.append(bottom_set(rs, frac, n_min))
    return out


# ═════════════════════════════════ 분류 스냅숏 ═════════════════════════════════

def common_of(ticker: str) -> str:
    """우선주 → 보통주 코드(앞 5자리 + "0"). 보통주면 그대로."""
    t = str(ticker)
    return t if t.endswith("0") else t[:5] + "0"


class Classifier:
    """월초 스냅숏 목록 [(스냅숏 날짜, {종목: 버킷})] — 조회일 d 보다 **앞선**(엄격히 작은) 마지막 스냅숏을 쓴다.

    backfill=True 면 첫 스냅숏보다 앞선 날에도 첫 스냅숏을 쓴다(민감도 판 · 분류에 한해 미래 정보).
    없는 종목은 보통주 코드로 한 번 더 찾고, 그래도 없으면 None(미분류 → 통과).
    """

    def __init__(self, snaps: "list[tuple[pd.Timestamp, dict]]", backfill: bool = False):
        snaps = sorted(snaps, key=lambda x: x[0])
        self.dates = [pd.Timestamp(d).value for d, _ in snaps]
        self.maps = [m for _, m in snaps]
        self.backfill = backfill

    def snap_index(self, d) -> int:
        i = bisect_left(self.dates, pd.Timestamp(d).value) - 1
        if i < 0 and self.backfill and self.maps:
            return 0
        return i

    def bucket(self, ticker: str, d) -> "str | None":
        i = self.snap_index(d)
        if i < 0:
            return None
        m = self.maps[i]
        b = m.get(ticker)
        if b is None:
            b = m.get(common_of(ticker))
        return b


# ═════════════════════════════════ 관문 ═════════════════════════════════

class SectorGate:
    """계좌 루프의 하루 신호 목록을 거른다. 꺼져 있으면 목록을 그대로 돌려준다(원판과 같은 결과).

    - excl_at(p) = p 날 종가로 정한 하위 버킷 집합(p = 신호일 d 보다 앞선 마지막 KRX 거래일 색인).
    - bucket_of(ticker, d) = 분류(그날 앞선 스냅숏).
    - 실행(씨앗 · 창)이 바뀌면(gd 가 줄거나 같아지면) 새 기록을 연다.
    """

    def __init__(self, cal_krx: pd.DatetimeIndex, excl: "list | None", classify, *, enabled: bool = True,
                 date_override=None, key=None):
        self.cal_ns = pd.DatetimeIndex(cal_krx).asi8
        self.excl = excl
        self.classify = classify
        self.enabled = enabled
        self.date_override = date_override       # gd → 날짜(루프에 cal 이 없을 때)
        self.key = key or (lambda o: o.ticker)   # 신호 → 종목코드
        self.reset()

    def reset(self):
        self.runs: list = []
        self._last_gd = None

    def _new_run(self):
        self.runs.append({"days": 0, "seen": 0, "dropped": [], "unclassified": 0, "classified": 0,
                          "trades_ref": None, "mr_fills": [], "cal": None,
                          "by_year": {}})

    def date_of(self, gd, loc) -> pd.Timestamp:
        if self.date_override is not None:
            return pd.Timestamp(self.date_override[gd])
        return pd.Timestamp(loc["cal"][gd])

    def p_of(self, d: pd.Timestamp) -> int:
        return int(np.searchsorted(self.cal_ns, d.value, side="left")) - 1

    def filter(self, gd: int, todays: list, loc: dict) -> list:
        if self._last_gd is None or gd <= self._last_gd:
            self._new_run()
        self._last_gd = gd
        run = self.runs[-1]
        run["days"] += 1
        if "trades" in loc and isinstance(loc["trades"], list):
            run["trades_ref"] = loc["trades"]
        if run.get("cal") is None and "cal" in loc:
            run["cal"] = loc["cal"]
        if not todays:
            return todays
        d = self.date_of(gd, loc)
        p = self.p_of(d)
        ex = self.excl[p] if (self.excl is not None and 0 <= p < len(self.excl)) else frozenset()
        keep = []
        for s in todays:
            t = self.key(s)
            b = self.classify(t, d)
            run["seen"] += 1
            yb = run["by_year"].setdefault(d.year, [0, 0, 0])
            yb[0] += 1
            if b is None:
                run["unclassified"] += 1
                yb[1] += 1
            else:
                run["classified"] += 1
            if self.enabled and b is not None and b in ex:
                run["dropped"].append((str(d.date()), str(t), b))
                yb[2] += 1
                continue
            keep.append(s)
        return keep if self.enabled else todays

    def mr_fill(self, cd):
        self.runs[-1]["mr_fills"].append(cd)


_SHUF = re.compile(r"^(?P<ind>[ \t]*)todays = list\((?P<src>[A-Za-z_][A-Za-z_0-9]*)\.get\(gd, \[\]\)\)[ \t]*\n"
                   r"(?P=ind)rng\.shuffle\(todays\)[ \t]*$", re.M)
_MR_FILL = re.compile(r"^(?P<ind>[ \t]*)pos\[cd\.tid\] = \(cd, q\)[ \t]*$", re.M)


def gate_source(src: str, mr: bool = False) -> "tuple[str, int]":
    """「목록 꺼내기 + 섞기」 두 줄 뒤에 거르는 한 줄을 넣는다(섞기 뒤 → 난수 흐름이 원판과 같다)."""
    def rep(m):
        return m.group(0) + f"\n{m.group('ind')}todays = _SRS_GATE.filter(gd, todays, locals())"
    new, n = _SHUF.subn(rep, src)
    if mr:
        new, k = _MR_FILL.subn(lambda m: m.group(0) + f"\n{m.group('ind')}_SRS_GATE.mr_fill(cd)", new)
        if k != 1:
            return new, -1
    return new, n


def gate_function(module, name: str, gate, mr: bool = False):
    """``module.name`` 을 관문 사본으로 바꾼다. 반환 = 원 함수. 넣은 줄이 정확히 1 이어야 한다."""
    orig = getattr(module, name)
    src = textwrap.dedent(inspect.getsource(orig))
    new, n = gate_source(src, mr=mr)
    if n != 1:
        raise RuntimeError(f"[sector_rs] {module.__name__}.{name}: 끼울 자리 {n}개(1 이어야 한다)")
    ns = module.__dict__
    ns["_SRS_GATE"] = gate
    loc: dict = {}
    exec(compile(new, f"<srs_gate {module.__name__}.{name}>", "exec"), ns, loc)
    setattr(module, name, loc[name])
    return orig


# ═════════════════════════════════ 거래 · 빠진 거래 ═════════════════════════════════

def trade_rows(run: dict, date_of_gd, mr_names=None) -> "list[tuple[str, str, float]]":
    """한 실행의 거래 → [(진입일, 종목, 순수익 = 청산가/진입가 − 1 − 0.38%)]. 청산가 없는 랏은 뺀다."""
    out = []
    if run.get("mr_fills"):
        for cd in run["mr_fills"]:
            out.append((str(pd.Timestamp(date_of_gd(cd.e_gd)).date()), str(mr_names[cd.tid]),
                        float(cd.X / cd.E - 1.0 - COST_RT)))
        return out
    for ps in run.get("trades_ref") or []:
        px = getattr(ps, "exit_px", None)
        E = getattr(ps, "E", None)
        if E is None:
            E = ps.s.E
        if px is None or not (E and E > 0):
            continue
        out.append((str(pd.Timestamp(date_of_gd(ps.s.gd)).date()), str(ps.s.ticker), float(px / E - 1.0 - COST_RT)))
    return out


def match_dropped(base_trades: list, dropped: list) -> list:
    """원판 거래 중 관문 판에서 빠진 (날짜, 종목) 신호와 같은 것들의 순수익."""
    keys = {(d, t) for d, t, _ in dropped}
    return [r for d, t, r in base_trades if (d, t) in keys]


def month_clusters(dates: "list[str]") -> np.ndarray:
    m = np.array([d[:7] for d in dates])
    _, inv = np.unique(m, return_inverse=True)
    return inv
