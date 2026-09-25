# [국내주식] 실시간시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (29개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 162 | WEBSOCKET | 국내지수 실시간예상체결 | H0UPANC0 | POST | `/tryitout/H0UPANC0` |  |
| 163 | REST | 국내주식 장운영정보 (통합) | H0UNMKO0 | POST | `/tryitout/H0UNMKO0` |  |
| 164 | WEBSOCKET | 국내주식 실시간회원사 (NXT) | H0NXMBC0 | POST | `/tryitout/H0NXMBC0` |  |
| 165 | WEBSOCKET | 국내주식 실시간체결통보 | H0STCNI0 | POST | `/tryitout/H0STCNI0` | ✓ |
| 166 | WEBSOCKET | 국내주식 시간외 실시간예상체결 (KRX) | H0STOAC0 | POST | `/tryitout/H0STOAC0` |  |
| 167 | WEBSOCKET | 국내주식 시간외 실시간호가 (KRX) | H0STOAA0 | POST | `/tryitout/H0STOAA0` |  |
| 168 | WEBSOCKET | 국내주식 실시간프로그램매매 (통합) | H0UNPGM0 | POST | `/tryitout/H0UNPGM0` |  |
| 169 | WEBSOCKET | 국내주식 실시간호가 (통합) | H0UNASP0 | POST | `/tryitout/H0UNASP0` |  |
| 170 | WEBSOCKET | 국내주식 실시간프로그램매매 (KRX) | H0STPGM0 | POST | `/tryitout/H0STPGM0` |  |
| 171 | WEBSOCKET | 국내주식 장운영정보 (KRX) | H0STMKO0 | POST | `/tryitout/H0STMKO0` |  |
| 172 | WEBSOCKET | 국내주식 실시간체결가 (KRX) | H0STCNT0 | POST | `/tryitout/H0STCNT0` |  |
| 173 | WEBSOCKET | 국내지수 실시간프로그램매매 | H0UPPGM0 | POST | `/tryitout/H0UPPGM0` |  |
| 174 | WEBSOCKET | 국내주식 실시간회원사 (통합) | H0UNMBC0 | POST | `/tryitout/H0UNMBC0` |  |
| 175 | WEBSOCKET | 국내지수 실시간체결 | H0UPCNT0 | POST | `/tryitout/H0UPCNT0` |  |
| 176 | WEBSOCKET | 국내주식 실시간예상체결 (KRX) | H0STANC0 | POST | `/tryitout/H0STANC0` |  |
| 177 | WEBSOCKET | ELW 실시간호가 | H0EWASP0 | POST | `/tryitout/H0EWASP0` |  |
| 178 | WEBSOCKET | 국내주식 실시간호가 (KRX) | H0STASP0 | POST | `/tryitout/H0STASP0` |  |
| 179 | WEBSOCKET | 국내주식 실시간체결가 (통합) | H0UNCNT0 | POST | `/tryitout/H0UNCNT0` |  |
| 180 | WEBSOCKET | 국내주식 실시간호가 (NXT) | H0NXASP0 | POST | `/tryitout/H0NXASP0` |  |
| 181 | WEBSOCKET | 국내주식 실시간프로그램매매 (NXT) | H0NXPGM0 | POST | `/tryitout/H0NXPGM0` |  |
| 182 | WEBSOCKET | 국내주식 실시간체결가 (NXT) | H0NXCNT0 | POST | `/tryitout/H0NXCNT0` |  |
| 183 | WEBSOCKET | ELW 실시간체결가 | H0EWCNT0 | POST | `/tryitout/H0EWCNT0` |  |
| 184 | WEBSOCKET | ELW 실시간예상체결 | H0EWANC0 | POST | `/tryitout/H0EWANC0` |  |
| 185 | WEBSOCKET | 국내주식 실시간예상체결 (NXT) | H0NXANC0 | POST | `/tryitout/H0NXANC0` |  |
| 186 | WEBSOCKET | 국내주식 실시간회원사 (KRX) | H0STMBC0 | POST | `/tryitout/H0STMBC0` |  |
| 187 | WEBSOCKET | 국내주식 실시간예상체결 (통합) | H0UNANC0 | POST | `/tryitout/H0UNANC0` |  |
| 188 | REST | 국내주식 장운영정보 (NXT) | H0NXMKO0 | POST | `/tryitout/H0NXMKO0` |  |
| 189 | WEBSOCKET | 국내ETF NAV추이 | H0STNAV0 | POST | `/tryitout/H0STNAV0` |  |
| 190 | WEBSOCKET | 국내주식 시간외 실시간체결가 (KRX) | H0STOUP0 | POST | `/tryitout/H0STOUP0` |  |

---

## 상세 명세


### 국내지수 실시간예상체결

- **API ID**: 실시간-027
- **실전 TR_ID**: H0UPANC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0UPANC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0UPANC0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 업종구분코드 |

#### Response Body (30)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `BSTP_CLS_CODE` | 업종 구분 코드 | object | Y | 4 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 6 |  |
| 2 | `PRPR_NMIX` | 현재가 지수 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일 대비 부호 | string | Y | 1 |  |
| 4 | `BSTP_NMIX_PRDY_VRSS` | 업종 지수 전일 대비 | string | Y | 1 |  |
| 5 | `ACML_VOL` | 누적 거래량 | string | Y | 1 |  |
| 6 | `ACML_TR_PBMN` | 누적 거래 대금 | string | Y | 1 |  |
| 7 | `PCAS_VOL` | 건별 거래량 | string | Y | 1 |  |
| 8 | `PCAS_TR_PBMN` | 건별 거래 대금 | string | Y | 1 |  |
| 9 | `PRDY_CTRT` | 전일 대비율 | string | Y | 1 |  |
| 10 | `OPRC_NMIX` | 시가 지수 | string | Y | 1 |  |
| 11 | `NMIX_HGPR` | 지수 최고가 | string | Y | 1 |  |
| 12 | `NMIX_LWPR` | 지수 최저가 | string | Y | 1 |  |
| 13 | `OPRC_VRSS_NMIX_PRPR` | 시가 대비 지수 현재가 | string | Y | 1 |  |
| 14 | `OPRC_VRSS_NMIX_SIGN` | 시가 대비 지수 부호 | string | Y | 1 |  |
| 15 | `HGPR_VRSS_NMIX_PRPR` | 최고가 대비 지수 현재가 | string | Y | 1 |  |
| 16 | `HGPR_VRSS_NMIX_SIGN` | 최고가 대비 지수 부호 | string | Y | 1 |  |
| 17 | `LWPR_VRSS_NMIX_PRPR` | 최저가 대비 지수 현재가 | string | Y | 1 |  |
| 18 | `LWPR_VRSS_NMIX_SIGN` | 최저가 대비 지수 부호 | string | Y | 1 |  |
| 19 | `PRDY_CLPR_VRSS_OPRC_RATE` | 전일 종가 대비 시가2 비율 | string | Y | 1 |  |
| 20 | `PRDY_CLPR_VRSS_HGPR_RATE` | 전일 종가 대비 최고가 비율 | string | Y | 1 |  |
| 21 | `PRDY_CLPR_VRSS_LWPR_RATE` | 전일 종가 대비 최저가 비율 | string | Y | 1 |  |
| 22 | `UPLM_ISSU_CNT` | 상한 종목 수 | string | Y | 1 |  |
| 23 | `ASCN_ISSU_CNT` | 상승 종목 수 | string | Y | 1 |  |
| 24 | `STNR_ISSU_CNT` | 보합 종목 수 | string | Y | 1 |  |
| 25 | `DOWN_ISSU_CNT` | 하락 종목 수 | string | Y | 1 |  |
| 26 | `LSLM_ISSU_CNT` | 하한 종목 수 | string | Y | 1 |  |
| 27 | `QTQT_ASCN_ISSU_CNT` | 기세 상승 종목수 | string | Y | 1 |  |
| 28 | `QTQT_DOWN_ISSU_CNT` | 기세 하락 종목수 | string | Y | 1 |  |
| 29 | `TICK_VRSS` | TICK대비 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0UPANC0",
            "tr_key": "0001"
        }
    }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0UPANC0", 
        "tr_key": "0001", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0UPANC0|001|0001^085910^2607.71^2^15.85^5424^192338^5424^192338^0.61^0^43
9^201^251^201
```

</details>



### 국내주식 장운영정보 (통합)

> 🔴 **[실측 2026-09-21~23 · 손으로 넣은 항목] 라이브 프레임은 첫 칸이 종목코드다 — 아래 Response Body 표와 한 칸 어긋난다.**
> 아래 표는 종목코드 칸 없이 `[0]=TRHT_YN` 으로 시작한다. EC2 에서 받은 라이브 `H0UNMKO0` 프레임 17건은 **전부**
> KRX(`H0STMKO0`)·NXT(`H0NXMKO0`) 표처럼 `[0]=종목코드` 로 시작하고, 뒤 칸이 한 칸씩 밀린다. 맨 끝 `EXCH_CLS_CODE` 칸은 오지 않았다.
> 예: `100840^N^(null)^AB1^112^^^55^N^` → `[1]` `TRHT_YN`=`N` · `[2]` `TR_SUSP_REAS_CNTT`=`(null)` · `[3]` `MKOP_CLS_CODE`=`AB1` ·
> `[4]` `ANTC_MKOP_CLS_CODE`=`112` · `[7]` `ISCD_STAT_CLS_CODE`=`55` · `[8]` `VI_CLS_CODE`=`N`. 빈 칸은 `(null)` 글자 그대로 올 수 있다.
> 우리 파서의 대응과 근거 = [README.md](README.md) 「제도 변경 공지 반영」 절 · 실측 정정 ①. **이 문서를 재생성하면 이 주의문을 다시 넣는다.**

- **API ID**: 국내주식 장운영정보 (통합)
- **실전 TR_ID**: H0UNMKO0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: POST
- **URL**: `/tryitout/H0UNMKO0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 2 | `tr_type` | 거래타입 | string | N | 1 | 1 : 등록<br>2 : 해제 |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0UNMKO0 : 국내주식 장운영정보 (통합) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (10)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `TRHT_YN` | 거래정지 여부 | string | Y | 1 |  |
| 1 | `TR_SUSP_REAS_CNTT` | 거래 정지 사유 내용 | string | Y | 100 |  |
| 2 | `MKOP_CLS_CODE` | 장운영 구분 코드 | string | Y | 3 |  |
| 3 | `ANTC_MKOP_CLS_CODE` | 예상 장운영 구분 코드 | string | Y | 3 |  |
| 4 | `MRKT_TRTM_CLS_CODE` | 임의연장구분코드 | string | Y | 1 |  |
| 5 | `DIVI_APP_CLS_CODE` | 동시호가배분처리구분코드 | string | Y | 2 |  |
| 6 | `ISCD_STAT_CLS_CODE` | 종목상태구분코드 | string | Y | 2 |  |
| 7 | `VI_CLS_CODE` | VI적용구분코드 | string | Y | 1 |  |
| 8 | `OVTM_VI_CLS_CODE` | 시간외단일가VI적용구분코드 | string | Y | 1 |  |
| 9 | `EXCH_CLS_CODE` | 거래소 구분코드 | string | Y | 1 |  |


### 국내주식 실시간회원사 (NXT)

- **API ID**: 국내주식 실시간회원사 (NXT)
- **실전 TR_ID**: H0NXMBC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0NXMBC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | N | 1 | 'B : 법인<br>P : 개인' |
| 2 | `tr_type` | 거래타입 | string | N | 1 | '1 : 등록<br>2 : 해제' |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | '	utf-8' |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0NXMBC0 : 국내주식 주식종목회원사 (NXT) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (78)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `SELN2_MBCR_NAME1` | 매도2 회원사명1 | string | Y | 16 |  |
| 2 | `SELN2_MBCR_NAME2` | 매도2 회원사명2 | string | Y | 16 |  |
| 3 | `SELN2_MBCR_NAME3` | 매도2 회원사명3 | string | Y | 16 |  |
| 4 | `SELN2_MBCR_NAME4` | 매도2 회원사명4 | string | Y | 16 |  |
| 5 | `SELN2_MBCR_NAME5` | 매도2 회원사명5 | string | Y | 16 |  |
| 6 | `BYOV_MBCR_NAME1` | 매수 회원사명1 | string | Y | 16 |  |
| 7 | `BYOV_MBCR_NAME2` | 매수 회원사명2 | string | Y | 16 |  |
| 8 | `BYOV_MBCR_NAME3` | 매수 회원사명3 | string | Y | 16 |  |
| 9 | `BYOV_MBCR_NAME4` | 매수 회원사명4 | string | Y | 16 |  |
| 10 | `BYOV_MBCR_NAME5` | 매수 회원사명5 | string | Y | 16 |  |
| 11 | `TOTAL_SELN_QTY1` | 총 매도 수량1 | string | Y | 8 |  |
| 12 | `TOTAL_SELN_QTY2` | 총 매도 수량2 | string | Y | 8 |  |
| 13 | `TOTAL_SELN_QTY3` | 총 매도 수량3 | string | Y | 8 |  |
| 14 | `TOTAL_SELN_QTY4` | 총 매도 수량4 | string | Y | 8 |  |
| 15 | `TOTAL_SELN_QTY5` | 총 매도 수량5 | string | Y | 8 |  |
| 16 | `TOTAL_SHNU_QTY1` | 총 매수2 수량1 | string | Y | 8 |  |
| 17 | `TOTAL_SHNU_QTY2` | 총 매수2 수량2 | string | Y | 8 |  |
| 18 | `TOTAL_SHNU_QTY3` | 총 매수2 수량3 | string | Y | 8 |  |
| 19 | `TOTAL_SHNU_QTY4` | 총 매수2 수량4 | string | Y | 8 |  |
| 20 | `TOTAL_SHNU_QTY5` | 총 매수2 수량5 | string | Y | 8 |  |
| 21 | `SELN_MBCR_GLOB_YN_1` | 매도거래원구분1 | string | Y | 1 |  |
| 22 | `SELN_MBCR_GLOB_YN_2` | 매도거래원구분2 | string | Y | 1 |  |
| 23 | `SELN_MBCR_GLOB_YN_3` | 매도거래원구분3 | string | Y | 1 |  |
| 24 | `SELN_MBCR_GLOB_YN_4` | 매도거래원구분4 | string | Y | 1 |  |
| 25 | `SELN_MBCR_GLOB_YN_5` | 매도거래원구분5 | string | Y | 1 |  |
| 26 | `SHNU_MBCR_GLOB_YN_1` | 매수거래원구분1 | string | Y | 1 |  |
| 27 | `SHNU_MBCR_GLOB_YN_2` | 매수거래원구분2 | string | Y | 1 |  |
| 28 | `SHNU_MBCR_GLOB_YN_3` | 매수거래원구분3 | string | Y | 1 |  |
| 29 | `SHNU_MBCR_GLOB_YN_4` | 매수거래원구분4 | string | Y | 1 |  |
| 30 | `SHNU_MBCR_GLOB_YN_5` | 매수거래원구분5 | string | Y | 1 |  |
| 31 | `SELN_MBCR_NO1` | 매도거래원코드1 | string | Y | 5 |  |
| 32 | `SELN_MBCR_NO2` | 매도거래원코드2 | string | Y | 5 |  |
| 33 | `SELN_MBCR_NO3` | 매도거래원코드3 | string | Y | 5 |  |
| 34 | `SELN_MBCR_NO4` | 매도거래원코드4 | string | Y | 5 |  |
| 35 | `SELN_MBCR_NO5` | 매도거래원코드5 | string | Y | 5 |  |
| 36 | `SHNU_MBCR_NO1` | 매수거래원코드1 | string | Y | 5 |  |
| 37 | `SHNU_MBCR_NO2` | 매수거래원코드2 | string | Y | 5 |  |
| 38 | `SHNU_MBCR_NO3` | 매수거래원코드3 | string | Y | 5 |  |
| 39 | `SHNU_MBCR_NO4` | 매수거래원코드4 | string | Y | 5 |  |
| 40 | `SHNU_MBCR_NO5` | 매수거래원코드5 | string | Y | 5 |  |
| 41 | `SELN_MBCR_RLIM1` | 매도 회원사 비중1 | string | Y | 8 |  |
| 42 | `SELN_MBCR_RLIM2` | 매도 회원사 비중2 | string | Y | 8 |  |
| 43 | `SELN_MBCR_RLIM3` | 매도 회원사 비중3 | string | Y | 8 |  |
| 44 | `SELN_MBCR_RLIM4` | 매도 회원사 비중4 | string | Y | 8 |  |
| 45 | `SELN_MBCR_RLIM5` | 매도 회원사 비중5 | string | Y | 8 |  |
| 46 | `SHNU_MBCR_RLIM1` | 매수2 회원사 비중1 | string | Y | 8 |  |
| 47 | `SHNU_MBCR_RLIM2` | 매수2 회원사 비중2 | string | Y | 8 |  |
| 48 | `SHNU_MBCR_RLIM3` | 매수2 회원사 비중3 | string | Y | 8 |  |
| 49 | `SHNU_MBCR_RLIM4` | 매수2 회원사 비중4 | string | Y | 8 |  |
| 50 | `SHNU_MBCR_RLIM5` | 매수2 회원사 비중5 | string | Y | 8 |  |
| 51 | `SELN_QTY_ICDC1` | 매도 수량 증감1 | string | Y | 4 |  |
| 52 | `SELN_QTY_ICDC2` | 매도 수량 증감2 | string | Y | 4 |  |
| 53 | `SELN_QTY_ICDC3` | 매도 수량 증감3 | string | Y | 4 |  |
| 54 | `SELN_QTY_ICDC4` | 매도 수량 증감4 | string | Y | 4 |  |
| 55 | `SELN_QTY_ICDC5` | 매도 수량 증감5 | string | Y | 4 |  |
| 56 | `SHNU_QTY_ICDC1` | 매수2 수량 증감1 | string | Y | 4 |  |
| 57 | `SHNU_QTY_ICDC2` | 매수2 수량 증감2 | string | Y | 4 |  |
| 58 | `SHNU_QTY_ICDC3` | 매수2 수량 증감3 | string | Y | 4 |  |
| 59 | `SHNU_QTY_ICDC4` | 매수2 수량 증감4 | string | Y | 4 |  |
| 60 | `SHNU_QTY_ICDC5` | 매수2 수량 증감5 | string | Y | 4 |  |
| 61 | `GLOB_TOTAL_SELN_QTY` | 외국계 총 매도 수량 | string | Y | 8 |  |
| 62 | `GLOB_TOTAL_SHNU_QTY` | 외국계 총 매수2 수량 | string | Y | 8 |  |
| 63 | `GLOB_TOTAL_SELN_QTY_ICDC` | 외국계 총 매도 수량 증감 | string | Y | 4 |  |
| 64 | `GLOB_TOTAL_SHNU_QTY_ICDC` | 외국계 총 매수2 수량 증감 | string | Y | 4 |  |
| 65 | `GLOB_NTBY_QTY` | 외국계 순매수 수량 | string | Y | 8 |  |
| 66 | `GLOB_SELN_RLIM` | 외국계 매도 비중 | string | Y | 8 |  |
| 67 | `GLOB_SHNU_RLIM` | 외국계 매수2 비중 | string | Y | 8 |  |
| 68 | `SELN2_MBCR_ENG_NAME1` | 매도2 영문회원사명1 | string | Y | 20 |  |
| 69 | `SELN2_MBCR_ENG_NAME2` | 매도2 영문회원사명2 | string | Y | 20 |  |
| 70 | `SELN2_MBCR_ENG_NAME3` | 매도2 영문회원사명3 | string | Y | 20 |  |
| 71 | `SELN2_MBCR_ENG_NAME4` | 매도2 영문회원사명4 | string | Y | 20 |  |
| 72 | `SELN2_MBCR_ENG_NAME5` | 매도2 영문회원사명5 | string | Y | 20 |  |
| 73 | `BYOV_MBCR_ENG_NAME1` | 매수 영문회원사명1 | string | Y | 20 |  |
| 74 | `BYOV_MBCR_ENG_NAME2` | 매수 영문회원사명2 | string | Y | 20 |  |
| 75 | `BYOV_MBCR_ENG_NAME3` | 매수 영문회원사명3 | string | Y | 20 |  |
| 76 | `BYOV_MBCR_ENG_NAME4` | 매수 영문회원사명4 | string | Y | 20 |  |
| 77 | `BYOV_MBCR_ENG_NAME5` | 매수 영문회원사명5 | string | Y | 20 |  |


