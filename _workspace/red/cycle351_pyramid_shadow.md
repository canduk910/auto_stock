# cycle351 Red — 피라미딩 가상 기록(셰도) leaf + 콜렉터 끝 키 (tdd-engineer, 2026-09-25)

명세(정본) = [`cycle351_pyramid_shadow_spec.md`](cycle351_pyramid_shadow_spec.md) · 설계 = `_workspace/design/2026-09-24_three_stage_sizing_pyramiding.md`.
base = HEAD `0a7752a`(프로덕션 무변경). 이 단계는 **테스트만** 썼다 — `src/` 무접촉, 커밋·push 없음.

## 1. 골든 (§4-1) — 확장 전 코드로 먼저 만들었다

- 파일 = `tests/fixtures/cycle351/collector_golden_head.json` (190줄, sha256 `23c9f94f…942e`)
- 입력 정의 = `tests/unit/engine/test_cycle351_pyramid_shadow_collect.py::install_golden_inputs` / `_golden_collect`
  (로그 6 + ERROR/CRITICAL 2 · 거래 5 · api/funnel/stages/포트폴리오 고정 · 레지스트리 vcp·kojiro·donchian ·
  셰도용 페어 3 + 일봉). 시계 = T=2026-10-19(월) 21:30 KST 동결, `now_kst` 명시.
- 생성 = 세션 스크래치패드 `gen_cycle351_golden.py`(커밋 안 됨): `tests.conftest` import → `MonkeyPatch` 한 벌로
  `_golden_collect(mp)` → `pyramid_shadow` 를 뺀 10키를 `{base_sha, generated_by, target_date, frozen_utc, metrics}`
  로 감싸 `json.dumps(ensure_ascii=False, indent=2)`. 스크립트는 `git rev-parse HEAD == 0a7752a` ∧ `src/` 무변경 ∧
  leaf 부재를 단언한 뒤에만 쓴다. 두 번 돌려 sha 동일(결정적) 확인.
- 판정: `test_golden_existing_ten_keys_byte_identical_to_head` = HEAD 에서 **초록**(Green 뒤에도 초록이어야 함) ·
  `test_golden_input_appends_pyramid_shadow_last_and_it_actually_ran` = Red(키 부재).

## 2. 새 테스트 — 82개

| 파일 | 수 | 덮는 것 |
|---|---|---|
| `tests/unit/engine/test_cycle351_pyramid_shadow_core.py` | 34 | C1~C14 + LADDER_C + 손절 먼저(M7) + 앵커 뒤 봉 무시 + D0 앵커(C7d) + 비유한 N 거부 |
| `tests/unit/engine/test_cycle351_pyramid_shadow_collect.py` | 39 | 골든 2 · 반환 모양 · A1~A12 · 요약 · 50개 상한 · add_stage/add_macd |
| `tests/unit/ast/test_cycle351_pyramid_shadow_scope.py` | 9 | §4-4 범위 가드(S1~S5) |

코어 기대값은 전부 손계산(각 테스트 docstring 에 날짜별 판정).

## 3. Red 확인

```
python -m pytest -q -p no:cacheprovider \
  tests/unit/engine/test_cycle351_pyramid_shadow_core.py \
  tests/unit/engine/test_cycle351_pyramid_shadow_collect.py \
  tests/unit/ast/test_cycle351_pyramid_shadow_scope.py
→ 78 failed, 4 passed
```

- 73건 = leaf 부재 게이트(`_ps()`/`_require_leaf()` 의 `pytest.fail("Red — … 미구현")`, cycle249 `_collector()` 선례 —
  수집 오류가 아니라 실패로 떨어진다)
- 5건 = 단언 실패: 골든 입력 키 순서(11키 기대) · A6 `"pyramid_shadow" in metrics` · A10 상한 상수 부재 ×2 ·
  S1(`pyramid_shadow` 를 import 하는 프로덕션 모듈 = [] ≠ {콜렉터})
