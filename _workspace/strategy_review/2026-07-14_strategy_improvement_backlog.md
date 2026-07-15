# 매매전략 개선안 백로그 (Phase A) — 2026-07-14

> 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` / 상세 자문: `2026-07-14_phaseA_domain_analysis.md`
> 데이터: 신규 프로젝트 `qqylpfzlbfxnkrrdcsxr` (MCP READ-ONLY) + 코드/DB 교차검증
> 범위: **prepare/파라미터 계층 한정** — 매매 안전성 8영역 무관 (208/209와 동일 blast radius)

## 핵심 발견 4

1. **systemic — AI 자문 "감액만 적용" = 단조 조임 ratchet** (`auto_apply_recommendations` L1077: `float(v)>current_v`만 통과, 완화 경로 없음). 손절/일일한도를 시간에 걸쳐 조여 전략을 교살. **단, 신규 DB의 조임은 수동 apply(43건) 결과 — `applied_auto`=0** → 현재 손실 원인 아닌 **auto 켜는 순간 재발하는 예방 대상**.
2. **donchian 단독 방치** — daily_loss_limit **-0.8**(코드 -8) + stop **-3.2**(코드 -7). VB/LTV/momentum은 수동 복원됨. → 208/209로 신호는 나와도 **진입 직후 죽음**(작은 손실 1회=당일 중단). 5/19 이후 매매 중단과 일치.
3. **BFB·VCP 도입 후 매매 0건** — 희소(정상) vs 진입 과엄 미구분(성과지표 부재) → Phase B funnel 스윕 필수.
4. **성과 극과 극** — momentum +47K(승률30%·손익비2.67, 검증된 최고, 6/17 중단) / LTV +18K / donchian -10K(6건, 교살) / VB **-40K**(승률33%·손익비1.57=**기대값 음수**).

## 우선순위 백로그

| # | 개선안 | 전략 | 문제(근거) | 시정(값) | 사이클 | 우선 |
|---|---|---|---|---|---|:--:|
| A | **donchian 손절/한도 복원** | donchian | daily_loss -0.8=당일중단 + stop -3.2 상시손절 → 208/209 무력화 | daily_loss -0.8→**-6.0**(보수 -4.0), stop -3.2→**-6.0** | 1 | **P0** |
| B | **auto_apply 손절키 제외** | 전전략 | 조임만 통과·완화경로 없음=ratchet, auto 켜면 재발 | `_CONSERVATIVE_KEYS`서 daily_loss+손절5키 제거 | 1 | **P0** |
| C | **VB position_ratio 축소** | VB | 기대값 음수, pos 0.5+max 2=2종목 몰빵, avg_loss -5,947 최대 | pos_ratio 0.5→**0.35**(±max_pos 3) | 1 | **P1** |
| D | **진입임계 PARAM_RANGES 제외(1차)** | momentum,donchian | buy_threshold/donchian_period=진입 정체성(208/209 논리) | 2키 PARAM_RANGES 제외 | 1 | **P1** |
| E | **LTV 재진입 쿨다운** | LTV | 테스 이틀 whipsaw -20,000, LTV 무방비 | on_position_closed 훅 override, 2~3영업일 *설계 자문 선행* | 1+consult | **P1** |
| F | **momentum 중단 원인 규명** | momentum | +47K인데 6/17 중단, 유니버스/차단 vs 희소 미구분 | funnel+로그 실측, 204 반영 확인 | Phase B | **P1** |
| G | **BFB/VCP funnel 스윕** | BFB,VCP | 무거래, 희소 vs 과엄 미구분 | 단계별 탈락 관찰→pole 20→15·base_depth 0.35→0.5 등 완화 후보 | Phase B | **P1** |
| H | 진입임계 제외(2차)+min_mcap floor | LTV,VCP,전 | min_prdy_rate/last_pullback_max 정체성, min_mcap 과조임 고갈 | 2키 제외 + min_mcap floor 100억 | 1 | P2 |
| I | VB k값 상향 | VB | k 1.3 페이크 물림→승률↓ | 1.3→1.5(funnel 후) | Phase B후 | P2 |
| J | 복원(완화) 경로 노출 | 전전략 | 완화 자문 영구 무시 | 리포트 미적용 완화 노출+원클릭 | Phase C | P2 |
| K | 비중 재배분 | BFB,VCP→mom | 무거래 12%×2 유휴 | G/F 후 판정 | Phase B후 | P2 |

## P0 즉시 사이클화 스펙 (208/209 형식)

**P0-A — donchian 손절/한도 복원** (DB UPDATE + `00_leader_trading_rules.md` 동기화)
```
donchian_swing.params: daily_loss_limit -0.8→-6.0 (보수 -4.0) / stop_loss_rate -3.2→-6.0
                       min_market_cap 100억 유지(원복 보류)