### 국내주식 실시간체결통보

- **API ID**: 실시간-005
- **실전 TR_ID**: H0STCNI0
- **모의 TR_ID**: H0STCNI9
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STCNI0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `ws://ops.koreainvestment.com:31000`

<details><summary>개요</summary>

```text
국내주식 실시간 체결통보 수신 시에 (1) 주문·정정·취소·거부 접수 통보 와 (2) 체결 통보 가 모두 수신됩니다.
(14번째 값(CNTG_YN;체결여부)가 2이면 체결통보, 1이면 주문·정정·취소·거부 접수 통보입니다.)

※ 모의투자는 H0STCNI9 로 변경하여 사용합니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id
- 데이터 건수 : (ex. 001 데이터 건수를 참조하여 활용)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)

체결 통보 응답 결과는 암호화되어 출력됩니다. AES256 KEY IV를 활용해 복호화하여 활용하세요. 자세한 예제는 [도구&gt;wikidocs]에 준비되어 있습니다.
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 2 | `tr_type` | 거래타입 | string | N | 1 | 1: 등록 2 : 해제 |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | '[실전/모의투자]<br>H0STCNI0 : 국내주식 실시간체결통보<br>H0STCNI9 : 모의투자 실시간 체결통보 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | HTS ID |

#### Response Body (26)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `CUST_ID` | 고객 ID | string | Y | 8 |  |
| 1 | `ACNT_NO` | 계좌번호 | string | Y | 10 |  |
| 2 | `ODER_NO` | 주문번호 | string | Y | 10 |  |
| 3 | `OODER_NO` | 원주문번호 | string | Y | 10 |  |
| 4 | `SELN_BYOV_CLS` | 매도매수구분 | string | Y | 2 | 01 : 매도 <br>02 : 매수 |
| 5 | `RCTF_CLS` | 접수구분 | string | Y | 1 | 0:정상 <br>1:정정 <br>2:취소 |
| 6 | `ODER_KIND` | 주문종류 | string | Y | 2 | [KRX]<br>00 : 지정가<br>01 : 시장가<br>02 : 조건부지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>05 : 장전 시간외<br>06 : 장후 시간외<br>07 : 시간외 단일가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[NXT]<br>00 : 지정가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소)<br>21 : 중간가<br>22 : 스톱지정가<br>23 : 중간가IOC<br>24 : 중간가FOK<br>[SOR]<br>00 : 지정가<br>01 : 시장가<br>03 : 최유리지정가<br>04 : 최우선지정가<br>11 : IOC지정가 (즉시체결,잔량취소)<br>12 : FOK지정가 (즉시체결,전량취소)<br>13 : IOC시장가 (즉시체결,잔량취소)<br>14 : FOK시장가 (즉시체결,전량취소)<br>15 : IOC최유리 (즉시체결,잔량취소)<br>16 : FOK최유리 (즉시체결,전량취소) |
| 7 | `ODER_COND` | 주문조건 | string | Y | 1 | 0:없음<br>1:IOC <br>2:FOK |
| 8 | `STCK_SHRN_ISCD` | 주식 단축 종목코드 | string | Y | 9 |  |
| 9 | `CNTG_QTY` | 체결 수량 | string | Y | 10 |  |
| 10 | `CNTG_UNPR` | 체결단가 | string | Y | 9 |  |
| 11 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 |  |
| 12 | `RFUS_YN` | 거부여부 | string | Y | 1 | 0 : 승인 <br>1 : 거부 |
| 13 | `CNTG_YN` | 체결여부 | string | Y | 1 | 1 : 주문,정정,취소,거부<br>2 : 체결 |
| 14 | `ACPT_YN` | 접수여부 | string | Y | 1 | 1 : 주문접수<br>2 : 확인<br>3 : 취소(FOK/IOC) |
| 15 | `BRNC_NO` | 지점번호 | string | Y | 5 |  |
| 16 | `ODER_QTY` | 주문수량 | string | Y | 9 |  |
| 17 | `ACNT_NAME` | 계좌명 | string | Y | 12 |  |
| 18 | `ORD_COND_PRC` | 호가조건가격 | string | Y | 9 | 스톱지정가 시 표시 |
| 19 | `ORD_EXG_GB` | 주문거래소 구분 | string | Y | 1 | 1:KRX, 2:NXT, 3:SOR-KRX, 4:SOR-NXT |
| 20 | `POPUP_YN` | 실시간체결창 표시여부 | string | Y | 1 | Y/N |
| 21 | `FILLER` | 필러 | string | Y | 3 |  |
| 22 | `CRDT_CLS` | 신용구분 | string | Y | 2 |  |
| 23 | `CRDT_LOAN_DATE` | 신용대출일자 | string | Y | 8 |  |
| 24 | `CNTG_ISNM40` | 체결종목명 | string | Y | 40 |  |
| 25 | `ODER_PRC` | 주문가격 | string | Y | 9 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0STCNI0",
                           "tr_key":"HTS ID"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```json
{
    "header": {
        "tr_id": "H0STCNI0", 
        "tr_key": "HTS ID", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output - 주문·정정·취소·거부 접수 통보
HTS ID^1234567801^0000002891^^02^0^01^0^136480^0000000001^000000000^094941^0
^1^1^06010^000000001^김한투^하림^10^^하림^

# output - 체결 통보
HTS ID^1234567801^0000002891^^02^0^00^0^136480^0000000001^000003190^094941^0
^2^2^06010^000000001^김한투^하림^10^^하림^000000000
```

</details>



### 국내주식 시간외 실시간예상체결 (KRX)

> 🔴 **[공지 2026-09-09 · 시행 2026-09-14(월)] 시간외단일가 폐지 — 이 채널의 대상 시장이 사라진다.**
> KRX 는 2026-09-14 부터 16:00~20:00 **애프터마켓**(연속 실시간 체결)을 신설하고 **시간외단일가를 폐지**했다.
> 애프터마켓 체결·호가는 이 시간외 전용 채널이 아니라 **기존 정규 채널**로 온다 —
> `H0STCNT0`/`H0UNCNT0`/`H0NXCNT0`(체결가)·`H0STASP0`(호가)에 `MARKET_CLS_CODE=3`(애프터)으로 실린다.
> ⚠️ 공지는 이 채널들의 **폐지 여부를 명시하지 않았다** — 구독이 계속 ACK 되는지, 프레임이 오는지는 실측으로 확인한다.

- **API ID**: 실시간-024
- **실전 TR_ID**: H0STOAC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STOAC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 시간외 실시간예상체결 API입니다.
국내주식 시간외 단일가(16:00~18:00) 시간대에 실시간예상체결 데이터 확인 가능합니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info


[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0STOAC0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (43)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식현재가 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비구분 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 1 |  |
| 5 | `PRDY_CTRT` | 등락율 | string | Y | 1 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중평균주식가격 | string | Y | 1 |  |
| 7 | `STCK_OPRC` | 시가 | string | Y | 1 |  |
| 8 | `STCK_HGPR` | 고가 | string | Y | 1 |  |
| 9 | `STCK_LWPR` | 저가 | string | Y | 1 |  |
| 10 | `ASKP1` | 매도호가 | string | Y | 1 |  |
| 11 | `BIDP1` | 매수호가 | string | Y | 1 |  |
| 12 | `CNTG_VOL` | 거래량 | string | Y | 1 |  |
| 13 | `ACML_VOL` | 누적거래량 | string | Y | 1 |  |
| 14 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 1 |  |
| 15 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 1 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 1 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 1 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 1 |  |
| 19 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 1 |  |
| 20 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 1 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수비율 | string | Y | 1 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 1 |  |
| 24 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가대비구분 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가대비 | string | Y | 1 |  |
| 27 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 고가대비구분 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 고가대비 | string | Y | 1 |  |
| 30 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 저가대비구분 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 저가대비 | string | Y | 1 |  |
| 33 | `BSOP_DATE` | 영업일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신장운영구분코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 37 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 40 | `VOL_TNRT` | 거래량회전율 | string | Y | 1 |  |
| 41 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일동시간누적거래량 | string | Y | 1 |  |
| 42 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일동시간누적거래량비율 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0STOAC0",
                           "tr_key":"005930"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STOAC0", 
        "tr_key": "005930", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0STOAC0|001|005930^164128^77700^2^100^0.13^78209.85^77600^77800^77
600^77800^77700^82^82^6371400^2^2^0^71.12^6995^5511^1^0.38^69.15^161015^3^100^162004^5^
-100^161015^3^100^20240503^49^N^71160^6882^24644^30955^0.00^0^0.00
```

</details>



### 국내주식 시간외 실시간호가 (KRX)

> 🔴 **[공지 2026-09-09 · 시행 2026-09-14(월)] 시간외단일가 폐지 — 이 채널의 대상 시장이 사라진다.**
> KRX 는 2026-09-14 부터 16:00~20:00 **애프터마켓**(연속 실시간 체결)을 신설하고 **시간외단일가를 폐지**했다.
> 애프터마켓 체결·호가는 이 시간외 전용 채널이 아니라 **기존 정규 채널**로 온다 —
> `H0STCNT0`/`H0UNCNT0`/`H0NXCNT0`(체결가)·`H0STASP0`(호가)에 `MARKET_CLS_CODE=3`(애프터)으로 실린다.
> ⚠️ 공지는 이 채널들의 **폐지 여부를 명시하지 않았다** — 구독이 계속 ACK 되는지, 프레임이 오는지는 실측으로 확인한다.

- **API ID**: 실시간-025
- **실전 TR_ID**: H0STOAA0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STOAA0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 시간외 실시간호가 API입니다.
국내주식 시간외 단일가(16:00~18:00) 시간대에 실시간호가 데이터 확인 가능합니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info


[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0STOAA0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (54)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `HOUR_CLS_CODE` | 시간구분코드 | string | Y | 1 |  |
| 3 | `ASKP1` | 매도호가1 | string | Y | 1 |  |
| 4 | `ASKP2` | 매도호가2 | string | Y | 1 |  |
| 5 | `ASKP3` | 매도호가3 | string | Y | 1 |  |
| 6 | `ASKP4` | 매도호가4 | string | Y | 1 |  |
| 7 | `ASKP5` | 매도호가5 | string | Y | 1 |  |
| 8 | `ASKP6` | 매도호가6 | string | Y | 1 |  |
| 9 | `ASKP7` | 매도호가7 | string | Y | 1 |  |
| 10 | `ASKP8` | 매도호가8 | string | Y | 1 |  |
| 11 | `ASKP9` | 매도호가9 | string | Y | 1 |  |
| 12 | `BIDP1` | 매수호가1 | string | Y | 1 |  |
| 13 | `BIDP2` | 매수호가2 | string | Y | 1 |  |
| 14 | `BIDP3` | 매수호가3 | string | Y | 1 |  |
| 15 | `BIDP4` | 매수호가4 | string | Y | 1 |  |
| 16 | `BIDP5` | 매수호가5 | string | Y | 1 |  |
| 17 | `BIDP6` | 매수호가6 | string | Y | 1 |  |
| 18 | `BIDP7` | 매수호가7 | string | Y | 1 |  |
| 19 | `BIDP8` | 매수호가8 | string | Y | 1 |  |
| 20 | `BIDP9` | 매수호가9 | string | Y | 1 |  |
| 21 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 22 | `ASKP_RSQN2` | 매도호가잔량2 | string | Y | 1 |  |
| 23 | `ASKP_RSQN3` | 매도호가잔량3 | string | Y | 1 |  |
| 24 | `ASKP_RSQN4` | 매도호가잔량4 | string | Y | 1 |  |
| 25 | `ASKP_RSQN5` | 매도호가잔량5 | string | Y | 1 |  |
| 26 | `ASKP_RSQN6` | 매도호가잔량6 | string | Y | 1 |  |
| 27 | `ASKP_RSQN7` | 매도호가잔량7 | string | Y | 1 |  |
| 28 | `ASKP_RSQN8` | 매도호가잔량8 | string | Y | 1 |  |
| 29 | `ASKP_RSQN9` | 매도호가잔량9 | string | Y | 1 |  |
| 30 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 31 | `BIDP_RSQN2` | 매수호가잔량2 | string | Y | 1 |  |
| 32 | `BIDP_RSQN3` | 매수호가잔량3 | string | Y | 1 |  |
| 33 | `BIDP_RSQN4` | 매수호가잔량4 | string | Y | 1 |  |
| 34 | `BIDP_RSQN5` | 매수호가잔량5 | string | Y | 1 |  |
| 35 | `BIDP_RSQN6` | 매수호가잔량6 | string | Y | 1 |  |
| 36 | `BIDP_RSQN7` | 매수호가잔량7 | string | Y | 1 |  |
| 37 | `BIDP_RSQN8` | 매수호가잔량8 | string | Y | 1 |  |
| 38 | `BIDP_RSQN9` | 매수호가잔량9 | string | Y | 1 |  |
| 39 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 40 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 41 | `OVTM_TOTAL_ASKP_RSQN` | 시간외총매도호가잔량 | string | Y | 1 |  |
| 42 | `OVTM_TOTAL_BIDP_RSQN` | 시간외총매수호가잔량 | string | Y | 1 |  |
| 43 | `ANTC_CNPR` | 예상체결가 | string | Y | 1 |  |
| 44 | `ANTC_CNQN` | 예상체결량 | string | Y | 1 |  |
| 45 | `ANTC_VOL` | 예상거래량 | string | Y | 1 |  |
| 46 | `ANTC_CNTG_VRSS` | 예상체결대비 | string | Y | 1 |  |
| 47 | `ANTC_CNTG_VRSS_SIGN` | 예상체결대비부호 | string | Y | 1 |  |
| 48 | `ANTC_CNTG_PRDY_CTRT` | 예상체결전일대비율 | string | Y | 1 |  |
| 49 | `ACML_VOL` | 누적거래량 | string | Y | 1 |  |
| 50 | `TOTAL_ASKP_RSQN_ICDC` | 총매도호가잔량증감 | string | Y | 1 |  |
| 51 | `TOTAL_BIDP_RSQN_ICDC` | 총매수호가잔량증감 | string | Y | 1 |  |
| 52 | `OVTM_TOTAL_ASKP_ICDC` | 시간외총매도호가증감 | string | Y | 1 |  |
| 53 | `OVTM_TOTAL_BIDP_ICDC` | 시간외총매수호가증감 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0STOAA0",
                           "tr_key":"005930"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STOAA0", 
        "tr_key": "005930", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0STOAA0|001|005930^164128^B^77800^77900^78000^0^0^0^0^0^0^0^77700^
77600^77500^0^0^0^0^0^0^0^8005^7355^9284^0^0^0^0^0^0^0^4^16654^14297^0^0^0^0^0^0^0^2464
4^30955^0^37426^77700^82^82^100^2^0.13^13069425^-1^0^0^0
```

</details>



### 국내주식 실시간프로그램매매 (통합)

- **API ID**: 국내주식 실시간프로그램매매 (통합)
- **실전 TR_ID**: H0UNPGM0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0UNPGM0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | N | 1 | 'B : 법인<br>P : 개인' |
| 2 | `tr_type` | 거래타입 | string | N | 1 | '1 : 등록<br>2 : 해제' |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | '	utf-8' |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0UNPGM0 : 실시간 주식종목프로그램매매 통합 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 |  |
| 2 | `SELN_CNQN` | 매도 체결량 | string | Y | 8 |  |
| 3 | `SELN_TR_PBMN` | 매도 거래 대금 | string | Y | 8 |  |
| 4 | `SHNU_CNQN` | 매수2 체결량 | string | Y | 8 |  |
| 5 | `SHNU_TR_PBMN` | 매수2 거래 대금 | string | Y | 8 |  |
| 6 | `NTBY_CNQN` | 순매수 체결량 | string | Y | 8 |  |
| 7 | `NTBY_TR_PBMN` | 순매수 거래 대금 | string | Y | 8 |  |
| 8 | `SELN_RSQN` | 매도호가잔량 | string | Y | 8 |  |
| 9 | `SHNU_RSQN` | 매수호가잔량 | string | Y | 8 |  |
| 10 | `WHOL_NTBY_QTY` | 전체순매수호가잔량 | string | Y | 8 |  |


### 국내주식 실시간호가 (통합)

- **API ID**: 국내주식 실시간호가 (통합)
- **실전 TR_ID**: H0UNASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0UNASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | N | 1 | 'B : 법인<br>P : 개인' |
| 2 | `tr_type` | 거래타입 | string | N | 1 | '1 : 등록<br>2 : 해제' |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | '	utf-8' |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0UNASP0 : 실시간 주식 체결가 통합 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (66)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 6 |  |
| 2 | `HOUR_CLS_CODE` | 시간 구분 코드 | string | Y | 1 |  |
| 3 | `ASKP1` | 매도호가1 | string | Y | 4 |  |
| 4 | `ASKP2` | 매도호가2 | string | Y | 4 |  |
| 5 | `ASKP3` | 매도호가3 | string | Y | 4 |  |
| 6 | `ASKP4` | 매도호가4 | string | Y | 4 |  |
| 7 | `ASKP5` | 매도호가5 | string | Y | 4 |  |
| 8 | `ASKP6` | 매도호가6 | string | Y | 4 |  |
| 9 | `ASKP7` | 매도호가7 | string | Y | 4 |  |
| 10 | `ASKP8` | 매도호가8 | string | Y | 4 |  |
| 11 | `ASKP9` | 매도호가9 | string | Y | 4 |  |
| 12 | `ASKP10` | 매도호가10 | string | Y | 4 |  |
| 13 | `BIDP1` | 매수호가1 | string | Y | 4 |  |
| 14 | `BIDP2` | 매수호가2 | string | Y | 4 |  |
| 15 | `BIDP3` | 매수호가3 | string | Y | 4 |  |
| 16 | `BIDP4` | 매수호가4 | string | Y | 4 |  |
| 17 | `BIDP5` | 매수호가5 | string | Y | 4 |  |
| 18 | `BIDP6` | 매수호가6 | string | Y | 4 |  |
| 19 | `BIDP7` | 매수호가7 | string | Y | 4 |  |
| 20 | `BIDP8` | 매수호가8 | string | Y | 4 |  |
| 21 | `BIDP9` | 매수호가9 | string | Y | 4 |  |
| 22 | `BIDP10` | 매수호가10 | string | Y | 4 |  |
| 23 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 24 | `ASKP_RSQN2` | 매도호가 잔량2 | string | Y | 8 |  |
| 25 | `ASKP_RSQN3` | 매도호가 잔량3 | string | Y | 8 |  |
| 26 | `ASKP_RSQN4` | 매도호가 잔량4 | string | Y | 8 |  |
| 27 | `ASKP_RSQN5` | 매도호가 잔량5 | string | Y | 8 |  |
| 28 | `ASKP_RSQN6` | 매도호가 잔량6 | string | Y | 8 |  |
| 29 | `ASKP_RSQN7` | 매도호가 잔량7 | string | Y | 8 |  |
| 30 | `ASKP_RSQN8` | 매도호가 잔량8 | string | Y | 8 |  |
| 31 | `ASKP_RSQN9` | 매도호가 잔량9 | string | Y | 8 |  |
| 32 | `ASKP_RSQN10` | 매도호가 잔량10 | string | Y | 8 |  |
| 33 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 34 | `BIDP_RSQN2` | 매수호가 잔량2 | string | Y | 8 |  |
| 35 | `BIDP_RSQN3` | 매수호가 잔량3 | string | Y | 8 |  |
| 36 | `BIDP_RSQN4` | 매수호가 잔량4 | string | Y | 8 |  |
| 37 | `BIDP_RSQN5` | 매수호가 잔량5 | string | Y | 8 |  |
| 38 | `BIDP_RSQN6` | 매수호가 잔량6 | string | Y | 8 |  |
| 39 | `BIDP_RSQN7` | 매수호가 잔량7 | string | Y | 8 |  |
| 40 | `BIDP_RSQN8` | 매수호가 잔량8 | string | Y | 8 |  |
| 41 | `BIDP_RSQN9` | 매수호가 잔량9 | string | Y | 8 |  |
| 42 | `BIDP_RSQN10` | 매수호가 잔량10 | string | Y | 8 |  |
| 43 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 8 |  |
| 44 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 8 |  |
| 45 | `OVTM_TOTAL_ASKP_RSQN` | 시간외 총 매도호가 잔량 | string | Y | 8 |  |
| 46 | `OVTM_TOTAL_BIDP_RSQN` | 시간외 총 매수호가 잔량 | string | Y | 8 |  |
| 47 | `ANTC_CNPR` | 예상 체결가 | string | Y | 4 |  |
| 48 | `ANTC_CNQN` | 예상 체결량 | string | Y | 8 |  |
| 49 | `ANTC_VOL` | 예상 거래량 | string | Y | 8 |  |
| 50 | `ANTC_CNTG_VRSS` | 예상 체결 대비 | string | Y | 4 |  |
| 51 | `ANTC_CNTG_VRSS_SIGN` | 예상 체결 대비 부호 | string | Y | 1 |  |
| 52 | `ANTC_CNTG_PRDY_CTRT` | 예상 체결 전일 대비율 | string | Y | 8 |  |
| 53 | `ACML_VOL` | 누적 거래량 | string | Y | 8 |  |
| 54 | `TOTAL_ASKP_RSQN_ICDC` | 총 매도호가 잔량 증감 | string | Y | 4 |  |
| 55 | `TOTAL_BIDP_RSQN_ICDC` | 총 매수호가 잔량 증감 | string | Y | 4 |  |
| 56 | `OVTM_TOTAL_ASKP_ICDC` | 시간외 총 매도호가 증감 | string | Y | 4 |  |
| 57 | `OVTM_TOTAL_BIDP_ICDC` | 시간외 총 매수호가 증감 | string | Y | 4 |  |
| 58 | `STCK_DEAL_CLS_CODE` | 주식 매매 구분 코드 | string | Y | 2 |  |
| 59 | `KMID_PRC` | KRX 중간가 | string | Y | 4 |  |
| 60 | `KMID_TOTAL_RSQN` | KRX 중간가잔량합계수량 | string | Y | 8 |  |
| 61 | `KMID_CLS_CODE` | KRX 중간가 매수매도 구분 | string | Y | 1 |  |
| 62 | `NMID_PRC` | NXT 중간가 | string | Y | 4 |  |
| 63 | `NMID_TOTAL_RSQN` | NXT 중간가잔량합계수량 | string | Y | 8 |  |
| 64 | `NMID_CLS_CODE` | NXT 중간가 매수매도 구분 | string | Y | 1 |  |
| 65 | `ANTC_EXCH_CLS_CODE` | 예상체결 거래소구분 | string | Y | 1 | **[신규 · 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월)]** 예상체결 거래소구분 — 1:KRX 2:NXT. ⚠️ payload 안의 위치(index)는 공지에 없다 — 실측 확정 필요 |


### 국내주식 실시간프로그램매매 (KRX)

- **API ID**: 실시간-048
- **실전 TR_ID**: H0STPGM0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STPGM0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0STPGM0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | object | Y | 9 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `SELN_CNQN` | 매도체결량 | string | Y | 1 |  |
| 3 | `SELN_TR_PBMN` | 매도거래대금 | string | Y | 1 |  |
| 4 | `SHNU_CNQN` | 매수2체결량 | string | Y | 1 |  |
| 5 | `SHNU_TR_PBMN` | 매수2거래대금 | string | Y | 1 |  |
| 6 | `NTBY_CNQN` | 순매수체결량 | string | Y | 1 |  |
| 7 | `NTBY_TR_PBMN` | 순매수거래대금 | string | Y | 1 |  |
| 8 | `SELN_RSQN` | 매도호가잔량 | string | Y | 1 |  |
| 9 | `SHNU_RSQN` | 매수호가잔량 | string | Y | 1 |  |
| 10 | `WHOL_NTBY_QTY` | 전체순매수호가잔량 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0STPGM0",
            "tr_key": "005930"
        }
    }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STPGM0", 
        "tr_key": "005930", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0STPGM0|001|005930^092237^1413444^109159646900^1189408^91931710200^-2240
36^-17227936700^65033^15475^-49558
```

</details>



### 국내주식 장운영정보 (KRX)

- **API ID**: 실시간-049
- **실전 TR_ID**: H0STMKO0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STMKO0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 장운영정보 연결 시, 연결종목의 VI 발동 시와 VI 해제 시에 데이터 수신됩니다. 

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0STMKO0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | object | Y | 9 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `TRHT_YN` | 거래정지여부 | string | Y | 1 |  |
| 2 | `TR_SUSP_REAS_CNTT` | 거래정지사유내용 | string | Y | 100 |  |
| 3 | `MKOP_CLS_CODE` | 장운영구분코드 | string | Y | 3 | 110        장전 동시호가 개시                      <br>112        장개시                                  <br>121        장후 동시호가 개시                      <br>129        장마감                                  <br>130        장개시전시간외개시                      <br>139        장개시전시간외종료                      <br>140        시간외 종가 매매 개시                   <br>146        장종료후시간외 체결지시                 <br>149        시간외 종가 매매 종료                   <br>150        시간외 단일가 매매 개시                 <br>156        시간외단일가 체결지시                   <br>159        시간외 단일가 매매 종료                 <br>164        시장임시정지                            <br>174        서킷브레이크 발동                       <br>175        서킷브레이크 해제                       <br>182        서킷브레이크 장중동시마감               <br>184        서킷브레이크 개시                       <br>185        서킷브레이크 해제                       <br>387        사이드카 매도발동                       <br>388        사이드카 매도발동해제                   <br>397        사이드카 매수발동                       <br>398        사이드카 매수발동해제                   <br>???        단일가개시                              <br>???        서킷브레이크 단일가접수                 <br>F01        장개시 10초전                           <br>F06        장개시 1분전                            <br>F07        장개시 5분전                            <br>F08        장개시 10분전                           <br>F09        장개시 3분전                            <br>F11        장마감 10초전                           <br>F16        장마감 1분전                            <br>F17        장마감 5분전                            <br>F18        장마감 3분전                            <br>P01        장개시 10초전                           <br>P06        장개시 1분전                            <br>P07        장개시 5분전                            <br>P08        장개시 10분전                           <br>P09        장개시 30분전                           <br>P11        장마감 10초전                           <br>P16        장마감 1분전                            <br>P17        장마감 5분전                            <br>P18        장마감 3분전 |
| 4 | `ANTC_MKOP_CLS_CODE` | 예상장운영구분코드 | string | Y | 3 | 112    장전예상종료 <br>121   장후예상시작<br>129   장후예상종료<br>311  장전예상시작 |
| 5 | `MRKT_TRTM_CLS_CODE` | 임의연장구분코드 | string | Y | 1 | 1  시초동시 임의종료 지정<br>2  시초동시 임의종료 해제 <br>3  마감동시 임의종료 지정 <br>4  마감동시 임의종료 해제  <br>5  시간외단일가임의종료 지정 <br>6  시간외단일가임의종료 해제 |
| 6 | `DIVI_APP_CLS_CODE` | 동시호가배분처리구분코드 | string | Y | 2 | divi_app_cls_code[0]  1: 배분개시 2: 배분해제<br>divi_app_cls_code[1] 1: 매수상한 2: 매수하한 3: 매도상한 4: 매도하한 |
| 7 | `ISCD_STAT_CLS_CODE` | 종목상태구분코드 | string | Y | 2 | 51  관리종목 지정 종목<br>52  시장경고 구분이 '투자위험'인 종목<br>53  시장경고 구분이 '투자경고'인 종목<br>54  시장경고 구분이 '투자주의'인 종목<br>55  당사 신용가능 종목<br>57  당사 증거금률이 100인 종목<br>58  거래정지 지정된 종목  <br>59  단기과열종목으로 지정되거나 지정 연장된 종목<br>00 그 외 종목 |
| 8 | `VI_CLS_CODE` | VI적용구분코드 | string | Y | 1 | Y  VI적용된 종목<br>N  VI적용되지 않은 종목 |
| 9 | `OVTM_VI_CLS_CODE` | 시간외단일가VI적용구분코드 | string | Y | 1 | Y 시간외단일가VI 적용된 종목<br>N 시간외단일가VI 적용되지 않은 종목 |
| 10 | `EXCH_CLS_CODE` | 거래소구분코드 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0STMKO0",
            "tr_key": "396300"
        }
    }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STMKO0", 
        "tr_key": "396300", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0STMKO0|001|396300^N^(null)^^311^^^55^N^N
```

</details>



### 국내주식 실시간체결가 (KRX)

- **API ID**: 실시간-003
- **실전 TR_ID**: H0STCNT0
- **모의 TR_ID**: H0STCNT0
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `ws://ops.koreainvestment.com:31000`

<details><summary>개요</summary>

```text
[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py
실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)

※ 데이터가 많은 경우 여러 건을 페이징 처리해서 데이터를 보내는 점 참고 부탁드립니다.
ex) 0|H0STCNT0|004|... 인 경우 004가 데이터 개수를 의미하여, 뒤에 체결데이터가 4건 들어옴
→ 0|H0STCNT0|004|005930^123929...(체결데이터1)...^005930^123929...(체결데이터2)...^005930^123929...(체결데이터3)...^005930^123929...(체결데이터4)...
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | Y | 1 | B : 법인<br>P : 개인 |
| 2 | `tr_type` | 거래타입 | string | Y | 1 | 1 : 등록<br>2 : 해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 1 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 1 | [실전/모의투자]<br>H0STCNT0 : 실시간 주식 체결가 |
| 1 | `tr_key` | 구분값 | string | Y | 1 | 종목번호 (6자리)<br>ETN의 경우, Q로 시작 (EX. Q500001) |

#### Response Body (47)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식 현재가 | number | Y | 4 | 체결가격 |
| 3 | `PRDY_VRSS_SIGN` | 전일 대비 부호 | string | Y | 1 | 1 : 상한<br>2 : 상승<br>3 : 보합<br>4 : 하한<br>5 : 하락 |
| 4 | `PRDY_VRSS` | 전일 대비 | number | Y | 4 |  |
| 5 | `PRDY_CTRT` | 전일 대비율 | number | Y | 8 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중 평균 주식 가격 | number | Y | 8 |  |
| 7 | `STCK_OPRC` | 주식 시가 | number | Y | 4 |  |
| 8 | `STCK_HGPR` | 주식 최고가 | number | Y | 4 |  |
| 9 | `STCK_LWPR` | 주식 최저가 | number | Y | 4 |  |
| 10 | `ASKP1` | 매도호가1 | number | Y | 4 |  |
| 11 | `BIDP1` | 매수호가1 | number | Y | 4 |  |
| 12 | `CNTG_VOL` | 체결 거래량 | number | Y | 8 |  |
| 13 | `ACML_VOL` | 누적 거래량 | number | Y | 8 |  |
| 14 | `ACML_TR_PBMN` | 누적 거래 대금 | number | Y | 8 |  |
| 15 | `SELN_CNTG_CSNU` | 매도 체결 건수 | number | Y | 4 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수 체결 건수 | number | Y | 4 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수 체결 건수 | number | Y | 4 |  |
| 18 | `CTTR` | 체결강도 | number | Y | 8 |  |
| 19 | `SELN_CNTG_SMTN` | 총 매도 수량 | number | Y | 8 |  |
| 20 | `SHNU_CNTG_SMTN` | 총 매수 수량 | number | Y | 8 |  |
| 21 | `CCLD_DVSN` | 체결구분 | string | Y | 1 | 1:매수(+) <br>3:장전 <br>5:매도(-) |
| 22 | `SHNU_RATE` | 매수비율 | number | Y | 8 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일 거래량 대비 등락율 | number | Y | 8 |  |
| 24 | `OPRC_HOUR` | 시가 시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가대비구분 | string | Y | 1 | 1 : 상한<br>2 : 상승<br>3 : 보합<br>4 : 하한<br>5 : 하락 |
| 26 | `OPRC_VRSS_PRPR` | 시가대비 | number | Y | 4 |  |
| 27 | `HGPR_HOUR` | 최고가 시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 고가대비구분 | string | Y | 1 | 1 : 상한<br>2 : 상승<br>3 : 보합<br>4 : 하한<br>5 : 하락 |
| 29 | `HGPR_VRSS_PRPR` | 고가대비 | number | Y | 4 |  |
| 30 | `LWPR_HOUR` | 최저가 시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 저가대비구분 | string | Y | 1 | 1 : 상한<br>2 : 상승<br>3 : 보합<br>4 : 하한<br>5 : 하락 |
| 32 | `LWPR_VRSS_PRPR` | 저가대비 | number | Y | 4 |  |
| 33 | `BSOP_DATE` | 영업 일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신 장운영 구분 코드 | string | Y | 2 | (1) 첫 번째 비트<br>1 : 장개시전<br>2 : 장중<br>3 : 장종료후<br>4 : 시간외단일가<br>7 : 일반Buy-in<br>8 : 당일Buy-in<br>(2) 두 번째 비트<br>0 : 보통<br>1 : 종가<br>2 : 대량<br>3 : 바스켓<br>7 : 정리매매<br>8 : Buy-in |
| 35 | `TRHT_YN` | 거래정지 여부 | string | Y | 1 | Y : 정지<br>N : 정상거래 |
| 36 | `ASKP_RSQN1` | 매도호가 잔량1 | number | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가 잔량1 | number | Y | 8 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | number | Y | 8 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | number | Y | 8 |  |
| 40 | `VOL_TNRT` | 거래량 회전율 | number | Y | 8 |  |
| 41 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일 동시간 누적 거래량 | number | Y | 8 |  |
| 42 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일 동시간 누적 거래량 비율 | number | Y | 8 |  |
| 43 | `HOUR_CLS_CODE` | 시간 구분 코드 | string | Y | 1 | 0 : 장중<br>A : 장후예상<br>B : 장전예상<br>C : 9시이후의 예상가, VI발동<br>D : 시간외 단일가 예상 |
| 44 | `MRKT_TRTM_CLS_CODE` | 임의종료구분코드 | string | Y | 1 |  |
| 45 | `VI_STND_PRC` | 정적VI발동기준가 | number | Y | 4 |  |
| 46 | `MARKET_CLS_CODE` | 장 구분 코드 | string | Y | 1 | **[신규 · 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월)]** 장 구분 코드 — 1:프리 2:정규 3:애프터 5:종가. ⚠️ 공지는 **추가된다**고만 밝히고 파이프 구분 payload 안의 **위치(index)를 명시하지 않았다** — 우리 핸들러는 위치로 파싱하므로 2026-09-14 첫 프레임 실측으로 확정해야 한다 |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0STCNT0",
                           "tr_key":"005930"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STCNT0", 
        "tr_key": "005930", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
005930^093354^71900^5^-100^-0.14^72023.83^72100^72400^71700^71900^71800^1^3052
507^219853241700^5105^6937^1832^84.90^1366314^1159996^1^0.39^20.28^090020^5^-2
00^090820^5^-500^092619^2^200^20230612^20^N^65945^216924^1118750^2199206^0.05^
2424142^125.92^0^^72100
```

</details>



### 국내지수 실시간프로그램매매

- **API ID**: 실시간-028
- **실전 TR_ID**: H0UPPGM0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0UPPGM0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0UPPGM0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 업종구분코드 |

#### Response Body (88)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `BSTP_CLS_CODE` | 업종 구분 코드 | object | Y | 4 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 6 |  |
| 2 | `ARBT_SELN_ENTM_CNQN` | 차익 매도 위탁 체결량 | string | Y | 1 |  |
| 3 | `ARBT_SELN_ONSL_CNQN` | 차익 매도 자기 체결량 | string | Y | 1 |  |
| 4 | `ARBT_SHNU_ENTM_CNQN` | 차익 매수2 위탁 체결량 | string | Y | 1 |  |
| 5 | `ARBT_SHNU_ONSL_CNQN` | 차익 매수2 자기 체결량 | string | Y | 1 |  |
| 6 | `NABT_SELN_ENTM_CNQN` | 비차익 매도 위탁 체결량 | string | Y | 1 |  |
| 7 | `NABT_SELN_ONSL_CNQN` | 비차익 매도 자기 체결량 | string | Y | 1 |  |
| 8 | `NABT_SHNU_ENTM_CNQN` | 비차익 매수2 위탁 체결량 | string | Y | 1 |  |
| 9 | `NABT_SHNU_ONSL_CNQN` | 비차익 매수2 자기 체결량 | string | Y | 1 |  |
| 10 | `ARBT_SELN_ENTM_CNTG_AMT` | 차익 매도 위탁 체결 금액 | string | Y | 1 |  |
| 11 | `ARBT_SELN_ONSL_CNTG_AMT` | 차익 매도 자기 체결 금액 | string | Y | 1 |  |
| 12 | `ARBT_SHNU_ENTM_CNTG_AMT` | 차익 매수2 위탁 체결 금액 | string | Y | 1 |  |
| 13 | `ARBT_SHNU_ONSL_CNTG_AMT` | 차익 매수2 자기 체결 금액 | string | Y | 1 |  |
| 14 | `NABT_SELN_ENTM_CNTG_AMT` | 비차익 매도 위탁 체결 금액 | string | Y | 1 |  |
| 15 | `NABT_SELN_ONSL_CNTG_AMT` | 비차익 매도 자기 체결 금액 | string | Y | 1 |  |
| 16 | `NABT_SHNU_ENTM_CNTG_AMT` | 비차익 매수2 위탁 체결 금액 | string | Y | 1 |  |
| 17 | `NABT_SHNU_ONSL_CNTG_AMT` | 비차익 매수2 자기 체결 금액 | string | Y | 1 |  |
| 18 | `ARBT_SMTN_SELN_VOL` | 차익 합계 매도 거래량 | string | Y | 1 |  |
| 19 | `ARBT_SMTM_SELN_VOL_RATE` | 차익 합계 매도 거래량 비율 | string | Y | 1 |  |
| 20 | `ARBT_SMTN_SELN_TR_PBMN` | 차익 합계 매도 거래 대금 | string | Y | 1 |  |
| 21 | `ARBT_SMTM_SELN_TR_PBMN_RATE` | 차익 합계 매도 거래대금 비율 | string | Y | 1 |  |
| 22 | `ARBT_SMTN_SHNU_VOL` | 차익 합계 매수2 거래량 | string | Y | 1 |  |
| 23 | `ARBT_SMTM_SHNU_VOL_RATE` | 차익 합계 매수 거래량 비율 | string | Y | 1 |  |
| 24 | `ARBT_SMTN_SHNU_TR_PBMN` | 차익 합계 매수2 거래 대금 | string | Y | 1 |  |
| 25 | `ARBT_SMTM_SHNU_TR_PBMN_RATE` | 차익 합계 매수 거래대금 비율 | string | Y | 1 |  |
| 26 | `ARBT_SMTN_NTBY_QTY` | 차익 합계 순매수 수량 | string | Y | 1 |  |
| 27 | `ARBT_SMTM_NTBY_QTY_RATE` | 차익 합계 순매수 수량 비율 | string | Y | 1 |  |
| 28 | `ARBT_SMTN_NTBY_TR_PBMN` | 차익 합계 순매수 거래 대금 | string | Y | 1 |  |
| 29 | `ARBT_SMTM_NTBY_TR_PBMN_RATE` | 차익 합계 순매수 거래대금 비율 | string | Y | 1 |  |
| 30 | `NABT_SMTN_SELN_VOL` | 비차익 합계 매도 거래량 | string | Y | 1 |  |
| 31 | `NABT_SMTM_SELN_VOL_RATE` | 비차익 합계 매도 거래량 비율 | string | Y | 1 |  |
| 32 | `NABT_SMTN_SELN_TR_PBMN` | 비차익 합계 매도 거래 대금 | string | Y | 1 |  |
| 33 | `NABT_SMTM_SELN_TR_PBMN_RATE` | 비차익 합계 매도 거래대금 비율 | string | Y | 1 |  |
| 34 | `NABT_SMTN_SHNU_VOL` | 비차익 합계 매수2 거래량 | string | Y | 1 |  |
| 35 | `NABT_SMTM_SHNU_VOL_RATE` | 비차익 합계 매수 거래량 비율 | string | Y | 1 |  |
| 36 | `NABT_SMTN_SHNU_TR_PBMN` | 비차익 합계 매수2 거래 대금 | string | Y | 1 |  |
| 37 | `NABT_SMTM_SHNU_TR_PBMN_RATE` | 비차익 합계 매수 거래대금 비율 | string | Y | 1 |  |
| 38 | `NABT_SMTN_NTBY_QTY` | 비차익 합계 순매수 수량 | string | Y | 1 |  |
| 39 | `NABT_SMTM_NTBY_QTY_RATE` | 비차익 합계 순매수 수량 비율 | string | Y | 1 |  |
| 40 | `NABT_SMTN_NTBY_TR_PBMN` | 비차익 합계 순매수 거래 대금 | string | Y | 1 |  |
| 41 | `NABT_SMTM_NTBY_TR_PBMN_RATE` | 비차익 합계 순매수 거래대금 비 | string | Y | 1 |  |
| 42 | `WHOL_ENTM_SELN_VOL` | 전체 위탁 매도 거래량 | string | Y | 1 |  |
| 43 | `ENTM_SELN_VOL_RATE` | 위탁 매도 거래량 비율 | string | Y | 1 |  |
| 44 | `WHOL_ENTM_SELN_TR_PBMN` | 전체 위탁 매도 거래 대금 | string | Y | 1 |  |
| 45 | `ENTM_SELN_TR_PBMN_RATE` | 위탁 매도 거래대금 비율 | string | Y | 1 |  |
| 46 | `WHOL_ENTM_SHNU_VOL` | 전체 위탁 매수2 거래량 | string | Y | 1 |  |
| 47 | `ENTM_SHNU_VOL_RATE` | 위탁 매수 거래량 비율 | string | Y | 1 |  |
| 48 | `WHOL_ENTM_SHNU_TR_PBMN` | 전체 위탁 매수2 거래 대금 | string | Y | 1 |  |
| 49 | `ENTM_SHNU_TR_PBMN_RATE` | 위탁 매수 거래대금 비율 | string | Y | 1 |  |
| 50 | `WHOL_ENTM_NTBY_QT` | 전체 위탁 순매수 수량 | string | Y | 1 |  |
| 51 | `ENTM_NTBY_QTY_RAT` | 위탁 순매수 수량 비율 | string | Y | 1 |  |
| 52 | `WHOL_ENTM_NTBY_TR_PBMN` | 전체 위탁 순매수 거래 대금 | string | Y | 1 |  |
| 53 | `ENTM_NTBY_TR_PBMN_RATE` | 위탁 순매수 금액 비율 | string | Y | 1 |  |
| 54 | `WHOL_ONSL_SELN_VOL` | 전체 자기 매도 거래량 | string | Y | 1 |  |
| 55 | `ONSL_SELN_VOL_RATE` | 자기 매도 거래량 비율 | string | Y | 1 |  |
| 56 | `WHOL_ONSL_SELN_TR_PBMN` | 전체 자기 매도 거래 대금 | string | Y | 1 |  |
| 57 | `ONSL_SELN_TR_PBMN_RATE` | 자기 매도 거래대금 비율 | string | Y | 1 |  |
| 58 | `WHOL_ONSL_SHNU_VOL` | 전체 자기 매수2 거래량 | string | Y | 1 |  |
| 59 | `ONSL_SHNU_VOL_RATE` | 자기 매수 거래량 비율 | string | Y | 1 |  |
| 60 | `WHOL_ONSL_SHNU_TR_PBMN` | 전체 자기 매수2 거래 대금 | string | Y | 1 |  |
| 61 | `ONSL_SHNU_TR_PBMN_RATE` | 자기 매수 거래대금 비율 | string | Y | 1 |  |
| 62 | `WHOL_ONSL_NTBY_QTY` | 전체 자기 순매수 수량 | string | Y | 1 |  |
| 63 | `ONSL_NTBY_QTY_RATE` | 자기 순매수량 비율 | string | Y | 1 |  |
| 64 | `WHOL_ONSL_NTBY_TR_PBMN` | 전체 자기 순매수 거래 대금 | string | Y | 1 |  |
| 65 | `ONSL_NTBY_TR_PBMN_RATE` | 자기 순매수 대금 비율 | string | Y | 1 |  |
| 66 | `TOTAL_SELN_QTY` | 총 매도 수량 | string | Y | 1 |  |
| 67 | `WHOL_SELN_VOL_RATE` | 전체 매도 거래량 비율 | string | Y | 1 |  |
| 68 | `TOTAL_SELN_TR_PBMN` | 총 매도 거래 대금 | string | Y | 1 |  |
| 69 | `WHOL_SELN_TR_PBMN_RATE` | 전체 매도 거래대금 비율 | string | Y | 1 |  |
| 70 | `SHNU_CNTG_SMTN` | 총 매수 수량 | string | Y | 1 |  |
| 71 | `WHOL_SHUN_VOL_RATE` | 전체 매수 거래량 비율 | string | Y | 1 |  |
| 72 | `TOTAL_SHNU_TR_PBMN` | 총 매수2 거래 대금 | string | Y | 1 |  |
| 73 | `WHOL_SHUN_TR_PBMN_RATE` | 전체 매수 거래대금 비율 | string | Y | 1 |  |
| 74 | `WHOL_NTBY_QTY` | 전체 순매수 수량 | string | Y | 1 |  |
| 75 | `WHOL_SMTM_NTBY_QTY_RATE` | 전체 합계 순매수 수량 비율 | string | Y | 1 |  |
| 76 | `WHOL_NTBY_TR_PBMN` | 전체 순매수 거래 대금 | string | Y | 1 |  |
| 77 | `WHOL_NTBY_TR_PBMN_RATE` | 전체 순매수 거래대금 비율 | string | Y | 1 |  |
| 78 | `ARBT_ENTM_NTBY_QTY` | 차익 위탁 순매수 수량 | string | Y | 1 |  |
| 79 | `ARBT_ENTM_NTBY_TR_PBMN` | 차익 위탁 순매수 거래 대금 | string | Y | 1 |  |
| 80 | `ARBT_ONSL_NTBY_QTY` | 차익 자기 순매수 수량 | string | Y | 1 |  |
| 81 | `ARBT_ONSL_NTBY_TR_PBMN` | 차익 자기 순매수 거래 대금 | string | Y | 1 |  |
| 82 | `NABT_ENTM_NTBY_QTY` | 비차익 위탁 순매수 수량 | string | Y | 1 |  |
| 83 | `NABT_ENTM_NTBY_TR_PBMN` | 비차익 위탁 순매수 거래 대금 | string | Y | 1 |  |
| 84 | `NABT_ONSL_NTBY_QTY` | 비차익 자기 순매수 수량 | string | Y | 1 |  |
| 85 | `NABT_ONSL_NTBY_TR_PBMN` | 비차익 자기 순매수 거래 대금 | string | Y | 1 |  |
| 86 | `ACML_VOL` | 누적 거래량 | string | Y | 1 |  |
| 87 | `ACML_TR_PBMN` | 누적 거래 대금 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0UPPGM0",
            "tr_key": "0001"
        }
    }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0UPPGM0", 
        "tr_key": "0001", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0UPPGM0|001|0001^085913^0^0^0^0^0^0^1^0^0^0^0^0^1^0^10^0^0^0.00^0^0.00^0^
