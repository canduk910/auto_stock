# 3일치 AI 자문 취합 리포트 (2026-07-06 ~ 07-08)

> 작성: 2026-07-09 (메인 세션) · 원천: `daily_log_reports` + `parameter_recommendations` (Supabase 실측)
> 목적: 20:00 파라미터 추천 + 20:10 로그분석 3일치를 취합·중복제거하여 **실제 반영할 것**을 우선순위화.
> 결정(AskUserQuestion): 비중/파라미터 = **domain-expert 검증 후 선별** / 산출물 = 본 문서 + 반영안.

---

## 0. 핵심 진단 (한 줄)

**6개 전략 중 4개(momentum·donchian·bull_flag_breakout·vcp_breakout)가 3일 내내 신호 0건.** LTV(7/6 1신호 미체결)·VB(7/8 2신호→체결 -7,000원)만 작동. → AI의 비중/파라미터 추천은 **VB 외 표본 부족**, 진짜 문제는 **"왜 신호가 0건인지"**.

---

## 1. 3일 원본 요약

### 1-1. 매매·신호 실측 (strategy_funnel = signals→orders→fills)

| 전략 | 7/6 | 7/7 | 7/8 | 3일 신호 합 |
|------|-----|-----|-----|:---:|
| momentum | 0/0/0 | 0/0/0 | 0/0/0 | **0** |
| volatility_breakout | 0/0/0 | 0/0/0 | **2/2/2** | 2 |
| long_tail_volatility | **1/1/0** | 0/0/0 | 0/0/0 | 1 |
| donchian_swing | 0/0/0 | 0/0/0 | 0/0/0 | **0** |
| bull_flag_breakout | 0/0/0 | 0/0/0 | 0/0/0 | **0** |
| vcp_breakout | 0/0/0 | 0/0/0 | 0/0/0 | **0** |
| **실현손익** | 0 (미체결) | 0 (무거래) | **-7,000** | -7,000 |
| 로그 (INFO/WARN/ERR) | 3389/224/42 | 3194/76/11 | 3270/**750**/14 | — |

- 3일 총 체결 = VB 4건뿐(7/8, 105560 -5,300 / 066570 -1,700, 전량 15시 청산).
- 7/8 WARNING 750 = 대부분 **41-cap 666회**(사이클 197 대상).

### 1-2. 로그분석 findings (일자별, severity)

**7/6** (7건): tick coverage stale 52.4%(H) / stock_master_daily 조회실패(H) / Supabase RemoteProtocolError(H) / 잔고 500 34건(M) / scanner upsert skip(M) / LTV PENDING 미체결(M) / dkstock 매수가드 비활성·VI 폴백(L)
**7/7** (6건): **전 전략 신호 0건(H)** / stock_master_daily 오류(H) / Supabase 재시도(M) / BFB 후보공백 재prepare(M) / dkstock 매수가드 비활성(M) / VI 폴백(L)
**7/8** (6건): **41-cap 666회(H)** / stock_master_daily 조회실패(H) / 잔고 500 9건 retry복구(M) / ws UNSUBSCRIBE OPSP0003 not found(M) / **VB -7,000 15시 집중(M)** / dkstock 비활성·SOR→KRX 다운(L)

### 1-3. 파라미터 추천 (3일 일관성)

**비중 (recommended_weight, `applied_weight` 전부 NULL = 미반영):**

| 전략 | 현재(추정) | 7/6 | 7/7 | 7/8 | 방향 |
|------|:---:|:---:|:---:|:---:|------|
| momentum | 0.25 | 0.22 | 0.33 | 0.30 | **↑ (최우수)** |
| volatility_breakout | **0.36** | 0.18 | 0.18 | 0.18 | **↓↓ (최악 -15%)** |
| long_tail_volatility | 0.10 | 0.14 | 0.08 | 0.08 | ↓ |
| donchian_swing | 0.10 | 0.06 | 0.07 | 0.06 | ↓ (0거래) |
| bull_flag_breakout | 0.10 | 0.06 | 0.04 | 0.05 | ↓ (0거래) |
| vcp_breakout | ~0.06 | 0.06 | 0.06 | 0.06 | 유지 (0거래) |

