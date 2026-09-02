# 피라미딩 심층 검토 (2026-09-03) — 정량 근거 스크립트·데이터 영속화

보고서: `_workspace/domain_consult/pyramiding_deep_review_20260903.md`
이 디렉토리는 보고서의 정량 근거(EC2 운영 DB read-only 실측 → 왕복 추출 → N단위 MFE/사다리 시뮬)를
scratchpad 에서 옮겨 온 것이다(보고서 열린 질문 "시뮬 스크립트 영속화" 처분 = 즉시 영속). 재산출 시
`dbcheck*.py` 로 왕복을 다시 뽑고 `adv_sim.py`/`analyze*.py` 로 사다리 변형(V0~V4)을 재현한다.