0.00^0^0.00^0^0.00^0^0.00^0^0.00^1^0.00^1^0.00^10^0.00^1^0.00^9^0.00^0^0.00^1^0.00^1^0.00^10^0
.00^1^0.00^9^0.00^0^0.00^0^0.00^0^0.00^0^0.00^0^0.00^0^0.00^0^0.00^1^0.00^1^0.00^10^0.00^1^0.0
0^9^0.00^0^0^0^0^1^9^0^0^0^0
```

</details>



### 국내주식 실시간회원사 (통합)

- **API ID**: 국내주식 실시간회원사 (통합)
- **실전 TR_ID**: H0UNMBC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0UNMBC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | N | 1 | 'B : 법인<br>P : 개인' |
| 2 | `tr_type` | 거래타입 | string | N | 1 | '1 : 등록<br>2 : 해제' |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | '	utf-8' |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0UNMBC0 : 국내주식 주식종목회원사 (통합) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (78)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `SELN2_MBCR_NAME1` | 매도2 회원사명1 | string | Y | 16 |  |
| 2 | `SELN2_MBCR_NAME2` | 매도2 회원사명2 | string | Y | 16 |  |
| 3 | `SELN2_MBCR_NAME3` | 매도2 회원사명3 | string | Y | 16 |  |
| 4 | `SELN2_MBCR_NAME4` | 매도2 회원사명4 | string | Y | 16 |  |
| 5 | `SELN2_MBCR_NAME5` | 매도2 회원사명5 | string | Y | 16 |  |
| 6 | `BYOV_MBCR_NAME1` | 매수 회원사명1 | string | Y | 16 |  |
| 7 | `BYOV_MBCR_NAME2` | 매수 회원사명2 | string | Y | 16 |  |
| 8 | `BYOV_MBCR_NAME3` | 매수 회원사명3 | string | Y | 16 |  |
| 9 | `BYOV_MBCR_NAME4` | 매수 회원사명4 | string | Y | 16 |  |
| 10 | `BYOV_MBCR_NAME5` | 매수 회원사명5 | string | Y | 16 |  |
| 11 | `TOTAL_SELN_QTY1` | 총 매도 수량1 | string | Y | 8 |  |
| 12 | `TOTAL_SELN_QTY2` | 총 매도 수량2 | string | Y | 8 |  |
| 13 | `TOTAL_SELN_QTY3` | 총 매도 수량3 | string | Y | 8 |  |
| 14 | `TOTAL_SELN_QTY4` | 총 매도 수량4 | string | Y | 8 |  |
| 15 | `TOTAL_SELN_QTY5` | 총 매도 수량5 | string | Y | 8 |  |
| 16 | `TOTAL_SHNU_QTY1` | 총 매수2 수량1 | string | Y | 8 |  |
| 17 | `TOTAL_SHNU_QTY2` | 총 매수2 수량2 | string | Y | 8 |  |
| 18 | `TOTAL_SHNU_QTY3` | 총 매수2 수량3 | string | Y | 8 |  |
| 19 | `TOTAL_SHNU_QTY4` | 총 매수2 수량4 | string | Y | 8 |  |
| 20 | `TOTAL_SHNU_QTY5` | 총 매수2 수량5 | string | Y | 8 |  |
| 21 | `SELN_MBCR_GLOB_YN_1` | 매도거래원구분1 | string | Y | 1 |  |
| 22 | `SELN_MBCR_GLOB_YN_2` | 매도거래원구분2 | string | Y | 1 |  |
| 23 | `SELN_MBCR_GLOB_YN_3` | 매도거래원구분3 | string | Y | 1 |  |
| 24 | `SELN_MBCR_GLOB_YN_4` | 매도거래원구분4 | string | Y | 1 |  |
| 25 | `SELN_MBCR_GLOB_YN_5` | 매도거래원구분5 | string | Y | 1 |  |
| 26 | `SHNU_MBCR_GLOB_YN_1` | 매수거래원구분1 | string | Y | 1 |  |
| 27 | `SHNU_MBCR_GLOB_YN_2` | 매수거래원구분2 | string | Y | 1 |  |
| 28 | `SHNU_MBCR_GLOB_YN_3` | 매수거래원구분3 | string | Y | 1 |  |
| 29 | `SHNU_MBCR_GLOB_YN_4` | 매수거래원구분4 | string | Y | 1 |  |
| 30 | `SHNU_MBCR_GLOB_YN_5` | 매수거래원구분5 | string | Y | 1 |  |
| 31 | `SELN_MBCR_NO1` | 매도거래원코드1 | string | Y | 5 |  |
| 32 | `SELN_MBCR_NO2` | 매도거래원코드2 | string | Y | 5 |  |
| 33 | `SELN_MBCR_NO3` | 매도거래원코드3 | string | Y | 5 |  |
| 34 | `SELN_MBCR_NO4` | 매도거래원코드4 | string | Y | 5 |  |
| 35 | `SELN_MBCR_NO5` | 매도거래원코드5 | string | Y | 5 |  |
| 36 | `SHNU_MBCR_NO1` | 매수거래원코드1 | string | Y | 5 |  |
| 37 | `SHNU_MBCR_NO2` | 매수거래원코드2 | string | Y | 5 |  |
| 38 | `SHNU_MBCR_NO3` | 매수거래원코드3 | string | Y | 5 |  |
| 39 | `SHNU_MBCR_NO4` | 매수거래원코드4 | string | Y | 5 |  |
| 40 | `SHNU_MBCR_NO5` | 매수거래원코드5 | string | Y | 5 |  |
| 41 | `SELN_MBCR_RLIM1` | 매도 회원사 비중1 | string | Y | 8 |  |
| 42 | `SELN_MBCR_RLIM2` | 매도 회원사 비중2 | string | Y | 8 |  |
| 43 | `SELN_MBCR_RLIM3` | 매도 회원사 비중3 | string | Y | 8 |  |
| 44 | `SELN_MBCR_RLIM4` | 매도 회원사 비중4 | string | Y | 8 |  |
| 45 | `SELN_MBCR_RLIM5` | 매도 회원사 비중5 | string | Y | 8 |  |
| 46 | `SHNU_MBCR_RLIM1` | 매수2 회원사 비중1 | string | Y | 8 |  |
| 47 | `SHNU_MBCR_RLIM2` | 매수2 회원사 비중2 | string | Y | 8 |  |
| 48 | `SHNU_MBCR_RLIM3` | 매수2 회원사 비중3 | string | Y | 8 |  |
| 49 | `SHNU_MBCR_RLIM4` | 매수2 회원사 비중4 | string | Y | 8 |  |
| 50 | `SHNU_MBCR_RLIM5` | 매수2 회원사 비중5 | string | Y | 8 |  |
| 51 | `SELN_QTY_ICDC1` | 매도 수량 증감1 | string | Y | 4 |  |
| 52 | `SELN_QTY_ICDC2` | 매도 수량 증감2 | string | Y | 4 |  |
| 53 | `SELN_QTY_ICDC3` | 매도 수량 증감3 | string | Y | 4 |  |
| 54 | `SELN_QTY_ICDC4` | 매도 수량 증감4 | string | Y | 4 |  |
| 55 | `SELN_QTY_ICDC5` | 매도 수량 증감5 | string | Y | 4 |  |
| 56 | `SHNU_QTY_ICDC1` | 매수2 수량 증감1 | string | Y | 4 |  |
| 57 | `SHNU_QTY_ICDC2` | 매수2 수량 증감2 | string | Y | 4 |  |
| 58 | `SHNU_QTY_ICDC3` | 매수2 수량 증감3 | string | Y | 4 |  |
| 59 | `SHNU_QTY_ICDC4` | 매수2 수량 증감4 | string | Y | 4 |  |
| 60 | `SHNU_QTY_ICDC5` | 매수2 수량 증감5 | string | Y | 4 |  |
| 61 | `GLOB_TOTAL_SELN_QTY` | 외국계 총 매도 수량 | string | Y | 8 |  |
| 62 | `GLOB_TOTAL_SHNU_QTY` | 외국계 총 매수2 수량 | string | Y | 8 |  |
| 63 | `GLOB_TOTAL_SELN_QTY_ICDC` | 외국계 총 매도 수량 증감 | string | Y | 4 |  |
| 64 | `GLOB_TOTAL_SHNU_QTY_ICDC` | 외국계 총 매수2 수량 증감 | string | Y | 4 |  |
| 65 | `GLOB_NTBY_QTY` | 외국계 순매수 수량 | string | Y | 8 |  |
| 66 | `GLOB_SELN_RLIM` | 외국계 매도 비중 | string | Y | 8 |  |
| 67 | `GLOB_SHNU_RLIM` | 외국계 매수2 비중 | string | Y | 8 |  |
| 68 | `SELN2_MBCR_ENG_NAME1` | 매도2 영문회원사명1 | string | Y | 20 |  |
| 69 | `SELN2_MBCR_ENG_NAME2` | 매도2 영문회원사명2 | string | Y | 20 |  |
| 70 | `SELN2_MBCR_ENG_NAME3` | 매도2 영문회원사명3 | string | Y | 20 |  |
| 71 | `SELN2_MBCR_ENG_NAME4` | 매도2 영문회원사명4 | string | Y | 20 |  |
| 72 | `SELN2_MBCR_ENG_NAME5` | 매도2 영문회원사명5 | string | Y | 20 |  |
| 73 | `BYOV_MBCR_ENG_NAME1` | 매수 영문회원사명1 | string | Y | 20 |  |
| 74 | `BYOV_MBCR_ENG_NAME2` | 매수 영문회원사명2 | string | Y | 20 |  |
| 75 | `BYOV_MBCR_ENG_NAME3` | 매수 영문회원사명3 | string | Y | 20 |  |
| 76 | `BYOV_MBCR_ENG_NAME4` | 매수 영문회원사명4 | string | Y | 20 |  |
| 77 | `BYOV_MBCR_ENG_NAME5` | 매수 영문회원사명5 | string | Y | 20 |  |


### 국내지수 실시간체결

- **API ID**: 실시간-026
- **실전 TR_ID**: H0UPCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0UPCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0UPCNT0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 업종구분코드 |

#### Response Body (30)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `bstp_cls_code` | 업종 구분 코드 | object | Y | 4 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `bsop_hour` | 영업 시간 | string | Y | 6 |  |
| 2 | `prpr_nmix` | 현재가 지수 | string | Y | 1 |  |
| 3 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 |  |
| 4 | `bstp_nmix_prdy_vrss` | 업종 지수 전일 대비 | string | Y | 1 |  |
| 5 | `acml_vol` | 누적 거래량 | string | Y | 1 |  |
| 6 | `acml_tr_pbmn` | 누적 거래 대금 | string | Y | 1 |  |
| 7 | `pcas_vol` | 건별 거래량 | string | Y | 1 |  |
| 8 | `pcas_tr_pbmn` | 건별 거래 대금 | string | Y | 1 |  |
| 9 | `prdy_ctrt` | 전일 대비율 | string | Y | 1 |  |
| 10 | `oprc_nmix` | 시가 지수 | string | Y | 1 |  |
| 11 | `nmix_hgpr` | 지수 최고가 | string | Y | 1 |  |
| 12 | `nmix_lwpr` | 지수 최저가 | string | Y | 1 |  |
| 13 | `oprc_vrss_nmix_prpr` | 시가 대비 지수 현재가 | string | Y | 1 |  |
| 14 | `oprc_vrss_nmix_sign` | 시가 대비 지수 부호 | string | Y | 1 |  |
| 15 | `hgpr_vrss_nmix_prpr` | 최고가 대비 지수 현재가 | string | Y | 1 |  |
| 16 | `hgpr_vrss_nmix_sign` | 최고가 대비 지수 부호 | string | Y | 1 |  |
| 17 | `lwpr_vrss_nmix_prpr` | 최저가 대비 지수 현재가 | string | Y | 1 |  |
| 18 | `lwpr_vrss_nmix_sign` | 최저가 대비 지수 부호 | string | Y | 1 |  |
| 19 | `prdy_clpr_vrss_oprc_rate` | 전일 종가 대비 시가2 비율 | string | Y | 1 |  |
| 20 | `prdy_clpr_vrss_hgpr_rate` | 전일 종가 대비 최고가 비율 | string | Y | 1 |  |
| 21 | `prdy_clpr_vrss_lwpr_rate` | 전일 종가 대비 최저가 비율 | string | Y | 1 |  |
| 22 | `uplm_issu_cnt` | 상한 종목 수 | string | Y | 1 |  |
| 23 | `ascn_issu_cnt` | 상승 종목 수 | string | Y | 1 |  |
| 24 | `stnr_issu_cnt` | 보합 종목 수 | string | Y | 1 |  |
| 25 | `down_issu_cnt` | 하락 종목 수 | string | Y | 1 |  |
| 26 | `lslm_issu_cnt` | 하한 종목 수 | string | Y | 1 |  |
| 27 | `qtqt_ascn_issu_cnt` | 기세 상승 종목수 | string | Y | 1 |  |
| 28 | `qtqt_down_issu_cnt` | 기세 하락 종목수 | string | Y | 1 |  |
| 29 | `tick_vrss` | TICK대비 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0UPCNT0",
            "tr_key": "0001"
        }
    }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0UPCNT0", 
        "tr_key": "0001", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0UPCNT0|001|0001^091240^2624.54^2^32.68^63952^1650684^439^10335^1.26^2615
.72^2624.82^2610.00^23.86^2^32.96^2^18.14^2^0.92^1.27^0.70^0^670^72^177^0^0^0^19
```

