# [국내선물옵션] 기본시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (9개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 206 | REST | 선물옵션 시세 | FHMIF10000000 | GET | `/uapi/domestic-futureoption/v1/quotations/inquire-price` | ✓ |
| 207 | REST | 국내선물 기초자산 시세 | FHPIF05030000 | GET | `/uapi/domestic-futureoption/v1/quotations/display-board-top` |  |
| 208 | REST | 선물옵션 일중예상체결추이 | FHPIF05110100 | GET | `/uapi/domestic-futureoption/v1/quotations/exp-price-trend` |  |
| 210 | REST | 국내옵션전광판_선물 | FHPIF05030200 | GET | `/uapi/domestic-futureoption/v1/quotations/display-board-futures` |  |
| 211 | REST | 선물옵션 분봉조회 | FHKIF03020200 | GET | `/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice` |  |
| 212 | REST | 국내옵션전광판_옵션월물리스트 | FHPIO056104C0 | GET | `/uapi/domestic-futureoption/v1/quotations/display-board-option-list` |  |
| 213 | REST | 선물옵션 시세호가 | FHMIF10010000 | GET | `/uapi/domestic-futureoption/v1/quotations/inquire-asking-price` |  |
| 214 | REST | 국내옵션전광판_콜풋 | FHPIF05030100 | GET | `/uapi/domestic-futureoption/v1/quotations/display-board-callput` |  |
| 9999 | REST | 선물옵션기간별시세(일_주_월_년) | FHKIF03020100 | GET | `/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice` |  |

---

## 상세 명세


### 선물옵션 시세

- **API ID**: v1_국내선물-006
- **실전 TR_ID**: FHMIF10000000
- **모의 TR_ID**: FHMIF10000000
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/inquire-price`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
선물옵션 시세 API입니다. 

※ 종목코드 마스터파일 파이썬 정제코드는 한국투자증권 Github 참고 부탁드립니다.
   https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전/모의투자]<br>FHMIF10000000 : 선물 옵션 시세 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | FID 조건 시장 분류 코드 | string | Y | 2 | F: 지수선물, O:지수옵션<br>JF: 주식선물, JO:주식옵션<br>CF: 상품선물(금), 금리선물(국채), 통화선물(달러)<br>CM: 야간선물, EU: 야간옵션 |
| 1 | `FID_INPUT_ISCD` | FID 입력 종목코드 | string | Y | 12 | 종목코드 (예: A01609) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (52)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output1` | 응답상세1 | object | Y |  |  |
| 4 | `hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 | 종목명 |
| 5 | `futs_prpr` | 선물 현재가 | string | Y | 14 | 선물의 현재가격 |
| 6 | `futs_prdy_vrss` | 선물 전일 대비 | string | Y | 14 | 선물의 전일 종가와 당일 현재가의 차이 (당일 현재가-전일 종가) |
| 7 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 | 1 : 상한 <br>2 : 상승<br>3 : 보합<br>4 : 하한<br>5 : 하락 |
| 8 | `futs_prdy_clpr` | 선물 전일 종가 | string | Y | 14 | 해당 선물 종목의 전일 종가 |
| 9 | `futs_prdy_ctrt` | 선물 전일 대비율 | string | Y | 11 | 선물 전일 대비 / 당일 현재가 * 100 |
| 10 | `acml_vol` | 누적 거래량 | string | Y | 18 | 당일 조회시점까지 전체 거래량 |
| 11 | `acml_tr_pbmn` | 누적 거래 대금 | string | Y | 18 | 당일 조회시점까지 전체 거래금액 |
| 12 | `hts_otst_stpl_qty` | HTS 미결제 약정 수량 | string | Y | 18 | 현재까지 반대매매로 청산되지 않은 계약수 |
| 13 | `otst_stpl_qty_icdc` | 미결제 약정 수량 증감 | string | Y | 10 | 전일대비 미결제 약정 수량의 증감 |
| 14 | `futs_oprc` | 선물 시가2 | string | Y | 14 | 당일 최초 거래가격 |
| 15 | `futs_hgpr` | 선물 최고가 | string | Y | 14 | 당일 조회 시점까지 가장 높은 거래가격 |
| 16 | `futs_lwpr` | 선물 최저가 | string | Y | 14 | 당일 조회 시점까지 가장 낮은 거래가격 |
| 17 | `futs_mxpr` | 선물 상한가 | string | Y | 14 | 당일 거래 가능한 최고 가격 |
| 18 | `futs_llam` | 선물 하한가 | string | Y | 14 | 당일 거래 가능한 최저 가격 |
| 19 | `basis` | 베이시스 | string | Y | 13 | 이론베이시스<br>선물 이론가격과 현물가격과의 차이 |
| 20 | `futs_sdpr` | 선물 기준가 | string | Y | 14 |  |
| 21 | `hts_thpr` | HTS 이론가 | string | Y | 14 | 해당 월물의 이론적 가치를 계산한 것으로 주가지수 선물 이론가격은 (주가지수 선물 이론가격 = 주가지수 + 기간이자비용 - 기간배당수입) 로 계산 |
| 22 | `dprt` | 괴리율 | string | Y | 11 | 현재의 시장가가 이론가격으로부터 얼마나 벗어나 있는지에 대한 측정 자료<br>괴리도 = (현재가 - 이론가격) |
| 23 | `crbr_aply_mxpr` | 서킷브레이커 적용 상한가 | string | Y | 14 |  |
| 24 | `crbr_aply_llam` | 서킷브레이커 적용 하한가 | string | Y | 14 |  |
| 25 | `futs_last_tr_date` | 선물 최종 거래 일자 | string | Y | 8 | 해당 선물 종목의 마지막 거래일 |
| 26 | `hts_rmnn_dynu` | HTS 잔존 일수 | string | Y | 5 | 최종 거래일까지 남은 일수 |
| 27 | `futs_lstn_medm_hgpr` | 선물 상장 중 최고가 | string | Y | 14 | 해당 선물 종목의 상장일 이후 최고 거래가격 |
| 28 | `futs_lstn_medm_lwpr` | 선물 상장 중 최저가 | string | Y | 14 | 해당 선물 종목의 상장일 이후 최저 거래가격 |
| 29 | `delta_val` | 델타 값 | string | Y | 16 | 옵션 종목의 지표값 |
| 30 | `gama` | 감마 | string | Y | 13 | 옵션 종목의 지표값 |
| 31 | `theta` | 세타 | string | Y | 13 | 옵션 종목의 지표값 |
| 32 | `vega` | 베가 | string | Y | 13 | 옵션 종목의 지표값 |
| 33 | `rho` | 로우 | string | Y | 13 | 옵션 종목의 지표값 |
| 34 | `hist_vltl` | 역사적 변동성 | string | Y | 16 | 옵션 종목의 지표값 |
| 35 | `hts_ints_vltl` | HTS 내재 변동성 | string | Y | 16 | 옵션 종목의 지표값 |
| 36 | `mrkt_basis` | 시장 베이시스 | string | Y | 13 | 시장베이시스<br>현재 시장에서 형성된 선물가격과 현물가격과의 차이 |
| 37 | `acpr` | 행사가 | string | Y | 14 | 옵션의 행사가격 |
| 38 | `output2` | 응답상세2 | object | Y |  |  |
| 39 | `bstp_cls_code` | 업종 구분 코드 | string | Y | 4 |  |
| 40 | `hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 | 종목명 |
| 41 | `bstp_nmix_prpr` | 업종 지수 현재가 | string | Y | 14 |  |
| 42 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 |  |
| 43 | `bstp_nmix_prdy_vrss` | 업종 지수 전일 대비 | string | Y | 14 |  |
| 44 | `bstp_nmix_prdy_ctrt` | 업종 지수 전일 대비율 | string | Y | 11 |  |
| 45 | `output3` | 응답상세3 | object | Y |  |  |
| 46 | `bstp_cls_code` | 업종 구분 코드 | string | Y | 4 |  |
| 47 | `hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 |  |
| 48 | `bstp_nmix_prpr` | 업종 지수 현재가 | string | Y | 14 |  |
| 49 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 |  |
| 50 | `bstp_nmix_prdy_vrss` | 업종 지수 전일 대비 | string | Y | 14 |  |
| 51 | `bstp_nmix_prdy_ctrt` | 업종 지수 전일 대비율 | string | Y | 11 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"fid_cond_mrkt_div_code": "F",
"fid_input_iscd": "101S03"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "output1": {
    "hts_kor_isnm": "F 202203",
    "futs_prpr": "395.00",
    "futs_prdy_vrss": "6.70",
    "prdy_vrss_sign": "2",
    "futs_prdy_clpr": "388.30",
    "futs_prdy_ctrt": "1.73",
    "acml_vol": "220924",
    "acml_tr_pbmn": "21741293338",
    "hts_otst_stpl_qty": "247121",
    "otst_stpl_qty_icdc": "-592",
    "futs_oprc": "391.05",
    "futs_hgpr": "395.15",
    "futs_lwpr": "391.00",
    "futs_mxpr": "419.35",
    "futs_llam": "357.25",
    "basis": "0.82",
    "futs_sdpr": "388.30",
    "hts_thpr": "395.48",
    "dprt": "-0.12",
    "crbr_aply_mxpr": "0.00",
    "crbr_aply_llam": "0.00",
    "futs_last_tr_date": "20220310",
    "hts_rmnn_dynu": "58",
    "futs_lstn_medm_hgpr": "434.00",
    "futs_lstn_medm_lwpr": "366.60",
    "delta_val": "1.0000",
    "gama": "0.0000",
    "theta": "0.0000",
    "vega": "0.0000",
    "rho": "0.0000",
    "mrkt_basis": "0.34"
  },
  "output2": {
    "bstp_cls_code": "0001",
    "hts_kor_isnm": "종합",
    "bstp_nmix_prpr": "2972.48",
    "prdy_vrss_sign": "2",
    "bstp_nmix_prdy_vrss": "45.10",
    "bstp_nmix_prdy_ctrt": "1.54"
  },
  "output3": {
    "bstp_cls_code": "2001",
    "hts_kor_isnm": "KOSPI200",
    "bstp_nmix_prpr": "394.66",
    "prdy_vrss_sign": "2",
    "bstp_nmix_prdy_vrss": "5.69",
    "bstp_nmix_prdy_ctrt": "1.46"
  },
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "정상처리 되었습니다!"
}
```

