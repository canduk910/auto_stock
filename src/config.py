"""환경 설정 모듈 - 실전/모의 환경 분리, 인증 정보 관리.

.env에서 KIS_ENV 값에 따라 실전(_REAL) 또는 모의(_VTS) 인증 정보를 선택한다.
"""

import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import computed_field

load_dotenv()

# KIS_ENV에 따라 적절한 인증 정보를 KIS_APP_KEY 등으로 매핑
_env = os.getenv("KIS_ENV", "vts")
_suffix = "_REAL" if _env == "real" else "_VTS"

for key in ("KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "KIS_ACCOUNT_PRODUCT", "KIS_HTS_ID"):
    env_val = os.getenv(f"{key}{_suffix}") or os.getenv(key)
    if env_val:
        os.environ[key] = env_val


class Settings(BaseSettings):
    # KIS OpenAPI 인증 (KIS_ENV에 따라 _REAL 또는 _VTS에서 자동 매핑)
    kis_app_key: str
    kis_app_secret: str
    kis_account_no: str
    kis_account_product: str = "01"
    kis_hts_id: str = ""  # 실전 체결통보(H0STCNI0) 구독 시 필요

    # 환경: "vts"(모의) 또는 "real"(실전)
    kis_env: str = "vts"

    # Supabase
    supabase_url: str
    supabase_key: str

    # RDS(PostgreSQL) — Supabase→RDS 이전 단계 0 (asyncpg 인프라, 사이클 M0)
    # supabase_url/supabase_key 와 병존(삭제 금지) — pg.py 는 아직 어느 db 모듈도 미사용
    database_url: str = ""

    # 서버
    host: str = "0.0.0.0"
    port: int = 8000
    auto_start: bool = False  # True: 서버 기동 시 자동 매매 시작

    # cycle243 — API 인증(X-API-Key). 미설정이면 **fail-closed**(/health 를 뺀 전 경로 401)
    # + 기동 시 `[api_auth_key_missing]` CRITICAL. fail-open 은 "키가 없으면 인증이 조용히
    # 사라진다" = 이 사이클이 고치려는 결함의 재현이라 채택하지 않는다.
    # 생성: python3 -c "import secrets;print(secrets.token_urlsafe(32))"
    api_auth_key: str = ""
    # 교차 출처 허용 목록(CSV). 기본 빈 문자열 = same-origin 전용.
    # CORS `allow_origins` 와 상태변경 Origin 검사가 이 값 하나를 공유한다. dev 예:
    # http://localhost:3000
    api_allowed_origins: str = ""

    # cycle249 — 리포터 스코프 키. Basic Auth 사용자 `reporter` 에게만 nginx
    # `map $remote_user` 가 이 값을 주입한다(운영 키와 다른 값). 허용 범위는
    # GET/HEAD 전체 + `POST /api/log-reports/{date}/external` 단 한 경로뿐이다
    # (20:20 KST 클라우드 루틴 — 로그 안 외부 문자열에 의한 prompt injection 이
    # 매매 조작으로 승격되지 않도록 쓰기 표면을 구조적으로 좁힌다).
    # 기본 빈 문자열 = 리포터 역할 **비활성**(어떤 요청도 리포터로 통과하지 못한다 —
    # `authorize()` 가 빈 리포터 키를 비교 자체를 하지 않는다, compare_digest("","")
    # True 함정 방지).
    api_reporter_key: str = ""

    # OpenAI 파라미터 추천
    openai_api_key: str = ""
    openai_recommend_model: str = "gpt-5.6-luna"

    # cycle274 — VB·LTV 매수 신호 LLM 평가 게이트(shadow) 전용 모델. 20:00 자문
    # 모델(openai_recommend_model)과 분리 — 한쪽을 더 싼 모델로 옮기고 싶을 때
    # 다른 쪽이 딸려가면 안 된다(자문 §6.3). `openai_api_key` 는 재사용한다.
    openai_buy_gate_model: str = "gpt-5.6-luna"

    # 외부 백테스트 서버 (MCP) — Phase 1
    # 운영 EC2 → AWS EC2 backtest 서버. KIS_MCP_ENABLED=true 일 때만 호출.
    kis_mcp_url: str = "http://43.202.187.5:3846/mcp"
    kis_mcp_enabled: bool = False
    backtest_timeout_secs: int = 300

    # 매크로 레짐 — 우리 `macro` 컨테이너 (`macro_lite`, 인증 없음)
    # DKSTOCK_REGIME_ENABLED=true 일 때만 _boot 매크로 fetch + 레짐 관찰 활성.
    # false (기본) 면 외부 호출 0건 (graceful degrade). 레짐은 매수를 차단하지 않는다.
    # 🔴 토글 키 이름은 유지한다 — 운영 DB `system_config.dkstock_regime_enabled` 행과 짝이다.
    macro_api_url: str = "http://macro:8000"
    # macro-cycle 은 지표를 다 모으는 첫 호출이 오래 걸린다. 캐시가 차면 3초대다.
    # 🔴 이 값은 상한이지 목표가 아니다 — 한 번의 콜드 호출이 이 상한을 넘을 수 있고,
    #    그때는 00:05 KST prewarm(`tools/ops/macro_prewarm.sh`)이 채운 다음 날 값으로 복구된다.
    #    상한을 실측 최악값까지 올리면 그만큼 부팅·토글 응답이 길어지므로 올리지 않는다.
    macro_api_read_timeout_secs: float = 90.0
    # 🔴 부팅 경로는 따로 조인다. `boot_manager.boot` 이 이 fetch 를 인라인으로 기다리고
    #    그 앞뒤로 자금 배분·포지션 복구가 이어지므로, 여기서 오래 붙잡으면 재시작 직후
    #    시세가 안 들어오는 창(tick blind)이 그만큼 길어진다. 레짐은 관찰 지표라
    #    부팅을 붙잡을 값어치가 없다 — 못 받으면 그날은 empty 로 간다.
    macro_api_boot_timeout_secs: float = 25.0
    dkstock_regime_enabled: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @computed_field
    @property
    def kis_base_url(self) -> str:
        if self.kis_env == "real":
            return "https://openapi.koreainvestment.com:9443"
        return "https://openapivts.koreainvestment.com:29443"

    @computed_field
    @property
    def kis_ws_url(self) -> str:
        if self.kis_env == "real":
            return "ws://ops.koreainvestment.com:21000"
        return "ws://ops.koreainvestment.com:31000"

    @computed_field
    @property
    def is_production(self) -> bool:
        return self.kis_env == "real"

    def get_tr_id(self, base_tr_id: str) -> str:
        """모의투자 환경에서 TR_ID 접두사를 변환한다.

        실전: TTTC0802U -> TTTC0802U (그대로)
        모의: TTTC0802U -> VTTC0802U (T->V)
        """
        if self.is_production:
            return base_tr_id
        return "V" + base_tr_id[1:]


settings = Settings()