</details>



### 국내주식 실시간예상체결 (KRX)

- **API ID**: 실시간-041
- **실전 TR_ID**: H0STANC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STANC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 실시간예상체결 API입니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info


[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)


아래와 같이 건별로 데이터를 수신 받게 되며,
수신받으신 데이터에 대한 처리는 ^기호를 통해 구분 처리하는 것을 권장드립니다.

0|H0STANC0|002|

005930^085130^308000^5^-10000^-3.14^0.00^0^0^0^308000^307500^3^313469^96548452000^0^0^0^0.00^0^0^1^0.01^0.00^000000^3^0^000000^3^0^000000^3^0^20260707^00^N^3502^1437^44094^6872^0.01^0^0.00^B^^318000 -&gt;첫 번째 건의 마지막 뒤 dummy 데이터 318000 추가 

^005930^085130^308000^5^-10000^-3.14^0.00^0^0^0^308000^307500^1^313470^96548760000^0^0^0^0.00^0^0^1^0.01^0.00^000000^3^0^000000^3^0^000000^3^0^20260707^00^N^3531^1437^44123^6872^0.01^0^0.00^B^^318000 -&gt; 번째 건의 마지막 뒤 dummy 데이터 318000 추가
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0STANC0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (46)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식현재가 | string | Y | 4 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비구분 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 4 |  |
| 5 | `PRDY_CTRT` | 등락율 | string | Y | 8 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중평균주식가격 | string | Y | 8 |  |
| 7 | `STCK_OPRC` | 시가 | string | Y | 4 |  |
| 8 | `STCK_HGPR` | 고가 | string | Y | 4 |  |
| 9 | `STCK_LWPR` | 저가 | string | Y | 4 |  |
| 10 | `ASKP1` | 매도호가 | string | Y | 4 |  |
| 11 | `BIDP1` | 매수호가 | string | Y | 4 |  |
| 12 | `CNTG_VOL` | 거래량 | string | Y | 8 |  |
| 13 | `ACML_VOL` | 누적거래량 | string | Y | 8 |  |
| 14 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 8 |  |
| 15 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 4 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 4 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 4 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 19 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 8 |  |
| 20 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 8 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수비율 | string | Y | 8 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 8 |  |
| 24 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가대비구분 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가대비 | string | Y | 4 |  |
| 27 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 고가대비구분 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 고가대비 | string | Y | 4 |  |
| 30 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 저가대비구분 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 저가대비 | string | Y | 4 |  |
| 33 | `BSOP_DATE` | 영업일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신장운영구분코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 8 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 8 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 8 |  |
| 40 | `VOL_TNRT` | 거래량회전율 | string | Y | 8 |  |
| 41 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일동시간누적거래량 | string | Y | 8 |  |
| 42 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일동시간누적거래량비율 | string | Y | 8 |  |
| 43 | `HOUR_CLS_CODE` | 시간구분코드 | string | Y | 1 |  |
| 44 | `MRKT_TRTM_CLS_CODE` | 임의종료구분코드 | string | Y | 1 |  |
| 45 | `dummy(사용하지 않는 필드)` | dummy(사용하지 않는 필드) | number | Y | 4 | 사용하지 않는 필드입니다. |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0STANC0",
                           "tr_key":"005930"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STANC0", 
        "tr_key": "005930", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0STANC0|001|005930^084945^77600^2^1300^1.70^0.00^0^0^0^77600^77