**파라미터 (recommended_params, 3일 공통 방향):**
- **VB 디리스크**: `position_ratio` 0.5→0.35 · `stop_loss_rate` -5→-4.2~-4.5 · `max_positions` 2→1 · `k_value_krx_main` 1.3→1.45~1.5 · `min_trade_amount` 50B→80B · `daily_loss_limit` -7→-5
- **LTV 디리스크**: `max_positions` 4→3 · `position_ratio` 0.5→0.35~0.4 · 손절/트레일링 타이트 · `k_value` 상향
- **momentum**: `position_ratio` 0.25→0.2~0.22 · `daily_loss_limit` -10→-8 · `trailing_stop_rate` -1.3→-1
- **0거래 전략(BFB/donchian/VCP)**: 필터 완화(`min_trade_amount`↓, `volume_mult`↓, `max_scan_stocks`↑) = 신호 유도

**code_review_notes 반복 테마 (전 전략 공통, 빈도순):**
1. **퍼널 단계별 탈락 진단** — "왜 0건인지 분해할 로그/메트릭 부재" (최다, 전 전략)
2. **적응형 완화** — 무신호 N일 시 필터 단계적 자동 완화
3. **진입품질 필터** — 시간대(장초반 과열 회피)/수급(체결강도·거래대금 배수)/섹터 중복 제한
4. **time-stop / break-even stop** — 실패 돌파 빠른 제거 (LTV/momentum/VB, 승률 낮고 평균이익 큰 구조)
5. **포트폴리오 상관 제어** — 돌파류(VB/VCP/BFB) 동시보유·동일종목 중복진입 제한

---

## 2. 취합 진단 (중복제거·일관성 가중)

### 2-1. 확정 근거 (실데이터 뒷받침)
- **VB 감액**: 유일하게 실거래 표본 충분(-15% 누적, 승률 25%, 7/8 -7,000 단독), 3일 추천 일관 0.18. → **반영 근거 뚜렷.**
- **신호 생성 실패가 근본**: 4/6 전략 3일 0신호 = 비중/파라미터가 아니라 **후보 생성·필터 병목**. code_review·log finding 최다 반복과 정확히 일치.

### 2-2. 표본 부족·판단 보류
- momentum 상향: 최우수이나 거래 13건 소표본 → domain-expert 판단.
- 0거래 3전략 비중 컷/필터 완화: 성과가 아니라 **신호 0 원인 미규명** 상태 → 진단(C-1) 전 보류.

---

## 3. 우선순위 반영안

### A. 비중 (domain-expert 검증 → 선별 수동 apply)
| ID | 항목 | 근거 | 조치 |
|----|------|------|------|
| **A-1** | VB 감액 0.36→~0.18 | 실거래 -15%/승률25%, 3일 일관 | **우선.** domain-expert 검증 후 `POST /api/recommendations/{id}/apply` 또는 Settings |
| A-2 | momentum 상향 | 최우수, 소표본(13건) | domain-expert 판단 |
| A-3 | 0거래 3전략 비중 컷 | 비중 아닌 신호 문제 | **보류** (C-1 후) |

### B. 파라미터 (domain-expert 검증 → 선별, PARAM_RANGES 내)
| ID | 항목 | 조치 |
|----|------|------|
| **B-1** | VB/LTV 디리스크 (position_ratio↓/손절 타이트/max_positions↓/daily_loss_limit↓) | A-1 동반 검증 |
| B-2 | 0거래 전략 필터 완화 | **보류** (저품질 매매 위험, C-1 후) |

### C. 코드/관찰성 (TDD 사이클, domain-expert 동반)
| ID | 항목 | 비고 |
|----|------|------|
| **C-1** | **신호 0건 원인 진단** | **최우선·근본.** 기존 `strategy_funnel_snapshots`(사이클 170/175) + log_analysis funnel 먼저 활용 → 3일 0신호 원인(스캔부족 vs 패턴불충족 vs 주문탈락) 분석 → 부족한 per-filter 카운트만 보강. **신규구축 회피** |
| C-2 | 진입품질 필터(시간대/과열/수급/섹터) | 다수 전략 공통, 각 domain-expert |
| C-3 | 적응형 완화(무신호 N일→필터 완화) | C-1 진단 데이터 후 |
| C-4 | time-stop / break-even stop | LTV·momentum·VB |
| C-5 | 포트폴리오 상관 제어(돌파류 중복 제한) | — |

