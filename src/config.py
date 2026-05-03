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

    # 서버
    host: str = "0.0.0.0"
    port: int = 8000
    auto_start: bool = False  # True: 서버 기동 시 자동 매매 시작

    # OpenAI 파라미터 추천
    openai_api_key: str = ""
    openai_recommend_model: str = "gpt-5.4"

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