- 4 passed = 골든 10키 일치(HEAD) · S1b ×3(하류 3파일은 셰도를 모른다 — 지금도 참, Green 뒤에도 참이어야 함)

기존 테스트 중 이번에 붉어지는 것 = **4건**(키 순서 핀):
`test_cycle249_collect_metrics.py::test_collect_when_called_then_metric_keys_identical` ·
`test_cycle259_log_metrics_collector.py::test_l3_metric_key_order_is_byte_identical` · `::test_l3b_reexported_entrypoint_returns_same_shape` ·
`test_cycle349_vcp_breakout_events_metrics.py::test_e4_key_appended_last_after_existing_nine`.

## 4. 충족 가능성·돌연변이 사전 검증 (스크래치 워크트리, 본 트리 무접촉)

스크래치 `git worktree`(HEAD) 에 명세를 글자대로 옮긴 **일회용 참조 구현**(leaf + 콜렉터 배선)을 넣고 돌렸다 —
새 82 + 수정된 기존 62 전부 초록. 같은 참조에 §5 돌연변이 M1~M12(M1·M9 는 두 변형씩 = 14) + 추가 9종(본전 같은 날 발동 · `be_atr[d]` ·
kojiro 창 전부 · donchian 오래된 순 · int 절삭 삭제 · sell_time 게이트 · T 이후 매수 · `bas_dd` 필터 · 오늘 게이트) +
콜렉터 5종(사본 아님 · wait_for 삭제 · 키 위치 · never-raise 삭제 · 예산 int 아님)을 하나씩 넣어 **28/28 KILLED**. 참조 구현은 Green 몫이 아니므로 본 트리에 두지 않았다(워크트리는 검증 뒤 삭제).

## 5. 기존 테스트에 한 일

- 키 순서 핀 3곳에 `"pyramid_shadow"` 를 맨 끝에 추가(cycle249 · cycle259 · cycle349).
- 콜렉터를 실제로 부르는 기존 픽스처 8파일에 `_collect_pyramid_shadow` 대역(`raising=False`) —
  cycle249 `isolated` · cycle259 `_isolate_collector` · cycle349 `isolated` · cycle251 `collect_deps` ·
  cycle199 ×2 · cycleH `_stub_common` · b2_b4 ×2 · log_analysis_metrics. (DB·30초 상한을 타지 않게.)

- 영향 인덱스 `_workspace/test_index.yaml` 재생성(`build_index.py` **백엔드만** — 커밋된 인덱스가 백엔드 포맷이라
  프론트까지 돌리면 들여쓰기 전체가 바뀌어 26만 줄 diff 가 난다. 실측). `test_cycle318_impact_index_freshness` 초록 확인.

## 6. Green 이 함께 고쳐야 할 기존 핀 (실측)

참조 구현을 넣은 스크래치 워크트리에서 `tests/unit` + `tests/contract` 전체를 돌려 **붉어진 것 전부**(5건, 그 밖 0):

| 가드 | 고칠 값 |
|---|---|
| `tests/unit/ast/test_cycle287_ast_scope.py::test_s1b_whole_src_tree_is_byte_identical_except_the_three` | `_SRC_TREE_FILES` 155 → 156 + `_SRC_TREE_DIGEST` 새 값(직전 값 `397c83e3…8d84` 를 주석에 기록하는 관례) |
| `…test_cycle287_ast_scope.py::test_s1d_no_new_files_slip_into_pinned_dirs[src/engine]` | `_PINNED_DIR_FILE_COUNTS["src/engine"]` 77 → 78 |
| `tests/unit/ast/test_cycle290_ast_scope.py::test_g290_3_no_new_module_under_src_engine[src/engine]` | `_ENGINE_PY_FILES["src/engine"]` 에 `"pyramid_shadow.py"` 등재(사유 주석) |
| `tests/unit/ast/test_cycle291_ast_scope.py::test_a8_no_new_leaf_in_src_engine` | `src/engine/*.py` 기준선 67 → 68(docstring 에 cycle351 줄) |
| `tests/unit/deploy/test_cycle318_impact_index_freshness.py::test_backend_index_is_fresh` | leaf 생성 뒤 `python tools/test_impact/build_index.py` 재실행(백엔드만) |

