# [국내주식] ELW 시세 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (22개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 49 | REST | ELW 현재가 시세 | FHKEW15010000 | GET | `/uapi/domestic-stock/v1/quotations/inquire-elw-price` |  |
| 50 | REST | ELW 신규상장종목 | FHKEW154800C0 | GET | `/uapi/elw/v1/quotations/newly-listed` |  |
| 51 | REST | ELW 투자지표추이(일별) | FHPEW02740200 | GET | `/uapi/elw/v1/quotations/indicator-trend-daily` |  |
| 52 | REST | ELW 민감도 순위 | FHPEW02850000 | GET | `/uapi/elw/v1/ranking/sensitivity` |  |
| 53 | REST | ELW 기초자산별 종목시세 | FHKEW154101C0 | GET | `/uapi/elw/v1/quotations/udrl-asset-price` |  |
| 54 | REST | ELW 종목검색 | FHKEW15100000 | GET | `/uapi/elw/v1/quotations/cond-search` |  |
| 55 | REST | ELW 변동성 추이(분별) | FHPEW02840300 | GET | `/uapi/elw/v1/quotations/volatility-trend-minute` |  |
| 56 | REST | ELW 변동성추이(체결) | FHPEW02840100 | GET | `/uapi/elw/v1/quotations/volatility-trend-ccnl` |  |
| 57 | REST | ELW 당일급변종목 | FHPEW02870000 | GET | `/uapi/elw/v1/ranking/quick-change` |  |
| 58 | REST | ELW 투자지표추이(분별) | FHPEW02740300 | GET | `/uapi/elw/v1/quotations/indicator-trend-minute` |  |
| 59 | REST | ELW 기초자산 목록조회 | FHKEW154100C0 | GET | `/uapi/elw/v1/quotations/udrl-asset-list` |  |
| 60 | REST | ELW 변동성 추이(일별) | FHPEW02840200 | GET | `/uapi/elw/v1/quotations/volatility-trend-daily` |  |
| 61 | REST | ELW 거래량순위 | FHPEW02780000 | GET | `/uapi/elw/v1/ranking/volume-rank` |  |
| 62 | REST | ELW 지표순위 | FHPEW02790000 | GET | `/uapi/elw/v1/ranking/indicator` |  |
| 63 | REST | ELW 투자지표추이(체결) | FHPEW02740100 | GET | `/uapi/elw/v1/quotations/indicator-trend-ccnl` |  |
| 64 | REST | ELW 상승률순위 | FHPEW02770000 | GET | `/uapi/elw/v1/ranking/updown-rate` |  |
| 65 | REST | ELW 민감도 추이(일별) | FHPEW02830200 | GET | `/uapi/elw/v1/quotations/sensitivity-trend-daily` |  |
| 66 | REST | ELW 비교대상종목조회 | FHKEW151701C0 | GET | `/uapi/elw/v1/quotations/compare-stocks` |  |
| 68 | REST | ELW LP매매추이 | FHPEW03760000 | GET | `/uapi/elw/v1/quotations/lp-trade-trend` |  |
| 69 | REST | ELW 민감도 추이(체결) | FHPEW02830100 | GET | `/uapi/elw/v1/quotations/sensitivity-trend-ccnl` |  |
| 70 | REST | ELW 변동성 추이(틱) | FHPEW02840400 | GET | `/uapi/elw/v1/quotations/volatility-trend-tick` |  |
| 9999 | REST | ELW 만기예정_만기종목 | FHKEW154700C0 | GET | `/uapi/elw/v1/quotations/expiration-stocks` |  |

---

## 상세 명세


### ELW 현재가 시세

- **API ID**: v1_국내주식-014
- **실전 TR_ID**: FHKEW15010000
- **모의 TR_ID**: FHKEW15010000
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/inquire-elw-price`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `https://openapivts.koreainvestment.com:29443`

<details><summary>개요</summary>

```text
ELW 현재가 시세 API입니다. ELW 관련 정보를 얻을 수 있습니다.
```

</details>


#### Request Header (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `authorization` | 접근토큰 | string | Y | 40 | OAuth 토큰이 필요한 API 경우 발급한 Access token <br>일반고객(Access token 유효기간 1일, OAuth 2.0의 Client Credentials Grant 절차를 준용) <br>법인(Access token 유효기간 3개월, Refresh token 유효기간 1년, OAuth 2.0의 Authorization Code Grant 절차를 준용) |
| 2 | `appkey` | 앱키 | string | Y | 36 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 3 | `appsecret` | 앱시크릿키 | string | Y | 180 | 한국투자증권 홈페이지에서 발급받은 appkey (절대 노출되지 않도록 주의해주세요.) |
| 4 | `personalseckey` | 고객식별키 | string | N | 180 | [법인 필수] 제휴사 회원 관리를 위한 고객식별키 |
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKEW15010000 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건 시장 분류 코드 | string | Y | 2 | W |
| 1 | `FID_INPUT_ISCD` | 입력 종목코드 | string | Y | 12 | 종목번호 (6자리) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (42)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `elw_shrn_iscd` | ELW 단축 종목코드 | string | Y | 9 |  |
| 5 | `hts_kor_isnm` | HTS 한글 종목명 | string | Y | 40 |  |
| 6 | `elw_prpr` | ELW 현재가 | string | Y | 10 |  |
| 7 | `prdy_vrss` | 전일 대비 | string | Y | 10 |  |
| 8 | `prdy_vrss_sign` | 전일 대비 부호 | string | Y | 1 |  |
| 9 | `prdy_ctrt` | 전일 대비율 | string | Y | 11 |  |
| 10 | `acml_vol` | 누적 거래량 | string | Y | 18 |  |
| 11 | `prdy_vrss_vol_rate` | 전일 대비 거래량 비율 | string | Y | 13 |  |
| 12 | `unas_shrn_iscd` | 기초자산 단축 종목코드 | string | Y | 9 |  |
| 13 | `unas_isnm` | 기초자산 종목명 | string | Y | 40 |  |
| 14 | `unas_prpr` | 기초자산 현재가 | string | Y | 14 |  |
| 15 | `unas_prdy_vrss` | 기초자산 전일 대비 | string | Y | 14 |  |
| 16 | `unas_prdy_vrss_sign` | 기초자산 전일 대비 부호 | string | Y | 1 |  |
| 17 | `unas_prdy_ctrt` | 기초자산 전일 대비율 | string | Y | 11 |  |
| 18 | `bidp` | 매수호가 | string | Y | 10 |  |
| 19 | `askp` | 매도호가 | string | Y | 10 |  |
| 20 | `acml_tr_pbmn` | 누적 거래 대금 | string | Y | 18 |  |
| 21 | `vol_tnrt` | 거래량 회전율 | string | Y | 11 |  |
| 22 | `elw_oprc` | ELW 시가2 | string | Y | 10 |  |
| 23 | `elw_hgpr` | ELW 최고가 | string | Y | 10 |  |
| 24 | `elw_lwpr` | ELW 최저가 | string | Y | 10 |  |
| 25 | `stck_prdy_clpr` | 주식 전일 종가 | string | Y | 10 |  |
| 26 | `hts_thpr` | HTS 이론가 | string | Y | 14 |  |
| 27 | `dprt` | 괴리율 | string | Y | 11 |  |
| 28 | `atm_cls_name` | ATM 구분 명 | string | Y | 10 |  |
| 29 | `hts_ints_vltl` | HTS 내재 변동성 | string | Y | 16 |  |
| 30 | `acpr` | 행사가 | string | Y | 14 |  |
| 31 | `pvt_scnd_dmrs_prc` | 피벗 2차 디저항 가격 | string | Y | 10 |  |
| 32 | `pvt_frst_dmrs_prc` | 피벗 1차 디저항 가격 | string | Y | 10 |  |
| 33 | `pvt_pont_val` | 피벗 포인트 값 | string | Y | 10 |  |
| 34 | `pvt_frst_dmsp_prc` | 피벗 1차 디지지 가격 | string | Y | 10 |  |
| 35 | `pvt_scnd_dmsp_prc` | 피벗 2차 디지지 가격 | string | Y | 10 |  |
| 36 | `dmsp_val` | 디지지 값 | string | Y | 10 |  |
| 37 | `dmrs_val` | 디저항 값 | string | Y | 10 |  |
| 38 | `elw_sdpr` | ELW 기준가 | string | Y | 10 |  |
| 39 | `apprch_rate` | 접근도 | string | Y | 14 |  |
| 40 | `tick_conv_prc` | 틱환산가 | string | Y | 11 |  |
| 41 | `invt_epmd_cntt` | 투자 유의 내용 | string | Y | 200 |  |

<details><summary>Request Example (Python)</summary>

```json
{
"fid_cond_mrkt_div_code": "J",
"fid_input_iscd": "000660"
}
```

</details>


<details><summary>Response Example</summary>

```json
{
  "output": {
    "elw_prpr": "0",
    "prdy_vrss": "0",
    "prdy_ctrt": "0.00",
    "acml_vol": "0",
    "prdy_vrss_vol_rate": "0.00",
    "unas_isnm": "BASKET",
    "unas_prpr": "0.00",
    "unas_prdy_vrss": "0.00",
    "unas_prdy_vrss_sign": "3",
    "unas_prdy_ctrt": "0.00",
    "bidp": "0",
    "askp": "0",
    "acml_tr_pbmn": "0",
    "vol_tnrt": "0.00",
    "elw_oprc": "0",
    "elw_hgpr": "0",
    "elw_lwpr": "0",
    "stck_prdy_clpr": "0",
    "hts_thpr": "0.00",
    "dprt": "0.00",
    "atm_cls_name": "ATM",
    "hts_ints_vltl": "0.00",
    "acpr": "0.00",
    "pvt_scnd_dmrs_prc": "0",
    "pvt_frst_dmrs_prc": "0",
    "pvt_pont_val": "0",
    "pvt_frst_dmsp_prc": "0",
    "pvt_scnd_dmsp_prc": "0",
    "dmsp_val": "0",
    "dmrs_val": "0",
    "elw_sdpr": "0",
    "apprch_rate": "0.00",
    "tick_conv_prc": "0.00"
  },
  "rt_cd": "0",
  "msg_cd": "MCA00000",
  "msg1": "정상처리 되었습니다!"
}
```

</details>



### ELW 신규상장종목

