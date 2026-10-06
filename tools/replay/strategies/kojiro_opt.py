"""kojiro 효율화(2026-10-05) — 전수 점검 전략 층(``kojiro.py``) 위에 얹는 탐색 축.

사전 등록 = ``_workspace/analysis/strategy_opt_20261005/kojiro/prereg.frozen.md`` §2·§3.

- 체결가 보정(``slip_sig``): E = D 시가 × (1 + slip). 갭 판정은 원래 시가로 이미 끝났다(신호 단계).
- 시간 청산(``OptPos``): 진입일 = 1봉, (1 + time_n)번째 봉 시가에 ``TIME_EXIT``. 운영 시가 청산
  (받침·바닥·스테이지3·샹들리에)이 먼저 걸리면 그것. 하한가 잠김이면 다음 날로 미룬다(전수 점검과 같다).
- 시장 유닛 사용법(``mu_keep``): ``cur`` = m>0 전부 · ``only1`` = m=1 날만 · ``no075`` = m=0.75 날 빼기.
- 순위(``top_k``): 같은 진입일 신호 중 운영 점수 상위 k 개만.
- 모집단(``population_memo``): 전수 점검 ``population`` 과 같은 규칙(종목마다 앞 거래가 끝난 뒤에만 다음
  진입 · m ≤ 0 진입 없음)이고, 경로를 (종목, 진입 봉, 청산 설정, 끝 날)로 기억해 192조합에서 다시 쓴다.
  경로는 신선도·밴드와 무관하다(쓰는 것이 ATR·스테이지·봉뿐이다).
"""
from __future__ import annotations

import dataclasses

from replay.strategies import kojiro as KJ

MU_RULES = ("cur", "only1", "no075")


def slip_sig(s: KJ.Sig, slip: float) -> KJ.Sig:
    if not slip:
        return s
    return dataclasses.replace(s, E=s.E * (1.0 + slip), E_raw=s.E_raw * (1.0 + slip))


def mu_keep(m: float, rule: str) -> bool:
    if m <= 0:
        return False
    if rule == "cur":
        return True
    if rule == "only1":
        return m >= 1.0
    if rule == "no075":
        return m != 0.75
    raise ValueError(rule)


def top_k(sigs: "list[KJ.Sig]", k: "int | None") -> "list[KJ.Sig]":
    if k is None:
        return list(sigs)
    by: dict = {}
    for s in sigs:
        by.setdefault(s.gd, []).append(s)
    out = []
    for g in sorted(by):
        out.extend(sorted(by[g], key=lambda s: (-s.score, s.ticker))[:k])
    return out


def select(sigs, mu_rule: str, k: "int | None") -> "list[KJ.Sig]":
    return top_k([s for s in sigs if mu_keep(s.m, mu_rule)], k)


class OptPos(KJ.KJPos):
    def __init__(self, sig, b, f, qty, p, *, mode="color", locks=True, time_n: "int | None" = None):
        super().__init__(sig, b, f, qty, p, mode=mode, locks=locks)
        self.time_n = time_n

    def open_phase(self, ti: int, gd: int) -> bool:
        if self.b["notrade"][ti]:
            return False
        if super().open_phase(ti, gd):
            return True
        if self.time_n is not None and ti - self.s.ti >= self.time_n and self.exit_reason is None:
            if self._locked(ti):
                self.locked_days += 1
                return False
            self._exit(self.b["o"][ti], "TIME_EXIT", gd, "open")
            return True
        return False


def run_path(sig, b, f, p, end_gd: int, mode: str = "color", time_n: "int | None" = None) -> OptPos:
    """전수 점검 ``KJ.run_path`` 와 같은 걷기(1주 · 예산 무관), 포지션만 ``OptPos``."""
    ps = OptPos(sig, b, f, 1, p, mode=mode, time_n=time_n)
    if ps.intraday_phase(sig.ti, sig.gd, True):
        return ps
    for t in range(sig.ti + 1, len(b["c"])):
        gd = int(b["di"][t])
        if gd > end_gd:
            break
        if ps.open_phase(t, gd) or ps.intraday_phase(t, gd, False):
            return ps
    ps._exit(ps.last_px, "END", None)
    return ps


@dataclasses.dataclass(frozen=True)
class ExitCfg:
    be: float = 1.5
    trail: float = 2.5
    time_n: "int | None" = None

    def params(self, p: dict) -> dict:
        return {**p, "breakeven_promote_atr": self.be, "trail_atr": self.trail}


class PathMemo:
    def __init__(self, bars: dict, feats: dict, p: dict):
        self.bars, self.feats, self.p = bars, feats, p
        self.memo: dict = {}

    def get(self, s: KJ.Sig, cfg: ExitCfg, end_gd: int, slip: float, mode: str = "color") -> OptPos:
        key = (s.ticker, s.ti, cfg, end_gd, slip, mode)
        ps = self.memo.get(key)
        if ps is None:
            ps = run_path(slip_sig(s, slip), self.bars[s.ticker], self.feats[s.ticker], cfg.params(self.p),
                          end_gd, mode, cfg.time_n)
            self.memo[key] = ps
        return ps


def population_memo(sigs, memo: PathMemo, cfg: ExitCfg, start_gd: int, end_gd: int, slip: float,
                    mode: str = "color") -> "list[OptPos]":
    out, busy = [], {}
    for s in sorted(sigs, key=lambda s: (s.gd, s.ticker)):
        if s.gd < start_gd or s.gd > end_gd or s.m <= 0:
            continue
        if busy.get(s.ticker, -1) >= s.gd:
            continue
        ps = memo.get(s, cfg, end_gd, slip, mode)
        busy[s.ticker] = ps.exit_gd if ps.exit_gd is not None else 10 ** 9
        out.append(ps)
    return out
