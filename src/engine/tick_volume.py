"""cycle227 — 실측 누적거래량(ACML_VOL) 관측 leaf 모듈.

`bull_flag_breakout`/`vcp_breakout` 의 매수 최종 관문이
`scanner.ticker_prices[t]["acml_vol"]` 을 읽는데, 그 키를 쓰는 코드가 전체
소스에 없어(P0-1) 두 전략이 구조적으로 매수 불가였다. WS payload `[13] ACML_VOL`
은 이미 실려 오고 있었으므로(`realtime/handler.py::_parse_acml_vol`), 시정의
첫 단계(Stage 0 = 배관 + 관측)가 그 값을 흘려 담는 이 모듈이다.

`ticker_prices` 에 직접 주입하지 않는 이유 — `donchian_swing` 이 같은 dict 에서
`daily_high = max(stck_hgpr, high_price, current_price, open_price)` 를 읽어
`ext_pct` 과열 가드를 계산한다. 키가 하나라도 늘면 **donchian 매수 행위가
바뀐다**. 그래서 관측값은 이 전용 leaf 모듈에만 살고(AST-1 가드가 `ticker_prices`
주입을 영구 차단), BFB/VCP 는 필요 시 이 모듈을 직접 조회한다.

날짜 키 자기 리셋 — `scheduler._reset_daily_state()` 훅에 의존하지 않는다.
이번 사이클은 `scheduler.py` diff 0 이 설계 목표(미커밋 cycle221 잔류와 커밋
분리)이고, `DailyEmitCap` 계열의 KST 자기 리셋 선례(`_max_sub_warn_date` 등)를
따른다. 외부 의존 최소 — DB/HTTP 없음, KST 시각만(`portfolio_risk.py` 순수 모듈
선례).

**sentinel 계약**: 미관측은 `None`. `0` 은 절대 미관측을 뜻하지 않는다 — `0` 이
바로 P0 결함이 유령 키를 항상 0 으로 읽던 그 값이라, "미수신"과 "진짜 거래량
0"을 다시 뭉개면 결함을 이식하는 것이다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_KST = timezone(timedelta(hours=9))

# 모듈 전역 상태 — ticker -> 관측 누적거래량 (last-write-wins).
_observed: dict[str, int] = {}
# 위 dict 가 담고 있는 값의 저장 날짜(KST, "YYYY-MM-DD"). None = 아직 아무 것도 없음.
_observed_day: str | None = None


def _today_kst() -> str:
    return datetime.now(_KST).strftime("%Y-%m-%d")


def record_acml_vol(ticker: str, value: int) -> None:
    """실측 누적거래량을 기록한다 (last-write-wins).

    - `value < 0` (handler sentinel `-1` 등) 은 **무시** — 기존 정상 관측을
      덮어써서 지우지 않는다(WS 재연결 직후 짧은 payload 한 건에 관측이 통째로
      사라지는 것을 방지).
    - `value == 0` 은 **유효한 관측**(아직 거래가 없는 종목)이라 그대로 기록한다.
    - 날짜(KST)가 바뀌면 이 호출이 이전 날짜 데이터를 전체 clear 한 뒤 기록한다
      (무한 성장 차단 + 크로스데이 오염 차단).
    """
    if value < 0:
        return
    global _observed_day
    today = _today_kst()
    if _observed_day != today:
        _observed_day = today
        _observed.clear()
    _observed[ticker] = value


def get_observed_acml_vol(ticker: str) -> int | None:
    """오늘(KST) 관측된 누적거래량. 미관측이거나 날짜가 바뀌었으면 `None`.

    읽기 전용 — 날짜 불일치를 발견해도 내부 상태를 clear 하지 않는다(그건
    `record_acml_vol` 의 책임). 어제 관측이 오늘 판정에 새어 들어가는 것만 막는다.
    """
    if _observed_day != _today_kst():
        return None
    return _observed.get(ticker)


def reset_for_test() -> None:
    """테스트 격리용 — 전체 초기화."""
    global _observed_day
    _observed.clear()
    _observed_day = None