- **API ID**: 국내주식-181
- **실전 TR_ID**: FHKEW154800C0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/newly-listed`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 신규상장종목 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0297] ELW 신규상장종목 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKEW154800C0 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | Unique key(11548) |
| 2 | `FID_DIV_CLS_CODE` | 분류구분코드 | string | Y | 2 | 전체(02), 콜(00), 풋(01) |
| 3 | `FID_UNAS_INPUT_ISCD` | 기초자산입력종목코드 | string | Y | 12 | 'ex) 000000(전체), 2001(코스피200)<br>, 3003(코스닥150), 005930(삼성전자) ' |
| 4 | `FID_INPUT_ISCD_2` | 입력종목코드2 | string | Y | 8 | '00003(한국투자증권), 00017(KB증권),<br> 00005(미래에셋증권)' |
| 5 | `FID_INPUT_DATE_1` | 입력날짜1 | string | Y | 10 | 날짜 (ex) 20240402) |
| 6 | `FID_BLNC_CLS_CODE` | 결재방법 | string | Y | 2 | 0(전체), 1(일반), 2(조기종료) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `stck_lstn_date` | 주식상장일자 | string | Y | 8 |  |
| 5 | `elw_kor_isnm` | ELW한글종목명 | string | Y | 40 |  |
| 6 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 7 | `unas_isnm` | 기초자산종목명 | string | Y | 40 |  |
| 8 | `pblc_co_name` | 발행회사명 | string | Y | 40 |  |
| 9 | `lstn_stcn` | 상장주수 | string | Y | 18 |  |
| 10 | `acpr` | 행사가 | string | Y | 112 |  |
| 11 | `stck_last_tr_date` | 주식최종거래일자 | string | Y | 8 |  |
| 12 | `elw_ko_barrier` | 조기종료발생기준가격 | string | Y | 112 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:11548
FID_DIV_CLS_CODE:02
FID_UNAS_INPUT_ISCD:000000
FID_INPUT_ISCD_2:00003
FID_INPUT_DATE_1:20240410
FID_BLNG_CLS_CODE:0
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국K924HLB콜",
            "elw_shrn_iscd": "57K924",
            "unas_isnm": "HLB",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "7100000",
            "acpr": "78000.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국K925HMM콜",
            "elw_shrn_iscd": "57K925",
            "unas_isnm": "HMM",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "6700000",
            "acpr": "20000.00",
            "stck_last_tr_date": "20240912",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국K926HMM콜",
            "elw_shrn_iscd": "57K926",
            "unas_isnm": "HMM",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "5600000",
            "acpr": "20000.00",
            "stck_last_tr_date": "20241212",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KB45HMM풋",
            "elw_shrn_iscd": "57KB45",
            "unas_isnm": "HMM",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "6900000",
            "acpr": "17700.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국K927KB금융콜",
            "elw_shrn_iscd": "57K927",
            "unas_isnm": "KB금융",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "24400000",
            "acpr": "73600.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국K928KB금융콜",
            "elw_shrn_iscd": "57K928",
            "unas_isnm": "KB금융",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "22300000",
            "acpr": "73600.00",
            "stck_last_tr_date": "20240912",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국K929KB금융콜",
            "elw_shrn_iscd": "57K929",
            "unas_isnm": "KB금융",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "18200000",
            "acpr": "72000.00",
            "stck_last_tr_date": "20240711",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국K930KB금융콜",
            "elw_shrn_iscd": "57K930",
            "unas_isnm": "KB금융",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "20000000",
            "acpr": "70500.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국K931KB금융콜",
            "elw_shrn_iscd": "57K931",
            "unas_isnm": "KB금융",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "15700000",
            "acpr": "69000.00",
            "stck_last_tr_date": "20240711",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KB46KB금융풋",
            "elw_shrn_iscd": "57KB46",
            "unas_isnm": "KB금융",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "11200000",
            "acpr": "65000.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KB47KB금융풋",
            "elw_shrn_iscd": "57KB47",
            "unas_isnm": "KB금융",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "12000000",
            "acpr": "63700.00",
            "stck_last_tr_date": "20240711",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KB98KOSPI200풋",
            "elw_shrn_iscd": "57KB98",
            "unas_isnm": "KOSPI200",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "7000000",
            "acpr": "400.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KB99KOSPI200풋",
            "elw_shrn_iscd": "57KB99",
            "unas_isnm": "KOSPI200",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "7000000",
            "acpr": "395.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KC00KOSPI200풋",
            "elw_shrn_iscd": "57KC00",
            "unas_isnm": "KOSPI200",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "7000000",
            "acpr": "390.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KC01KOSPI200풋",
            "elw_shrn_iscd": "57KC01",
            "unas_isnm": "KOSPI200",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "9000000",
            "acpr": "387.50",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KC02KOSPI200풋",
            "elw_shrn_iscd": "57KC02",
            "unas_isnm": "KOSPI200",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "10000000",
            "acpr": "385.00",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },
        {
            "stck_lstn_date": "20240320",
            "elw_kor_isnm": "한국KC03KOSPI200풋",
            "elw_shrn_iscd": "57KC03",
            "unas_isnm": "KOSPI200",
            "pblc_co_name": "한국투자증권(주)",
            "lstn_stcn": "9000000",
            "acpr": "382.50",
            "stck_last_tr_date": "20240613",
            "elw_ko_barrier": "0.00"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 투자지표추이(일별)

- **API ID**: 국내주식-173
- **실전 TR_ID**: FHPEW02740200
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/indicator-trend-daily`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 투자지표추이(일별) API입니다.
한국투자 HTS(eFriend Plus) &gt; [0274] ELW 투자지표추이 화면에서 "일자별 비교추이" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02740200 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 시장분류코드 | string | Y | 2 | W |
| 1 | `FID_INPUT_ISCD` | 종콕코드 | string | Y | 12 | ex. 57K281 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `stck_bsop_date` | 주식영업일자 | string | Y | 8 |  |
| 5 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 6 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 7 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 8 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 9 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 10 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |
| 11 | `gear` | 기어링 | string | Y | 84 |  |
| 12 | `tmvl_val` | 시간가치값 | string | Y | 132 |  |
| 13 | `invl_val` | 내재가치값 | string | Y | 132 |  |
| 14 | `prit` | 패리티 | string | Y | 112 |  |
| 15 | `elw_oprc` | ELW시가2 | string | Y | 10 |  |
| 16 | `elw_hgpr` | ELW최고가 | string | Y | 10 |  |
| 17 | `elw_lwpr` | ELW최저가 | string | Y | 10 |  |
| 18 | `apprch_rate` | 접근도 | string | Y | 112 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:57K281
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "stck_bsop_date": "20240503",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "1000020",
            "lvrg_val": "-11.0377",
            "gear": "19.45",
            "tmvl_val": "18.00",
            "invl_val": "22.00",
            "prit": "102.82",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "35",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240502",
            "elw_prpr": "45",
            "prdy_vrss_sign": "3",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "acml_vol": "789280",
            "lvrg_val": "-9.5810",
            "gear": "17.33",
            "tmvl_val": "25.00",
            "invl_val": "20.00",
            "prit": "102.56",
            "elw_oprc": "45",
            "elw_hgpr": "45",
            "elw_lwpr": "35",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240430",
            "elw_prpr": "45",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-10.00",
            "acml_vol": "62090",
            "lvrg_val": "-10.0683",
            "gear": "17.22",
            "tmvl_val": "20.00",
            "invl_val": "25.00",
            "prit": "103.22",
            "elw_oprc": "50",
            "elw_hgpr": "50",
            "elw_lwpr": "45",
            "apprch_rate": "0.00"
        },...
        {
            "stck_bsop_date": "20240117",
            "elw_prpr": "0",
            "prdy_vrss_sign": "0",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "lvrg_val": "-0.0000",
            "gear": "0.00",
            "tmvl_val": "-90.00",
            "invl_val": "90.00",
            "prit": "0.00",
            "elw_oprc": "0",
            "elw_hgpr": "0",
            "elw_lwpr": "0",
            "apprch_rate": "0.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 민감도 순위

- **API ID**: 국내주식-170
- **실전 TR_ID**: FHPEW02850000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/ranking/sensitivity`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 민감도 순위 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0285] ELW 민감도 순위 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02850000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | Unique key(20285) |
| 2 | `FID_UNAS_INPUT_ISCD` | 기초자산입력종목코드 | string | Y | 12 | '000000(전체), 2001(코스피200)<br>, 3003(코스닥150), 005930(삼성전자) ' |
| 3 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | '00000(전체), 00003(한국투자증권)<br>, 00017(KB증권), 00005(미래에셋주식회사)' |
| 4 | `FID_DIV_CLS_CODE` | 콜풋구분코드 | string | Y | 2 | 0(전체), 1(콜), 2(풋) |
| 5 | `FID_INPUT_PRICE_1` | 가격(이상) | string | Y | 12 |  |
| 6 | `FID_INPUT_PRICE_2` | 가격(이하) | string | Y | 12 |  |
| 7 | `FID_INPUT_VOL_1` | 거래량(이상) | string | Y | 18 |  |
| 8 | `FID_INPUT_VOL_2` | 거래량(이하) | string | Y | 18 |  |
| 9 | `FID_RANK_SORT_CLS_CODE` | 순위정렬구분코드 | string | Y | 2 | '0(이론가), 1(델타), 2(감마), 3(로), 4(베가) , 5(로)<br>, 6(내재변동성), 7(90일변동성)' |
| 10 | `FID_INPUT_RMNN_DYNU_1` | 잔존일수(이상) | string | Y | 5 |  |
| 11 | `FID_INPUT_DATE_1` | 조회기준일 | string | Y | 10 |  |
| 12 | `FID_BLNG_CLS_CODE` | 결재방법 | string | Y | 2 | 0(전체), 1(일반), 2(조기종료) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 5 | `elw_kor_isnm` | ELW한글종목명 | string | Y | 40 |  |
| 6 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 7 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 8 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 9 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 10 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 11 | `hts_thpr` | HTS이론가 | string | Y | 112 |  |
| 12 | `delta_val` | 델타값 | string | Y | 114 |  |
| 13 | `gama` | 감마 | string | Y | 84 |  |
| 14 | `theta` | 세타 | string | Y | 84 |  |
| 15 | `vega` | 베가 | string | Y | 84 |  |
| 16 | `rho` | 로우 | string | Y | 84 |  |
| 17 | `hts_ints_vltl` | HTS내재변동성 | string | Y | 114 |  |
| 18 | `d90_hist_vltl` | 90일역사적변동성 | string | Y | 114 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:20285
FID_UNAS_INPUT_ISCD:000000
FID_INPUT_ISCD:00000
FID_INPUT_RMNN_DYNU_1:0
FID_DIV_CLS_CODE:0
FID_INPUT_PRICE_1:
FID_INPUT_PRICE_2:
FID_INPUT_VOL_1:
FID_INPUT_VOL_2:
FID_RANK_SORT_CLS_CODE:0
FID_INPUT_RMNN_DYNU_1:
FID_INPUT_DATE_1:
FID_BLNG_CLS_CODE:0
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "elw_shrn_iscd": "57K852",
            "elw_kor_isnm": "한국K852KOSPI200콜",
            "elw_prpr": "7770",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "hts_thpr": "8290.81",
            "delta_val": "1.000000",
            "gama": "0.0000",
            "theta": "3.8670",
            "vega": "0.0000",
            "rho": "19.3352",
            "hts_ints_vltl": "0.00",
            "d90_hist_vltl": "16.793295"
        },
        {
            "elw_shrn_iscd": "57JAVS",
            "elw_kor_isnm": "한국JAVSKOSPI200콜",
            "elw_prpr": "4690",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "hts_thpr": "7891.32",
            "delta_val": "1.000000",
            "gama": "0.0000",
            "theta": "3.9449",
            "vega": "0.0000",
            "rho": "119.9611",
            "hts_ints_vltl": "0.00",
            "d90_hist_vltl": "16.793295"
        },
        {
            "elw_shrn_iscd": "57JAVD",
            "elw_kor_isnm": "한국JAVDKOSPI200콜",
            "elw_prpr": "7800",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "hts_thpr": "7793.07",
            "delta_val": "0.993055",
            "gama": "0.0005",
            "theta": "4.3385",
            "vega": "4.0200",
            "rho": "91.7439",
            "hts_ints_vltl": "17.48",
            "d90_hist_vltl": "16.793295"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 기초자산별 종목시세

- **API ID**: 국내주식-186
- **실전 TR_ID**: FHKEW154101C0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/udrl-asset-price`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 기초자산별 종목시세  API입니다.
한국투자 HTS(eFriend Plus) &gt; [0288] ELW 기초자산별 ELW 시세 화면의 "우측 기초자산별 종목 리스트" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKEW154101C0 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (16)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분(W) |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | Uniquekey(11541) |
| 2 | `FID_MRKT_CLS_CODE` | 시장구분코드 | string | Y | 2 | 전체(A),콜(C),풋(P) |
| 3 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | '00000(전체), 00003(한국투자증권)<br>, 00017(KB증권), 00005(미래에셋주식회사)' |
| 4 | `FID_UNAS_INPUT_ISCD` | 기초자산입력종목코드 | string | Y | 12 |  |
| 5 | `FID_VOL_CNT` | 거래량수 | string | Y | 12 | 전일거래량(정수량미만) |
| 6 | `FID_TRGT_EXLS_CLS_CODE` | 대상제외구분코드 | string | Y | 32 | 거래불가종목제외(0:미체크,1:체크) |
| 7 | `FID_INPUT_PRICE_1` | 입력가격1 | string | Y | 12 | 가격~원이상 |
| 8 | `FID_INPUT_PRICE_2` | 입력가격2 | string | Y | 12 | 가격~월이하 |
| 9 | `FID_INPUT_VOL_1` | 입력거래량1 | string | Y | 18 | 거래량~계약이상 |
| 10 | `FID_INPUT_VOL_2` | 입력거래량2 | string | Y | 18 | 거래량~계약이하 |
| 11 | `FID_INPUT_RMNN_DYNU_1` | 입력잔존일수1 | string | Y | 5 | 잔존일(~일이상) |
| 12 | `FID_INPUT_RMNN_DYNU_2` | 입력잔존일수2 | string | Y | 5 | 잔존일(~일이하) |
| 13 | `FID_OPTION` | 옵션 | string | Y | 5 | 옵션상태(0:없음,1:ATM,2:ITM,3:OTM) |
| 14 | `FID_INPUT_OPTION_1` | 입력옵션1 | string | Y | 10 |  |
| 15 | `FID_INPUT_OPTION_2` | 입력옵션2 | string | Y | 10 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (33)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 5 | `hts_kor_isnm` | HTS한글종목명 | string | Y | 40 |  |
| 6 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 7 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 8 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 9 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 10 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 11 | `acpr` | 행사가 | string | Y | 112 |  |
| 12 | `prls_qryr_stpr_prc` | 손익분기주가가격 | string | Y | 112 |  |
| 13 | `hts_rmnn_dynu` | HTS잔존일수 | string | Y | 5 |  |
| 14 | `hts_ints_vltl` | HTS내재변동성 | string | Y | 114 |  |
| 15 | `stck_cnvr_rate` | 주식전환비율 | string | Y | 136 |  |
| 16 | `lp_hvol` | LP보유량 | string | Y | 18 |  |
| 17 | `lp_rlim` | LP비중 | string | Y | 52 |  |
| 18 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |
| 19 | `gear` | 기어링 | string | Y | 84 |  |
| 20 | `delta_val` | 델타값 | string | Y | 114 |  |
| 21 | `gama` | 감마 | string | Y | 84 |  |
| 22 | `vega` | 베가 | string | Y | 84 |  |
| 23 | `theta` | 세타 | string | Y | 84 |  |
| 24 | `prls_qryr_rate` | 손익분기비율 | string | Y | 84 |  |
| 25 | `cfp` | 자본지지점 | string | Y | 112 |  |
| 26 | `prit` | 패리티 | string | Y | 112 |  |
| 27 | `invl_val` | 내재가치값 | string | Y | 132 |  |
| 28 | `tmvl_val` | 시간가치값 | string | Y | 132 |  |
| 29 | `hts_thpr` | HTS이론가 | string | Y | 112 |  |
| 30 | `stck_lstn_date` | 주식상장일자 | string | Y | 8 |  |
| 31 | `stck_last_tr_date` | 주식최종거래일자 | string | Y | 8 |  |
| 32 | `lp_ntby_qty` | LP순매도량 | string | Y | 18 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:11541
FID_MRKT_CLS_CODE:A
FID_INPUT_ISCD:00000
FID_UNAS_INPUT_ISCD:005930
FID_VOL_CNT:
FID_TRGT_EXLS_CLS_CODE:0
FID_INPUT_PRICE_1:
FID_INPUT_PRICE_2:
FID_INPUT_VOL_1:
FID_INPUT_VOL_2:
FID_INPUT_RMNN_DYNU_1:
FID_INPUT_RMNN_DYNU_2:
FID_OPTION:0
FID_INPUT_OPTION_1:
FID_INPUT_OPTION_2:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "elw_shrn_iscd": "57JAAQ",
            "hts_kor_isnm": "한국JAAQ삼성전자풋",
            "elw_prpr": "10",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "63300.00",
            "prls_qryr_stpr_prc": "62300.00",
            "hts_rmnn_dynu": "42",
            "hts_ints_vltl": "60.72",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "17298270",
            "lp_rlim": "99.99",
            "lvrg_val": "-9.448319",
            "gear": "77.7000",
            "delta_val": "-0.121600",
            "gama": "0.0000",
            "vega": "0.5078",
            "theta": "0.5759",
            "prls_qryr_rate": "-19.8100",
            "cfp": "-19.5600",
            "prit": "81.46",
            "invl_val": "0.00",
            "tmvl_val": "10.00",
            "hts_thpr": "0.18",
            "stck_lstn_date": "20231018",
            "stck_last_tr_date": "20240613",
            "lp_ntby_qty": "0"
        },
        {
            "elw_shrn_iscd": "57JAML",
            "hts_kor_isnm": "한국JAML삼성전자콜",
            "elw_prpr": "120",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "64700.00",
            "prls_qryr_stpr_prc": "76700.00",
            "hts_rmnn_dynu": "7",
            "hts_ints_vltl": "0.00",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "11995780",
            "lp_rlim": "99.96",
            "lvrg_val": "5.184000",
            "gear": "6.4800",
            "delta_val": "0.800000",
            "gama": "0.0000",
            "vega": "0.0000",
            "theta": "0.0669",
            "prls_qryr_rate": "-1.4100",
            "cfp": "-1.6700",
            "prit": "120.24",
            "invl_val": "132.00",
            "tmvl_val": "-12.00",
            "hts_thpr": "131.60",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20240509",
            "lp_ntby_qty": "0"
        },
        {
            "elw_shrn_iscd": "57JAMM",
            "hts_kor_isnm": "한국JAMM삼성전자콜",
            "elw_prpr": "115",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "67300.00",
            "prls_qryr_stpr_prc": "78800.00",
            "hts_rmnn_dynu": "42",
            "hts_ints_vltl": "32.23",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "12499500",
            "lp_rlim": "100.00",
            "lvrg_val": "6.288443",
            "gear": "6.7600",
            "delta_val": "0.930243",
            "gama": "0.0000",
            "vega": "0.3368",
            "theta": "0.2915",
            "prls_qryr_rate": "1.2800",
            "cfp": "1.5000",
            "prit": "115.60",
            "invl_val": "105.00",
            "tmvl_val": "10.00",
            "hts_thpr": "108.09",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20240613",
            "lp_ntby_qty": "0"
        },
        {
            "elw_shrn_iscd": "57JAMN",
            "hts_kor_isnm": "한국JAMN삼성전자콜",
            "elw_prpr": "120",
            "prdy_vrss": "5",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "4.35",
            "acml_vol": "10",
            "acpr": "68700.00",
            "prls_qryr_stpr_prc": "80700.00",
            "hts_rmnn_dynu": "161",
            "hts_ints_vltl": "27.90",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "8800820",
            "lp_rlim": "84.62",
            "lvrg_val": "5.212408",
            "gear": "6.4800",
            "delta_val": "0.804384",
            "gama": "0.0000",
            "vega": "1.3937",
            "theta": "0.2545",
            "prls_qryr_rate": "3.7200",
            "cfp": "4.4000",
            "prit": "113.24",
            "invl_val": "91.00",
            "tmvl_val": "29.00",
            "hts_thpr": "111.27",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20241010",
            "lp_ntby_qty": "0"
        },
        {
            "elw_shrn_iscd": "57JAMP",
            "hts_kor_isnm": "한국JAMP삼성전자콜",
            "elw_prpr": "90",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-10.00",
            "acml_vol": "20",
            "acpr": "70200.00",
            "prls_qryr_stpr_prc": "79200.00",
            "hts_rmnn_dynu": "70",
            "hts_ints_vltl": "28.96",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "12997850",
            "lp_rlim": "99.98",
            "lvrg_val": "7.137444",
            "gear": "8.6400",
            "delta_val": "0.826093",
            "gama": "0.0000",
            "vega": "0.8580",
            "theta": "0.3448",
            "prls_qryr_rate": "1.7900",
            "cfp": "2.0300",
            "prit": "110.82",
            "invl_val": "76.00",
            "tmvl_val": "14.00",
            "hts_thpr": "86.23",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20240711",
            "lp_ntby_qty": "-20"
        },
        {
            "elw_shrn_iscd": "57JAMR",
            "hts_kor_isnm": "한국JAMR삼성전자콜",
            "elw_prpr": "75",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "73300.00",
            "prls_qryr_stpr_prc": "80800.00",
            "hts_rmnn_dynu": "98",
            "hts_ints_vltl": "27.07",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "13926710",
            "lp_rlim": "98.77",
            "lvrg_val": "7.394173",
            "gear": "10.3700",
            "delta_val": "0.713035",
            "gama": "0.0000",
            "vega": "1.3629",
            "theta": "0.3448",
            "prls_qryr_rate": "3.8500",
            "cfp": "4.2600",
            "prit": "106.13",
            "invl_val": "45.00",
            "tmvl_val": "30.00",
            "hts_thpr": "68.15",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20240808",
            "lp_ntby_qty": "0"
        },
        {
            "elw_shrn_iscd": "57JAMS",
            "hts_kor_isnm": "한국JAMS삼성전자콜",
            "elw_prpr": "120",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "73300.00",
            "prls_qryr_stpr_prc": "85300.00",
            "hts_rmnn_dynu": "133",
            "hts_ints_vltl": "26.88",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "13399930",
            "lp_rlim": "100.00",
            "lvrg_val": "4.540122",
            "gear": "6.4800",
            "delta_val": "0.700636",
            "gama": "0.0000",
            "vega": "1.6226",
            "theta": "0.3056",
            "prls_qryr_rate": "9.6400",
            "cfp": "11.3900",
            "prit": "106.13",
            "invl_val": "45.00",
            "tmvl_val": "75.00",
            "hts_thpr": "74.43",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20240912",
            "lp_ntby_qty": "0"
        },
        {
            "elw_shrn_iscd": "57JAPS",
            "hts_kor_isnm": "한국JAPS삼성전자풋",
            "elw_prpr": "10",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "70000.00",
            "prls_qryr_stpr_prc": "69000.00",
            "hts_rmnn_dynu": "42",
            "hts_ints_vltl": "39.14",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "8789750",
            "lp_rlim": "99.88",
            "lvrg_val": "-13.763233",
            "gear": "77.7000",
            "delta_val": "-0.177133",
            "gama": "0.0000",
            "vega": "0.6533",
            "theta": "0.4692",
            "prls_qryr_rate": "-11.1900",
            "cfp": "-11.0500",
            "prit": "90.09",
            "invl_val": "0.00",
            "tmvl_val": "10.00",
            "hts_thpr": "3.39",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20240613",
            "lp_ntby_qty": "0"
        },
        {
            "elw_shrn_iscd": "57JAPT",
            "hts_kor_isnm": "한국JAPT삼성전자풋",
            "elw_prpr": "20",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "70000.00",
            "prls_qryr_stpr_prc": "68000.00",
            "hts_rmnn_dynu": "133",
            "hts_ints_vltl": "31.53",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "7593700",
            "lp_rlim": "99.92",
            "lvrg_val": "-9.186005",
            "gear": "38.8500",
            "delta_val": "-0.236448",
            "gama": "0.0000",
            "vega": "1.4404",
            "theta": "0.2237",
            "prls_qryr_rate": "-12.4800",
            "cfp": "-12.1700",
            "prit": "90.09",
            "invl_val": "0.00",
            "tmvl_val": "20.00",
            "hts_thpr": "13.97",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20240912",
            "lp_ntby_qty": "0"
        },
        {
            "elw_shrn_iscd": "57JAZR",
            "hts_kor_isnm": "한국JAZR삼성전자콜",
            "elw_prpr": "70",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-12.50",
            "acml_vol": "5130",
            "acpr": "77300.00",
            "prls_qryr_stpr_prc": "84300.00",
            "hts_rmnn_dynu": "196",
            "hts_ints_vltl": "26.13",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "13970240",
            "lp_rlim": "97.69",
            "lvrg_val": "6.527688",
            "gear": "11.1000",
            "delta_val": "0.588080",
            "gama": "0.0000",
            "vega": "2.1844",
            "theta": "0.2725",
            "prls_qryr_rate": "8.4900",
            "cfp": "9.3300",
            "prit": "100.51",
            "invl_val": "6.00",
            "tmvl_val": "64.00",
            "hts_thpr": "60.18",
            "stck_lstn_date": "20231220",
            "stck_last_tr_date": "20241114",
            "lp_ntby_qty": "5020"
        },
        {
            "elw_shrn_iscd": "57JAZS",
            "hts_kor_isnm": "한국JAZS삼성전자콜",
            "elw_prpr": "55",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "504200",
            "acpr": "75600.00",
            "prls_qryr_stpr_prc": "81100.00",
            "hts_rmnn_dynu": "70",
            "hts_ints_vltl": "28.73",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "15421560",
            "lp_rlim": "98.23",
            "lvrg_val": "8.965918",
            "gear": "14.1200",
            "delta_val": "0.634980",
            "gama": "0.0000",
            "vega": "1.2562",
            "theta": "0.4515",
            "prls_qryr_rate": "4.3700",
            "cfp": "4.7000",
            "prit": "102.77",
            "invl_val": "23.00",
            "tmvl_val": "32.00",
            "hts_thpr": "46.86",
            "stck_lstn_date": "20231220",
            "stck_last_tr_date": "20240711",
            "lp_ntby_qty": "45700"
        },...
        {
            "elw_shrn_iscd": "57KA61",
            "hts_kor_isnm": "한국KA61삼성전자콜",
            "elw_prpr": "40",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "331400",
            "acpr": "78300.00",
            "prls_qryr_stpr_prc": "82300.00",
            "hts_rmnn_dynu": "70",
            "hts_ints_vltl": "28.17",
            "stck_cnvr_rate": "0.010000",
            "lp_hvol": "23296960",
            "lp_rlim": "99.99",
            "lvrg_val": "10.171226",
            "gear": "19.4200",
            "delta_val": "0.523750",
            "gama": "0.0000",
            "vega": "1.3308",
            "theta": "0.4570",
            "prls_qryr_rate": "5.9200",
            "cfp": "6.2400",
            "prit": "99.23",
            "invl_val": "0.00",
            "tmvl_val": "40.00",
            "hts_thpr": "32.21",
            "stck_lstn_date": "20240320",
            "stck_last_tr_date": "20240711",
            "lp_ntby_qty": "0"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 종목검색

- **API ID**: 국내주식-166
- **실전 TR_ID**: FHKEW15100000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/cond-search`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 종목검색 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0291] ELW 종목검색 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
한 번의 호출에 최대 100건까지 확인 가능합니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKEW15100000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (57)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | ELW(W) |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | 화면번호(11510) |
| 2 | `FID_RANK_SORT_CLS_CODE` | 순위정렬구분코드 | string | Y | 2 | '정렬1정렬안함(0)종목코드(1)현재가(2)대비율(3)거래량(4)행사가격(5)<br>전환비율(6)상장일(7)만기일(8)잔존일수(9)레버리지(10)' |
| 3 | `FID_INPUT_CNT_1` | 입력수1 | string | Y | 12 | 정렬1기준 - 상위(1)하위(2) |
| 4 | `FID_RANK_SORT_CLS_CODE_2` | 순위정렬구분코드2 | string | Y | 2 | 정렬2 |
| 5 | `FID_INPUT_CNT_2` | 입력수2 | string | Y | 12 | 정렬2기준 - 상위(1)하위(2) |
| 6 | `FID_RANK_SORT_CLS_CODE_3` | 순위정렬구분코드3 | string | Y | 2 | 정렬3 |
| 7 | `FID_INPUT_CNT_3` | 입력수3 | string | Y | 12 | 정렬3기준 - 상위(1)하위(2) |
| 8 | `FID_TRGT_CLS_CODE` | 대상구분코드 | string | Y | 32 | 0:발행회사종목코드,1:기초자산종목코드,2:FID시장구분코드,3:FID입력날짜1(상장일),<br>4:FID입력날짜2(만기일),5:LP회원사종목코드,6:행사가기초자산비교>=(1) <=(2), <br>7:잔존일 이상 이하, 8:현재가, 9:전일대비율, 10:거래량, 11:최종거래일, 12:레버리지 |
| 9 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | 발행사종목코드전체(00000) |
| 10 | `FID_UNAS_INPUT_ISCD` | 기초자산입력종목코드 | string | Y | 12 |  |
| 11 | `FID_MRKT_CLS_CODE` | 시장구분코드 | string | Y | 2 | 권리유형전체(A)콜(CO)풋(PO) |
| 12 | `FID_INPUT_DATE_1` | 입력날짜1 | string | Y | 10 | 상장일전체(0)금일(1)7일이하(2)8~30일(3)31~90일(4) |
| 13 | `FID_INPUT_DATE_2` | 입력날짜2 | string | Y | 10 | 만기일전체(0)1개월(1)1~2(2)2~3(3)3~6(4)6~9(5)9~12(6)12이상(7) |
| 14 | `FID_INPUT_ISCD_2` | 입력종목코드2 | string | Y | 8 |  |
| 15 | `FID_ETC_CLS_CODE` | 기타구분코드 | string | Y | 2 | 행사가전체(0)>=(1) |
| 16 | `FID_INPUT_RMNN_DYNU_1` | 입력잔존일수1 | string | Y | 5 | 잔존일이상 |
| 17 | `FID_INPUT_RMNN_DYNU_2` | 입력잔존일수2 | string | Y | 5 | 잔존일이하 |
| 18 | `FID_PRPR_CNT1` | 현재가수1 | string | Y | 11 | 현재가이상 |
| 19 | `FID_PRPR_CNT2` | 현재가수2 | string | Y | 11 | 현재가이하 |
| 20 | `FID_RSFL_RATE1` | 등락비율1 | string | Y | 132 | 전일대비율이상 |
| 21 | `FID_RSFL_RATE2` | 등락비율2 | string | Y | 132 | 전일대비율이하 |
| 22 | `FID_VOL1` | 거래량1 | string | Y | 18 | 거래량이상 |
| 23 | `FID_VOL2` | 거래량2 | string | Y | 18 | 거래량이하 |
| 24 | `FID_APLY_RANG_PRC_1` | 적용범위가격1 | string | Y | 18 | 최종거래일from |
| 25 | `FID_APLY_RANG_PRC_2` | 적용범위가격2 | string | Y | 18 | 최종거래일to |
| 26 | `FID_LVRG_VAL1` | 레버리지값1 | string | Y | 114 |  |
| 27 | `FID_LVRG_VAL2` | 레버리지값2 | string | Y | 114 |  |
| 28 | `FID_VOL3` | 거래량3 | string | Y | 18 | LP종료일from |
| 29 | `FID_VOL4` | 거래량4 | string | Y | 18 | LP종료일to |
| 30 | `FID_INTS_VLTL1` | 내재변동성1 | string | Y | 114 | 내재변동성이상 |
| 31 | `FID_INTS_VLTL2` | 내재변동성2 | string | Y | 114 | 내재변동성이하 |
| 32 | `FID_PRMM_VAL1` | 프리미엄값1 | string | Y | 132 | 프리미엄이상 |
| 33 | `FID_PRMM_VAL2` | 프리미엄값2 | string | Y | 132 | 프리미엄이하 |
| 34 | `FID_GEAR1` | 기어링1 | string | Y | 84 | 기어링이상 |
| 35 | `FID_GEAR2` | 기어링2 | string | Y | 84 | 기어링이하 |
| 36 | `FID_PRLS_QRYR_RATE1` | 손익분기비율1 | string | Y | 132 | 손익분기이상 |
| 37 | `FID_PRLS_QRYR_RATE2` | 손익분기비율2 | string | Y | 132 | 손익분기이하 |
| 38 | `FID_DELTA1` | 델타1 | string | Y | 84 | 델타이상 |
| 39 | `FID_DELTA2` | 델타2 | string | Y | 84 | 델타이하 |
| 40 | `FID_ACPR1` | 행사가1 | string | Y | 133 |  |
| 41 | `FID_ACPR2` | 행사가2 | string | Y | 133 |  |
| 42 | `FID_STCK_CNVR_RATE1` | 주식전환비율1 | string | Y | 94 | 전환비율이상 |
| 43 | `FID_STCK_CNVR_RATE2` | 주식전환비율2 | string | Y | 94 | 전환비율이하 |
| 44 | `FID_DIV_CLS_CODE` | 분류구분코드 | string | Y | 2 | 0:전체,1:일반,2:조기종료 |
| 45 | `FID_PRIT1` | 패리티1 | string | Y | 112 | 패리티이상 |
| 46 | `FID_PRIT2` | 패리티2 | string | Y | 112 | 패리티이하 |
| 47 | `FID_CFP1` | 자본지지점1 | string | Y | 112 | 배리어이상 |
| 48 | `FID_CFP2` | 자본지지점2 | string | Y | 112 | 배리어이하 |
| 49 | `FID_INPUT_NMIX_PRICE_1` | 지수가격1 | string | Y | 112 | LP보유비율이상 |
| 50 | `FID_INPUT_NMIX_PRICE_2` | 지수가격2 | string | Y | 112 | LP보유비율이하 |
| 51 | `FID_EGEA_VAL1` | E기어링값1 | string | Y | 132 | 접근도이상 |
| 52 | `FID_EGEA_VAL2` | E기어링값2 | string | Y | 132 | 접근도이하 |
| 53 | `FID_INPUT_DVDN_ERT` | 배당수익율 | string | Y | 112 | 손익분기점이상 |
| 54 | `FID_INPUT_HIST_VLTL` | 역사적변동성 | string | Y | 112 | 손익분기점이하 |
| 55 | `FID_THETA1` | 세타1 | string | Y | 84 | MONEYNESS이상 |
| 56 | `FID_THETA2` | 세타2 | string | Y | 84 | MONEYNESS이하 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (47)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `bond_shrn_iscd` | 채권단축종목코드 | string | Y | 9 |  |
| 5 | `hts_kor_isnm` | HTS한글종목명 | string | Y | 40 |  |
| 6 | `rght_type_name` | 권리유형명 | string | Y | 40 |  |
| 7 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 8 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 9 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 10 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 11 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 12 | `acpr` | 행사가 | string | Y | 112 |  |
| 13 | `stck_cnvr_rate` | 주식전환비율 | string | Y | 136 |  |
| 14 | `stck_lstn_date` | 주식상장일자 | string | Y | 8 |  |
| 15 | `stck_last_tr_date` | 주식최종거래일자 | string | Y | 8 |  |
| 16 | `hts_rmnn_dynu` | HTS잔존일수 | string | Y | 5 |  |
| 17 | `unas_isnm` | 기초자산종목명 | string | Y | 40 |  |
| 18 | `unas_prpr` | 기초자산현재가 | string | Y | 112 |  |
| 19 | `unas_prdy_vrss` | 기초자산전일대비 | string | Y | 112 |  |
| 20 | `unas_prdy_vrss_sign` | 기초자산전일대비부호 | string | Y | 1 |  |
| 21 | `unas_prdy_ctrt` | 기초자산전일대비율 | string | Y | 82 |  |
| 22 | `unas_acml_vol` | 기초자산누적거래량 | string | Y | 18 |  |
| 23 | `moneyness` | MONEYNESS | string | Y | 132 |  |
| 24 | `atm_cls_name` | ATM구분명 | string | Y | 10 |  |
| 25 | `prit` | 패리티 | string | Y | 112 |  |
| 26 | `delta_val` | 델타값 | string | Y | 114 |  |
| 27 | `hts_ints_vltl` | HTS내재변동성 | string | Y | 114 |  |
| 28 | `tmvl_val` | 시간가치값 | string | Y | 132 |  |
| 29 | `gear` | 기어링 | string | Y | 84 |  |
| 30 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |
| 31 | `prls_qryr_rate` | 손익분기비율 | string | Y | 84 |  |
| 32 | `cfp` | 자본지지점 | string | Y | 112 |  |
| 33 | `lstn_stcn` | 상장주수 | string | Y | 18 |  |
| 34 | `pblc_co_name` | 발행회사명 | string | Y | 40 |  |
| 35 | `lp_mbcr_name` | LP회원사명 | string | Y | 50 |  |
| 36 | `lp_hldn_rate` | LP보유비율 | string | Y | 84 |  |
| 37 | `elw_rght_form` | ELW권리형태 | string | Y | 20 |  |
| 38 | `elw_ko_barrier` | 조기종료발생기준가격 | string | Y | 112 |  |
| 39 | `apprch_rate` | 접근도 | string | Y | 112 |  |
| 40 | `unas_shrn_iscd` | 기초자산단축종목코드 | string | Y | 9 |  |
| 41 | `mtrt_date` | 만기일자 | string | Y | 8 |  |
| 42 | `prmm_val` | 프리미엄값 | string | Y | 114 |  |
| 43 | `stck_lp_fin_date` | 주식LP종료일자 | string | Y | 8 |  |
| 44 | `tick_conv_prc` | 틱환산가 | string | Y | 11 |  |
| 45 | `prls_qryr_stpr_prc` | 손익분기주가가격 | string | Y | 112 |  |
| 46 | `lp_hvol` | LP보유량 | string | Y | 18 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:11510
FID_RANK_SORT_CLS_CODE:0
FID_INPUT_CNT_1:1
FID_RANK_SORT_CLS_CODE_2:
FID_INPUT_CNT_2:
FID_RANK_SORT_CLS_CODE_3:
FID_INPUT_CNT_3:
FID_TRGT_CLS_CODE:
FID_INPUT_ISCD:
FID_UNAS_INPUT_ISCD:
FID_MRKT_CLS_CODE:
FID_INPUT_DATE_1:
FID_INPUT_DATE_2:
FID_INPUT_ISCD_2:
FID_ETC_CLS_CODE:
FID_INPUT_RMNN_DYNU_1:
FID_INPUT_RMNN_DYNU_2:
FID_PRPR_CNT1:
FID_PRPR_CNT2:
FID_RSFL_RATE1:
FID_RSFL_RATE2:
FID_VOL1:
FID_VOL2:
FID_APLY_RANG_PRC_1:
FID_APLY_RANG_PRC_2:
FID_LVRG_VAL1:
FID_LVRG_VAL2:
FID_VOL3:
FID_VOL4:
FID_INTS_VLTL1:
FID_INTS_VLTL2:
FID_PRMM_VAL1:
FID_PRMM_VAL2:
FID_GEAR1:
FID_GEAR2:
FID_PRLS_QRYR_RATE1:
FID_PRLS_QRYR_RATE2:
FID_DELTA1:
FID_DELTA2:
FID_ACPR1:
FID_ACPR2:
FID_STCK_CNVR_RATE1:
FID_STCK_CNVR_RATE2:
FID_DIV_CLS_CODE:
FID_PRIT1:
FID_PRIT2:
FID_CFP1:
FID_CFP2:
FID_INPUT_NMIX_PRICE_1:
FID_INPUT_NMIX_PRICE_2:
FID_EGEA_VAL1:
FID_EGEA_VAL2:
FID_INPUT_DVDN_ERT:
FID_INPUT_HIST_VLTL:
FID_THETA1:
FID_THETA2:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "bond_shrn_iscd": "57JAES",
            "hts_kor_isnm": "한국JAESKOSPI200콜",
            "rght_type_name": "CALL",
            "elw_prpr": "1560",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "325.00",
            "stck_cnvr_rate": "100.000000",
            "stck_lstn_date": "20231018",
            "stck_last_tr_date": "20240613",
            "hts_rmnn_dynu": "1",
            "unas_isnm": "KOSPI200",
            "unas_prpr": "377.90",
            "unas_prdy_vrss": "6.78",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "1.83",
            "unas_acml_vol": "80478000",
            "moneyness": "16.277",
            "atm_cls_name": "ITM",
            "prit": "116.27",
            "delta_val": "1.000000",
            "hts_ints_vltl": "0.00",
            "tmvl_val": "-3751.00",
            "gear": "24.2200",
            "lvrg_val": "24.219999",
            "prls_qryr_rate": "-9.8600",
            "cfp": "-10.2900",
            "lstn_stcn": "10000000",
            "pblc_co_name": "한국투자증권(주)",
            "lp_mbcr_name": "한국증권",
            "lp_hldn_rate": "100.00",
            "elw_rght_form": "표준형",
            "elw_ko_barrier": "0.00",
            "apprch_rate": "0.00",
            "unas_shrn_iscd": "2001",
            "mtrt_date": "20240617",
            "prmm_val": "4.13",
            "stck_lp_fin_date": "20240613",
            "tick_conv_prc": "5.00",
            "prls_qryr_stpr_prc": "340.60",
            "lp_hvol": "9999800"
        },
        {
            "bond_shrn_iscd": "57JAET",
            "hts_kor_isnm": "한국JAETKOSPI200콜",
            "rght_type_name": "CALL",
            "elw_prpr": "4090",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "322.50",
            "stck_cnvr_rate": "100.000000",
            "stck_lstn_date": "20231018",
            "stck_last_tr_date": "20240613",
            "hts_rmnn_dynu": "1",
            "unas_isnm": "KOSPI200",
            "unas_prpr": "377.90",
            "unas_prdy_vrss": "6.78",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "1.83",
            "unas_acml_vol": "80478000",
            "moneyness": "17.178",
            "atm_cls_name": "ITM",
            "prit": "117.17",
            "delta_val": "1.000000",
            "hts_ints_vltl": "0.00",
            "tmvl_val": "-1471.00",
            "gear": "9.2300",
            "lvrg_val": "9.230000",
            "prls_qryr_rate": "-3.8300",
            "cfp": "-4.2900",
            "lstn_stcn": "9000000",
            "pblc_co_name": "한국투자증권(주)",
            "lp_mbcr_name": "한국증권",
            "lp_hldn_rate": "99.99",
            "elw_rght_form": "표준형",
            "elw_ko_barrier": "0.00",
            "apprch_rate": "0.00",
            "unas_shrn_iscd": "2001",
            "mtrt_date": "20240617",
            "prmm_val": "10.82",
            "stck_lp_fin_date": "20240613",
            "tick_conv_prc": "5.00",
            "prls_qryr_stpr_prc": "363.40",
            "lp_hvol": "8999270"
        },
        {
            "bond_shrn_iscd": "57JAEV",
            "hts_kor_isnm": "한국JAEVKOSPI200콜",
            "rght_type_name": "CALL",
            "elw_prpr": "4510",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "320.00",
            "stck_cnvr_rate": "100.000000",
            "stck_lstn_date": "20231018",
            "stck_last_tr_date": "20240613",
            "hts_rmnn_dynu": "1",
            "unas_isnm": "KOSPI200",
            "unas_prpr": "377.90",
            "unas_prdy_vrss": "6.78",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "1.83",
            "unas_acml_vol": "80478000",
            "moneyness": "18.094",
            "atm_cls_name": "ITM",
            "prit": "118.09",
            "delta_val": "0.963518",
            "hts_ints_vltl": "177.59",
            "tmvl_val": "-1301.00",
            "gear": "8.3700",
            "lvrg_val": "8.064646",
            "prls_qryr_rate": "-3.3800",
            "cfp": "-3.8400",
            "lstn_stcn": "11000000",
            "pblc_co_name": "한국투자증권(주)",
            "lp_mbcr_name": "한국증권",
            "lp_hldn_rate": "99.99",
            "elw_rght_form": "표준형",
            "elw_ko_barrier": "0.00",
            "apprch_rate": "0.00",
            "unas_shrn_iscd": "2001",
            "mtrt_date": "20240617",
            "prmm_val": "11.93",
            "stck_lp_fin_date": "20240613",
            "tick_conv_prc": "4.82",
            "prls_qryr_stpr_prc": "365.10",
            "lp_hvol": "10999000"
        },
        {
            "bond_shrn_iscd": "57JAEW",
            "hts_kor_isnm": "한국JAEWKOSPI200콜",
            "rght_type_name": "CALL",
            "elw_prpr": "2555",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "317.50",
            "stck_cnvr_rate": "100.000000",
            "stck_lstn_date": "20231018",
            "stck_last_tr_date": "20240613",
            "hts_rmnn_dynu": "1",
            "unas_isnm": "KOSPI200",
            "unas_prpr": "377.90",
            "unas_prdy_vrss": "6.78",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "1.83",
            "unas_acml_vol": "80478000",
            "moneyness": "19.024",
            "atm_cls_name": "ITM",
            "prit": "119.02",
            "delta_val": "0.959424",
            "hts_ints_vltl": "191.44",
            "tmvl_val": "-3506.00",
            "gear": "14.7900",
            "lvrg_val": "14.189881",
            "prls_qryr_rate": "-9.2100",
            "cfp": "-9.8800",
            "lstn_stcn": "9000000",
            "pblc_co_name": "한국투자증권(주)",
            "lp_mbcr_name": "한국증권",
            "lp_hldn_rate": "99.99",
            "elw_rght_form": "표준형",
            "elw_ko_barrier": "0.00",
            "apprch_rate": "0.00",
            "unas_shrn_iscd": "2001",
            "mtrt_date": "20240617",
            "prmm_val": "6.76",
            "stck_lp_fin_date": "20240613",
            "tick_conv_prc": "4.80",
            "prls_qryr_stpr_prc": "343.05",
            "lp_hvol": "8998900"
        },
        {
            "bond_shrn_iscd": "57JAEX",
            "hts_kor_isnm": "한국JAEXKOSPI200콜",
            "rght_type_name": "CALL",
            "elw_prpr": "4850",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "acpr": "315.00",
            "stck_cnvr_rate": "100.000000",
            "stck_lstn_date": "20231018",
            "stck_last_tr_date": "20240613",
            "hts_rmnn_dynu": "1",
            "unas_isnm": "KOSPI200",
            "unas_prpr": "377.90",
            "unas_prdy_vrss": "6.78",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "1.83",
            "unas_acml_vol": "80478000",
            "moneyness": "19.968",
            "atm_cls_name": "ITM",
            "prit": "119.96",
            "delta_val": "0.959709",
            "hts_ints_vltl": "200.01",
            "tmvl_val": "-1461.00",
            "gear": "7.7900",
            "lvrg_val": "7.476133",
            "prls_qryr_rate": "-3.8000",
            "cfp": "-4.3600",
            "lstn_stcn": "10000000",
            "pblc_co_name": "한국투자증권(주)",
            "lp_mbcr_name": "한국증권",
            "lp_hldn_rate": "99.99",
            "elw_rght_form": "표준형",
            "elw_ko_barrier": "0.00",
            "apprch_rate": "0.00",
            "unas_shrn_iscd": "2001",
            "mtrt_date": "20240617",
            "prmm_val": "12.83",
            "stck_lp_fin_date": "20240613",
            "tick_conv_prc": "4.80",
            "prls_qryr_stpr_prc": "363.50",
            "lp_hvol": "9999400"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 변동성 추이(분별)

- **API ID**: 국내주식-179
- **실전 TR_ID**: FHPEW02840300
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/volatility-trend-minute`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 변동성 추이(분별) API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0284] ELW 변동성 추이 화면의 "분별" 변동성 추이 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02840300 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | W(Unique key) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | ex) 58J297(KBJ297삼성전자콜) |
| 2 | `FID_HOUR_CLS_CODE` | 시간구분코드 | string | Y | 5 | '60(1분), 180(3분), 300(5분), 600(10분), 1800(30분), 3600(60분)<br>' |
| 3 | `FID_PW_DATA_INCU_YN` | 과거데이터 포함 여부 | string | Y | 2 | N(과거데이터포함X),Y(과거데이터포함O) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `stck_bsop_date` | 주식 영업 일자 | string | Y | 6 |  |
| 5 | `stck_cntg_hour` | 주식 체결 시간 | string | Y | 10 |  |
| 6 | `stck_prpr` | 주식 현재가 | string | Y | 10 |  |
| 7 | `elw_oprc` | ELW 시가2 | string | Y | 1 |  |
| 8 | `elw_hgpr` | ELW 최고가 | string | Y | 82 |  |
| 9 | `elw_lwpr` | ELW 최저가 | string | Y | 10 |  |
| 10 | `hts_ints_vltl` | HTS 내재 변동성 | string | Y | 10 |  |
| 11 | `hist_vltl` | 역사적 변동성 | string | Y | 18 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:57JS61
FID_HOUR_CLS_CODE:60
FID_PW_DATA_INCU_YN:N
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "stck_bsop_date": "20240422",
            "stck_cntg_hour": "142800",
            "stck_prpr": "265",
            "elw_oprc": "265",
            "elw_hgpr": "265",
            "elw_lwpr": "265",
            "hts_ints_vltl": "21.90",
            "hist_vltl": ""
        },
        {
            "stck_bsop_date": "20240422",
            "stck_cntg_hour": "142700",
            "stck_prpr": "265",
            "elw_oprc": "270",
            "elw_hgpr": "270",
            "elw_lwpr": "260",
            "hts_ints_vltl": "21.90",
            "hist_vltl": ""
        },
        {
            "stck_bsop_date": "20240422",
            "stck_cntg_hour": "142600",
            "stck_prpr": "275",
            "elw_oprc": "275",
            "elw_hgpr": "275",
            "elw_lwpr": "275",
            "hts_ints_vltl": "22.06",
            "hist_vltl": ""
        },
        {
            "stck_bsop_date": "20240422",
            "stck_cntg_hour": "142500",
            "stck_prpr": "270",
            "elw_oprc": "275",
            "elw_hgpr": "275",
            "elw_lwpr": "270",
            "hts_ints_vltl": "22.06",
            "hist_vltl": ""
        },
		...
        {
            "stck_bsop_date": "20240422",
            "stck_cntg_hour": "124900",
            "stck_prpr": "275",
            "elw_oprc": "280",
            "elw_hgpr": "280",
            "elw_lwpr": "275",
            "hts_ints_vltl": "22.24",
            "hist_vltl": ""
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 변동성추이(체결)

- **API ID**: 국내주식-177
- **실전 TR_ID**: FHPEW02840100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/volatility-trend-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 변동성 추이(체결) API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0284] ELW 변동성 추이 화면의 "시간별" 변동성 추이 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02840100 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | W(Unique key) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | ex) 58J297(KBJ297삼성전자콜) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (13)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  |  |
| 4 | `stck_cntg_hour` | 주식체결시간 | string | Y | 6 |  |
| 5 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 6 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 7 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 8 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 9 | `bidp` | 매수호가 | string | Y | 10 |  |
| 10 | `askp` | 매도호가 | string | Y | 10 |  |
| 11 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 12 | `hts_ints_vltl` | HTS내재변동성 | string | Y | 114 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:58J540
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "stck_cntg_hour": "150121",
            "elw_prpr": "45",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "52690",
            "hts_ints_vltl": "33.05"
        },
        {
            "stck_cntg_hour": "140354",
            "elw_prpr": "45",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "bidp": "45",
            "askp": "0",
            "acml_vol": "52680",
            "hts_ints_vltl": "31.96"
        },
        {
            "stck_cntg_hour": "140340",
            "elw_prpr": "45",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "bidp": "45",
            "askp": "0",
            "acml_vol": "47680",
            "hts_ints_vltl": "31.96"
        },
        {
            "stck_cntg_hour": "140334",
            "elw_prpr": "45",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "47670",
            "hts_ints_vltl": "31.96"
        },
        {
            "stck_cntg_hour": "140334",
            "elw_prpr": "45",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "42690",
            "hts_ints_vltl": "31.96"
        },
        {
            "stck_cntg_hour": "140334",
            "elw_prpr": "45",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "42680",
            "hts_ints_vltl": "31.96"
        },
        {
            "stck_cntg_hour": "140334",
            "elw_prpr": "45",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "37680",
            "hts_ints_vltl": "31.96"
        },
        {
            "stck_cntg_hour": "114800",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "50",
            "askp": "55",
            "acml_vol": "37670",
            "hts_ints_vltl": "33.49"
        },
        {
            "stck_cntg_hour": "114046",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "50",
            "askp": "55",
            "acml_vol": "32670",
            "hts_ints_vltl": "26.54"
        },
        {
            "stck_cntg_hour": "104344",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "50",
            "askp": "55",
            "acml_vol": "30170",
            "hts_ints_vltl": "32.33"
        },
        {
            "stck_cntg_hour": "104344",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "50",
            "askp": "55",
            "acml_vol": "27670",
            "hts_ints_vltl": "32.33"
        },
        {
            "stck_cntg_hour": "102100",
            "elw_prpr": "55",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "bidp": "50",
            "askp": "55",
            "acml_vol": "17750",
            "hts_ints_vltl": "31.27"
        },
        {
            "stck_cntg_hour": "095235",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "17730",
            "hts_ints_vltl": "27.36"
        },
        {
            "stck_cntg_hour": "095235",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "17720",
            "hts_ints_vltl": "27.36"
        },
        {
            "stck_cntg_hour": "095235",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "7810",
            "hts_ints_vltl": "27.36"
        },
        {
            "stck_cntg_hour": "091645",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "7720",
            "hts_ints_vltl": "25.08"
        },
        {
            "stck_cntg_hour": "091645",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "7630",
            "hts_ints_vltl": "25.08"
        },
        {
            "stck_cntg_hour": "091502",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "45",
            "askp": "50",
            "acml_vol": "7620",
            "hts_ints_vltl": "27.27"
        },
        {
            "stck_cntg_hour": "091222",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "50",
            "askp": "55",
            "acml_vol": "120",
            "hts_ints_vltl": "32.07"
        },
        {
            "stck_cntg_hour": "091222",
            "elw_prpr": "50",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-9.09",
            "bidp": "50",
            "askp": "55",
            "acml_vol": "110",
            "hts_ints_vltl": "32.07"
        },
        {
            "stck_cntg_hour": "090223",
            "elw_prpr": "55",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "bidp": "55",
            "askp": "0",
            "acml_vol": "100",
            "hts_ints_vltl": "22.69"
        },
        {
            "stck_cntg_hour": "090223",
            "elw_prpr": "55",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "bidp": "50",
            "askp": "55",
            "acml_vol": "10",
            "hts_ints_vltl": "22.69"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 당일급변종목

- **API ID**: 국내주식-171
- **실전 TR_ID**: FHPEW02870000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/ranking/quick-change`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 당일급변종목 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0287] ELW 당일급변종목 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02870000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (14)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | Unique key(20287) |
| 2 | `FID_UNAS_INPUT_ISCD` | 기초자산입력종목코드 | string | Y | 12 | '000000(전체), 2001(코스피200)<br>, 3003(코스닥150), 005930(삼성전자) ' |
| 3 | `FID_INPUT_ISCD` | 발행사 | string | Y | 12 | '00000(전체), 00003(한국투자증권)<br>, 00017(KB증권), 00005(미래에셋주식회사)' |
| 4 | `FID_MRKT_CLS_CODE` | 시장구분코드 | string | Y | 2 | Unique key(A) |
| 5 | `FID_INPUT_PRICE_1` | 가격(이상) | string | Y | 12 |  |
| 6 | `FID_INPUT_PRICE_2` | 가격(이하) | string | Y | 12 |  |
| 7 | `FID_INPUT_VOL_1` | 거래량(이상) | string | Y | 18 |  |
| 8 | `FID_INPUT_VOL_2` | 거래량(이하) | string | Y | 18 |  |
| 9 | `FID_HOUR_CLS_CODE` | 시간구분코드 | string | Y | 5 | 1(분), 2(일) |
| 10 | `FID_INPUT_HOUR_1` | 입력 일 또는 분 | string | Y | 10 |  |
| 11 | `FID_INPUT_HOUR_2` | 기준시간(분 선택 시) | string | Y | 10 |  |
| 12 | `FID_RANK_SORT_CLS_CODE` | 순위정렬구분코드 | string | Y | 2 | '1(가격급등), 2(가격급락), 3(거래량급증)<br>, 4(매수잔량급증), 5(매도잔량급증)' |
| 13 | `FID_BLNG_CLS_CODE` | 결재방법 | string | Y | 2 | 0(전체), 1(일반), 2(조기종료) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (18)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 5 | `elw_kor_isnm` | ELW한글종목명 | string | Y | 40 |  |
| 6 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 7 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 8 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 9 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 10 | `askp` | 매도호가 | string | Y | 10 |  |
| 11 | `bidp` | 매수호가 | string | Y | 10 |  |
| 12 | `total_askp_rsqn` | 총매도호가잔량 | string | Y | 12 |  |
| 13 | `total_bidp_rsqn` | 총매수호가잔량 | string | Y | 12 |  |
| 14 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 15 | `stnd_val` | 기준값 | string | Y | 10 |  |
| 16 | `stnd_val_vrss` | 기준값대비 | string | Y | 11 |  |
| 17 | `stnd_val_ctrt` | 기준값대비율 | string | Y | 162 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:20287
FID_UNAS_INPUT_ISCD:000000
FID_INPUT_ISCD:00000
FID_MRKT_CLS_CODE:A
FID_INPUT_PRICE_1:
FID_INPUT_PRICE_2:
FID_INPUT_VOL_1:
FID_INPUT_VOL_2:
FID_HOUR_CLS_CODE:2
FID_INPUT_HOUR_1:1
FID_INPUT_HOUR_2:
FID_RANK_SORT_CLS_CODE:1
FID_BLNG_CLS_CODE:0
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "elw_shrn_iscd": "57JAKW",
            "elw_kor_isnm": "한국JAKWLS일렉콜",
            "elw_prpr": "460",
            "prdy_vrss_sign": "2",
            "prdy_vrss": "350",
            "prdy_ctrt": "318.18",
            "askp": "0",
            "bidp": "145",
            "total_askp_rsqn": "0",
            "total_bidp_rsqn": "49060",
            "acml_vol": "3320",
            "stnd_val": "110",
            "stnd_val_vrss": "350",
            "stnd_val_ctrt": "318.18"
        },
        {
            "elw_shrn_iscd": "58JF27",
            "elw_kor_isnm": "KBJF27KOSPI200콜",
            "elw_prpr": "2395",
            "prdy_vrss_sign": "2",
            "prdy_vrss": "1745",
            "prdy_ctrt": "268.46",
            "askp": "0",
            "bidp": "15",
            "total_askp_rsqn": "0",
            "total_bidp_rsqn": "29000",
            "acml_vol": "100",
            "stnd_val": "650",
            "stnd_val_vrss": "1745",
            "stnd_val_ctrt": "268.46"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 투자지표추이(분별)

- **API ID**: 국내주식-174
- **실전 TR_ID**: FHPEW02740300
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/indicator-trend-minute`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 투자지표추이(분별) API입니다.
한국투자 HTS(eFriend Plus) &gt; [0274] ELW 투자지표추이 화면 데이터의 "분별 비교추이" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02740300 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | ex) 58J297(KBJ297삼성전자콜) |
| 2 | `FID_HOUR_CLS_CODE` | 시간구분코드 | string | Y | 5 | '60(1분), 180(3분), 300(5분), 600(10분), 1800(30분), 3600(60분), 7200(60분)<br>' |
| 3 | `FID_PW_DATA_INCU_YN` | 과거데이터 포함 여부 | string | Y | 2 | N(과거데이터포함X),Y(과거데이터포함O) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (17)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `stck_bsop_date` | 주식영업일자 | string | Y | 8 |  |
| 5 | `stck_cntg_hour` | 주식체결시간 | string | Y | 6 |  |
| 6 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 7 | `elw_oprc` | ELW시가2 | string | Y | 10 |  |
| 8 | `elw_hgpr` | ELW최고가 | string | Y | 10 |  |
| 9 | `elw_lwpr` | ELW최저가 | string | Y | 10 |  |
| 10 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |
| 11 | `gear` | 기어링 | string | Y | 84 |  |
| 12 | `prmm_val` | 프리미엄값 | string | Y | 114 |  |
| 13 | `invl_val` | 내재가치값 | string | Y | 132 |  |
| 14 | `prit` | 패리티 | string | Y | 112 |  |
| 15 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 16 | `cntg_vol` | 체결거래량 | string | Y | 18 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:57K281
FID_HOUR_CLS_CODE:60
FID_PW_DATA_INCU_YN:Y
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131900",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "-10.8818",
            "gear": "19.5700",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "102.17",
            "acml_vol": "827720",
            "cntg_vol": "55700"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131800",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131700",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131600",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131500",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131400",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131300",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131200",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131100",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "131000",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "130900",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "130800",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "130700",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "130600",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "130500",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "130400",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        },...
        {
            "stck_bsop_date": "20240503",
            "stck_cntg_hour": "114000",
            "elw_prpr": "40",
            "elw_oprc": "40",
            "elw_hgpr": "40",
            "elw_lwpr": "40",
            "lvrg_val": "19.5700",
            "gear": "33.5300",
            "prmm_val": "5.1086",
            "invl_val": "17.00",
            "prit": "-10.72",
            "acml_vol": "772020",
            "cntg_vol": "0"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 기초자산 목록조회

- **API ID**: 국내주식-185
- **실전 TR_ID**: FHKEW154100C0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/udrl-asset-list`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 기초자산 목록조회 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0288] ELW 기초자산별 ELW 시세 화면 의 "왼쪽 기초자산 목록" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKEW154100C0 |
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
| 0 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | 11541(Primary key) |
| 1 | `FID_RANK_SORT_CLS_CODE` | 순위정렬구분코드 | string | Y | 2 | 0(종목명순), 1(콜발행종목순), 2(풋발행종목순), 3(전일대비 상승율순), 4(전일대비 하락율순), 5(현재가 크기순), 6(종목코드순) |
| 2 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | 00000(전체), 00003(한국투자증권), 00017(KB증권), 00005(미래에셋) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (10)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `unas_shrn_iscd` | 기초자산단축종목코드 | string | Y | 9 |  |
| 5 | `unas_isnm` | 기초자산종목명 | string | Y | 40 |  |
| 6 | `unas_prpr` | 기초자산현재가 | string | Y | 112 |  |
| 7 | `unas_prdy_vrss` | 기초자산전일대비 | string | Y | 112 |  |
| 8 | `unas_prdy_vrss_sign` | 기초자산전일대비부호 | string | Y | 1 |  |
| 9 | `unas_prdy_ctrt` | 기초자산전일대비율 | string | Y | 82 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_SCR_DIV_CODE:11541
FID_RANK_SORT_CLS_CODE:0
FID_INPUT_ISCD:00000
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "unas_shrn_iscd": "2001",
            "unas_isnm": "KOSPI200",
            "unas_prpr": "371.33",
            "unas_prdy_vrss": "0.17",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "0.05"
        },
        {
            "unas_shrn_iscd": "000990",
            "unas_isnm": "DB하이텍",
            "unas_prpr": "40850.00",
            "unas_prdy_vrss": "-300.00",
            "unas_prdy_vrss_sign": "5",
            "unas_prdy_ctrt": "-0.73"
        },
        {
            "unas_shrn_iscd": "009540",
            "unas_isnm": "HD한국조선해양",
            "unas_prpr": "135400.00",
            "unas_prdy_vrss": "1100.00",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "0.82"
        },
        {
            "unas_shrn_iscd": "267260",
            "unas_isnm": "HD현대일렉트릭",
            "unas_prpr": "302500.00",
            "unas_prdy_vrss": "9000.00",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "3.07"
        },
        {
            "unas_shrn_iscd": "028300",
            "unas_isnm": "HLB",
            "unas_prpr": "64700.00",
            "unas_prdy_vrss": "8500.00",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "15.12"
        },
        {
            "unas_shrn_iscd": "011200",
            "unas_isnm": "HMM",
            "unas_prpr": "18010.00",
            "unas_prdy_vrss": "460.00",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "2.62"
        },
        {
            "unas_shrn_iscd": "403870",
            "unas_isnm": "HPSP",
            "unas_prpr": "45200.00",
            "unas_prdy_vrss": "2900.00",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "6.86"
        },
        {
            "unas_shrn_iscd": "035900",
            "unas_isnm": "JYP Ent.",
            "unas_prpr": "58800.00",
            "unas_prdy_vrss": "-1700.00",
            "unas_prdy_vrss_sign": "5",
            "unas_prdy_ctrt": "-2.81"
        },
        {
            "unas_shrn_iscd": "105560",
            "unas_isnm": "KB금융",
            "unas_prpr": "77100.00",
            "unas_prdy_vrss": "800.00",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "1.05"
        },
        {
            "unas_shrn_iscd": "3003",
            "unas_isnm": "KSQ150",
            "unas_prpr": "1355.15",
            "unas_prdy_vrss": "0.44",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "0.03"
        },
        {
            "unas_shrn_iscd": "030200",
            "unas_isnm": "KT",
            "unas_prpr": "36150.00",
            "unas_prdy_vrss": "-450.00",
            "unas_prdy_vrss_sign": "5",
            "unas_prdy_ctrt": "-1.23"
        },
        {
            "unas_shrn_iscd": "033780",
            "unas_isnm": "KT&G",
            "unas_prpr": "86100.00",
            "unas_prdy_vrss": "-100.00",
            "unas_prdy_vrss_sign": "5",
            "unas_prdy_ctrt": "-0.12"
        },
        {
            "unas_shrn_iscd": "003550",
            "unas_isnm": "LG",
            "unas_prpr": "81400.00",
            "unas_prdy_vrss": "1500.00",
            "unas_prdy_vrss_sign": "2",
            "unas_prdy_ctrt": "1.88"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 변동성 추이(일별)

- **API ID**: 국내주식-178
- **실전 TR_ID**: FHPEW02840200
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/volatility-trend-daily`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 변동성 추이(일별) API입니다.
한국투자 HTS(eFriend Plus) &gt; [0284] ELW 변동성 추이 화면의 "일별" 변동성 추이 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02840200 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | ex) 58J297(KBJ297삼성전자콜) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (19)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `stck_bsop_date` | 주식 영업 일자 | string | Y | 8 |  |
| 5 | `elw_prpr` | ELW 현재가 | string | Y | 10 |  |
| 6 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 7 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 8 | `prdy_ctrt` | 전일대비율 | string | Y | 8 |  |
| 9 | `elw_oprc` | elw 시가2 | string | Y | 10 |  |
| 10 | `elw_hgpr` | elw 최고가 | string | Y | 10 |  |
| 11 | `elw_lwpr` | elw 최저가 | string | Y | 10 |  |
| 12 | `acml_vol` | 누적 거래량 | string | Y | 18 |  |
| 13 | `d10_hist_vltl` | 10일 역사적 변동성 | string | Y | 11 |  |
| 14 | `d20_hist_vltl` | 20일 역사적 변동성 | string | Y | 11 |  |
| 15 | `d30_hist_vltl` | 30일 역사적 변동성 | string | Y | 11 |  |
| 16 | `d60_hist_vltl` | 60일 역사적 변동성 | string | Y | 11 |  |
| 17 | `d90_hist_vltl` | 90일 역사적 변동성 | string | Y | 11 |  |
| 18 | `hts_ints_vltl` | HTS 내재 변동성 | string | Y | 11 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:57JS61
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "stck_bsop_date": "20240503",
            "elw_prpr": "5",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "elw_oprc": "5",
            "elw_hgpr": "5",
            "elw_lwpr": "5",
            "acml_vol": "76410",
            "d10_hist_vltl": "21.05",
            "d20_hist_vltl": "20.32",
            "d30_hist_vltl": "19.58",
            "d60_hist_vltl": "17.91",
            "d90_hist_vltl": "18.33",
            "hts_ints_vltl": "23.37"
        },
        {
            "stck_bsop_date": "20240502",
            "elw_prpr": "5",
            "prdy_vrss": "-15",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-75.00",
            "elw_oprc": "20",
            "elw_hgpr": "20",
            "elw_lwpr": "5",
            "acml_vol": "6509850",
            "d10_hist_vltl": "23.00",
            "d20_hist_vltl": "21.31",
            "d30_hist_vltl": "20.17",
            "d60_hist_vltl": "19.07",
            "d90_hist_vltl": "18.33",
            "hts_ints_vltl": "20.16"
        },
        {
            "stck_bsop_date": "20240430",
            "elw_prpr": "20",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-20.00",
            "elw_oprc": "25",
            "elw_hgpr": "25",
            "elw_lwpr": "15",
            "acml_vol": "1839420",
            "d10_hist_vltl": "23.69",
            "d20_hist_vltl": "21.39",
            "d30_hist_vltl": "20.42",
            "d60_hist_vltl": "19.43",
            "d90_hist_vltl": "18.33",
            "hts_ints_vltl": "23.45"
        },
        {
            "stck_bsop_date": "20240429",
            "elw_prpr": "25",
            "prdy_vrss": "-40",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-61.54",
            "elw_oprc": "35",
            "elw_hgpr": "40",
            "elw_lwpr": "25",
            "acml_vol": "3301030",
            "d10_hist_vltl": "26.85",
            "d20_hist_vltl": "21.38",
            "d30_hist_vltl": "20.48",
            "d60_hist_vltl": "19.44",
            "d90_hist_vltl": "18.37",
            "hts_ints_vltl": "21.85"
        },
        {
            "stck_bsop_date": "20240426",
            "elw_prpr": "65",
            "prdy_vrss": "-70",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-51.85",
            "elw_oprc": "65",
            "elw_hgpr": "95",
            "elw_lwpr": "50",
            "acml_vol": "11476800",
            "d10_hist_vltl": "26.51",
            "d20_hist_vltl": "21.14",
            "d30_hist_vltl": "21.13",
            "d60_hist_vltl": "19.34",
            "d90_hist_vltl": "18.45",
            "hts_ints_vltl": "22.04"
        },
        {
            "stck_bsop_date": "20240425",
            "elw_prpr": "135",
            "prdy_vrss": "80",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "145.45",
            "elw_oprc": "100",
            "elw_hgpr": "135",
            "elw_lwpr": "85",
            "acml_vol": "16588080",
            "d10_hist_vltl": "26.14",
            "d20_hist_vltl": "20.66",
            "d30_hist_vltl": "21.01",
            "d60_hist_vltl": "19.30",
            "d90_hist_vltl": "18.39",
            "hts_ints_vltl": "21.20"
        },
        {
            "stck_bsop_date": "20240424",
            "elw_prpr": "55",
            "prdy_vrss": "-115",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-67.65",
            "elw_oprc": "75",
            "elw_hgpr": "75",
            "elw_lwpr": "50",
            "acml_vol": "8909400",
            "d10_hist_vltl": "23.99",
            "d20_hist_vltl": "19.38",
            "d30_hist_vltl": "20.25",
            "d60_hist_vltl": "18.86",
            "d90_hist_vltl": "18.11",
            "hts_ints_vltl": "20.73"
        },
        {
            "stck_bsop_date": "20240423",
            "elw_prpr": "170",
            "prdy_vrss": "-20",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-10.53",
            "elw_oprc": "180",
            "elw_hgpr": "200",
            "elw_lwpr": "145",
            "acml_vol": "44577440",
            "d10_hist_vltl": "21.44",
            "d20_hist_vltl": "18.18",
            "d30_hist_vltl": "19.40",
            "d60_hist_vltl": "18.35",
            "d90_hist_vltl": "17.77",
            "hts_ints_vltl": "20.33"
        },
        {
            "stck_bsop_date": "20240422",
            "elw_prpr": "190",
            "prdy_vrss": "-210",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-52.50",
            "elw_oprc": "265",
            "elw_hgpr": "305",
            "elw_lwpr": "190",
            "acml_vol": "79163330",
            "d10_hist_vltl": "21.44",
            "d20_hist_vltl": "18.25",
            "d30_hist_vltl": "19.58",
            "d60_hist_vltl": "18.37",
            "d90_hist_vltl": "17.88",
            "hts_ints_vltl": "21.25"
        },
        {
            "stck_bsop_date": "20240419",
            "elw_prpr": "400",
            "prdy_vrss": "215",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "116.22",
            "elw_oprc": "290",
            "elw_hgpr": "725",
            "elw_lwpr": "285",
            "acml_vol": "63410060",
            "d10_hist_vltl": "21.22",
            "d20_hist_vltl": "17.73",
            "d30_hist_vltl": "19.66",
            "d60_hist_vltl": "18.26",
            "d90_hist_vltl": "17.76",
            "hts_ints_vltl": "24.18"
        },
        {
            "stck_bsop_date": "20240418",
            "elw_prpr": "185",
            "prdy_vrss": "-165",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-47.14",
            "elw_oprc": "295",
            "elw_hgpr": "325",
            "elw_lwpr": "180",
            "acml_vol": "35347180",
            "d10_hist_vltl": "20.69",
            "d20_hist_vltl": "19.36",
            "d30_hist_vltl": "18.92",
            "d60_hist_vltl": "17.87",
            "d90_hist_vltl": "17.50",
            "hts_ints_vltl": "21.30"
        },
        {
            "stck_bsop_date": "20240417",
            "elw_prpr": "350",
            "prdy_vrss": "80",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "29.63",
            "elw_oprc": "235",
            "elw_hgpr": "350",
            "elw_lwpr": "215",
            "acml_vol": "68687230",
            "d10_hist_vltl": "20.70",
            "d20_hist_vltl": "19.25",
            "d30_hist_vltl": "18.23",
            "d60_hist_vltl": "17.87",
            "d90_hist_vltl": "17.33",
            "hts_ints_vltl": "21.02"
        },
        {
            "stck_bsop_date": "20240416",
            "elw_prpr": "270",
            "prdy_vrss": "170",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "170.00",
            "elw_oprc": "180",
            "elw_hgpr": "320",
            "elw_lwpr": "165",
            "acml_vol": "45554270",
            "d10_hist_vltl": "20.10",
            "d20_hist_vltl": "19.26",
            "d30_hist_vltl": "18.17",
            "d60_hist_vltl": "17.74",
            "d90_hist_vltl": "17.24",
            "hts_ints_vltl": "21.23"
        },
        {
            "stck_bsop_date": "20240415",
            "elw_prpr": "100",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "elw_oprc": "140",
            "elw_hgpr": "195",
            "elw_lwpr": "100",
            "acml_vol": "16103560",
            "d10_hist_vltl": "15.63",
            "d20_hist_vltl": "17.28",
            "d30_hist_vltl": "17.35",
            "d60_hist_vltl": "17.87",
            "d90_hist_vltl": "16.86",
            "hts_ints_vltl": "19.64"
        },
        {
            "stck_bsop_date": "20240412",
            "elw_prpr": "100",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-4.76",
            "elw_oprc": "85",
            "elw_hgpr": "120",
            "elw_lwpr": "80",
            "acml_vol": "5222010",
            "d10_hist_vltl": "15.51",
            "d20_hist_vltl": "18.67",
            "d30_hist_vltl": "17.31",
            "d60_hist_vltl": "18.05",
            "d90_hist_vltl": "16.86",
            "hts_ints_vltl": "20.27"
        },
        {
            "stck_bsop_date": "20240411",
            "elw_prpr": "105",
            "prdy_vrss": "5",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "5.00",
            "elw_oprc": "125",
            "elw_hgpr": "160",
            "elw_lwpr": "90",
            "acml_vol": "2031830",
            "d10_hist_vltl": "14.74",
            "d20_hist_vltl": "18.70",
            "d30_hist_vltl": "17.41",
            "d60_hist_vltl": "17.96",
            "d90_hist_vltl": "16.79",
            "hts_ints_vltl": "22.02"
        },
        {
            "stck_bsop_date": "20240409",
            "elw_prpr": "100",
            "prdy_vrss": "10",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "11.11",
            "elw_oprc": "65",
            "elw_hgpr": "100",
            "elw_lwpr": "60",
            "acml_vol": "999560",
            "d10_hist_vltl": "14.75",
            "d20_hist_vltl": "18.80",
            "d30_hist_vltl": "17.56",
            "d60_hist_vltl": "18.00",
            "d90_hist_vltl": "16.90",
            "hts_ints_vltl": "20.93"
        },
        {
            "stck_bsop_date": "20240408",
            "elw_prpr": "90",
            "prdy_vrss": "-20",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "elw_oprc": "95",
            "elw_hgpr": "95",
            "elw_lwpr": "75",
            "acml_vol": "159080",
            "d10_hist_vltl": "15.41",
            "d20_hist_vltl": "18.88",
            "d30_hist_vltl": "17.65",
            "d60_hist_vltl": "17.96",
            "d90_hist_vltl": "16.87",
            "hts_ints_vltl": "21.04"
        },
        {
            "stck_bsop_date": "20240405",
            "elw_prpr": "110",
            "prdy_vrss": "40",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "57.14",
            "elw_oprc": "95",
            "elw_hgpr": "115",
            "elw_lwpr": "80",
            "acml_vol": "562130",
            "d10_hist_vltl": "15.60",
            "d20_hist_vltl": "19.16",
            "d30_hist_vltl": "17.65",
            "d60_hist_vltl": "18.05",
            "d90_hist_vltl": "16.93",
            "hts_ints_vltl": "21.19"
        },
        {
            "stck_bsop_date": "20240404",
            "elw_prpr": "70",
            "prdy_vrss": "-30",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-30.00",
            "elw_oprc": "70",
            "elw_hgpr": "70",
            "elw_lwpr": "60",
            "acml_vol": "1086750",
            "d10_hist_vltl": "14.58",
            "d20_hist_vltl": "19.40",
            "d30_hist_vltl": "17.41",
            "d60_hist_vltl": "17.94",
            "d90_hist_vltl": "16.83",
            "hts_ints_vltl": "20.35"
        },
        {
            "stck_bsop_date": "20240403",
            "elw_prpr": "100",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "elw_oprc": "75",
            "elw_hgpr": "100",
            "elw_lwpr": "75",
            "acml_vol": "305570",
            "d10_hist_vltl": "19.05",
            "d20_hist_vltl": "18.53",
            "d30_hist_vltl": "16.79",
            "d60_hist_vltl": "17.67",
            "d90_hist_vltl": "16.62",
            "hts_ints_vltl": "18.85"
        },
        {
            "stck_bsop_date": "20240402",
            "elw_prpr": "100",
            "prdy_vrss": "30",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "42.86",
            "elw_oprc": "65",
            "elw_hgpr": "100",
            "elw_lwpr": "55",
            "acml_vol": "1056250",
            "d10_hist_vltl": "18.75",
            "d20_hist_vltl": "17.42",
            "d30_hist_vltl": "16.29",
            "d60_hist_vltl": "17.29",
            "d90_hist_vltl": "16.39",
            "hts_ints_vltl": "21.66"
        },
        {
            "stck_bsop_date": "20240401",
            "elw_prpr": "70",
            "prdy_vrss": "-15",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-17.65",
            "elw_oprc": "60",
            "elw_hgpr": "120",
            "elw_lwpr": "60",
            "acml_vol": "839440",
            "d10_hist_vltl": "19.44",
            "d20_hist_vltl": "17.67",
            "d30_hist_vltl": "16.80",
            "d60_hist_vltl": "17.35",
            "d90_hist_vltl": "16.40",
            "hts_ints_vltl": "18.57"
        },...
        {
            "stck_bsop_date": "20231206",
            "elw_prpr": "1775",
            "prdy_vrss": "65",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "3.80",
            "elw_oprc": "1775",
            "elw_hgpr": "1775",
            "elw_lwpr": "1775",
            "acml_vol": "20",
            "d10_hist_vltl": "11.54",
            "d20_hist_vltl": "12.91",
            "d30_hist_vltl": "22.19",
            "d60_hist_vltl": "19.42",
            "d90_hist_vltl": "0.00",
            "hts_ints_vltl": "10.60"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 거래량순위

- **API ID**: 국내주식-168
- **실전 TR_ID**: FHPEW02780000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/ranking/volume-rank`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 거래량순위 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0278] ELW 거래량순위 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02780000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (15)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | W |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | 20278 |
| 2 | `FID_UNAS_INPUT_ISCD` | 기초자산입력종목코드 | string | Y | 12 | 000000 |
| 3 | `FID_INPUT_ISCD` | 발행사 | string | Y | 12 | 00000(전체), 00003(한국투자증권)<br>, 00017(KB증권), 00005(미래에셋주식회사)' |
| 4 | `FID_INPUT_RMNN_DYNU_1` | 입력잔존일수 | string | Y | 5 |  |
| 5 | `FID_DIV_CLS_CODE` | 콜풋구분코드 | string | Y | 2 | 0(전체), 1(콜), 2(풋) |
| 6 | `FID_INPUT_PRICE_1` | 가격(이상) | string | Y | 12 | 거래가격1(이상) |
| 7 | `FID_INPUT_PRICE_2` | 가격(이하) | string | Y | 12 | 거래가격1(이하) |
| 8 | `FID_INPUT_VOL_1` | 거래량(이상) | string | Y | 18 | 거래량1(이상) |
| 9 | `FID_INPUT_VOL_2` | 거래량(이하) | string | Y | 18 | 거래량1(이하) |
| 10 | `FID_INPUT_DATE_1` | 조회기준일 | string | Y | 10 | 입력날짜(기준가 조회기준) |
| 11 | `FID_RANK_SORT_CLS_CODE` | 순위정렬구분코드 | string | Y | 2 | 0: 거래량순 1: 평균거래증가율 2: 평균거래회전율 3:거래금액순 4: 순매수잔량순 5: 순매도잔량순 |
| 12 | `FID_BLNG_CLS_CODE` | 소속구분코드 | string | Y | 2 | 0: 전체 |
| 13 | `FID_INPUT_ISCD_2` | LP발행사 | string | Y | 8 | 0000 |
| 14 | `FID_INPUT_DATE_2` | 만기일-최종거래일조회 | string | Y | 10 | 공백 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (46)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `elw_kor_isnm` | ELW한글종목명 | string | Y | 40 |  |
| 5 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 6 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 7 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 8 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 9 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 10 | `lstn_stcn` | 상장주수 | string | Y | 18 |  |
| 11 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 12 | `n_prdy_vol` | N전일거래량 | string | Y | 18 |  |
| 13 | `n_prdy_vol_vrss` | N전일거래량대비 | string | Y | 18 |  |
| 14 | `vol_inrt` | 거래량증가율 | string | Y | 84 |  |
| 15 | `vol_tnrt` | 거래량회전율 | string | Y | 82 |  |
| 16 | `nday_vol_tnrt` | N일거래량회전율 | string | Y | 8 |  |
| 17 | `acml_tr_pbmn` | 누적거래대금 | string | Y | 18 |  |
| 18 | `n_prdy_tr_pbmn` | N전일거래대금 | string | Y | 18 |  |
| 19 | `n_prdy_tr_pbmn_vrss` | N전일거래대금대비 | string | Y | 18 |  |
| 20 | `total_askp_rsqn` | 총매도호가잔량 | string | Y | 12 |  |
| 21 | `total_bidp_rsqn` | 총매수호가잔량 | string | Y | 12 |  |
| 22 | `ntsl_rsqn` | 순매도잔량 | string | Y | 13 |  |
| 23 | `ntby_rsqn` | 순매수잔량 | string | Y | 12 |  |
| 24 | `seln_rsqn_rate` | 매도잔량비율 | string | Y | 84 |  |
| 25 | `shnu_rsqn_rate` | 매수2잔량비율 | string | Y | 84 |  |
| 26 | `stck_cnvr_rate` | 주식전환비율 | string | Y | 136 |  |
| 27 | `hts_rmnn_dynu` | HTS잔존일수 | string | Y | 5 |  |
| 28 | `invl_val` | 내재가치값 | string | Y | 132 |  |
| 29 | `tmvl_val` | 시간가치값 | string | Y | 132 |  |
| 30 | `acpr` | 행사가 | string | Y | 112 |  |
| 31 | `lp_mbcr_name` | LP회원사명 | string | Y | 50 |  |
| 32 | `unas_isnm` | 기초자산명 | string | Y | 40 |  |
| 33 | `stck_last_tr_date` | 최종거래일 | string | Y | 8 |  |
| 34 | `unas_shrn_iscd` | 기초자산코드 | string | Y | 12 |  |
| 35 | `prdy_vol` | 전일거래량 | string | Y | 18 |  |
| 36 | `lp_hldn_rate` | LP보유비율 | string | Y | 84 |  |
| 37 | `prit` | 패리티 | string | Y | 112 |  |
| 38 | `prls_qryr_stpr_prc` | 손익분기주가가격 | string | Y | 112 |  |
| 39 | `delta_val` | 델타값 | string | Y | 114 |  |
| 40 | `theta` | 세타 | string | Y | 84 |  |
| 41 | `prls_qryr_rate` | 손익분기비율 | string | Y | 84 |  |
| 42 | `stck_lstn_date` | 주식상장일자 | string | Y | 8 |  |
| 43 | `hts_ints_vltl` | HTS내재변동성 | string | Y | 114 |  |
| 44 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |
| 45 | `lp_ntby_qty` | LP순매도량 | string | Y | 18 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:20278
FID_UNAS_INPUT_ISCD:000000
FID_INPUT_ISCD:00000
FID_INPUT_RMNN_DYNU_1:0
FID_DIV_CLS_CODE:0
FID_INPUT_PRICE_1:
FID_INPUT_PRICE_2:
FID_INPUT_VOL_1:
FID_INPUT_VOL_2:
FID_INPUT_DATE_1:
FID_RANK_SORT_CLS_CODE:0
FID_BLNG_CLS_CODE:0
FID_INPUT_ISCD_2:0000
FID_INPUT_DATE_2:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "elw_kor_isnm": "한국JS54KOSPI200콜",
            "elw_shrn_iscd": "57JS54",
            "elw_prpr": "135",
            "prdy_vrss": "-100",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-42.55",
            "lstn_stcn": "10000000",
            "acml_vol": "44020240",
            "n_prdy_vol": "0",
            "n_prdy_vol_vrss": "44020240",
            "vol_inrt": "0.00",
            "vol_tnrt": "440.20",
            "nday_vol_tnrt": "440.20",
            "acml_tr_pbmn": "7881452400",
            "n_prdy_tr_pbmn": "7881452400",
            "n_prdy_tr_pbmn_vrss": "0",
            "total_askp_rsqn": "1512690",
            "total_bidp_rsqn": "337490",
            "ntsl_rsqn": "-1175200",
            "ntby_rsqn": "-1175200",
            "seln_rsqn_rate": "81.76",
            "shnu_rsqn_rate": "18.24",
            "stck_cnvr_rate": "100.000000",
            "hts_rmnn_dynu": "28",
            "invl_val": "0.00",
            "tmvl_val": "135.00",
            "acpr": "385.00",
            "lp_mbcr_name": "한국증권",
            "unas_isnm": "KOSPI200",
            "stck_last_tr_date": "20240509",
            "unas_shrn_iscd": "2001",
            "prdy_vol": "9013220",
            "lp_hldn_rate": "11.21",
            "prit": "95.38",
            "prls_qryr_stpr_prc": "386.35",
            "delta_val": "0.160726",
            "theta": "12.4577",
            "prls_qryr_rate": "5.2000",
            "stck_lstn_date": "20230817",
            "hts_ints_vltl": "16.98",
            "lvrg_val": "43.722294",
            "lp_ntby_qty": "5919560"
        },
        {
            "elw_kor_isnm": "한국JS57KOSPI200풋",
            "elw_shrn_iscd": "57JS57",
            "elw_prpr": "250",
            "prdy_vrss": "15",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "6.38",
            "lstn_stcn": "10000000",
            "acml_vol": "41360790",
            "n_prdy_vol": "0",
            "n_prdy_vol_vrss": "41360790",
            "vol_inrt": "0.00",
            "vol_tnrt": "413.61",
            "nday_vol_tnrt": "413.61",
            "acml_tr_pbmn": "9642006500",
            "n_prdy_tr_pbmn": "9642006500",
            "n_prdy_tr_pbmn_vrss": "0",
            "total_askp_rsqn": "591950",
            "total_bidp_rsqn": "320140",
            "ntsl_rsqn": "-271810",
            "ntby_rsqn": "-271810",
            "seln_rsqn_rate": "64.90",
            "shnu_rsqn_rate": "35.10",
            "stck_cnvr_rate": "100.000000",
            "hts_rmnn_dynu": "28",
            "invl_val": "0.00",
            "tmvl_val": "250.00",
            "acpr": "355.00",
            "lp_mbcr_name": "한국증권",
            "unas_isnm": "KOSPI200",
            "stck_last_tr_date": "20240509",
            "unas_shrn_iscd": "2001",
            "prdy_vol": "3829210",
            "lp_hldn_rate": "38.24",
            "prit": "96.66",
            "prls_qryr_stpr_prc": "352.50",
            "delta_val": "-0.227848",
            "theta": "15.2298",
            "prls_qryr_rate": "-4.0100",
            "stck_lstn_date": "20230817",
            "hts_ints_vltl": "19.27",
            "lvrg_val": "-33.470867",
            "lp_ntby_qty": "3929370"
        },
        {
            "elw_kor_isnm": "한국JS59KOSPI200풋",
            "elw_shrn_iscd": "57JS59",
            "elw_prpr": "165",
            "prdy_vrss": "5",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "3.12",
            "lstn_stcn": "11000000",
            "acml_vol": "34510630",
            "n_prdy_vol": "0",
            "n_prdy_vol_vrss": "34510630",
            "vol_inrt": "0.00",
            "vol_tnrt": "313.73",
            "nday_vol_tnrt": "313.73",
            "acml_tr_pbmn": "5293873100",
            "n_prdy_tr_pbmn": "5293873100",
            "n_prdy_tr_pbmn_vrss": "0",
            "total_askp_rsqn": "348740",
            "total_bidp_rsqn": "639850",
            "ntsl_rsqn": "291110",
            "ntby_rsqn": "291110",
            "seln_rsqn_rate": "35.28",
            "shnu_rsqn_rate": "64.72",
            "stck_cnvr_rate": "100.000000",
            "hts_rmnn_dynu": "28",
            "invl_val": "0.00",
            "tmvl_val": "165.00",
            "acpr": "350.00",
            "lp_mbcr_name": "한국증권",
            "unas_isnm": "KOSPI200",
            "stck_last_tr_date": "20240509",
            "unas_shrn_iscd": "2001",
            "prdy_vol": "7133790",
            "lp_hldn_rate": "37.29",
            "prit": "95.30",
            "prls_qryr_stpr_prc": "348.35",
            "delta_val": "-0.160062",
            "theta": "12.8688",
            "prls_qryr_rate": "-5.1400",
            "stck_lstn_date": "20230817",
            "hts_ints_vltl": "19.97",
            "lvrg_val": "-35.625000",
            "lp_ntby_qty": "3185360"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 지표순위

- **API ID**: 국내주식-169
- **실전 TR_ID**: FHPEW02790000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/ranking/indicator`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 지표순위 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0279] ELW 지표순위 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02790000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (11)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | Unique key(20279) |
| 2 | `FID_UNAS_INPUT_ISCD` | 기초자산입력종목코드 | string | Y | 12 | '000000(전체), 2001(코스피200)<br>, 3003(코스닥150), 005930(삼성전자) ' |
| 3 | `FID_INPUT_ISCD` | 발행사 | string | Y | 12 | '00000(전체), 00003(한국투자증권)<br>, 00017(KB증권), 00005(미래에셋주식회사)' |
| 4 | `FID_DIV_CLS_CODE` | 콜풋구분코드 | string | Y | 2 | 0(전체), 1(콜), 2(풋) |
| 5 | `FID_INPUT_PRICE_1` | 가격(이상) | string | Y | 12 |  |
| 6 | `FID_INPUT_PRICE_2` | 가격(이하) | string | Y | 12 |  |
| 7 | `FID_INPUT_VOL_1` | 거래량(이상) | string | Y | 18 |  |
| 8 | `FID_INPUT_VOL_2` | 거래량(이하) | string | Y | 18 |  |
| 9 | `FID_RANK_SORT_CLS_CODE` | 순위정렬구분코드 | string | Y | 2 | 0(전환비율), 1(레버리지), 2(행사가 ), 3(내재가치), 4(시간가치) |
| 10 | `FID_BLNG_CLS_CODE` | 결재방법 | string | Y | 2 | 0(전체), 1(일반), 2(조기종료) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (17)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 5 | `elw_kor_isnm` | ELW한글종목명 | string | Y | 40 |  |
| 6 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 7 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 8 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 9 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 10 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 11 | `stck_cnvr_rate` | 주식전환비율 | string | Y | 136 |  |
| 12 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |
| 13 | `acpr` | 행사가 | string | Y | 112 |  |
| 14 | `tmvl_val` | 시간가치값 | string | Y | 132 |  |
| 15 | `invl_val` | 내재가치값 | string | Y | 132 |  |
| 16 | `elw_ko_barrier` | 조기종료발생기준가격 | string | Y | 112 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:20279
FID_UNAS_INPUT_ISCD:000000
FID_INPUT_ISCD:00000
FID_DIV_CLS_CODE:0
FID_INPUT_PRICE_1:
FID_INPUT_PRICE_2:
FID_INPUT_VOL_1:
FID_INPUT_VOL_2:
FID_RANK_SORT_CLS_CODE:0
FID_BLNG_CLS_CODE:0
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "elw_shrn_iscd": "52JW82",
            "elw_kor_isnm": "미래JW82KOSPI200콜",
            "elw_prpr": "360",
            "prdy_vrss": "-170",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-32.08",
            "acml_vol": "726070",
            "stck_cnvr_rate": "100.000000",
            "lvrg_val": "35.047882",
            "acpr": "375.00",
            "tmvl_val": "360.00",
            "invl_val": "0.00",
            "elw_ko_barrier": "0.00"
        },
        {
            "elw_shrn_iscd": "52JW83",
            "elw_kor_isnm": "미래JW83KOSPI200콜",
            "elw_prpr": "450",
            "prdy_vrss": "180",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "66.67",
            "acml_vol": "194290",
            "stck_cnvr_rate": "100.000000",
            "lvrg_val": "32.774658",
            "acpr": "372.50",
            "tmvl_val": "450.00",
            "invl_val": "0.00",
            "elw_ko_barrier": "0.00"
        },
        {
            "elw_shrn_iscd": "52JW84",
            "elw_kor_isnm": "미래JW84KOSPI200콜",
            "elw_prpr": "565",
            "prdy_vrss": "215",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "61.43",
            "acml_vol": "41160",
            "stck_cnvr_rate": "100.000000",
            "lvrg_val": "30.090385",
            "acpr": "370.00",
            "tmvl_val": "565.00",
            "invl_val": "0.00",
            "elw_ko_barrier": "0.00"
        },
        {
            "elw_shrn_iscd": "52JW85",
            "elw_kor_isnm": "미래JW85KOSPI200콜",
            "elw_prpr": "640",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "stck_cnvr_rate": "100.000000",
            "lvrg_val": "30.062588",
            "acpr": "367.50",
            "tmvl_val": "640.00",
            "invl_val": "0.00",
            "elw_ko_barrier": "0.00"
        },
        {
            "elw_shrn_iscd": "52JW86",
            "elw_kor_isnm": "미래JW86KOSPI200콜",
            "elw_prpr": "450",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "acml_vol": "0",
            "stck_cnvr_rate": "100.000000",
            "lvrg_val": "55.580410",
            "acpr": "365.00",
            "tmvl_val": "228.00",
            "invl_val": "222.00",
            "elw_ko_barrier": "0.00"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 투자지표추이(체결)

- **API ID**: 국내주식-172
- **실전 TR_ID**: FHPEW02740100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/indicator-trend-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 투자지표추이(체결) API입니다.
한국투자 HTS(eFriend Plus) &gt; [0274] ELW 투자지표추이 화면에서 "시간별 비교추이" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02740100 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | ex) 58J297(KBJ297삼성전자콜) |

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
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `stck_cntg_hour` | 주식체결시간 | string | Y | 6 |  |
| 5 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 6 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 7 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 8 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 9 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 10 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |
| 11 | `gear` | 기어링 | string | Y | 84 |  |
| 12 | `tmvl_val` | 시간가치값 | string | Y | 132 |  |
| 13 | `invl_val` | 내재가치값 | string | Y | 132 |  |
| 14 | `prit` | 패리티 | string | Y | 112 |  |
| 15 | `apprch_rate` | 접근도 | string | Y | 112 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:57K281
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "stck_cntg_hour": "125151",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "827720",
            "lvrg_val": "-10.8818",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "113228",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "772020",
            "lvrg_val": "-10.7220",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "112254",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "762920",
            "lvrg_val": "-10.7587",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "112254",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "753820",
            "lvrg_val": "-10.7587",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "112028",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "707220",
            "lvrg_val": "-10.6040",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "112028",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "692220",
            "lvrg_val": "-10.6040",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "111947",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "651530",
            "lvrg_val": "-10.6040",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "105955",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "599740",
            "lvrg_val": "-10.7413",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "105955",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "559050",
            "lvrg_val": "-10.7413",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "100603",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "544050",
            "lvrg_val": "-10.6177",
            "gear": "19.6000",
            "tmvl_val": "24.00",
            "invl_val": "16.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "100541",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "544040",
            "lvrg_val": "-10.6177",
            "gear": "19.6000",
            "tmvl_val": "24.00",
            "invl_val": "16.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "100540",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "532200",
            "lvrg_val": "-10.6177",
            "gear": "19.6000",
            "tmvl_val": "24.00",
            "invl_val": "16.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "100540",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "531340",
            "lvrg_val": "-10.6177",
            "gear": "19.6000",
            "tmvl_val": "24.00",
            "invl_val": "16.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "100507",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "529040",
            "lvrg_val": "-10.6015",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "100407",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "514900",
            "lvrg_val": "-10.7188",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "100347",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "473340",
            "lvrg_val": "-10.7188",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "095709",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "472140",
            "lvrg_val": "-10.7387",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "095709",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "471730",
            "lvrg_val": "-10.7387",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "095709",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "431030",
            "lvrg_val": "-10.7387",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "094251",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "416030",
            "lvrg_val": "-10.7455",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "094209",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "414380",
            "lvrg_val": "-10.7290",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "094209",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "399380",
            "lvrg_val": "-10.7290",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "094134",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "358680",
            "lvrg_val": "-10.6168",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "094134",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "317980",
            "lvrg_val": "-10.6168",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "094021",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "302980",
            "lvrg_val": "-10.6006",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "092950",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "287980",
            "lvrg_val": "-10.8278",
            "gear": "19.5500",
            "tmvl_val": "22.00",
            "invl_val": "18.00",
            "prit": "102.3000",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "092945",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "287960",
            "lvrg_val": "-10.8278",
            "gear": "19.5500",
            "tmvl_val": "22.00",
            "invl_val": "18.00",
            "prit": "102.3000",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091933",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "287950",
            "lvrg_val": "-10.8896",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091930",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "232250",
            "lvrg_val": "-10.8896",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091653",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "217250",
            "lvrg_val": "-10.7536",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091652",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "176550",
            "lvrg_val": "-10.7536",
            "gear": "19.6000",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091434",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "161550",
            "lvrg_val": "-10.5888",
            "gear": "19.5500",
            "tmvl_val": "24.00",
            "invl_val": "16.00",
            "prit": "102.3000",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091432",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "160650",
            "lvrg_val": "-10.5888",
            "gear": "19.5500",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.3000",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091314",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "145650",
            "lvrg_val": "-10.7370",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091312",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "130650",
            "lvrg_val": "-10.7370",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "091006",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "128890",
            "lvrg_val": "-12.0998",
            "gear": "22.3400",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.3000",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "090814",
            "elw_prpr": "35",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-10",
            "prdy_ctrt": "-22.22",
            "acml_vol": "108910",
            "lvrg_val": "-10.5019",
            "gear": "19.6000",
            "tmvl_val": "19.00",
            "invl_val": "16.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "090800",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "108900",
            "lvrg_val": "-10.4962",
            "gear": "19.6000",
            "tmvl_val": "24.00",
            "invl_val": "16.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "090758",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "55720",
            "lvrg_val": "-10.4962",
            "gear": "19.6000",
            "tmvl_val": "24.00",
            "invl_val": "16.00",
            "prit": "102.0400",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "090729",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "55710",
            "lvrg_val": "-10.4801",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "090710",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "20010",
            "lvrg_val": "-10.4801",
            "gear": "19.5700",
            "tmvl_val": "23.00",
            "invl_val": "17.00",
            "prit": "102.1700",
            "apprch_rate": "0.00"
        },
        {
            "stck_cntg_hour": "090504",
            "elw_prpr": "40",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-11.11",
            "acml_vol": "10",
            "lvrg_val": "-9.2509",
            "gear": "17.4600",
            "tmvl_val": "25.00",
            "invl_val": "15.00",
            "prit": "101.7800",
            "apprch_rate": "0.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 상승률순위

- **API ID**: 국내주식-167
- **실전 TR_ID**: FHPEW02770000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/ranking/updown-rate`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
ELW 상승률순위 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0277] ELW 상승률순위 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02770000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (14)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 사용자권한정보 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_COND_SCR_DIV_CODE` | 거래소코드 | string | Y | 5 | Unique key(20277) |
| 2 | `FID_UNAS_INPUT_ISCD` | 상승율/하락율 구분 | string | Y | 12 | '000000(전체), 2001(코스피200)<br>, 3003(코스닥150), 005930(삼성전자) ' |
| 3 | `FID_INPUT_ISCD` | N일자값 | string | Y | 12 | '00000(전체), 00003(한국투자증권)<br>, 00017(KB증권), 00005(미래에셋주식회사)' |
| 4 | `FID_INPUT_RMNN_DYNU_1` | 거래량조건 | string | Y | 5 | '0(전체), 1(1개월이하), 2(1개월~2개월), <br>3(2개월~3개월), 4(3개월~6개월),<br>5(6개월~9개월),6(9개월~12개월), 7(12개월이상)' |
| 5 | `FID_DIV_CLS_CODE` | NEXT KEY BUFF | string | Y | 2 | 0(전체), 1(콜), 2(풋) |
| 6 | `FID_INPUT_PRICE_1` | 사용자권한정보 | string | Y | 12 |  |
| 7 | `FID_INPUT_PRICE_2` | 거래소코드 | string | Y | 12 |  |
| 8 | `FID_INPUT_VOL_1` | 상승율/하락율 구분 | string | Y | 18 |  |
| 9 | `FID_INPUT_VOL_2` | N일자값 | string | Y | 18 |  |
| 10 | `FID_INPUT_DATE_1` | 거래량조건 | string | Y | 10 |  |
| 11 | `FID_RANK_SORT_CLS_CODE` | NEXT KEY BUFF | string | Y | 2 | '0(상승율), 1(하락율), 2(시가대비상승율)<br>, 3(시가대비하락율), 4(변동율)' |
| 12 | `FID_BLNG_CLS_CODE` | 사용자권한정보 | string | Y | 2 | 0(전체) |
| 13 | `FID_INPUT_DATE_2` | 거래소코드 | string | Y | 10 |  |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (39)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `hts_kor_isnm` | HTS한글종목명 | string | Y | 40 |  |
| 5 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 6 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 7 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 8 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 9 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 10 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 11 | `stck_sdpr` | 주식기준가 | string | Y | 10 |  |
| 12 | `sdpr_vrss_prpr_sign` | 기준가대비현재가부호 | string | Y | 1 |  |
| 13 | `sdpr_vrss_prpr` | 기준가대비현재가 | string | Y | 10 |  |
| 14 | `sdpr_vrss_prpr_rate` | 기준가대비현재가비율 | string | Y | 84 |  |
| 15 | `stck_oprc` | 주식시가2 | string | Y | 10 |  |
| 16 | `oprc_vrss_prpr_sign` | 시가2대비현재가부호 | string | Y | 1 |  |
| 17 | `oprc_vrss_prpr` | 시가2대비현재가 | string | Y | 10 |  |
| 18 | `oprc_vrss_prpr_rate` | 시가2대비현재가비율 | string | Y | 84 |  |
| 19 | `stck_hgpr` | 주식최고가 | string | Y | 10 |  |
| 20 | `stck_lwpr` | 주식최저가 | string | Y | 10 |  |
| 21 | `prd_rsfl_sign` | 기간등락부호 | string | Y | 1 |  |
| 22 | `prd_rsfl` | 기간등락 | string | Y | 10 |  |
| 23 | `prd_rsfl_rate` | 기간등락비율 | string | Y | 84 |  |
| 24 | `stck_cnvr_rate` | 주식전환비율 | string | Y | 136 |  |
| 25 | `hts_rmnn_dynu` | HTS잔존일수 | string | Y | 5 |  |
| 26 | `acpr` | 행사가 | string | Y | 112 |  |
| 27 | `unas_isnm` | 기초자산명 | string | Y | 40 |  |
| 28 | `unas_shrn_iscd` | 기초자산코드 | string | Y | 12 |  |
| 29 | `lp_hldn_rate` | LP보유비율 | string | Y | 84 |  |
| 30 | `prit` | 패리티 | string | Y | 112 |  |
| 31 | `prls_qryr_stpr_prc` | 손익분기주가가격 | string | Y | 112 |  |
| 32 | `delta_val` | 델타값 | string | Y | 114 |  |
| 33 | `theta` | 세타 | string | Y | 84 |  |
| 34 | `prls_qryr_rate` | 손익분기비율 | string | Y | 84 |  |
| 35 | `stck_lstn_date` | 주식상장일자 | string | Y | 8 |  |
| 36 | `stck_last_tr_date` | 주식최종거래일자 | string | Y | 8 |  |
| 37 | `hts_ints_vltl` | HTS내재변동성 | string | Y | 114 |  |
| 38 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:20277
FID_UNAS_INPUT_ISCD:000000
FID_INPUT_ISCD:00000
FID_INPUT_RMNN_DYNU_1:0
FID_DIV_CLS_CODE:0
FID_INPUT_PRICE_1:
FID_INPUT_PRICE_2:
FID_INPUT_VOL_1:
FID_INPUT_VOL_2:
FID_INPUT_DATE_1:1
FID_RANK_SORT_CLS_CODE:0
FID_BLNG_CLS_CODE:0
FID_INPUT_DATE_2:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "hts_kor_isnm": "한국JAKWLS일렉콜",
            "elw_shrn_iscd": "57JAKW",
            "elw_prpr": "460",
            "prdy_vrss": "350",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "318.18",
            "acml_vol": "3320",
            "stck_sdpr": "110",
            "sdpr_vrss_prpr_sign": "2",
            "sdpr_vrss_prpr": "460",
            "sdpr_vrss_prpr_rate": "0.00",
            "stck_oprc": "470",
            "oprc_vrss_prpr_sign": "5",
            "oprc_vrss_prpr": "-10",
            "oprc_vrss_prpr_rate": "-2.13",
            "stck_hgpr": "605",
            "stck_lwpr": "0",
            "prd_rsfl_sign": "2",
            "prd_rsfl": "0",
            "prd_rsfl_rate": "34.44",
            "stck_cnvr_rate": "0.010000",
            "hts_rmnn_dynu": "63",
            "acpr": "95600.00",
            "unas_isnm": "LS ELECTRIC",
            "unas_shrn_iscd": "010120",
            "lp_hldn_rate": "99.96",
            "prit": "146.12",
            "prls_qryr_stpr_prc": "141600.00",
            "delta_val": "0.930744",
            "theta": "0.7829",
            "prls_qryr_rate": "1.3600",
            "stck_lstn_date": "20231116",
            "stck_last_tr_date": "20240613",
            "hts_ints_vltl": "71.91",
            "lvrg_val": "2.820154"
        },
        {
            "hts_kor_isnm": "KBJF27KOSPI200콜",
            "elw_shrn_iscd": "58JF27",
            "elw_prpr": "2395",
            "prdy_vrss": "1745",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "268.46",
            "acml_vol": "100",
            "stck_sdpr": "650",
            "sdpr_vrss_prpr_sign": "2",
            "sdpr_vrss_prpr": "2395",
            "sdpr_vrss_prpr_rate": "0.00",
            "stck_oprc": "2395",
            "oprc_vrss_prpr_sign": "3",
            "oprc_vrss_prpr": "0",
            "oprc_vrss_prpr_rate": "0.00",
            "stck_hgpr": "2395",
            "stck_lwpr": "0",
            "prd_rsfl_sign": "3",
            "prd_rsfl": "0",
            "prd_rsfl_rate": "0.00",
            "stck_cnvr_rate": "100.000000",
            "hts_rmnn_dynu": "28",
            "acpr": "345.00",
            "unas_isnm": "KOSPI200",
            "unas_shrn_iscd": "2001",
            "lp_hldn_rate": "99.99",
            "prit": "106.44",
            "prls_qryr_stpr_prc": "368.95",
            "delta_val": "0.900891",
            "theta": "13.8535",
            "prls_qryr_rate": "0.4600",
            "stck_lstn_date": "20231228",
            "stck_last_tr_date": "20240509",
            "hts_ints_vltl": "19.71",
            "lvrg_val": "13.810659"
        },
		...
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 민감도 추이(일별)