</details>



### 국내선물 기초자산 시세

- **API ID**: 국내선물-021
- **실전 TR_ID**: FHPIF05030000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/display-board-top`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내선물 기초자산 시세 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0503] 선물옵션 종합시세(Ⅰ) 화면의 "상단 바" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPIF05030000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건 시장 분류 코드 | string | Y | 2 | 시장구분코드 (F: 선물) |
| 1 | `FID_INPUT_ISCD` | 입력 종목코드 | string | Y | 12 | 선물최근월물 ex)(선물 6자리, 옵션 9자) |
| 2 | `FID_COND_MRKT_DIV_CODE1` | 조건 시장 분류 코드 | string | Y | 2 | 공백 |
| 3 | `FID_COND_SCR_DIV_CODE` | 조건 화면 분류 코드 | string | Y | 5 | 공백 |
| 4 | `FID_MTRT_CNT` | 만기 수 | string | Y | 11 | 공백 |
| 5 | `FID_COND_MRKT_CLS_CODE` | 조건 시장 구분 코드 | string | Y | 6 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (16)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `unas_prpr` | 기초자산 현재가 | string | Y | 112 |  |
| 5 | `unas_prdy_vrss` | 기초자산 전일 대비 | string | Y | 112 |  |
| 6 | `unas_prdy_vrss_sign` | 기초자산 전일 대비 부호 | string | Y | 1 |  |
| 7 | `unas_prdy_ctrt` | 기초자산 전일 대비율 | string | Y | 82 |  |
| 8 | `unas_acml_vol` | 기초자산 누적 거래량 | string | Y | 18 |  |
| 9 | `hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 |  |
| 10 | `futs_prpr` | 선물 현재가 | string | Y | 112 |  |
| 11 | `futs_prdy_vrss` | 선물 전일 대비 | string | Y | 112 |  |
| 12 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 |  |
| 13 | `futs_prdy_ctrt` | 선물 전일 대비율 | string | Y | 82 |  |
| 14 | `output2` | 응답상세 | object array | Y |  | array |
| 15 | `hts_rmnn_dynu` | HTS 잔존 일수 | string | Y | 5 |  |

<details><summary>Request Example (Python)</summary>