가드: is_daily_loss_exceeded / STOP_LOSS 값만 변경, 로직 불변. 안전성 8영역 diff 0.
선행: 208/209 효과를 교살 상태에서 측정하면 오판 → P0-A 먼저 또는 동시.
```
**P0-B — auto_apply ratchet 차단** (`recommendation_engine.py`)
```
_CONSERVATIVE_KEYS 에서 제거: daily_loss_limit(1순위) + stop_loss_rate/intraday/overnight/main/pre_nxt
position_ratio 도 함께 제외 권고(자동 축소=과소진입). → auto_apply 는 weight 감액만 잔존.
가드: auto_apply 손절키 0건 단언 + AST. 현재 auto=0이라 즉효손실 없음=예방적 P0.
```

## Phase B / C 이관

- **Phase B (funnel 스윕)**: BFB(pole/flag/돌파)·VCP(base/수축/눌림/EMA)·momentum(유니버스/차단) 단계별 탈락 실측 → 완화 후보 확정 + VB 재진입 손실 trade-level + 비중 재배분.
- **Phase C (자문 품질)**: 복원 경로 노출 / auto_apply 재설계(param은 사람·weight만 자동?) / 진입임계 전면 제외 함의.

## 데이터 한계

1. 신규 프로젝트 성과 표본 부족(donchian 6/BFB 0/VCP 0) → A는 "교살 해제 후 재관측" 목적, 성과개선 확정 아님.
2. ratchet 계보 = 수동 apply(auto=0) → P0-B는 미래 재발 방지 성격.
3. funnel 실측 부재 → 완화 후보값(pole 20→15 등)은 **스윕 시작점**, 확정값 아님.
4. BFB pole_min_return code=15 vs **DB=20**(실효) → 논의는 DB 기준.

---

## Phase B 결과 (2026-07-14, funnel 실측 + BFB 오프라인 스윕)

**funnel 병목 단계 (신규 프로젝트 7/14):**
- **BFB**: 유니버스 293 → step5 폴 검출 **80**(-72%) → step6 플래그 **12**(-85%) → step7 거래량 1 → 최종 1. 병목 = 폴/플래그 패턴 단계.
- **VCP**: 331 → step5 EMA정렬 **14**(-96%, 추세필터=정당) → step6 베이스 6 → step7 Pullback **0**(전멸). 병목 = EMA(추세, 시장종속) + Pullback(정의적 패턴).

**BFB 완화 스윕 (95종목 subset):** A(pole20/retr0.382)=2 / B(pole15/retr0.382)=3 / **C(pole15/retr0.5)=10 (3.3배)**. → `flag_retracement_max` 0.382→0.5 가 최대 레버, pole 20→15는 DB/코드 정합(소폭). flag_volume_ratio 0.6 안전장치 유지.

**Phase B 판정:**
| 전략 | 판정 | 조치 |
|---|---|---|
| **BFB** | **진입 과엄 (완화 여지 실측)** | **G-B1 (P1)**: `flag_retracement_max` 0.382→**0.5**(3.3배 레버) + `pole_min_return` DB 20→**15**(코드 정합) + flag_volume_ratio 0.6 유지. 사이클화 후보(198 답습, domain-consult+TDD) |
| **VCP** | **순수 희소 (시장 종속)** | **G-V1 (P2/관찰)**: EMA 추세필터 96% drop(정당) + Pullback 횡보장 전멸 = 상승장 전환 시 자연 발화. param 완화 ceiling 낮음(upstream EMA/base 6종목 제한). **상승장 대기, 완화 보류**. (last_pullback_max 0.1→0.15는 소폭, 우선순위 낮음) |
| **momentum** | **라이브 관찰 필요** | **G-M1 (P1)**: 6/17 중단은 구 프로젝트 데이터. 신규 프로젝트 관찰 시작. buy_threshold 29=진입 정체성(불변, PARAM_RANGES 제외=P1-D). 6/17 중단이 유니버스/차단(204 반영)인지 희소인지 신규 로그로 재판정 |
| **VB** | trade-level 재진단 | -40K 손실이 재진입 whipsaw vs 신규 손절 구성 → trade_history 상세(P1 후속) |

## 다음 단계 (Phase B 후)
- **즉시 사이클화 후보**: **G-B1 (BFB flag_retracement 0.382→0.5 + pole 20→15)** = 실측 근거 확실, 198 답습. + Phase A P1 = **C(VB pos_ratio 0.35)·D(진입임계 PARAM_RANGES 제외)·E(LTV 재진입 쿨다운)**.
- **관찰/보류**: VCP(상승장 대기)·momentum(라이브)·VB trade-level.
- **Phase C**(자문 품질)는 별도.
