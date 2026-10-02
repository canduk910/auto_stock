# cycle402 Red — 청산 사유 표기 시정

- 명세: `_workspace/domain_consult/cycle367_exit_rules_consult.md` §4 · ETF 설계 §4.2.3-4 / §10.2 R4 (b)
- 테스트: `tests/unit/engine/test_cycle402_exit_reasons.py`
- Red 실행(main b04b0b0 + 테스트만): **21 failed, 7 passed** — 실패 = 새 이름 3종 부재 · 다섯 분기 반환 · `force_clear_signal`/`resolve_force_clear_signal` 부재 · 15:20 하드코딩. 통과(가드) = 기존 값 불변 · BFB/VCP 샹들리에 · donchian 하드 손절 · 15:20 기본 FORCE_CLEAR · 훅 예외 시에도 판다 · risk.py `!= NONE`.
- 설계 결정: `check_force_clear()` 반환 모양(`list[str]`)은 유지하고 사유는 같은 전략의 `force_clear_signal(ticker)`(기본 FORCE_CLEAR)를 never-raise 해석기 `strategy_base.resolve_force_clear_signal` 로 읽는다 — VB·LTV 무접촉, 골든 `force_clear_1520` 무변경.
- Green: 새 테스트 30 통과(`--log-level=DEBUG`). 검토 반영 = 해석기 훅 조회까지 try 안으로 · `order_engine.py` 이름 분기 0 AST 추가 · 동어반복 단언 제거.
- 돌연변이 5종 전부 검출: M1 15:20 하드코딩 복원 · M2 NONE/BUY 거름 제거 · M3 BFB 시간청산 옛 이름 · M4 except 축소 · M5 훅 조회 try 밖.
- 전체 스위트(재핀 후): 14234 passed, 15 skipped, 335 xfailed, 13 xpassed, 0 failed. cycle398 골든 무변경.