- **API ID**: 국내주식-176
- **실전 TR_ID**: FHPEW02830200
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/sensitivity-trend-daily`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 민감도 추이(일별) API입니다.
한국투자 HTS(eFriend Plus) &gt; [0283] ELW 민감도 추이 화면의 "일자별" 민감도추이 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02830200 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | ex)(58J438(KBJ438삼성전자풋) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (15)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `stck_bsop_date` | 주식영업일자 | string | Y | 8 |  |
| 5 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 6 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 7 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 8 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 9 | `hts_thpr` | HTS이론가 | string | Y | 112 |  |
| 10 | `delta_val` | 델타값 | string | Y | 114 |  |
| 11 | `gama` | 감마 | string | Y | 84 |  |
| 12 | `theta` | 세타 | string | Y | 84 |  |
| 13 | `vega` | 베가 | string | Y | 84 |  |
| 14 | `rho` | 로우 | string | Y | 84 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:57K281
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "stck_bsop_date": "20240507",
            "elw_prpr": "25",
            "prdy_vrss": "-20",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-44.44",
            "hts_thpr": "20.39",
            "delta_val": "-0.4034",
            "gama": "0.0000",
            "theta": "0.5843",
            "vega": "0.9954",
            "rho": "-0.3529"
        },
        {
            "stck_bsop_date": "20240503",
            "elw_prpr": "45",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "hts_thpr": "39.43",
            "delta_val": "-0.5792",
            "gama": "0.0000",
            "theta": "0.5531",
            "vega": "0.9786",
            "rho": "-0.5143"
        },
        {
            "stck_bsop_date": "20240502",
            "elw_prpr": "45",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "hts_thpr": "37.16",
            "delta_val": "-0.5529",
            "gama": "0.0000",
            "theta": "0.5859",
            "vega": "1.0136",
            "rho": "-0.5143"
        },
        {
            "stck_bsop_date": "20240430",
            "elw_prpr": "45",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-10.00",
            "hts_thpr": "39.30",
            "delta_val": "-0.5847",
            "gama": "0.0000",
            "theta": "0.4979",
            "vega": "1.0113",
            "rho": "-0.5579"
        },
        {
            "stck_bsop_date": "20240429",
            "elw_prpr": "50",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "hts_thpr": "44.66",
            "delta_val": "-0.6211",
            "gama": "0.0000",
            "theta": "0.4599",
            "vega": "0.9938",
            "rho": "-0.6106"
        },
        {
            "stck_bsop_date": "20240426",
            "elw_prpr": "50",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "hts_thpr": "44.96",
            "delta_val": "-0.6202",
            "gama": "0.0000",
            "theta": "0.4439",
            "vega": "1.0115",
            "rho": "-0.6308"
        },
        {
            "stck_bsop_date": "20240425",
            "elw_prpr": "50",
            "prdy_vrss": "5",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "11.11",
            "hts_thpr": "47.92",
            "delta_val": "-0.6534",
            "gama": "0.0000",
            "theta": "0.3673",
            "vega": "0.9917",
            "rho": "-0.6802"
        },
        {
            "stck_bsop_date": "20240424",
            "elw_prpr": "45",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-18.18",
            "hts_thpr": "33.74",
            "delta_val": "-0.5173",
            "gama": "0.0000",
            "theta": "0.5516",
            "vega": "1.1208",
            "rho": "-0.5781"
        },
        {
            "stck_bsop_date": "20240423",
            "elw_prpr": "55",
            "prdy_vrss": "-5",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-8.33",
            "hts_thpr": "53.36",
            "delta_val": "-0.6933",
            "gama": "0.0000",
            "theta": "0.3086",
            "vega": "0.9632",
            "rho": "-0.7635"
        },
        {
            "stck_bsop_date": "20240422",
            "elw_prpr": "60",
            "prdy_vrss": "15",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "33.33",
            "hts_thpr": "49.10",
            "delta_val": "-0.6135",
            "gama": "0.0000",
            "theta": "0.4786",
            "vega": "1.0740",
            "rho": "-0.7166"
        },
        {
            "stck_bsop_date": "20240419",
            "elw_prpr": "45",
            "prdy_vrss": "10",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "28.57",
            "hts_thpr": "38.76",
            "delta_val": "-0.5727",
            "gama": "0.0000",
            "theta": "0.4045",
            "vega": "1.1391",
            "rho": "-0.6851"
        },
        {
            "stck_bsop_date": "20240418",
            "elw_prpr": "35",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "hts_thpr": "28.22",
            "delta_val": "-0.4785",
            "gama": "0.0000",
            "theta": "0.4284",
            "vega": "1.2033",
            "rho": "-0.5988"
        },
        {
            "stck_bsop_date": "20240417",
            "elw_prpr": "35",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "hts_thpr": "31.87",
            "delta_val": "-0.5156",
            "gama": "0.0000",
            "theta": "0.3620",
            "vega": "1.2100",
            "rho": "-0.6539"
        },
        {
            "stck_bsop_date": "20240416",
            "elw_prpr": "35",
            "prdy_vrss": "10",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "40.00",
            "hts_thpr": "26.58",
            "delta_val": "-0.4591",
            "gama": "0.0000",
            "theta": "0.4314",
            "vega": "1.2378",
            "rho": "-0.6115"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 비교대상종목조회

- **API ID**: 국내주식-183
- **실전 TR_ID**: FHKEW151701C0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/compare-stocks`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 비교대상종목조회 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0288] ELW 기초자산별 ELW 시세의 좌측 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKEW151701C0 |
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
| 0 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | 11517(Primary key) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | 종목코드(ex)005930(삼성전자)) |

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
| 3 | `output` | 응답상세 | object | Y |  |  |
| 4 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 5 | `elw_kor_isnm` | ELW한글종목명 | string | Y | 40 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_SCR_DIV_CODE:11517
FID_INPUT_ISCD:005930
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "elw_shrn_iscd": "58J782",
            "elw_kor_isnm": "KBJ782삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58J993",
            "elw_kor_isnm": "KBJ993삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58JC71",
            "elw_kor_isnm": "KBJC71삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58JC72",
            "elw_kor_isnm": "KBJC72삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58JC73",
            "elw_kor_isnm": "KBJC73삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58JC74",
            "elw_kor_isnm": "KBJC74삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58JC75",
            "elw_kor_isnm": "KBJC75삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58JC76",
            "elw_kor_isnm": "KBJC76삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58JE26",
            "elw_kor_isnm": "KBJE26삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58JE27",
            "elw_kor_isnm": "KBJE27삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58JE28",
            "elw_kor_isnm": "KBJE28삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58JE30",
            "elw_kor_isnm": "KBJE30삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K001",
            "elw_kor_isnm": "KBK001삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K002",
            "elw_kor_isnm": "KBK002삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K003",
            "elw_kor_isnm": "KBK003삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K004",
            "elw_kor_isnm": "KBK004삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K005",
            "elw_kor_isnm": "KBK005삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K006",
            "elw_kor_isnm": "KBK006삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K167",
            "elw_kor_isnm": "KBK167삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K168",
            "elw_kor_isnm": "KBK168삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K169",
            "elw_kor_isnm": "KBK169삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K314",
            "elw_kor_isnm": "KBK314삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K416",
            "elw_kor_isnm": "KBK416삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K417",
            "elw_kor_isnm": "KBK417삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K418",
            "elw_kor_isnm": "KBK418삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K419",
            "elw_kor_isnm": "KBK419삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K420",
            "elw_kor_isnm": "KBK420삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K421",
            "elw_kor_isnm": "KBK421삼성전자풋"
        },
        {
            "elw_shrn_iscd": "58K579",
            "elw_kor_isnm": "KBK579삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K580",
            "elw_kor_isnm": "KBK580삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K581",
            "elw_kor_isnm": "KBK581삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K582",
            "elw_kor_isnm": "KBK582삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K583",
            "elw_kor_isnm": "KBK583삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K584",
            "elw_kor_isnm": "KBK584삼성전자콜"
        },
        {
            "elw_shrn_iscd": "58K585",
            "elw_kor_isnm": "KBK585삼성전자풋"
        },
        ...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW LP매매추이

