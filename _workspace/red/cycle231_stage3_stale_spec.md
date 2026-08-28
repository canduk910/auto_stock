# 사이클 231 명세 — kojiro `_held_stage3` 날짜 키 무효화 (P2-5)

> 작성: team-leader, 2026-08-29
> 자문 정본: `_workspace/domain_consult/cycle231_kojiro_stage3_stale.md` (전제 정정 2건 포함 — 필독)
> 배포: cycle230 과 주말 동반 푸시(사용자 확정).

## 전제 (자문 정정 반영 — 구속력)

- kojiro `recompute_held_atr` 는 **skip 게이트 없이 보유 전수 순회**한다(cycle225 게이트는 donchian 것). cross-day stale 경로 = ① recompute 루프 미실행/중도중단(`boot_manager:341` 단일 try) ② **recompute 이후에 도는 prepare** — 07:59 재-prepare(`scheduler:743`, 후보 빈 날 — kojiro strict entry 특성상 흔함) + 16:20 evening prepare. boot prepare 는 positions 복구 전이라 무관.
- `prepare()` held 마킹(`:394-400`)은 **ATR 밴드 게이트(`:365`)보다 뒤** — 밴드 상한(>6%) 이탈 = 변동성 급팽창 = **급등 종목이 마킹을 못 받는다**(승률 11%/RR 3.19 전략의 오른쪽 꼬리를 배관 실패로 자르는 경로, 실도달 가능).
- `:649` 가 fail-open(`_held_stage3=False`, §1·§2·§4 유지)을 이미 계약화 — 이번 시정은 신설 정책이 아니라 **한 파일 안의 두 답 통일**.

## 행위

### W1. 날짜 키 무효화 (`kojiro.py` 단독)

- `_held_stage3: dict[str, tuple[date, bool]]` 로 전환 — 값 = `(판정 수행일, stage==3)`. **판정 수행일**이다(봉 날짜 아님 — 연휴에 무효화가 안 걸린다).
- 기록 지점 전부(prepare `:400` + recompute 5곳) 동일 튜플 형식으로 갱신.
- 소비처(`:897`): `entry = self._held_stage3.get(ticker)` → **`entry is not None and entry[0] == today(KST) and entry[1]`** 일 때만 §3 발화. "익일 아침 발화" 설계는 불변 — D+1 07:55 recompute 가 D 봉으로 D+1 날짜 재기록 → 09:00 소비(kojiro 는 프리장 평가 보류 대상이라 마진 충분).
- `on_position_closed` pop(`:1040`) 불변.

### W2. 관측 (자문 Q3)

- stale/미판정으로 §3 를 억제한 경우 `[kojiro_stage3_stale_skip] ticker=%s judged_on=%s age_days=%d` — cap 1회/ticker/일(날짜 키 자기 리셋), **age_days 1 = INFO / ≥2 = WARNING**(debug 단독 금지 — `_DbLogHandler` INFO 컷).
  - 발화 조건 = 오늘 판정이 아닌 `True` 엔트리를 만났을 때(어제 True 를 억제한 사건). `False`/부재는 로그 불요(정상 미발화).
- `[kojiro_stage3_exit]`(`:898`) 에 `judged_on=%s` 필드 추가(사후 복기용, 문구 앞부분 byte 보존).

### W3. 부수 방어 (자문 부수 발견 — 매매 무변경)

- `kojiro.py:685` `pos.buy_date < today` 비교를 per-ticker try 안으로(또는 사전 `isinstance(pos.buy_date, date)` 가드 + 미충족 시 해당 종목 graceful skip + WARNING 1행) — cycle226 L-2 동형(try 밖 예외 지점이 뒤 보유 종목의 ATR/stage3/floor 재계산을 통째 유실). 현재 잠복(`boot_manager:162` 가 date 보장)이므로 방어만.

### W4. 테스트

- **의미 전환 4곳**: `test_kojiro.py:167/277/303` + `test_cycle220_kojiro_breakeven_floor.py:371` 의 `_held_stage3` 직접 주입 → `(오늘, True)` 튜플로 갱신(이 전환 자체가 "오늘 판정이면 발화" 계약 문서).
- **신규 RED 짝**: 어제 날짜 `(yesterday, True)` 주입 → §3 **미발화** + `[kojiro_stage3_stale_skip]` 발화(age 1=INFO, 2=WARNING, cap 1회/일) / 오늘 `(today, False)` → 미발화·로그 0 / 오늘 `(today, True)` → 발화 + `judged_on` 필드 / recompute·prepare 기록이 튜플 형식인지 / W3 방어(비정상 buy_date 1종목이 뒤 종목 재계산을 죽이지 않음).
- 전체 회귀 0 실패.

## 제약

- **kojiro.py + 테스트만** — 8영역·타 전략 diff 0. FREEZE(진입·파라미터 무변경 — 청산 §3 판정 유효성만). §4 샹들리에 2.5 불변(억제 대가를 트레일링 조임으로 메우지 말 것). PARAM_RANGES 신규 0.
- 커밋은 team-leader. cycle230 과 주말 동반 푸시.
- 자문 명시 한계(문서화): (a) 는 다수 케이스에서 하루 늦은 청산 실비용 — kojiro 저승률·고RR 구조라 유리한 교환이며 **고승률·저RR 전략에 복사 금지**. `[kojiro_stage3_exit]` 표본 ~20건 시 §3 존재 가치 재검정.
