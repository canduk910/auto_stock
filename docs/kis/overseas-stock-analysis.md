# [해외주식] 시세분석 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260911_030009.xlsx`

> 이 문서는 워크북에서 **전 필드 그대로** 생성됩니다. 손으로 고치지 마세요 — `사용` 표시만 보존됩니다.


## API 목록 (15개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 267 | REST | 해외주식 거래증가율순위 | HHDFS76330000 | GET | `/uapi/overseas-stock/v1/ranking/trade-growth` |  |
| 268 | REST | 해외주식 기간별권리조회 | CTRGT011R | GET | `/uapi/overseas-price/v1/quotations/period-rights` |  |
| 269 | REST | 해외주식 가격급등락 | HHDFS76260000 | GET | `/uapi/overseas-stock/v1/ranking/price-fluct` |  |
| 270 | REST | 해외주식 거래대금순위 | HHDFS76320010 | GET | `/uapi/overseas-stock/v1/ranking/trade-pbmn` |  |
| 271 | REST | 해외주식 거래량급증 | HHDFS76270000 | GET | `/uapi/overseas-stock/v1/ranking/volume-surge` |  |
| 273 | REST | 해외주식 매수체결강도상위 | HHDFS76280000 | GET | `/uapi/overseas-stock/v1/ranking/volume-power` |  |
| 274 | REST | 해외주식 거래회전율순위 | HHDFS76340000 | GET | `/uapi/overseas-stock/v1/ranking/trade-turnover` |  |
| 275 | REST | 해외뉴스종합(제목) | HHPSTH60100C1 | GET | `/uapi/overseas-price/v1/quotations/news-title` |  |
| 276 | REST | 당사 해외주식담보대출 가능 종목 | CTLN4050R | GET | `/uapi/overseas-price/v1/quotations/colable-by-company` |  |
| 277 | REST | 해외주식 시가총액순위 | HHDFS76350100 | GET | `/uapi/overseas-stock/v1/ranking/market-cap` |  |
| 278 | REST | 해외속보(제목) | FHKST01011801 | GET | `/uapi/overseas-price/v1/quotations/brknews-title` |  |
| 280 | REST | 해외주식 권리종합 | HHDFS78330900 | GET | `/uapi/overseas-price/v1/quotations/rights-by-ice` |  |
| 281 | REST | 해외주식 거래량순위 | HHDFS76310010 | GET | `/uapi/overseas-stock/v1/ranking/trade-vol` |  |
| 9999 | REST | 해외주식 신고_신저가 | HHDFS76300000 | GET | `/uapi/overseas-stock/v1/ranking/new-highlow` |  |
| 9999 | REST | 해외주식 상승율_하락율 | HHDFS76290000 | GET | `/uapi/overseas-stock/v1/ranking/updown-rate` |  |

---

## 상세 명세


### 해외주식 거래증가율순위

- **API ID**: 해외주식-045
- **실전 TR_ID**: HHDFS76330000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/trade-growth`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 거래증가율순위 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7633] 거래증가율순위 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76330000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `NDAY` | N일자값 | string | Y | 1 | N일전 : 0(당일), 1(2일), 2(3일), 3(5일), 4(10일), 5(20일전), 6(30일), 7(60일), 8(120일), 9(1년) |
| 4 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (26)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메시지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태정보 | string | Y | 20 |  |
| 6 | `crec` | 현재조회종목수 | string | Y | 6 |  |
| 7 | `trec` | 전체조회종목수 | string | Y | 6 |  |
| 8 | `nrec` | RecordCount | string | Y | 4 |  |
| 9 | `output2` | 응답상세 | object array | Y |  | array |
| 10 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 11 | `excd` | 거래소코드 | string | Y | 4 |  |
| 12 | `symb` | 종목코드 | string | Y | 1 |  |
| 13 | `name` | 종목명 | string | Y | 48 |  |
| 14 | `last` | 현재가 | string | Y | 16 |  |
| 15 | `sign` | 기호 | string | Y | 1 |  |
| 16 | `diff` | 대비 | string | Y | 12 |  |
| 17 | `rate` | 등락율 | string | Y | 12 |  |
| 18 | `pask` | 매도호가 | string | Y | 12 |  |
| 19 | `pbid` | 매수호가 | string | Y | 12 |  |
| 20 | `tvol` | 거래량 | string | Y | 14 |  |
| 21 | `n_tvol` | 평균거래량 | string | Y | 14 |  |
| 22 | `n_rate` | 증가율 | string | Y | 12 |  |
| 23 | `rank` | 순위 | string | Y | 6 |  |
| 24 | `ename` | 영문종목명 | string | Y | 48 |  |
| 25 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외주식 기간별권리조회

- **API ID**: 해외주식-052
- **실전 TR_ID**: CTRGT011R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/period-rights`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `모의투자 미지원`

<details><summary>개요</summary>