500^64^221986^17226113600^0^0^0^0.00^0^0^1^0.01^0.00^000000^3^0^000000^3^0^000000^3^
0^20240426^00^N^11591^2878^41034^6265^0.00^0^0.00^B^
```

</details>



### ELW 실시간호가

- **API ID**: 실시간-062
- **실전 TR_ID**: H0EWASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0EWASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 실시간호가 API입니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info


[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0EWASP0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | ELW 종목코드(ex. 57LA24) |

#### Response Body (73)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업시간 | string | Y | 6 |  |
| 2 | `HOUR_CLS_CODE` | 시간구분코드 | string | Y | 1 |  |
| 3 | `ASKP1` | 매도호가1 | string | Y | 1 |  |
| 4 | `ASKP2` | 매도호가2 | string | Y | 1 |  |
| 5 | `ASKP3` | 매도호가3 | string | Y | 1 |  |
| 6 | `ASKP4` | 매도호가4 | string | Y | 1 |  |
| 7 | `ASKP5` | 매도호가5 | string | Y | 1 |  |
| 8 | `ASKP6` | 매도호가6 | string | Y | 1 |  |
| 9 | `ASKP7` | 매도호가7 | string | Y | 1 |  |
| 10 | `ASKP8` | 매도호가8 | string | Y | 1 |  |
| 11 | `ASKP9` | 매도호가9 | string | Y | 1 |  |
| 12 | `ASKP10` | 매도호가10 | string | Y | 1 |  |
| 13 | `BIDP1` | 매수호가1 | string | Y | 1 |  |
| 14 | `BIDP2` | 매수호가2 | string | Y | 1 |  |
| 15 | `BIDP3` | 매수호가3 | string | Y | 1 |  |
| 16 | `BIDP4` | 매수호가4 | string | Y | 1 |  |
| 17 | `BIDP5` | 매수호가5 | string | Y | 1 |  |
| 18 | `BIDP6` | 매수호가6 | string | Y | 1 |  |
| 19 | `BIDP7` | 매수호가7 | string | Y | 1 |  |
| 20 | `BIDP8` | 매수호가8 | string | Y | 1 |  |
| 21 | `BIDP9` | 매수호가9 | string | Y | 1 |  |
| 22 | `BIDP10` | 매수호가10 | string | Y | 1 |  |
| 23 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 24 | `ASKP_RSQN2` | 매도호가잔량2 | string | Y | 1 |  |
| 25 | `ASKP_RSQN3` | 매도호가잔량3 | string | Y | 1 |  |
| 26 | `ASKP_RSQN4` | 매도호가잔량4 | string | Y | 1 |  |
| 27 | `ASKP_RSQN5` | 매도호가잔량5 | string | Y | 1 |  |
| 28 | `ASKP_RSQN6` | 매도호가잔량6 | string | Y | 1 |  |
| 29 | `ASKP_RSQN7` | 매도호가잔량7 | string | Y | 1 |  |
| 30 | `ASKP_RSQN8` | 매도호가잔량8 | string | Y | 1 |  |
| 31 | `ASKP_RSQN9` | 매도호가잔량9 | string | Y | 1 |  |
| 32 | `ASKP_RSQN10` | 매도호가잔량10 | string | Y | 1 |  |
| 33 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 34 | `BIDP_RSQN2` | 매수호가잔량2 | string | Y | 1 |  |
| 35 | `BIDP_RSQN3` | 매수호가잔량3 | string | Y | 1 |  |
| 36 | `BIDP_RSQN4` | 매수호가잔량4 | string | Y | 1 |  |
| 37 | `BIDP_RSQN5` | 매수호가잔량5 | string | Y | 1 |  |
| 38 | `BIDP_RSQN6` | 매수호가잔량6 | string | Y | 1 |  |
| 39 | `BIDP_RSQN7` | 매수호가잔량7 | string | Y | 1 |  |
| 40 | `BIDP_RSQN8` | 매수호가잔량8 | string | Y | 1 |  |
| 41 | `BIDP_RSQN9` | 매수호가잔량9 | string | Y | 1 |  |
| 42 | `BIDP_RSQN10` | 매수호가잔량10 | string | Y | 1 |  |
| 43 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 44 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 45 | `ANTC_CNPR` | 예상체결가 | string | Y | 1 |  |
| 46 | `ANTC_CNQN` | 예상체결량 | string | Y | 1 |  |
| 47 | `ANTC_CNTG_VRSS_SIGN` | 예상체결대비부호 | string | Y | 1 |  |
| 48 | `ANTC_CNTG_VRSS` | 예상체결대비 | string | Y | 1 |  |
| 49 | `ANTC_CNTG_PRDY_CTRT` | 예상체결전일대비율 | string | Y | 1 |  |
| 50 | `LP_ASKP_RSQN1` | LP매도호가잔량1 | string | Y | 1 |  |
| 51 | `LP_ASKP_RSQN2` | LP매도호가잔량2 | string | Y | 1 |  |
| 52 | `LP_ASKP_RSQN3` | LP매도호가잔량3 | string | Y | 1 |  |
| 53 | `LP_BIDP_RSQN4` | LP매수호가잔량4 | string | Y | 1 |  |
| 54 | `LP_ASKP_RSQN4` | LP매도호가잔량4 | string | Y | 1 |  |
| 55 | `LP_BIDP_RSQN5` | LP매수호가잔량5 | string | Y | 1 |  |
| 56 | `LP_ASKP_RSQN5` | LP매도호가잔량5 | string | Y | 1 |  |
| 57 | `LP_BIDP_RSQN6` | LP매수호가잔량6 | string | Y | 1 |  |
| 58 | `LP_ASKP_RSQN6` | LP매도호가잔량6 | string | Y | 1 |  |
| 59 | `LP_BIDP_RSQN7` | LP매수호가잔량7 | string | Y | 1 |  |
| 60 | `LP_ASKP_RSQN7` | LP매도호가잔량7 | string | Y | 1 |  |
| 61 | `LP_ASKP_RSQN8` | LP매도호가잔량8 | string | Y | 1 |  |
| 62 | `LP_BIDP_RSQN8` | LP매수호가잔량8 | string | Y | 1 |  |
| 63 | `LP_ASKP_RSQN9` | LP매도호가잔량9 | string | Y | 1 |  |
| 64 | `LP_BIDP_RSQN9` | LP매수호가잔량9 | string | Y | 1 |  |
| 65 | `LP_ASKP_RSQN10` | LP매도호가잔량10 | string | Y | 1 |  |
| 66 | `LP_BIDP_RSQN10` | LP매수호가잔량10 | string | Y | 1 |  |
| 67 | `LP_BIDP_RSQN1` | LP매수호가잔량1 | string | Y | 1 |  |
| 68 | `LP_TOTAL_ASKP_RSQN` | LP총매도호가잔량 | string | Y | 1 |  |
| 69 | `LP_BIDP_RSQN2` | LP매수호가잔량2 | string | Y | 1 |  |
| 70 | `LP_TOTAL_BIDP_RSQN` | LP총매수호가잔량 | string | Y | 1 |  |
| 71 | `LP_BIDP_RSQN3` | LP매수호가잔량3 | string | Y | 1 |  |
| 72 | `ANTC_VOL` | 예상거래량 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0EWASP0",
                           "tr_key":"57JN53"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0EWASP0", 
        "tr_key": "57JN53", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0EWASP0|001|57JN53^090333^0^270^275^280^285^290^295^300^305^310
^315^265^260^255^250^245^240^235^230^225^220^132730^144770^53560^139510^104910^16386
0^111580^41530^66600^41040^119950^176460^142150^218620^148250^160210^154250^141660^1
40270^160640^1000090^1562460^0^0^3^0^0.00^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^0^
0^0
```

</details>



### 국내주식 실시간호가 (KRX)

- **API ID**: 실시간-004
- **실전 TR_ID**: H0STASP0
- **모의 TR_ID**: H0STASP0
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `ws://ops.koreainvestment.com:31000`

<details><summary>개요</summary>