```text
fid_cond_mrkt_div_code:F
fid_input_iscd:A01609
fid_cond_mrkt_div_code1:
fid_cond_scr_div_code:
fid_mtrt_cnt:
fid_cond_mrkt_cls_code:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": {
        "unas_prpr": "367.25",
        "unas_prdy_vrss": "-3.47",
        "unas_prdy_vrss_sign": "5",
        "unas_prdy_ctrt": "-0.94",
        "unas_acml_vol": "161725000",
        "hts_kor_isnm": "F 202406",
        "futs_prpr": "369.35",
        "futs_prdy_vrss": "-3.45",
        "prdy_vrss_sign": "5",
        "futs_prdy_ctrt": "-0.93"
    },
    "output2": [],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 선물옵션 일중예상체결추이

- **API ID**: 국내선물-018
- **실전 TR_ID**: FHPIF05110100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/exp-price-trend`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
선물옵션 일중예상체결추이 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0548] 선물옵션 예상체결추이 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPIF05110100 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_INPUT_ISCD` | 입력 종목코드 | string | Y | 12 | 종목번호 (지수선물:6자리, 지수옵션 9자리) |
| 1 | `FID_COND_MRKT_DIV_CODE` | 조건 시장 분류 코드 | string | Y | 2 | F : 지수선물, O : 지수옵션 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (16)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `hts_kor_isnm` | 영업 시간 | string | Y | 40 |  |
| 5 | `futs_antc_cnpr` | 업종 지수 현재가 | string | Y | 112 |  |
| 6 | `antc_cntg_vrss_sign` | 업종 지수 전일 대비 | string | Y | 1 |  |
| 7 | `futs_antc_cntg_vrss` | 전일 대비 부호 | string | Y | 112 |  |
| 8 | `antc_cntg_prdy_ctrt` | 업종 지수 전일 대비율 | string | Y | 82 |  |
| 9 | `futs_sdpr` | 누적 거래 대금 | string | Y | 112 |  |
| 10 | `output2` | 응답상세 | object array | Y |  | array |
| 11 | `stck_cntg_hour` | 주식체결시간 | string | Y | 6 |  |
| 12 | `futs_antc_cnpr` | 선물예상체결가 | string | Y | 112 |  |
| 13 | `antc_cntg_vrss_sign` | 예상체결대비부호 | string | Y | 1 |  |
| 14 | `futs_antc_cntg_vrss` | 선물예상체결대비 | string | Y | 112 |  |
| 15 | `antc_cntg_prdy_ctrt` | 예상체결전일대비율 | string | Y | 82 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:F
FID_INPUT_ISCD:101V06
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": {
        "hts_kor_isnm": "F 202406",
        "futs_antc_cnpr": "0.000",
        "antc_cntg_vrss_sign": "0",
        "futs_antc_cntg_vrss": "0.000",
        "antc_cntg_prdy_ctrt": "0.00",
        "futs_sdpr": "376.95"
    },
    "output2": [
        {
            "stck_cntg_hour": "084500",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "380.00",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.05",
            "antc_cntg_prdy_ctrt": "0.81"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "380.00",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.05",
            "antc_cntg_prdy_ctrt": "0.81"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "380.00",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.05",
            "antc_cntg_prdy_ctrt": "0.81"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "380.00",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.05",
            "antc_cntg_prdy_ctrt": "0.81"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.95",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "3.00",
            "antc_cntg_prdy_ctrt": "0.80"
        },
        {
            "stck_cntg_hour": "084459",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.90",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.95",
            "antc_cntg_prdy_ctrt": "0.78"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.80",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.85",
            "antc_cntg_prdy_ctrt": "0.76"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.80",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.85",
            "antc_cntg_prdy_ctrt": "0.76"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084458",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.75",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.80",
            "antc_cntg_prdy_ctrt": "0.74"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084457",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084456",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084455",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.70",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.75",
            "antc_cntg_prdy_ctrt": "0.73"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.60",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.65",
            "antc_cntg_prdy_ctrt": "0.70"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084454",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.65",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.70",
            "antc_cntg_prdy_ctrt": "0.72"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.60",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.65",
            "antc_cntg_prdy_ctrt": "0.70"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        },
        {
            "stck_cntg_hour": "084453",
            "futs_antc_cnpr": "379.55",
            "antc_cntg_vrss_sign": "2",
            "futs_antc_cntg_vrss": "2.60",
            "antc_cntg_prdy_ctrt": "0.69"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 국내옵션전광판_선물

- **API ID**: 국내선물-023
- **실전 TR_ID**: FHPIF05030200
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/display-board-futures`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내옵션전광판_선물 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0503] 선물옵션 종합시세(Ⅰ) 화면의 "하단" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPIF05030200 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (3)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건 시장 분류 코드 | string | Y | 2 | 시장구분코드 (F: 선물) |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건 화면 분류 코드 | string | Y | 5 | Unique key(20503) |
| 2 | `FID_COND_MRKT_CLS_CODE` | 조건 시장 구분 코드 | string | Y | 6 | 공백: KOSPI200<br>MKI: 미니KOSPI200<br>WKM: KOSPI200위클리(월)<br>WKI: KOSPI200위클리(목)<br>KQI: KOSDAQ150 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (24)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `futs_shrn_iscd` | 선물 단축 종목코드 | string | Y | 9 |  |
| 5 | `hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 |  |
| 6 | `futs_prpr` | 선물 현재가 | string | Y | 112 |  |
| 7 | `futs_prdy_vrss` | 선물 전일 대비 | string | Y | 112 |  |
| 8 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 |  |
| 9 | `futs_prdy_ctrt` | 선물 전일 대비율 | string | Y | 82 |  |
| 10 | `hts_thpr` | HTS 이론가 | string | Y | 112 |  |
| 11 | `acml_vol` | 누적 거래량 | string | Y | 18 |  |
| 12 | `futs_askp` | 선물 매도호가 | string | Y | 112 |  |
| 13 | `futs_bidp` | 선물 매수호가 | string | Y | 112 |  |
| 14 | `hts_otst_stpl_qty` | HTS 미결제 약정 수량 | string | Y | 18 |  |
| 15 | `futs_hgpr` | 선물 최고가 | string | Y | 112 |  |
| 16 | `futs_lwpr` | 선물 최저가 | string | Y | 112 |  |
| 17 | `hts_rmnn_dynu` | HTS 잔존 일수 | string | Y | 5 |  |
| 18 | `total_askp_rsqn` | 총 매도호가 잔량 | string | Y | 12 |  |
| 19 | `total_bidp_rsqn` | 총 매수호가 잔량 | string | Y | 12 |  |
| 20 | `futs_antc_cnpr` | 선물예상체결가 | string | Y | 112 |  |
| 21 | `futs_antc_cntg_vrss` | 선물예상체결대비 | string | Y | 112 |  |
| 22 | `antc_cntg_vrss_sign` | 예상 체결 대비 부호 | string | Y | 1 |  |
| 23 | `antc_cntg_prdy_ctrt` | 예상 체결 전일 대비율 | string | Y | 82 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:F
FID_COND_SCR_DIV_CODE:20503
FID_COND_MRKT_CLS_CODE:MKI
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "futs_shrn_iscd": "105V05",
            "hts_kor_isnm": "미니F 202405",
            "futs_prpr": "368.28",
            "futs_prdy_vrss": "-3.32",
            "prdy_vrss_sign": "5",
            "futs_prdy_ctrt": "-0.89",
            "hts_thpr": "368.26",
            "acml_vol": "91624",
            "futs_askp": "368.28",
            "futs_bidp": "368.26",
            "hts_otst_stpl_qty": "38188",
            "futs_hgpr": "372.86",
            "futs_lwpr": "367.40",
            "hts_rmnn_dynu": "28",
            "total_askp_rsqn": "934",
            "total_bidp_rsqn": "282",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V06",
            "hts_kor_isnm": "미니F 202406",
            "futs_prpr": "369.48",
            "futs_prdy_vrss": "-3.32",
            "prdy_vrss_sign": "5",
            "futs_prdy_ctrt": "-0.89",
            "hts_thpr": "369.51",
            "acml_vol": "621",
            "futs_askp": "369.54",
            "futs_bidp": "369.48",
            "hts_otst_stpl_qty": "3433",
            "futs_hgpr": "374.16",
            "futs_lwpr": "368.64",
            "hts_rmnn_dynu": "63",
            "total_askp_rsqn": "68",
            "total_bidp_rsqn": "53",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V07",
            "hts_kor_isnm": "미니F 202407",
            "futs_prpr": "369.00",
            "futs_prdy_vrss": "-3.98",
            "prdy_vrss_sign": "5",
            "futs_prdy_ctrt": "-1.07",
            "hts_thpr": "369.43",
            "acml_vol": "19",
            "futs_askp": "370.24",
            "futs_bidp": "367.52",
            "hts_otst_stpl_qty": "31",
            "futs_hgpr": "372.00",
            "futs_lwpr": "369.00",
            "hts_rmnn_dynu": "91",
            "total_askp_rsqn": "257",
            "total_bidp_rsqn": "13",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V08",
            "hts_kor_isnm": "미니F 202408",
            "futs_prpr": "373.78",
            "futs_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "futs_prdy_ctrt": "0.00",
            "hts_thpr": "370.41",
            "acml_vol": "0",
            "futs_askp": "403.58",
            "futs_bidp": "344.00",
            "hts_otst_stpl_qty": "1",
            "futs_hgpr": "0.00",
            "futs_lwpr": "0.00",
            "hts_rmnn_dynu": "119",
            "total_askp_rsqn": "4",
            "total_bidp_rsqn": "5",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V09",
            "hts_kor_isnm": "미니F 202409",
            "futs_prpr": "374.00",
            "futs_prdy_vrss": "-0.50",
            "prdy_vrss_sign": "5",
            "futs_prdy_ctrt": "-0.13",
            "hts_thpr": "371.67",
            "acml_vol": "3",
            "futs_askp": "404.36",
            "futs_bidp": "369.82",
            "hts_otst_stpl_qty": "10",
            "futs_hgpr": "374.00",
            "futs_lwpr": "371.00",
            "hts_rmnn_dynu": "154",
            "total_askp_rsqn": "4",
            "total_bidp_rsqn": "12",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
        {
            "futs_shrn_iscd": "105V10",
            "hts_kor_isnm": "미니F 202410",
            "futs_prpr": "375.26",
            "futs_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "futs_prdy_ctrt": "0.00",
            "hts_thpr": "371.72",
            "acml_vol": "0",
            "futs_askp": "405.18",
            "futs_bidp": "345.34",
            "hts_otst_stpl_qty": "0",
            "futs_hgpr": "0.00",
            "futs_lwpr": "0.00",
            "hts_rmnn_dynu": "182",
            "total_askp_rsqn": "4",
            "total_bidp_rsqn": "4",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 선물옵션 분봉조회

- **API ID**: v1_국내선물-012
- **실전 TR_ID**: FHKIF03020200
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/inquire-time-fuopchartprice`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
선물옵션 분봉조회 API입니다.
실전계좌의 경우, 한 번의 호출에 최대 102건까지 확인 가능하며, 
FID_INPUT_DATE_1(입력날짜), FID_INPUT_HOUR_1(입력시간)을 이용하여 다음조회 가능합니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKIF03020200 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (7)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | FID 조건 시장 분류 코드 | string | Y | 2 | F: 지수선물, O:지수옵션<br>JF: 주식선물, JO:주식옵션,<br>CF: 상품선물(금), 금리선물(국채), 통화선물(달러)<br>CM: 야간선물, EU: 야간옵션 |
| 1 | `FID_INPUT_ISCD` | FID 입력 종목코드 | string | Y | 12 | 종목번호 (지수선물:6자리, 지수옵션 9자리) |
| 2 | `FID_HOUR_CLS_CODE` | FID 시간 구분 코드 | string | Y | 5 | FID 시간 구분 코드(30: 30초, 60: 1분, 3600: 1시간) |
| 3 | `FID_PW_DATA_INCU_YN` | FID 과거 데이터 포함 여부 | string | Y | 2 | Y(과거) / N (당일) |
| 4 | `FID_FAKE_TICK_INCU_YN` | FID 허봉 포함 여부 | string | Y | 2 | N으로 입력 |
| 5 | `FID_INPUT_DATE_1` | FID 입력 날짜1 | string | Y | 10 | 입력 날짜 기준으로 이전 기간 조회(YYYYMMDD)<br>ex) 20230908 입력 시, 2023년 9월 8일부터 일자 역순으로 조회 |
| 6 | `FID_INPUT_HOUR_1` | FID 입력 시간1 | string | Y | 10 | 입력 시간 기준으로 이전 시간 조회(HHMMSS)<br>ex) 093000 입력 시, 오전 9시 30분부터 역순으로 분봉 조회<br>* CM(야간선물), EU(야간옵션)인 경우, 자정 이후 시간은 +24시간으로 입력<br>ex) 253000 입력 시, 새벽 1시 30분부터 역순으로 분봉 조회 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (44)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `Output1` | 응답상세 | object array | Y |  |  |
| 4 | `futs_prdy_vrss` | 선물 전일 대비 | string | Y | 11 |  |
| 5 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 | 1: 상한<br>2: 상승<br>3: 보합<br>4: 하한<br>5: 하락 |
| 6 | `futs_prdy_ctrt` | 선물 전일 대비율 | string | Y | 8 |  |
| 7 | `futs_prdy_clpr` | 선물 전일 종가 | string | Y | 11 |  |
| 8 | `prdy_nmix` | 전일 지수 | string | Y | 11 |  |
| 9 | `acml_vol` | 누적 거래량 | string | Y | 18 |  |
| 10 | `acml_tr_pbmn` | 누적 거래 대금 | string | Y | 18 |  |
| 11 | `hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 |  |
| 12 | `futs_prpr` | 선물 현재가 | string | Y | 11 |  |
| 13 | `futs_shrn_iscd` | 선물 단축 종목코드 | string | Y | 9 |  |
| 14 | `prdy_vol` | 전일 거래량 | string | Y | 18 |  |
| 15 | `futs_mxpr` | 선물 상한가 | string | Y | 11 |  |
| 16 | `futs_llam` | 선물 하한가 | string | Y | 11 |  |
| 17 | `futs_oprc` | 선물 시가2 | string | Y | 11 |  |
| 18 | `futs_hgpr` | 선물 최고가 | string | Y | 11 |  |
| 19 | `futs_lwpr` | 선물 최저가 | string | Y | 11 |  |
| 20 | `futs_prdy_oprc` | 선물 전일 시가 | string | Y | 11 |  |
| 21 | `futs_prdy_hgpr` | 선물 전일 최고가 | string | Y | 11 |  |
| 22 | `futs_prdy_lwpr` | 선물 전일 최저가 | string | Y | 11 |  |
| 23 | `futs_askp` | 선물 매도호가 | string | Y | 11 |  |
| 24 | `futs_bidp` | 선물 매수호가 | string | Y | 11 |  |
| 25 | `basis` | 베이시스 | string | Y | 8 |  |
| 26 | `kospi200_nmix` | KOSPI200 지수 | string | Y | 11 |  |
| 27 | `kospi200_prdy_vrss` | KOSPI200 전일 대비 | string | Y | 18 |  |
| 28 | `kospi200_prdy_ctrt` | KOSPI200 전일 대비율 | string | Y | 8 |  |
| 29 | `kospi200_prdy_vrss_sign` | KOSPI200 전일 대비 부호 | string | Y | 1 |  |
| 30 | `hts_otst_stpl_qty` | HTS 미결제 약정 수량 | string | Y | 18 |  |
| 31 | `otst_stpl_qty_icdc` | 미결제 약정 수량 증감 | string | Y | 10 |  |
| 32 | `tday_rltv` | 당일 체결강도 | string | Y | 11 |  |
| 33 | `hts_thpr` | HTS 이론가 | string | Y | 11 |  |
| 34 | `dprt` | 괴리율 | string | Y | 8 |  |
| 35 | `Output2` | 응답상세2 | object | Y |  | array |
| 36 | `stck_bsop_date` | 주식 영업 일자 | string | Y | 8 |  |
| 37 | `stck_cntg_hour` | 주식 체결 시간 | string | Y | 6 | CM(야간선물), EU(야간옵션)인 경우, 자정 이후 시간은 +24시간으로 표시<br>ex) "260000"인 경우, 오전 4시를 의미 |
| 38 | `futs_prpr` | 선물 현재가 | string | Y | 11 |  |
| 39 | `futs_oprc` | 선물 시가2 | string | Y | 11 |  |
| 40 | `futs_hgpr` | 선물 최고가 | string | Y | 11 |  |
| 41 | `futs_lwpr` | 선물 최저가 | string | Y | 11 |  |
| 42 | `cntg_vol` | 체결 거래량 | string | Y | 18 |  |
| 43 | `acml_tr_pbmn` | 누적 거래 대금 | string | Y | 18 |  |

<details><summary>Request Example (Python)</summary>

```text
fid_cond_mrkt_div_code:F
fid_input_iscd:101V09
fid_hour_cls_code:30
fid_pw_data_incu_yn:N
fid_fake_tick_incu_yn:Y
fid_input_date_1:
fid_input_hour_1:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": {
        "futs_prdy_vrss": "-0.30",
        "prdy_vrss_sign": "5",
        "futs_prdy_ctrt": "-0.08",
        "futs_prdy_clpr": "359.90",
        "prdy_nmix": "359.90",
        "acml_vol": "349",
        "acml_tr_pbmn": "31394925",
        "hts_kor_isnm": "F 202409",
        "futs_prpr": "359.60",
        "futs_shrn_iscd": "101V09",
        "prdy_vol": "721",
        "futs_mxpr": "388.65",
        "futs_llam": "331.15",
        "futs_oprc": "361.50",
        "futs_hgpr": "362.00",
        "futs_lwpr": "357.20",
        "futs_prdy_oprc": "364.95",
        "futs_prdy_hgpr": "365.30",
        "futs_prdy_lwpr": "358.60",
        "futs_askp": "359.65",
        "futs_bidp": "359.50",
        "basis": "4.06",
        "kospi200_nmix": "356.42",
        "hts_otst_stpl_qty": "11529",
        "otst_stpl_qty_icdc": "0",
        "tday_rltv": "78.97",
        "hts_thpr": "360.48",
        "dprt": "-0.25"
    },
    "output2": [
        {
            "stck_bsop_date": "20240417",
            "stck_cntg_hour": "141500",
            "futs_prpr": "359.60",
            "futs_oprc": "359.60",
            "futs_hgpr": "359.60",
            "futs_lwpr": "359.60",
            "cntg_vol": "0",
            "acml_tr_pbmn": "31394925"
        },
        {
            "stck_bsop_date": "20240417",
            "stck_cntg_hour": "141430",
            "futs_prpr": "359.60",
            "futs_oprc": "359.60",
            "futs_hgpr": "359.60",
            "futs_lwpr": "359.60",
            "cntg_vol": "0",
            "acml_tr_pbmn": "31394925"
        },
        {
            "stck_bsop_date": "20240417",
            "stck_cntg_hour": "141400",
            "futs_prpr": "359.60",
            "futs_oprc": "359.60",
            "futs_hgpr": "359.60",
            "futs_lwpr": "359.60",
            "cntg_vol": "0",
            "acml_tr_pbmn": "31394925"
        },
        {
            "stck_bsop_date": "20240417",
            "stck_cntg_hour": "141330",
            "futs_prpr": "359.60",
            "futs_oprc": "359.60",
            "futs_hgpr": "359.60",
            "futs_lwpr": "359.60",
            "cntg_vol": "0",
            "acml_tr_pbmn": "31394925"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 국내옵션전광판_옵션월물리스트

- **API ID**: 국내선물-020
- **실전 TR_ID**: FHPIO056104C0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/display-board-option-list`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내업종 국내옵션전광판_옵션월물리스트 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0503] 선물옵션 종합시세(Ⅰ) 화면의 "월물리스트 목록 확인" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPIO056104C0 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (3)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_SCR_DIV_CODE` | 조건 화면 분류 코드 | string | Y | 5 | Unique key(509) |
| 1 | `FID_COND_MRKT_DIV_CODE` | 조건 시장 분류 코드 | string | Y | 2 | 공백 |
| 2 | `FID_COND_MRKT_CLS_CODE` | 조건 시장 구분 코드 | string | Y | 6 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `mtrt_yymm_code` | 만기 년월 코드 | string | Y | 6 |  |
| 5 | `mtrt_yymm` | 만기 년월 | string | Y | 6 |  |

<details><summary>Request Example (Python)</summary>

```text
fid_cond_scr_div_code:509
fid_cond_mrkt_div_code:
fid_cond_mrkt_cls_code:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "mtrt_yymm_code": "0V05",
            "mtrt_yymm": "202405"
        },
        {
            "mtrt_yymm_code": "0V06",
            "mtrt_yymm": "202406"
        },
        {
            "mtrt_yymm_code": "0V07",
            "mtrt_yymm": "202407"
        },
        {
            "mtrt_yymm_code": "0V08",
            "mtrt_yymm": "202408"
        },
        {
            "mtrt_yymm_code": "0V09",
            "mtrt_yymm": "202409"
        },
        {
            "mtrt_yymm_code": "0V10",
            "mtrt_yymm": "202410"
        },
        {
            "mtrt_yymm_code": "0V12",
            "mtrt_yymm": "202412"
        },
        {
            "mtrt_yymm_code": "0W03",
            "mtrt_yymm": "202503"
        },
        {
            "mtrt_yymm_code": "0W06",
            "mtrt_yymm": "202506"
        },
        {
            "mtrt_yymm_code": "0W12",
            "mtrt_yymm": "202512"
        },
        {
            "mtrt_yymm_code": "0612",
            "mtrt_yymm": "202612"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 선물옵션 시세호가

- **API ID**: v1_국내선물-007
- **실전 TR_ID**: FHMIF10010000
- **모의 TR_ID**: FHMIF10010000
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/inquire-asking-price`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
선물옵션 시세호가 API입니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용)<br>※ 토큰 지정시 토큰 타입("Bearer") 지정 필요. 즉, 발급받은 접근토큰 앞에 앞에 "Bearer" 붙여서 호출<br>EX) "Bearer eyJ..........8GA" |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | [실전/모의투자]<br>FHMIF10010000 : 선물 옵션 시세 호가 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (2)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | FID 조건 시장 분류 코드 | string | Y | 2 | F: 지수선물, O:지수옵션<br>JF: 주식선물, JO:주식옵션<br>CF: 상품선물(금), 금리선물(국채), 통화선물(달러)<br>CM: 야간선물, EU: 야간옵션 |
| 1 | `FID_INPUT_ISCD` | FID 입력 종목코드 | string | Y | 12 | 종목코드 (예: A01609) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | Y | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (48)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공<br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output1` | 응답상세1 | object | Y |  |  |
| 4 | `hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 | 종목명 |
| 5 | `futs_prpr` | 선물 현재가 | string | Y | 14 | 선물의 현재가격 |
| 6 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 | 1 : 상한 <br>2 : 상승<br>3 : 보합<br>4 : 하한<br>5 : 하락 |
| 7 | `futs_prdy_vrss` | 선물 전일 대비 | string | Y | 14 | 선물의 전일 종가와 당일 현재가의 차이 (당일 현재가-전일 종가) |
| 8 | `futs_prdy_ctrt` | 선물 전일 대비율 | string | Y | 11 | 선물 전일 대비 / 당일 현재가 * 100 |
| 9 | `acml_vol` | 누적 거래량 | string | Y | 18 | 당일 조회시점까지 전체 거래량 |
| 10 | `futs_prdy_clpr` | 선물 전일 종가 | string | Y | 14 | 해당 선물 종목의 전일 종가 |
| 11 | `futs_shrn_iscd` | 선물 단축 종목코드 | string | Y | 9 |  |
| 12 | `output2` | 응답상세2 | object array | Y |  | Array |
| 13 | `futs_askp1` | 선물 매도호가1 | string | Y | 14 | 해당 종목의 매도호가 중 1번째 낮은 호가 |
| 14 | `futs_askp2` | 선물 매도호가2 | string | Y | 14 | 해당 종목의 매도호가 중 2번째 낮은 호가 |
| 15 | `futs_askp3` | 선물 매도호가3 | string | Y | 14 | 해당 종목의 매도호가 중 3번째 낮은 호가 |
| 16 | `futs_askp4` | 선물 매도호가4 | string | Y | 14 | 해당 종목의 매도호가 중 4번째 낮은 호가 |
| 17 | `futs_askp5` | 선물 매도호가5 | string | Y | 14 | 해당 종목의 매도호가 중 5번째 낮은 호가 |
| 18 | `futs_bidp1` | 선물 매수호가1 | string | Y | 14 | 해당 종목의 매수호가 중 가장 높은 호가 |
| 19 | `futs_bidp2` | 선물 매수호가1 | string | Y | 14 | 해당 종목의 매수호가 중 2번째 높은 호가 |
| 20 | `futs_bidp3` | 선물 매수호가3 | string | Y | 14 | 해당 종목의 매수호가 중 3번째 높은 호가 |
| 21 | `futs_bidp4` | 선물 매수호가4 | string | Y | 14 | 해당 종목의 매수호가 중 4번째 높은 호가 |
| 22 | `futs_bidp5` | 선물 매수호가5 | string | Y | 14 | 해당 종목의 매수호가 중 5번째 높은 호가 |
| 23 | `askp_rsqn1` | 매도호가 잔량1 | string | Y | 12 | 매도호가 1의 미체결수량 |
| 24 | `askp_rsqn2` | 매도호가 잔량2 | string | Y | 12 | 매도호가 2의 미체결수량 |
| 25 | `askp_rsqn3` | 매도호가 잔량3 | string | Y | 12 | 매도호가 3의 미체결수량 |
| 26 | `askp_rsqn4` | 매도호가 잔량4 | string | Y | 12 | 매도호가 4의 미체결수량 |
| 27 | `askp_rsqn5` | 매도호가 잔량5 | string | Y | 12 | 매도호가 5의 미체결수량 |
| 28 | `bidp_rsqn1` | 매수호가 잔량1 | string | Y | 12 | 매수호가 1의 미체결수량 |
| 29 | `bidp_rsqn2` | 매수호가 잔량2 | string | Y | 12 | 매수호가 2의 미체결수량 |
| 30 | `bidp_rsqn3` | 매수호가 잔량3 | string | Y | 12 | 매수호가 3의 미체결수량 |
| 31 | `bidp_rsqn4` | 매수호가 잔량4 | string | Y | 12 | 매수호가 4의 미체결수량 |
| 32 | `bidp_rsqn5` | 매수호가 잔량5 | string | Y | 12 | 매수호가 5의 미체결수량 |
| 33 | `askp_csnu1` | 매도호가 건수1 | string | Y | 10 | 매도호가 1의 미체결 주문 건수 |
| 34 | `askp_csnu2` | 매도호가 건수2 | string | Y | 10 | 매도호가 2의 미체결 주문 건수 |
| 35 | `askp_csnu3` | 매도호가 건수3 | string | Y | 10 | 매도호가 3의 미체결 주문 건수 |
| 36 | `askp_csnu4` | 매도호가 건수4 | string | Y | 10 | 매도호가 4의 미체결 주문 건수 |
| 37 | `askp_csnu5` | 매도호가 건수5 | string | Y | 10 | 매도호가 5의 미체결 주문 건수 |
| 38 | `bidp_csnu1` | 매수호가 건수1 | string | Y | 10 | 매수호가 1의 미체결 주문 건수 |
| 39 | `bidp_csnu2` | 매수호가 건수2 | string | Y | 10 | 매수호가 2의 미체결 주문 건수 |
| 40 | `bidp_csnu3` | 매수호가 건수3 | string | Y | 10 | 매수호가 3의 미체결 주문 건수 |
| 41 | `bidp_csnu4` | 매수호가 건수4 | string | Y | 10 | 매수호가 4의 미체결 주문 건수 |
| 42 | `bidp_csnu5` | 매수호가 건수5 | string | Y | 10 | 매수호가 5의 미체결 주문 건수 |
| 43 | `total_askp_rsqn` | 총 매도호가 잔량 | string | Y | 12 | 매도호가 1~5의 잔량 합계 |
| 44 | `total_bidp_rsqn` | 총 매수호가 잔량 | string | Y | 12 | 매수호가 1~5의 잔량 합계 |
| 45 | `total_askp_csnu` | 총 매도호가 건수 | string | Y | 10 | 매도호가 1~5의 미체결 주문 건수 합계 |
| 46 | `total_bidp_csnu` | 총 매수호가 건수 | string | Y | 10 | 매수호가 1~5의 미체결 주문 건수 합계 |
| 47 | `aspr_acpt_hour` | 호가 접수 시간 | string | Y | 6 | 가장 최근 호가의 접수 시간 |

