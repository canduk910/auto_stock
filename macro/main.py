"""macro-api — macro_lite FastAPI 진입점 (cycle303, 매매 이미지와 완전 분리된 독립 컨테이너).

`macro_lite/` 는 stock-manager 에서 무수정 vendor 한 패키지다(`README.md` 참조). 이 파일은
그 패키지의 라우터를 얹는 통합 코드로, 이 프로젝트(auto_stock) 전용이며 vendor 대상이 아니다.

인증: `AUTH_DEPENDENCY` 를 macro_lite/router.py 에서 `None` **그대로** 둔다. 이유 —
이 프로세스는 auto_stock 의 `ApiAuthMiddleware`(`src/middleware/`, X-API-Key fail-closed)를
갖지 않고, compose 도 이 컨테이너의 포트를 호스트에 게시하지 않는다(`docker-compose.prod.yml`
macro 서비스에 `ports:` 없음). 유일한 진입로는 nginx(frontend 컨테이너)의
`location /api/macro/` 뿐이고, 그 앞단이 이미 Basic Auth 로 잠겨 있다 — 이중 인증 대신
nginx 한 겹에 위임한다(원본 패키지의 설계 의도와 동일: "None 이면 인증 없이 공개" 는
"보호는 앞단이 한다" 는 전제 위에서만 안전하다).

`docs_url/redoc_url/openapi_url` 은 모두 끈다 — 내부 전용 API 라 공개 문서 UI 가 필요 없다.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from macro_lite.router import router as macro_router

from sp500 import get_sp500

app = FastAPI(title="macro-api", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(macro_router)  # prefix "/api/macro" 는 라우터 내장


@app.get("/api/macro/sp500")
async def sp500():
    """S&P500 주간 종가 — 금리차·하이일드 차트에 겹쳐 그릴 붉은 선의 원천(cycle310).

    `macro_lite/` 밖(`sp500.py`)에 두어 vendor 재이식에 휩쓸리지 않게 한다.
    yfinance 호출이 동기 블로킹이라 스레드풀로 내보낸다 — 이벤트 루프를 잡으면
    같은 프로세스의 다른 매크로 요청이 함께 멈춘다.
    """
    return await run_in_threadpool(get_sp500)


@app.get("/health")
def health():
    """compose healthcheck / 운영 진단용. macro_router 밖(인증·prefix 무관 고정 경로)."""
    return {"status": "ok"}