- **API ID**: 국내주식-182
- **실전 TR_ID**: FHPEW03760000
- **모의 TR_ID**: 
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/lp-trade-trend`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW LP매매추이 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0376] ELW LP매매추이 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW03760000 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분(W) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | 입력종목코드(ex 52K577(미래 K577KOSDAQ150콜) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (34)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 5 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 6 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 7 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 8 | `acml_vol` | 누적거래량 | string | Y | 18 |  |
| 9 | `prdy_vol` | 전일거래량 | string | Y | 18 |  |
| 10 | `stck_cnvr_rate` | 주식전환비율 | string | Y | 136 |  |
| 11 | `prit` | 패리티 | string | Y | 112 |  |
| 12 | `lvrg_val` | 레버리지값 | string | Y | 114 |  |
| 13 | `gear` | 기어링 | string | Y | 84 |  |
| 14 | `prls_qryr_rate` | 손익분기비율 | string | Y | 84 |  |
| 15 | `cfp` | 자본지지점 | string | Y | 112 |  |
| 16 | `invl_val` | 내재가치값 | string | Y | 132 |  |
| 17 | `tmvl_val` | 시간가치값 | string | Y | 132 |  |
| 18 | `acpr` | 행사가 | string | Y | 112 |  |
| 19 | `elw_ko_barrier` | 조기종료발생기준가격 | string | Y | 112 |  |
| 20 | `output2` | 응답상세 | object array | Y |  | array |
| 21 | `stck_bsop_date` | 주식영업일자 | string | Y | 8 |  |
| 22 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 23 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 24 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 25 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 26 | `lp_seln_qty` | LP매도수량 | string | Y | 19 |  |
| 27 | `lp_seln_avrg_unpr` | LP매도평균단가 | string | Y | 19 |  |
| 28 | `lp_shnu_qty` | LP매수수량 | string | Y | 19 |  |
| 29 | `lp_shnu_avrg_unpr` | LP매수평균단가 | string | Y | 19 |  |
| 30 | `lp_hvol` | LP보유량 | string | Y | 18 |  |
| 31 | `lp_hldn_rate` | LP보유비율 | string | Y | 84 |  |
| 32 | `prsn_deal_qty` | 개인매매수량 | string | Y | 19 |  |
| 33 | `apprch_rate` | 접근도 | string | Y | 112 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:57K281
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": {
        "elw_prpr": "40",
        "prdy_vrss_sign": "2",
        "prdy_vrss": "5",
        "prdy_ctrt": "14.29",
        "acml_vol": "320750",
        "prdy_vol": "114850",
        "stck_cnvr_rate": "0.010000",
        "prit": "103.35",
        "lvrg_val": "-12.130651",
        "gear": "19.3500",
        "prls_qryr_rate": "-1.8000",
        "cfp": "-1.7100",
        "invl_val": "27.00",
        "tmvl_val": "13.00",
        "acpr": "80000.00",
        "elw_ko_barrier": "0.00"
    },
    "output2": [
        {
            "stck_bsop_date": "20240516",
            "elw_prpr": "35",
            "prdy_vrss_sign": "3",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "lp_seln_qty": "30030",
            "lp_seln_avrg_unpr": "30",
            "lp_shnu_qty": "84810",
            "lp_shnu_avrg_unpr": "34",
            "lp_hvol": "7999900",
            "lp_hldn_rate": "99.99",
            "prsn_deal_qty": "10",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240514",
            "elw_prpr": "35",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-12.50",
            "lp_seln_qty": "73510",
            "lp_seln_avrg_unpr": "35",
            "lp_shnu_qty": "74440",
            "lp_shnu_avrg_unpr": "35",
            "lp_hvol": "7945120",
            "lp_hldn_rate": "99.31",
            "prsn_deal_qty": "1260",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240513",
            "elw_prpr": "40",
            "prdy_vrss_sign": "2",
            "prdy_vrss": "10",
            "prdy_ctrt": "33.33",
            "lp_seln_qty": "282010",
            "lp_seln_avrg_unpr": "36",
            "lp_shnu_qty": "277980",
            "lp_shnu_avrg_unpr": "36",
            "lp_hvol": "7944190",
            "lp_hldn_rate": "99.30",
            "prsn_deal_qty": "11140",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240510",
            "elw_prpr": "30",
            "prdy_vrss_sign": "2",
            "prdy_vrss": "5",
            "prdy_ctrt": "20.00",
            "lp_seln_qty": "137480",
            "lp_seln_avrg_unpr": "27",
            "lp_shnu_qty": "209950",
            "lp_shnu_avrg_unpr": "25",
            "lp_hvol": "7948220",
            "lp_hldn_rate": "99.35",
            "prsn_deal_qty": "2040",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240509",
            "elw_prpr": "25",
            "prdy_vrss_sign": "3",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "lp_seln_qty": "280020",
            "lp_seln_avrg_unpr": "25",
            "lp_shnu_qty": "209910",
            "lp_shnu_avrg_unpr": "25",
            "lp_hvol": "7875750",
            "lp_hldn_rate": "98.44",
            "prsn_deal_qty": "120",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240508",
            "elw_prpr": "25",
            "prdy_vrss_sign": "3",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "lp_seln_qty": "630000",
            "lp_seln_avrg_unpr": "25",
            "lp_shnu_qty": "630000",
            "lp_shnu_avrg_unpr": "25",
            "lp_hvol": "7945860",
            "lp_hldn_rate": "99.32",
            "prsn_deal_qty": "10000",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240507",
            "elw_prpr": "25",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-20",
            "prdy_ctrt": "-44.44",
            "lp_seln_qty": "98550",
            "lp_seln_avrg_unpr": "27",
            "lp_shnu_qty": "160420",
            "lp_shnu_avrg_unpr": "28",
            "lp_hvol": "7945860",
            "lp_hldn_rate": "99.32",
            "prsn_deal_qty": "26200",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240503",
            "elw_prpr": "45",
            "prdy_vrss_sign": "3",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "lp_seln_qty": "501890",
            "lp_seln_avrg_unpr": "40",
            "lp_shnu_qty": "491690",
            "lp_shnu_avrg_unpr": "40",
            "lp_hvol": "7883990",
            "lp_hldn_rate": "98.55",
            "prsn_deal_qty": "8440",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240502",
            "elw_prpr": "45",
            "prdy_vrss_sign": "3",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "lp_seln_qty": "402940",
            "lp_seln_avrg_unpr": "40",
            "lp_shnu_qty": "332240",
            "lp_shnu_avrg_unpr": "40",
            "lp_hvol": "7894190",
            "lp_hldn_rate": "98.67",
            "prsn_deal_qty": "54100",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240430",
            "elw_prpr": "45",
            "prdy_vrss_sign": "5",
            "prdy_vrss": "-5",
            "prdy_ctrt": "-10.00",
            "lp_seln_qty": "27840",
            "lp_seln_avrg_unpr": "48",
            "lp_shnu_qty": "33540",
            "lp_shnu_avrg_unpr": "45",
            "lp_hvol": "7964890",
            "lp_hldn_rate": "99.56",
            "prsn_deal_qty": "710",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240429",
            "elw_prpr": "50",
            "prdy_vrss_sign": "3",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "lp_seln_qty": "211510",
            "lp_seln_avrg_unpr": "50",
            "lp_shnu_qty": "175810",
            "lp_shnu_avrg_unpr": "50",
            "lp_hvol": "7959190",
            "lp_hldn_rate": "99.49",
            "prsn_deal_qty": "15700",
            "apprch_rate": "0.00"
        },
        {
            "stck_bsop_date": "20240426",
            "elw_prpr": "50",
            "prdy_vrss_sign": "3",
            "prdy_vrss": "0",
            "prdy_ctrt": "0.00",
            "lp_seln_qty": "35700",
            "lp_seln_avrg_unpr": "50",
            "lp_shnu_qty": "91400",
            "lp_shnu_avrg_unpr": "48",
            "lp_hvol": "7994890",
            "lp_hldn_rate": "99.93",
            "prsn_deal_qty": "60",
            "apprch_rate": "0.00"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 민감도 추이(체결)

- **API ID**: 국내주식-175
- **실전 TR_ID**: FHPEW02830100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/sensitivity-trend-ccnl`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 민감도 추이(체결) API입니다.
한국투자 HTS(eFriend Plus) &gt; [0283] ELW 민감도 추이 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02830100 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | 시장구분코드 (W) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | ex) 58J297(KBJ297삼성전자콜) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (15)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `stck_cntg_hour` | 주식체결시간 | string | Y | 6 |  |
| 5 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 6 | `prdy_vrss` | 전일대비 | string | Y | 10 |  |
| 7 | `prdy_vrss_sign` | 전일대비부호 | string | Y | 1 |  |
| 8 | `prdy_ctrt` | 전일대비율 | string | Y | 82 |  |
| 9 | `hts_thpr` | hts 이론가 | string | Y | 112 |  |
| 10 | `delta_val` | 델타 값 | string | Y | 114 |  |
| 11 | `gama` | 감마 | string | Y | 84 |  |
| 12 | `theta` | 세타 | string | Y | 84 |  |
| 13 | `vega` | 베가 | string | Y | 84 |  |
| 14 | `rho` | 로우 | string | Y | 84 |  |