```text
해외주식 기간별권리조회 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7520] 기간별해외증권권리조회 화면을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

※ 확정여부가 '예정'으로 표시되는 경우는 권리정보가 변경될 수 있으니 참고자료로만 활용하시기 바랍니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTRGT011R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `RGHT_TYPE_CD` | 권리유형코드 | string | Y | 2 | '%%(전체), 01(유상), 02(무상), 03(배당), 11(합병), <br>14(액면분할), 15(액면병합), 17(감자), 54(WR청구),<br>61(원리금상환), 71(WR소멸), 74(배당옵션), 75(특별배당), 76(ISINCODE변경), 77(실권주청약)' |
| 1 | `INQR_DVSN_CD` | 조회구분코드 | string | Y | 2 | 02(현지기준일), 03(청약시작일), 04(청약종료일) |
| 2 | `INQR_STRT_DT` | 조회시작일자 | string | Y | 8 | 일자 ~ |
| 3 | `INQR_END_DT` | 조회종료일자 | string | Y | 8 | ~ 일자 |
| 4 | `PDNO` | 상품번호 | string | Y | 12 | 공백 |
| 5 | `PRDT_TYPE_CD` | 상품유형코드 | string | Y | 3 | 공백 |
| 6 | `CTX_AREA_NK50` | 연속조회키50 | string | Y | 50 | 공백 |
| 7 | `CTX_AREA_FK50` | 연속조회검색조건50 | string | Y | 50 | 공백 |

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
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `bass_dt` | 기준일자 | string | Y | 8 |  |
| 5 | `rght_type_cd` | 권리유형코드 | string | Y | 2 |  |
| 6 | `pdno` | 상품번호 | string | Y | 12 |  |
| 7 | `prdt_name` | 상품명 | string | Y | 60 |  |
| 8 | `prdt_type_cd` | 상품유형코드 | string | Y | 3 |  |
| 9 | `std_pdno` | 표준상품번호 | string | Y | 12 |  |
| 10 | `acpl_bass_dt` | 현지기준일자 | string | Y | 8 |  |
| 11 | `sbsc_strt_dt` | 청약시작일자 | string | Y | 8 |  |
| 12 | `sbsc_end_dt` | 청약종료일자 | string | Y | 8 |  |
| 13 | `cash_alct_rt` | 현금배정비율 | string | Y | 191 |  |
| 14 | `stck_alct_rt` | 주식배정비율 | string | Y | 2012 |  |
| 15 | `crcy_cd` | 통화코드 | string | Y | 3 |  |
| 16 | `crcy_cd2` | 통화코드2 | string | Y | 3 |  |
| 17 | `crcy_cd3` | 통화코드3 | string | Y | 3 |  |
| 18 | `crcy_cd4` | 통화코드4 | string | Y | 3 |  |
| 19 | `alct_frcr_unpr` | 배정외화단가 | string | Y | 195 |  |
| 20 | `stkp_dvdn_frcr_amt2` | 주당배당외화금액2 | string | Y | 195 |  |
| 21 | `stkp_dvdn_frcr_amt3` | 주당배당외화금액3 | string | Y | 195 |  |
| 22 | `stkp_dvdn_frcr_amt4` | 주당배당외화금액4 | string | Y | 195 |  |
| 23 | `dfnt_yn` | 확정여부 | string | Y | 1 |  |

<details><summary>Request Example (Python)</summary>

```text
RGHT_TYPE_CD:%%
INQR_DVSN_CD:02
INQR_STRT_DT:20240417
INQR_END_DT:20240417
PDNO:
PRDT_TYPE_CD:
CTX_AREA_NK50:
CTX_AREA_FK50:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_nk50": "                                                  ",
    "ctx_area_fk50": "%%!^02!^20240417!^20240417!^!^                    ",
    "output": [
        {
            "bass_dt": "20240418",
            "rght_type_cd": "03",
            "pdno": "000661",
            "prdt_name": "[000661]CHANGCHUN HIGH-TECH INDUSTRY (GROUP",
            "prdt_type_cd": "552",
            "std_pdno": "CNE0000007J8",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "450.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "CNY",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "4.50000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "03",
            "pdno": "AIR",
            "prdt_name": "AIRBUS GROUP NV",
            "prdt_type_cd": "542",
            "std_pdno": "NL0000235190",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "180.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "EUR",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "1.80000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "03",
            "pdno": "GYLD",
            "prdt_name": "ARROW ETF TR ARROW DOW JONES GLOBAL YIELD ETF",
            "prdt_type_cd": "513",
            "std_pdno": "US04273H1041",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "12.6000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.12600",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "03",
            "pdno": "NORAM",
            "prdt_name": "NORAM DRILLING",
            "prdt_type_cd": "525",
            "std_pdno": "NO0010360019",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "43.8000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "NOK",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.43800",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "15",
            "pdno": "BENF",
            "prdt_name": "BENEFICIENT",
            "prdt_type_cd": "512",
            "std_pdno": "US08178Q3092",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "1.250000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "15",
            "pdno": "NCNA",
            "prdt_name": "NUCANA PLC SPON ADR EACH REP 25 ORD SHS(POST SPLIT)",
            "prdt_type_cd": "512",
            "std_pdno": "US67022C2052",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "4.000000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240415",
            "rght_type_cd": "54",
            "pdno": "WWRSF",
            "prdt_name": "RIVERNORTH CAPITAL AND INCM FD INC",
            "prdt_type_cd": "513",
            "std_pdno": "USX589013472",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "20240415",
            "sbsc_end_dt": "20240417",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "33.333340000000",
            "crcy_cd": "USD",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "15.28000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240411",
            "rght_type_cd": "74",
            "pdno": "FTF",
            "prdt_name": "FRANKLIN LIMITED DURATION INCOME TR",
            "prdt_type_cd": "529",
            "std_pdno": "US35472T1016",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "20240411",
            "sbsc_end_dt": "20240416",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "USD",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240411",
            "rght_type_cd": "74",
            "pdno": "TEI",
            "prdt_name": "TEMPLETON EMERGING MARKETS INC FD",
            "prdt_type_cd": "513",
            "std_pdno": "US8801921094",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "20240411",
            "sbsc_end_dt": "20240416",
            "cash_alct_rt": "0.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "USD",
            "crcy_cd2": "USD",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "0.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        },
        {
            "bass_dt": "20240418",
            "rght_type_cd": "75",
            "pdno": "AIR",
            "prdt_name": "AIRBUS GROUP NV",
            "prdt_type_cd": "542",
            "std_pdno": "NL0000235190",
            "acpl_bass_dt": "20240417",
            "sbsc_strt_dt": "",
            "sbsc_end_dt": "",
            "cash_alct_rt": "100.0000000000",
            "stck_alct_rt": "0.000000000000",
            "crcy_cd": "EUR",
            "crcy_cd2": "",
            "crcy_cd3": "",
            "crcy_cd4": "",
            "alct_frcr_unpr": "1.00000",
            "stkp_dvdn_frcr_amt2": "0.00000",
            "stkp_dvdn_frcr_amt3": "0.00000",
            "stkp_dvdn_frcr_amt4": "0.00000",
            "dfnt_yn": "Y"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>



### 해외주식 가격급등락

- **API ID**: 해외주식-038
- **실전 TR_ID**: HHDFS76260000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/price-fluct`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 가격급등락 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7626] 가격급등락 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76260000 |
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
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `GUBN` | 급등/급락구분 | string | Y | 1 | 0(급락), 1(급등) |
| 4 | `MINX` | N분전콤보값 | string | Y | 1 | N분전 : 0(1분전), 1(2분전), 2(3분전), 3(5분전), 4(10분전), 5(15분전), 6(20분전), 7(30분전), 8(60분전), 9(120분전) |
| 5 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

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
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태 | string | Y | 20 |  |
| 6 | `nrec` | RecordCount | string | Y | 4 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 9 | `excd` | 거래소코드 | string | Y | 4 |  |
| 10 | `symb` | 종목코드 | string | Y | 16 |  |
| 11 | `knam` | 종목명 | string | Y | 48 |  |
| 12 | `last` | 현재가 | string | Y | 12 |  |
| 13 | `sign` | 기호 | string | Y | 1 |  |
| 14 | `diff` | 대비 | string | Y | 12 |  |
| 15 | `rate` | 등락율 | string | Y | 12 |  |
| 16 | `tvol` | 거래량 | string | Y | 14 |  |
| 17 | `pask` | 매도호가 | string | Y | 12 |  |
| 18 | `pbid` | 매수호가 | string | Y | 12 |  |
| 19 | `n_base` | 기준가격 | string | Y | 12 |  |
| 20 | `n_diff` | 기준가격대비 | string | Y | 12 |  |
| 21 | `n_rate` | 기준가격대비율 | string | Y | 12 |  |
| 22 | `enam` | 영문종목명 | string | Y | 48 |  |
| 23 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외주식 거래대금순위

- **API ID**: 해외주식-044
- **실전 TR_ID**: HHDFS76320010
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/trade-pbmn`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 거래대금순위 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7632] 거래대금순위 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76320010 |
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
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `NDAY` | N일자값 | string | Y | 1 | N일전 : 0(당일), 1(2일), 2(3일), 3(5일), 4(10일), 5(20일전), 6(30일), 7(60일), 8(120일), 9(1년) |
| 4 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |
| 5 | `PRC1` | 현재가 필터범위 1 | string | Y | 12 | 가격 ~ |
| 6 | `PRC2` | 현재가 필터범위 2 | string | Y | 12 | ~ 가격 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (26)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태정보 | string | Y | 20 |  |
| 6 | `crec` | 현재조회종목수 | string | Y | 6 |  |
| 7 | `trec` | 전체조회종목수 | string | Y | 6 |  |
| 8 | `nrec` | RecordCount | string | Y | 4 |  |
| 9 | `output2` | 응답상세 | object array | Y |  | array |
| 10 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 11 | `excd` | 거래소코드 | string | Y | 4 |  |
| 12 | `symb` | 종목코드 | string | Y | 1 |  |
| 13 | `name` | 종목명 | string | Y | 48 |  |
| 14 | `last` | 현재가 | string | Y | 16 |  |
| 15 | `sign` | 기호 | string | Y | 1 |  |
| 16 | `diff` | 대비 | string | Y | 12 |  |
| 17 | `rate` | 등락율 | string | Y | 12 |  |
| 18 | `pask` | 매도호가 | string | Y | 12 |  |
| 19 | `pbid` | 매수호가 | string | Y | 12 |  |
| 20 | `tvol` | 거래량 | string | Y | 14 |  |
| 21 | `tamt` | 거래대금 | string | Y | 14 |  |
| 22 | `a_tamt` | 평균거래대금 | string | Y | 14 |  |
| 23 | `rank` | 순위 | string | Y | 6 |  |
| 24 | `ename` | 영문종목명 | string | Y | 48 |  |
| 25 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외주식 거래량급증

- **API ID**: 해외주식-039
- **실전 TR_ID**: HHDFS76270000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/volume-surge`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 거래량급증 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7627] 거래대금순위 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76270000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `MINX` | N분전콤보값 | string | Y | 1 | N분전 : 0(1분전), 1(2분전), 2(3분전), 3(5분전), 4(10분전), 5(15분전), 6(20분전), 7(30분전), 8(60분전), 9(120분전) |
| 4 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

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
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태 | string | Y | 20 |  |
| 6 | `nrec` | RecordCount | string | Y | 4 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 9 | `excd` | 거래소코드 | string | Y | 4 |  |
| 10 | `symb` | 종목코드 | string | Y | 16 |  |
| 11 | `knam` | 종목명 | string | Y | 48 |  |
| 12 | `last` | 현재가 | string | Y | 12 |  |
| 13 | `sign` | 기호 | string | Y | 1 |  |
| 14 | `diff` | 대비 | string | Y | 12 |  |
| 15 | `rate` | 등락율 | string | Y | 12 |  |
| 16 | `tvol` | 거래량 | string | Y | 14 |  |
| 17 | `pask` | 매도호가 | string | Y | 12 |  |
| 18 | `pbid` | 매수호가 | string | Y | 12 |  |
| 19 | `n_tvol` | 기준거래량 | string | Y | 14 |  |
| 20 | `n_diff` | 증가량 | string | Y | 12 |  |
| 21 | `n_rate` | 증가율 | string | Y | 12 |  |
| 22 | `enam` | 영문종목명 | string | Y | 48 |  |
| 23 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외주식 매수체결강도상위

- **API ID**: 해외주식-040
- **실전 TR_ID**: HHDFS76280000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/volume-power`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 매수체결강도상위 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7628] 매수체결강도상위 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76280000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `NDAY` | N일자값 | string | Y | 1 | N분전 : 0(1분전), 1(2분전), 2(3분전), 3(5분전), 4(10분전), 5(15분전), 6(20분전), 7(30분전), 8(60분전), 9(120분전) |
| 4 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (23)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태 | string | Y | 20 |  |
| 6 | `nrec` | RecordCount | string | Y | 4 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 9 | `excd` | 거래소코드 | string | Y | 4 |  |
| 10 | `symb` | 종목코드 | string | Y | 16 |  |
| 11 | `knam` | 종목명 | string | Y | 48 |  |
| 12 | `last` | 현재가 | string | Y | 12 |  |
| 13 | `sign` | 기호 | string | Y | 1 |  |
| 14 | `diff` | 대비 | string | Y | 12 |  |
| 15 | `rate` | 등락율 | string | Y | 12 |  |
| 16 | `tvol` | 거래량 | string | Y | 14 |  |
| 17 | `pask` | 매도호가 | string | Y | 12 |  |
| 18 | `pbid` | 매수호가 | string | Y | 12 |  |
| 19 | `tpow` | 당일체결강도 | string | Y | 10 |  |
| 20 | `powx` | 체결강도 | string | Y | 10 |  |
| 21 | `enam` | 영문종목명 | string | Y | 48 |  |
| 22 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외주식 거래회전율순위

- **API ID**: 해외주식-046
- **실전 TR_ID**: HHDFS76340000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/trade-turnover`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 거래회전율순위 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7634] 거래회전율순위 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76340000 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (5)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `NDAY` | N일자값 | string | Y | 1 | N일전 : 0(당일), 1(2일), 2(3일), 3(5일), 4(10일), 5(20일전), 6(30일), 7(60일), 8(120일), 9(1년) |
| 4 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (27)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태정보 | string | Y | 20 |  |
| 6 | `crec` | 현재조회종목수 | string | Y | 6 |  |
| 7 | `trec` | 전체조회종목수 | string | Y | 6 |  |
| 8 | `nrec` | RecordCount | string | Y | 4 |  |
| 9 | `output2` | 응답상세 | object array | Y |  | array |
| 10 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 11 | `excd` | 거래소코드 | string | Y | 4 |  |
| 12 | `symb` | 종목코드 | string | Y | 1 |  |
| 13 | `name` | 종목명 | string | Y | 48 |  |
| 14 | `last` | 현재가 | string | Y | 16 |  |
| 15 | `sign` | 기호 | string | Y | 1 |  |
| 16 | `diff` | 대비 | string | Y | 12 |  |
| 17 | `rate` | 등락율 | string | Y | 12 |  |
| 18 | `tvol` | 거래량 | string | Y | 14 |  |
| 19 | `pask` | 매도호가 | string | Y | 12 |  |
| 20 | `pbid` | 매수호가 | string | Y | 12 |  |
| 21 | `n_tvol` | 평균거래량 | string | Y | 14 |  |
| 22 | `shar` | 상장주식수 | string | Y | 16 |  |
| 23 | `tover` | 회전율 | string | Y | 10 |  |
| 24 | `rank` | 순위 | string | Y | 6 |  |
| 25 | `ename` | 영문종목명 | string | Y | 48 |  |
| 26 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외뉴스종합(제목)

- **API ID**: 해외주식-053
- **실전 TR_ID**: HHPSTH60100C1
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/news-title`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외뉴스종합(제목) API입니다.
한국투자 HTS(eFriend Plus) &gt; [7702] 해외뉴스종합 화면의 "우측 상단 뉴스목록" 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHPSTH60100C1 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (8)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `INFO_GB` | 뉴스구분 | string | Y | 1 | 전체: 공백 |
| 1 | `CLASS_CD` | 중분류 | string | Y | 2 | 전체: 공백 |
| 2 | `NATION_CD` | 국가코드 | string | Y | 2 | 전체: 공백<br>CN(중국), HK(홍콩), US(미국) |
| 3 | `EXCHANGE_CD` | 거래소코드 | string | Y | 3 | 전체: 공백 |
| 4 | `SYMB` | 종목코드 | string | Y | 20 | 전체: 공백 |
| 5 | `DATA_DT` | 조회일자 | string | Y | 8 | 전체: 공백<br>특정일자(YYYYMMDD) ex. 20240502 |
| 6 | `DATA_TM` | 조회시간 | string | Y | 6 | 전체: 공백<br>전체: 공백<br>특정시간(HHMMSS) ex. 093500 |
| 7 | `CTS` | 다음키 | string | Y | 35 | 공백 입력 |

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
| 3 | `outblock1` | 응답상세 | object array | Y |  | array |
| 4 | `info_gb` | 뉴스구분 | string | Y | 1 |  |
| 5 | `news_key` | 뉴스키 | string | Y | 20 |  |
| 6 | `data_dt` | 조회일자 | string | Y | 8 |  |
| 7 | `data_tm` | 조회시간 | string | Y | 6 |  |
| 8 | `class_cd` | 중분류 | string | Y | 2 |  |
| 9 | `class_name` | 중분류명 | string | Y | 20 |  |
| 10 | `source` | 자료원 | string | Y | 20 |  |
| 11 | `nation_cd` | 국가코드 | string | Y | 2 |  |
| 12 | `exchange_cd` | 거래소코드 | string | Y | 3 |  |
| 13 | `symb` | 종목코드 | string | Y | 20 |  |
| 14 | `symb_name` | 종목명 | string | Y | 48 |  |
| 15 | `title` | 제목 | string | Y | 128 |  |

<details><summary>Request Example (Python)</summary>

```text
INFO_GB:
CLASS_CD:
NATION_CD:
EXCHANGE_CD:
SYMB:
DATA_DT:
DATA_TM:
CTS:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "outblock1": [
        {
            "info_gb": "t",
            "news_key": "ICH709214",
            "data_dt": "20240503",
            "data_tm": "145447",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "톰 리 “단기 내 금리인하 가능”"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709213",
            "data_dt": "20240503",
            "data_tm": "144451",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "美 연준, 7월 금리인하 예상 GS 외"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709212",
            "data_dt": "20240503",
            "data_tm": "144313",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NAS",
            "symb": "NFLX",
            "symb_name": "넷플릭스",
            "title": "넷플릭스, 광고 전망 낙관 제프리스"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709215",
            "data_dt": "20240503",
            "data_tm": "143706",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "美 4월 비농업부문 고용자 수 +24.0만 명 추정 아데코"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709208",
            "data_dt": "20240503",
            "data_tm": "142518",
            "class_cd": "03",
            "class_name": "전략/산업",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "美 모기지 금리, 5주 연속 상승"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709207",
            "data_dt": "20240503",
            "data_tm": "141851",
            "class_cd": "02",
            "class_name": "정책",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "",
            "symb": "",
            "symb_name": "",
            "title": "금리, 현재 정점에 있을 확률 높아 펀드스트랫"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709206",
            "data_dt": "20240503",
            "data_tm": "140506",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NYS",
            "symb": "FSLY",
            "symb_name": "패스틀리",
            "title": "패스틀리, 단기 악재 직면 - BofA"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709205",
            "data_dt": "20240503",
            "data_tm": "135416",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NYS",
            "symb": "TJX",
            "symb_name": "TJX",
            "title": "TJX, 기존 소매점 위협 중 - UBS"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709204",
            "data_dt": "20240503",
            "data_tm": "134647",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NAS",
            "symb": "TTD",
            "symb_name": "트레이드 데스크",
            "title": "트레이드 데스크, 광고시장 현대화로 수혜 가능 - 제프리스"
        },
        {
            "info_gb": "t",
            "news_key": "ICH709203",
            "data_dt": "20240503",
            "data_tm": "133734",
            "class_cd": "05",
            "class_name": "종목리포트",
            "source": "연합미국",
            "nation_cd": "US",
            "exchange_cd": "NYS",
            "symb": "MGM",
            "symb_name": "MGM 리조츠 인터내셔널",
            "title": "MGM 리조트, 매출 증가세 가속 중 - 서스퀘하나"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 당사 해외주식담보대출 가능 종목

- **API ID**: 해외주식-051
- **실전 TR_ID**: CTLN4050R
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/colable-by-company`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
당사 해외주식담보대출 가능 종목 API입니다.
한국투자 HTS(eFriend Plus) &gt; [0497] 당사 해외주식담보대출 가능 종목 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

한 번의 호출에 20건까지 조회가 가능하며 다음조회가 불가하기에, PDNO에 데이터 확인하고자 하는 종목코드를 입력하여 단건조회용으로 사용하시기 바랍니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | CTLN4050R |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (12)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `PDNO` | 상품번호 | string | Y | 12 | ex)AMD |
| 1 | `PRDT_TYPE_CD` | 상품유형코드 | string | Y | 3 | 공백 |
| 2 | `INQR_STRT_DT` | 조회시작일자 | string | Y | 8 | 공백 |
| 3 | `INQR_END_DT` | 조회종료일자 | string | Y | 8 | 공백 |
| 4 | `INQR_DVSN` | 조회구분 | string | Y | 2 | 공백 |
| 5 | `NATN_CD` | 국가코드 | string | Y | 3 | 840(미국), 344(홍콩), 156(중국) |
| 6 | `INQR_SQN_DVSN` | 조회순서구분 | string | Y | 2 | 01(이름순), 02(코드순) |
| 7 | `RT_DVSN_CD` | 비율구분코드 | string | Y | 2 | 공백 |
| 8 | `RT` | 비율 | string | Y | 238 | 공백 |
| 9 | `LOAN_PSBL_YN` | 대출가능여부 | string | Y | 1 | 공백 |
| 10 | `CTX_AREA_FK100` | 연속조회검색조건100 | string | Y | 100 | 공백 |
| 11 | `CTX_AREA_NK100` | 연속조회키100 | string | Y | 100 | 공백 |

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
| 3 | `output1` | 응답상세 | array | Y |  |  |
| 4 | `pdno` | 상품번호 | string | Y | 12 |  |
| 5 | `ovrs_item_name` | 해외종목명 | string | Y | 60 |  |
| 6 | `loan_rt` | 대출비율 | string | Y | 238 |  |
| 7 | `mgge_mntn_rt` | 담보유지비율 | string | Y | 238 |  |
| 8 | `mgge_ensu_rt` | 담보확보비율 | string | Y | 238 |  |
| 9 | `loan_exec_psbl_yn` | 대출실행가능여부 | string | Y | 1 |  |
| 10 | `stff_name` | 직원명 | string | Y | 60 |  |
| 11 | `erlm_dt` | 등록일자 | string | Y | 8 |  |
| 12 | `tr_mket_name` | 거래시장명 | string | Y | 60 |  |
| 13 | `crcy_cd` | 통화코드 | string | Y | 3 |  |
| 14 | `natn_kor_name` | 국가한글명 | string | Y | 60 |  |
| 15 | `ovrs_excg_cd` | 해외거래소코드 | string | Y | 4 |  |
| 16 | `output2` | 응답상세 | object | Y |  | array |
| 17 | `loan_psbl_item_num` | 대출가능종목수 | string | Y | 20 |  |

