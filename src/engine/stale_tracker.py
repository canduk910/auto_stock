"""Stale 추적 + force_retry + silent_inactive + universe guard + ccnl cache 통합 상태.

사이클 48 (2026-05-22, refactor-review 카드 #2) — scheduler.py 에 산재된 stale 관련
7 dict/set 필드를 단일 데이터클래스로 통합.

배경:
- 사이클 17 이전 `_stale_retry_count`
- 사이클 24 `_silent_inactive_first_seen` + `_silent_inactive_recovery_count`
- 사이클 28 `_stale_last_resubscribe_at`
- 사이클 29-R1 `_stale_force_retry_history`
- 사이클 32 R4 `_universe_excluded_today`
- 사이클 37 `_last_ccnl_cache`
- 사이클 45 TTL evict 보강

분산 7 필드 → 통합 1 데이터클래스. 관계 명시 + reset 누락 위험 차단 + 사이클 49
scheduler 분해 사전 준비.

호환 layer:
- `TradingScheduler` 의 7 property 가 본 데이터클래스 필드 직접 노출 (`is` 동일성 보장).
- 외부 코드 (test 등) 의 `scheduler._stale_*` 직접 접근도 정상 동작.

안전 가드:
- `reset_daily()` 가 7 필드 일괄 clear — `_reset_daily_state` 동행 위임.
- 사이클 45 TTL evict 정책 보존 — 본 데이터클래스는 lookup/저장만, evict 로직은 scheduler 헬퍼.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StaleTrackerState:
    """Stale 추적 + force_retry + silent_inactive + universe guard + ccnl cache 통합 상태.

    사이클 48 (2026-05-22) — refactor-review 카드 #2.

    7 필드 모두 영업일 단위 reset (`_reset_daily_state` 동행 위임). 사이클 추가 시 신규
    필드 누락 사고 차단.

    Attributes:
        retry_count: 종목별 stale 사이클 카운터 (사이클 17 이전).
            fresh 회복 시 자동 clear / `_check_and_resubscribe_stale` 매 호출 ++.
        last_resubscribe_at: 종목별 마지막 강제 재구독 시각 (사이클 28).
            진단 로그 `[stale_watcher_detail]` 의 `@HH:MM:SS` 필드 출처.
        force_retry_history: 종목별 60분 sliding window force_retry 시각 (사이클 29-R1).
            `STALE_FORCE_RETRY_HOURLY_CAP=12` 비교 + 사이클 45 evict 보강.
        silent_inactive_first_seen: 세션별 silent inactive 첫 감지 시각 (사이클 24).
            5분 지속 임계 비교용. label 단위 (메인=main / 보조=DB 라벨).
        silent_inactive_recovery_count: 세션별 시간당 reconnect 시각 list (사이클 24).
            시간당 2회 cap (LMS 위험 차단).
        universe_excluded_today: 일일 universe 제외 종목 (사이클 32 R4).
            stale > 5 + 거래량 빈약 자동 제외. 영업일 단위 reset (영구 블랙리스트 금지).
        last_ccnl_cache: 종목별 KIS 최근 체결 캐시 (사이클 37).
            TTL 5분 + 사이클 45 자동 evict 보강. UI [tickers_detail] 노출용.
    """
    retry_count: dict[str, int] = field(default_factory=dict)
    last_resubscribe_at: dict[str, datetime] = field(default_factory=dict)
    force_retry_history: dict[str, list[datetime]] = field(default_factory=dict)
    silent_inactive_first_seen: dict[str, datetime] = field(default_factory=dict)
    silent_inactive_recovery_count: dict[str, list[float]] = field(default_factory=dict)
    universe_excluded_today: set[str] = field(default_factory=set)
    last_ccnl_cache: dict[str, dict] = field(default_factory=dict)

    def reset_daily(self) -> None:
        """매일 정산 후 7 필드 일괄 clear — `_reset_daily_state` 가 위임 호출.

        영업일 단위 reset 정책 보존:
        - retry_count: 사이클 17 이전 부터 매일 0 초기화
        - last_resubscribe_at: 사이클 28 부터 G5 cleanup 동행
        - force_retry_history: 사이클 29-R1 부터 매일 clear
        - silent_inactive_*: 사이클 24 부터 매일 clear (세션 reconnect cap 리셋)
        - universe_excluded_today: 사이클 32 R4 — 영구 블랙리스트 금지 (다음 영업일 재진입)
        - last_ccnl_cache: 사이클 37 부터 daily clear + 사이클 45 TTL evict 이중 안전망
        """
        self.retry_count.clear()
        self.last_resubscribe_at.clear()
        self.force_retry_history.clear()
        self.silent_inactive_first_seen.clear()
        self.silent_inactive_recovery_count.clear()
        self.universe_excluded_today.clear()
        self.last_ccnl_cache.clear()
