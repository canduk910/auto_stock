"""한국투자증권 Open API 클라이언트 (REST).

프로젝트 지침 준수 사항:
- 토큰 24h 캐시 재사용 (접근토큰발급(P))
- POST body 키는 대문자, 수량/단가는 String
- 주문 등 POST 요청에 Hashkey 헤더 첨부
- rt_cd != "0" → msg_cd/msg1 로그
- 초당 호출 제한 대비 최소 호출 간격 유지
"""
import json
import logging
import time
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger("kis")

_MIN_INTERVAL = 0.06  # 초당 제한 대비 (실전 20건/s, 모의 2건/s → 모의는 0.5 권장)


class KisClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self._token: str | None = None
        self._token_expire: float = 0.0
        self._last_call: float = 0.0

    # ---------- 공통 ----------
    def _throttle(self):
        wait = _MIN_INTERVAL - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _headers(self, tr_id: str, hashkey: str | None = None) -> dict:
        h = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token}",
            "appkey": self.cfg.app_key,
            "appsecret": self.cfg.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if hashkey:
            h["hashkey"] = hashkey
        return h

    def _check(self, res: requests.Response) -> dict:
        res.raise_for_status()
        data = res.json()
        if data.get("rt_cd", "0") != "0":
            logger.error("KIS 오류 msg_cd=%s msg1=%s", data.get("msg_cd"), data.get("msg1"))
            raise KisApiError(data.get("msg_cd", ""), data.get("msg1", ""))
        return data

    # ---------- 인증 ----------
    @property
    def token(self) -> str:
        if self._token and time.time() < self._token_expire - 600:
            return self._token
        cache = Path(self.cfg.token_cache)
        if cache.exists():
            saved = json.loads(cache.read_text())
            if time.time() < saved.get("expire_at", 0) - 600:
                self._token = saved["access_token"]
                self._token_expire = saved["expire_at"]
                return self._token
        return self._issue_token()

    def _issue_token(self) -> str:
        self._throttle()
        res = requests.post(
            f"{self.cfg.base_url}/oauth2/tokenP",
            json={"grant_type": "client_credentials",
                  "appkey": self.cfg.app_key, "appsecret": self.cfg.app_secret},
            timeout=10,
        )
        res.raise_for_status()
        data = res.json()
        self._token = data["access_token"]
        self._token_expire = time.time() + int(data.get("expires_in", 86400))
        Path(self.cfg.token_cache).write_text(json.dumps(
            {"access_token": self._token, "expire_at": self._token_expire}))
        logger.info("토큰 신규 발급 완료")
        return self._token

    def hashkey(self, body: dict) -> str:
        self._throttle()
        res = requests.post(
            f"{self.cfg.base_url}/uapi/hashkey",
            headers={"content-type": "application/json; charset=utf-8",
                     "appkey": self.cfg.app_key, "appsecret": self.cfg.app_secret},
            json=body, timeout=10,
        )
        res.raise_for_status()
        return res.json()["HASH"]

    # ---------- 시세 ----------
    def daily_chart(self, code: str, start: str, end: str) -> pd.DataFrame:
        """국내주식기간별시세 (일봉, 수정주가). start/end: YYYYMMDD, 최대 100봉."""
        self._throttle()
        res = requests.get(
            f"{self.cfg.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            headers=self._headers(self.cfg.tr_id("daily_chart")),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": start,
                "FID_INPUT_DATE_2": end,
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",   # 0: 수정주가
            }, timeout=10,
        )
        data = self._check(res)
        rows = [r for r in data.get("output2", []) if r.get("stck_bsop_date")]
        df = pd.DataFrame([{
            "date": r["stck_bsop_date"],
            "open": float(r["stck_oprc"]),
            "high": float(r["stck_hgpr"]),
            "low": float(r["stck_lwpr"]),
            "close": float(r["stck_clpr"]),
            "volume": int(r["acml_vol"]),
        } for r in rows])
        return df.sort_values("date").set_index("date")

    def is_holiday(self, yyyymmdd: str) -> bool:
        """국내휴장일조회 — 모의투자 미지원이므로 모의 환경에선 주말만 체크."""
        if self.cfg.is_paper:
            import datetime as dt
            return dt.datetime.strptime(yyyymmdd, "%Y%m%d").weekday() >= 5
        self._throttle()
        res = requests.get(
            f"{self.cfg.base_url}/uapi/domestic-stock/v1/quotations/chk-holiday",
            headers=self._headers(self.cfg.tr_id("holiday")),
            params={"BASS_DT": yyyymmdd, "CTX_AREA_NK": "", "CTX_AREA_FK": ""},
            timeout=10,
        )
        data = self._check(res)
        rows = data.get("output", [])
        return not (rows and rows[0].get("opnd_yn") == "Y")

    # ---------- 주문/계좌 ----------
    def order_cash(self, code: str, qty: int, price: int, side: str) -> dict:
        """주식주문(현금). side: 'buy'|'sell'. price=0 → 시장가.

        POST body 키는 반드시 대문자, 수치는 String (프로젝트 지침).
        """
        body = {
            "CANO": self.cfg.cano,
            "ACNT_PRDT_CD": self.cfg.acnt_prdt_cd,
            "PDNO": code,
            "ORD_DVSN": "01" if price == 0 else "00",  # 01: 시장가, 00: 지정가
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        self._throttle()
        res = requests.post(
            f"{self.cfg.base_url}/uapi/domestic-stock/v1/trading/order-cash",
            headers=self._headers(self.cfg.tr_id(side), hashkey=self.hashkey(body)),
            json=body, timeout=10,
        )
        data = self._check(res)
        logger.info("%s 주문 접수 %s x%d @%s → 주문번호 %s",
                    side, code, qty, price or "시장가",
                    data.get("output", {}).get("ODNO"))
        return data

    def balance(self) -> dict:
        """잔고조회 — output1: 보유종목, output2: 계좌 요약(예수금 등)."""
        self._throttle()
        res = requests.get(
            f"{self.cfg.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=self._headers(self.cfg.tr_id("balance")),
            params={
                "CANO": self.cfg.cano, "ACNT_PRDT_CD": self.cfg.acnt_prdt_cd,
                "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02",
                "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            }, timeout=10,
        )
        return self._check(res)


class KisApiError(Exception):
    def __init__(self, msg_cd: str, msg1: str):
        self.msg_cd, self.msg1 = msg_cd, msg1
        super().__init__(f"[{msg_cd}] {msg1}")
