"""cycle412 Red — 범위 가드: 거래일지 1a 는 **8영역·`scheduler.py`·주문/청산 판단 경로 0줄**이다(내용 sha).

정본 = 설계 관찰자안 4절 「8영역·scheduler·주문 경로 접촉」 · 사용자 결정 E1a(워커는 src 밖) · E1b(`balance.py` 만).

| # | 계약 |
|---|---|
| S1 | 8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py`·`src/api/order.py`·`src/realtime/**`·`src/auth/**`) + `scheduler.py` 내용 sha = 기준 `272c76c1` 그대로 |
| S2 | 주문·청산 판단 경로도 그대로 — `boot_manager.py`(R7 철회) · `llm_buy_gate.py`(R1 철회) · `routes/trading.py`(R6 철회) · `strategy_base.py` · 전략 파일 전부(`check_*`) · leaf `position_exit_lines.py` · 리포터 키 경계 `middleware/api_auth.py` |
| S3 | `src/**/*.py` 파일 집합이 그대로다(새 파일 0 — 워커는 `journal_worker/`) |
| S4 | `src/` 안에서 바뀌는 `.py` 는 `src/routes/balance.py` 하나뿐이어야 한다 — 그 파일은 이 dict 에 없다 |
| S5 | 기존 마이그레이션 001~046 무수정(이름·내용) — 047 은 새 파일로 더한다 |

왜 내용 sha 인가 — `ast.dump` 는 3.12(CI)/3.13(로컬) 출력이 달라 핀하지 않는다(cycle256·259).
스캔은 `Path.rglob("*.py")` — `git ls-files` 는 미추적 새 파일을 못 본다(cycle259 S4b).

⚠️ **사이클 한정 — cycle412 병합 후 삭제.** 이 dict 는 기준 `272c76c1`(feat/cost-overlay) blob 이라
cycle412 의 무접촉 증거로만 유효하다. 병합 전에 main 이 이 파일들을 정당하게 바꾸면(리베이스) 이 가드를
지운다(고아 가드 방지). dict 이름을 `*_CONTENT_SHA` 로 짓지 않는다(`test_cycle223g3` `_PIN_GUARD_FILES` 관례).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_BASE_SHA = {
    "src/engine/risk.py": "a2187b8270446379988d24dfbe39b902d6ab37b112d4b6ce7330ee171434e222",
    "src/engine/order_engine.py": "08c479841352fb579f767c109de3e8f901d1c27bdce705b39b5ba6556fc0b3e1",
    "src/engine/session.py": "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    # 🔁 cycle417(2026-10-09) 재핀 — cycle417 사용자 승인 10-09 — 일봉 증분 적재 구멍(증분 분기 창 확대 + 구멍 판정 1회 호출). 나머지 7영역 diff 0.
    "src/engine/scanner.py": "b570762dfd92df49471dab261d44ecd364d376300ffe9e2f5b7ac19cceb9efcc",
    "src/engine/strategy_registry.py": "3b6366c3cdb6e83907428435b95611880f1b8223e572c361a1cad2d00b13a067",
    "src/api/order.py": "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    "src/engine/scheduler.py": "f53d41a11fe162f80e113c6ff48cf6d235581769be7979499c5782ff11d49646",
    "src/realtime/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py": "e1a484e9ac82d43f0fa85cba693ea5a206ecfbae1076dfee0f4e6bf6d4f2a2d4",
    "src/realtime/websocket.py": "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py": "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    "src/auth/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py": "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    "src/auth/token.py": "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
}

_ORDER_PATH_SHA = {
    "src/engine/boot_manager.py": "b595f0c1dadc924baf9c50c2775290d9326624b0ade697fb478df31fa8c28cf4",
    "src/engine/llm_buy_gate.py": "933f58d3ab8d461e79878bd604951f8daa6c47634d24b7fbbcada63e9ded1bc5",
    "src/routes/trading.py": "c3274c12323760a3939e6189ce5fd333118f6d188c35905238885ad04312b1f5",
    "src/engine/position_exit_lines.py": "a760e3016f19e833280410e12cfa0357828fc468735985b647b31005e79700cf",
    "src/engine/strategy_base.py": "f4c2c5619fb3b2f70fa0b4faab0fd38d55c83d0b9370c986c97de4f564430822",
    "src/middleware/api_auth.py": "17b5096a9de30def56ee6502148d9c746695e6763890046bc2190eccded0cc32",
    "src/engine/strategies/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/engine/strategies/bull_flag_breakout.py": "879d85e779f9594ffbd9da93ce3ec41986f02abc78cc751cb22d022c20b0f298",
    "src/engine/strategies/donchian_swing.py": "c8c7172e8e33fa164e2d11c30641562e8ab2d6474e7a84f241320bf2fbab58f3",
    "src/engine/strategies/etf_trend.py": "31776865ec1c206df7f61020966fa2e21be17e39939f1c9e443557834f54c318",
    "src/engine/strategies/kojiro.py": "1d04d3d6dc0c72ff6c7e7d930be9da63f2408fb709e889906a133a9c5480fc74",
    "src/engine/strategies/long_tail_volatility.py": "44f7f103b3c714522b09da7de5a4de2ec0423ffc2a3032f43540c4c70943778d",
    "src/engine/strategies/momentum.py": "686171e29ac365e8ea66f7659f2e02962f58bbac9d9ab9545095c7b3544bb403",
    "src/engine/strategies/vcp_breakout.py": "9a53b5b6d9a5dcf96966b168291640df6b258daf059f03e4cdd5b12324589706",
    "src/engine/strategies/volatility_breakout.py": "c07e7298743496129601e79598b799472242d2f02b60eb2f92217b6bed1ee1b4",
}

#: 기준 `272c76c1` 의 `src/**/*.py` 경로 목록(정렬, 개행 연결) sha 와 개수.
#: 🔴 이 가드는 cycle412 병합 후에도 지워지지 않고 남아 있었다(고아 가드 — 파일 docstring의
#: "병합 후 삭제" 가 지켜지지 않은 사례). cycle416(매크로 시장 등락 통계)이 신규 2파일
#: (`engine/market_breadth.py`·`routes/market_breadth.py`) 로 182 → **184** 가 된 것을 보고
#: 값만 옮긴다 — 삭제는 샌드박스의 비가역 파일 삭제 차단에 걸려 이 사이클에서 못 했다.
#: 이 파일은 더 이상 "cycle412 무접촉 증거" 가 아니라 평범한 src 파일 집합 핀이 됐으니,
#: 다음에 손대는 사람이 지우거나 cycle287/290/291 가드와 합치는 것이 맞다.
_SRC_PY_COUNT = 184
_SRC_PY_SET_SHA = "7972545ddf052270027462e8deaf4af0c904f1dd4bea151cf690e796452cdfd1"


#: 기준 `272c76c1` 의 `supabase/migrations/*.sql` 46개 — (이름, 내용 sha) 연쇄 digest.
_MIGRATIONS_BASE_COUNT = 46
_MIGRATIONS_BASE_DIGEST = "bffe4cb5a4ef27852572bf7f76f361366d39f8c828f15e1a3d1b546c75c1c05a"


def _sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


def _src_py() -> list[str]:
    return sorted(
        p.relative_to(_ROOT).as_posix() for p in (_ROOT / "src").rglob("*.py") if "__pycache__" not in p.parts
    )


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_s1_eight_areas_and_scheduler_unchanged(rel):
    assert _sha(rel) == _BASE_SHA[rel], f"{rel} 가 바뀌었다 — cycle412 는 8영역·scheduler.py 0줄(E1a)"


@pytest.mark.parametrize("rel", sorted(_ORDER_PATH_SHA))
def test_s2_order_and_exit_decision_path_unchanged(rel):
    assert _sha(rel) == _ORDER_PATH_SHA[rel], f"{rel} 가 바뀌었다 — 주문·청산 판단 경로 0줄(관찰자 방식)"


def test_s3_no_new_or_removed_src_py():
    files = _src_py()
    assert len(files) == _SRC_PY_COUNT, f"src/*.py {len(files)}개 — 워커 코드는 src 밖 journal_worker/ 에 둔다"
    assert hashlib.sha256("\n".join(files).encode()).hexdigest() == _SRC_PY_SET_SHA


def test_s4_balance_route_is_the_only_unpinned_engine_neighbor():
    assert "src/routes/balance.py" not in _BASE_SHA and "src/routes/balance.py" not in _ORDER_PATH_SHA
    for d in ("src/realtime", "src/auth", "src/engine/strategies"):
        found = {p.relative_to(_ROOT).as_posix() for p in (_ROOT / d).rglob("*.py") if "__pycache__" not in p.parts}
        pinned = {k for k in {**_BASE_SHA, **_ORDER_PATH_SHA} if k.startswith(d + "/")}
        assert found == pinned, d


def test_s5_existing_migrations_unchanged():
    files = sorted((_ROOT / "supabase" / "migrations").glob("*.sql"))
    base = [f for f in files if int(f.name[:3]) <= _MIGRATIONS_BASE_COUNT]
    assert len(base) == _MIGRATIONS_BASE_COUNT
    h = hashlib.sha256()
    for f in base:
        h.update(f.name.encode() + b"\0" + hashlib.sha256(f.read_bytes()).hexdigest().encode() + b"\n")
    assert h.hexdigest() == _MIGRATIONS_BASE_DIGEST, "기존 마이그레이션을 고치지 않는다 — 047 은 가산형 새 파일"
