# 세션 예약 점검 3건 — 재부팅 복원용 (2026-10-12 06:4x 저장)

macOS 업데이트로 세션 예약(session-only cron)이 사라지므로 원문을 그대로 남긴다. 복원 = 각 항목을 CronCreate(cron, prompt, recurring=false)로 다시 등록.

## cron `7 10 12 10 *`

```text
[예약 10-12(월) 10:07] 10-09 배포(실비용 cycle411 + 거래일지 1a cycle412)의 첫 거래일 실측 — EC2 에서 ① journal_worker Up·RestartCount 0·docker stats <160m ② docker logs 에 [journal_fetch_error]·[journal_rotate_error]·[journal_write_error]·[journal_gap] 건수 ③ trade_journal_cursor 갱신 시각(15초 주기) ④ 오늘 trade_history 체결 주문 수 = trade_journal_orders(source=log_harvest) 행 수, 사유 미상 매도 0, trade_journal_stops 의 first/change 사건 생성 여부(보유 15종목) ⑤ backend 로그 [cost_overlay_unavailable] 0 · [cost_overlay_unmatched_cost]·[cost_overlay_tax_unallocated] 건수 ⑥ 대시보드 API(/api/costs/today·/api/performance/summary) 정상. 이상이 있으면 원인과 함께, 없으면 짧게 사용자에게 보고. (오늘은 신규 매수 멈춤 날이라 매수 행은 0 이 정상)
```

## cron `42 21 12 10 *`

```text
[예약 10-12(월) 21:42] 주계좌 전환 전날 점검 — 사용자 결정 10-08: 10-13(화) 07:00 대체·이체 → 07:40 전 bankis-fee 로 전환, 10-08·10-12 이틀 신규 매수 멈춤(buy_paused true: kojiro·donchian_swing·vcp_breakout·bull_flag_breakout·etf_trend). 확인: ① positions 의 buy_date 가 전부 10-07 이하(10-08·10-12 신규 매수 0) — 아니면 사용자에게 보고(그 종목은 10-13 대체 불가) ② 다섯 전략 buy_paused 가 아직 true ③ EC2 ~/auto_stock/.env.bankis-fee_20261008 (bankis-fee 4값) 존재·600, 현재 .env·컨테이너 계좌 끝 1589 ④ 사용자에게 내일 07:00 대체·이체 리마인드(결제 완료분 전부 + 예수금 — 10-12 매도분 대금은 D+2 라 일부 남을 수 있음).
```

## cron `4 7 13 10 *`

```text
[예약 10-13(화) 07:04] 주계좌 전환 당일(사용자 결정 10-08) — 사용자가 07:00 에 bankis-fee(계좌 끝 5334)로 주식 대체·예수금 이체. 순서: ① 사용자에게 완료 확인, 옛 계좌(끝 1589) 잔고가 보유 0 이 됐는지 GET /api/balance 로 확인(옛 계좌에 남은 주식이 있으면 전환 중지·보고) ② 07:40 전: `cp .env.bankis-fee_20261008 .env`(600) → kis_quote_accounts label='bankis-fee' active=false → backend 재생성 `docker compose -f docker-compose.prod.yml -f docker-compose.tls.yml -f docker-compose.tls2.yml up -d --no-deps backend`(마커 .tls_enabled·.tls_stage2 확인) → health 200 ③ 컨테이너 계좌 끝 4=5334 · GET /api/balance 종목·수량 = positions · 예수금 · 07:45 부팅 로그 · 체결통보 구독 ④ 모두 정상이면 다섯 전략 buy_paused false(kojiro·donchian_swing·vcp_breakout·bull_flag_breakout·etf_trend) → GET 확인 ⑤ 실패 시 롤백(.env.rollback_20261007 → .env, active=true, backend 재생성) — 단 주식이 이미 새 계좌로 갔으면 롤백 대신 사용자와 상의, buy_paused 는 그대로 유지. 07:45 전 못 끝내면 즉시 보고. ⑥ 저녁 21:10 대사에서 수수료 0.014% 확인.
```
## 덧붙임 — 10-11 배포분 첫 거래일 확인 (10:07 점검에 함께 본다)

10:07 예약 원문은 10-09 에 만든 것이라 아래가 빠져 있다. 복원 시 10:07 프롬프트 끝에 붙인다.

- llm_worker 08:15·08:35·08:55 실행 — `exit_ai_runs` 오늘 행·`exit_ai_evaluations` 건수 · 잔고 화면 「AI 판단」 칸에 값이 찍히는지 · 컨테이너 Up·메모리 <192m
- 잔고 조회 5xx 로그에 msg_cd 가 남는지(EGW00215 여부, cycle447)
- NDX2x `[ndx2x_signal]` 로그 · `overseas_index_daily` 적재 300행 이상
- 섀도 전략(VB·LTV·momentum·ndx2x) `[shadow_buy]` 기록
- 07:45 부팅 `[corporate_action_*]`·`[boot_recover_strategy_unknown]` · 장중 `[sell_send_unknown]`·`[sell_insufficient_unexplained]` · 경고등 색(워크리스트 10-10 항목)
- 21:30 `daily_log_reports` 가 OpenAI 없이 metrics 로 upsert 되는지(cycle445) — 21:42 점검에서 확인
- 10-13 21:10 실비용 대사에서 수수료율 0.014% 확인(계좌 전환 뒤)

## cron `33 18 12 10 *` (10-12 15:4x 추가)

```text
[예약 10-12(월) 18:33] BFB 「슬롯이 비는 순간 매수」 결함 수정 착수 — 사용자 결정 10-12 「슬롯비는 순간 매수 문제 오늘 저녁에 해결하자」. 슬롯 4개가 찬 동안 check_buy_signal 이 is_max_positions()(bull_flag_breakout.py:989)에서 먼저 끝나 _prev_price(:1050) 가 갱신되지 않아, 슬롯이 비는 첫 틱에 이미 돌파선 위 종목이 「방금 돌파」로 읽힌다(실사례 3건 전부 손실). 근거 = _workspace/domain_consult/2026-10-12_bfb_breakout_volume_mult.md. team-leader 라우팅 TDD 사이클, 고치는 방식은 구현 전 사용자 확인, 커밋·push 는 따로 묻고 배포는 21:35 이후. 미결: breakout_volume_mult 1.0→1.5 여부.
```

## cron `40 15 13 10 *` (10-13 00시대 추가)

```text
[예약 10-13(화) 15:40] cycle449(BFB·VCP 만석 중 직전 가격 추적) + cycle450(나스닥2배 폴 루프 NameError 수정) 배포 — 사용자 결정 10-13 「오늘 15:40에 배포하자, 4번도 고쳐서 함께」. 15:30~16:00 창 확인 → 커밋 확인 → 배포 모드·EC2 메모리·디스크 점검 → git push origin main(권한 거부면 사용자에게 ! git push 요청) → CI·Deploy 확인 → 재기동·health·계좌 끝 4자리·구독·ndx2x 폴 루프 예외 0 실측 → 보고. 16:00 전에 못 끝낼 것 같으면 중단하고 21:35 이후로 미룰지 묻는다.
```

## 10-13 07:04 계좌 전환 덧붙임 (사용자 결정 10-13)

`cp .env.bankis-fee_20261008 .env` 직후, backend 재생성 전에 `.env` 의 `OPENAI_RECOMMEND_MODEL` 을 `gpt-6.1-sol` 로 맞춘다(전환용 파일은 `gpt-6-luna` 로 낡았다).