8영역·`scheduler.py`·전략 7파일·`strategy_base.py` 핀(`test_cycle287` `_BASE_SHA`·`_SCHEDULER_LINES` 등)은 참조 구현에서
**움직이지 않았다** — 움직이면 범위 위반이다. 문서(`src/engine/CLAUDE.md` 모듈 맵 등)는 `/sync-docs` 몫(테스트 핀 아님).

## 7. 명세 해석 (모호했던 점)

1. **상한 상수 이름** — 명세는 30초만 정했다. 테스트가 상한을 줄일 수 있게 `log_metrics_collector._PYRAMID_SHADOW_TIMEOUT_SECS = 30.0` 로 정했다(A10).
2. **매수일 청산(anchor_idx == entry_idx)** — 표에 없다. §1 「사다리는 앵커보다 늦게 나가지 않는다」에서 「D0 에 앵커가로 청산,
   트랜치 1, kind=anchor」를 도출해 `test_c7d` 로 고정했다(kojiro 당일 손절 = S1 에서 sell_date == buy_date).
3. **A6 get_trade_pairs 예외 → 키 None** — leaf 가 이 예외를 삼켜 dict 를 돌려주면 키가 None 이 아니다. 그래서 leaf 는
   `get_trade_pairs` 예외를 **전파**하고 콜렉터가 흡수한다고 읽었다(레코드 단위 예외 = 일봉·계산만 레코드 error).
4. **보유 레코드의 exit_date/exit_price/exit_time** — 「실제 청산」 필드로 읽어 `None` 을 기대했다.
5. **params_source 의 비-폴백 값** — 명세는 `"fallback"` 만 정했다 → `!= "fallback"` 만 단언.
6. **일봉 예외 레코드의 error 문자열** — 미정 → 비어 있지 않은 문자열만 단언. `no_entry_bar`·`no_atr` 는 글자 그대로.
   donchian 앞 봉이 `atr_period+2` 미만이면 `_atr` 가 0 → `no_atr` 로 기대.
7. **error 레코드가 open_n/closed_n 에 들어가는가** — 미정 → error 가 섞인 테스트에서는 그 둘을 단언하지 않았다(errors_n 만).
8. **마커 값 서식**(부동소수·리스트·None) — 미정 → 필드 **순서** + 모호하지 않은 값(strategy·ticker·buy_date·exit_date·
   v_exit_kind·tranches·killed)만 단언. cap 키 `strategy:ticker:buy_date` 는 `key in cap` 으로 확인.
9. **「오늘(KST)」 판정** — freezegun 으로 동결하고 `now_kst` 를 넘기지 않는다(`now_kst or datetime.now(KST)` 어느 쪽이든 통과).
10. **예산 0 이하 → None 을 누가 바꾸나** — leaf 에서 0 → None(A8) 은 단언, 콜렉터가 0 을 넘기든 None 을 넘기든 허용.
11. **add_stage/add_macd** — 오라클 = `kojiro_indicators.enrich(기본 KojiroIndicatorConfig)` 를 T 이하 전 봉에 돌린 d−1 봉 값.
    enrich 실패 시(None) 경로는 단언하지 않았다.
12. **동점 kind**(두 항이 같은 선) · **앵커 날 stop_after_add 이 앵커보다 낮을 때의 kind** · **params 일부 키만 있을 때** — 미정, 단언 없음.
13. **no_add_flags 반환형** — `list(...)` 로 감싸 비교(튜플·리스트 무관).
