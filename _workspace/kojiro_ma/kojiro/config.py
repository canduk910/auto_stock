"""환경 설정 — AppKey/Secret은 절대 하드코딩하지 않고 .env에서 로드."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class KisConfig:
    app_key: str = os.getenv("KIS_APP_KEY", "")
    app_secret: str = os.getenv("KIS_APP_SECRET", "")
    cano: str = os.getenv("KIS_CANO", "")                    # 종합계좌 8자리
    acnt_prdt_cd: str = os.getenv("KIS_ACNT_PRDT_CD", "01")  # 계좌상품코드 2자리
    is_paper: bool = os.getenv("KIS_PAPER", "true").lower() == "true"  # 모의투자 여부
    token_cache: str = os.getenv("KIS_TOKEN_CACHE", ".kis_token.json")

    @property
    def base_url(self) -> str:
        return ("https://openapivts.koreainvestment.com:29443" if self.is_paper
                else "https://openapi.koreainvestment.com:9443")

    def tr_id(self, key: str) -> str:
        """실전/모의에 따라 tr_id 결정."""
        table = {
            "buy":     ("TTTC0012U", "VTTC0012U"),
            "sell":    ("TTTC0011U", "VTTC0011U"),
            "balance": ("TTTC8434R", "VTTC8434R"),
            "daily_chart": ("FHKST03010100", "FHKST03010100"),
            "holiday": ("CTCA0903R", "CTCA0903R"),  # 모의 미지원 → 실전키로만 호출
        }
        real, paper = table[key]
        return paper if self.is_paper else real


@dataclass
class StrategyConfig:
    """전략 파라미터 — 설계서 §2, §4, §5와 1:1 대응."""
    ema_short: int = 5
    ema_mid: int = 20
    ema_long: int = 40
    macd_signal: int = 9
    atr_period: int = 20
    slope_lookback: int = 1          # 기울기 판정 봉 수 (노이즈 억제 시 3)
    allow_early_entry: bool = False  # 스테이지6 조기 진입 on/off
    stop_atr: float = 2.0            # 손절 = 진입가 - 2*ATR
    trail_atr: float = 2.5           # 트레일링 = 최고종가 - 2.5*ATR
    pyramid_trigger_atr: float = 1.0 # +1ATR 수익 시 증축
    risk_pct: float = 0.01           # 1유닛 리스크 = 총자금의 1%
    max_units_per_stock: int = 2
    max_units_total: int = 10
    universe: list = field(default_factory=lambda: ["005930", "000660", "035420"])