<details><summary>Request Example (Python)</summary>

```json
{
"fid_cond_mrkt_div_code" : "F",
"fid_input_iscd" : "101S06"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "output1": {
    "hts_kor_isnm": "F 202206",
    "futs_prpr": "364.40",
    "prdy_vrss_sign": "2",
    "futs_prdy_vrss": "3.00",
    "futs_prdy_ctrt": "0.83",
    "acml_vol": "193112",
    "futs_prdy_clpr": "361.40",
    "futs_shrn_iscd": "101S06"
  },
  "output2": {
    "futs_askp1": "364.40",
    "futs_askp2": "364.45",
    "futs_askp3": "364.50",
    "futs_askp4": "364.55",
    "futs_askp5": "364.60",
    "futs_bidp1": "364.35",
    "futs_bidp2": "364.30",
    "futs_bidp3": "364.25",
    "futs_bidp4": "364.20",
    "futs_bidp5": "364.15",
    "askp_rsqn1": "35",
    "askp_rsqn2": "47",
    "askp_rsqn3": "32",
    "askp_rsqn4": "56",
    "askp_rsqn5": "88",
    "bidp_rsqn1": "22",
    "bidp_rsqn2": "70",
    "bidp_rsqn3": "68",
    "bidp_rsqn4": "97",
    "bidp_rsqn5": "42",
    "askp_csnu1": "9",
    "askp_csnu2": "19",
    "askp_csnu3": "21",
    "askp_csnu4": "28",
    "askp_csnu5": "20",
    "bidp_csnu1": "9",
    "bidp_csnu2": "45",
    "bidp_csnu3": "26",
    "bidp_csnu4": "31",
    "bidp_csnu5": "22",
    "total_askp_rsqn": "7140",
    "total_bidp_rsqn": "9319",
    "total_askp_csnu": "1091",
    "total_bidp_csnu": "1115",
    "aspr_acpt_hour": "153744"
  },
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "정상처리 되었습니다."
}
```