### D. 이미 처리됨 (확인만)
| 항목 | 처리 | 확인 |
|------|------|------|
| 41-cap 666회(7/8 H) | **사이클 197** log-cap 완료 | 구조적 축출 = cycle 149 backlog |
| DB retry(get_recent_daily/max_bas_dd) | **사이클 187·189** 양성 | purge=사이클 192 |
| VCP 데이터 churn | **사이클 196** | D+1(7/8~) mode=incremental 실측 |

### E. 관찰성/리포트 개선 (신규, 소형 사이클)
| ID | 항목 | 출처 |
|----|------|------|
| **E-1** | 일일 리포트에 **스캔 후보 수·전략 활성화 설정·장 개폐** 포함 (신호 0 정상/비정상 판단용) | 7/7 finding(H), C-1 시너지 |
| E-2 | graceful 실패 건수(get_recent_daily 등) 리포트 필수 노출 | 7/6·7/8 finding(H) |
| E-3 | 주문 생명주기(PENDING 유지시간/정정/취소) 모니터링 | 7/6 finding(M) |

### F. 신규 backlog 후보 (3일 취합으로 부상, domain/조사 필요)
| ID | 항목 | 근거 | 성격 |
|----|------|------|------|
| **F-1** | **잔고조회 HTTP 500** (inquire-balance) 호출빈도 완화 + 단기캐시 | 3일 반복(34/0/9건, retry 복구), 기존 "잔고 500 fallback" backlog와 동일 | MEDIUM |
| F-2 | Supabase httpx **연결풀/keep-alive/timeout 튜닝** (RemoteProtocolError 근본) | 사이클 187 retry는 증상완화, 근본은 stale HTTP/2 keep-alive | MEDIUM |
| F-3 | **dkstock 매수가드 3일 내내 OFF** (DKSTOCK_REGIME_ENABLED 미설정) — 의도 확인 | 3일 반복 WARNING | 확인 필요 |
| F-4 | ws UNSUBSCRIBE OPSP0003 not found (reconnect 후 중복 해지) | 7/8 2회 | LOW |

---

## 4. 기존 사이클/backlog 교차참조 요약

- **완료·처리됨**: 41-cap(197) / DB read retry(187·189) / daily purge(192) / VCP churn(196) / reprepare cap(189, BFB 후보공백).
- **기존 backlog와 일치**: F-1 잔고 500 fallback(장기 이월 MEDIUM) / cycle 149 구독 구조적 축출(41-cap 구조 fix).
- **신규 부상**: F-2 연결풀 튜닝 / F-3 dkstock 가드 OFF 확인 / F-4 중복 unsubscribe / C-1~5 전략 코드.

---

## 5. 다음 단계 (항목별 승인·실행)

1. **C-1 (최우선)** — 기존 funnel로 4개 전략 3일 0신호 원인 규명 (스캔 후보 수부터). = 반영안 대부분의 선행조건.
2. **A-1 + B-1** — VB 감액·디리스크 domain-expert 검증 → 선별 적용.
3. **E-1~3** — 리포트 관찰성 보강 (C-1과 병행 가능).
4. **F-1/F-3** — 잔고 500 완화 + dkstock 가드 의도 확인.
5. A-2/A-3/B-2/C-2~5/F-2/F-4 = C-1 진단 결과 + 승인 후 순차.

> **미실행 (범위 밖)**: `auto_apply_enabled` 활성화 안 함 / AI 값 일괄적용 안 함 / 0거래 전략 비중·필터 변경은 C-1 전 보류.

---

## 6. C-1 진단 결과 (2026-07-09, `strategy_funnel_snapshots` 4일 실측)

