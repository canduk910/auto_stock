# 사이클 C2 — 퀀트 재무필터 순수 함수 (마법공식 + F-Score-7) Red 메모

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (C2 즉시 착수)

**성격**: 순수 함수 (DB/HTTP/시계 미접촉) → mock/freeze_time 불필요. 매매 무관 (계산 계층, C3/C4 에서 통합·활성). 매매 안전성 8영역 diff 0.

**병렬성**: C1 (db/api/base.py/migration) Green 을 다른 에이전트가 병렬 구현 중. C2 는 `src/engine/quant_score.py` + `tests/unit/engine/test_cycleC2_quant_score.py` 만 다룸 (C1 파일 절대 미접촉).

## Red 근거 (모듈 부재)

`src/engine/quant_score.py` 미존재 → `from src.engine.quant_score import compute_f_score_7, compute_magic_formula` 가 **collection 단계 ModuleNotFoundError** → 파일 전체 FAIL (37 케이스 전량 error).

## 대상 순수 함수 2

### `compute_f_score_7(curr: dict, prev: dict) -> int | None`
당기 vs 전기 2기 비교, 7지표 각 +1 (최대 7):
1. `cptl_ntin_rate > 0` (ROA 양수)
2. `curr.cptl_ntin_rate > prev.cptl_ntin_rate` (ΔROA>0)
3. `curr.lblt_rate < prev.lblt_rate` (부채비율↓)
4. `curr.crnt_rate > prev.crnt_rate` (유동비율↑)
5. `curr.sale_totl_rate > prev.sale_totl_rate` (매출총이익율↑)
6. `curr.sale_account/curr.total_aset > prev.sale_account/prev.total_aset` (총자산회전율↑, 분모>0 가드)
7. `curr.cpfn <= prev.cpfn` (자본금=주식수 근사 불변/감소)

- 결측/0분모 graceful: 개별 지표 계산 불가 → 그 지표 미가점(+0), 전체 계속.
- 2기 부족(prev=None/curr=None/prev 필수 필드 전부 결측) → **None** (fail-open 신호, 배제 아님).
- 반환 타입: 유효 시 `int` (bool 아님), 부족 시 `None`.

### `compute_magic_formula(series_by_ticker, mktcap_by_ticker) -> dict[str, dict]`
유니버스 상대 순위. 각 ticker 당기 재무 dict + 시총(원):
- **EY**: `ev_ebitda>0` → `ey=1/ev_ebitda` (직접). 아니면 폴백 `ey=bsop_prti/EV` (EV = 시총(원) + total_lblt, EV>0 가드). 둘 다 불가 → `ey=None`.
- **ROC**: `bsop_prti / ((cras - flow_lblt) + fxas)` (분모>0 가드, 아니면 None).
- **ey_rank/roc_rank**: 유니버스 내 **내림차순** (높을수록 우량=순위 1). None 은 최하위.
- **mf_rank** = `ey_rank + roc_rank` (낮을수록 우량).
- 반환 `{ticker: {ey, roc, ey_rank, roc_rank, mf_rank}}` — 입력 전 종목 존재 (결측도 None 표기, 제외 아님).
- 결정성: 동일 입력 → 동일 랭킹 (정렬 안정성, 동점 결정적 배정).

## 회귀 가드 매트릭스 (37 케이스)

### F-Score-7 지표 경계 (20)
- **지표1** ROA: 양수 가점 / 0 미가점 / 음수 미가점 (3)
- **지표2** ΔROA: 초과 가점 / 같음 미가점 / 미만 미가점 (3)
- **지표3** 부채비율: 감소 가점 / 같음 미가점 / 증가 미가점 (3)
- **지표4** 유동비율: 증가 가점 / 같음 미가점 (2)
- **지표5** 매출총이익율: 증가 가점 / 같음 미가점 (2)
- **지표6** 총자산회전율: 증가 가점 / 같음 미가점 / curr 0분모 graceful / prev 0분모 graceful (4)
- **지표7** 자본금: 감소 가점 / 같음 가점(<=) / 증가 미가점 (3)

### F-Score-7 총점 경계 (4)
- 0점 (전 지표 미가점) / 7점 만점 / 1점 (C4 ≤1 배제 경계 = 배제 대상) / 2점 (≥2 통과 경계)

### F-Score-7 결측/2기 부족 (7)
- 지표 필드 결측 → 그 지표만 미가점 나머지 계속 / None 값 graceful / 비숫자 문자열 graceful
- prev=None → None / prev 빈 dict(전부 결측) → None / curr=None → None
- 반환 타입 계약 (int/None, bool 차단)

### 마법공식 EY (5) — 직접 + 폴백
- ev_ebitda 직접 (1/ev_ebitda, 폴백 미사용 우선) / ev_ebitda=0 폴백 / ev_ebitda 음수 폴백
- ev_ebitda<=0 AND EV<=0 → None / 시총 결측 + total_lblt 0 → EV=0 → None

### 마법공식 ROC (4) — 분모 가드
- 정상 계산 / 분모 0 → None / 분모 음수 → None / 구성 필드 결측 → None

### 마법공식 랭킹 + 결정성 (9)
- ey_rank 내림차순 / roc_rank 내림차순 / mf_rank 합산
- 동일 입력 2회 identical / 동점 결정적 배정
- 결측(None) 최하위 순위 / 입력 전 종목 출력 존재
- 빈 유니버스 → {} / 단일 종목 rank 1

## 헬퍼 설계 메모
- `_base_fin(**overrides)`: 7지표 전부 '미가점' 중립 기준점 (지표7 cpfn 동일만 자동 가점 → 기준 1점). 개별 테스트가 override 로 특정 지표만 켬 → 경계 격리.
- 마법공식 유니버스 헬퍼 `_universe()`: 3종목 EY(0.20/0.10/0.05)·ROC(0.50/0.25/0.10) 명확 차별화 → rank 결정적 검증.

## Green 인계 (backend-dev)
- `src/engine/quant_score.py` 신규 순수 함수 2개. import/DB/HTTP 절대 금지 (순수 함수).
- `_safe_float` 유틸 (None/빈문자열/비숫자 graceful → None). C1 `stock_master_financial.py::_safe_float` 미러 가능하나 **C1 파일 import 금지** (순환/결합 회피 — 자체 정의).
- 랭킹 결정성: `sorted(..., key=lambda)` 안정 정렬 + tie-break 는 ticker 문자열 등 결정적 키.
- **주의**: bool 은 int 서브클래스 → `int(sum(...))` 명시로 bool 반환 차단.