```text
[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id
- 데이터 건수 : (ex. 001 데이터 건수를 참조하여 활용)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | Y | 1 | B : 법인<br>P : 개인 |
| 2 | `tr_type` | 거래타입 | string | Y | 1 | 1 : 등록<br>2 : 해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 1 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 1 | [실전/모의투자]<br>H0STASP0 : 주식호가 |
| 1 | `tr_key` | 구분값 | string | Y | 1 | 종목번호 (6자리)<br>ETN의 경우, Q로 시작 (EX. Q500001) |

#### Response Body (63)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 6 |  |
| 2 | `HOUR_CLS_CODE` | 시간 구분 코드 | string | Y | 1 | 0 : 장중<br>A : 장후예상<br>B : 장전예상<br>C : 9시이후의 예상가, VI발동<br>D : 시간외 단일가 예상 |
| 3 | `ASKP1` | 매도호가1 | number | Y | 4 |  |
| 4 | `ASKP2` | 매도호가2 | number | Y | 4 |  |
| 5 | `ASKP3` | 매도호가3 | number | Y | 4 |  |
| 6 | `ASKP4` | 매도호가4 | number | Y | 4 |  |
| 7 | `ASKP5` | 매도호가5 | number | Y | 4 |  |
| 8 | `ASKP6` | 매도호가6 | number | Y | 4 |  |
| 9 | `ASKP7` | 매도호가7 | number | Y | 4 |  |
| 10 | `ASKP8` | 매도호가8 | number | Y | 4 |  |
| 11 | `ASKP9` | 매도호가9 | number | Y | 4 |  |
| 12 | `ASKP10` | 매도호가10 | number | Y | 4 |  |
| 13 | `BIDP1` | 매수호가1 | number | Y | 4 |  |
| 14 | `BIDP2` | 매수호가2 | number | Y | 4 |  |
| 15 | `BIDP3` | 매수호가3 | number | Y | 4 |  |
| 16 | `BIDP4` | 매수호가4 | number | Y | 4 |  |
| 17 | `BIDP5` | 매수호가5 | number | Y | 4 |  |
| 18 | `BIDP6` | 매수호가6 | number | Y | 4 |  |
| 19 | `BIDP7` | 매수호가7 | number | Y | 4 |  |
| 20 | `BIDP8` | 매수호가8 | number | Y | 4 |  |
| 21 | `BIDP9` | 매수호가9 | number | Y | 4 |  |
| 22 | `BIDP10` | 매수호가10 | number | Y | 4 |  |
| 23 | `ASKP_RSQN1` | 매도호가 잔량1 | number | Y | 8 |  |
| 24 | `ASKP_RSQN2` | 매도호가 잔량2 | number | Y | 8 |  |
| 25 | `ASKP_RSQN3` | 매도호가 잔량3 | number | Y | 8 |  |
| 26 | `ASKP_RSQN4` | 매도호가 잔량4 | number | Y | 8 |  |
| 27 | `ASKP_RSQN5` | 매도호가 잔량5 | number | Y | 8 |  |
| 28 | `ASKP_RSQN6` | 매도호가 잔량6 | number | Y | 8 |  |
| 29 | `ASKP_RSQN7` | 매도호가 잔량7 | number | Y | 8 |  |
| 30 | `ASKP_RSQN8` | 매도호가 잔량8 | number | Y | 8 |  |
| 31 | `ASKP_RSQN9` | 매도호가 잔량9 | number | Y | 8 |  |
| 32 | `ASKP_RSQN10` | 매도호가 잔량10 | number | Y | 8 |  |
| 33 | `BIDP_RSQN1` | 매수호가 잔량1 | number | Y | 8 |  |
| 34 | `BIDP_RSQN2` | 매수호가 잔량2 | number | Y | 8 |  |
| 35 | `BIDP_RSQN3` | 매수호가 잔량3 | number | Y | 8 |  |
| 36 | `BIDP_RSQN4` | 매수호가 잔량4 | number | Y | 8 |  |
| 37 | `BIDP_RSQN5` | 매수호가 잔량5 | number | Y | 8 |  |
| 38 | `BIDP_RSQN6` | 매수호가 잔량6 | number | Y | 8 |  |
| 39 | `BIDP_RSQN7` | 매수호가 잔량7 | number | Y | 8 |  |
| 40 | `BIDP_RSQN8` | 매수호가 잔량8 | number | Y | 8 |  |
| 41 | `BIDP_RSQN9` | 매수호가 잔량9 | number | Y | 8 |  |
| 42 | `BIDP_RSQN10` | 매수호가 잔량10 | number | Y | 8 |  |
| 43 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | number | Y | 8 |  |
| 44 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | number | Y | 8 |  |
| 45 | `OVTM_TOTAL_ASKP_RSQN` | 시간외 총 매도호가 잔량 | number | Y | 8 |  |
| 46 | `OVTM_TOTAL_BIDP_RSQN` | 시간외 총 매수호가 잔량 | number | Y | 8 |  |
| 47 | `ANTC_CNPR` | 예상 체결가 | number | Y | 4 | 동시호가 등 특정 조건하에서만 발생 |
| 48 | `ANTC_CNQN` | 예상 체결량 | number | Y | 8 | 동시호가 등 특정 조건하에서만 발생 |
| 49 | `ANTC_VOL` | 예상 거래량 | number | Y | 8 | 동시호가 등 특정 조건하에서만 발생 |
| 50 | `ANTC_CNTG_VRSS` | 예상 체결 대비 | number | Y | 4 | 동시호가 등 특정 조건하에서만 발생 |
| 51 | `ANTC_CNTG_VRSS_SIGN` | 예상 체결 대비 부호 | string | Y | 1 | 동시호가 등 특정 조건하에서만 발생<br>1 : 상한<br>2 : 상승<br>3 : 보합<br>4 : 하한<br>5 : 하락 |
| 52 | `ANTC_CNTG_PRDY_CTRT` | 예상 체결 전일 대비율 | number | Y | 8 |  |
| 53 | `ACML_VOL` | 누적 거래량 | number | Y | 8 |  |
| 54 | `TOTAL_ASKP_RSQN_ICDC` | 총 매도호가 잔량 증감 | number | Y | 4 |  |
| 55 | `TOTAL_BIDP_RSQN_ICDC` | 총 매수호가 잔량 증감 | number | Y | 4 |  |
| 56 | `OVTM_TOTAL_ASKP_ICDC` | 시간외 총 매도호가 증감 | number | Y | 4 |  |
| 57 | `OVTM_TOTAL_BIDP_ICDC` | 시간외 총 매수호가 증감 | number | Y | 4 |  |
| 58 | `STCK_DEAL_CLS_CODE` | 주식 매매 구분 코드 | string | Y | 2 | 사용 X (삭제된 값) |
| 59 | `MID_PRC` | 중간가 | number | Y | 4 |  |
| 60 | `MIDP_TOTAL_RSQN` | 중간가잔량합계수량 | number | Y | 8 |  |
| 61 | `MIDP_CLS_CODE` | 중간가 매수매도 구분 | string | Y | 1 |  |
| 62 | `MARKET_CLS_CODE` | 장 구분 코드 | string | Y | 1 | **[신규 · 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월)]** 장 구분 코드 — 1:프리 2:정규 3:애프터 5:종가. ⚠️ 공지는 **추가된다**고만 밝히고 파이프 구분 payload 안의 **위치(index)를 명시하지 않았다** — 우리 핸들러는 위치로 파싱하므로 2026-09-14 첫 프레임 실측으로 확정해야 한다 |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0STASP0",
                           "tr_key":"005930"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STASP0", 
        "tr_key": "005930", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
005930^093730^0^71900^72000^72100^72200^72300^72400^72500^72600^72700^72800^71
800^71700^71600^71500^71400^71300^71200^71100^71000^70900^91918^117942^92673^7
9708^106729^141988^176192^113906^134077^104229^95221^159371^220746^284657^2127
42^195370^182710^209747^376432^158171^1159362^2095167^0^0^0^0^525579^-72000^5^
-100.00^3159115^0^8^0^0^0
```

</details>



### 국내주식 실시간체결가 (통합)

- **API ID**: 국내주식 실시간체결가 (통합)
- **실전 TR_ID**: H0UNCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0UNCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | N | 1 | B : 법인 P : 개인 |
| 2 | `tr_type` | 거래타입 | string | N | 1 | 1 : 등록 2 : 해제 |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0UNCNT0 : 실시간 주식 체결가 통합 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (47)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식 현재가 | string | Y | 4 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일 대비 부호 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일 대비 | string | Y | 4 |  |
| 5 | `PRDY_CTRT` | 전일 대비율 | string | Y | 8 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중 평균 주식 가격 | string | Y | 8 |  |
| 7 | `STCK_OPRC` | 주식 시가 | string | Y | 4 |  |
| 8 | `STCK_HGPR` | 주식 최고가 | string | Y | 4 |  |
| 9 | `STCK_LWPR` | 주식 최저가 | string | Y | 4 |  |
| 10 | `ASKP1` | 매도호가1 | string | Y | 4 |  |
| 11 | `BIDP1` | 매수호가1 | string | Y | 4 |  |
| 12 | `CNTG_VOL` | 체결 거래량 | string | Y | 8 |  |
| 13 | `ACML_VOL` | 누적 거래량 | string | Y | 8 |  |
| 14 | `ACML_TR_PBMN` | 누적 거래 대금 | string | Y | 8 |  |
| 15 | `SELN_CNTG_CSNU` | 매도 체결 건수 | string | Y | 4 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수 체결 건수 | string | Y | 4 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수 체결 건수 | string | Y | 4 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 19 | `SELN_CNTG_SMTN` | 총 매도 수량 | string | Y | 8 |  |
| 20 | `SHNU_CNTG_SMTN` | 총 매수 수량 | string | Y | 8 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수비율 | string | Y | 8 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일 거래량 대비 등락율 | string | Y | 8 |  |
| 24 | `OPRC_HOUR` | 시가 시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가대비구분 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가대비 | string | Y | 4 |  |
| 27 | `HGPR_HOUR` | 최고가 시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 고가대비구분 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 고가대비 | string | Y | 4 |  |
| 30 | `LWPR_HOUR` | 최저가 시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 저가대비구분 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 저가대비 | string | Y | 4 |  |
| 33 | `BSOP_DATE` | 영업 일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신 장운영 구분 코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지 여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 8 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 8 |  |
| 40 | `VOL_TNRT` | 거래량 회전율 | string | Y | 8 |  |
| 41 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일 동시간 누적 거래량 | string | Y | 8 |  |
| 42 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일 동시간 누적 거래량 비율 | string | Y | 8 |  |
| 43 | `HOUR_CLS_CODE` | 시간 구분 코드 | string | Y | 1 |  |
| 44 | `MRKT_TRTM_CLS_CODE` | 임의종료구분코드 | string | Y | 1 |  |
| 45 | `VI_STND_PRC` | 정적VI발동기준가 | string | Y | 4 |  |
| 46 | `MARKET_CLS_CODE` | 장 구분 코드 | string | Y | 1 | **[신규 · 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월)]** 장 구분 코드 — 1:프리 2:정규 3:애프터 5:종가. ⚠️ 공지는 **추가된다**고만 밝히고 파이프 구분 payload 안의 **위치(index)를 명시하지 않았다** — 우리 핸들러는 위치로 파싱하므로 2026-09-14 첫 프레임 실측으로 확정해야 한다 |


### 국내주식 실시간호가 (NXT)

- **API ID**: 국내주식 실시간호가 (NXT)
- **실전 TR_ID**: H0NXASP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0NXASP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | N | 1 | 'B : 법인<br>P : 개인' |
| 2 | `tr_type` | 거래타입 | string | N | 1 | '1 : 등록<br>2 : 해제' |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | '	utf-8' |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0NXASP0 : 실시간 주식 호가 (NXT) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (62)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `BSOP_HOUR` | 영업 시간 | string | Y | 6 |  |
| 2 | `HOUR_CLS_CODE` | 시간 구분 코드 | string | Y | 1 |  |
| 3 | `ASKP1` | 매도호가1 | number | Y | 4 |  |
| 4 | `ASKP2` | 매도호가2 | number | Y | 4 |  |
| 5 | `ASKP3` | 매도호가3 | number | Y | 4 |  |
| 6 | `ASKP4` | 매도호가4 | number | Y | 4 |  |
| 7 | `ASKP5` | 매도호가5 | number | Y | 4 |  |
| 8 | `ASKP6` | 매도호가6 | number | Y | 4 |  |
| 9 | `ASKP7` | 매도호가7 | number | Y | 4 |  |
| 10 | `ASKP8` | 매도호가8 | number | Y | 4 |  |
| 11 | `ASKP9` | 매도호가9 | number | Y | 4 |  |
| 12 | `ASKP10` | 매도호가10 | number | Y | 4 |  |
| 13 | `BIDP1` | 매수호가1 | number | Y | 4 |  |
| 14 | `BIDP2` | 매수호가2 | number | Y | 4 |  |
| 15 | `BIDP3` | 매수호가3 | number | Y | 4 |  |
| 16 | `BIDP4` | 매수호가4 | number | Y | 4 |  |
| 17 | `BIDP5` | 매수호가5 | number | Y | 4 |  |
| 18 | `BIDP6` | 매수호가6 | number | Y | 4 |  |
| 19 | `BIDP7` | 매수호가7 | number | Y | 4 |  |
| 20 | `BIDP8` | 매수호가8 | number | Y | 4 |  |
| 21 | `BIDP9` | 매수호가9 | string | Y | 4 |  |
| 22 | `BIDP10` | 매수호가10 | number | Y | 4 |  |
| 23 | `ASKP_RSQN1` | 매도호가 잔량1 | number | Y | 8 |  |
| 24 | `ASKP_RSQN2` | 매도호가 잔량2 | number | Y | 8 |  |
| 25 | `ASKP_RSQN3` | 매도호가 잔량3 | number | Y | 8 |  |
| 26 | `ASKP_RSQN4` | 매도호가 잔량4 | number | Y | 8 |  |
| 27 | `ASKP_RSQN5` | 매도호가 잔량5 | number | Y | 8 |  |
| 28 | `ASKP_RSQN6` | 매도호가 잔량6 | number | Y | 8 |  |
| 29 | `ASKP_RSQN7` | 매도호가 잔량7 | number | Y | 8 |  |
| 30 | `ASKP_RSQN8` | 매도호가 잔량8 | number | Y | 8 |  |
| 31 | `ASKP_RSQN9` | 매도호가 잔량9 | number | Y | 8 |  |
| 32 | `ASKP_RSQN10` | 매도호가 잔량10 | number | Y | 8 |  |
| 33 | `BIDP_RSQN1` | 매수호가 잔량1 | number | Y | 8 |  |
| 34 | `BIDP_RSQN2` | 매수호가 잔량2 | number | Y | 8 |  |
| 35 | `BIDP_RSQN3` | 매수호가 잔량3 | number | Y | 8 |  |
| 36 | `BIDP_RSQN4` | 매수호가 잔량4 | number | Y | 8 |  |
| 37 | `BIDP_RSQN5` | 매수호가 잔량5 | number | Y | 8 |  |
| 38 | `BIDP_RSQN6` | 매수호가 잔량6 | number | Y | 8 |  |
| 39 | `BIDP_RSQN7` | 매수호가 잔량7 | number | Y | 8 |  |
| 40 | `BIDP_RSQN8` | 매수호가 잔량8 | number | Y | 8 |  |
| 41 | `BIDP_RSQN9` | 매수호가 잔량9 | number | Y | 8 |  |
| 42 | `BIDP_RSQN10` | 매수호가 잔량10 | number | Y | 8 |  |
| 43 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | number | Y | 8 |  |
| 44 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | number | Y | 8 |  |
| 45 | `OVTM_TOTAL_ASKP_RSQN` | 시간외 총 매도호가 잔량 | number | Y | 8 |  |
| 46 | `OVTM_TOTAL_BIDP_RSQN` | 시간외 총 매수호가 잔량 | number | Y | 8 |  |
| 47 | `ANTC_CNPR` | 예상 체결가 | number | Y | 4 |  |
| 48 | `ANTC_CNQN` | 예상 체결량 | number | Y | 8 |  |
| 49 | `ANTC_VOL` | 예상 거래량 | string | Y | 8 |  |
| 50 | `ANTC_CNTG_VRSS` | 예상 체결 대비 | number | Y | 4 |  |
| 51 | `ANTC_CNTG_VRSS_SIGN` | 예상 체결 대비 부호 | number | Y | 1 |  |
| 52 | `ANTC_CNTG_PRDY_CTRT` | 예상 체결 전일 대비율 | number | Y | 8 |  |
| 53 | `ACML_VOL` | 누적 거래량 | number | Y | 8 |  |
| 54 | `TOTAL_ASKP_RSQN_ICDC` | 총 매도호가 잔량 증감 | number | Y | 4 |  |
| 55 | `TOTAL_BIDP_RSQN_ICDC` | 총 매수호가 잔량 증감 | number | Y | 4 |  |
| 56 | `OVTM_TOTAL_ASKP_ICDC` | 시간외 총 매도호가 증감 | number | Y | 4 |  |
| 57 | `OVTM_TOTAL_BIDP_ICDC` | 시간외 총 매수호가 증감 | number | Y | 4 |  |
| 58 | `STCK_DEAL_CLS_CODE` | 주식 매매 구분 코드 | string | Y | 2 |  |
| 59 | `NMID_PRC` | NXT 중간가 | number | Y | 4 |  |
| 60 | `NMID_TOTAL_RSQN` | NXT 중간가잔량합계수량 | number | Y | 8 |  |
| 61 | `NMID_CLS_CODE` | NXT 중간가 매수매도 구분 | string | Y | 1 |  |


### 국내주식 실시간프로그램매매 (NXT)

- **API ID**: 국내주식 실시간프로그램매매 (NXT)
- **실전 TR_ID**: H0NXPGM0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0NXPGM0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | N | 1 | 'B : 법인<br>P : 개인' |
| 2 | `tr_type` | 거래타입 | string | N | 1 | '1 : 등록<br>2 : 해제' |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | '	utf-8' |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0NXPGM0 : 실시간 주식프로그램매매 (NXT) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 |  |
| 2 | `SELN_CNQN` | 매도 체결량 | string | Y | 8 |  |
| 3 | `SELN_TR_PBMN` | 매도 거래 대금 | string | Y | 8 |  |
| 4 | `SHNU_CNQN` | 매수2 체결량 | string | Y | 8 |  |
| 5 | `SHNU_TR_PBMN` | 매수2 거래 대금 | string | Y | 8 |  |
| 6 | `NTBY_CNQN` | 순매수 체결량 | string | Y | 8 |  |
| 7 | `NTBY_TR_PBMN` | 순매수 거래 대금 | string | Y | 8 |  |
| 8 | `SELN_RSQN` | 매도호가잔량 | string | Y | 8 |  |
| 9 | `SHNU_RSQN` | 매수호가잔량 | string | Y | 8 |  |
| 10 | `WHOL_NTBY_QTY` | 전체순매수호가잔량 | string | Y | 8 |  |


### 국내주식 실시간체결가 (NXT)

- **API ID**: 국내주식 실시간체결가 (NXT)
- **실전 TR_ID**: H0NXCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0NXCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객타입 | string | N | 1 | 'B : 법인<br>P : 개인' |
| 2 | `tr_type` | 거래타입 | string | N | 1 | '1 : 등록<br>2 : 해제' |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | '	utf-8' |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0NXCNT0 : 주식종목체결 (NXT) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (47)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권 단축 종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식 체결 시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식 현재가 | string | Y | 4 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일 대비 부호 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일 대비 | string | Y | 4 |  |
| 5 | `PRDY_CTRT` | 전일 대비율 | string | Y | 8 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중 평균 주식 가격 | string | Y | 8 |  |
| 7 | `STCK_OPRC` | 주식 시가 | string | Y | 4 |  |
| 8 | `STCK_HGPR` | 주식 최고가 | string | Y | 4 |  |
| 9 | `STCK_LWPR` | 주식 최저가 | string | Y | 4 |  |
| 10 | `ASKP1` | 매도호가1 | string | Y | 4 |  |
| 11 | `BIDP1` | 매수호가1 | string | Y | 4 |  |
| 12 | `CNTG_VOL` | 체결 거래량 | string | Y | 8 |  |
| 13 | `ACML_VOL` | 누적 거래량 | string | Y | 8 |  |
| 14 | `ACML_TR_PBMN` | 누적 거래 대금 | string | Y | 8 |  |
| 15 | `SELN_CNTG_CSNU` | 매도 체결 건수 | string | Y | 4 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수 체결 건수 | string | Y | 4 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수 체결 건수 | string | Y | 4 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 19 | `SELN_CNTG_SMTN` | 총 매도 수량 | string | Y | 8 |  |
| 20 | `SHNU_CNTG_SMTN` | 총 매수 수량 | string | Y | 8 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수비율 | string | Y | 8 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일 거래량 대비 등락율 | string | Y | 8 |  |
| 24 | `OPRC_HOUR` | 시가 시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가대비구분 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가대비 | string | Y | 4 |  |
| 27 | `HGPR_HOUR` | 최고가 시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 고가대비구분 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 고가대비 | string | Y | 4 |  |
| 30 | `LWPR_HOUR` | 최저가 시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 저가대비구분 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 저가대비 | string | Y | 4 |  |
| 33 | `BSOP_DATE` | 영업 일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신 장운영 구분 코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지 여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가 잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가 잔량1 | string | Y | 8 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총 매도호가 잔량 | string | Y | 8 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총 매수호가 잔량 | string | Y | 8 |  |
| 40 | `VOL_TNRT` | 거래량 회전율 | string | Y | 8 |  |
| 41 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일 동시간 누적 거래량 | string | Y | 8 |  |
| 42 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일 동시간 누적 거래량 비율 | string | Y | 8 |  |
| 43 | `HOUR_CLS_CODE` | 시간 구분 코드 | string | Y | 1 |  |
| 44 | `MRKT_TRTM_CLS_CODE` | 임의종료구분코드 | string | Y | 1 |  |
| 45 | `VI_STND_PRC` | 정적VI발동기준가 | string | Y | 4 |  |
| 46 | `MARKET_CLS_CODE` | 장 구분 코드 | string | Y | 1 | **[신규 · 공지 2026-09-09 「[중요] KRX 애프터마켓 도입 및 NXT 제도 변경에 따른 안내」 · 시행 2026-09-14(월)]** 장 구분 코드 — 1:프리 2:정규 3:애프터 5:종가. ⚠️ 공지는 **추가된다**고만 밝히고 파이프 구분 payload 안의 **위치(index)를 명시하지 않았다** — 우리 핸들러는 위치로 파싱하므로 2026-09-14 첫 프레임 실측으로 확정해야 한다 |