### 6-1. 결론: 파이프라인 정상 — 0신호는 대부분 "패턴 희소성"(버그 아님)

funnel 4일(7/6~7/9) 단계별 생존 종목 실측 — 탈락은 **거래대금/시총 필터가 아니라 패턴 검출 단계**에서 발생:

| 전략 | 유니버스 | 필터후 | 0으로 떨어지는 지점 | 성격 |
|------|:---:|:---:|------|------|
| donchian_swing | 200 | 55~64 | **신고가 돌파**(20일 신고가) 55→0~1 | 시장/패턴 (신고가 희소) |
| bull_flag_breakout | 47~143 | 16~36 | **플래그 검출**(폴 3~8→플래그 0~1) | 패턴 희소 |
| vcp_breakout | 200 | 63~67 | **Pullback 점진 수축**(베이스 2~6→0) | 패턴 희소(설계상 rare) |
| momentum | — | — | 상한가 근접(buy_threshold 29) 후보 없음 | 시장 (상한가 rare) |
| volatility_breakout | 15~43 | 7~29 | 준비 정상, intraday K돌파 대기 (**7/8 2건 발생**) | **정상** |
| long_tail_volatility | 6~76 | 2~38 | 준비 정상, intraday 대기 | **정상** |

→ 시스템은 정상 작동. 7월초 횡보장이 신고가/플래그/VCP 셋업을 거의 안 만든 것. VB/LTV는 후보를 준비하며 intraday 돌파를 대기(VB는 7/8 실제 2건 체결).

### 6-2. AI 추천 재평가 (진단 반영)
- **"퍼널 단계별 진단 부재" = 사실 아님.** cycle 170/175 funnel이 이미 정확히 제공(위 표). AI가 못 본 이유 =
  일일 리포트 `metrics`에 미노출(coarse signals/orders/fills만). → **E-1(리포트에 funnel 노출)이 진짜 해결책**, 신규 구축 불요.
- **"필터 완화로 신호 생성"(B-2) = 역효과 우려.** 0신호는 튜닝 가능 필터(거래대금/시총, 43~200 통과)가 아니라
  패턴 희소성. `min_trade_amount`↓해도 플래그/VCP 패턴은 안 생김. → **B-2 폐기 권고.**

### 6-3. 실제 defect / 후속
- **D-1 (관찰성 버그, 소형)**: VCP funnel step1/step2 = 0인데 step3 = 64~67 (7/6·7/9, 논리상 step3>step1 불가).
  코드상 step1/2 = `_scan_universe()` 동일 tickers(vcp_breakout.py:204-213)인데, 早期 return(L226) + 재-prepare/
  provisional 캡처 간 in-place upsert 비원자성으로 stale 잔존. **매매 무관.**
- **도메인 질문(버그 아님)**: donchian 20일 신고가 / VCP pullback / BFB 플래그 패턴이 한국 시장 일상 셋업에
  과도하게 엄격한가? = **전략 설계 문제 → domain-expert 자문 대상**(코드 버그 아님).

### 6-4. C-1 후속 반영안 (수정)
| ID | 항목 | 조치 |
|----|------|------|
| **E-1 (승격, 최우선)** | 일일 리포트에 전략별 funnel 단계 + "0신호 = 패턴희소 vs 후보부족" 자동 판정 노출 | AI #1 요구 실질 충족. 소형 관찰성 사이클 |
| **D-1** | VCP funnel step1/2 기록 정합 | 소형 수정 |
| **도메인 자문** | 패턴 엄격도 vs 시장 (신고가/플래그/VCP 셋업 조건) | domain-expert, 사용자 판단 |
| **B-2 폐기 / A-3 유지** | 0거래 전략 필터완화·비중컷 = 패턴 문제라 무효 | 보류→폐기 |

**C-1 핵심 시사**: 3일 AI 자문이 "시스템 고장"으로 오인한 0신호는 대부분 **정상(패턴 희소 + 횡보장)**. 진짜 gap =
(a) 기존 funnel을 리포트에 **노출**(E-1), (b) VCP funnel 기록 정합(D-1), (c) 패턴 엄격도 **도메인 판단**.
