# [국내주식] 종목정보 API 명세

> 원본: `한국투자증권_오픈API_전체문서_20260418_030007.xlsx`


## API 목록 (26개)

| # | 통신 | API명 | TR_ID | Method | URL | 사용 |
|---|------|------|-------|--------|-----|:---:|
| 85 | REST | 상품기본조회 | CTPF1604R | GET | `/uapi/domestic-stock/v1/quotations/search-info` |  |
| 86 | REST | 예탁원정보(상장정보일정) | HHKDB669107C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/list-info` |  |
| 87 | REST | 예탁원정보(공모주청약일정) | HHKDB669108C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/pub-offer` |  |
| 88 | REST | 국내주식 재무비율 | FHKST66430300 | GET | `/uapi/domestic-stock/v1/finance/financial-ratio` |  |
| 89 | REST | 예탁원정보(자본감소일정) | HHKDB669106C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/cap-dcrs` |  |
| 90 | REST | 예탁원정보(무상증자일정) | HHKDB669101C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/bonus-issue` |  |
| 91 | REST | 국내주식 증권사별 투자의견 | FHKST663400C0 | GET | `/uapi/domestic-stock/v1/quotations/invest-opbysec` |  |
| 92 | REST | 국내주식 당사 신용가능종목 | FHPST04770000 | GET | `/uapi/domestic-stock/v1/quotations/credit-by-company` |  |
| 93 | REST | 예탁원정보(주식매수청구일정) | HHKDB669103C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/purreq` |  |
| 94 | REST | 예탁원정보(액면교체일정) | HHKDB669105C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/rev-split` |  |
| 95 | REST | 예탁원정보(배당일정) | HHKDB669102C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/dividend` |  |
| 96 | REST | 국내주식 종목투자의견 | FHKST663300C0 | GET | `/uapi/domestic-stock/v1/quotations/invest-opinion` |  |
| 97 | REST | 국내주식 안정성비율 | FHKST66430600 | GET | `/uapi/domestic-stock/v1/finance/stability-ratio` |  |
| 98 | REST | 국내주식 수익성비율 | FHKST66430400 | GET | `/uapi/domestic-stock/v1/finance/profit-ratio` |  |
| 99 | REST | 예탁원정보(실권주일정) | HHKDB669109C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/forfeit` |  |
| 100 | REST | 예탁원정보(의무예치일정) | HHKDB669110C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/mand-deposit` |  |
| 101 | REST | 국내주식 손익계산서 | FHKST66430200 | GET | `/uapi/domestic-stock/v1/finance/income-statement` |  |
| 102 | REST | 당사 대주가능 종목 | CTSC2702R | GET | `/uapi/domestic-stock/v1/quotations/lendable-by-company` |  |
| 103 | REST | 주식기본조회 | CTPF1002R | GET | `/uapi/domestic-stock/v1/quotations/search-stock-info` |  |
| 104 | REST | 예탁원정보(유상증자일정) | HHKDB669100C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/paidin-capin` |  |
| 105 | REST | 예탁원정보(주주총회일정) | HHKDB669111C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/sharehld-meet` |  |
| 106 | REST | 국내주식 성장성비율 | FHKST66430800 | GET | `/uapi/domestic-stock/v1/finance/growth-ratio` |  |
| 107 | REST | 국내주식 대차대조표 | FHKST66430100 | GET | `/uapi/domestic-stock/v1/finance/balance-sheet` |  |
| 108 | REST | 예탁원정보(합병/분할일정) | HHKDB669104C0 | GET | `/uapi/domestic-stock/v1/ksdinfo/merger-split` |  |
| 109 | REST | 국내주식 종목추정실적 | HHKST668300C0 | GET | `/uapi/domestic-stock/v1/quotations/estimate-perform` |  |
| 110 | REST | 국내주식 기타주요비율 | FHKST66430500 | GET | `/uapi/domestic-stock/v1/finance/other-major-ratios` |  |

---

## 상세 명세

### 상품기본조회

- **TR_ID**: CTPF1604R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/search-info`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
	"PDNO":"AAPL",
	"PRDT_TYPE_CD":"512"
} |  |
| Response Example | {
    "output": {
        "pdno": "AAPL",
        "prdt_type_cd": "512",
        "prdt_name": "애플",
        "prdt_name120": "애플",
        "prdt_abrv_name": "애플",
        "prdt_eng_name": "APPLE INC",
        "prdt_eng_name120": "APPLE INC",
        "prdt_eng_abrv_name": "APPLE INC",
        "std_pdno": "US0378331005",
        "shtn_pdno": "AAPL",
        "prdt_sale_stat_cd": "",
        "prdt_risk_grad_cd": "",
        "prdt_clsf_cd": "101210",
        "prdt_clsf_name": "해외주식",
        "sale_strt_dt": "",
        "sale_end_dt": "",
        "wrap_asst_type_cd": "06",
        "ivst_prdt_type_cd": "1012",
        "ivst_prdt_type_cd_name": "해외주식",
        "frst_erlm_dt": ""
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0530",
    "msg1": "조회되었습니다                                                                  "
} |  |


### 예탁원정보(상장정보일정)

- **TR_ID**: HHKDB669107C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/list-info`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230301
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "list_dt": "20240326",
            "sht_cd": "034220",
            "isin_name": "LG디스플레이",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "   142184300",
            "tot_issue_stk_qty": "   500000000",
            "issue_price": "     9090"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "047560",
            "isin_name": "이스트소프트",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       13000",
            "tot_issue_stk_qty": "    11488232",
            "issue_price": "    15000"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "054180",
            "isin_name": "메디콕스",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "     2348484",
            "tot_issue_stk_qty": "    57151168",
            "issue_price": "      792"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "067310",
            "isin_name": "하나마이크론",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "        5500",
            "tot_issue_stk_qty": "    52136475",
            "issue_price": "     9275"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "146060",
            "isin_name": "율촌",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "     2391679",
            "tot_issue_stk_qty": "    24015595",
            "issue_price": "     1154"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "403490",
            "isin_name": "우듬지팜",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "      288000",
            "tot_issue_stk_qty": "    45212464",
            "issue_price": "     1000"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "455900",
            "isin_name": "엔젤로보틱스",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "     1648000",
            "tot_issue_stk_qty": "    14322012",
            "issue_price": "    20000"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "455900",
            "isin_name": "엔젤로보틱스",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "      692224",
            "tot_issue_stk_qty": "    14322012",
            "issue_price": "     2891"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "455900",
            "isin_name": "엔젤로보틱스",
            "stk_kind": "보통",
            "issue_type": "통일교체",
            "issue_stk_qty": "     8850720",
            "tot_issue_stk_qty": "    14322012",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240326",
            "sht_cd": "455900",
            "isin_name": "엔젤로보틱스",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "      161120",
            "tot_issue_stk_qty": "    14322012",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "007980",
            "isin_name": "태평양물산",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      162337",
            "tot_issue_stk_qty": "    51175130",
            "issue_price": "     1848"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "119650",
            "isin_name": "케이씨코트렐",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "    12733857",
            "tot_issue_stk_qty": "    63669287",
            "issue_price": "     1380"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "123840",
            "isin_name": "뉴온",
            "stk_kind": "보통",
            "issue_type": "합병",
            "issue_stk_qty": "   175537376",
            "tot_issue_stk_qty": "   277394122",
            "issue_price": "      100"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "151910",
            "isin_name": "에스비더블유생명과학",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "     1700680",
            "tot_issue_stk_qty": "   190071722",
            "issue_price": "      294"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "192230",
            "isin_name": "아리바이오",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       16500",
            "tot_issue_stk_qty": "    23632031",
            "issue_price": "     7500"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "192650",
            "isin_name": "드림텍",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       45000",
            "tot_issue_stk_qty": "    68852050",
            "issue_price": "     4518"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "222080",
            "isin_name": "씨아이에스",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      350261",
            "tot_issue_stk_qty": "    71440876",
            "issue_price": "     9707"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "373200",
            "isin_name": "하인크코리아",
            "stk_kind": "보통",
            "issue_type": "무상증자",
            "issue_stk_qty": "    56778657",
            "tot_issue_stk_qty": "    75705657",
            "issue_price": "      100"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "420570",
            "isin_name": "제이투케이바이오",
            "stk_kind": "보통",
            "issue_type": "통일교체",
            "issue_stk_qty": "     5059840",
            "tot_issue_stk_qty": "     5574115",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240325",
            "sht_cd": "420570",
            "isin_name": "제이투케이바이오",
            "stk_kind": "보통",
            "issue_type": "합병",
            "issue_stk_qty": "      514275",
            "tot_issue_stk_qty": "     5574115",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "005320",
            "isin_name": "국동",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      144300",
            "tot_issue_stk_qty": "    66750697",
            "issue_price": "      693"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "005810",
            "isin_name": "풍산홀딩스",
            "stk_kind": "보통",
            "issue_type": "무상증자",
            "issue_stk_qty": "     4668764",
            "tot_issue_stk_qty": "    14417292",
            "issue_price": "     5000"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "012510",
            "isin_name": "더존비즈온",
            "stk_kind": "보통",
            "issue_type": "합병",
            "issue_stk_qty": "     9423939",
            "tot_issue_stk_qty": "    30382784",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "024850",
            "isin_name": "에이치엘비이노베이션",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "     2681010",
            "tot_issue_stk_qty": "    72378055",
            "issue_price": "     1022"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "036180",
            "isin_name": "지더블유바이텍",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "    28911564",
            "tot_issue_stk_qty": "    91464525",
            "issue_price": "      588"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "038460",
            "isin_name": "바이오스마트",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      140230",
            "tot_issue_stk_qty": "    21437123",
            "issue_price": "     3209"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "060280",
            "isin_name": "큐렉소",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "        5000",
            "tot_issue_stk_qty": "    41084990",
            "issue_price": "     9510"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "066970",
            "isin_name": "엘앤에프",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "         168",
            "tot_issue_stk_qty": "    36255993",
            "issue_price": "    71430"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "115450",
            "isin_name": "에이치엘비테라퓨틱스",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       15351",
            "tot_issue_stk_qty": "    77948338",
            "issue_price": "     3619"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "197140",
            "isin_name": "디지캡",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       16000",
            "tot_issue_stk_qty": "     9596854",
            "issue_price": "     4098"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "199730",
            "isin_name": "바이오인프라",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       37500",
            "tot_issue_stk_qty": "     4834367",
            "issue_price": "     6667"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "314930",
            "isin_name": "바이오다인",
            "stk_kind": "보통",
            "issue_type": "무상증자",
            "issue_stk_qty": "    23581408",
            "tot_issue_stk_qty": "    29764103",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "403550",
            "isin_name": "쏘카",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "        3125",
            "tot_issue_stk_qty": "    32791402",
            "issue_price": "    16000"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "440110",
            "isin_name": "파두",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       34520",
            "tot_issue_stk_qty": "    49072322",
            "issue_price": "     7107"
        },
        {
            "list_dt": "20240322",
            "sht_cd": "441270",
            "isin_name": "파인엠텍",
            "stk_kind": "보통",
            "issue_type": "국내BW행사",
            "issue_stk_qty": "       42313",
            "tot_issue_stk_qty": "    36928663",
            "issue_price": "     7090"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "023960",
            "isin_name": "에쓰씨엔지니어링",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       23132",
            "tot_issue_stk_qty": "    32861366",
            "issue_price": "     1513"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "064520",
            "isin_name": "테크엘",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       50124",
            "tot_issue_stk_qty": "    22005961",
            "issue_price": "     3990"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "065650",
            "isin_name": "메디프론디비티",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "     3814835",
            "tot_issue_stk_qty": "    63153285",
            "issue_price": "      983"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "114840",
            "isin_name": "아이패밀리에스씨",
            "stk_kind": "보통",
            "issue_type": "무상증자",
            "issue_stk_qty": "     8600972",
            "tot_issue_stk_qty": "    17201944",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "199800",
            "isin_name": "툴젠",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "        2000",
            "tot_issue_stk_qty": "     7930258",
            "issue_price": "    32850"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "222080",
            "isin_name": "씨아이에스",
            "stk_kind": "보통",
            "issue_type": "합병",
            "issue_stk_qty": "      544552",
            "tot_issue_stk_qty": "    71440876",
            "issue_price": "    11116"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "245620",
            "isin_name": "이원다이애그노믹스",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "    17633408",
            "tot_issue_stk_qty": "   138493951",
            "issue_price": "      431"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "323410",
            "isin_name": "카카오뱅크",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "        5000",
            "tot_issue_stk_qty": "   476921137",
            "issue_price": "     5000"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "417010",
            "isin_name": "나노팀",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "      228000",
            "tot_issue_stk_qty": "    19724328",
            "issue_price": "     2631"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "437730",
            "isin_name": "삼현",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "     2033333",
            "tot_issue_stk_qty": "    10569189",
            "issue_price": "    30000"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "437730",
            "isin_name": "삼현",
            "stk_kind": "보통",
            "issue_type": "통일교체",
            "issue_stk_qty": "     8535856",
            "tot_issue_stk_qty": "    10569189",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240321",
            "sht_cd": "452300",
            "isin_name": "캡스톤파트너스",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       66250",
            "tot_issue_stk_qty": "    14060755",
            "issue_price": "      560"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "001210",
            "isin_name": "금호전기",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      260416",
            "tot_issue_stk_qty": "    38069709",
            "issue_price": "      768"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "011300",
            "isin_name": "성안",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "     1828152",
            "tot_issue_stk_qty": "    70551785",
            "issue_price": "     1094"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "031310",
            "isin_name": "아이즈비전",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       61859",
            "tot_issue_stk_qty": "    22843356",
            "issue_price": "     2829"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "067630",
            "isin_name": "에이치엘비생명과학",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       20990",
            "tot_issue_stk_qty": "   107122760",
            "issue_price": "    11434"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "170900",
            "isin_name": "동아에스티",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "          56",
            "tot_issue_stk_qty": "     8834970",
            "issue_price": "    72359"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "255220",
            "isin_name": "에스지이",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "     1692045",
            "tot_issue_stk_qty": "    61173984",
            "issue_price": "     1182"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "255220",
            "isin_name": "에스지이",
            "stk_kind": "보통",
            "issue_type": "국내BW행사",
            "issue_stk_qty": "       87918",
            "tot_issue_stk_qty": "    61173984",
            "issue_price": "     1125"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "321550",
            "isin_name": "티움바이오",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "      220001",
            "tot_issue_stk_qty": "    25662498",
            "issue_price": "     7500"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "355150",
            "isin_name": "코스텍시스",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      186000",
            "tot_issue_stk_qty": "     7706770",
            "issue_price": "     5000"
        },
        {
            "list_dt": "20240320",
            "sht_cd": "457190",
            "isin_name": "이수스페셜티케미컬",
            "stk_kind": "보통",
            "issue_type": "국내BW행사",
            "issue_stk_qty": "        1059",
            "tot_issue_stk_qty": "     5599832",
            "issue_price": "    18602"
        },
        {
            "list_dt": "20240319",
            "sht_cd": "007280",
            "isin_name": "한국특강",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      223713",
            "tot_issue_stk_qty": "    60813311",
            "issue_price": "     1788"
        },
        {
            "list_dt": "20240319",
            "sht_cd": "032980",
            "isin_name": "바이온",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      220264",
            "tot_issue_stk_qty": "    40517904",
            "issue_price": "      908"
        },
        {
            "list_dt": "20240319",
            "sht_cd": "064800",
            "isin_name": "젬백스링크",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       71123",
            "tot_issue_stk_qty": "   107875617",
            "issue_price": "     1406"
        },
        {
            "list_dt": "20240319",
            "sht_cd": "073570",
            "isin_name": "리튬포어스",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      218575",
            "tot_issue_stk_qty": "    35970918",
            "issue_price": "     4575"
        },
        {
            "list_dt": "20240319",
            "sht_cd": "082740",
            "isin_name": "한화엔진 주식회사",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "    11903148",
            "tot_issue_stk_qty": "    83447142",
            "issue_price": "     7520"
        },
        {
            "list_dt": "20240319",
            "sht_cd": "174900",
            "isin_name": "앱클론",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "      130707",
            "tot_issue_stk_qty": "    16423321",
            "issue_price": "    10079"
        },
        {
            "list_dt": "20240319",
            "sht_cd": "367000",
            "isin_name": "플래티어",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       21000",
            "tot_issue_stk_qty": "     8388207",
            "issue_price": "     4930"
        },
        {
            "list_dt": "20240318",
            "sht_cd": "000040",
            "isin_name": "케이알모터스",
            "stk_kind": "보통",
            "issue_type": "자본감소",
            "issue_stk_qty": "    29132868",
            "tot_issue_stk_qty": "    29132868",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240318",
            "sht_cd": "001720",
            "isin_name": "신영증권",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "        4950",
            "tot_issue_stk_qty": "     9434532",
            "issue_price": "    16233"
        },
        {
            "list_dt": "20240318",
            "sht_cd": "114630",
            "isin_name": "폴라리스우노",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      506512",
            "tot_issue_stk_qty": "    77757548",
            "issue_price": "      691"
        },
        {
            "list_dt": "20240318",
            "sht_cd": "123840",
            "isin_name": "뉴온",
            "stk_kind": "보통",
            "issue_type": "상호변경",
            "issue_stk_qty": "   277394122",
            "tot_issue_stk_qty": "   277394122",
            "issue_price": "      100"
        },
        {
            "list_dt": "20240318",
            "sht_cd": "214870",
            "isin_name": "뉴지랩파마",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "    13670000",
            "tot_issue_stk_qty": "    46796106",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240318",
            "sht_cd": "217330",
            "isin_name": "싸이토젠",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "        3286",
            "tot_issue_stk_qty": "    22423102",
            "issue_price": "    15290"
        },
        {
            "list_dt": "20240318",
            "sht_cd": "311390",
            "isin_name": "네오크레마",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "     2922552",
            "tot_issue_stk_qty": "    10979147",
            "issue_price": "     6159"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "035720",
            "isin_name": "카카오",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "      154263",
            "tot_issue_stk_qty": "   445243887",
            "issue_price": "    28199"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "047920",
            "isin_name": "에이치엘비제약",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       15000",
            "tot_issue_stk_qty": "    31746701",
            "issue_price": "     5608"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "059270",
            "isin_name": "해성티피씨",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       33000",
            "tot_issue_stk_qty": "    10797992",
            "issue_price": "     3000"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "067630",
            "isin_name": "에이치엘비생명과학",
            "stk_kind": "보통",
            "issue_type": "국내BW행사",
            "issue_stk_qty": "      738038",
            "tot_issue_stk_qty": "   107122760",
            "issue_price": "     8889"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "079160",
            "isin_name": "씨제이씨지브이",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "          50",
            "tot_issue_stk_qty": "   122432139",
            "issue_price": "    17745"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "082740",
            "isin_name": "한화엔진 주식회사",
            "stk_kind": "보통",
            "issue_type": "상호변경",
            "issue_stk_qty": "    71543994",
            "tot_issue_stk_qty": "    83447142",
            "issue_price": "     1000"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "117670",
            "isin_name": "알파홀딩스",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "     1645434",
            "tot_issue_stk_qty": "    39641629",
            "issue_price": "      942"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "139670",
            "isin_name": "키네마스터",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "       22899",
            "tot_issue_stk_qty": "    14118810",
            "issue_price": "    13100"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "140860",
            "isin_name": "파크시스템스",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "        2000",
            "tot_issue_stk_qty": "     6970859",
            "issue_price": "    25940"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "214330",
            "isin_name": "금호에이치티",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "     2384614",
            "tot_issue_stk_qty": "   213914131",
            "issue_price": "      650"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "261200",
            "isin_name": "덴티스",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       55358",
            "tot_issue_stk_qty": "    15809700",
            "issue_price": "     9032"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "272110",
            "isin_name": "케이엔제이보통주",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       15000",
            "tot_issue_stk_qty": "     7975395",
            "issue_price": "     3000"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "282880",
            "isin_name": "코윈테크",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      160365",
            "tot_issue_stk_qty": "    10825983",
            "issue_price": "    24943"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "288330",
            "isin_name": "브릿지바이오테라퓨틱스",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "      279328",
            "tot_issue_stk_qty": "    24119154",
            "issue_price": "     7160"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "348370",
            "isin_name": "엔켐",
            "stk_kind": "보통",
            "issue_type": "국내BW행사",
            "issue_stk_qty": "        2859",
            "tot_issue_stk_qty": "    18694319",
            "issue_price": "    78677"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "348370",
            "isin_name": "엔켐",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "      301947",
            "tot_issue_stk_qty": "    18694319",
            "issue_price": "    55648"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "384470",
            "isin_name": "코어라인소프트",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "      272453",
            "tot_issue_stk_qty": "    12793664",
            "issue_price": "     5322"
        },
        {
            "list_dt": "20240315",
            "sht_cd": "418620",
            "isin_name": "이에이트",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       52000",
            "tot_issue_stk_qty": "     9647677",
            "issue_price": "     9761"
        },
        {
            "list_dt": "20240314",
            "sht_cd": "052770",
            "isin_name": "아이톡시",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "      646825",
            "tot_issue_stk_qty": "    43550918",
            "issue_price": "     1260"
        },
        {
            "list_dt": "20240314",
            "sht_cd": "084180",
            "isin_name": "수성웹툰",
            "stk_kind": "보통",
            "issue_type": "상호변경",
            "issue_stk_qty": "   115499325",
            "tot_issue_stk_qty": "   115499325",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240314",
            "sht_cd": "091810",
            "isin_name": "티웨이항공",
            "stk_kind": "보통",
            "issue_type": "주식전환",
            "issue_stk_qty": "    14607425",
            "tot_issue_stk_qty": "   215378976",
            "issue_price": "     1643"
        },
        {
            "list_dt": "20240314",
            "sht_cd": "139050",
            "isin_name": "비에프랩스",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       19724",
            "tot_issue_stk_qty": "     8644551",
            "issue_price": "    10545"
        },
        {
            "list_dt": "20240314",
            "sht_cd": "276240",
            "isin_name": "엘리비젼",
            "stk_kind": "보통",
            "issue_type": "유상증자",
            "issue_stk_qty": "     2360000",
            "tot_issue_stk_qty": "    10413138",
            "issue_price": "      500"
        },
        {
            "list_dt": "20240314",
            "sht_cd": "311060",
            "isin_name": "엘에이티",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "       26000",
            "tot_issue_stk_qty": "     7074134",
            "issue_price": "     2063"
        },
        {
            "list_dt": "20240314",
            "sht_cd": "377300",
            "isin_name": "카카오페이",
            "stk_kind": "보통",
            "issue_type": "STOCKOPTION행사",
            "issue_stk_qty": "        2700",
            "tot_issue_stk_qty": "   134470018",
            "issue_price": "    34101"
        },
        {
            "list_dt": "20240313",
            "sht_cd": "000520",
            "isin_name": "삼일제약",
            "stk_kind": "보통",
            "issue_type": "국내CB행사",
            "issue_stk_qty": "       46474",
            "tot_issue_stk_qty": "    19806074",
            "issue_price": "     7531"
        },
        {
            "list_dt": "20240313",
            "sht_cd": "000520",
            "isin_name": "삼일제약",
            "stk_kind": "보통",
            "issue_type": "국내BW행사",
            "issue_stk_qty": "     1131380",
            "tot_issue_stk_qty" |  |


### 예탁원정보(공모주청약일정)

- **TR_ID**: HHKDB669108C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/pub-offer`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230301
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20240325",
            "sht_cd": "461030",
            "isin_name": "아이엠비디엑스",
            "fix_subscr_pri": "       13000",
            "face_value": "000000100",
            "subscr_dt": "2024/03/25 ~ 2024/03/26",
            "pay_dt": "2024/03/28",
            "refund_dt": "2024/03/28",
            "list_dt": "",
            "lead_mgr": "미래에셋증권",
            "pub_bf_cap": "     1141762",
            "pub_af_cap": "       62500",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240318",
            "sht_cd": "475240",
            "isin_name": "하나32호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/03/18 ~ 2024/03/19",
            "pay_dt": "2024/03/21",
            "refund_dt": "2024/03/21",
            "list_dt": "2024/03/27",
            "lead_mgr": "하나증권",
            "pub_bf_cap": "       20000",
            "pub_af_cap": "       75000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240314",
            "sht_cd": "455900",
            "isin_name": "엔젤로보틱스",
            "fix_subscr_pri": "       20000",
            "face_value": "000000500",
            "subscr_dt": "2024/03/14 ~ 2024/03/15",
            "pay_dt": "2024/03/19",
            "refund_dt": "2024/03/19",
            "list_dt": "2024/03/26",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "     6648690",
            "pub_af_cap": "      240000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240312",
            "sht_cd": "437730",
            "isin_name": "삼현",
            "fix_subscr_pri": "       30000",
            "face_value": "000000500",
            "subscr_dt": "2024/03/12 ~ 2024/03/13",
            "pay_dt": "2024/03/15",
            "refund_dt": "2024/03/15",
            "list_dt": "2024/03/21",
            "lead_mgr": "한국투자증권",
            "pub_bf_cap": "     4267928",
            "pub_af_cap": "      250000",
            "assign_stk_qty": "      500000"
        },
        {
            "record_date": "20240304",
            "sht_cd": "036220",
            "isin_name": "오상헬스케어",
            "fix_subscr_pri": "       20000",
            "face_value": "000000500",
            "subscr_dt": "2024/03/04 ~ 2024/03/05",
            "pay_dt": "2024/03/07",
            "refund_dt": "2024/03/07",
            "list_dt": "",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "     6542358",
            "pub_af_cap": "      123750",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240226",
            "sht_cd": "199430",
            "isin_name": "케이엔알시스템",
            "fix_subscr_pri": "       13500",
            "face_value": "000000100",
            "subscr_dt": "2024/02/26 ~ 2024/02/27",
            "pay_dt": "2024/02/29",
            "refund_dt": "2024/02/29",
            "list_dt": "2024/03/07",
            "lead_mgr": "DB금융투자",
            "pub_bf_cap": "      870059",
            "pub_af_cap": "       52600",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240222",
            "sht_cd": "469900",
            "isin_name": "하나31호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/02/22 ~ 2024/02/23",
            "pay_dt": "2024/02/27",
            "refund_dt": "2024/02/27",
            "list_dt": "2024/03/05",
            "lead_mgr": "하나증권",
            "pub_bf_cap": "       60500",
            "pub_af_cap": "      125000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240220",
            "sht_cd": "472230",
            "isin_name": "에스케이증권제11호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/02/20 ~ 2024/02/21",
            "pay_dt": "2024/02/23",
            "refund_dt": "2024/02/23",
            "list_dt": "2024/03/04",
            "lead_mgr": "SK증권",
            "pub_bf_cap": "       15500",
            "pub_af_cap": "      100000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240220",
            "sht_cd": "473050",
            "isin_name": "유안타제15호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/02/20 ~ 2024/02/21",
            "pay_dt": "2024/02/23",
            "refund_dt": "2024/02/23",
            "list_dt": "2024/02/29",
            "lead_mgr": "유안타증권",
            "pub_bf_cap": "       51000",
            "pub_af_cap": "      162500",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240219",
            "sht_cd": "468760",
            "isin_name": "유진기업인수목적10호",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/02/19 ~ 2024/02/20",
            "pay_dt": "2024/02/22",
            "refund_dt": "2024/02/22",
            "list_dt": "2024/02/29",
            "lead_mgr": "유진투자증권",
            "pub_bf_cap": "       24000",
            "pub_af_cap": "      100000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240219",
            "sht_cd": "473370",
            "isin_name": "비엔케이제2호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/02/19 ~ 2024/02/20",
            "pay_dt": "2024/02/22",
            "refund_dt": "2024/02/22",
            "list_dt": "2024/03/05",
            "lead_mgr": "비엔케이투자증권",
            "pub_bf_cap": "       21000",
            "pub_af_cap": "      100000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240214",
            "sht_cd": "278470",
            "isin_name": "에이피알",
            "fix_subscr_pri": "      250000",
            "face_value": "000000500",
            "subscr_dt": "2024/02/14 ~ 2024/02/15",
            "pay_dt": "2024/02/19",
            "refund_dt": "2024/02/19",
            "list_dt": "2024/02/27",
            "lead_mgr": "신한투자증권, 하나증권",
            "pub_bf_cap": "     3637689",
            "pub_af_cap": "       56850",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240213",
            "sht_cd": "068100",
            "isin_name": "케이웨더",
            "fix_subscr_pri": "        7000",
            "face_value": "000000500",
            "subscr_dt": "2024/02/13 ~ 2024/02/14",
            "pay_dt": "2024/02/16",
            "refund_dt": "2024/02/16",
            "list_dt": "2024/02/22",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "     4454807",
            "pub_af_cap": "      125000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240213",
            "sht_cd": "360350",
            "isin_name": "코셈",
            "fix_subscr_pri": "       16000",
            "face_value": "000000500",
            "subscr_dt": "2024/02/13 ~ 2024/02/14",
            "pay_dt": "2024/02/16",
            "refund_dt": "2024/02/16",
            "list_dt": "2024/02/23",
            "lead_mgr": "키움증권",
            "pub_bf_cap": "     2521985",
            "pub_af_cap": "       75000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240213",
            "sht_cd": "418620",
            "isin_name": "이에이트",
            "fix_subscr_pri": "       20000",
            "face_value": "000000500",
            "subscr_dt": "2024/02/13 ~ 2024/02/14",
            "pay_dt": "2024/02/16",
            "refund_dt": "2024/02/16",
            "list_dt": "2024/02/23",
            "lead_mgr": "한화투자증권",
            "pub_bf_cap": "     4205888",
            "pub_af_cap": "      141250",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240125",
            "sht_cd": "415380",
            "isin_name": "스튜디오삼익",
            "fix_subscr_pri": "       18000",
            "face_value": "000000500",
            "subscr_dt": "2024/01/25 ~ 2024/01/26",
            "pay_dt": "2024/01/30",
            "refund_dt": "2024/01/30",
            "list_dt": "2024/02/06",
            "lead_mgr": "DB금융투자",
            "pub_bf_cap": "     1674999",
            "pub_af_cap": "      106250",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240125",
            "sht_cd": "472220",
            "isin_name": "신영해피투모로우제10호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/01/25 ~ 2024/01/26",
            "pay_dt": "2024/01/30",
            "refund_dt": "2024/01/30",
            "list_dt": "2024/02/06",
            "lead_mgr": "신영증권",
            "pub_bf_cap": "       11500",
            "pub_af_cap": "      114375",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240123",
            "sht_cd": "452400",
            "isin_name": "이닉스",
            "fix_subscr_pri": "       14000",
            "face_value": "000000500",
            "subscr_dt": "2024/01/23 ~ 2024/01/24",
            "pay_dt": "2024/01/26",
            "refund_dt": "2024/01/26",
            "list_dt": "2024/02/01",
            "lead_mgr": "삼성증권㈜",
            "pub_bf_cap": "     3000000",
            "pub_af_cap": "      375000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240123",
            "sht_cd": "469480",
            "isin_name": "아이비케이에스제24호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/01/23 ~ 2024/01/24",
            "pay_dt": "2024/01/26",
            "refund_dt": "2024/01/26",
            "list_dt": "",
            "lead_mgr": "아이비케이투자증권㈜",
            "pub_bf_cap": "       23000",
            "pub_af_cap": "      100000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240117",
            "sht_cd": "105760",
            "isin_name": "포스뱅크",
            "fix_subscr_pri": "       18000",
            "face_value": "000000500",
            "subscr_dt": "2024/01/17 ~ 2024/01/18",
            "pay_dt": "2024/01/22",
            "refund_dt": "2024/01/22",
            "list_dt": "2024/01/29",
            "lead_mgr": "하나증권",
            "pub_bf_cap": "     3905242",
            "pub_af_cap": "      187500",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240117",
            "sht_cd": "460930",
            "isin_name": "현대힘스",
            "fix_subscr_pri": "        7300",
            "face_value": "000000500",
            "subscr_dt": "2024/01/17 ~ 2024/01/18",
            "pay_dt": "2024/01/22",
            "refund_dt": "2024/01/24",
            "list_dt": "2024/01/26",
            "lead_mgr": "미래에셋증권",
            "pub_bf_cap": "    14800000",
            "pub_af_cap": "     1306050",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240116",
            "sht_cd": "440290",
            "isin_name": "에이치비인베스트먼트",
            "fix_subscr_pri": "        3400",
            "face_value": "000000500",
            "subscr_dt": "2024/01/16 ~ 2024/01/17",
            "pay_dt": "2024/01/19",
            "refund_dt": "2024/01/19",
            "list_dt": "2024/01/25",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "    10000000",
            "pub_af_cap": "      833375",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240116",
            "sht_cd": "457550",
            "isin_name": "우진엔텍",
            "fix_subscr_pri": "        5300",
            "face_value": "000000500",
            "subscr_dt": "2024/01/16 ~ 2024/01/17",
            "pay_dt": "2024/01/19",
            "refund_dt": "2024/01/19",
            "list_dt": "2024/01/24",
            "lead_mgr": "KB증권",
            "pub_bf_cap": "     3574770",
            "pub_af_cap": "      257500",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20240115",
            "sht_cd": "471050",
            "isin_name": "대신밸런스제17호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2024/01/15 ~ 2024/01/16",
            "pay_dt": "2024/01/18",
            "refund_dt": "2024/01/18",
            "list_dt": "2024/01/24",
            "lead_mgr": "대신증권",
            "pub_bf_cap": "       56000",
            "pub_af_cap": "      137500",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231214",
            "sht_cd": "017860",
            "isin_name": "디에스단석",
            "fix_subscr_pri": "      100000",
            "face_value": "000000500",
            "subscr_dt": "2023/12/14 ~ 2023/12/15",
            "pay_dt": "2023/12/19",
            "refund_dt": "2023/12/19",
            "list_dt": "",
            "lead_mgr": "KB증권,NH투자증권",
            "pub_bf_cap": "     2530702",
            "pub_af_cap": "      152500",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231213",
            "sht_cd": "469880",
            "isin_name": "하나30호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2023/12/13 ~ 2023/12/14",
            "pay_dt": "2023/12/18",
            "refund_dt": "2023/12/18",
            "list_dt": "2023/12/22",
            "lead_mgr": "하나증권㈜",
            "pub_bf_cap": "       30500",
            "pub_af_cap": "      175000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231212",
            "sht_cd": "467930",
            "isin_name": "아이비케이에스제23호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2023/12/12 ~ 2023/12/13",
            "pay_dt": "2023/12/15",
            "refund_dt": "2023/12/15",
            "list_dt": "2023/12/22",
            "lead_mgr": "아이비케이투자증권",
            "pub_bf_cap": "       23000",
            "pub_af_cap": "      100000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231204",
            "sht_cd": "439580",
            "isin_name": "블루엠텍",
            "fix_subscr_pri": "       19000",
            "face_value": "000000100",
            "subscr_dt": "2023/12/04 ~ 2023/12/05",
            "pay_dt": "2023/12/07",
            "refund_dt": "2023/12/07",
            "list_dt": "2023/12/13",
            "lead_mgr": "하나증권,키움증권",
            "pub_bf_cap": "      920819",
            "pub_af_cap": "       35000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231201",
            "sht_cd": "417200",
            "isin_name": "엘에스머트리얼즈",
            "fix_subscr_pri": "        6000",
            "face_value": "000000500",
            "subscr_dt": "2023/12/01 ~ 2023/12/04",
            "pay_dt": "2023/12/06",
            "refund_dt": "2023/12/06",
            "list_dt": "2023/12/12",
            "lead_mgr": "키움증권,KB증권,이베스트투자증권,하이투",
            "pub_bf_cap": "    29438830",
            "pub_af_cap": "     1828125",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231127",
            "sht_cd": "432470",
            "isin_name": "케이엔에스",
            "fix_subscr_pri": "       23000",
            "face_value": "000000100",
            "subscr_dt": "2023/11/27 ~ 2023/11/28",
            "pay_dt": "2023/11/30",
            "refund_dt": "2023/11/30",
            "list_dt": "2023/12/06",
            "lead_mgr": "신영증권",
            "pub_bf_cap": "      311106",
            "pub_af_cap": "       18750",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231123",
            "sht_cd": "338840",
            "isin_name": "와이바이오로직스",
            "fix_subscr_pri": "        9000",
            "face_value": "000000500",
            "subscr_dt": "2023/11/23 ~ 2023/11/24",
            "pay_dt": "2023/11/28",
            "refund_dt": "2023/11/28",
            "list_dt": "2023/12/05",
            "lead_mgr": "유안타증권",
            "pub_bf_cap": "     6639074",
            "pub_af_cap": "      750000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231123",
            "sht_cd": "465320",
            "isin_name": "교보15호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2023/11/23 ~ 2023/11/24",
            "pay_dt": "2023/11/28",
            "refund_dt": "2023/11/28",
            "list_dt": "",
            "lead_mgr": "교보증권",
            "pub_bf_cap": "       31000",
            "pub_af_cap": "      350000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231123",
            "sht_cd": "468510",
            "isin_name": "삼성기업인수목적9호",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2023/11/23 ~ 2023/11/24",
            "pay_dt": "2023/11/28",
            "refund_dt": "2023/11/28",
            "list_dt": "2023/12/04",
            "lead_mgr": "삼성증권",
            "pub_bf_cap": "      105000",
            "pub_af_cap": "     1000000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231121",
            "sht_cd": "355690",
            "isin_name": "에이텀",
            "fix_subscr_pri": "       18000",
            "face_value": "000000500",
            "subscr_dt": "2023/11/21 ~ 2023/11/22",
            "pay_dt": "2023/11/24",
            "refund_dt": "2023/11/24",
            "list_dt": "2023/12/01",
            "lead_mgr": "하나증권",
            "pub_bf_cap": "     2337840",
            "pub_af_cap": "       81250",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231121",
            "sht_cd": "466910",
            "isin_name": "엔에이치기업인수목적30호",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2023/11/21 ~ 2023/11/22",
            "pay_dt": "2023/11/24",
            "refund_dt": "2023/11/24",
            "list_dt": "2023/12/01",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "      110000",
            "pub_af_cap": "      200000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231116",
            "sht_cd": "453860",
            "isin_name": "에이에스텍",
            "fix_subscr_pri": "       28000",
            "face_value": "000000500",
            "subscr_dt": "2023/11/16 ~ 2023/11/17",
            "pay_dt": "2023/11/21",
            "refund_dt": "2023/11/21",
            "list_dt": "2023/11/28",
            "lead_mgr": "미래에셋증권",
            "pub_bf_cap": "     2388750",
            "pub_af_cap": "      175875",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231113",
            "sht_cd": "402490",
            "isin_name": "그린리소스",
            "fix_subscr_pri": "       17000",
            "face_value": "000000500",
            "subscr_dt": "2023/11/13 ~ 2023/11/14",
            "pay_dt": "2023/11/16",
            "refund_dt": "2023/11/16",
            "list_dt": "2023/11/24",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "     3247372",
            "pub_af_cap": "      205000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231113",
            "sht_cd": "452280",
            "isin_name": "한선엔지니어링",
            "fix_subscr_pri": "        7000",
            "face_value": "000000500",
            "subscr_dt": "2023/11/13 ~ 2023/11/14",
            "pay_dt": "2023/11/16",
            "refund_dt": "2023/11/16",
            "list_dt": "2023/11/24",
            "lead_mgr": "대신증권",
            "pub_bf_cap": "     6312500",
            "pub_af_cap": "      531250",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231110",
            "sht_cd": "448280",
            "isin_name": "에코아이",
            "fix_subscr_pri": "       34700",
            "face_value": "000000500",
            "subscr_dt": "2023/11/10 ~ 2023/11/13",
            "pay_dt": "2023/11/15",
            "refund_dt": "2023/11/15",
            "list_dt": "2023/11/21",
            "lead_mgr": "KB증권",
            "pub_bf_cap": "     3884612",
            "pub_af_cap": "      259875",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231109",
            "sht_cd": "111380",
            "isin_name": "동인기연",
            "fix_subscr_pri": "       30000",
            "face_value": "000000100",
            "subscr_dt": "2023/11/09 ~ 2023/11/10",
            "pay_dt": "2023/11/14",
            "refund_dt": "2023/11/14",
            "list_dt": "2023/11/21",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "      500000",
            "pub_af_cap": "       44112",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231109",
            "sht_cd": "352090",
            "isin_name": "스톰테크",
            "fix_subscr_pri": "       11000",
            "face_value": "000000100",
            "subscr_dt": "2023/11/09 ~ 2023/11/10",
            "pay_dt": "2023/11/14",
            "refund_dt": "2023/11/14",
            "list_dt": "2023/11/20",
            "lead_mgr": "하이투자증권",
            "pub_bf_cap": "      999559",
            "pub_af_cap": "       83750",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231108",
            "sht_cd": "450080",
            "isin_name": "에코프로머티리얼즈",
            "fix_subscr_pri": "       36200",
            "face_value": "000000500",
            "subscr_dt": "2023/11/08 ~ 2023/11/09",
            "pay_dt": "2023/11/13",
            "refund_dt": "2023/11/13",
            "list_dt": "2023/11/17",
            "lead_mgr": "미래에셋증권, NH투자증권, 하이투자증권",
            "pub_bf_cap": "    28951079",
            "pub_af_cap": "     1737120",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231106",
            "sht_cd": "452300",
            "isin_name": "캡스톤파트너스",
            "fix_subscr_pri": "        4000",
            "face_value": "000000200",
            "subscr_dt": "2023/11/06 ~ 2023/11/07",
            "pay_dt": "2023/11/09",
            "refund_dt": "2023/11/09",
            "list_dt": "2023/11/15",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "     2340500",
            "pub_af_cap": "       79800",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231102",
            "sht_cd": "445090",
            "isin_name": "에이직랜드",
            "fix_subscr_pri": "       25000",
            "face_value": "000000500",
            "subscr_dt": "2023/11/02 ~ 2023/11/03",
            "pay_dt": "2023/11/07",
            "refund_dt": "2023/11/07",
            "list_dt": "2023/11/13",
            "lead_mgr": "삼성증권",
            "pub_bf_cap": "     3954495",
            "pub_af_cap": "      329542",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231101",
            "sht_cd": "365330",
            "isin_name": "에스와이스틸텍",
            "fix_subscr_pri": "        1800",
            "face_value": "000000500",
            "subscr_dt": "2023/11/01 ~ 2023/11/02",
            "pay_dt": "2023/11/06",
            "refund_dt": "2023/11/06",
            "list_dt": "2023/11/13",
            "lead_mgr": "KB증권",
            "pub_bf_cap": "    11700000",
            "pub_af_cap": "      875000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231101",
            "sht_cd": "464440",
            "isin_name": "한국제13호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2023/11/01 ~ 2023/11/02",
            "pay_dt": "2023/11/06",
            "refund_dt": "2023/11/06",
            "list_dt": "2023/11/13",
            "lead_mgr": "한국투자증권",
            "pub_bf_cap": "       32000",
            "pub_af_cap": "      100000",
            "assign_stk_qty": "     1000000"
        },
        {
            "record_date": "20231031",
            "sht_cd": "372320",
            "isin_name": "큐로셀",
            "fix_subscr_pri": "       20000",
            "face_value": "000000500",
            "subscr_dt": "2023/10/31 ~ 2023/11/01",
            "pay_dt": "2023/11/03",
            "refund_dt": "2023/11/03",
            "list_dt": "2023/11/09",
            "lead_mgr": "삼성증권,미래에셋증권",
            "pub_bf_cap": "     5982368",
            "pub_af_cap": "      200000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231031",
            "sht_cd": "413640",
            "isin_name": "비아이매트릭스",
            "fix_subscr_pri": "       13000",
            "face_value": "000000500",
            "subscr_dt": "2023/10/31 ~ 2023/11/01",
            "pay_dt": "2023/11/03",
            "refund_dt": "2023/11/03",
            "list_dt": "2023/11/09",
            "lead_mgr": "아이비케이투자증권",
            "pub_bf_cap": "     2985470",
            "pub_af_cap": "      150000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231031",
            "sht_cd": "446540",
            "isin_name": "메가터치",
            "fix_subscr_pri": "        4800",
            "face_value": "000000500",
            "subscr_dt": "2023/10/31 ~ 2023/11/01",
            "pay_dt": "2023/11/03",
            "refund_dt": "2023/11/03",
            "list_dt": "2023/11/09",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "     7707500",
            "pub_af_cap": "      650000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231031",
            "sht_cd": "451760",
            "isin_name": "컨텍",
            "fix_subscr_pri": "       22500",
            "face_value": "000000500",
            "subscr_dt": "2023/10/31 ~ 2023/11/01",
            "pay_dt": "2023/11/03",
            "refund_dt": "2023/11/03",
            "list_dt": "2023/11/09",
            "lead_mgr": "대신증권",
            "pub_bf_cap": "     6169890",
            "pub_af_cap": "      257500",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231026",
            "sht_cd": "088280",
            "isin_name": "쏘닉스",
            "fix_subscr_pri": "        7500",
            "face_value": "000001000",
            "subscr_dt": "2023/10/26 ~ 2023/10/27",
            "pay_dt": "2023/10/31",
            "refund_dt": "2023/10/31",
            "list_dt": "2023/11/07",
            "lead_mgr": "KB증권",
            "pub_bf_cap": "    13598490",
            "pub_af_cap": "      900000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231024",
            "sht_cd": "464680",
            "isin_name": "케이비제27호기업인수목적",
            "fix_subscr_pri": "        2000",
            "face_value": "000000100",
            "subscr_dt": "2023/10/24 ~ 2023/10/25",
            "pay_dt": "2023/10/27",
            "refund_dt": "2023/10/27",
            "list_dt": "2023/11/03",
            "lead_mgr": "KB증권",
            "pub_bf_cap": "       40500",
            "pub_af_cap": "      312500",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231023",
            "sht_cd": "221800",
            "isin_name": "유투바이오",
            "fix_subscr_pri": "        4400",
            "face_value": "000000500",
            "subscr_dt": "2023/10/23 ~ 2023/10/24",
            "pay_dt": "2023/10/26",
            "refund_dt": "2023/10/26",
            "list_dt": "",
            "lead_mgr": "신한투자증권",
            "pub_bf_cap": "     5051020",
            "pub_af_cap": "      141090",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231023",
            "sht_cd": "240600",
            "isin_name": "유진테크놀로지",
            "fix_subscr_pri": "       17000",
            "face_value": "000000500",
            "subscr_dt": "2023/10/23 ~ 2023/10/24",
            "pay_dt": "2023/10/26",
            "refund_dt": "2023/10/26",
            "list_dt": "2023/11/02",
            "lead_mgr": "NH투자증권",
            "pub_bf_cap": "     2642734",
            "pub_af_cap": "      131186",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231018",
            "sht_cd": "432720",
            "isin_name": "퀄리타스반도체",
            "fix_subscr_pri": "       17000",
            "face_value": "000000500",
            "subscr_dt": "2023/10/18 ~ 2023/10/19",
            "pay_dt": "2023/10/23",
            "refund_dt": "2023/10/23",
            "list_dt": "2023/10/27",
            "lead_mgr": "한국투자증권",
            "pub_bf_cap": "     4476920",
            "pub_af_cap": "      225000",
            "assign_stk_qty": "      450000"
        },
        {
            "record_date": "20231016",
            "sht_cd": "396470",
            "isin_name": "워트",
            "fix_subscr_pri": "        6500",
            "face_value": "000000100",
            "subscr_dt": "2023/10/16 ~ 2023/10/17",
            "pay_dt": "2023/10/19",
            "refund_dt": "2023/10/19",
            "list_dt": "2023/10/26",
            "lead_mgr": "키움증권",
            "pub_bf_cap": "     1200000",
            "pub_af_cap": "      100000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231010",
            "sht_cd": "246250",
            "isin_name": "에스엘에스바이오",
            "fix_subscr_pri": "        7000",
            "face_value": "000000500",
            "subscr_dt": "2023/10/10 ~ 2023/10/11",
            "pay_dt": "2023/10/13",
            "refund_dt": "2023/10/13",
            "list_dt": "2023/10/20",
            "lead_mgr": "하나증권",
            "pub_bf_cap": "     3432802",
            "pub_af_cap": "       96250",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231010",
            "sht_cd": "416180",
            "isin_name": "신성에스티",
            "fix_subscr_pri": "       26000",
            "face_value": "000000500",
            "subscr_dt": "2023/10/10 ~ 2023/10/11",
            "pay_dt": "2023/10/13",
            "refund_dt": "2023/10/13",
            "list_dt": "2023/10/19",
            "lead_mgr": "미래에셋증권",
            "pub_bf_cap": "     3500658",
            "pub_af_cap": "      250000",
            "assign_stk_qty": "           0"
        },
        {
            "record_date": "20231005",
            "sht_cd": "445180",
            "isin_name": "퓨릿",
            "fix_subscr_pri": "       10700",
            "face_value": "000000500",
            "subscr_dt": "2023/10/05 ~ 2023/10/06",
            "pay_dt": "2023/10/11",
            "refu |  |


### 국내주식 재무비율

- **TR_ID**: FHKST66430300
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/finance/financial-ratio`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"J",
"fid_input_iscd":"005930",
"fid_div_cls_code":"1"
} |  |
| Response Example | {
    "output": [
        {
            "stac_yymm": "202312",
            "grs": "-14.33",
            "bsop_prfi_inrt": "-84.86",
            "ntin_inrt": "-72.17",
            "roe_val": "4.14",
            "eps": "2131.00",
            "sps": "38120",
            "bps": "52002.00",
            "rsrv_rate": "39256.91",
            "lblt_rate": "25.36"
        },
        {
            "stac_yymm": "202309",
            "grs": "-17.52",
            "bsop_prfi_inrt": "-90.42",
            "ntin_inrt": "-71.26",
            "roe_val": "3.22",
            "eps": "1244.00",
            "sps": "37522",
            "bps": "52068.00",
            "rsrv_rate": "39306.65",
            "lblt_rate": "24.89"
        },
        {
            "stac_yymm": "202306",
            "grs": "-20.15",
            "bsop_prfi_inrt": "-95.36",
            "ntin_inrt": "-85.29",
            "roe_val": "1.70",
            "eps": "434.00",
            "sps": "36437",
            "bps": "51385.00",
            "rsrv_rate": "38789.91",
            "lblt_rate": "24.80"
        },
        {
            "stac_yymm": "202303",
            "grs": "-18.05",
            "bsop_prfi_inrt": "-95.47",
            "ntin_inrt": "-86.10",
            "roe_val": "1.61",
            "eps": "206.00",
            "sps": "37538",
            "bps": "51529.00",
            "rsrv_rate": "38898.83",
            "lblt_rate": "26.21"
        },
        {
            "stac_yymm": "202212",
            "grs": "8.09",
            "bsop_prfi_inrt": "-15.99",
            "ntin_inrt": "39.46",
            "roe_val": "17.07",
            "eps": "8057.00",
            "sps": "44494",
            "bps": "50817.00",
            "rsrv_rate": "38360.25",
            "lblt_rate": "26.41"
        },
        {
            "stac_yymm": "202209",
            "grs": "14.15",
            "bsop_prfi_inrt": "3.45",
            "ntin_inrt": "9.44",
            "roe_val": "13.18",
            "eps": "4597.00",
            "sps": "45494",
            "bps": "49387.00",
            "rsrv_rate": "37277.71",
            "lblt_rate": "36.35"
        },
        {
            "stac_yymm": "202206",
            "grs": "20.09",
            "bsop_prfi_inrt": "28.56",
            "ntin_inrt": "33.66",
            "roe_val": "14.36",
            "eps": "3251.00",
            "sps": "45633",
            "bps": "46937.00",
            "rsrv_rate": "35423.75",
            "lblt_rate": "36.64"
        },
        {
            "stac_yymm": "202203",
            "grs": "18.95",
            "bsop_prfi_inrt": "50.50",
            "ntin_inrt": "58.57",
            "roe_val": "14.77",
            "eps": "1638.00",
            "sps": "45803",
            "bps": "45106.00",
            "rsrv_rate": "34037.84",
            "lblt_rate": "39.34"
        },
        {
            "stac_yymm": "202112",
            "grs": "18.07",
            "bsop_prfi_inrt": "43.45",
            "ntin_inrt": "51.12",
            "roe_val": "13.92",
            "eps": "5777.00",
            "sps": "41163",
            "bps": "43611.00",
            "rsrv_rate": "32906.47",
            "lblt_rate": "39.92"
        },
        {
            "stac_yymm": "202109",
            "grs": "15.85",
            "bsop_prfi_inrt": "40.15",
            "ntin_inrt": "46.81",
            "roe_val": "13.72",
            "eps": "4211.00",
            "sps": "39855",
            "bps": "42447.00",
            "rsrv_rate": "32025.54",
            "lblt_rate": "38.30"
        },
        {
            "stac_yymm": "202106",
            "grs": "19.18",
            "bsop_prfi_inrt": "50.41",
            "ntin_inrt": "60.69",
            "roe_val": "12.21",
            "eps": "2435.00",
            "sps": "38000",
            "bps": "40361.00",
            "rsrv_rate": "30446.66",
            "lblt_rate": "36.29"
        },
        {
            "stac_yymm": "202103",
            "grs": "18.19",
            "bsop_prfi_inrt": "45.53",
            "ntin_inrt": "46.20",
            "roe_val": "10.64",
            "eps": "1044.00",
            "sps": "38505",
            "bps": "39126.00",
            "rsrv_rate": "29511.49",
            "lblt_rate": "43.23"
        },
        {
            "stac_yymm": "202012",
            "grs": "2.78",
            "bsop_prfi_inrt": "29.62",
            "ntin_inrt": "21.48",
            "roe_val": "9.99",
            "eps": "3841.00",
            "sps": "34862",
            "bps": "39406.00",
            "rsrv_rate": "29723.53",
            "lblt_rate": "37.07"
        },
        {
            "stac_yymm": "202009",
            "grs": "2.78",
            "bsop_prfi_inrt": "30.76",
            "ntin_inrt": "19.92",
            "roe_val": "10.02",
            "eps": "2892.00",
            "sps": "34401",
            "bps": "39446.00",
            "rsrv_rate": "29753.81",
            "lblt_rate": "36.09"
        },
        {
            "stac_yymm": "202006",
            "grs": "-0.20",
            "bsop_prfi_inrt": "13.74",
            "ntin_inrt": "2.11",
            "roe_val": "8.04",
            "eps": "1528.00",
            "sps": "31885",
            "bps": "38534.00",
            "rsrv_rate": "29063.37",
            "lblt_rate": "32.67"
        },
        {
            "stac_yymm": "202003",
            "grs": "5.61",
            "bsop_prfi_inrt": "3.43",
            "ntin_inrt": "-3.15",
            "roe_val": "7.62",
            "eps": "720.00",
            "sps": "32579",
            "bps": "38053.00",
            "rsrv_rate": "28699.75",
            "lblt_rate": "34.19"
        },
        {
            "stac_yymm": "201912",
            "grs": "-5.48",
            "bsop_prfi_inrt": "-52.84",
            "ntin_inrt": "-50.98",
            "roe_val": "8.69",
            "eps": "3166.00",
            "sps": "33919",
            "bps": "37528.00",
            "rsrv_rate": "28302.40",
            "lblt_rate": "34.12"
        },
        {
            "stac_yymm": "201909",
            "grs": "-7.58",
            "bsop_prfi_inrt": "-57.14",
            "ntin_inrt": "-53.98",
            "roe_val": "8.76",
            "eps": "2396.00",
            "sps": "33471",
            "bps": "37600.00",
            "rsrv_rate": "28356.77",
            "lblt_rate": "34.14"
        },
        {
            "stac_yymm": "201906",
            "grs": "-8.85",
            "bsop_prfi_inrt": "-57.95",
            "ntin_inrt": "-55.02",
            "roe_val": "8.30",
            "eps": "1498.00",
            "sps": "31950",
            "bps": "36789.00",
            "rsrv_rate": "27742.76",
            "lblt_rate": "33.05"
        },
        {
            "stac_yymm": "201903",
            "grs": "-13.50",
            "bsop_prfi_inrt": "-60.15",
            "ntin_inrt": "-56.85",
            "roe_val": "8.41",
            "eps": "752.00",
            "sps": "30848",
            "bps": "36142.00",
            "rsrv_rate": "27253.31",
            "lblt_rate": "36.27"
        },
        {
            "stac_yymm": "201812",
            "grs": "1.75",
            "bsop_prfi_inrt": "9.77",
            "ntin_inrt": "5.12",
            "roe_val": "19.63",
            "eps": "6024.00",
            "sps": "33458",
            "bps": "35342.00",
            "rsrv_rate": "26648.22",
            "lblt_rate": "36.97"
        },
        {
            "stac_yymm": "201809",
            "grs": "6.28",
            "bsop_prfi_inrt": "24.91",
            "ntin_inrt": "19.88",
            "roe_val": "21.47",
            "eps": "4853.00",
            "sps": "33572",
            "bps": "32685.00",
            "rsrv_rate": "26568.28",
            "lblt_rate": "39.28"
        },
        {
            "stac_yymm": "201806",
            "grs": "6.72",
            "bsop_prfi_inrt": "27.32",
            "ntin_inrt": "21.31",
            "roe_val": "20.88",
            "eps": "3082.00",
            "sps": "32482",
            "bps": "31483.00",
            "rsrv_rate": "25587.24",
            "lblt_rate": "36.70"
        },
        {
            "stac_yymm": "201803",
            "grs": "19.82",
            "bsop_prfi_inrt": "58.03",
            "ntin_inrt": "52.11",
            "roe_val": "21.96",
            "eps": "1583.00",
            "sps": "33017",
            "bps": "30146.00",
            "rsrv_rate": "24496.79",
            "lblt_rate": "39.96"
        },
        {
            "stac_yymm": "201712",
            "grs": "18.68",
            "bsop_prfi_inrt": "83.46",
            "ntin_inrt": "85.63",
            "roe_val": "21.01",
            "eps": "5421.00",
            "sps": "31414",
            "bps": "28971.00",
            "rsrv_rate": "23681.42",
            "lblt_rate": "40.68"
        },
        {
            "stac_yymm": "201709",
            "grs": "16.87",
            "bsop_prfi_inrt": "92.30",
            "ntin_inrt": "91.40",
            "roe_val": "20.06",
            "eps": "3804.00",
            "sps": "30021",
            "bps": "28305.00",
            "rsrv_rate": "23266.64",
            "lblt_rate": "40.76"
        },
        {
            "stac_yymm": "201706",
            "grs": "10.75",
            "bsop_prfi_inrt": "61.71",
            "ntin_inrt": "68.81",
            "roe_val": "19.25",
            "eps": "2328.00",
            "sps": "28399",
            "bps": "26828.00",
            "rsrv_rate": "22216.19",
            "lblt_rate": "38.31"
        },
        {
            "stac_yymm": "201703",
            "grs": "1.54",
            "bsop_prfi_inrt": "48.27",
            "ntin_inrt": "46.29",
            "roe_val": "16.21",
            "eps": "929.00",
            "sps": "25087",
            "bps": "24184.00",
            "rsrv_rate": "21617.29",
            "lblt_rate": "39.20"
        },
        {
            "stac_yymm": "201612",
            "grs": "0.60",
            "bsop_prfi_inrt": "10.70",
            "ntin_inrt": "19.23",
            "roe_val": "12.48",
            "eps": "2735.00",
            "sps": "24632",
            "bps": "24340.00",
            "rsrv_rate": "21757.56",
            "lblt_rate": "35.87"
        },
        {
            "stac_yymm": "201609",
            "grs": "0.81",
            "bsop_prfi_inrt": "-1.24",
            "ntin_inrt": "-1.25",
            "roe_val": "11.94",
            "eps": "1881.00",
            "sps": "24033",
            "bps": "22708.00",
            "rsrv_rate": "20291.88",
            "lblt_rate": "36.17"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 예탁원정보(자본감소일정)

- **TR_ID**: HHKDB669106C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/cap-dcrs`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230301
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20240315",
            "sht_cd": "067390",
            "isin_name": "아스트",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2024/03/14 ~ 2024/03/31",
            "list_dt": "2024/04/01"
        },
        {
            "record_date": "20240226",
            "sht_cd": "000040",
            "isin_name": "케이알모터스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.30",
            "comp_way": "곱하기",
            "td_stop_dt": "2024/02/23 ~ 2024/03/17",
            "list_dt": "2024/03/18"
        },
        {
            "record_date": "20240208",
            "sht_cd": "033180",
            "isin_name": "케이에이치필룩스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.20",
            "comp_way": "곱하기",
            "td_stop_dt": "2024/02/07 ~ 2024/02/28",
            "list_dt": "2024/02/29"
        },
        {
            "record_date": "20240207",
            "sht_cd": "219750",
            "isin_name": "지티지웰니스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 4.00",
            "comp_way": "나누기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20240129",
            "sht_cd": "057880",
            "isin_name": "피에이치씨",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "2024/01/26 ~ 2024/02/20",
            "list_dt": "2024/02/21"
        },
        {
            "record_date": "20240115",
            "sht_cd": "001140",
            "isin_name": "국보",
            "stk_kind": "보통",
            "reduce_cap_type": "",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2024/01/12 ~ 2024/02/01",
            "list_dt": "2024/02/02"
        },
        {
            "record_date": "20240108",
            "sht_cd": "078130",
            "isin_name": "국일제지",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2024/01/05 ~ 2024/02/21",
            "list_dt": "2024/02/22"
        },
        {
            "record_date": "20240102",
            "sht_cd": "013090",
            "isin_name": "인켈",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.07",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20240102",
            "sht_cd": "013095",
            "isin_name": "인켈1우",
            "stk_kind": "우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.07",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20240102",
            "sht_cd": "013097",
            "isin_name": "인켈2우",
            "stk_kind": "2우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.07",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20231227",
            "sht_cd": "078130",
            "isin_name": "국일제지",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/26 ~ 2024/02/20",
            "list_dt": "2024/02/21"
        },
        {
            "record_date": "20231227",
            "sht_cd": "088240",
            "isin_name": "대우조선해양건설",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.00",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20231226",
            "sht_cd": "043590",
            "isin_name": "웰킵스하이텍",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.75",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/22 ~ 2024/01/18",
            "list_dt": "2024/01/19"
        },
        {
            "record_date": "20231222",
            "sht_cd": "227420",
            "isin_name": "도부마스크",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.50",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": "2024/01/19"
        },
        {
            "record_date": "20231218",
            "sht_cd": "076610",
            "isin_name": "해성옵틱스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.20",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/15 ~ 2024/01/07",
            "list_dt": "2024/01/08"
        },
        {
            "record_date": "20231218",
            "sht_cd": "217480",
            "isin_name": "에스디생명공학",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.70",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/15 ~ 2024/01/24",
            "list_dt": "2024/01/25"
        },
        {
            "record_date": "20231215",
            "sht_cd": "321080",
            "isin_name": "메타엠",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.43",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/14 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231214",
            "sht_cd": "299910",
            "isin_name": "베스파",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.10",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/13 ~ 2024/01/14",
            "list_dt": "2024/01/15"
        },
        {
            "record_date": "20231213",
            "sht_cd": "314170",
            "isin_name": "메디에이지",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.20",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/12 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231211",
            "sht_cd": "003560",
            "isin_name": "아이에이치큐",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.33",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/08 ~ 2024/01/03",
            "list_dt": "2024/01/04"
        },
        {
            "record_date": "20231211",
            "sht_cd": "078860",
            "isin_name": "아이오케이컴퍼니",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/08 ~ 2023/12/26",
            "list_dt": "2023/12/27"
        },
        {
            "record_date": "20231208",
            "sht_cd": "088240",
            "isin_name": "대우조선해양건설",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.00",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20231208",
            "sht_cd": "08824K",
            "isin_name": "대우조선해양건설1우",
            "stk_kind": "우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.00",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20231208",
            "sht_cd": "08824L",
            "isin_name": "대우조선해양건설2우",
            "stk_kind": "2우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.00",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20231208",
            "sht_cd": "08824M",
            "isin_name": "대우조선해양건설3우",
            "stk_kind": "3우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.00",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20231207",
            "sht_cd": "159910",
            "isin_name": "스킨앤스킨",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.10",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/06 ~ 2023/12/26",
            "list_dt": "2023/12/27"
        },
        {
            "record_date": "20231205",
            "sht_cd": "013090",
            "isin_name": "인켈",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.01",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/04 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231205",
            "sht_cd": "013095",
            "isin_name": "인켈1우",
            "stk_kind": "우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.01",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/04 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231205",
            "sht_cd": "013097",
            "isin_name": "인켈2우",
            "stk_kind": "2우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.01",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/04 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231204",
            "sht_cd": "002880",
            "isin_name": "대유에이텍",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 3.00",
            "comp_way": "나누기",
            "td_stop_dt": "2023/12/01 ~ 2023/12/19",
            "list_dt": "2023/12/20"
        },
        {
            "record_date": "20231204",
            "sht_cd": "174880",
            "isin_name": "장원테크",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.20",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/01 ~ 2023/12/20",
            "list_dt": "2023/12/21"
        },
        {
            "record_date": "20231204",
            "sht_cd": "406830",
            "isin_name": "여기어때컴퍼니",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.46",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/01 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231204",
            "sht_cd": "40683K",
            "isin_name": "여기어때컴퍼니1우",
            "stk_kind": "우선",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.46",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/12/01 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231129",
            "sht_cd": "299910",
            "isin_name": "베스파",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.33",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/11/28 ~ 2024/01/14",
            "list_dt": "2024/01/15"
        },
        {
            "record_date": "20231127",
            "sht_cd": "412790",
            "isin_name": "테람스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.10",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20231123",
            "sht_cd": "181690",
            "isin_name": "디엔지비",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.25",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/11/22 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231117",
            "sht_cd": "058450",
            "isin_name": "엔터파트너즈",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.20",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/11/16 ~ 2023/12/11",
            "list_dt": "2023/12/12"
        },
        {
            "record_date": "20231117",
            "sht_cd": "155960",
            "isin_name": "지디",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.10",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/11/16 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231117",
            "sht_cd": "186630",
            "isin_name": "리치앤타임",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/11/16 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231113",
            "sht_cd": "144620",
            "isin_name": "코오롱머티리얼",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.75",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/11/10 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231107",
            "sht_cd": "181690",
            "isin_name": "디엔지비",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.50",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/11/06 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231106",
            "sht_cd": "148140",
            "isin_name": "비디아이",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.10",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/11/03 ~ 2023/12/11",
            "list_dt": "2023/12/12"
        },
        {
            "record_date": "20231101",
            "sht_cd": "155900",
            "isin_name": "바다로19호선박투자회사",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/10/31 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231030",
            "sht_cd": "197210",
            "isin_name": "리드",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.10",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/10/27 ~",
            "list_dt": ""
        },
        {
            "record_date": "20231030",
            "sht_cd": "238500",
            "isin_name": "로보쓰리에이아이앤로보틱스",
            "stk_kind": "보통",
            "reduce_cap_type": "",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/10/27 ~ 2023/11/16",
            "list_dt": "2023/11/17"
        },
        {
            "record_date": "20231020",
            "sht_cd": "148140",
            "isin_name": "비디아이",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.25",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/10/19 ~ 2023/12/11",
            "list_dt": "2023/12/12"
        },
        {
            "record_date": "20231018",
            "sht_cd": "115390",
            "isin_name": "락앤락",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.86",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/10/17 ~ 2023/11/05",
            "list_dt": "2023/11/06"
        },
        {
            "record_date": "20231012",
            "sht_cd": "326830",
            "isin_name": "모르페우스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.20",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20231010",
            "sht_cd": "005110",
            "isin_name": "한창",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.20",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/10/06 ~ 2023/10/26",
            "list_dt": "2023/10/27"
        },
        {
            "record_date": "20230926",
            "sht_cd": "065560",
            "isin_name": "녹원씨엔아이",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.50",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/25 ~ 2023/10/22",
            "list_dt": "2023/10/23"
        },
        {
            "record_date": "20230925",
            "sht_cd": "447800",
            "isin_name": "브릿지벤처스",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230922",
            "sht_cd": "101140",
            "isin_name": "인바이오젠",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/21 ~ 2023/10/22",
            "list_dt": "2023/10/23"
        },
        {
            "record_date": "20230922",
            "sht_cd": "101145",
            "isin_name": "인바이오젠1우",
            "stk_kind": "우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/21 ~ 2023/10/22",
            "list_dt": "2023/10/23"
        },
        {
            "record_date": "20230919",
            "sht_cd": "06911M",
            "isin_name": "코스온3우",
            "stk_kind": "3우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.17",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/18 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230914",
            "sht_cd": "234760",
            "isin_name": "고위드",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.72",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/13 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230912",
            "sht_cd": "069110",
            "isin_name": "코스온",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.17",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/11 ~ 2023/10/10",
            "list_dt": "2023/10/11"
        },
        {
            "record_date": "20230911",
            "sht_cd": "046640",
            "isin_name": "씨디데이타",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.40",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230907",
            "sht_cd": "058420",
            "isin_name": "제이웨이",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/06 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230907",
            "sht_cd": "05842L",
            "isin_name": "제이웨이2우",
            "stk_kind": "2우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/06 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230906",
            "sht_cd": "033180",
            "isin_name": "케이에이치필룩스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.33",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/09/05 ~ 2023/10/03",
            "list_dt": "2023/10/04"
        },
        {
            "record_date": "20230823",
            "sht_cd": "003560",
            "isin_name": "아이에이치큐",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.07",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/08/22 ~ 2023/09/13",
            "list_dt": "2023/09/14"
        },
        {
            "record_date": "20230822",
            "sht_cd": "036630",
            "isin_name": "세종텔레콤",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.81",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/08/21 ~ 2023/09/07",
            "list_dt": "2023/09/08"
        },
        {
            "record_date": "20230822",
            "sht_cd": "043420",
            "isin_name": "에코이에스",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.73",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230822",
            "sht_cd": "220630",
            "isin_name": "맘스터치앤컴퍼니",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.26",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/08/21 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230811",
            "sht_cd": "000360",
            "isin_name": "삼환기업",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/08/10 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230807",
            "sht_cd": "048180",
            "isin_name": "씨제이푸드빌",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.63",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230807",
            "sht_cd": "434840",
            "isin_name": "니즈게임즈",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.88",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/08/04 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230725",
            "sht_cd": "111870",
            "isin_name": "케이에이치전자",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.07",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/07/24 ~ 2023/08/16",
            "list_dt": "2023/08/17"
        },
        {
            "record_date": "20230720",
            "sht_cd": "091090",
            "isin_name": "세원이앤씨",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.20",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/07/19 ~ 2023/08/13",
            "list_dt": "2023/08/14"
        },
        {
            "record_date": "20230719",
            "sht_cd": "203810",
            "isin_name": "국제16호선박투자회사",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.16",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/07/18 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230710",
            "sht_cd": "087800",
            "isin_name": "KDB생명보험",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.25",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/07/07 ~ 2023/07/26",
            "list_dt": "2023/07/27"
        },
        {
            "record_date": "20230703",
            "sht_cd": "038530",
            "isin_name": "케이바이오컴퍼니",
            "stk_kind": "보통",
            "reduce_cap_type": "",
            "reduce_cap_rate": " 1.00",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/06/30 ~ 2023/07/20",
            "list_dt": "2023/07/21"
        },
        {
            "record_date": "20230612",
            "sht_cd": "197210",
            "isin_name": "리드",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.04",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/06/09 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230612",
            "sht_cd": "19721K",
            "isin_name": "리드1우",
            "stk_kind": "우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.04",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/06/09 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230608",
            "sht_cd": "139050",
            "isin_name": "시티랩스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.07",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/06/07 ~ 2023/06/27",
            "list_dt": "2023/06/28"
        },
        {
            "record_date": "20230515",
            "sht_cd": "373560",
            "isin_name": "페이투스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.50",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230509",
            "sht_cd": "351160",
            "isin_name": "케이온네트워크",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.58",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/05/08 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230508",
            "sht_cd": "138690",
            "isin_name": "엘아이에스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.04",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/05/04 ~ 2023/06/26",
            "list_dt": "2023/06/27"
        },
        {
            "record_date": "20230502",
            "sht_cd": "115580",
            "isin_name": "현대인프라코어",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.50",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/28 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230501",
            "sht_cd": "333830",
            "isin_name": "티비에스머티리얼",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.10",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230428",
            "sht_cd": "113300",
            "isin_name": "세명테크",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.50",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/27 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230424",
            "sht_cd": "112240",
            "isin_name": "에스에프씨",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/21 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230420",
            "sht_cd": "050320",
            "isin_name": "에스에이치엔엘",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230420",
            "sht_cd": "05032K",
            "isin_name": "에스에이치엔엘1우",
            "stk_kind": "우선",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230418",
            "sht_cd": "203810",
            "isin_name": "국제16호선박투자회사",
            "stk_kind": "보통",
            "reduce_cap_type": "유상감자",
            "reduce_cap_rate": " 0.91",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/17 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230418",
            "sht_cd": "391360",
            "isin_name": "버디버디(budybudy)",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/17 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230417",
            "sht_cd": "141020",
            "isin_name": "디에스앤엘",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.25",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/14 ~ 2023/05/08",
            "list_dt": "2023/05/09"
        },
        {
            "record_date": "20230417",
            "sht_cd": "219750",
            "isin_name": "지티지웰니스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.50",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/14 ~ 2023/05/07",
            "list_dt": "2023/05/08"
        },
        {
            "record_date": "20230417",
            "sht_cd": "329820",
            "isin_name": "정금에프앤씨",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.05",
            "comp_way": "곱하기",
            "td_stop_dt": "",
            "list_dt": ""
        },
        {
            "record_date": "20230413",
            "sht_cd": "019570",
            "isin_name": "리더스기술투자",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.33",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/12 ~ 2023/05/02",
            "list_dt": "2023/05/03"
        },
        {
            "record_date": "20230411",
            "sht_cd": "050090",
            "isin_name": "비케이홀딩스",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.25",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/04/10 ~ 2023/05/07",
            "list_dt": "2023/05/08"
        },
        {
            "record_date": "20230403",
            "sht_cd": "362570",
            "isin_name": "아이프리원",
            "stk_kind": "보통",
            "reduce_cap_type": "무상감자",
            "reduce_cap_rate": " 0.50",
            "comp_way": "곱하기",
            "td_stop_dt": "2023/03/31 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230329",
            "sht_cd": "101000", |  |


### 예탁원정보(무상증자일정)

- **TR_ID**: HHKDB669101C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/bonus-issue`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230301
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20240326",
            "sht_cd": "466100",
            "isin_name": "클로봇",
            "fix_rate": "1000.0",
            "odd_rec_price": "000000000",
            "right_dt": "20240325",
            "odd_pay_dt": "",
            "list_date": "",
            "tot_issue_stk_qty": "     1885394",
            "issue_stk_qty": "    18853940",
            "stk_kind": "01"
        },
        {
            "record_date": "20240315",
            "sht_cd": "473980",
            "isin_name": "노머스",
            "fix_rate": "3900.0",
            "odd_rec_price": "000000000",
            "right_dt": "20240314",
            "odd_pay_dt": "",
            "list_date": "",
            "tot_issue_stk_qty": "      234220",
            "issue_stk_qty": "     9134580",
            "stk_kind": "01"
        },
        {
            "record_date": "20240314",
            "sht_cd": "377220",
            "isin_name": "프롬바이오",
            "fix_rate": "100.00",
            "odd_rec_price": "000000000",
            "right_dt": "20240313",
            "odd_pay_dt": "",
            "list_date": "20240405",
            "tot_issue_stk_qty": "    14155000",
            "issue_stk_qty": "    14155000",
            "stk_kind": "01"
        },
        {
            "record_date": "20240307",
            "sht_cd": "357230",
            "isin_name": "에이치피오",
            "fix_rate": "100.00",
            "odd_rec_price": "000000000",
            "right_dt": "20240306",
            "odd_pay_dt": "",
            "list_date": "20240329",
            "tot_issue_stk_qty": "    21149725",
            "issue_stk_qty": "    20337240",
            "stk_kind": "01"
        },
        {
            "record_date": "20240305",
            "sht_cd": "005810",
            "isin_name": "풍산홀딩스",
            "fix_rate": " 50.00",
            "odd_rec_price": "000029850",
            "right_dt": "20240304",
            "odd_pay_dt": "2024/03/29 ~ 2024/03/29",
            "list_date": "20240322",
            "tot_issue_stk_qty": "     9748528",
            "issue_stk_qty": "     4668764",
            "stk_kind": "01"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식 증권사별 투자의견

- **TR_ID**: FHKST663400C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/invest-opbysec`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:J
FID_COND_SCR_DIV_CODE:16633
FID_INPUT_ISCD:999
FID_DIV_CLS_CODE:0
FID_INPUT_DATE_1:20240428
FID_INPUT_DATE_2:20240528 |  |
| Response Example | {
    "output": [
        {
            "stck_bsop_date": "20240527",
            "stck_shrn_iscd": "454910",
            "hts_kor_isnm": "두산로보틱스",
            "invt_opnn": "NotRated",
            "invt_opnn_cls_code": "3",
            "rgbf_invt_opnn": "NotRated",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "상상인",
            "stck_prpr": "74300",
            "prdy_vrss": "500",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.68",
            "hts_goal_prc": "0",
            "stck_prdy_clpr": "71600",
            "stft_esdg": "74300",
            "dprt": "0.00"
        },
        {
            "stck_bsop_date": "20240527",
            "stck_shrn_iscd": "389140",
            "hts_kor_isnm": "포바이포",
            "invt_opnn": "NotRated",
            "invt_opnn_cls_code": "3",
            "rgbf_invt_opnn": "NotRated",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "상상인",
            "stck_prpr": "10330",
            "prdy_vrss": "0",
            "prdy_vrss_sign": "3",
            "prdy_ctrt": "0.00",
            "hts_goal_prc": "0",
            "stck_prdy_clpr": "10120",
            "stft_esdg": "10330",
            "dprt": "0.00"
        },
        {
            "stck_bsop_date": "20240527",
            "stck_shrn_iscd": "336260",
            "hts_kor_isnm": "두산퓨얼셀",
            "invt_opnn": "BUY",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "BUY",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "상상인",
            "stck_prpr": "26150",
            "prdy_vrss": "-50",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-0.19",
            "hts_goal_prc": "33000",
            "stck_prdy_clpr": "25000",
            "stft_esdg": "-6850",
            "dprt": "-20.76"
        },
        {
            "stck_bsop_date": "20240527",
            "stck_shrn_iscd": "298380",
            "hts_kor_isnm": "에이비엘바이오",
            "invt_opnn": "NotRated",
            "invt_opnn_cls_code": "3",
            "rgbf_invt_opnn": "NotRated",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "상상인",
            "stck_prpr": "23300",
            "prdy_vrss": "-100",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-0.43",
            "hts_goal_prc": "0",
            "stck_prdy_clpr": "24300",
            "stft_esdg": "23300",
            "dprt": "0.00"
        },
        {
            "stck_bsop_date": "20240527",
            "stck_shrn_iscd": "377740",
            "hts_kor_isnm": "바이오노트",
            "invt_opnn": "BUY",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "BUY",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "다올투자",
            "stck_prpr": "4135",
            "prdy_vrss": "-10",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-0.24",
            "hts_goal_prc": "5700",
            "stck_prdy_clpr": "4175",
            "stft_esdg": "-1565",
            "dprt": "-27.46"
        },
        {
            "stck_bsop_date": "20240527",
            "stck_shrn_iscd": "137310",
            "hts_kor_isnm": "에스디바이오센서",
            "invt_opnn": "HOLD",
            "invt_opnn_cls_code": "3",
            "rgbf_invt_opnn": "HOLD",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "다올투자",
            "stck_prpr": "10110",
            "prdy_vrss": "60",
            "prdy_vrss_sign": "2",
            "prdy_ctrt": "0.60",
            "hts_goal_prc": "11000",
            "stck_prdy_clpr": "10060",
            "stft_esdg": "-890",
            "dprt": "-8.09"
        },
        {
            "stck_bsop_date": "20240527",
            "stck_shrn_iscd": "298020",
            "hts_kor_isnm": "효성티앤씨",
            "invt_opnn": "매수",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "매수",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "IBK투자",
            "stck_prpr": "389000",
            "prdy_vrss": "-19000",
            "prdy_vrss_sign": "5",
            "prdy_ctrt": "-4.66",
            "hts_goal_prc": "550000",
            "stck_prdy_clpr": "400500",
            "stft_esdg": "-161000",
            "dprt": "-29.27"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식 당사 신용가능종목

- **TR_ID**: FHPST04770000
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/credit-by-company`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"J",
"fid_cond_scr_div_code":"20477",
"fid_input_iscd":"0000",
"fid_slct_yn":"0",
"fid_rank_sort_cls_code":"1"
} |  |
| Response Example | {
    "output": [
        {
            "stck_shrn_iscd": "473440",
            "hts_kor_isnm": "ACE 11월만기자동연장회사채AA-이상액티브",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "105190",
            "hts_kor_isnm": "ACE 200",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "332500",
            "hts_kor_isnm": "ACE 200TR",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "448880",
            "hts_kor_isnm": "ACE 24-12 회사채(AA-이상)액티브",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "461270",
            "hts_kor_isnm": "ACE 26-06 회사채(AA-이상)액티브",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "414270",
            "hts_kor_isnm": "ACE G2전기차&자율주행액티브",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "365780",
            "hts_kor_isnm": "ACE 국고채10년",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "446770",
            "hts_kor_isnm": "ACE 글로벌반도체TOP4 Plus SOLACTIVE",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "190620",
            "hts_kor_isnm": "ACE 단기통안채",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "453850",
            "hts_kor_isnm": "ACE 미국30년국채액티브(H)",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "360200",
            "hts_kor_isnm": "ACE 미국S&P500",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "438080",
            "hts_kor_isnm": "ACE 미국S&P500채권혼합액티브",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "309230",
            "hts_kor_isnm": "ACE 미국WideMoat가치주",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "367380",
            "hts_kor_isnm": "ACE 미국나스닥100",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "456880",
            "hts_kor_isnm": "ACE 미국달러SOFR금리(합성)",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "402970",
            "hts_kor_isnm": "ACE 미국배당다우존스",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "465580",
            "hts_kor_isnm": "ACE 미국빅테크TOP7 Plus",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "245710",
            "hts_kor_isnm": "ACE 베트남VN30(합성)",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "448540",
            "hts_kor_isnm": "ACE 엔비디아채권혼합블룸버그",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "238720",
            "hts_kor_isnm": "ACE 일본Nikkei225(H)",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "356540",
            "hts_kor_isnm": "ACE 종합채권(AA-이상)KIS액티브",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "457480",
            "hts_kor_isnm": "ACE 테슬라밸류체인액티브",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "469170",
            "hts_kor_isnm": "ACE 포스코그룹포커스",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "265520",
            "hts_kor_isnm": "AP시스템",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "152100",
            "hts_kor_isnm": "ARIRANG 200",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "453010",
            "hts_kor_isnm": "ARIRANG KOFR금리",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "449450",
            "hts_kor_isnm": "ARIRANG K방산Fn",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "161510",
            "hts_kor_isnm": "ARIRANG 고배당주",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "464470",
            "hts_kor_isnm": "ARIRANG 미국채30년액티브",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "195980",
            "hts_kor_isnm": "ARIRANG 신흥국MSCI(합성 H)",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "421320",
            "hts_kor_isnm": "ARIRANG 우주항공&UAM iSelect",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "328370",
            "hts_kor_isnm": "ARIRANG 코스피TR",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "027410",
            "hts_kor_isnm": "BGF",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "282330",
            "hts_kor_isnm": "BGF리테일",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "126600",
            "hts_kor_isnm": "BGF에코머티리얼즈",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "138930",
            "hts_kor_isnm": "BNK금융지주",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "001040",
            "hts_kor_isnm": "CJ",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "000120",
            "hts_kor_isnm": "CJ대한통운",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "011150",
            "hts_kor_isnm": "CJ씨푸드",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "097950",
            "hts_kor_isnm": "CJ제일제당",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "097955",
            "hts_kor_isnm": "CJ제일제당 우",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "051500",
            "hts_kor_isnm": "CJ프레시웨이",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "058820",
            "hts_kor_isnm": "CMG제약",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "012030",
            "hts_kor_isnm": "DB",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "005830",
            "hts_kor_isnm": "DB손해보험",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "000990",
            "hts_kor_isnm": "DB하이텍",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "139130",
            "hts_kor_isnm": "DGB금융지주",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "001530",
            "hts_kor_isnm": "DI동일",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "375500",
            "hts_kor_isnm": "DL이앤씨",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "068790",
            "hts_kor_isnm": "DMS",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "007340",
            "hts_kor_isnm": "DN오토모티브",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "241520",
            "hts_kor_isnm": "DSC인베스트먼트",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "017940",
            "hts_kor_isnm": "E1",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "007700",
            "hts_kor_isnm": "F&F홀딩스",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "078930",
            "hts_kor_isnm": "GS",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "001250",
            "hts_kor_isnm": "GS글로벌",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "007070",
            "hts_kor_isnm": "GS리테일",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "293180",
            "hts_kor_isnm": "HANARO 200",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "454320",
            "hts_kor_isnm": "HANARO CAPEX설비투자iSelect",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "395290",
            "hts_kor_isnm": "HANARO Fn K-POP&미디어",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "395270",
            "hts_kor_isnm": "HANARO Fn K-반도체",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "441540",
            "hts_kor_isnm": "HANARO Fn조선해운",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "434730",
            "hts_kor_isnm": "HANARO 원자력iSelect",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "078150",
            "hts_kor_isnm": "HB테크놀러지",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "089470",
            "hts_kor_isnm": "HDC현대EP",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "009540",
            "hts_kor_isnm": "HD한국조선해양",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "267250",
            "hts_kor_isnm": "HD현대",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "267270",
            "hts_kor_isnm": "HD현대건설기계",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "322000",
            "hts_kor_isnm": "HD현대에너지솔루션",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "042670",
            "hts_kor_isnm": "HD현대인프라코어",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "329180",
            "hts_kor_isnm": "HD현대중공업",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "195940",
            "hts_kor_isnm": "HK이노엔",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "204320",
            "hts_kor_isnm": "HL만도",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "060980",
            "hts_kor_isnm": "HL홀딩스",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "011200",
            "hts_kor_isnm": "HMM",
            "crdt_rate": "20.00"
        },
        {
            "stck_shrn_iscd": "036640",
            "hts_kor_isnm": "HRS",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "095340",
            "hts_kor_isnm": "ISC",
            "crdt_rate": "60.00"
        },
        {
            "stck_shrn_iscd": "175330",
            "hts_kor_isnm": "JB금융지주",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "234080",
            "hts_kor_isnm": "JW생명과학",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "035900",
            "hts_kor_isnm": "JYP Ent.",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "148020",
            "hts_kor_isnm": "KBSTAR 200",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "448600",
            "hts_kor_isnm": "KBSTAR 25-11 회사채(AA-이상)액티브",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "465330",
            "hts_kor_isnm": "KBSTAR 2차전지TOP10",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "422420",
            "hts_kor_isnm": "KBSTAR 2차전지액티브",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "469070",
            "hts_kor_isnm": "KBSTAR AI&로봇",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "290130",
            "hts_kor_isnm": "KBSTAR ESG사회책임투자",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "367760",
            "hts_kor_isnm": "KBSTAR Fn5G테크",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "367770",
            "hts_kor_isnm": "KBSTAR Fn수소경제테마",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "326240",
            "hts_kor_isnm": "KBSTAR IT플러스",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "385560",
            "hts_kor_isnm": "KBSTAR KIS국고채30년Enhanced",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "401170",
            "hts_kor_isnm": "KBSTAR iSelect메타버스",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "266160",
            "hts_kor_isnm": "KBSTAR 고배당",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "385550",
            "hts_kor_isnm": "KBSTAR 단기종합채권(AA-이상)액티브",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "196230",
            "hts_kor_isnm": "KBSTAR 단기통안채",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "315960",
            "hts_kor_isnm": "KBSTAR 대형고배당10TR",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "455890",
            "hts_kor_isnm": "KBSTAR 머니마켓액티브",
            "crdt_rate": "30.00"
        },
        {
            "stck_shrn_iscd": "379780",
            "hts_kor_isnm": "KBSTAR 미국S&P500",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "453330",
            "hts_kor_isnm": "KBSTAR 미국S&P500(H)",
            "crdt_rate": "50.00"
        },
        {
            "stck_shrn_iscd": "368590",
            "hts_kor_isnm": "KBSTAR 미국나스닥100",
            "crdt_rate": "40.00"
        },
        {
            "stck_shrn_iscd": "437350",
            "hts_kor_isnm": "KBSTAR 미국단기투자등급회사채액티브",
            "crdt_rate": "40.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 예탁원정보(주식매수청구일정)

- **TR_ID**: HHKDB669103C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/purreq`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230301
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20240313",
            "sht_cd": "065350",
            "isin_name": "신성델타테크",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240326",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240311",
            "sht_cd": "472850",
            "isin_name": "폰드그룹",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240325",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240306",
            "sht_cd": "238930",
            "isin_name": "제이비케이랩",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240319",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240305",
            "sht_cd": "435620",
            "isin_name": "하나금융25호기업인수목적",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240409",
            "buy_req_rcpt_term": "020240430",
            "buy_req_price": "000000010578",
            "buy_amt_pay_dt": "2024/05/16",
            "get_meet_dt": "2024/04/12"
        },
        {
            "record_date": "20240305",
            "sht_cd": "452450",
            "isin_name": "피아이이",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240409",
            "buy_req_rcpt_term": "020240430",
            "buy_req_price": "000000006733",
            "buy_amt_pay_dt": "2024/05/16",
            "get_meet_dt": "2024/04/12"
        },
        {
            "record_date": "20240304",
            "sht_cd": "065150",
            "isin_name": "대산에프앤비",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240327",
            "buy_req_rcpt_term": "020240417",
            "buy_req_price": "000000000260",
            "buy_amt_pay_dt": "2024/05/17",
            "get_meet_dt": "2024/03/29"
        },
        {
            "record_date": "20240229",
            "sht_cd": "034110",
            "isin_name": "조선호텔앤리조트",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240322",
            "buy_req_rcpt_term": "020240412",
            "buy_req_price": "000000016577",
            "buy_amt_pay_dt": "2024/05/14",
            "get_meet_dt": "2024/03/26"
        },
        {
            "record_date": "20240229",
            "sht_cd": "034300",
            "isin_name": "신세계건설",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240322",
            "buy_req_rcpt_term": "020240412",
            "buy_req_price": "000000011865",
            "buy_amt_pay_dt": "2024/05/14",
            "get_meet_dt": "2024/03/26"
        },
        {
            "record_date": "20240228",
            "sht_cd": "011690",
            "isin_name": "와이투솔루션",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240312",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240222",
            "sht_cd": "021240",
            "isin_name": "코웨이",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240320",
            "buy_req_rcpt_term": "020240409",
            "buy_req_price": "000000056357",
            "buy_amt_pay_dt": "2024/05/07",
            "get_meet_dt": "2024/03/22"
        },
        {
            "record_date": "20240222",
            "sht_cd": "035720",
            "isin_name": "카카오",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240307",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240221",
            "sht_cd": "039310",
            "isin_name": "세중",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240305",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240216",
            "sht_cd": "101000",
            "isin_name": "상상인인더스트리",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240308",
            "buy_req_rcpt_term": "020240329",
            "buy_req_price": "000000002310",
            "buy_amt_pay_dt": "2024/04/30",
            "get_meet_dt": "2024/03/12"
        },
        {
            "record_date": "20240216",
            "sht_cd": "101005",
            "isin_name": "상상인인더스트리1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240308",
            "buy_req_rcpt_term": "020240329",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "2024/04/30",
            "get_meet_dt": "2024/03/12"
        },
        {
            "record_date": "20240216",
            "sht_cd": "101007",
            "isin_name": "상상인인더스트리2우",
            "stk_kind": "2우선",
            "opp_opi_rcpt_term": "020240308",
            "buy_req_rcpt_term": "020240329",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "2024/04/30",
            "get_meet_dt": "2024/03/12"
        },
        {
            "record_date": "20240216",
            "sht_cd": "101009",
            "isin_name": "상상인인더스트리3우",
            "stk_kind": "3우선",
            "opp_opi_rcpt_term": "020240308",
            "buy_req_rcpt_term": "020240329",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "2024/04/30",
            "get_meet_dt": "2024/03/12"
        },
        {
            "record_date": "20240214",
            "sht_cd": "053300",
            "isin_name": "한국정보인증",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240322",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240214",
            "sht_cd": "123010",
            "isin_name": "아이윈플러스",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240227",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240214",
            "sht_cd": "123015",
            "isin_name": "아이윈플러스1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240227",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240214",
            "sht_cd": "123017",
            "isin_name": "아이윈플러스2우",
            "stk_kind": "2우선",
            "opp_opi_rcpt_term": "020240227",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240214",
            "sht_cd": "123019",
            "isin_name": "아이윈플러스3우",
            "stk_kind": "3우선",
            "opp_opi_rcpt_term": "020240227",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240214",
            "sht_cd": "12301A",
            "isin_name": "아이윈플러스4우",
            "stk_kind": "4우선",
            "opp_opi_rcpt_term": "020240227",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240208",
            "sht_cd": "044180",
            "isin_name": "KD",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240226",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240208",
            "sht_cd": "095190",
            "isin_name": "이엠코리아",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240222",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240208",
            "sht_cd": "097780",
            "isin_name": "에코볼트",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240222",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240208",
            "sht_cd": "097785",
            "isin_name": "에코볼트1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240222",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240208",
            "sht_cd": "457190",
            "isin_name": "이수스페셜티케미컬",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240221",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240207",
            "sht_cd": "019440",
            "isin_name": "세아특수강",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240220",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240205",
            "sht_cd": "140430",
            "isin_name": "카티스",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240313",
            "buy_req_rcpt_term": "020240403",
            "buy_req_price": "000000003359",
            "buy_amt_pay_dt": "2024/04/12",
            "get_meet_dt": "2024/03/15"
        },
        {
            "record_date": "20240205",
            "sht_cd": "296170",
            "isin_name": "에스엘바이젠",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240219",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240205",
            "sht_cd": "29617K",
            "isin_name": "에스엘바이젠1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240219",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240205",
            "sht_cd": "29617L",
            "isin_name": "에스엘바이젠2우",
            "stk_kind": "2우선",
            "opp_opi_rcpt_term": "020240219",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240205",
            "sht_cd": "29617M",
            "isin_name": "에스엘바이젠3우",
            "stk_kind": "3우선",
            "opp_opi_rcpt_term": "020240219",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240205",
            "sht_cd": "29617N",
            "isin_name": "에스엘바이젠4우",
            "stk_kind": "4우선",
            "opp_opi_rcpt_term": "020240219",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240205",
            "sht_cd": "29617P",
            "isin_name": "에스엘바이젠5우",
            "stk_kind": "5우선",
            "opp_opi_rcpt_term": "020240219",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240205",
            "sht_cd": "419270",
            "isin_name": "신영해피투모로우제7호기업인수목적",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240229",
            "buy_req_rcpt_term": "020240322",
            "buy_req_price": "000000002092",
            "buy_amt_pay_dt": "2024/04/05",
            "get_meet_dt": "2024/03/05"
        },
        {
            "record_date": "20240205",
            "sht_cd": "436530",
            "isin_name": "케이비제22호기업인수목적",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240313",
            "buy_req_rcpt_term": "020240403",
            "buy_req_price": "000000002093",
            "buy_amt_pay_dt": "2024/04/12",
            "get_meet_dt": "2024/03/15"
        },
        {
            "record_date": "20240205",
            "sht_cd": "451250",
            "isin_name": "삐아",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240229",
            "buy_req_rcpt_term": "020240322",
            "buy_req_price": "000000007334",
            "buy_amt_pay_dt": "2024/04/05",
            "get_meet_dt": "2024/03/05"
        },
        {
            "record_date": "20240129",
            "sht_cd": "299910",
            "isin_name": "베스파",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240213",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240126",
            "sht_cd": "217270",
            "isin_name": "넵튠",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240208",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240119",
            "sht_cd": "151860",
            "isin_name": "케이지이티에스",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240208",
            "buy_req_rcpt_term": "020240304",
            "buy_req_price": "000000011116",
            "buy_amt_pay_dt": "2024/04/04",
            "get_meet_dt": "2024/02/14"
        },
        {
            "record_date": "20240118",
            "sht_cd": "391060",
            "isin_name": "엔에이치기업인수목적20호",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240221",
            "buy_req_rcpt_term": "099991229",
            "buy_req_price": "000000010580",
            "buy_amt_pay_dt": "9999/12/31",
            "get_meet_dt": "2024/02/23"
        },
        {
            "record_date": "20240118",
            "sht_cd": "439270",
            "isin_name": "크리에이츠",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240221",
            "buy_req_rcpt_term": "099991229",
            "buy_req_price": "000000024996",
            "buy_amt_pay_dt": "9999/12/31",
            "get_meet_dt": "2024/02/23"
        },
        {
            "record_date": "20240112",
            "sht_cd": "445090",
            "isin_name": "에이직랜드",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240125",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240112",
            "sht_cd": "44509K",
            "isin_name": "에이직랜드1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240125",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240112",
            "sht_cd": "44509L",
            "isin_name": "에이직랜드2우",
            "stk_kind": "2우선",
            "opp_opi_rcpt_term": "020240125",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240111",
            "sht_cd": "177350",
            "isin_name": "베셀",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240111",
            "sht_cd": "17735K",
            "isin_name": "베셀1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240111",
            "sht_cd": "222080",
            "isin_name": "씨아이에스",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240111",
            "sht_cd": "445090",
            "isin_name": "에이직랜드",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240111",
            "sht_cd": "44509K",
            "isin_name": "에이직랜드1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240111",
            "sht_cd": "44509L",
            "isin_name": "에이직랜드2우",
            "stk_kind": "2우선",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20240105",
            "sht_cd": "009730",
            "isin_name": "코센",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240118",
            "buy_req_rcpt_term": "020240213",
            "buy_req_price": "000000003054",
            "buy_amt_pay_dt": "2024/03/13",
            "get_meet_dt": "2024/01/22"
        },
        {
            "record_date": "20240103",
            "sht_cd": "012160",
            "isin_name": "영흥",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240123",
            "buy_req_rcpt_term": "020240213",
            "buy_req_price": "000000000566",
            "buy_amt_pay_dt": "2024/03/13",
            "get_meet_dt": "2024/01/25"
        },
        {
            "record_date": "20240102",
            "sht_cd": "023530",
            "isin_name": "롯데쇼핑",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240115",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231231",
            "sht_cd": "017680",
            "isin_name": "데코앤에프",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240327",
            "buy_req_rcpt_term": "020240417",
            "buy_req_price": "000000063827",
            "buy_amt_pay_dt": "2024/06/17",
            "get_meet_dt": "2024/03/29"
        },
        {
            "record_date": "20231231",
            "sht_cd": "017685",
            "isin_name": "데코앤에프1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240327",
            "buy_req_rcpt_term": "020240417",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "2024/06/17",
            "get_meet_dt": "2024/03/29"
        },
        {
            "record_date": "20231231",
            "sht_cd": "033540",
            "isin_name": "파라텍",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240325",
            "buy_req_rcpt_term": "020240415",
            "buy_req_price": "000000002607",
            "buy_amt_pay_dt": "2024/05/14",
            "get_meet_dt": "2024/03/27"
        },
        {
            "record_date": "20231231",
            "sht_cd": "037710",
            "isin_name": "광주신세계",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240326",
            "buy_req_rcpt_term": "020240416",
            "buy_req_price": "000000030905",
            "buy_amt_pay_dt": "2024/05/10",
            "get_meet_dt": "2024/03/28"
        },
        {
            "record_date": "20231231",
            "sht_cd": "065650",
            "isin_name": "메디프론디비티",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240326",
            "buy_req_rcpt_term": "020240416",
            "buy_req_price": "000000001336",
            "buy_amt_pay_dt": "2024/05/16",
            "get_meet_dt": "2024/03/28"
        },
        {
            "record_date": "20231231",
            "sht_cd": "06565K",
            "isin_name": "메디프론디비티 1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240326",
            "buy_req_rcpt_term": "020240416",
            "buy_req_price": "000000001336",
            "buy_amt_pay_dt": "2024/05/16",
            "get_meet_dt": "2024/03/28"
        },
        {
            "record_date": "20231231",
            "sht_cd": "215000",
            "isin_name": "골프존",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240327",
            "buy_req_rcpt_term": "020240417",
            "buy_req_price": "000000087629",
            "buy_amt_pay_dt": "2024/04/26",
            "get_meet_dt": "2024/03/29"
        },
        {
            "record_date": "20231231",
            "sht_cd": "234690",
            "isin_name": "녹십자웰빙",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240325",
            "buy_req_rcpt_term": "020240415",
            "buy_req_price": "000000009043",
            "buy_amt_pay_dt": "2024/05/10",
            "get_meet_dt": "2024/03/27"
        },
        {
            "record_date": "20231231",
            "sht_cd": "278270",
            "isin_name": "네오임플란트",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240322",
            "buy_req_rcpt_term": "020240412",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "2024/04/30",
            "get_meet_dt": "2024/03/26"
        },
        {
            "record_date": "20231231",
            "sht_cd": "371110",
            "isin_name": "포인트임플란트",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240327",
            "buy_req_rcpt_term": "020240417",
            "buy_req_price": "000000002400",
            "buy_amt_pay_dt": "2024/06/17",
            "get_meet_dt": "2024/03/29"
        },
        {
            "record_date": "20231229",
            "sht_cd": "356950",
            "isin_name": "클래스101",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231229",
            "sht_cd": "35695K",
            "isin_name": "클래스101 1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231229",
            "sht_cd": "35695L",
            "isin_name": "클래스101 2우",
            "stk_kind": "2우선",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231229",
            "sht_cd": "35695M",
            "isin_name": "클래스101 3우",
            "stk_kind": "3우선",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231229",
            "sht_cd": "35695N",
            "isin_name": "클래스101 4우",
            "stk_kind": "4우선",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231229",
            "sht_cd": "35695P",
            "isin_name": "클래스101 5우",
            "stk_kind": "5우선",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231229",
            "sht_cd": "35695Q",
            "isin_name": "클래스101 6우",
            "stk_kind": "6우선",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231229",
            "sht_cd": "35695R",
            "isin_name": "클래스101 7우",
            "stk_kind": "7우선",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231229",
            "sht_cd": "35695S",
            "isin_name": "클래스101 8우",
            "stk_kind": "8우선",
            "opp_opi_rcpt_term": "020240116",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231226",
            "sht_cd": "016880",
            "isin_name": "웅진",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240108",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231222",
            "sht_cd": "397880",
            "isin_name": "교보11호기업인수목적",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240130",
            "buy_req_rcpt_term": "020240220",
            "buy_req_price": "000000002126",
            "buy_amt_pay_dt": "2024/02/29",
            "get_meet_dt": "2024/02/01"
        },
        {
            "record_date": "20231222",
            "sht_cd": "420570",
            "isin_name": "제이투케이바이오",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240130",
            "buy_req_rcpt_term": "020240220",
            "buy_req_price": "000000017267",
            "buy_amt_pay_dt": "2024/02/29",
            "get_meet_dt": "2024/02/01"
        },
        {
            "record_date": "20231214",
            "sht_cd": "227100",
            "isin_name": "에이치앤비디자인",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020231227",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231214",
            "sht_cd": "22710K",
            "isin_name": "에이치앤비디자인1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020231227",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231212",
            "sht_cd": "369370",
            "isin_name": "블리츠웨이",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240108",
            "buy_req_rcpt_term": "020240129",
            "buy_req_price": "000000002022",
            "buy_amt_pay_dt": "2024/02/08",
            "get_meet_dt": "2024/01/10"
        },
        {
            "record_date": "20231211",
            "sht_cd": "041520",
            "isin_name": "이라이콤",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020231221",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231211",
            "sht_cd": "123840",
            "isin_name": "한일진공",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "020240214",
            "buy_req_price": "000000000465",
            "buy_amt_pay_dt": "2024/03/15",
            "get_meet_dt": "2024/01/26"
        },
        {
            "record_date": "20231211",
            "sht_cd": "452240",
            "isin_name": "뉴온",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "020240214",
            "buy_req_price": "000000011964",
            "buy_amt_pay_dt": "2024/02/27",
            "get_meet_dt": "2024/01/26"
        },
        {
            "record_date": "20231211",
            "sht_cd": "45224K",
            "isin_name": "뉴온 1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020240124",
            "buy_req_rcpt_term": "020240214",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "2024/02/27",
            "get_meet_dt": "2024/01/26"
        },
        {
            "record_date": "20231206",
            "sht_cd": "054210",
            "isin_name": "이랜텍",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020231219",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231206",
            "sht_cd": "05421K",
            "isin_name": "이랜텍1우",
            "stk_kind": "우선",
            "opp_opi_rcpt_term": "020231219",
            "buy_req_rcpt_term": "",
            "buy_req_price": "000000000000",
            "buy_amt_pay_dt": "",
            "get_meet_dt": ""
        },
        {
            "record_date": "20231129",
            "sht_cd": "034300",
            "isin_name": "신세계건설",
            "stk_kind": "보통",
            "opp_opi_rcpt_term": "020231220",
            "buy_req_rcpt_term": "020240110",
            "buy_req_price": "000000013424",
            "buy_amt_pay_dt": "2024/01/22",
            "get_meet_dt": "2023/12/22"
        },
        {
            "record_date": "20231129",
            " |  |


### 예탁원정보(액면교체일정)

- **TR_ID**: HHKDB669105C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/rev-split`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230301
t_dt:20240326
sht_cd:
market_gb:1 |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20230823",
            "sht_cd": "001390",
            "isin_name": "케이지케미칼",
            "inter_bf_face_amt": "000005000",
            "inter_af_face_amt": "000001000",
            "td_stop_dt": "2023/08/22 ~ 2023/08/27",
            "list_dt": "2023/08/28"
        },
        {
            "record_date": "20230823",
            "sht_cd": "011690",
            "isin_name": "와이투솔루션",
            "inter_bf_face_amt": "000000500",
            "inter_af_face_amt": "000002500",
            "td_stop_dt": "2023/08/22 ~ 2023/09/11",
            "list_dt": "2023/09/12"
        },
        {
            "record_date": "20230626",
            "sht_cd": "017860",
            "isin_name": "디에스단석",
            "inter_bf_face_amt": "000001000",
            "inter_af_face_amt": "000000500",
            "td_stop_dt": "2023/06/23 ~",
            "list_dt": ""
        },
        {
            "record_date": "20230525",
            "sht_cd": "111380",
            "isin_name": "동인기연",
            "inter_bf_face_amt": "000010000",
            "inter_af_face_amt": "000000100",
            "td_stop_dt": "2023/05/24 ~",
            "list_dt": "2023/11/21"
        },
        {
            "record_date": "20230525",
            "sht_cd": "11138K",
            "isin_name": "동인기연1우",
            "inter_bf_face_amt": "000010000",
            "inter_af_face_amt": "000000100",
            "td_stop_dt": "2023/05/24 ~",
            "list_dt": "2023/11/21"
        },
        {
            "record_date": "20230509",
            "sht_cd": "002900",
            "isin_name": "티와이엠",
            "inter_bf_face_amt": "000000500",
            "inter_af_face_amt": "000002500",
            "td_stop_dt": "2023/05/08 ~ 2023/05/21",
            "list_dt": "2023/05/22"
        },
        {
            "record_date": "20230503",
            "sht_cd": "001140",
            "isin_name": "국보",
            "inter_bf_face_amt": "000000500",
            "inter_af_face_amt": "000005000",
            "td_stop_dt": "2023/05/02 ~ 2023/05/22",
            "list_dt": "2023/05/23"
        },
        {
            "record_date": "20230502",
            "sht_cd": "001440",
            "isin_name": "대한전선",
            "inter_bf_face_amt": "000000100",
            "inter_af_face_amt": "000001000",
            "td_stop_dt": "2023/04/28 ~ 2023/05/15",
            "list_dt": "2023/05/16"
        },
        {
            "record_date": "20230420",
            "sht_cd": "016590",
            "isin_name": "신대양제지",
            "inter_bf_face_amt": "000005000",
            "inter_af_face_amt": "000000500",
            "td_stop_dt": "2023/04/19 ~ 2023/04/23",
            "list_dt": "2023/04/24"
        },
        {
            "record_date": "20230414",
            "sht_cd": "049770",
            "isin_name": "동원에프앤비",
            "inter_bf_face_amt": "000005000",
            "inter_af_face_amt": "000001000",
            "td_stop_dt": "2023/04/13 ~ 2023/04/18",
            "list_dt": "2023/04/19"
        },
        {
            "record_date": "20230413",
            "sht_cd": "003120",
            "isin_name": "일성신약",
            "inter_bf_face_amt": "000005000",
            "inter_af_face_amt": "000001000",
            "td_stop_dt": "2023/04/12 ~ 2023/04/16",
            "list_dt": "2023/04/17"
        },
        {
            "record_date": "20230413",
            "sht_cd": "007120",
            "isin_name": "미래아이앤지",
            "inter_bf_face_amt": "000000100",
            "inter_af_face_amt": "000000500",
            "td_stop_dt": "2023/04/12 ~ 2023/05/03",
            "list_dt": "2023/05/04"
        },
        {
            "record_date": "20230411",
            "sht_cd": "002200",
            "isin_name": "한국수출포장공업",
            "inter_bf_face_amt": "000005000",
            "inter_af_face_amt": "000000500",
            "td_stop_dt": "2023/04/10 ~ 2023/04/16",
            "list_dt": "2023/04/17"
        },
        {
            "record_date": "20230410",
            "sht_cd": "380440",
            "isin_name": "엔에이치기업인수목적19호",
            "inter_bf_face_amt": "000000100",
            "inter_af_face_amt": "000000500",
            "td_stop_dt": "2023/04/07 ~ 2023/05/01",
            "list_dt": "2023/05/02"
        },
        {
            "record_date": "20230407",
            "sht_cd": "000480",
            "isin_name": "시알홀딩스",
            "inter_bf_face_amt": "000005000",
            "inter_af_face_amt": "000000500",
            "td_stop_dt": "2023/04/06 ~ 2023/04/12",
            "list_dt": "2023/04/13"
        },
        {
            "record_date": "20230407",
            "sht_cd": "003200",
            "isin_name": "일신방직",
            "inter_bf_face_amt": "000005000",
            "inter_af_face_amt": "000000500",
            "td_stop_dt": "2023/04/06 ~ 2023/04/13",
            "list_dt": "2023/04/14"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 예탁원정보(배당일정)

- **TR_ID**: HHKDB669102C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/dividend`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
gb1:0
f_dt:20230301
t_dt:20240326
sht_cd:
high_gb:0 |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20240326",
            "sht_cd": "000720",
            "isin_name": "현대건설",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000600",
            "divi_rate": " 12.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240326",
            "sht_cd": "000725",
            "isin_name": "현대건설1우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000650",
            "divi_rate": " 13.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240326",
            "sht_cd": "003540",
            "isin_name": "대신증권",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000001200",
            "divi_rate": " 24.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/16",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240326",
            "sht_cd": "003545",
            "isin_name": "대신증권1우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000001250",
            "divi_rate": " 25.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/16",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240326",
            "sht_cd": "003547",
            "isin_name": "대신증권2우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000001200",
            "divi_rate": " 24.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/16",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "2우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240326",
            "sht_cd": "012510",
            "isin_name": "더존비즈온",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000217",
            "divi_rate": " 43.40",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/15",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240326",
            "sht_cd": "01251K",
            "isin_name": "더존비즈온2우",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000004861",
            "divi_rate": "972.20",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/15",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "2우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240325",
            "sht_cd": "012330",
            "isin_name": "현대모비스",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000003500",
            "divi_rate": " 70.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240325",
            "sht_cd": "012335",
            "isin_name": "현대모비스1우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000003550",
            "divi_rate": " 71.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240322",
            "sht_cd": "030210",
            "isin_name": "다올투자증권",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000150",
            "divi_rate": "  3.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/09",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240322",
            "sht_cd": "03021K",
            "isin_name": "다올투자증권3우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000356",
            "divi_rate": "  7.14",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/09",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "3우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240322",
            "sht_cd": "03021L",
            "isin_name": "다올투자증권4우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000295",
            "divi_rate": "  5.91",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/09",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "4우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240321",
            "sht_cd": "006840",
            "isin_name": "에이케이홀딩스",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000200",
            "divi_rate": "  4.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240321",
            "sht_cd": "014680",
            "isin_name": "한솔케미칼",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000002100",
            "divi_rate": " 42.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/08",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240321",
            "sht_cd": "380440",
            "isin_name": "엔에이치기업인수목적19호",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000000",
            "divi_rate": "  0.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240320",
            "sht_cd": "000270",
            "isin_name": "기아",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000005600",
            "divi_rate": "112.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/15",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240320",
            "sht_cd": "276970",
            "isin_name": "삼성KODEX 미국S&P500배당귀족커버드콜증권",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000130",
            "divi_rate": "  1.30",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/22",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240315",
            "sht_cd": "012690",
            "isin_name": "모나리자",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000050",
            "divi_rate": " 10.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/11",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240315",
            "sht_cd": "474220",
            "isin_name": "미래에셋TIGER미국테크TOP10+10%프리미엄증",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000092",
            "divi_rate": "  0.92",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/19",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240311",
            "sht_cd": "028100",
            "isin_name": "동아지질",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000500",
            "divi_rate": "100.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240311",
            "sht_cd": "267790",
            "isin_name": "배럴",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000050",
            "divi_rate": " 10.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/16",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240311",
            "sht_cd": "26779L",
            "isin_name": "배럴 2우",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000112",
            "divi_rate": " 22.40",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/16",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "2우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "114100",
            "isin_name": "KB KBSTAR 국고채3년 증권 상장지수 투자신",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000720",
            "divi_rate": "  0.70",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "114460",
            "isin_name": "한국투자ACE국고채증권상장지수투자신탁(채",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000580",
            "divi_rate": "  0.56",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "114470",
            "isin_name": "키움 KOSEF 국고채 상장지수증권투자신탁[",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000580",
            "divi_rate": "  0.57",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/13",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "114820",
            "isin_name": "미래에셋TIGER국채3증권상장지수투자신탁(",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000518",
            "divi_rate": "  0.50",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "346000",
            "isin_name": "NH-Amundi HANARO KAP 초장기국고채 증권 ",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000354",
            "divi_rate": "  0.71",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "385560",
            "isin_name": "KB KBSTAR KIS국고채30년Enhanced 증권 상",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000001570",
            "divi_rate": "  1.57",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "464230",
            "isin_name": "키움히어로즈24-09회사채(AA-이상)액티브증",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000300",
            "divi_rate": "  0.60",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/13",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "464240",
            "isin_name": "키움히어로즈26-09회사채(AA-이상)액티브증",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000300",
            "divi_rate": "  0.60",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/13",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240308",
            "sht_cd": "467620",
            "isin_name": "키움히어로즈25-09미국달러채권(AA-이상)액",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000200",
            "divi_rate": "  0.40",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/13",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240307",
            "sht_cd": "042700",
            "isin_name": "한미반도체",
            "divi_kind": "결산",
            "face_val": "000000100",
            "per_sto_divi_amt": "000000000420",
            "divi_rate": "420.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/29",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240306",
            "sht_cd": "004310",
            "isin_name": "현대약품",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000035",
            "divi_rate": "  7.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/27",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240305",
            "sht_cd": "152550",
            "isin_name": "한국투자ANKOR유전해외자원개발특별자산투",
            "divi_kind": "결산",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000000",
            "divi_rate": "  0.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240305",
            "sht_cd": "377630",
            "isin_name": "삼성기업인수목적4호",
            "divi_kind": "결산",
            "face_val": "000000100",
            "per_sto_divi_amt": "000000000000",
            "divi_rate": "2079.0",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240301",
            "sht_cd": "002900",
            "isin_name": "티와이엠",
            "divi_kind": "결산",
            "face_val": "000002500",
            "per_sto_divi_amt": "000000000110",
            "divi_rate": "  4.40",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/19",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240301",
            "sht_cd": "084870",
            "isin_name": "티비에이치글로벌",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000050",
            "divi_rate": " 10.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "002380",
            "isin_name": "케이씨씨",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000007000",
            "divi_rate": "140.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "005380",
            "isin_name": "현대자동차",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000008400",
            "divi_rate": "168.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/19",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "005385",
            "isin_name": "현대자동차1우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000008450",
            "divi_rate": "169.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/19",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "005387",
            "isin_name": "현대자동차2우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000008500",
            "divi_rate": "170.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/19",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "2우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "005389",
            "isin_name": "현대자동차3우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000008450",
            "divi_rate": "169.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/19",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "3우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "005490",
            "isin_name": "포스코홀딩스",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000002500",
            "divi_rate": " 50.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "007340",
            "isin_name": "디엔오토모티브",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000002500",
            "divi_rate": "500.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "035720",
            "isin_name": "카카오",
            "divi_kind": "결산",
            "face_val": "000000100",
            "per_sto_divi_amt": "000000000061",
            "divi_rate": " 61.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "092870",
            "isin_name": "엑시콘",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000100",
            "divi_rate": " 20.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/16",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "097950",
            "isin_name": "씨제이제일제당",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000002500",
            "divi_rate": " 50.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "097955",
            "isin_name": "씨제이제일제당1우",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000002550",
            "divi_rate": " 51.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "105560",
            "isin_name": "KB금융지주",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000001530",
            "divi_rate": " 30.60",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/11",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "136340",
            "isin_name": "KB KBSTAR 중기우량회사채 증권 상장지수 ",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000370",
            "divi_rate": "  0.37",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "138930",
            "isin_name": "BNK금융지주",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000410",
            "divi_rate": "  8.20",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "139130",
            "isin_name": "DGB금융지주",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000550",
            "divi_rate": " 11.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "148150",
            "isin_name": "세경하이테크",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000100",
            "divi_rate": " 20.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "14815K",
            "isin_name": "세경하이테크1우",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000180",
            "divi_rate": " 36.17",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/12",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "우선",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "166400",
            "isin_name": "미래에셋 TIGER 200커버드콜5%OTM 증권상장",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000060",
            "divi_rate": "  0.60",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "175330",
            "isin_name": "JB금융지주",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000735",
            "divi_rate": " 14.70",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "182480",
            "isin_name": "미래에셋TIGERMSCIUS리츠부동산상장지수투",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000040",
            "divi_rate": "  0.40",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "245340",
            "isin_name": "미래에셋TIGER미국다우존스30증권상장지수",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000020",
            "divi_rate": "  0.20",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "246250",
            "isin_name": "에스엘에스바이오",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000000050",
            "divi_rate": " 10.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/15",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "251600",
            "isin_name": "한화ARIRANG고배당주채권혼합증권상장지수",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000030",
            "divi_rate": "  0.30",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "271830",
            "isin_name": "팸텍",
            "divi_kind": "결산",
            "face_val": "000000100",
            "per_sto_divi_amt": "000000000030",
            "divi_rate": " 30.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/19",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "282690",
            "isin_name": "동아타이어공업(신설)",
            "divi_kind": "결산",
            "face_val": "000000500",
            "per_sto_divi_amt": "000000001000",
            "divi_rate": "200.00",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "289480",
            "isin_name": "미래에셋TIGER200커버드콜ATM증권상장지수",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000062",
            "divi_rate": "  0.62",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "290080",
            "isin_name": "KB KBSTAR 200 고배당 커버드콜 ATM 증권 ",
            "divi_kind": "",
            "face_val": "000000000",
            "per_sto_divi_amt": "000000000053",
            "divi_rate": "  0.53",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/03/05",
            "stk_div_pay_dt": "",
            "odd_pay_dt": "",
            "stk_kind": "보통",
            "high_divi_gb": ""
        },
        {
            "record_date": "20240229",
            "sht_cd": "316140",
            "isin_name": "우리금융지주",
            "divi_kind": "결산",
            "face_val": "000005000",
            "per_sto_divi_amt": "000000000640",
            "divi_rate": " 12.80",
            "stk_divi_rate": "  0.00",
            "divi_pay_dt": "2024/04/09",
            "stk_div_pay_dt": "", |  |


### 국내주식 종목투자의견

- **TR_ID**: FHKST663300C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/invest-opinion`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | FID_COND_MRKT_DIV_CODE:J
FID_COND_SCR_DIV_CODE:16633
FID_INPUT_ISCD:005930
FID_INPUT_DATE_1:20240101
FID_INPUT_DATE_2:20240528 |  |
| Response Example | {
    "output": [
        {
            "stck_bsop_date": "20240527",
            "invt_opnn": "매수",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "매수",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "SK",
            "hts_goal_prc": "105000",
            "stck_prdy_clpr": "75900",
            "stck_nday_esdg": "-29100",
            "nday_dprt": "-27.71",
            "stft_esdg": "-27400",
            "dprt": "-26.10"
        },
        {
            "stck_bsop_date": "20240520",
            "invt_opnn": "BUY",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "BUY",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "하이투자",
            "hts_goal_prc": "91000",
            "stck_prdy_clpr": "77400",
            "stck_nday_esdg": "-13600",
            "nday_dprt": "-14.95",
            "stft_esdg": "-13400",
            "dprt": "-14.73"
        },
        {
            "stck_bsop_date": "20240516",
            "invt_opnn": "매수",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "매수",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "미래에셋",
            "hts_goal_prc": "110000",
            "stck_prdy_clpr": "78300",
            "stck_nday_esdg": "-31700",
            "nday_dprt": "-28.82",
            "stft_esdg": "-32400",
            "dprt": "-29.45"
        },
        {
            "stck_bsop_date": "20240502",
            "invt_opnn": "BUY",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "BUY",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "다올투자",
            "hts_goal_prc": "105000",
            "stck_prdy_clpr": "77500",
            "stck_nday_esdg": "-27500",
            "nday_dprt": "-26.19",
            "stft_esdg": "-27400",
            "dprt": "-26.10"
        },
        {
            "stck_bsop_date": "20240502",
            "invt_opnn": "BUY",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "BUY",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "하이투자",
            "hts_goal_prc": "95000",
            "stck_prdy_clpr": "77500",
            "stck_nday_esdg": "-17500",
            "nday_dprt": "-18.42",
            "stft_esdg": "-17400",
            "dprt": "-18.32"
        },
        {
            "stck_bsop_date": "20240502",
            "invt_opnn": "BUY",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "BUY",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "KB",
            "hts_goal_prc": "120000",
            "stck_prdy_clpr": "77500",
            "stck_nday_esdg": "-42500",
            "nday_dprt": "-35.42",
            "stft_esdg": "-42400",
            "dprt": "-35.33"
        },
        {
            "stck_bsop_date": "20240502",
            "invt_opnn": "매수",
            "invt_opnn_cls_code": "2",
            "rgbf_invt_opnn": "매수",
            "rgbf_invt_opnn_cls_code": "3",
            "mbcr_name": "신한투자증권",
            "hts_goal_prc": "110000",
            "stck_prdy_clpr": "77500",
            "stck_nday_esdg": "-32500",
            "nday_dprt": "-29.55",
            "stft_esdg": "-32400",
            "dprt": "-29.45"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식 안정성비율

- **TR_ID**: FHKST66430600
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/finance/stability-ratio`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"J",
"fid_input_iscd":"005930",
"fid_div_cls_code":"1"
} |  |
| Response Example | {
    "output": [
        {
            "stac_yymm": "202312",
            "lblt_rate": "25.36",
            "bram_depn": "2.78",
            "crnt_rate": "258.77",
            "quck_rate": "190.59"
        },
        {
            "stac_yymm": "202309",
            "lblt_rate": "24.89",
            "bram_depn": "2.21",
            "crnt_rate": "280.39",
            "quck_rate": "205.34"
        },
        {
            "stac_yymm": "202306",
            "lblt_rate": "24.80",
            "bram_depn": "2.04",
            "crnt_rate": "288.18",
            "quck_rate": "209.76"
        },
        {
            "stac_yymm": "202303",
            "lblt_rate": "26.21",
            "bram_depn": "2.19",
            "crnt_rate": "281.95",
            "quck_rate": "210.40"
        },
        {
            "stac_yymm": "202212",
            "lblt_rate": "26.41",
            "bram_depn": "2.30",
            "crnt_rate": "278.86",
            "quck_rate": "212.24"
        },
        {
            "stac_yymm": "202209",
            "lblt_rate": "36.35",
            "bram_depn": "2.65",
            "crnt_rate": "294.17",
            "quck_rate": "226.96"
        },
        {
            "stac_yymm": "202206",
            "lblt_rate": "36.64",
            "bram_depn": "3.89",
            "crnt_rate": "283.45",
            "quck_rate": "220.96"
        },
        {
            "stac_yymm": "202203",
            "lblt_rate": "39.34",
            "bram_depn": "4.11",
            "crnt_rate": "256.86",
            "quck_rate": "204.26"
        },
        {
            "stac_yymm": "202112",
            "lblt_rate": "39.92",
            "bram_depn": "4.31",
            "crnt_rate": "247.58",
            "quck_rate": "200.62"
        },
        {
            "stac_yymm": "202109",
            "lblt_rate": "38.30",
            "bram_depn": "4.65",
            "crnt_rate": "259.91",
            "quck_rate": "213.74"
        },
        {
            "stac_yymm": "202106",
            "lblt_rate": "36.29",
            "bram_depn": "4.35",
            "crnt_rate": "263.75",
            "quck_rate": "217.39"
        },
        {
            "stac_yymm": "202103",
            "lblt_rate": "43.23",
            "bram_depn": "5.08",
            "crnt_rate": "232.11",
            "quck_rate": "198.13"
        },
        {
            "stac_yymm": "202012",
            "lblt_rate": "37.07",
            "bram_depn": "5.35",
            "crnt_rate": "262.17",
            "quck_rate": "219.79"
        },
        {
            "stac_yymm": "202009",
            "lblt_rate": "36.09",
            "bram_depn": "5.22",
            "crnt_rate": "278.77",
            "quck_rate": "234.36"
        },
        {
            "stac_yymm": "202006",
            "lblt_rate": "32.67",
            "bram_depn": "4.66",
            "crnt_rate": "300.88",
            "quck_rate": "252.96"
        },
        {
            "stac_yymm": "202003",
            "lblt_rate": "34.19",
            "bram_depn": "4.38",
            "crnt_rate": "288.34",
            "quck_rate": "244.41"
        },
        {
            "stac_yymm": "201912",
            "lblt_rate": "34.12",
            "bram_depn": "5.22",
            "crnt_rate": "284.38",
            "quck_rate": "242.41"
        },
        {
            "stac_yymm": "201909",
            "lblt_rate": "34.14",
            "bram_depn": "4.57",
            "crnt_rate": "293.89",
            "quck_rate": "245.06"
        },
        {
            "stac_yymm": "201906",
            "lblt_rate": "33.05",
            "bram_depn": "4.51",
            "crnt_rate": "292.42",
            "quck_rate": "239.74"
        },
        {
            "stac_yymm": "201903",
            "lblt_rate": "36.27",
            "bram_depn": "3.83",
            "crnt_rate": "263.37",
            "quck_rate": "216.66"
        },
        {
            "stac_yymm": "201812",
            "lblt_rate": "36.97",
            "bram_depn": "4.32",
            "crnt_rate": "252.89",
            "quck_rate": "210.93"
        },
        {
            "stac_yymm": "201809",
            "lblt_rate": "39.28",
            "bram_depn": "6.43",
            "crnt_rate": "235.97",
            "quck_rate": "198.16"
        },
        {
            "stac_yymm": "201806",
            "lblt_rate": "36.70",
            "bram_depn": "5.05",
            "crnt_rate": "239.29",
            "quck_rate": "197.58"
        },
        {
            "stac_yymm": "201803",
            "lblt_rate": "39.96",
            "bram_depn": "4.12",
            "crnt_rate": "226.86",
            "quck_rate": "188.10"
        },
        {
            "stac_yymm": "201712",
            "lblt_rate": "40.68",
            "bram_depn": "6.23",
            "crnt_rate": "218.80",
            "quck_rate": "181.61"
        },
        {
            "stac_yymm": "201709",
            "lblt_rate": "40.76",
            "bram_depn": "6.26",
            "crnt_rate": "219.61",
            "quck_rate": "178.76"
        },
        {
            "stac_yymm": "201706",
            "lblt_rate": "38.31",
            "bram_depn": "6.02",
            "crnt_rate": "226.06",
            "quck_rate": "186.68"
        },
        {
            "stac_yymm": "201703",
            "lblt_rate": "39.20",
            "bram_depn": "5.01",
            "crnt_rate": "227.44",
            "quck_rate": "188.99"
        },
        {
            "stac_yymm": "201612",
            "lblt_rate": "35.87",
            "bram_depn": "5.83",
            "crnt_rate": "258.54",
            "quck_rate": "224.99"
        },
        {
            "stac_yymm": "201609",
            "lblt_rate": "36.17",
            "bram_depn": "5.30",
            "crnt_rate": "261.93",
            "quck_rate": "225.50"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식 수익성비율

- **TR_ID**: FHKST66430400
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/finance/profit-ratio`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"J",
"fid_input_iscd":"005930",
"fid_div_cls_code":"1"
} |  |
| Response Example | {
    "output": [
        {
            "stac_yymm": "202312",
            "cptl_ntin_rate": "3.43",
            "self_cptl_ntin_inrt": "4.14",
            "sale_ntin_rate": "5.98",
            "sale_totl_rate": "30.33"
        },
        {
            "stac_yymm": "202309",
            "cptl_ntin_rate": "2.70",
            "self_cptl_ntin_inrt": "3.22",
            "sale_ntin_rate": "4.78",
            "sale_totl_rate": "29.76"
        },
        {
            "stac_yymm": "202306",
            "cptl_ntin_rate": "1.47",
            "self_cptl_ntin_inrt": "1.70",
            "sale_ntin_rate": "2.67",
            "sale_totl_rate": "29.17"
        },
        {
            "stac_yymm": "202303",
            "cptl_ntin_rate": "1.40",
            "self_cptl_ntin_inrt": "1.61",
            "sale_ntin_rate": "2.47",
            "sale_totl_rate": "27.83"
        },
        {
            "stac_yymm": "202212",
            "cptl_ntin_rate": "12.72",
            "self_cptl_ntin_inrt": "17.07",
            "sale_ntin_rate": "18.41",
            "sale_totl_rate": "37.12"
        },
        {
            "stac_yymm": "202209",
            "cptl_ntin_rate": "9.46",
            "self_cptl_ntin_inrt": "13.18",
            "sale_ntin_rate": "13.73",
            "sale_totl_rate": "38.98"
        },
        {
            "stac_yymm": "202206",
            "cptl_ntin_rate": "10.25",
            "self_cptl_ntin_inrt": "14.36",
            "sale_ntin_rate": "14.47",
            "sale_totl_rate": "39.77"
        },
        {
            "stac_yymm": "202203",
            "cptl_ntin_rate": "10.46",
            "self_cptl_ntin_inrt": "14.77",
            "sale_ntin_rate": "14.56",
            "sale_totl_rate": "39.48"
        },
        {
            "stac_yymm": "202112",
            "cptl_ntin_rate": "9.92",
            "self_cptl_ntin_inrt": "13.92",
            "sale_ntin_rate": "14.27",
            "sale_totl_rate": "40.48"
        },
        {
            "stac_yymm": "202109",
            "cptl_ntin_rate": "9.83",
            "self_cptl_ntin_inrt": "13.72",
            "sale_ntin_rate": "14.32",
            "sale_totl_rate": "40.18"
        },
        {
            "stac_yymm": "202106",
            "cptl_ntin_rate": "8.79",
            "self_cptl_ntin_inrt": "12.21",
            "sale_ntin_rate": "13.00",
            "sale_totl_rate": "39.12"
        },
        {
            "stac_yymm": "202103",
            "cptl_ntin_rate": "7.41",
            "self_cptl_ntin_inrt": "10.64",
            "sale_ntin_rate": "10.92",
            "sale_totl_rate": "36.53"
        },
        {
            "stac_yymm": "202012",
            "cptl_ntin_rate": "7.23",
            "self_cptl_ntin_inrt": "9.99",
            "sale_ntin_rate": "11.15",
            "sale_totl_rate": "38.98"
        },
        {
            "stac_yymm": "202009",
            "cptl_ntin_rate": "7.25",
            "self_cptl_ntin_inrt": "10.02",
            "sale_ntin_rate": "11.30",
            "sale_totl_rate": "39.13"
        },
        {
            "stac_yymm": "202006",
            "cptl_ntin_rate": "5.88",
            "self_cptl_ntin_inrt": "8.04",
            "sale_ntin_rate": "9.64",
            "sale_totl_rate": "38.39"
        },
        {
            "stac_yymm": "202003",
            "cptl_ntin_rate": "5.50",
            "self_cptl_ntin_inrt": "7.62",
            "sale_ntin_rate": "8.83",
            "sale_totl_rate": "37.09"
        },
        {
            "stac_yymm": "201912",
            "cptl_ntin_rate": "6.28",
            "self_cptl_ntin_inrt": "8.69",
            "sale_ntin_rate": "9.44",
            "sale_totl_rate": "36.09"
        },
        {
            "stac_yymm": "201909",
            "cptl_ntin_rate": "6.36",
            "self_cptl_ntin_inrt": "8.76",
            "sale_ntin_rate": "9.68",
            "sale_totl_rate": "36.26"
        },
        {
            "stac_yymm": "201906",
            "cptl_ntin_rate": "5.99",
            "self_cptl_ntin_inrt": "8.30",
            "sale_ntin_rate": "9.42",
            "sale_totl_rate": "36.70"
        },
        {
            "stac_yymm": "201903",
            "cptl_ntin_rate": "5.90",
            "self_cptl_ntin_inrt": "8.41",
            "sale_ntin_rate": "9.63",
            "sale_totl_rate": "37.49"
        },
        {
            "stac_yymm": "201812",
            "cptl_ntin_rate": "13.83",
            "self_cptl_ntin_inrt": "19.63",
            "sale_ntin_rate": "18.19",
            "sale_totl_rate": "45.69"
        },
        {
            "stac_yymm": "201809",
            "cptl_ntin_rate": "14.98",
            "self_cptl_ntin_inrt": "21.47",
            "sale_ntin_rate": "19.45",
            "sale_totl_rate": "46.68"
        },
        {
            "stac_yymm": "201806",
            "cptl_ntin_rate": "14.66",
            "self_cptl_ntin_inrt": "20.88",
            "sale_ntin_rate": "19.10",
            "sale_totl_rate": "46.92"
        },
        {
            "stac_yymm": "201803",
            "cptl_ntin_rate": "15.22",
            "self_cptl_ntin_inrt": "21.96",
            "sale_ntin_rate": "19.30",
            "sale_totl_rate": "47.31"
        },
        {
            "stac_yymm": "201712",
            "cptl_ntin_rate": "14.96",
            "self_cptl_ntin_inrt": "21.01",
            "sale_ntin_rate": "17.61",
            "sale_totl_rate": "46.03"
        },
        {
            "stac_yymm": "201709",
            "cptl_ntin_rate": "14.28",
            "self_cptl_ntin_inrt": "20.06",
            "sale_ntin_rate": "17.24",
            "sale_totl_rate": "46.11"
        },
        {
            "stac_yymm": "201706",
            "cptl_ntin_rate": "13.89",
            "self_cptl_ntin_inrt": "19.25",
            "sale_ntin_rate": "16.80",
            "sale_totl_rate": "45.71"
        },
        {
            "stac_yymm": "201703",
            "cptl_ntin_rate": "11.68",
            "self_cptl_ntin_inrt": "16.21",
            "sale_ntin_rate": "15.20",
            "sale_totl_rate": "44.30"
        },
        {
            "stac_yymm": "201612",
            "cptl_ntin_rate": "9.01",
            "self_cptl_ntin_inrt": "12.48",
            "sale_ntin_rate": "11.26",
            "sale_totl_rate": "40.42"
        },
        {
            "stac_yymm": "201609",
            "cptl_ntin_rate": "8.57",
            "self_cptl_ntin_inrt": "11.94",
            "sale_ntin_rate": "10.53",
            "sale_totl_rate": "39.82"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 예탁원정보(실권주일정)

- **TR_ID**: HHKDB669109C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/forfeit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230301
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20240131",
            "sht_cd": "001440",
            "isin_name": "대한전선",
            "subscr_dt": "2024/03/14 ~ 2024/03/15",
            "subscr_price": "000007460",
            "subscr_stk_qty": "    62000000",
            "refund_dt": "2024/03/19",
            "list_dt": "2024/04/02",
            "lead_mgr": "케이비증권,미래에셋증권,"
        },
        {
            "record_date": "20240131",
            "sht_cd": "001447",
            "isin_name": "대한전선2우",
            "subscr_dt": "2024/03/14 ~ 2024/03/15",
            "subscr_price": "000007460",
            "subscr_stk_qty": "    62000000",
            "refund_dt": "2024/03/19",
            "list_dt": "2024/04/02",
            "lead_mgr": "케이비증권,미래에셋증권,"
        },
        {
            "record_date": "20240131",
            "sht_cd": "001449",
            "isin_name": "대한전선3우",
            "subscr_dt": "2024/03/14 ~ 2024/03/15",
            "subscr_price": "000007460",
            "subscr_stk_qty": "    62000000",
            "refund_dt": "2024/03/19",
            "list_dt": "2024/04/02",
            "lead_mgr": "케이비증권,미래에셋증권,"
        },
        {
            "record_date": "20240131",
            "sht_cd": "00144A",
            "isin_name": "대한전선4우",
            "subscr_dt": "2024/03/14 ~ 2024/03/15",
            "subscr_price": "000007460",
            "subscr_stk_qty": "    62000000",
            "refund_dt": "2024/03/19",
            "list_dt": "2024/04/02",
            "lead_mgr": "케이비증권,미래에셋증권,"
        },
        {
            "record_date": "20240131",
            "sht_cd": "00144K",
            "isin_name": "대한전선5우",
            "subscr_dt": "2024/03/14 ~ 2024/03/15",
            "subscr_price": "000007460",
            "subscr_stk_qty": "    62000000",
            "refund_dt": "2024/03/19",
            "list_dt": "2024/04/02",
            "lead_mgr": "케이비증권,미래에셋증권,"
        },
        {
            "record_date": "20240126",
            "sht_cd": "034220",
            "isin_name": "LG디스플레이",
            "subscr_dt": "2024/03/11 ~ 2024/03/12",
            "subscr_price": "000009090",
            "subscr_stk_qty": "   142184300",
            "refund_dt": "2024/03/14",
            "list_dt": "2024/03/26",
            "lead_mgr": "한국투자증권,NH투자증권,"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 예탁원정보(의무예치일정)

- **TR_ID**: HHKDB669110C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/mand-deposit`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230301
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "sht_cd": "27322R",
            "isin_name": "뷰텔7우",
            "stk_qty": "       68966",
            "depo_date": "2024/03/26 ~ 2025/03/26",
            "depo_reason": "모집매출",
            "tot_issue_qty_per_rate": "10000"
        },
        {
            "sht_cd": "455900",
            "isin_name": "엔젤로보틱스",
            "stk_qty": "       48000",
            "depo_date": "2024/03/26 ~ 2024/06/26",
            "depo_reason": "-",
            "tot_issue_qty_per_rate": "33.51"
        },
        {
            "sht_cd": "455900",
            "isin_name": "엔젤로보틱스",
            "stk_qty": "     4224840",
            "depo_date": "2024/03/26 ~ 2027/03/26",
            "depo_reason": "최대주주",
            "tot_issue_qty_per_rate": "3014."
        },
        {
            "sht_cd": "455900",
            "isin_name": "엔젤로보틱스",
            "stk_qty": "      307036",
            "depo_date": "2024/03/26 ~ 2024/04/26",
            "depo_reason": "최대주주",
            "tot_issue_qty_per_rate": "214.3"
        },
        {
            "sht_cd": "45590S",
            "isin_name": "엔젤로보틱스 8우",
            "stk_qty": "       65128",
            "depo_date": "2024/03/26 ~ 2024/04/26",
            "depo_reason": "벤처금융",
            "tot_issue_qty_per_rate": "700.0"
        },
        {
            "sht_cd": "45590S",
            "isin_name": "엔젤로보틱스 8우",
            "stk_qty": "      865277",
            "depo_date": "2024/03/26 ~ 2024/04/26",
            "depo_reason": "최대주주",
            "tot_issue_qty_per_rate": "9300."
        },
        {
            "sht_cd": "119650",
            "isin_name": "케이씨코트렐",
            "stk_qty": "    12733857",
            "depo_date": "2024/03/25 ~ 2025/03/25",
            "depo_reason": "모집매출",
            "tot_issue_qty_per_rate": "2000."
        },
        {
            "sht_cd": "123840",
            "isin_name": "뉴온",
            "stk_qty": "    62516803",
            "depo_date": "2024/03/25 ~ 2024/09/25",
            "depo_reason": "-",
            "tot_issue_qty_per_rate": "2253."
        },
        {
            "sht_cd": "420570",
            "isin_name": "제이투케이바이오",
            "stk_qty": "         951",
            "depo_date": "2024/03/25 ~ 2024/09/25",
            "depo_reason": "-",
            "tot_issue_qty_per_rate": " 1.71"
        },
        {
            "sht_cd": "019570",
            "isin_name": "리더스기술투자",
            "stk_qty": "     8905532",
            "depo_date": "2024/03/22 ~ 2025/03/22",
            "depo_reason": "-",
            "tot_issue_qty_per_rate": "1697."
        },
        {
            "sht_cd": "036180",
            "isin_name": "지더블유바이텍",
            "stk_qty": "    28911564",
            "depo_date": "2024/03/22 ~ 2025/03/22",
            "depo_reason": "모집매출",
            "tot_issue_qty_per_rate": "3160."
        },
        {
            "sht_cd": "069110",
            "isin_name": "코스온",
            "stk_qty": "     4000000",
            "depo_date": "2024/03/22 ~ 2025/03/22",
            "depo_reason": "모집매출",
            "tot_issue_qty_per_rate": "1107."
        },
        {
            "sht_cd": "440110",
            "isin_name": "파두",
            "stk_qty": "      270200",
            "depo_date": "2024/03/22 ~ 2024/08/07",
            "depo_reason": "-",
            "tot_issue_qty_per_rate": "55.06"
        },
        {
            "sht_cd": "222080",
            "isin_name": "씨아이에스",
            "stk_qty": "       42636",
            "depo_date": "2024/03/21 ~ 2024/09/21",
            "depo_reason": "-",
            "tot_issue_qty_per_rate": " 5.97"
        },
        {
            "sht_cd": "245620",
            "isin_name": "이원다이애그노믹스",
            "stk_qty": "    17633408",
            "depo_date": "2024/03/21 ~ 2025/03/21",
            "depo_reason": "모집매출",
            "tot_issue_qty_per_rate": "1273."
        },
        {
            "sht_cd": "437730",
            "isin_name": "삼현",
            "stk_qty": "       33333",
            "depo_date": "2024/03/21 ~ 2024/06/21",
            "depo_reason": "-",
            "tot_issue_qty_per_rate": "31.54"
        },
        {
            "sht_cd": "437730",
            "isin_name": "삼현",
            "stk_qty": "      390320",
            "depo_date": "2024/03/21 ~ 2024/04/21",
            "depo_reason": "벤처금융",
            "tot_issue_qty_per_rate": "369.3"
        },
        {
            "sht_cd": "476180",
            "isin_name": "마이공사",
            "stk_qty": "      100000",
            "depo_date": "2024/03/20 ~ 2024/09/20",
            "depo_reason": "-",
            "tot_issue_qty_per_rate": "2000."
        },
        {
            "sht_cd": "082740",
            "isin_name": "한화엔진 주식회사",
            "stk_qty": "    11903148",
            "depo_date": "2024/03/19 ~ 2025/03/19",
            "depo_reason": "모집매출",
            "tot_issue_qty_per_rate": "1426."
        },
        {
            "sht_cd": "214870",
            "isin_name": "뉴지랩파마",
            "stk_qty": "    13670000",
            "depo_date": "2024/03/18 ~ 2025/03/18",
            "depo_reason": "모집매출",
            "tot_issue_qty_per_rate": "2921."
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식 손익계산서

- **TR_ID**: FHKST66430200
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/finance/income-statement`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"J",
"fid_input_iscd":"005930",
"fid_div_cls_code":"1"
} |  |
| Response Example | {
    "output": [
        {
            "stac_yymm": "202312",
            "sale_account": "2589355.00",
            "sale_cost": "1803886.00",
            "sale_totl_prfi": "785469",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "65670.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "110063.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "154871.00"
        },
        {
            "stac_yymm": "202309",
            "sale_account": "1911556.00",
            "sale_cost": "1342731.00",
            "sale_totl_prfi": "568825",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "37423.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "74820.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "91423.00"
        },
        {
            "stac_yymm": "202306",
            "sale_account": "1237509.00",
            "sale_cost": "876543.00",
            "sale_totl_prfi": "360966",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "13087.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "35394.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "32982.00"
        },
        {
            "stac_yymm": "202303",
            "sale_account": "637454.00",
            "sale_cost": "460071.00",
            "sale_totl_prfi": "177383",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "6402.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "18264.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "15746.00"
        },
        {
            "stac_yymm": "202212",
            "sale_account": "3022314.00",
            "sale_cost": "1900418.00",
            "sale_totl_prfi": "1121896",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "433766.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "464405.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "556541.00"
        },
        {
            "stac_yymm": "202209",
            "sale_account": "2317668.00",
            "sale_cost": "1414141.00",
            "sale_totl_prfi": "903527",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "390705.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "413856.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "318126.00"
        },
        {
            "stac_yymm": "202206",
            "sale_account": "1549851.00",
            "sale_cost": "933418.00",
            "sale_totl_prfi": "616433",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "282185.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "295306.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "224234.00"
        },
        {
            "stac_yymm": "202203",
            "sale_account": "777815.00",
            "sale_cost": "470721.00",
            "sale_totl_prfi": "307094",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "141214.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "150698.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "113246.00"
        },
        {
            "stac_yymm": "202112",
            "sale_account": "2796048.00",
            "sale_cost": "1664113.00",
            "sale_totl_prfi": "1131935",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "516339.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "533518.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "399075.00"
        },
        {
            "stac_yymm": "202109",
            "sale_account": "2030393.00",
            "sale_cost": "1214648.00",
            "sale_totl_prfi": "815745",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "377671.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "389889.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "290695.00"
        },
        {
            "stac_yymm": "202106",
            "sale_account": "1290601.00",
            "sale_cost": "785659.00",
            "sale_totl_prfi": "504942",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "219496.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "226331.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "167762.00"
        },
        {
            "stac_yymm": "202103",
            "sale_account": "653885.00",
            "sale_cost": "415000.00",
            "sale_totl_prfi": "238885",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "93829.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "97506.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "71417.00"
        },
        {
            "stac_yymm": "202012",
            "sale_account": "2368070.00",
            "sale_cost": "1444883.00",
            "sale_totl_prfi": "923187",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "359939.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "363451.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "264078.00"
        },
        {
            "stac_yymm": "202009",
            "sale_account": "1752555.00",
            "sale_cost": "1066834.00",
            "sale_totl_prfi": "685721",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "269469.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "273707.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "198007.00"
        },
        {
            "stac_yymm": "202006",
            "sale_account": "1082913.00",
            "sale_cost": "667129.00",
            "sale_totl_prfi": "415784",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "145936.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "145265.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "104400.00"
        },
        {
            "stac_yymm": "202003",
            "sale_account": "553252.00",
            "sale_cost": "348067.00",
            "sale_totl_prfi": "205185",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "64473.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "67569.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "48849.00"
        },
        {
            "stac_yymm": "201912",
            "sale_account": "2304009.00",
            "sale_cost": "1472396.00",
            "sale_totl_prfi": "831613",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "277685.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "304322.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "217389.00"
        },
        {
            "stac_yymm": "201909",
            "sale_account": "1705161.00",
            "sale_cost": "1086850.00",
            "sale_totl_prfi": "618311",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "206082.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "227131.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "165118.00"
        },
        {
            "stac_yymm": "201906",
            "sale_account": "1085127.00",
            "sale_cost": "686912.00",
            "sale_totl_prfi": "398215",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "128303.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "140923.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "102242.00"
        },
        {
            "stac_yymm": "201903",
            "sale_account": "523855.00",
            "sale_cost": "327464.00",
            "sale_totl_prfi": "196391",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "62333.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "69130.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "50436.00"
        },
        {
            "stac_yymm": "201812",
            "sale_account": "2437714.00",
            "sale_cost": "1323944.00",
            "sale_totl_prfi": "1113770",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "588867.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "611600.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "443449.00"
        },
        {
            "stac_yymm": "201809",
            "sale_account": "1845064.00",
            "sale_cost": "983785.00",
            "sale_totl_prfi": "861279",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "480861.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "495521.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "358827.00"
        },
        {
            "stac_yymm": "201806",
            "sale_account": "1190464.00",
            "sale_cost": "631841.00",
            "sale_totl_prfi": "558623",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "305112.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "315827.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "227320.00"
        },
        {
            "stac_yymm": "201803",
            "sale_account": "605637.00",
            "sale_cost": "319095.00",
            "sale_totl_prfi": "286542",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "156422.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "161759.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "116885.00"
        },
        {
            "stac_yymm": "201712",
            "sale_account": "2395754.00",
            "sale_cost": "1292907.00",
            "sale_totl_prfi": "1102847",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "536450.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "561960.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "421867.00"
        },
        {
            "stac_yymm": "201709",
            "sale_account": "1735970.00",
            "sale_cost": "935596.00",
            "sale_totl_prfi": "800374",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "384981.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "394916.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "299316.00"
        },
        {
            "stac_yymm": "201706",
            "sale_account": "1115481.00",
            "sale_cost": "605555.00",
            "sale_totl_prfi": "509926",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "239649.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "245768.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "187382.00"
        },
        {
            "stac_yymm": "201703",
            "sale_account": "505475.00",
            "sale_cost": "281556.00",
            "sale_totl_prfi": "223919",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "98984.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "101646.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "76844.00"
        },
        {
            "stac_yymm": "201612",
            "sale_account": "2018667.00",
            "sale_cost": "1202777.00",
            "sale_totl_prfi": "815890",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "292407.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "307137.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "227261.00"
        },
        {
            "stac_yymm": "201609",
            "sale_account": "1485350.00",
            "sale_cost": "893942.00",
            "sale_totl_prfi": "591408",
            "depr_cost": "99.99",
            "sell_mang": "99.99",
            "bsop_prti": "200199.00",
            "bsop_non_ernn": "99.99",
            "bsop_non_expn": "99.99",
            "op_prfi": "211651.00",
            "spec_prfi": "99.99",
            "spec_loss": "99.99",
            "thtr_ntin": "156381.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 당사 대주가능 종목

- **TR_ID**: CTSC2702R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/lendable-by-company`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | EXCG_DVSN_CD:00
PDNO:
THCO_STLN_PSBL_YN:Y
INQR_DVSN_1:0
CTX_AREA_FK200:
CTX_AREA_NK100: |  |
| Response Example | {
    "ctx_area_fk200": "00!^!^Y!^0                                                                                                                                                                                              ",
    "ctx_area_nk100": "                                                                                                    ",
    "output1": [
        {
            "pdno": "130960",
            "prdt_name": "CJ E&M",
            "papr": "5000",
            "bfdy_clpr": "0",
            "sbst_prvs": "0",
            "tr_stop_dvsn_name": "거래정지",
            "psbl_yn_name": "가능",
            "lmt_qty1": "10520",
            "use_qty1": "0",
            "trad_psbl_qty2": "10520",
            "rght_type_cd": "11",
            "bass_dt": "20180629",
            "psbl_yn": "Y"
        },
        {
            "pdno": "110550",
            "prdt_name": "HIT 골드",
            "papr": "0",
            "bfdy_clpr": "0",
            "sbst_prvs": "0",
            "tr_stop_dvsn_name": "거래정지",
            "psbl_yn_name": "가능",
            "lmt_qty1": "0",
            "use_qty1": "0",
            "trad_psbl_qty2": "0",
            "rght_type_cd": "32",
            "bass_dt": "20111222",
            "psbl_yn": "Y"
        },
        {
            "pdno": "124090",
            "prdt_name": "HIT 보험",
            "papr": "0",
            "bfdy_clpr": "0",
            "sbst_prvs": "0",
            "tr_stop_dvsn_name": "거래정지",
            "psbl_yn_name": "가능",
            "lmt_qty1": "0",
            "use_qty1": "0",
            "trad_psbl_qty2": "0",
            "rght_type_cd": "32",
            "bass_dt": "20111219",
            "psbl_yn": "Y"
        },
        {
            "pdno": "002550",
            "prdt_name": "KB손해보험",
            "papr": "500",
            "bfdy_clpr": "0",
            "sbst_prvs": "0",
            "tr_stop_dvsn_name": "거래정지",
            "psbl_yn_name": "가능",
            "lmt_qty1": "0",
            "use_qty1": "0",
            "trad_psbl_qty2": "0",
            "rght_type_cd": "13",
            "bass_dt": "20170706",
            "psbl_yn": "Y"
        },
        {
            "pdno": "021960",
            "prdt_name": "KB캐피탈",
            "papr": "5000",
            "bfdy_clpr": "0",
            "sbst_prvs": "0",
            "tr_stop_dvsn_name": "거래정지",
            "psbl_yn_name": "가능",
            "lmt_qty1": "0",
            "use_qty1": "0",
            "trad_psbl_qty2": "0",
            "rght_type_cd": "13",
            "bass_dt": "20170706",
            "psbl_yn": "Y"
        },
        {
            "pdno": "105270",
            "prdt_name": "KINDEX 성장대형F15",
            "papr": "0",
            "bfdy_clpr": "0",
            "sbst_prvs": "0",
            "tr_stop_dvsn_name": "거래정지",
            "psbl_yn_name": "가능",
            "lmt_qty1": "0",
            "use_qty1": "0",
            "trad_psbl_qty2": "0",
            "rght_type_cd": "32",
            "bass_dt": "20140430",
            "psbl_yn": "Y"
        },...
        {
            "pdno": "003450",
            "prdt_name": "현대증권",
            "papr": "5000",
            "bfdy_clpr": "0",
            "sbst_prvs": "0",
            "tr_stop_dvsn_name": "거래정지",
            "psbl_yn_name": "가능",
            "lmt_qty1": "0",
            "use_qty1": "0",
            "trad_psbl_qty2": "0",
            "rght_type_cd": "13",
            "bass_dt": "20161018",
            "psbl_yn": "Y"
        }
    ],
    "output2": {
        "tot_stup_lmt_qty": "6441070",
        "brch_lmt_qty": "-1228",
        "rqst_psbl_qty": "6442095"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0460",
    "msg1": "조회 되었습니다. (마지막 자료)                                                  "
} |  |


### 주식기본조회

- **TR_ID**: CTPF1002R
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/search-stock-info`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"PDNO":"000660",
"PRDT_TYPE_CD":"300"
} |  |
| Response Example | {
    "output": {
        "pdno": "00000A000660",
        "prdt_type_cd": "300",
        "mket_id_cd": "STK",
        "scty_grp_id_cd": "ST",
        "excg_dvsn_cd": "02",
        "setl_mmdd": "12",
        "lstg_stqt": "728002365",
        "lstg_cptl_amt": "0",
        "cpta": "3657652050000",
        "papr": "5000",
        "issu_pric": "5000",
        "kospi200_item_yn": "Y",
        "scts_mket_lstg_dt": "19961226",
        "scts_mket_lstg_abol_dt": "",
        "kosdaq_mket_lstg_dt": "",
        "kosdaq_mket_lstg_abol_dt": "",
        "frbd_mket_lstg_dt": "19961226",
        "frbd_mket_lstg_abol_dt": "",
        "reits_kind_cd": "",
        "etf_dvsn_cd": "0",
        "oilf_fund_yn": "N",
        "idx_bztp_lcls_cd": "002",
        "idx_bztp_mcls_cd": "013",
        "idx_bztp_scls_cd": "013",
        "stck_kind_cd": "101",
        "mfnd_opng_dt": "",
        "mfnd_end_dt": "",
        "dpsi_erlm_cncl_dt": "",
        "etf_cu_qty": "0",
        "prdt_name": "에스케이하이닉스보통주",
        "prdt_name120": "에스케이하이닉스보통주",
        "prdt_abrv_name": "SK하이닉스",
        "std_pdno": "KR7000660001",
        "prdt_eng_name": "SK hynix",
        "prdt_eng_name120": "SK hynix",
        "prdt_eng_abrv_name": "SK hynix",
        "dpsi_aptm_erlm_yn": "Y",
        "etf_txtn_type_cd": "00",
        "etf_type_cd": "",
        "lstg_abol_dt": "",
        "nwst_odst_dvsn_cd": "1",
        "sbst_pric": "115980",
        "thco_sbst_pric": "115980",
        "thco_sbst_pric_chng_dt": "20240215",
        "tr_stop_yn": "N",
        "admn_item_yn": "N",
        "thdt_clpr": "146800",
        "bfdy_clpr": "148700",
        "clpr_chng_dt": "20240216",
        "std_idst_clsf_cd": "032601",
        "std_idst_clsf_cd_name": "반도체 제조업",
        "idx_bztp_lcls_cd_name": "시가총액규모대",
        "idx_bztp_mcls_cd_name": "전기,전자",
        "idx_bztp_scls_cd_name": "전기,전자",
        "ocr_no": "1147",
        "crfd_item_yn": "N",
        "elec_scty_yn": "Y"
    },
    "rt_cd": "0",
    "msg_cd": "KIOK0530",
    "msg1": "조회되었습니다                                                                  "
} |  |


### 예탁원정보(유상증자일정)

- **TR_ID**: HHKDB669100C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/paidin-capin`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
gb1:1
f_dt:20230301
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20240222",
            "sht_cd": "426530",
            "isin_name": "메타록",
            "tot_issue_stk_qty": "    31000000",
            "issue_stk_qty": "      273199",
            "fix_rate": " 20.00",
            "disc_rate": " 0.00",
            "fix_price": "     500",
            "right_dt": "20240221",
            "sub_term_ft": "20240325",
            "sub_term": "2024/03/25 ~ 2024/03/26",
            "list_date": "",
            "stk_kind": "01"
        },
        {
            "record_date": "20240219",
            "sht_cd": "429850",
            "isin_name": "애딥",
            "tot_issue_stk_qty": "      755400",
            "issue_stk_qty": "     1680196",
            "fix_rate": "397.14",
            "disc_rate": " 0.00",
            "fix_price": "     500",
            "right_dt": "20240216",
            "sub_term_ft": "20240319",
            "sub_term": "2024/03/19 ~ 2024/03/20",
            "list_date": "",
            "stk_kind": "01"
        },
        {
            "record_date": "20240213",
            "sht_cd": "321850",
            "isin_name": "나이스엘엠에스",
            "tot_issue_stk_qty": "    22826013",
            "issue_stk_qty": "     5337064",
            "fix_rate": " 44.95",
            "disc_rate": " 0.00",
            "fix_price": "    6000",
            "right_dt": "20240208",
            "sub_term_ft": "20240318",
            "sub_term": "2024/03/18 ~ 2024/03/18",
            "list_date": "",
            "stk_kind": "01"
        },
        {
            "record_date": "20240216",
            "sht_cd": "225340",
            "isin_name": "메디셀",
            "tot_issue_stk_qty": "    10085593",
            "issue_stk_qty": "     1058677",
            "fix_rate": " 29.70",
            "disc_rate": " 0.00",
            "fix_price": "    1000",
            "right_dt": "20240215",
            "sub_term_ft": "20240314",
            "sub_term": "2024/03/14 ~ 2024/03/15",
            "list_date": "",
            "stk_kind": "01"
        },
        {
            "record_date": "20240131",
            "sht_cd": "001440",
            "isin_name": "대한전선",
            "tot_issue_stk_qty": "   124447300",
            "issue_stk_qty": "    62000000",
            "fix_rate": " 50.13",
            "disc_rate": " 0.00",
            "fix_price": "    7460",
            "right_dt": "20240130",
            "sub_term_ft": "20240311",
            "sub_term": "2024/03/11 ~ 2024/03/12",
            "list_date": "2024/04/02",
            "stk_kind": "01"
        },...
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 예탁원정보(주주총회일정)

- **TR_ID**: HHKDB669111C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/sharehld-meet`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | cts:
f_dt:20230101
t_dt:20240326
sht_cd: |  |
| Response Example | {
    "output1": [
        {
            "record_date": "20240322",
            "sht_cd": "388370",
            "isin_name": "(주)우앤컴퍼니",
            "gen_meet_dt": "2024/04/18",
            "gen_meet_type": "임시총회",
            "agenda": "정관변경",
            "vote_tot_qty": "      959800"
        },
        {
            "record_date": "20240322",
            "sht_cd": "388370",
            "isin_name": "(주)우앤컴퍼니",
            "gen_meet_dt": "2024/04/18",
            "gen_meet_type": "임시총회",
            "agenda": "이사선임",
            "vote_tot_qty": "      959800"
        },
        {
            "record_date": "20240321",
            "sht_cd": "323530",
            "isin_name": "(주)아이월드제약",
            "gen_meet_dt": "2024/04/25",
            "gen_meet_type": "임시총회",
            "agenda": "사내이사 선임",
            "vote_tot_qty": "    25721999"
        },
        {
            "record_date": "20240321",
            "sht_cd": "323530",
            "isin_name": "(주)아이월드제약",
            "gen_meet_dt": "2024/04/25",
            "gen_meet_type": "임시총회",
            "agenda": "정관변경",
            "vote_tot_qty": "    25721999"
        },
        {
            "record_date": "20240321",
            "sht_cd": "323530",
            "isin_name": "(주)아이월드제약",
            "gen_meet_dt": "2024/04/25",
            "gen_meet_type": "임시총회",
            "agenda": "사외이사 선임",
            "vote_tot_qty": "    25721999"
        },
        {
            "record_date": "20240315",
            "sht_cd": "091090",
            "isin_name": "세원이앤씨(주)",
            "gen_meet_dt": "2024/04/12",
            "gen_meet_type": "임시총회",
            "agenda": "이사해임(주주제안)",
            "vote_tot_qty": "    52754723"
        },
        {
            "record_date": "20240315",
            "sht_cd": "091090",
            "isin_name": "세원이앤씨(주)",
            "gen_meet_dt": "2024/04/12",
            "gen_meet_type": "임시총회",
            "agenda": "정관변경(주주제안)",
            "vote_tot_qty": "    52754723"
        },
        {
            "record_date": "20240315",
            "sht_cd": "091090",
            "isin_name": "세원이앤씨(주)",
            "gen_meet_dt": "2024/04/12",
            "gen_meet_type": "임시총회",
            "agenda": "이사해임(주주제안)",
            "vote_tot_qty": "    52754723"
        },
        {
            "record_date": "20240315",
            "sht_cd": "091090",
            "isin_name": "세원이앤씨(주)",
            "gen_meet_dt": "2024/04/12",
            "gen_meet_type": "임시총회",
            "agenda": "사외이사 선임(주주제안)",
            "vote_tot_qty": "    52754723"
        },
        {
            "record_date": "20240315",
            "sht_cd": "091090",
            "isin_name": "세원이앤씨(주)",
            "gen_meet_dt": "2024/04/12",
            "gen_meet_type": "임시총회",
            "agenda": "사내이사 선임(주주제안)",
            "vote_tot_qty": "    52754723"
        },
        {
            "record_date": "20240312",
            "sht_cd": "380440",
            "isin_name": "엔에이치기업인수목적19호(주)",
            "gen_meet_dt": "2024/04/19",
            "gen_meet_type": "임시총회",
            "agenda": "청산결산보고서승인",
            "vote_tot_qty": "    10258000"
        },
        {
            "record_date": "20240308",
            "sht_cd": "263540",
            "isin_name": "(주)어스앤에어로스페이스",
            "gen_meet_dt": "2024/04/03",
            "gen_meet_type": "임시총회",
            "agenda": "사내이사 선임",
            "vote_tot_qty": "    14294091"
        },
        {
            "record_date": "20240308",
            "sht_cd": "263540",
            "isin_name": "(주)어스앤에어로스페이스",
            "gen_meet_dt": "2024/04/03",
            "gen_meet_type": "임시총회",
            "agenda": "사내이사 선임",
            "vote_tot_qty": "    14294091"
        },
        {
            "record_date": "20240308",
            "sht_cd": "263540",
            "isin_name": "(주)어스앤에어로스페이스",
            "gen_meet_dt": "2024/04/03",
            "gen_meet_type": "임시총회",
            "agenda": "정관변경",
            "vote_tot_qty": "    14294091"
        },
        {
            "record_date": "20240308",
            "sht_cd": "263540",
            "isin_name": "(주)어스앤에어로스페이스",
            "gen_meet_dt": "2024/04/03",
            "gen_meet_type": "임시총회",
            "agenda": "사내이사 선임",
            "vote_tot_qty": "    14294091"
        },
        {
            "record_date": "20240308",
            "sht_cd": "263540",
            "isin_name": "(주)어스앤에어로스페이스",
            "gen_meet_dt": "2024/04/03",
            "gen_meet_type": "임시총회",
            "agenda": "사외이사 선임",
            "vote_tot_qty": "    14294091"
        },
        {
            "record_date": "20240308",
            "sht_cd": "343990",
            "isin_name": "비즈플레이(주)",
            "gen_meet_dt": "2024/03/27",
            "gen_meet_type": "종류총회",
            "agenda": "정관변경",
            "vote_tot_qty": "    21751896"
        },
        {
            "record_date": "20240307",
            "sht_cd": "001140",
            "isin_name": "(주)국보",
            "gen_meet_dt": "2024/04/26",
            "gen_meet_type": "정기총회",
            "agenda": "사내이사 선임",
            "vote_tot_qty": "    13691728"
        },
        {
            "record_date": "20240307",
            "sht_cd": "001140",
            "isin_name": "(주)국보",
            "gen_meet_dt": "2024/04/26",
            "gen_meet_type": "정기총회",
            "agenda": "감사선임",
            "vote_tot_qty": "    13691728"
        },
        {
            "record_date": "20240307",
            "sht_cd": "001140",
            "isin_name": "(주)국보",
            "gen_meet_dt": "2024/04/26",
            "gen_meet_type": "정기총회",
            "agenda": "이사 보수한도액 승인",
            "vote_tot_qty": "    13691728"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식 성장성비율

- **TR_ID**: FHKST66430800
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/finance/growth-ratio`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"J",
"fid_input_iscd":"005930",
"fid_div_cls_code":"1"
} |  |
| Response Example | {
    "output": [
        {
            "stac_yymm": "202312",
            "grs": "-14.33",
            "bsop_prfi_inrt": "-84.86",
            "equt_inrt": "2.52",
            "totl_aset_inrt": "1.67"
        },
        {
            "stac_yymm": "202309",
            "grs": "-17.52",
            "bsop_prfi_inrt": "-90.42",
            "equt_inrt": "5.50",
            "totl_aset_inrt": "-3.36"
        },
        {
            "stac_yymm": "202306",
            "grs": "-20.15",
            "bsop_prfi_inrt": "-95.36",
            "equt_inrt": "9.47",
            "totl_aset_inrt": "-0.01"
        },
        {
            "stac_yymm": "202303",
            "grs": "-18.05",
            "bsop_prfi_inrt": "-95.47",
            "equt_inrt": "14.12",
            "totl_aset_inrt": "3.36"
        },
        {
            "stac_yymm": "202212",
            "grs": "8.09",
            "bsop_prfi_inrt": "-15.99",
            "equt_inrt": "16.35",
            "totl_aset_inrt": "5.11"
        },
        {
            "stac_yymm": "202209",
            "grs": "14.15",
            "bsop_prfi_inrt": "3.45",
            "equt_inrt": "16.22",
            "totl_aset_inrt": "14.58"
        },
        {
            "stac_yymm": "202206",
            "grs": "20.09",
            "bsop_prfi_inrt": "28.56",
            "equt_inrt": "16.15",
            "totl_aset_inrt": "16.44"
        },
        {
            "stac_yymm": "202203",
            "grs": "18.95",
            "bsop_prfi_inrt": "50.50",
            "equt_inrt": "14.96",
            "totl_aset_inrt": "11.84"
        },
        {
            "stac_yymm": "202112",
            "grs": "18.07",
            "bsop_prfi_inrt": "43.45",
            "equt_inrt": "10.49",
            "totl_aset_inrt": "12.79"
        },
        {
            "stac_yymm": "202109",
            "grs": "15.85",
            "bsop_prfi_inrt": "40.15",
            "equt_inrt": "7.47",
            "totl_aset_inrt": "9.22"
        },
        {
            "stac_yymm": "202106",
            "grs": "19.18",
            "bsop_prfi_inrt": "50.41",
            "equt_inrt": "4.64",
            "totl_aset_inrt": "7.49"
        },
        {
            "stac_yymm": "202103",
            "grs": "18.19",
            "bsop_prfi_inrt": "45.53",
            "equt_inrt": "2.96",
            "totl_aset_inrt": "9.89"
        },
        {
            "stac_yymm": "202012",
            "grs": "2.78",
            "bsop_prfi_inrt": "29.62",
            "equt_inrt": "4.97",
            "totl_aset_inrt": "7.28"
        },
        {
            "stac_yymm": "202009",
            "grs": "2.78",
            "bsop_prfi_inrt": "30.76",
            "equt_inrt": "4.82",
            "totl_aset_inrt": "6.34"
        },
        {
            "stac_yymm": "202006",
            "grs": "-0.20",
            "bsop_prfi_inrt": "13.74",
            "equt_inrt": "4.68",
            "totl_aset_inrt": "4.38"
        },
        {
            "stac_yymm": "202003",
            "grs": "5.61",
            "bsop_prfi_inrt": "3.43",
            "equt_inrt": "5.20",
            "totl_aset_inrt": "3.59"
        },
        {
            "stac_yymm": "201912",
            "grs": "-5.48",
            "bsop_prfi_inrt": "-52.84",
            "equt_inrt": "6.11",
            "totl_aset_inrt": "3.89"
        },
        {
            "stac_yymm": "201909",
            "grs": "-7.58",
            "bsop_prfi_inrt": "-57.14",
            "equt_inrt": "8.81",
            "totl_aset_inrt": "4.80"
        },
        {
            "stac_yymm": "201906",
            "grs": "-8.85",
            "bsop_prfi_inrt": "-57.95",
            "equt_inrt": "10.56",
            "totl_aset_inrt": "7.61"
        },
        {
            "stac_yymm": "201903",
            "grs": "-13.50",
            "bsop_prfi_inrt": "-60.15",
            "equt_inrt": "13.42",
            "totl_aset_inrt": "10.43"
        },
        {
            "stac_yymm": "201812",
            "grs": "1.75",
            "bsop_prfi_inrt": "9.77",
            "equt_inrt": "15.51",
            "totl_aset_inrt": "12.46"
        },
        {
            "stac_yymm": "201809",
            "grs": "6.28",
            "bsop_prfi_inrt": "24.91",
            "equt_inrt": "14.91",
            "totl_aset_inrt": "13.70"
        },
        {
            "stac_yymm": "201806",
            "grs": "6.72",
            "bsop_prfi_inrt": "27.32",
            "equt_inrt": "16.15",
            "totl_aset_inrt": "14.81"
        },
        {
            "stac_yymm": "201803",
            "grs": "19.82",
            "bsop_prfi_inrt": "58.03",
            "equt_inrt": "17.62",
            "totl_aset_inrt": "18.26"
        },
        {
            "stac_yymm": "201712",
            "grs": "18.68",
            "bsop_prfi_inrt": "83.46",
            "equt_inrt": "11.16",
            "totl_aset_inrt": "15.10"
        },
        {
            "stac_yymm": "201709",
            "grs": "16.87",
            "bsop_prfi_inrt": "92.30",
            "equt_inrt": "17.35",
            "totl_aset_inrt": "21.31"
        },
        {
            "stac_yymm": "201706",
            "grs": "10.75",
            "bsop_prfi_inrt": "61.71",
            "equt_inrt": "10.37",
            "totl_aset_inrt": "13.78"
        },
        {
            "stac_yymm": "201703",
            "grs": "1.54",
            "bsop_prfi_inrt": "48.27",
            "equt_inrt": "6.44",
            "totl_aset_inrt": "9.52"
        },
        {
            "stac_yymm": "201612",
            "grs": "0.60",
            "bsop_prfi_inrt": "10.70",
            "equt_inrt": "7.76",
            "totl_aset_inrt": "8.26"
        },
        {
            "stac_yymm": "201609",
            "grs": "0.81",
            "bsop_prfi_inrt": "-1.24",
            "equt_inrt": "-0.66",
            "totl_aset_inrt": "-0.85"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식 대차대조표

- **TR_ID**: FHKST66430100
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/finance/balance-sheet`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"J",
"fid_input_iscd":"005930",
"fid_div_cls_code":"1"
} |  |
| Response Example | {
    "output": [
        {
            "stac_yymm": "202312",
            "cras": "1959366.00",
            "fxas": "2599694.00",
            "total_aset": "4559060.00",
            "flow_lblt": "757195.00",
            "fix_lblt": "165087.00",
            "total_lblt": "922281.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3636779.00"
        },
        {
            "stac_yymm": "202309",
            "cras": "2064386.00",
            "fxas": "2480278.00",
            "total_aset": "4544664.00",
            "flow_lblt": "736252.00",
            "fix_lblt": "169486.00",
            "total_lblt": "905738.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3638926.00"
        },
        {
            "stac_yymm": "202306",
            "cras": "2039754.00",
            "fxas": "2440252.00",
            "total_aset": "4480006.00",
            "flow_lblt": "707806.00",
            "fix_lblt": "182443.00",
            "total_lblt": "890249.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3589756.00"
        },
        {
            "stac_yymm": "202303",
            "cras": "2144421.00",
            "fxas": "2396496.00",
            "total_aset": "4540918.00",
            "flow_lblt": "760574.00",
            "fix_lblt": "182349.00",
            "total_lblt": "942924.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3597994.00"
        },
        {
            "stac_yymm": "202212",
            "cras": "2184706.00",
            "fxas": "2299539.00",
            "total_aset": "4484245.00",
            "flow_lblt": "783449.00",
            "fix_lblt": "153301.00",
            "total_lblt": "936749.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3547496.00"
        },
        {
            "stac_yymm": "202209",
            "cras": "2508806.00",
            "fxas": "2193978.00",
            "total_aset": "4702784.00",
            "flow_lblt": "852857.00",
            "fix_lblt": "400859.00",
            "total_lblt": "1253715.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3449069.00"
        },
        {
            "stac_yymm": "202206",
            "cras": "2362875.00",
            "fxas": "2117532.00",
            "total_aset": "4480407.00",
            "flow_lblt": "833623.00",
            "fix_lblt": "367717.00",
            "total_lblt": "1201340.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3279067.00"
        },
        {
            "stac_yymm": "202203",
            "cras": "2323691.00",
            "fxas": "2069579.00",
            "total_aset": "4393270.00",
            "flow_lblt": "904637.00",
            "fix_lblt": "335723.00",
            "total_lblt": "1240360.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3152909.00"
        },
        {
            "stac_yymm": "202112",
            "cras": "2181632.00",
            "fxas": "2084580.00",
            "total_aset": "4266212.00",
            "flow_lblt": "881171.00",
            "fix_lblt": "336041.00",
            "total_lblt": "1217212.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "3048999.00"
        },
        {
            "stac_yymm": "202109",
            "cras": "2127930.00",
            "fxas": "1976277.00",
            "total_aset": "4104207.00",
            "flow_lblt": "818720.00",
            "fix_lblt": "317826.00",
            "total_lblt": "1136546.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2967661.00"
        },
        {
            "stac_yymm": "202106",
            "cras": "1911185.00",
            "fxas": "1936591.00",
            "total_aset": "3847777.00",
            "flow_lblt": "724615.00",
            "fix_lblt": "299920.00",
            "total_lblt": "1024534.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2823243.00"
        },
        {
            "stac_yymm": "202103",
            "cras": "2091554.00",
            "fxas": "1836709.00",
            "total_aset": "3928263.00",
            "flow_lblt": "901095.00",
            "fix_lblt": "284482.00",
            "total_lblt": "1185577.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2742686.00"
        },
        {
            "stac_yymm": "202012",
            "cras": "1982156.00",
            "fxas": "1800201.00",
            "total_aset": "3782357.00",
            "flow_lblt": "756044.00",
            "fix_lblt": "266834.00",
            "total_lblt": "1022877.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2759480.00"
        },
        {
            "stac_yymm": "202009",
            "cras": "2036349.00",
            "fxas": "1721538.00",
            "total_aset": "3757887.00",
            "flow_lblt": "730464.00",
            "fix_lblt": "266061.00",
            "total_lblt": "996526.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2761362.00"
        },
        {
            "stac_yymm": "202006",
            "cras": "1861368.00",
            "fxas": "1718227.00",
            "total_aset": "3579595.00",
            "flow_lblt": "618637.00",
            "fix_lblt": "262880.00",
            "total_lblt": "881517.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2698078.00"
        },
        {
            "stac_yymm": "202003",
            "cras": "1867397.00",
            "fxas": "1707178.00",
            "total_aset": "3574575.00",
            "flow_lblt": "647633.00",
            "fix_lblt": "263065.00",
            "total_lblt": "910698.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2663877.00"
        },
        {
            "stac_yymm": "201912",
            "cras": "1813853.00",
            "fxas": "1711792.00",
            "total_aset": "3525645.00",
            "flow_lblt": "637828.00",
            "fix_lblt": "259013.00",
            "total_lblt": "896841.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2628804.00"
        },
        {
            "stac_yymm": "201909",
            "cras": "1860421.00",
            "fxas": "1673439.00",
            "total_aset": "3533860.00",
            "flow_lblt": "633032.00",
            "fix_lblt": "266405.00",
            "total_lblt": "899437.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2634422.00"
        },
        {
            "stac_yymm": "201906",
            "cras": "1734335.00",
            "fxas": "1695067.00",
            "total_aset": "3429401.00",
            "flow_lblt": "593093.00",
            "fix_lblt": "258838.00",
            "total_lblt": "851931.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2577470.00"
        },
        {
            "stac_yymm": "201903",
            "cras": "1773885.00",
            "fxas": "1676794.00",
            "total_aset": "3450679.00",
            "flow_lblt": "673541.00",
            "fix_lblt": "244986.00",
            "total_lblt": "918527.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2532152.00"
        },
        {
            "stac_yymm": "201812",
            "cras": "1746974.00",
            "fxas": "1646598.00",
            "total_aset": "3393572.00",
            "flow_lblt": "690815.00",
            "fix_lblt": "225226.00",
            "total_lblt": "916041.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2477532.00"
        },
        {
            "stac_yymm": "201809",
            "cras": "1762820.00",
            "fxas": "1609137.00",
            "total_aset": "3371958.00",
            "flow_lblt": "747059.00",
            "fix_lblt": "203868.00",
            "total_lblt": "950926.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2421032.00"
        },
        {
            "stac_yymm": "201806",
            "cras": "1569768.00",
            "fxas": "1617115.00",
            "total_aset": "3186884.00",
            "flow_lblt": "656023.00",
            "fix_lblt": "199612.00",
            "total_lblt": "855635.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2331248.00"
        },
        {
            "stac_yymm": "201803",
            "cras": "1549420.00",
            "fxas": "1575312.00",
            "total_aset": "3124731.00",
            "flow_lblt": "682986.00",
            "fix_lblt": "209146.00",
            "total_lblt": "892132.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2232599.00"
        },
        {
            "stac_yymm": "201712",
            "cras": "1469825.00",
            "fxas": "1547696.00",
            "total_aset": "3017521.00",
            "flow_lblt": "671751.00",
            "fix_lblt": "200855.00",
            "total_lblt": "872607.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2144914.00"
        },
        {
            "stac_yymm": "201709",
            "cras": "1453223.00",
            "fxas": "1512562.00",
            "total_aset": "2965786.00",
            "flow_lblt": "661726.00",
            "fix_lblt": "197147.00",
            "total_lblt": "858873.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2106913.00"
        },
        {
            "stac_yymm": "201706",
            "cras": "1321727.00",
            "fxas": "1454168.00",
            "total_aset": "2775894.00",
            "flow_lblt": "584684.00",
            "fix_lblt": "184153.00",
            "total_lblt": "768837.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "2007057.00"
        },
        {
            "stac_yymm": "201703",
            "cras": "1292842.00",
            "fxas": "1349332.00",
            "total_aset": "2642174.00",
            "flow_lblt": "568431.00",
            "fix_lblt": "175563.00",
            "total_lblt": "743994.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "1898180.00"
        },
        {
            "stac_yymm": "201612",
            "cras": "1414297.00",
            "fxas": "1207446.00",
            "total_aset": "2621743.00",
            "flow_lblt": "547041.00",
            "fix_lblt": "145072.00",
            "total_lblt": "692113.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "1929630.00"
        },
        {
            "stac_yymm": "201609",
            "cras": "1321668.00",
            "fxas": "1123047.00",
            "total_aset": "2444715.00",
            "flow_lblt": "504595.00",
            "fix_lblt": "144756.00",
            "total_lblt": "649351.00",
            "cpfn": "8975",
            "cfp_surp": "99.99",
            "prfi_surp": "99.99",
            "total_cptl": "1795364.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 예탁원정보(합병/분할일정)

- **TR_ID**: HHKDB669104C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/ksdinfo/merger-split`

> ⚠ 원본 엑셀에 상세 명세 시트 없음

### 국내주식 종목추정실적

- **TR_ID**: HHKST668300C0
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/quotations/estimate-perform`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | SHT_CD:005930 |  |
| Response Example | {
    "output1": {
        "sht_cd": "A005930",
        "item_kor_nm": "삼성전자",
        "name1": "김한국",
        "name2": "",
        "estdate": "20240109",
        "rcmd_name": "매수",
        "capital": "8975.0",
        "forn_item_lmtrt": "0.00"
    },
    "output2": [
        {
            "data1": "2796048.0",
            "data2": "3022314.0",
            "data3": "2581509.0",
            "data4": "3048945.0",
            "data5": "3295675.0"
        },
        {
            "data1": "181.0",
            "data2": "81.0",
            "data3": "-146.0",
            "data4": "181.0",
            "data5": "81.0"
        },
        {
            "data1": "516339.0",
            "data2": "433766.0",
            "data3": "65405.0",
            "data4": "330172.0",
            "data5": "555410.0"
        },
        {
            "data1": "435.0",
            "data2": "-160.0",
            "data3": "-849.0",
            "data4": "4048.0",
            "data5": "682.0"
        },
        {
            "data1": "392438.0",
            "data2": "547300.0",
            "data3": "106144.0",
            "data4": "253332.0",
            "data5": "422055.0"
        },
        {
            "data1": "504.0",
            "data2": "395.0",
            "data3": "-806.0",
            "data4": "1387.0",
            "data5": "666.0"
        }
    ],
    "output3": [
        {
            "data1": "858812.0",
            "data2": "824843.0",
            "data3": "483199.0",
            "data4": "792602.0",
            "data5": "1043367.0"
        },
        {
            "data1": "57770.0",
            "data2": "80570.0",
            "data3": "15609.0",
            "data4": "36983.0",
            "data5": "61483.0"
        },
        {
            "data1": "504.0",
            "data2": "395.0",
            "data3": "-806.0",
            "data4": "1369.0",
            "data5": "662.0"
        },
        {
            "data1": "136.0",
            "data2": "69.0",
            "data3": "503.0",
            "data4": "207.0",
            "data5": "124.0"
        },
        {
            "data1": "50.0",
            "data2": "34.0",
            "data3": "95.0",
            "data4": "53.0",
            "data5": "39.0"
        },
        {
            "data1": "139.0",
            "data2": "171.0",
            "data3": "31.0",
            "data4": "70.0",
            "data5": "109.0"
        },
        {
            "data1": "399.0",
            "data2": "264.0",
            "data3": "255.0",
            "data4": "226.0",
            "data5": "163.0"
        },
        {
            "data1": "1197.0",
            "data2": "568.0",
            "data3": "58.0",
            "data4": "232.0",
            "data5": "655.0"
        }
    ],
    "output4": [
        {
            "dt": "2021.12"
        },
        {
            "dt": "2022.12"
        },
        {
            "dt": "2023.12E"
        },
        {
            "dt": "2024.12E"
        },
        {
            "dt": "2025.12E"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |


### 국내주식 기타주요비율

- **TR_ID**: FHKST66430500
- **Method**: GET
- **URL**: `/uapi/domestic-stock/v1/finance/other-major-ratios`

#### Response

| 필드 | 타입 | 설명 |
|-----|------|------|
| Example |  |  |
| Request Example (Python) | {
"fid_cond_mrkt_div_code":"J",
"fid_input_iscd":"005930",
"fid_div_cls_code":"1"
} |  |
| Response Example | {
    "output": [
        {
            "stac_yymm": "202309",
            "payout_rate": "-0.02",
            "eva": "0.00",
            "ebitda": "23464.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202306",
            "payout_rate": "-0.02",
            "eva": "0.00",
            "ebitda": "7851.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202303",
            "payout_rate": "-0.05",
            "eva": "0.00",
            "ebitda": "1574.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202212",
            "payout_rate": "0.05",
            "eva": "-18075.00",
            "ebitda": "209609.00",
            "ev_ebitda": "3.48"
        },
        {
            "stac_yymm": "202209",
            "payout_rate": "0.02",
            "eva": "0.00",
            "ebitda": "191549.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202206",
            "payout_rate": "0.02",
            "eva": "0.00",
            "ebitda": "139382.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202203",
            "payout_rate": "0.06",
            "eva": "0.00",
            "ebitda": "62600.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202112",
            "payout_rate": "0.01",
            "eva": "40178.00",
            "ebitda": "230671.00",
            "ev_ebitda": "4.59"
        },
        {
            "stac_yymm": "202109",
            "payout_rate": "0.02",
            "eva": "0.00",
            "ebitda": "160524.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202106",
            "payout_rate": "0.04",
            "eva": "0.00",
            "ebitda": "91711.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202103",
            "payout_rate": "0.12",
            "eva": "0.00",
            "ebitda": "38610.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202012",
            "payout_rate": "0.03",
            "eva": "3789.00",
            "ebitda": "147848.00",
            "ev_ebitda": "6.37"
        },
        {
            "stac_yymm": "202009",
            "payout_rate": "0.04",
            "eva": "0.00",
            "ebitda": "112945.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202006",
            "payout_rate": "0.06",
            "eva": "0.00",
            "ebitda": "75099.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "202003",
            "payout_rate": "0.19",
            "eva": "0.00",
            "ebitda": "31351.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201912",
            "payout_rate": "0.06",
            "eva": "-24528.00",
            "ebitda": "113396.00",
            "ev_ebitda": "6.76"
        },
        {
            "stac_yymm": "201909",
            "payout_rate": "0.06",
            "eva": "0.00",
            "ebitda": "87849.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201906",
            "payout_rate": "0.07",
            "eva": "0.00",
            "ebitda": "61528.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201903",
            "payout_rate": "0.11",
            "eva": "0.00",
            "ebitda": "34045.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201812",
            "payout_rate": "0.01",
            "eva": "123025.00",
            "ebitda": "272721.00",
            "ev_ebitda": "1.62"
        },
        {
            "stac_yymm": "201809",
            "payout_rate": "0.01",
            "eva": "0.00",
            "ebitda": "210889.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201806",
            "payout_rate": "0.02",
            "eva": "0.00",
            "ebitda": "129647.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201803",
            "payout_rate": "0.04",
            "eva": "0.00",
            "ebitda": "58160.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201712",
            "payout_rate": "0.01",
            "eva": "77272.00",
            "ebitda": "187476.00",
            "ev_ebitda": "2.97"
        },
        {
            "stac_yymm": "201709",
            "payout_rate": "0.02",
            "eva": "0.00",
            "ebitda": "129433.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201706",
            "payout_rate": "0.03",
            "eva": "0.00",
            "ebitda": "78973.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201703",
            "payout_rate": "0.06",
            "eva": "0.00",
            "ebitda": "36327.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201612",
            "payout_rate": "0.04",
            "eva": "11971.00",
            "ebitda": "77332.00",
            "ev_ebitda": "4.23"
        },
        {
            "stac_yymm": "201609",
            "payout_rate": "0.09",
            "eva": "0.00",
            "ebitda": "50536.00",
            "ev_ebitda": "0.00"
        },
        {
            "stac_yymm": "201606",
            "payout_rate": "0.16",
            "eva": "0.00",
            "ebitda": "32197.00",
            "ev_ebitda": "0.00"
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다."
} |  |