<details><summary>Request Example (Python)</summary>

```text
PDNO:AMD
PRDT_TYPE_CD:
INQR_STRT_DT:
INQR_END_DT:
INQR_DVSN:
NATN_CD:840
INQR_SQN_DVSN:02
RT_DVSN_CD:
RT:
LOAN_PSBL_YN:
CTX_AREA_FK100:
CTX_AREA_NK100:
```

</details>


<details><summary>Response Example</summary>

```json
{
    "ctx_area_fk100": "AMD!^!^!^!^!^840!^02                                                                                ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "pdno": "AMD",
            "ovrs_item_name": "AMD",
            "loan_rt": "50.00000000",
            "mgge_mntn_rt": "170.00000000",
            "mgge_ensu_rt": "170.00000000",
            "loan_exec_psbl_yn": "Y",
            "stff_name": "109477.석재민",
            "erlm_dt": "20221230",
            "tr_mket_name": "나스닥",
            "crcy_cd": "USD",
            "natn_kor_name": "미국",
            "ovrs_excg_cd": "NASD"
        }
    ],
    "output2": {
        "loan_psbl_item_num": "403"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
}
```

</details>



### 해외주식 시가총액순위

- **API ID**: 해외주식-047
- **실전 TR_ID**: HHDFS76350100
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/market-cap`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 시가총액순위 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7635] 시가총액순위 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76350100 |
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
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 1 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

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
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태정보 | string | Y | 20 |  |
| 6 | `crec` | 현재조회종목수 | string | Y | 6 |  |
| 7 | `trec` | 전체조회종목수 | string | Y | 6 |  |
| 8 | `nrec` | RecordCount | string | Y | 4 |  |
| 9 | `output2` | 응답상세 | object array | Y |  | array |
| 10 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 11 | `excd` | 거래소코드 | string | Y | 4 |  |
| 12 | `symb` | 종목코드 | string | Y | 1 |  |
| 13 | `name` | 종목명 | string | Y | 48 |  |
| 14 | `last` | 현재가 | string | Y | 16 |  |
| 15 | `sign` | 기호 | string | Y | 1 |  |
| 16 | `diff` | 대비 | string | Y | 12 |  |
| 17 | `rate` | 등락율 | string | Y | 12 |  |
| 18 | `tvol` | 거래량 | string | Y | 14 |  |
| 19 | `shar` | 상장주식수 | string | Y | 16 |  |
| 20 | `tomv` | 시가총액 | string | Y | 16 |  |
| 21 | `grav` | 비중 | string | Y | 10 |  |
| 22 | `rank` | 순위 | string | Y | 6 |  |
| 23 | `ename` | 영문종목명 | string | Y | 48 |  |
| 24 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외속보(제목)

- **API ID**: 해외주식-055
- **실전 TR_ID**: FHKST01011801
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/brknews-title`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외속보(제목) API입니다.
한국투자 HTS(eFriend Plus) &gt; [7704] 해외속보 화면 의 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