### ELW 변동성 추이(틱)

- **API ID**: 국내주식-180
- **실전 TR_ID**: FHPEW02840400
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/volatility-trend-tick`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 변동성 추이(틱) API입니다.
한국투자 HTS(eFriend Plus) &gt; [0284] ELW 변동성 추이 화면의 "틱 차트" 변동성 추이 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHPEW02840400 |
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
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | W(Unique key) |
| 1 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | ex) 58J297(KBJ297삼성전자콜) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `bsop_date` | 주식영업일자 | string | Y | 8 |  |
| 5 | `stck_cntg_hour` | ELW현재가 | string | Y | 6 |  |
| 6 | `elw_prpr` | 전일대비 | string | Y | 10 |  |
| 7 | `hts_ints_vltl` | 전일대비부호 | string | Y | 114 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_INPUT_ISCD:57K281
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "150619",
            "elw_prpr": "25",
            "hts_ints_vltl": "33.03"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "150032",
            "elw_prpr": "25",
            "hts_ints_vltl": "28.44"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "150031",
            "elw_prpr": "25",
            "hts_ints_vltl": "28.44"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "145743",
            "elw_prpr": "25",
            "hts_ints_vltl": "33.44"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "145743",
            "elw_prpr": "25",
            "hts_ints_vltl": "33.44"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "133437",
            "elw_prpr": "25",
            "hts_ints_vltl": "32.47"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "133434",
            "elw_prpr": "25",
            "hts_ints_vltl": "32.47"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "132342",
            "elw_prpr": "25",
            "hts_ints_vltl": "31.60"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "093016",
            "elw_prpr": "30",
            "hts_ints_vltl": "28.62"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "092952",
            "elw_prpr": "25",
            "hts_ints_vltl": "28.62"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "091704",
            "elw_prpr": "30",
            "hts_ints_vltl": "33.03"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090900",
            "elw_prpr": "30",
            "hts_ints_vltl": "33.02"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090735",
            "elw_prpr": "30",
            "hts_ints_vltl": "28.59"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090712",
            "elw_prpr": "30",
            "hts_ints_vltl": "28.59"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090710",
            "elw_prpr": "30",
            "hts_ints_vltl": "28.59"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090555",
            "elw_prpr": "30",
            "hts_ints_vltl": "33.46"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090553",
            "elw_prpr": "30",
            "hts_ints_vltl": "33.46"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090511",
            "elw_prpr": "30",
            "hts_ints_vltl": "33.46"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090445",
            "elw_prpr": "30",
            "hts_ints_vltl": "36.51"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090445",
            "elw_prpr": "30",
            "hts_ints_vltl": "36.51"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090445",
            "elw_prpr": "30",
            "hts_ints_vltl": "36.51"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090320",
            "elw_prpr": "35",
            "hts_ints_vltl": "36.51"
        },
        {
            "bsop_date": "20240507",
            "stck_cntg_hour": "090030",
            "elw_prpr": "40",
            "hts_ints_vltl": "32.97"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### ELW 만기예정_만기종목

- **API ID**: 국내주식-184
- **실전 TR_ID**: FHKEW154700C0
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/elw/v1/quotations/expiration-stocks`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
ELW 만기예정/만기종목 API입니다. 
한국투자 HTS(eFriend Plus) &gt; [0290] ELW 만기예정/만기종목 화면의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