### ELW 실시간체결가

- **API ID**: 실시간-061
- **실전 TR_ID**: H0EWCNT0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0EWCNT0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 실시간체결가 API입니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info


[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0EWCNT0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | ELW 종목코드(ex. 57LA24) |

#### Response Body (63)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식현재가 | string | Y | 4 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비부호 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 4 |  |
| 5 | `PRDY_CTRT` | 전일대비율 | string | Y | 8 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중평균주식가격 | string | Y | 8 |  |
| 7 | `STCK_OPRC` | 주식시가2 | string | Y | 4 |  |
| 8 | `STCK_HGPR` | 주식최고가 | string | Y | 4 |  |
| 9 | `STCK_LWPR` | 주식최저가 | string | Y | 4 |  |
| 10 | `ASKP1` | 매도호가1 | string | Y | 4 |  |
| 11 | `BIDP1` | 매수호가1 | string | Y | 4 |  |
| 12 | `CNTG_VOL` | 체결거래량 | string | Y | 8 |  |
| 13 | `ACML_VOL` | 누적거래량 | string | Y | 8 |  |
| 14 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 8 |  |
| 15 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 4 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 4 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 4 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 19 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 8 |  |
| 20 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 8 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분코드 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수2비율 | string | Y | 8 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 8 |  |
| 24 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가2대비현재가부호 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가2대비현재가 | string | Y | 4 |  |
| 27 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 최고가대비현재가부호 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 최고가대비현재가 | string | Y | 4 |  |
| 30 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 최저가대비현재가부호 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 최저가대비현재가 | string | Y | 4 |  |
| 33 | `BSOP_DATE` | 영업일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신장운영구분코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 8 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 8 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 8 |  |
| 40 | `TMVL_VAL` | 시간가치값 | string | Y | 8 |  |
| 41 | `PRIT` | 패리티 | string | Y | 8 |  |
| 42 | `PRMM_VAL` | 프리미엄값 | string | Y | 8 |  |
| 43 | `GEAR` | 기어링 | string | Y | 8 |  |
| 44 | `PRLS_QRYR_RATE` | 손익분기비율 | string | Y | 8 |  |
| 45 | `INVL_VAL` | 내재가치값 | string | Y | 8 |  |
| 46 | `PRMM_RATE` | 프리미엄비율 | string | Y | 8 |  |
| 47 | `CFP` | 자본지지점 | string | Y | 8 |  |
| 48 | `LVRG_VAL` | 레버리지값 | string | Y | 8 |  |
| 49 | `DELTA` | 델타 | string | Y | 8 |  |
| 50 | `GAMA` | 감마 | string | Y | 8 |  |
| 51 | `VEGA` | 베가 | string | Y | 8 |  |
| 52 | `THETA` | 세타 | string | Y | 8 |  |
| 53 | `RHO` | 로우 | string | Y | 8 |  |
| 54 | `HTS_INTS_VLTL` | HTS내재변동성 | string | Y | 8 |  |
| 55 | `HTS_THPR` | HTS이론가 | string | Y | 8 |  |
| 56 | `VOL_TNRT` | 거래량회전율 | string | Y | 8 |  |
| 57 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일동시간누적거래량 | string | Y | 8 |  |
| 58 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일동시간누적거래량비율 | string | Y | 8 |  |
| 59 | `APPRCH_RATE` | 접근도 | string | Y | 8 |  |
| 60 | `LP_HVOL` | LP보유량 | string | Y | 8 |  |
| 61 | `LP_HLDN_RATE` | LP보유비율 | string | Y | 8 |  |
| 62 | `LP_NTBY_QTY` | LP순매도량 | string | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0EWCNT0",
                           "tr_key":"57JN53"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0EWCNT0", 
        "tr_key": "57JN53", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0EWCNT0|001|57JN53^090333^265^2^50^23.26^285.39^305^310^255^265
^260^50^5071350^1447312100^560^310^-250^78.69^2650440^2085570^1^0.42^11.49^090019^5^
-40^090019^5^-45^090316^2^10^20240426^20^N^33300^181460^992350^1655180^265.00^98.62^
1.99^133.32^2.14^0.00^0.00^2.15^49.09^0.37^0.03^24.30^29.04^4.15^17.94^293.24^50.71^
0^0.00^0.00^0^0.00^0
```

</details>



### ELW 실시간예상체결

- **API ID**: 실시간-063
- **실전 TR_ID**: H0EWANC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0EWANC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 실시간예상체결 API입니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info


[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0EWANC0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | ELW 종목코드(ex. 57LA24) |

#### Response Body (59)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식현재가 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비부호 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 1 |  |
| 5 | `PRDY_CTRT` | 전일대비율 | string | Y | 1 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중평균주식가격 | string | Y | 1 |  |
| 7 | `STCK_OPRC` | 주식시가2 | string | Y | 1 |  |
| 8 | `STCK_HGPR` | 주식최고가 | string | Y | 1 |  |
| 9 | `STCK_LWPR` | 주식최저가 | string | Y | 1 |  |
| 10 | `ASKP1` | 매도호가1 | string | Y | 1 |  |
| 11 | `BIDP1` | 매수호가1 | string | Y | 1 |  |
| 12 | `CNTG_VOL` | 체결거래량 | string | Y | 1 |  |
| 13 | `ACML_VOL` | 누적거래량 | string | Y | 1 |  |
| 14 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 1 |  |
| 15 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 1 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 1 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 1 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 1 |  |
| 19 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 1 |  |
| 20 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 1 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분코드 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수2비율 | string | Y | 1 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 1 |  |
| 24 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가2대비현재가부호 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가2대비현재가 | string | Y | 1 |  |
| 27 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 최고가대비현재가부호 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 최고가대비현재가 | string | Y | 1 |  |
| 30 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 최저가대비현재가부호 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 최저가대비현재가 | string | Y | 1 |  |
| 33 | `BSOP_DATE` | 영업일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신장운영구분코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 37 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 40 | `TMVL_VAL` | 시간가치값 | string | Y | 1 |  |
| 41 | `PRIT` | 패리티 | string | Y | 1 |  |
| 42 | `PRMM_VAL` | 프리미엄값 | string | Y | 1 |  |
| 43 | `GEAR` | 기어링 | string | Y | 1 |  |
| 44 | `PRLS_QRYR_RATE` | 손익분기비율 | string | Y | 1 |  |
| 45 | `INVL_VAL` | 내재가치값 | string | Y | 1 |  |
| 46 | `PRMM_RATE` | 프리미엄비율 | string | Y | 1 |  |
| 47 | `CFP` | 자본지지점 | string | Y | 1 |  |
| 48 | `LVRG_VAL` | 레버리지값 | string | Y | 1 |  |
| 49 | `DELTA` | 델타 | string | Y | 1 |  |
| 50 | `GAMA` | 감마 | string | Y | 1 |  |
| 51 | `VEGA` | 베가 | string | Y | 1 |  |
| 52 | `THETA` | 세타 | string | Y | 1 |  |
| 53 | `RHO` | 로우 | string | Y | 1 |  |
| 54 | `HTS_INTS_VLTL` | HTS내재변동성 | string | Y | 1 |  |
| 55 | `HTS_THPR` | HTS이론가 | string | Y | 1 |  |
| 56 | `VOL_TNRT` | 거래량회전율 | string | Y | 1 |  |
| 57 | `LP_HVOL` | LP보유량 | string | Y | 1 |  |
| 58 | `LP_HLDN_RATE` | LP보유비율 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0EWANC0",
                           "tr_key":"57JN53"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0EWANC0", 
        "tr_key": "57JN53", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
```

</details>



### 국내주식 실시간예상체결 (NXT)

- **API ID**: 국내주식 실시간예상체결 (NXT)
- **실전 TR_ID**: H0NXANC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0NXANC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 실시간예상체결 (NXT)입니다.

아래와 같이 건별로 데이터를 수신 받게 되며,
수신받으신 데이터에 대한 처리는 ^기호를 통해 구분 처리하는 것을 권장드립니다.

0|H0NXANC0|002|

005930^085130^308000^5^-10000^-3.14^0.00^0^0^0^308000^307500^3^313469^96548452000^0^0^0^0.00^0^0^1^0.01^0.00^000000^3^0^000000^3^0^000000^3^0^20260707^00^N^3502^1437^44094^6872^0.01^0^0.00^B^^318000 -&gt;첫 번째 건의 마지막 뒤 dummy 데이터 318000 추가 

^005930^085130^308000^5^-10000^-3.14^0.00^0^0^0^308000^307500^1^313470^96548760000^0^0^0^0.00^0^0^1^0.01^0.00^000000^3^0^000000^3^0^000000^3^0^20260707^00^N^3531^1437^44123^6872^0.01^0^0.00^B^^318000 -&gt; 번째 건의 마지막 뒤 dummy 데이터 318000 추가
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | N | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 2 | `tr_type` | 거래타입 | string | N | 1 | 1 : 등록<br>2 : 해제 |
| 3 | `content-type` | 컨텐츠타입 | string | N | 1 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0NXANC0 : 국내주식 실시간예상체결 (NXT) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (47)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식현재가 | string | Y | 4 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비구분 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 4 |  |
| 5 | `PRDY_CTRT` | 등락율 | string | Y | 8 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중평균주식가격 | string | Y | 8 |  |
| 7 | `STCK_OPRC` | 시가 | string | Y | 4 |  |
| 8 | `STCK_HGPR` | 고가 | string | Y | 4 |  |
| 9 | `STCK_LWPR` | 저가 | string | Y | 4 |  |
| 10 | `ASKP1` | 매도호가 | string | Y | 4 |  |
| 11 | `BIDP1` | 매수호가 | string | Y | 4 |  |
| 12 | `CNTG_VOL` | 거래량 | string | Y | 8 |  |
| 13 | `ACML_VOL` | 누적거래량 | string | Y | 8 |  |
| 14 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 8 |  |
| 15 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 4 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 4 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 4 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 19 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 8 |  |
| 20 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 8 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수비율 | string | Y | 8 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 8 |  |
| 24 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가대비구분 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가대비 | string | Y | 4 |  |
| 27 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 고가대비구분 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 고가대비 | string | Y | 4 |  |
| 30 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 저가대비구분 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 저가대비 | string | Y | 4 |  |
| 33 | `BSOP_DATE` | 영업일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신장운영구분코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 8 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 8 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 8 |  |
| 40 | `VOL_TNRT` | 거래량회전율 | string | Y | 8 |  |
| 41 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일동시간누적거래량 | string | Y | 8 |  |
| 42 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일동시간누적거래량비율 | string | Y | 8 |  |
| 43 | `HOUR_CLS_CODE` | 시간구분코드 | string | Y | 1 |  |
| 44 | `MRKT_TRTM_CLS_CODE` | 임의종료구분코드 | string | Y | 1 |  |
| 45 | `VI_STND_PRC` | VI 상태값 | string | Y | 4 |  |
| 46 | `dummy(사용하지 않는 필드)` | dummy(사용하지 않는 필드) | number | Y | 4 | 사용하지 않는 필드입니다. |


### 국내주식 실시간회원사 (KRX)

- **API ID**: 실시간-047
- **실전 TR_ID**: H0STMBC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STMBC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info

[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | "1: 등록, 2:해제" |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 7 | H0STMBC0 |
| 1 | `tr_key` | 종목코드 | string | Y | 6 | 종목코드 |

#### Response Body (78)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | object | Y | 9 | '각 항목사이에는 구분자로 ^ 사용,<br>모든 데이터타입은 String으로 변환되어 push 처리됨' |
| 1 | `SELN2_MBCR_NAME1` | 매도2회원사명1 | string | Y | 16 |  |
| 2 | `SELN2_MBCR_NAME2` | 매도2회원사명2 | string | Y | 16 |  |
| 3 | `SELN2_MBCR_NAME3` | 매도2회원사명3 | string | Y | 16 |  |
| 4 | `SELN2_MBCR_NAME4` | 매도2회원사명4 | string | Y | 16 |  |
| 5 | `SELN2_MBCR_NAME5` | 매도2회원사명5 | string | Y | 16 |  |
| 6 | `BYOV_MBCR_NAME1` | 매수회원사명1 | string | Y | 16 |  |
| 7 | `BYOV_MBCR_NAME2` | 매수회원사명2 | string | Y | 16 |  |
| 8 | `BYOV_MBCR_NAME3` | 매수회원사명3 | string | Y | 16 |  |
| 9 | `BYOV_MBCR_NAME4` | 매수회원사명4 | string | Y | 16 |  |
| 10 | `BYOV_MBCR_NAME5` | 매수회원사명5 | string | Y | 16 |  |
| 11 | `TOTAL_SELN_QTY1` | 총매도수량1 | string | Y | 8 |  |
| 12 | `TOTAL_SELN_QTY2` | 총매도수량2 | string | Y | 8 |  |
| 13 | `TOTAL_SELN_QTY3` | 총매도수량3 | string | Y | 8 |  |
| 14 | `TOTAL_SELN_QTY4` | 총매도수량4 | string | Y | 8 |  |
| 15 | `TOTAL_SELN_QTY5` | 총매도수량5 | string | Y | 8 |  |
| 16 | `TOTAL_SHNU_QTY1` | 총매수2수량1 | string | Y | 8 |  |
| 17 | `TOTAL_SHNU_QTY2` | 총매수2수량2 | string | Y | 8 |  |
| 18 | `TOTAL_SHNU_QTY3` | 총매수2수량3 | string | Y | 8 |  |
| 19 | `TOTAL_SHNU_QTY4` | 총매수2수량4 | string | Y | 8 |  |
| 20 | `TOTAL_SHNU_QTY5` | 총매수2수량5 | string | Y | 8 |  |
| 21 | `SELN_MBCR_GLOB_YN_1` | 매도거래원구분1 | string | Y | 1 |  |
| 22 | `SELN_MBCR_GLOB_YN_2` | 매도거래원구분2 | string | Y | 1 |  |
| 23 | `SELN_MBCR_GLOB_YN_3` | 매도거래원구분3 | string | Y | 1 |  |
| 24 | `SELN_MBCR_GLOB_YN_4` | 매도거래원구분4 | string | Y | 1 |  |
| 25 | `SELN_MBCR_GLOB_YN_5` | 매도거래원구분5 | string | Y | 1 |  |
| 26 | `SHNU_MBCR_GLOB_YN_1` | 매수거래원구분1 | string | Y | 1 |  |
| 27 | `SHNU_MBCR_GLOB_YN_2` | 매수거래원구분2 | string | Y | 1 |  |
| 28 | `SHNU_MBCR_GLOB_YN_3` | 매수거래원구분3 | string | Y | 1 |  |
| 29 | `SHNU_MBCR_GLOB_YN_4` | 매수거래원구분4 | string | Y | 1 |  |
| 30 | `SHNU_MBCR_GLOB_YN_5` | 매수거래원구분5 | string | Y | 1 |  |
| 31 | `SELN_MBCR_NO1` | 매도거래원코드1 | string | Y | 5 |  |
| 32 | `SELN_MBCR_NO2` | 매도거래원코드2 | string | Y | 5 |  |
| 33 | `SELN_MBCR_NO3` | 매도거래원코드3 | string | Y | 5 |  |
| 34 | `SELN_MBCR_NO4` | 매도거래원코드4 | string | Y | 5 |  |
| 35 | `SELN_MBCR_NO5` | 매도거래원코드5 | string | Y | 5 |  |
| 36 | `SHNU_MBCR_NO1` | 매수거래원코드1 | string | Y | 5 |  |
| 37 | `SHNU_MBCR_NO2` | 매수거래원코드2 | string | Y | 5 |  |
| 38 | `SHNU_MBCR_NO3` | 매수거래원코드3 | string | Y | 5 |  |
| 39 | `SHNU_MBCR_NO4` | 매수거래원코드4 | string | Y | 5 |  |
| 40 | `SHNU_MBCR_NO5` | 매수거래원코드5 | string | Y | 5 |  |
| 41 | `SELN_MBCR_RLIM1` | 매도회원사비중1 | string | Y | 8 |  |
| 42 | `SELN_MBCR_RLIM2` | 매도회원사비중2 | string | Y | 8 |  |
| 43 | `SELN_MBCR_RLIM3` | 매도회원사비중3 | string | Y | 8 |  |
| 44 | `SELN_MBCR_RLIM4` | 매도회원사비중4 | string | Y | 8 |  |
| 45 | `SELN_MBCR_RLIM5` | 매도회원사비중5 | string | Y | 8 |  |
| 46 | `SHNU_MBCR_RLIM1` | 매수2회원사비중1 | string | Y | 8 |  |
| 47 | `SHNU_MBCR_RLIM2` | 매수2회원사비중2 | string | Y | 8 |  |
| 48 | `SHNU_MBCR_RLIM3` | 매수2회원사비중3 | string | Y | 8 |  |
| 49 | `SHNU_MBCR_RLIM4` | 매수2회원사비중4 | string | Y | 8 |  |
| 50 | `SHNU_MBCR_RLIM5` | 매수2회원사비중5 | string | Y | 8 |  |
| 51 | `SELN_QTY_ICDC1` | 매도수량증감1 | string | Y | 4 |  |
| 52 | `SELN_QTY_ICDC2` | 매도수량증감2 | string | Y | 4 |  |
| 53 | `SELN_QTY_ICDC3` | 매도수량증감3 | string | Y | 4 |  |
| 54 | `SELN_QTY_ICDC4` | 매도수량증감4 | string | Y | 4 |  |
| 55 | `SELN_QTY_ICDC5` | 매도수량증감5 | string | Y | 4 |  |
| 56 | `SHNU_QTY_ICDC1` | 매수2수량증감1 | string | Y | 4 |  |
| 57 | `SHNU_QTY_ICDC2` | 매수2수량증감2 | string | Y | 4 |  |
| 58 | `SHNU_QTY_ICDC3` | 매수2수량증감3 | string | Y | 4 |  |
| 59 | `SHNU_QTY_ICDC4` | 매수2수량증감4 | string | Y | 4 |  |
| 60 | `SHNU_QTY_ICDC5` | 매수2수량증감5 | string | Y | 4 |  |
| 61 | `GLOB_TOTAL_SELN_QTY` | 외국계총매도수량 | string | Y | 8 |  |
| 62 | `GLOB_TOTAL_SHNU_QTY` | 외국계총매수2수량 | string | Y | 8 |  |
| 63 | `GLOB_TOTAL_SELN_QTY_ICDC` | 외국계총매도수량증감 | string | Y | 4 |  |
| 64 | `GLOB_TOTAL_SHNU_QTY_ICDC` | 외국계총매수2수량증감 | string | Y | 4 |  |
| 65 | `GLOB_NTBY_QTY` | 외국계순매수수량 | string | Y | 8 |  |
| 66 | `GLOB_SELN_RLIM` | 외국계매도비중 | string | Y | 8 |  |
| 67 | `GLOB_SHNU_RLIM` | 외국계매수2비중 | string | Y | 8 |  |
| 68 | `SELN2_MBCR_ENG_NAME1` | 매도2영문회원사명1 | string | Y | 20 |  |
| 69 | `SELN2_MBCR_ENG_NAME2` | 매도2영문회원사명2 | string | Y | 20 |  |
| 70 | `SELN2_MBCR_ENG_NAME3` | 매도2영문회원사명3 | string | Y | 20 |  |
| 71 | `SELN2_MBCR_ENG_NAME4` | 매도2영문회원사명4 | string | Y | 20 |  |
| 72 | `SELN2_MBCR_ENG_NAME5` | 매도2영문회원사명5 | string | Y | 20 |  |
| 73 | `BYOV_MBCR_ENG_NAME1` | 매수영문회원사명1 | string | Y | 20 |  |
| 74 | `BYOV_MBCR_ENG_NAME2` | 매수영문회원사명2 | string | Y | 20 |  |
| 75 | `BYOV_MBCR_ENG_NAME3` | 매수영문회원사명3 | string | Y | 20 |  |
| 76 | `BYOV_MBCR_ENG_NAME4` | 매수영문회원사명4 | string | Y | 20 |  |
| 77 | `BYOV_MBCR_ENG_NAME5` | 매수영문회원사명5 | string | Y | 20 |  |

<details><summary>Request Example (Python)</summary>

```json
{
    "header": {
        "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
        "custtype": "P",
        "tr_type": "1",
        "content-type": "utf-8"
    },
    "body": {
        "input": {
            "tr_id": "H0STMBC0",
            "tr_key": "005930"
        }
    }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STMBC0", 
        "tr_key": "005930", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0STMBC0|001|005930^씨티그룹^미래에셋증권^모간서울^BNK증권^키움증권^미래
에셋증권^BNK증권^맥쿼리^NH투자증권^한국증권^903482^703873^484082^471203^246578^946273^571760^
343109^313536^311982^Y^N^Y^N^N^N^N^Y^N^N^00037^00005^00036^00086^00050^00005^00086^00035^0001
2^00003^19.06^14.85^10.21^9.94^5.20^19.96^12.06^7.24^6.61^6.58^14913^5054^7240^80000^3532^280
24^42986^0^5612^3043^1387564^681749^22153^0^-705815^29.27^14.38^^^^^^^^^^
```

</details>



### 국내주식 실시간예상체결 (통합)

- **API ID**: 국내주식 실시간예상체결 (통합)
- **실전 TR_ID**: H0UNANC0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0UNANC0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 실시간예상체결 (통합)입니다.

아래와 같이 건별로 데이터를 수신 받게 되며,
수신받으신 데이터에 대한 처리는 ^기호를 통해 구분 처리하는 것을 권장드립니다.

0|H0UNANC0|002|

005930^085130^308000^5^-10000^-3.14^0.00^0^0^0^308000^307500^3^313469^96548452000^0^0^0^0.00^0^0^1^0.01^0.00^000000^3^0^000000^3^0^000000^3^0^20260707^00^N^3502^1437^44094^6872^0.01^0^0.00^B^^318000 -&gt;첫 번째 건의 마지막 뒤 dummy 데이터 318000 추가 

^005930^085130^308000^5^-10000^-3.14^0.00^0^0^0^308000^307500^1^313470^96548760000^0^0^0^0.00^0^0^1^0.01^0.00^000000^3^0^000000^3^0^000000^3^0^20260707^00^N^3531^1437^44123^6872^0.01^0^0.00^B^^318000 -&gt; 번째 건의 마지막 뒤 dummy 데이터 318000 추가
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 2 | `tr_type` | 거래타입 | string | Y | 1 | 1 : 등록<br>2 : 해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 1 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | [실전투자]<br>H0UNANC0 : 국내주식 실시간예상체결 (통합) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (47)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식현재가 | string | Y | 4 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비구분 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 4 |  |
| 5 | `PRDY_CTRT` | 등락율 | string | Y | 8 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중평균주식가격 | string | Y | 8 |  |
| 7 | `STCK_OPRC` | 시가 | string | Y | 4 |  |
| 8 | `STCK_HGPR` | 고가 | string | Y | 4 |  |
| 9 | `STCK_LWPR` | 저가 | string | Y | 4 |  |
| 10 | `ASKP1` | 매도호가 | string | Y | 4 |  |
| 11 | `BIDP1` | 매수호가 | string | Y | 4 |  |
| 12 | `CNTG_VOL` | 거래량 | string | Y | 8 |  |
| 13 | `ACML_VOL` | 누적거래량 | string | Y | 8 |  |
| 14 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 8 |  |
| 15 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 4 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 4 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 4 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 8 |  |
| 19 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 8 |  |
| 20 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 8 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수비율 | string | Y | 8 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 8 |  |
| 24 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가대비구분 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가대비 | string | Y | 4 |  |
| 27 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 고가대비구분 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 고가대비 | string | Y | 4 |  |
| 30 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 저가대비구분 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 저가대비 | string | Y | 4 |  |
| 33 | `BSOP_DATE` | 영업일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신장운영구분코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 8 |  |
| 37 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 8 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 8 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 8 |  |
| 40 | `VOL_TNRT` | 거래량회전율 | string | Y | 8 |  |
| 41 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일동시간누적거래량 | string | Y | 8 |  |
| 42 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일동시간누적거래량비율 | string | Y | 8 |  |
| 43 | `HOUR_CLS_CODE` | 시간구분코드 | string | Y | 1 |  |
| 44 | `MRKT_TRTM_CLS_CODE` | 임의종료구분코드 | string | Y | 1 |  |
| 45 | `VI_STND_PRC` | VI 상태값 | string | Y | 4 |  |
| 46 | `dummy(사용하지 않는 필드)` | dummy(사용하지 않는 필드) | number | Y | 4 | 사용하지 않는 필드입니다. |


### 국내주식 장운영정보 (NXT)

> 🟡 **[공지 2026-09-09 · 시행 2026-09-14(월)] NXT 제도 변경 — 이 채널이 나르는 상태값의 의미가 넓어진다.**
> ① **단일가 도입** — 거래 정지 후 재개 시 매매 방식이 **단일가매매**로 바뀐다(호가접수 30초).
> ② **VI 제도 개선** — VI 발동 시 체결 방식이 **단일가매매(2분)** 로 바뀌고, **정적 VI 가 신규 도입**된다.
> ③ **프리마켓 전용호가 GTP** 신설 — 미체결잔량은 **프리마켓 종료(08:50)에 일괄 취소**된다
>    (주문 쪽 `ORD_DVSN` 27·28·29 — `domestic-stock-order.md` 주식주문(현금)/(신용)/(정정취소) 참조).
> ⚠️ 공지는 위 변경에 **신규 필드를 명시하지 않았다** — 기존 `트레이딩종료구분코드`·`VI 상태값` 등의
> 값 분포가 바뀌는 형태인지는 2026-09-14 이후 실측으로 확인한다.

- **API ID**: 국내주식 장운영정보 (NXT)
- **실전 TR_ID**: H0NXMKO0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: POST
- **URL**: `/tryitout/H0NXMKO0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 286 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 2 | `tr_type` | 거래타입 | string | Y | 1 | 1 : 등록<br>2 : 해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 1 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0NXMKO0 : 국내주식 장운영정보 (NXT) |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 종목코드 | string | Y | 9 |  |
| 1 | `TRHT_YN` | 거래정지 여부 | string | Y | 1 |  |
| 2 | `TR_SUSP_REAS_CNTT` | 거래 정지 사유 내용 | string | Y | 100 |  |
| 3 | `MKOP_CLS_CODE` | 장운영 구분 코드 | string | Y | 3 |  |
| 4 | `ANTC_MKOP_CLS_CODE` | 예상 장운영 구분 코드 | string | Y | 3 |  |
| 5 | `MRKT_TRTM_CLS_CODE` | 임의연장구분코드 | string | Y | 1 |  |
| 6 | `DIVI_APP_CLS_CODE` | 동시호가배분처리구분코드 | string | Y | 2 |  |
| 7 | `ISCD_STAT_CLS_CODE` | 종목상태구분코드 | string | Y | 2 |  |
| 8 | `VI_CLS_CODE` | VI적용구분코드 | string | Y | 1 |  |
| 9 | `OVTM_VI_CLS_CODE` | 시간외단일가VI적용구분코드 | string | Y | 1 |  |
| 10 | `EXCH_CLS_CODE` | 거래소 구분코드 | string | Y | 1 |  |


### 국내ETF NAV추이

- **API ID**: 실시간-051
- **실전 TR_ID**: H0STNAV0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STNAV0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0STNAV0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex. 005930 삼성전자) |

#### Response Body (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `NAV` | NAV | string | Y | 8 |  |
| 2 | `NAV_PRDY_VRSS_SIGN` | NAV전일대비부호 | string | Y | 1 |  |
| 3 | `NAV_PRDY_VRSS` | NAV전일대비 | string | Y | 8 |  |
| 4 | `NAV_PRDY_CTRT` | NAV전일대비율 | string | Y | 8 |  |
| 5 | `OPRC_NAV` | NAV시가 | string | Y | 8 |  |
| 6 | `HPRC_NAV` | NAV고가 | string | Y | 8 |  |
| 7 | `LPRC_NAV` | NAV저가 | string | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0STNAV0",
                           "tr_key":"069500"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STNAV0", 
        "tr_key": "069500", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0STNAV0|001|069500^37235.46^5^-381.26^-1.01^37646.25^37646.25^37202.10
```

</details>



### 국내주식 시간외 실시간체결가 (KRX)

> 🔴 **[공지 2026-09-09 · 시행 2026-09-14(월)] 시간외단일가 폐지 — 이 채널의 대상 시장이 사라진다.**
> KRX 는 2026-09-14 부터 16:00~20:00 **애프터마켓**(연속 실시간 체결)을 신설하고 **시간외단일가를 폐지**했다.
> 애프터마켓 체결·호가는 이 시간외 전용 채널이 아니라 **기존 정규 채널**로 온다 —
> `H0STCNT0`/`H0UNCNT0`/`H0NXCNT0`(체결가)·`H0STASP0`(호가)에 `MARKET_CLS_CODE=3`(애프터)으로 실린다.
> ⚠️ 공지는 이 채널들의 **폐지 여부를 명시하지 않았다** — 구독이 계속 ACK 되는지, 프레임이 오는지는 실측으로 확인한다.

- **API ID**: 실시간-042
- **실전 TR_ID**: H0STOUP0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: WEBSOCKET · **Method**: POST
- **URL**: `/tryitout/H0STOUP0`
- **실전 Domain**: `ws://ops.koreainvestment.com:21000`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내주식 시간외 실시간체결가 API입니다.
국내주식 시간외 단일가(16:00~18:00) 시간대에 실시간체결가 데이터 확인 가능합니다.

[참고자료]
실시간시세(웹소켓) 파이썬 샘플코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/blob/main/websocket/python/ws_domestic_overseas_all.py

실시간시세(웹소켓) API 사용방법에 대한 자세한 설명은 한국투자증권 Wikidocs 참고 부탁드립니다.
https://wikidocs.net/book/7847 (국내주식 업데이트 완료, 추후 해외주식·국내선물옵션 업데이트 예정)

종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info


[호출 데이터]
헤더와 바디 값을 합쳐 JSON 형태로 전송합니다.

[응답 데이터]
1. 정상 등록 여부 (JSON)
- JSON["body"]["msg1"] - 정상 응답 시, SUBSCRIBE SUCCESS
- JSON["body"]["output"]["iv"] - 실시간 결과 복호화에 필요한 AES256 IV (Initialize Vector)
- JSON["body"]["output"]["key"] - 실시간 결과 복호화에 필요한 AES256 Key

2. 실시간 결과 응답 ( | 로 구분되는 값)
ex) 0|H0STCNT0|004|005930^123929^73100^5^...
- 암호화 유무 : 0 암호화 되지 않은 데이터 / 1 암호화된 데이터
- TR_ID : 등록한 tr_id (ex. H0STCNT0)
- 데이터 건수 : (ex. 001 인 경우 데이터 건수 1건, 004인 경우 데이터 건수 4건)
- 응답 데이터 : 아래 response 데이터 참조 ( ^로 구분됨)
```

</details>


#### Request Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `approval_key` | 웹소켓 접속키 | string | Y | 36 | 실시간 (웹소켓) 접속키 발급 API(/oauth2/Approval)를 사용하여 발급받은 웹소켓 접속키 |
| 1 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 / P : 개인 |
| 2 | `tr_type` | 등록/해제 | string | Y | 1 | 1: 등록, 2:해제 |
| 3 | `content-type` | 컨텐츠타입 | string | Y | 20 | utf-8 |

#### Request Body (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `tr_id` | 거래ID | string | Y | 2 | H0STOUP0 |
| 1 | `tr_key` | 구분값 | string | Y | 12 | 종목코드 (ex 005930 삼성전자) |

#### Response Body (43)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `MKSC_SHRN_ISCD` | 유가증권단축종목코드 | string | Y | 9 |  |
| 1 | `STCK_CNTG_HOUR` | 주식체결시간 | string | Y | 6 |  |
| 2 | `STCK_PRPR` | 주식현재가 | string | Y | 1 |  |
| 3 | `PRDY_VRSS_SIGN` | 전일대비구분 | string | Y | 1 |  |
| 4 | `PRDY_VRSS` | 전일대비 | string | Y | 1 |  |
| 5 | `PRDY_CTRT` | 등락율 | string | Y | 1 |  |
| 6 | `WGHN_AVRG_STCK_PRC` | 가중평균주식가격 | string | Y | 1 |  |
| 7 | `STCK_OPRC` | 시가 | string | Y | 1 |  |
| 8 | `STCK_HGPR` | 고가 | string | Y | 1 |  |
| 9 | `STCK_LWPR` | 저가 | string | Y | 1 |  |
| 10 | `ASKP1` | 매도호가 | string | Y | 1 |  |
| 11 | `BIDP1` | 매수호가 | string | Y | 1 |  |
| 12 | `CNTG_VOL` | 거래량 | string | Y | 1 |  |
| 13 | `ACML_VOL` | 누적거래량 | string | Y | 1 |  |
| 14 | `ACML_TR_PBMN` | 누적거래대금 | string | Y | 1 |  |
| 15 | `SELN_CNTG_CSNU` | 매도체결건수 | string | Y | 1 |  |
| 16 | `SHNU_CNTG_CSNU` | 매수체결건수 | string | Y | 1 |  |
| 17 | `NTBY_CNTG_CSNU` | 순매수체결건수 | string | Y | 1 |  |
| 18 | `CTTR` | 체결강도 | string | Y | 1 |  |
| 19 | `SELN_CNTG_SMTN` | 총매도수량 | string | Y | 1 |  |
| 20 | `SHNU_CNTG_SMTN` | 총매수수량 | string | Y | 1 |  |
| 21 | `CNTG_CLS_CODE` | 체결구분 | string | Y | 1 |  |
| 22 | `SHNU_RATE` | 매수비율 | string | Y | 1 |  |
| 23 | `PRDY_VOL_VRSS_ACML_VOL_RATE` | 전일거래량대비등락율 | string | Y | 1 |  |
| 24 | `OPRC_HOUR` | 시가시간 | string | Y | 6 |  |
| 25 | `OPRC_VRSS_PRPR_SIGN` | 시가대비구분 | string | Y | 1 |  |
| 26 | `OPRC_VRSS_PRPR` | 시가대비 | string | Y | 1 |  |
| 27 | `HGPR_HOUR` | 최고가시간 | string | Y | 6 |  |
| 28 | `HGPR_VRSS_PRPR_SIGN` | 고가대비구분 | string | Y | 1 |  |
| 29 | `HGPR_VRSS_PRPR` | 고가대비 | string | Y | 1 |  |
| 30 | `LWPR_HOUR` | 최저가시간 | string | Y | 6 |  |
| 31 | `LWPR_VRSS_PRPR_SIGN` | 저가대비구분 | string | Y | 1 |  |
| 32 | `LWPR_VRSS_PRPR` | 저가대비 | string | Y | 1 |  |
| 33 | `BSOP_DATE` | 영업일자 | string | Y | 8 |  |
| 34 | `NEW_MKOP_CLS_CODE` | 신장운영구분코드 | string | Y | 2 |  |
| 35 | `TRHT_YN` | 거래정지여부 | string | Y | 1 |  |
| 36 | `ASKP_RSQN1` | 매도호가잔량1 | string | Y | 1 |  |
| 37 | `BIDP_RSQN1` | 매수호가잔량1 | string | Y | 1 |  |
| 38 | `TOTAL_ASKP_RSQN` | 총매도호가잔량 | string | Y | 1 |  |
| 39 | `TOTAL_BIDP_RSQN` | 총매수호가잔량 | string | Y | 1 |  |
| 40 | `VOL_TNRT` | 거래량회전율 | string | Y | 1 |  |
| 41 | `PRDY_SMNS_HOUR_ACML_VOL` | 전일동시간누적거래량 | string | Y | 1 |  |
| 42 | `PRDY_SMNS_HOUR_ACML_VOL_RATE` | 전일동시간누적거래량비율 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```json
{
         "header":
         {
                  "approval_key": "35xxxxxa-bxxa-4xxb-87xxx-f56xxxxxxxxxx",
                  "custtype":"P",
                  "tr_type":"1",
                  "content-type":"utf-8"
         },
         "body":
         {
                  "input":
                  {
                           "tr_id":"H0STOUP0",
                           "tr_key":"005930"
                  }
         }
}
```

</details>


<details><summary>Response Example</summary>

```text
# 연결 확인
{
    "header": {
        "tr_id": "H0STOUP0", 
        "tr_key": "005930", 
        "encrypt": "N"
        }, 
    "body": {
        "rt_cd": "0", 
        "msg_cd": "OPSP0000",
        "msg1": "SUBSCRIBE SUCCESS", 
        "output": {
            "iv": "0123456789abcdef", 
            "key": "abcdefghijklmnopabcdefghijklmnop"}
        }
}

# output
0|H0STOUP0|001|005930^165020^77700^2^100^0.13^78209.85^77600^77800^77
600^77800^77700^1034^13540^1052379900^3^2^-1^71.12^8029^5511^5^0.37^69.15^161015^3^100^
162004^5^-100^161015^3^100^20240503^40^N^7898^6461^24577^38548^0.00^18636724^0.07
```

</details>