최대 100건까지 조회 가능합니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | FHKST01011801 |
| 6 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 7 | `custtype` | 고객 타입 | string | Y | 1 | B : 법인 <br>P : 개인 |
| 8 | `seq_no` | 일련번호 | string | N | 2 | [법인 필수] 001 |
| 9 | `mac_address` | 맥주소 | string | N | 12 | 법인고객 혹은 개인고객의 Mac address 값 |
| 10 | `phone_number` | 핸드폰번호 | string | N | 12 | [법인 필수] 제휴사APP을 사용하는 경우 사용자(회원) 핸드폰번호 <br>ex) 01011112222 (하이픈 등 구분값 제거) |
| 11 | `ip_addr` | 접속 단말 공인 IP | string | N | 12 | [법인 필수] 사용자(회원)의 IP Address |
| 12 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Request Query Parameter (9)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `FID_NEWS_OFER_ENTP_CODE` | 뉴스제공업체코드 | string | Y | 40 | 뉴스제공업체구분=>0:전체조회 |
| 1 | `FID_COND_MRKT_CLS_CODE` | 조건시장구분코드 | string | Y | 6 | 공백 |
| 2 | `FID_INPUT_ISCD` | 입력종목코드 | string | Y | 12 | 공백 |
| 3 | `FID_TITL_CNTT` | 제목내용 | string | Y | 132 | 공백 |
| 4 | `FID_INPUT_DATE_1` | 입력날짜1 | string | Y | 10 | 공백 |
| 5 | `FID_INPUT_HOUR_1` | 입력시간1 | string | Y | 10 | 공백 |
| 6 | `FID_RANK_SORT_CLS_CODE` | 순위정렬구분코드 | string | Y | 2 | 공백 |
| 7 | `FID_INPUT_SRNO` | 입력일련번호 | string | Y | 20 | 공백 |
| 8 | `FID_COND_SCR_DIV_CODE` | 조건화면분류코드 | string | Y | 5 | 화면번호:11801 |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (31)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output` | 응답상세 | object array | Y |  | array |
| 4 | `cntt_usiq_srno` | 내용조회용일련번호 | string | Y | 20 |  |
| 5 | `news_ofer_entp_code` | 뉴스제공업체코드 | string | Y | 1 |  |
| 6 | `data_dt` | 작성일자 | string | Y | 8 |  |
| 7 | `data_tm` | 작성시간 | string | Y | 6 |  |
| 8 | `hts_pbnt_titl_cntt` | HTS공시제목내용 | string | Y | 400 |  |
| 9 | `news_lrdv_code` | 뉴스대구분 | string | Y | 8 |  |
| 10 | `dorg` | 자료원 | string | Y | 20 |  |
| 11 | `iscd1` | 종목코드1 | string | Y | 9 |  |
| 12 | `iscd2` | 종목코드2 | string | Y | 9 |  |
| 13 | `iscd3` | 종목코드3 | string | Y | 9 |  |
| 14 | `iscd4` | 종목코드4 | string | Y | 9 |  |
| 15 | `iscd5` | 종목코드5 | string | Y | 9 |  |
| 16 | `iscd6` | 종목코드6 | string | Y | 9 |  |
| 17 | `iscd7` | 종목코드7 | string | Y | 9 |  |
| 18 | `iscd8` | 종목코드8 | string | Y | 9 |  |
| 19 | `iscd9` | 종목코드9 | string | Y | 9 |  |
| 20 | `iscd10` | 종목코드10 | string | Y | 9 |  |
| 21 | `kor_isnm1` | 한글종목명1 | string | Y | 40 |  |
| 22 | `kor_isnm2` | 한글종목명2 | string | Y | 40 |  |
| 23 | `kor_isnm3` | 한글종목명3 | string | Y | 40 |  |
| 24 | `kor_isnm4` | 한글종목명4 | string | Y | 40 |  |
| 25 | `kor_isnm5` | 한글종목명5 | string | Y | 40 |  |
| 26 | `kor_isnm6` | 한글종목명6 | string | Y | 40 |  |
| 27 | `kor_isnm7` | 한글종목명7 | string | Y | 40 |  |
| 28 | `kor_isnm8` | 한글종목명8 | string | Y | 40 |  |
| 29 | `kor_isnm9` | 한글종목명9 | string | Y | 40 |  |
| 30 | `kor_isnm10` | 한글종목명10 | string | Y | 40 |  |

<details><summary>Request Example (Python)</summary>

```text
FID_NEWS_OFER_ENTP_CODE:0
FID_COND_MRKT_CLS_CODE:00
FID_INPUT_ISCD:
FID_TITL_CNTT:
FID_INPUT_DATE_1:
FID_INPUT_HOUR_1:
FID_RANK_SORT_CLS_CODE:
FID_INPUT_SRNO:
FID_COND_SCR_DIV_CODE:11801
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output": [
        {
            "cntt_usiq_srno": "2024052817340622954",
            "news_ofer_entp_code": "U",
            "data_dt": "20240528",
            "data_tm": "173406",
            "hts_pbnt_titl_cntt": "“시진핑, 기업인들 만나 신에너지 분야 과잉투자 경고”",
            "news_lrdv_code": "38",
            "dorg": "서울경제",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817332725534",
            "news_ofer_entp_code": "6",
            "data_dt": "20240528",
            "data_tm": "173327",
            "hts_pbnt_titl_cntt": "군부대 찾은 라이칭더, 中포위훈련 언급하며 \"모두 잘 대응\"",
            "news_lrdv_code": "11",
            "dorg": "연합뉴스",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817332721133",
            "news_ofer_entp_code": "6",
            "data_dt": "20240528",
            "data_tm": "173327",
            "hts_pbnt_titl_cntt": "적십자 \"기후변화로 '극단적 더위' 일수 1년 새 26일 증가\"",
            "news_lrdv_code": "11",
            "dorg": "연합뉴스",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817312094823",
            "news_ofer_entp_code": "6",
            "data_dt": "20240528",
            "data_tm": "173120",
            "hts_pbnt_titl_cntt": "미국제재 우려했나…중국 하이크비전, 러시아 사업 중단설",
            "news_lrdv_code": "11",
            "dorg": "연합뉴스",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817304250020",
            "news_ofer_entp_code": "8",
            "data_dt": "20240528",
            "data_tm": "173042",
            "hts_pbnt_titl_cntt": "[유럽개장]장 초반 혼조세…獨 0.25%↑",
            "news_lrdv_code": "10",
            "dorg": "아시아 경제",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },
        {
            "cntt_usiq_srno": "2024052817264510344",
            "news_ofer_entp_code": "A",
            "data_dt": "20240528",
            "data_tm": "172645",
            "hts_pbnt_titl_cntt": "122m 협곡 아래로 떨어졌는데 멀쩡하디니…기적 일어난 美 10대",
            "news_lrdv_code": "10",
            "dorg": "매일경제",
            "iscd1": "",
            "iscd2": "",
            "iscd3": "",
            "iscd4": "",
            "iscd5": "",
            "iscd6": "",
            "iscd7": "",
            "iscd8": "",
            "iscd9": "",
            "iscd10": "",
            "kor_isnm1": " ",
            "kor_isnm2": "",
            "kor_isnm3": "",
            "kor_isnm4": "",
            "kor_isnm5": "",
            "kor_isnm6": "",
            "kor_isnm7": "",
            "kor_isnm8": "",
            "kor_isnm9": "",
            "kor_isnm10": ""
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 해외주식 권리종합

- **API ID**: 해외주식-050
- **실전 TR_ID**: HHDFS78330900
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-price/v1/quotations/rights-by-ice`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 권리종합 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7833] 해외주식 권리(ICE제공) 화면의 "전체" 탭 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.

※ 조회기간 기준일 입력시 참고 - 상환: 상환일자, 조기상환: 조기상환일자, 티커변경: 적용일, 그 외: 발표일
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS78330900 |
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
| 0 | `NCOD` | 국가코드 | string | Y | 2 | CN:중국 HK:홍콩 US:미국 JP:일본 VN:베트남 |
| 1 | `SYMB` | 심볼 | string | Y | 20 | 종목코드 |
| 2 | `ST_YMD` | 일자 시작일 | string | Y | 8 | 미입력 시, 오늘-3개월<br>기간지정 시, 종료일 입력(ex. 20240514)<br>※ 조회기간 기준일 입력시 참고<br>- 상환: 상환일자, 조기상환: 조기상환일자, 티커변경: 적용일, 그 외: 발표일 |
| 3 | `ED_YMD` | 일자 종료일 | string | Y | 8 | 미입력 시, 오늘+3개월<br>기간지정 시, 종료일 입력(ex. 20240514)<br>※ 조회기간 기준일 입력시 참고<br>- 상환: 상환일자, 조기상환: 조기상환일자, 티커변경: 적용일, 그 외: 발표일 |

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
| 3 | `output1` | 응답상세 | object array | Y |  | array |
| 4 | `anno_dt` | ICE공시일 | string | Y | 8 |  |
| 5 | `ca_title` | 권리유형 | string | Y | 12 |  |
| 6 | `div_lock_dt` | 배당락일 | string | Y | 8 |  |
| 7 | `pay_dt` | 지급일 | string | Y | 8 |  |
| 8 | `record_dt` | 기준일 | string | Y | 8 |  |
| 9 | `validity_dt` | 효력일자 | string | Y | 8 |  |
| 10 | `local_end_dt` | 현지지시마감일 | string | Y | 8 |  |
| 11 | `lock_dt` | 권리락일 | string | Y | 8 |  |
| 12 | `delist_dt` | 상장폐지일 | string | Y | 8 |  |
| 13 | `redempt_dt` | 상환일자 | string | Y | 8 |  |
| 14 | `early_redempt_dt` | 조기상환일자 | string | Y | 8 |  |
| 15 | `effective_dt` | 적용일 | string | Y | 8 |  |

<details><summary>Request Example (Python)</summary>

```text
NCOD:US
SYMB:MAIN
ST_YMD:20240214
ED_YMD:20240514
```

</details>


<details><summary>Response Example</summary>

```json
{
    "output1": [
        {
            "anno_dt": "20240221",
            "ca_title": "현금배당",
            "div_lock_dt": "20240607",
            "pay_dt": "20240614",
            "record_dt": "20240607",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240221",
            "ca_title": "현금배당",
            "div_lock_dt": "20240405",
            "pay_dt": "20240415",
            "record_dt": "20240408",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240221",
            "ca_title": "현금배당",
            "div_lock_dt": "20240507",
            "pay_dt": "20240515",
            "record_dt": "20240508",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240507",
            "ca_title": "현금배당",
            "div_lock_dt": "20240808",
            "pay_dt": "20240815",
            "record_dt": "20240808",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240507",
            "ca_title": "현금배당",
            "div_lock_dt": "20240708",
            "pay_dt": "20240715",
            "record_dt": "20240708",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        },
        {
            "anno_dt": "20240507",
            "ca_title": "현금배당",
            "div_lock_dt": "20240906",
            "pay_dt": "20240913",
            "record_dt": "20240906",
            "validity_dt": "",
            "local_end_dt": "",
            "lock_dt": "",
            "delist_dt": "",
            "redempt_dt": "",
            "early_redempt_dt": "",
            "effective_dt": ""
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
}
```

</details>



### 해외주식 거래량순위

- **API ID**: 해외주식-043
- **실전 TR_ID**: HHDFS76310010
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/trade-vol`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 거래량순위 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7631] 거래대금순위 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76310010 |
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
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `NDAY` | N일자값 | string | Y | 1 | N일전 : 0(당일), 1(2일), 2(3일), 3(5일), 4(10일), 5(20일전), 6(30일), 7(60일), 8(120일), 9(1년) |
| 4 | `PRC1` | 현재가 필터범위 1 | string | Y | 12 | 가격 ~ |
| 5 | `PRC2` | 현재가 필터범위 2 | string | Y | 12 | ~ 가격 |
| 6 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (26)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태정보 | string | Y | 20 |  |
| 6 | `crec` | 현재조회종목수 | string | Y | 6 |  |
| 7 | `trec` | 전체조회종목수 | string | Y | 6 |  |
| 8 | `nrec` | RecordCount | string | Y | 4 |  |
| 9 | `output2` | 응답상세 | object array | Y |  | array |
| 10 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 11 | `excd` | 거래소코드 | string | Y | 4 |  |
| 12 | `symb` | 종목코드 | string | Y | 1 |  |
| 13 | `name` | 종목명 | string | Y | 48 |  |
| 14 | `last` | 현재가 | string | Y | 16 |  |
| 15 | `sign` | 기호 | string | Y | 1 |  |
| 16 | `diff` | 대비 | string | Y | 12 |  |
| 17 | `rate` | 등락율 | string | Y | 12 |  |
| 18 | `pask` | 매도호가 | string | Y | 12 |  |
| 19 | `pbid` | 매수호가 | string | Y | 12 |  |
| 20 | `tvol` | 거래량 | string | Y | 14 |  |
| 21 | `tamt` | 거래대금 | string | Y | 14 |  |
| 22 | `a_tvol` | 평균거래량 | string | Y | 14 |  |
| 23 | `rank` | 순위 | string | Y | 6 |  |
| 24 | `ename` | 영문종목명 | string | Y | 48 |  |
| 25 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외주식 신고_신저가

- **API ID**: 해외주식-042
- **실전 TR_ID**: HHDFS76300000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/new-highlow`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
"해외주식 신고/신저가 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7630] 신고/신저가 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다."
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76300000 |
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
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `GUBN` | 신고/신저 구분 | string | Y | 1 | 신고(1) 신저(0) |
| 4 | `GUBN2` | 일시돌파/돌파 구분 | string | Y | 1 | 일시돌파(0) 돌파유지(1) |
| 5 | `NDAY` | N일자값 | string | Y | 1 | N일전 : 0(5일), 1(10일), 2(20일), 3(30일), 4(60일), 5(120일전), 6(52주), 7(1년) |
| 6 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

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
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태정보 | string | Y | 20 |  |
| 6 | `nrec` | RecordCount | string | Y | 4 |  |
| 7 | `output2` | 응답상세 | object array | Y |  | array |
| 8 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 9 | `excd` | 거래소코드 | string | Y | 4 |  |
| 10 | `symb` | 종목코드 | string | Y | 1 |  |
| 11 | `name` | 종목명 | string | Y | 48 |  |
| 12 | `last` | 현재가 | string | Y | 16 |  |
| 13 | `sign` | 기호 | string | Y | 1 |  |
| 14 | `diff` | 대비 | string | Y | 12 |  |
| 15 | `rate` | 등락율 | string | Y | 12 |  |
| 16 | `tvol` | 거래량 | string | Y | 14 |  |
| 17 | `pask` | 매도호가 | string | Y | 12 |  |
| 18 | `pbid` | 매수호가 | string | Y | 12 |  |
| 19 | `n_base` | 기준가 | string | Y | 12 |  |
| 20 | `n_diff` | 기준가대비 | string | Y | 12 |  |
| 21 | `n_rate` | 기준가대비율 | string | Y | 12 |  |
| 22 | `ename` | 영문종목명 | string | Y | 48 |  |
| 23 | `e_ordyn` | 매매가능 | string | Y | 2 |  |


### 해외주식 상승율_하락율

- **API ID**: 해외주식-041
- **실전 TR_ID**: HHDFS76290000
- **모의 TR_ID**: 모의투자 미지원
- **통신방식**: REST · **Method**: GET
- **URL**: `/uapi/overseas-stock/v1/ranking/updown-rate`
- **실전 Domain**: `https://openapi.koreainvestment.com:9443`
- **모의 Domain**: `미지원`

<details><summary>개요</summary>

```text
해외주식 상승율/하락율 API입니다.
한국투자 HTS(eFriend Plus) &gt; [7629] 상승율/하락율 화면 기능을 API로 개발한 사항으로, 해당 화면을 참고하시면 기능을 이해하기 쉽습니다.
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
| 5 | `tr_id` | 거래ID | string | Y | 13 | HHDFS76290000 |
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
| 0 | `KEYB` | NEXT KEY BUFF | string | Y | 8 | 공백 |
| 1 | `AUTH` | 사용자권한정보 | string | Y | 32 | 공백 |
| 2 | `EXCD` | 거래소코드 | string | Y | 4 | 'NYS : 뉴욕, NAS : 나스닥,  AMS : 아멕스 <br>HKS : 홍콩, SHS : 상해 , SZS : 심천<br>HSX : 호치민, HNX : 하노이<br>TSE : 도쿄 ' |
| 3 | `GUBN` | 상승율/하락율 구분 | string | Y | 1 | 0(하락율), 1(상승율) |
| 4 | `NDAY` | N일자값 | string | Y | 1 | N일전 : 0(당일), 1(2일), 2(3일), 3(5일), 4(10일), 5(20일전), 6(30일), 7(60일), 8(120일), 9(1년) |
| 5 | `VOL_RANG` | 거래량조건 | string | Y | 1 | 0(전체), 1(1백주이상), 2(1천주이상), 3(1만주이상), 4(10만주이상), 5(100만주이상), 6(1000만주이상) |

#### Response Header (4)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `content-type` | 컨텐츠타입 | string | Y | 40 | application/json; charset=utf-8 |
| 1 | `tr_id` | 거래ID | string | Y | 13 | 요청한 tr_id |
| 2 | `tr_cont` | 연속 거래 여부 | string | N | 1 | tr_cont를 이용한 다음조회 불가 API |
| 3 | `gt_uid` | Global UID | string | N | 32 | [법인 전용] 거래고유번호로 사용하므로 거래별로 UNIQUE해야 함 |

#### Response Body (27)

| # | Element | 한글명 | Type | Req | Len | Description |
|--:|---------|--------|------|:---:|----:|-------------|
| 0 | `rt_cd` | 성공 실패 여부 | string | Y | 1 |  |
| 1 | `msg_cd` | 응답코드 | string | Y | 8 |  |
| 2 | `msg1` | 응답메세지 | string | Y | 80 |  |
| 3 | `output1` | 응답상세 | object | Y |  |  |
| 4 | `zdiv` | 소수점자리수 | string | Y | 1 |  |
| 5 | `stat` | 거래상태정보 | string | Y | 20 |  |
| 6 | `crec` | 현재Count | string | Y | 6 |  |
| 7 | `trec` | 전체조회종목수 | string | Y | 6 |  |
| 8 | `nrec` | RecordCount | string | Y | 4 |  |
| 9 | `output2` | 응답상세 | object array | Y |  | array |
| 10 | `rsym` | 실시간조회심볼 | string | Y | 16 |  |
| 11 | `excd` | 거래소코드 | string | Y | 4 |  |
| 12 | `symb` | 종목코드 | string | Y | 1 |  |
| 13 | `name` | 종목명 | string | Y | 48 |  |
| 14 | `last` | 현재가 | string | Y | 16 |  |
| 15 | `sign` | 기호 | string | Y | 1 |  |
| 16 | `diff` | 대비 | string | Y | 12 |  |
| 17 | `rate` | 등락율 | string | Y | 12 |  |
| 18 | `tvol` | 거래량 | string | Y | 14 |  |
| 19 | `pask` | 매도호가 | string | Y | 12 |  |
| 20 | `pbid` | 매수호가 | string | Y | 12 |  |
| 21 | `n_base` | 기준가격 | string | Y | 12 |  |
| 22 | `n_diff` | 기준가격대비 | string | Y | 12 |  |
| 23 | `n_rate` | 기준가격대비율 | string | Y | 12 |  |
| 24 | `rank` | 순위 | string | Y | 6 |  |
| 25 | `ename` | 영문종목명 | string | Y | 48 |  |
| 26 | `e_ordyn` | 매매가능 | string | Y | 2 |  |