최근 100건까지 데이터 조회 가능합니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKEW154700C0 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (10)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_COND_MRKT_DIV_CODE` | 조건시장분류코드 | string | Y | 2 | W 입력 |
| 1 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | 11547 입력 |
| 2 | `FID_INPUT_DATE_1` | 입력날짜1 | string | Y | 10 | 입력날짜 ~ (ex) 20240402) |
| 3 | `FID_INPUT_DATE_2` | 입력날짜2 | string | Y | 10 | ~입력날짜 (ex) 20240408) |
| 4 | `FID_DIV_CLS_CODE` | 분류구분코드 | string | Y | 2 | 0(콜),1(풋),2(전체) |
| 5 | `FID_ETC_CLS_CODE` | 기타구분코드 | string | Y | 2 | 공백 입력 |
| 6 | `FID_UNAS_INPUT_ISCD` | 기초자산입력종목코드 | string | Y | 12 | 000000(전체), 2001(KOSPI 200), 기초자산코드(종목코드 ex. 삼성전자-005930) |
| 7 | `FID_INPUT_ISCD_2` | 발행회사코드 | string | Y | 8 | 00000(전체), 00003(한국투자증권), 00017(KB증권), 00005(미래에셋증권) |
| 8 | `FID_BLNG_CLS_CODE` | 결제방법 | string | Y | 2 | 0(전체),1(일반),2(조기종료) |
| 9 | `FID_INPUT_OPTION_1` | 입력옵션1 | string | Y | 10 | 공백 입력 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (25)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `elw_shrn_iscd` | ELW단축종목코드 | string | Y | 9 |  |
| 5 | `elw_kor_isnm` | ELW한글종목명 | string | Y | 40 |  |
| 6 | `unas_isnm` | 기초자산종목명 | string | Y | 40 |  |
| 7 | `unas_prpr` | 기초자산현재가 | string | Y | 112 |  |
| 8 | `acpr` | 행사가 | string | Y | 112 |  |
| 9 | `stck_cnvr_rate` | 주식전환비율 | string | Y | 136 |  |
| 10 | `elw_prpr` | ELW현재가 | string | Y | 10 |  |
| 11 | `stck_lstn_date` | 주식상장일자 | string | Y | 8 |  |
| 12 | `stck_last_tr_date` | 주식최종거래일자 | string | Y | 8 |  |
| 13 | `total_rdmp_amt` | 총상환금액 | string | Y | 18 |  |
| 14 | `rdmp_amt` | 상환금액 | string | Y | 186 |  |
| 15 | `lstn_stcn` | 상장주수 | string | Y | 18 |  |
| 16 | `lp_hvol` | LP보유량 | string | Y | 18 |  |
| 17 | `ccls_paym_prc` | 확정지급2가격 | string | Y | 223 |  |
| 18 | `mtrt_vltn_amt` | 만기평가금액 | string | Y | 192 |  |
| 19 | `evnt_prd_fin_date` | 행사2기간종료일자 | string | Y | 8 |  |
| 20 | `stlm_date` | 결제일자 | string | Y | 8 |  |
| 21 | `pblc_prc` | 발행가격 | string | Y | 18 |  |
| 22 | `unas_shrn_iscd` | 기초자산단축종목코드 | string | Y | 9 |  |
| 23 | `stnd_iscd` | 표준종목코드 | string | Y | 12 |  |
| 24 | `rdmp_ask_amt` | 상환청구금액 | string | Y | 18 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_COND_MRKT_DIV_CODE:W
FID_COND_SCR_DIV_CODE:11547
FID_INPUT_DATE_1:20240611
FID_INPUT_DATE_2:20240618
FID_DIV_CLS_CODE:2
FID_ETC_CLS_CODE:
FID_UNAS_INPUT_ISCD:000000
FID_INPUT_ISCD_2:00000
FID_BLNG_CLS_CODE:0
FID_INPUT_OPTION_1:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "elw_shrn_iscd": "58K374",
            "elw_kor_isnm": "KBK374KOSPI200풋",
            "unas_isnm": "KOSPI200",
            "unas_prpr": "367.71",
            "acpr": "372.50",
            "stck_cnvr_rate": "100.000000",
            "elw_prpr": "515",
            "stck_lstn_date": "20240320",
            "stck_last_tr_date": "20240613",
            "total_rdmp_amt": "0",
            "rdmp_amt": "0.000000",
            "lstn_stcn": "5000000",
            "lp_hvol": "4982390",
            "ccls_paym_prc": "0.000",
            "mtrt_vltn_amt": "367.71",
            "evnt_prd_fin_date": "20240617",
            "stlm_date": "20240619",
            "pblc_prc": "1143",
            "unas_shrn_iscd": "2001",
            "stnd_iscd": "KRA583261E30",
            "rdmp_ask_amt": ""
        },
        {
            "elw_shrn_iscd": "58K373",
            "elw_kor_isnm": "KBK373KOSPI200풋",
            "unas_isnm": "KOSPI200",
            "unas_prpr": "367.71",
            "acpr": "370.00",
            "stck_cnvr_rate": "100.000000",
            "elw_prpr": "370",
            "stck_lstn_date": "20240320",
            "stck_last_tr_date": "20240613",
            "total_rdmp_amt": "0",
            "rdmp_amt": "0.000000",
            "lstn_stcn": "5000000",
            "lp_hvol": "4727930",
            "ccls_paym_prc": "0.000",
            "mtrt_vltn_amt": "367.71",
            "evnt_prd_fin_date": "20240617",
            "stlm_date": "20240619",
            "pblc_prc": "901",
            "unas_shrn_iscd": "2001",
            "stnd_iscd": "KRA583260E31",
            "rdmp_ask_amt": ""
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>


