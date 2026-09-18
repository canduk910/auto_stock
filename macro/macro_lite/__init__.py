"""macro_lite — 매크로 4섹션(경기사이클+체제 / 장단기금리차 / 하이일드 스프레드 / 환율·원자재)
자체 완결형 FastAPI 패키지.

원 프로젝트(stock-manager)의 `services/macro_*`, `stock/macro_fetcher.py`,
`stock/oas_history_store.py`, `stock/cache.py` 에서 추출. 외부 프로젝트 모듈 import 0건.

사용:
    from macro_lite.router import router as macro_router
    app.include_router(macro_router)

주의: 패키지 최상위에서 APIRouter 객체를 `router` 이름으로 재노출하지 않는다 —
서브모듈 `macro_lite.router` 를 가려 `macro_lite.router.router` 접근이 깨지기 때문.
여기서 노출하는 `router` 는 서브모듈이다.

부작용 import 금지 — seed 자동 적재 없음 (`python -m macro_lite.seed` 명시 실행).
"""
from . import cache, cycle, events, fetcher, oas_history_store, regime, router, service

__all__ = [
    "router",
    "service",
    "cache",
    "fetcher",
    "events",
    "cycle",
    "regime",
    "oas_history_store",
]