</details>



### 국내옵션전광판_콜풋

- **API ID**: 국내선물-022
- **실전 TR_ID**: FHPIF05030100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/display-board-callput`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
국내옵션전광판_콜풋 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0503] 선물옵션 종합시세(Ⅰ) 화면의 "중앙" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

※ output1, output2 각각 높은 행사가 순으로 100건까지만 확인이 가능합니다. 
※ 조회시간이 긴 API인 점 참고 부탁드리며, 잦은 호출을 삼가해주시기 바랍니다. (1초당 최대 1건 권장)
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPIF05030100 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건 시장 분류 코드 | string | Y | 2 | 시장구분코드 (O: 옵션) |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건 화면 분류 코드 | string | Y | 5 | Unique key(20503) |
| 2 | `FID_MRKT_CLS_CODE` | 시장 구분 코드 | string | Y | 2 | 시장구분코드 (CO: 콜옵션) |
| 3 | `FID_MTRT_CNT` | 만기 수 | string | Y | 11 | - FID_COND_MRKT_CLS_CODE : 공백(KOSPI200), MKI(미니KOSPI200), KQI(KOSDAQ150) 인 경우<br>: 만기년월(YYYYMM) 입력 (ex. 202407)<br>- FID_COND_MRKT_CLS_CODE : WKM(KOSPI200위클리(월)), WKI(KOSPI200위클리(목)) 인 경우<br>: 만기년월주차(YYMMWW) 입력<br>(ex. 2024년도 7월 3주차인 경우, 240703 입력) |
| 4 | `FID_COND_MRKT_CLS_CODE` | 조건 시장 구분 코드 | string | Y | 6 | 공백: KOSPI200<br>MKI: 미니KOSPI200<br>WKM: KOSPI200위클리(월)<br>WKI: KOSPI200위클리(목)<br>KQI: KOSDAQ150 |
| 5 | `FID_MRKT_CLS_CODE1` | 시장 구분 코드 | string | Y | 2 | 시장구분코드 (PO: 풋옵션) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (87)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `acpr` | 행사가 | string | Y | 112 |  |
| 5 | `unch_prpr` | 환산 현재가 | string | Y | 112 |  |
| 6 | `optn_shrn_iscd` | 옵션 단축 종목코드 | string | Y | 9 |  |
| 7 | `optn_prpr` | 옵션 현재가 | string | Y | 112 |  |
| 8 | `optn_prdy_vrss` | 옵션 전일 대비 | string | Y | 112 |  |
| 9 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 |  |
| 10 | `optn_prdy_ctrt` | 옵션 전일 대비율 | string | Y | 82 |  |
| 11 | `optn_bidp` | 옵션 매수호가 | string | Y | 112 |  |
| 12 | `optn_askp` | 옵션 매도호가 | string | Y | 112 |  |
| 13 | `tmvl_val` | 시간가치 값 | string | Y | 132 |  |
| 14 | `nmix_sdpr` | 지수 기준가 | string | Y | 112 |  |
| 15 | `acml_vol` | 누적 거래량 | string | Y | 18 |  |
| 16 | `seln_rsqn` | 매도 잔량 | string | Y | 12 |  |
| 17 | `shnu_rsqn` | 매수2 잔량 | string | Y | 12 |  |
| 18 | `acml_tr_pbmn` | 누적 거래 대금 | string | Y | 18 |  |
| 19 | `hts_otst_stpl_qty` | HTS 미결제 약정 수량 | string | Y | 18 |  |
| 20 | `otst_stpl_qty_icdc` | 미결제 약정 수량 증감 | string | Y | 10 |  |
| 21 | `delta_val` | 델타 값 | string | Y | 114 |  |
| 22 | `gama` | 감마 | string | Y | 84 |  |
| 23 | `vega` | 베가 | string | Y | 84 |  |
| 24 | `theta` | 세타 | string | Y | 84 |  |
| 25 | `rho` | 로우 | string | Y | 84 |  |
| 26 | `hts_ints_vltl` | HTS 내재 변동성 | string | Y | 114 |  |
| 27 | `invl_val` | 내재가치 값 | string | Y | 132 |  |
| 28 | `esdg` | 괴리도 | string | Y | 114 |  |
| 29 | `dprt` | 괴리율 | string | Y | 82 |  |
| 30 | `hist_vltl` | 역사적 변동성 | string | Y | 114 |  |
| 31 | `hts_thpr` | HTS 이론가 | string | Y | 112 |  |
| 32 | `optn_oprc` | 옵션 시가2 | string | Y | 112 |  |
| 33 | `optn_hgpr` | 옵션 최고가 | string | Y | 112 |  |
| 34 | `optn_lwpr` | 옵션 최저가 | string | Y | 112 |  |
| 35 | `optn_mxpr` | 옵션 상한가 | string | Y | 112 |  |
| 36 | `optn_llam` | 옵션 하한가 | string | Y | 112 |  |
| 37 | `atm_cls_name` | ATM 구분 명 | string | Y | 10 |  |
| 38 | `rgbf_vrss_icdc` | 직전 대비 증감 | string | Y | 10 |  |
| 39 | `total_askp_rsqn` | 총 매도호가 잔량 | string | Y | 12 |  |
| 40 | `total_bidp_rsqn` | 총 매수호가 잔량 | string | Y | 12 |  |
| 41 | `futs_antc_cnpr` | 선물예상체결가 | string | Y | 112 |  |
| 42 | `futs_antc_cntg_vrss` | 선물예상체결대비 | string | Y | 112 |  |
| 43 | `antc_cntg_vrss_sign` | 예상 체결 대비 부호 | string | Y | 1 |  |
| 44 | `antc_cntg_prdy_ctrt` | 예상 체결 전일 대비율 | string | Y | 82 |  |
| 45 | `output2` | 응답상세 | object array | Y |  | array |
| 46 | `acpr` | 행사가 | string | Y | 112 |  |
| 47 | `unch_prpr` | 환산 현재가 | string | Y | 112 |  |
| 48 | `optn_shrn_iscd` | 옵션 단축 종목코드 | string | Y | 9 |  |
| 49 | `optn_prpr` | 옵션 현재가 | string | Y | 112 |  |
| 50 | `optn_prdy_vrss` | 옵션 전일 대비 | string | Y | 112 |  |
| 51 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 |  |
| 52 | `optn_prdy_ctrt` | 옵션 전일 대비율 | string | Y | 82 |  |
| 53 | `optn_bidp` | 옵션 매수호가 | string | Y | 112 |  |
| 54 | `optn_askp` | 옵션 매도호가 | string | Y | 112 |  |
| 55 | `tmvl_val` | 시간가치 값 | string | Y | 132 |  |
| 56 | `nmix_sdpr` | 지수 기준가 | string | Y | 112 |  |
| 57 | `acml_vol` | 누적 거래량 | string | Y | 18 |  |
| 58 | `seln_rsqn` | 매도 잔량 | string | Y | 12 |  |
| 59 | `shnu_rsqn` | 매수2 잔량 | string | Y | 12 |  |
| 60 | `acml_tr_pbmn` | 누적 거래 대금 | string | Y | 18 |  |
| 61 | `hts_otst_stpl_qty` | HTS 미결제 약정 수량 | string | Y | 18 |  |
| 62 | `otst_stpl_qty_icdc` | 미결제 약정 수량 증감 | string | Y | 10 |  |
| 63 | `delta_val` | 델타 값 | string | Y | 114 |  |
| 64 | `gama` | 감마 | string | Y | 84 |  |
| 65 | `vega` | 베가 | string | Y | 84 |  |
| 66 | `theta` | 세타 | string | Y | 84 |  |
| 67 | `rho` | 로우 | string | Y | 84 |  |
| 68 | `hts_ints_vltl` | HTS 내재 변동성 | string | Y | 114 |  |
| 69 | `invl_val` | 내재가치 값 | string | Y | 132 |  |
| 70 | `esdg` | 괴리도 | string | Y | 114 |  |
| 71 | `dprt` | 괴리율 | string | Y | 82 |  |
| 72 | `hist_vltl` | 역사적 변동성 | string | Y | 114 |  |
| 73 | `hts_thpr` | HTS 이론가 | string | Y | 112 |  |
| 74 | `optn_oprc` | 옵션 시가2 | string | Y | 112 |  |
| 75 | `optn_hgpr` | 옵션 최고가 | string | Y | 112 |  |
| 76 | `optn_lwpr` | 옵션 최저가 | string | Y | 112 |  |
| 77 | `optn_mxpr` | 옵션 상한가 | string | Y | 112 |  |
| 78 | `optn_llam` | 옵션 하한가 | string | Y | 112 |  |
| 79 | `atm_cls_name` | ATM 구분 명 | string | Y | 10 |  |
| 80 | `rgbf_vrss_icdc` | 직전 대비 증감 | string | Y | 10 |  |
| 81 | `total_askp_rsqn` | 총 매도호가 잔량 | string | Y | 12 |  |
| 82 | `total_bidp_rsqn` | 총 매수호가 잔량 | string | Y | 12 |  |
| 83 | `futs_antc_cnpr` | 선물예상체결가 | string | Y | 112 |  |
| 84 | `futs_antc_cntg_vrss` | 선물예상체결대비 | string | Y | 112 |  |
| 85 | `antc_cntg_vrss_sign` | 예상 체결 대비 부호 | string | Y | 1 |  |
| 86 | `antc_cntg_prdy_ctrt` | 예상 체결 전일 대비율 | string | Y | 82 |  |

<details><summary>Request Example (Python)</summary>

```text
fid_cond_mrkt_div_code:O
fid_cond_scr_div_code:20503
fid_mrkt_cls_code:CO
fid_mtrt_cnt:202405
fid_cond_mrkt_cls_code:
fid_mrkt_cls_code1:PO
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": [
        {
            "acpr": "480.00",
            "unch_prpr": "3505.17",
            "optn_shrn_iscd": "201V05480",
            "optn_prpr": "0.01",
            "optn_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "optn_prdy_ctrt": "0.00",
            "optn_bidp": "0.00",
            "optn_askp": "0.01",
            "tmvl_val": "0.01",
            "nmix_sdpr": "0.01",
            "acml_vol": "34",
            "seln_rsqn": "1710",
            "shnu_rsqn": "0",
            "acml_tr_pbmn": "85",
            "hts_otst_stpl_qty": "642",
            "otst_stpl_qty_icdc": "39",
            "delta_val": "0.0000",
            "gama": "0.0000",
            "vega": "0.0000",
            "theta": "-0.0000",
            "rho": "0.0000",
            "hts_ints_vltl": "31.5614",
            "invl_val": "0.00",
            "esdg": "0.01",
            "dprt": "9999.99",
            "hist_vltl": "16.9285",
            "hts_thpr": "0.00",
            "optn_oprc": "0.01",
            "optn_hgpr": "0.01",
            "optn_lwpr": "0.01",
            "optn_mxpr": "5.20",
            "optn_llam": "0.01",
            "atm_cls_name": "OTM",
            "rgbf_vrss_icdc": "1",
            "total_askp_rsqn": "1710",
            "total_bidp_rsqn": "0",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },
		...
    ],
    "output2": [
        {
            "acpr": "480.00",
            "unch_prpr": "3505.17",
            "optn_shrn_iscd": "301V05480",
            "optn_prpr": "108.45",
            "optn_prdy_vrss": "0.00",
            "prdy_vrss_sign": "3",
            "optn_prdy_ctrt": "0.00",
            "optn_bidp": "78.35",
            "optn_askp": "142.60",
            "tmvl_val": "-4.30",
            "nmix_sdpr": "108.45",
            "acml_vol": "0",
            "seln_rsqn": "10",
            "shnu_rsqn": "10",
            "acml_tr_pbmn": "0",
            "hts_otst_stpl_qty": "48",
            "otst_stpl_qty_icdc": "0",
            "delta_val": "-1.0000",
            "gama": "0.0000",
            "vega": "0.0000",
            "theta": "0.0460",
            "rho": "-0.3541",
            "hts_ints_vltl": "0.0000",
            "invl_val": "112.75",
            "esdg": "-3.06",
            "dprt": "-2.74",
            "hist_vltl": "16.9285",
            "hts_thpr": "111.51",
            "optn_oprc": "0.00",
            "optn_hgpr": "0.00",
            "optn_lwpr": "0.00",
            "optn_mxpr": "142.60",
            "optn_llam": "78.35",
            "atm_cls_name": "ITM",
            "rgbf_vrss_icdc": "0",
            "total_askp_rsqn": "10",
            "total_bidp_rsqn": "10",
            "futs_antc_cnpr": "0.00",
            "futs_antc_cntg_vrss": "0.00",
            "antc_cntg_vrss_sign": "0",
            "antc_cntg_prdy_ctrt": "0.00"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 선물옵션기간별시세(일_주_월_년)

- **API ID**: v1_국내선물-008
- **실전 TR_ID**: FHKIF03020100
- **모의 TR_ID**: FHKIF03020100
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
(지수)선물옵션 기간별시세 데이터(일/주/월/년) 조회 (최대 100건 조회)
실전계좌의 경우, 한 번의 호출에 최대 100건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다. 
모의계좌의 경우, 한 번의 호출에 최대 100건까지 확인 가능하며, 이후의 값은 연속조회를 통해 확인하실 수 있습니다.
```

</details>


#### Request Header (6)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | N | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 350 | OAuth 토큰이 필요한 API 경우 발급한 Access token<br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용)<br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appsecret (절대 노출되지 않도록 주의해주세요.) |
| 4 | `tr_id` | 거래ID | string | Y | 13 | [실전/모의투자]<br>FHKIF03020100 |
| 5 | `custtype` | 고객타입 | string | N | 1 | B : 법인<br>P : 개인 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | FID 조건 시장 분류 코드 | string | Y | 2 | F: 지수선물, O:지수옵션<br>JF: 주식선물, JO:주식옵션,<br>CF: 상품선물(금), 금리선물(국채), 통화선물(달러)<br>CM: 야간선물, EU: 야간옵션 |
| 1 | `FID_INPUT_ISCD` | 종목코드 | string | Y | 12 | 종목번호 (지수선물:6자리, 지수옵션 9자리) |
| 2 | `FID_INPUT_DATE_1` | 조회 시작일자 | string | Y | 10 | 조회 시작일자 (ex. 20220401) |
| 3 | `FID_INPUT_DATE_2` | 조회 종료일자 | string | Y | 10 | 조회 종료일자 (ex. 20220524)<br>※ 주(W), 월(M), 년(Y) 봉 조회 시에 아래 참고<br>ㅁ FID_INPUT_DATE_2 가 현재일 까지일때<br>. 주봉 조회 : 해당 주의 첫번째 영업일이 포함되어야함<br>. 월봉 조회 : 해당 월의 전월 일자로 시작되어야함<br>. 년봉 조회 : 해당 년의 전년도 일자로 시작되어야함<br>ㅁ FID_INPUT_DATE_2 가 현재일보다 이전일 때<br>. 주봉 조회 : 해당 주의 첫번째 영업일이 포함되어야함<br>. 월봉 조회 : 해당 월의 영업일이 포함되어야함<br>. 년봉 조회 : 해당 년의 영업일이 포함되어야함 |
| 4 | `FID_PERIOD_DIV_CODE` | 기간분류코드 | string | Y | 32 | D:일봉 W:주봉, M:월봉, Y:년봉 |

#### Response Header (3)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `gt_uid` | Global UID | string | Y | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (43)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 | 0 : 성공 <br>0 이외의 값 : 실패 |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 | 응답코드 |
| 2 | `msg1` | 응답메세지 | string | Y | 80 | 응답메세지 |
| 3 | `output1` | 상세기본정보 | object | Y | 1 | 상세기본정보 |
| 4 | `-futs_prdy_vrss` | 전일 대비 | string | Y | 14 | 전일 대비 |
| 5 | `-prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 | 전일 대비 부호 |
| 6 | `-futs_prdy_ctrt` | 선물 전일 대비율 | string | Y | 11 | 선물 전일 대비율 |
| 7 | `-futs_prdy_clpr` | 선물 전일 종가 | string | Y | 14 | 선물 전일 종가 |
| 8 | `-acml_vol` | 누적 거래량 | string | Y | 18 | 누적 거래량 |
| 9 | `-acml_tr_pbmn` | 누적 거래 대금 | string | Y | 18 | 누적 거래 대금 |
| 10 | `-hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 | HTS 한글 종목명 |
| 11 | `-futs_prpr` | 현재가 | string | Y | 14 | 현재가 |
| 12 | `-futs_shrn_iscd` | 단축 종목코드 | string | Y | 9 | 단축 종목코드 |
| 13 | `-prdy_vol` | 전일 거래량 | string | Y | 18 | 전일 거래량 |
| 14 | `-futs_mxpr` | 상한가 | string | Y | 14 | 상한가 |
| 15 | `-futs_llam` | 하한가 | string | Y | 14 | 하한가 |
| 16 | `-futs_oprc` | 시가 | string | Y | 14 | 시가 |
| 17 | `-futs_hgpr` | 최고가 | string | Y | 14 | 최고가 |
| 18 | `-futs_lwpr` | 최저가 | string | Y | 14 | 최저가 |
| 19 | `-futs_prdy_oprc` | 전일 시가 | string | Y | 14 | 전일 시가 |
| 20 | `-futs_prdy_hgpr` | 전일 최고가 | string | Y | 14 | 전일 최고가 |
| 21 | `-futs_prdy_lwpr` | 전일 최저가 | string | Y | 14 | 전일 최저가 |
| 22 | `-futs_askp` | 매도호가 | string | Y | 14 | 매도호가 |
| 23 | `-futs_bidp` | 매수호가 | string | Y | 14 | 매수호가 |
| 24 | `-basis` | 베이시스 | string | Y | 12 | 베이시스 |
| 25 | `-kospi200_nmix` | KOSPI200 지수 | string | Y | 14 | KOSPI200 지수 |
| 26 | `-kospi200_prdy_vrss` | KOSPI200 전일 대비 | string | Y | 14 | KOSPI200 전일 대비 |
| 27 | `-kospi200_prdy_ctrt` | KOSPI200 전일 대비율 | string | Y | 11 | KOSPI200 전일 대비율 |
| 28 | `-kospi200_prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 | 전일 대비 부호 |
| 29 | `-hts_otst_stpl_qty` | HTS 미결제 약정 수량 | string | Y | 18 | HTS 미결제 약정 수량 |
| 30 | `-otst_stpl_qty_icdc` | 미결제 약정 수량 증감 | string | Y | 10 | 미결제 약정 수량 증감 |
| 31 | `-tday_rltv` | 당일 체결강도 | string | Y | 14 | 당일 체결강도 |
| 32 | `-hts_thpr` | HTS 이론가 | string | Y | 14 | HTS 이론가 |
| 33 | `-dprt` | 괴리율 | string | Y | 11 | 괴리율 |
| 34 | `output2` | 기간별 조회데이터 (배열) | array | Y | 1 | 기간별 조회데이터 (배열) |
| 35 | `-stck_bsop_date` | 영업 일자 | string | Y | 8 | 영업 일자 |
| 36 | `-futs_prpr` | 현재가 | string | Y | 14 | 현재가 |
| 37 | `-futs_oprc` | 시가 | string | Y | 14 | 시가 |
| 38 | `-futs_hgpr` | 최고가 | string | Y | 14 | 최고가 |
| 39 | `-futs_lwpr` | 최저가 | string | Y | 14 | 최저가 |
| 40 | `-acml_vol` | 누적 거래량 | string | Y | 18 | 누적 거래량 |
| 41 | `-acml_tr_pbmn` | 누적 거래 대금 | string | Y | 18 | 누적 거래 대금 |
| 42 | `-mod_yn` | 변경 여부 | string | Y | 1 | 변경 여부 |

<details><summary>Request Example (Python)</summary>

```text
"input": {
            "fid_cond_mrkt_div_code": "F",
            "fid_input_date_1": "20220401",
            "fid_input_date_2": "20220524",
            "fid_input_iscd": "101S06",
            "fid_period_div_code": "D"
        }
```

</details>


<details><summary>Response Example</summary>

```text
"output1": {
            "acml_tr_pbmn": "15491417875",
            "acml_vol": "178446",
            "basis": "0.28",
            "dprt": "-0.14",
            "futs_askp": "344.70",
            "futs_bidp": "344.65",
            "futs_hgpr": "349.75",
            "futs_llam": "322.65",
            "futs_lwpr": "344.65",
            "futs_mxpr": "378.75",
            "futs_oprc": "348.85",
            "futs_prdy_clpr": "350.70",
            "futs_prdy_ctrt": "-1.71",
            "futs_prdy_hgpr": "351.85",
            "futs_prdy_lwpr": "348.65",
            "futs_prdy_oprc": "351.55",
            "futs_prdy_vrss": "-6.00",
            "futs_prpr": "344.70",
            "futs_shrn_iscd": "101S06",
            "hts_kor_isnm": "F 202206",
            "hts_otst_stpl_qty": "297901",
            "hts_thpr": "345.17",
            "kospi200_nmix": "344.89",
            "otst_stpl_qty_icdc": "4348",
            "prdy_vol": "222987",
            "prdy_vrss_sign": "5",
            "tday_rltv": "92.20"
        },
        "output2": [
            {
                "acml_tr_pbmn": "15491417875",
                "acml_vol": "178446",
                "futs_hgpr": "349.75",
                "futs_lwpr": "344.65",
                "futs_oprc": "348.85",
                "futs_prpr": "344.70",
                "mod_yn": "N",
                "stck_bsop_date": "20220524"
            },
....
```

</details>


