# macro/ — macro_lite vendor 패키지

원본 = `/Users/koscom/Projects/stock-manager/packaging/macro_lite/`(원본은 읽기 전용, 이 리포에서 수정하지 않는다).
vendor 일자 = 2026-09-18 (cycle303).

`macro_lite/` · `data/` · `tests/` · `pytest.ini` · `requirements.txt` 는 원본 `backend/` 산출물을
**무수정 복사**한 것이다. 재이식(원본 갱신 반영) 시 이 다섯 항목은 새로 `cp -R` 로 통째로
덮어쓴다 — diff 를 부분 반영하지 않는다. `main.py` · `Dockerfile` · `.dockerignore` 는 이 리포 전용
통합 코드이므로 재이식 때도 보존한다.

세부 통합 계약(nginx·compose·배포 분류·도메인 제약)은 `_workspace/cycle303_macro_integration_spec.md` 와
`docs/macro-lite.md` 가 정본이다.
