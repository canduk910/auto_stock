"""cycle374 (2026-09-27) — 체결통보 채널의 **접수 전문**(`CNTG_YN=1`)을 기록한다 (Red).

## 왜

2026-09-14 계획(워크리스트 「09-14 실측 ①」 따라오는 것 3)은 접수 전문의 필드를 남기는 것이었는데
구현되지 않았다. `src/realtime/handler.py::_handle_execution` 은 `CNTG_YN != "2"` 프레임을
`order_no`·`ticker` 두 칸만 실은 **DEBUG** 한 줄로 버린다 — DEBUG 는 `_DbLogHandler`(INFO 이상)에
닿지 않으므로 **거래소가 접수 뒤 거부한 주문이 운영 로그에 한 줄도 남지 않는다**(cycle373 실측:
437730 09-15 매수 PENDING 잔존의 정체). 2026-09-27 사용자 결정 = 「거래소 거부 기록하기로 했었어
… 안되어있다면 바로 해야해」, 8영역 `handler.py` 접촉 승인.

## 범위 = 기록만

| 프레임 | 기대 |
|---|---|
| `CNTG_YN=1` (주문·정정·취소·거부 접수) | INFO `[order_notice] ` 1줄 — 이름 붙은 칸만 |
| 그중 `RFUS_YN` 이 거부(`"1"` KIS 명세 · `"Y"` 호출자 지시 — 둘 다) | 위 INFO + WARNING `[order_rejected_notice] ` 1줄(같은 칸) |
| `CNTG_YN=2` (체결) | **HEAD 와 행위 동일** — 콜백 인자 동일, 새 기록 0 |

- 콜백(`_on_execution`)·상태 변경 없음. 접수 프레임은 지금처럼 체결 경로 **앞에서** return.
- 이름 붙은 칸 = `order_no=[2] orig_order_no=[3] side=[4]→BUY/SELL rctf=[5] kind=[6] cond=[7]
  ticker=[8] qty=[9] price=[10] hour=[11] rfus=[12] acpt=[14] ord_qty=[16]`(없으면 생략 또는 빈 값).
  값은 **원문 그대로**다 — 접수 전문에서 [9]/[10] 이 무엇을 싣는지(주문수량·주문가인지 0 인지)가
  아직 실측되지 않았다(워크리스트 「아직 못 잰 것」). 숫자로 바꾸면 그 증거가 사라진다.
- 🔴 개인정보 금지 — `[0] CUST_ID(HTS ID)` · `[1] 계좌번호` · `[17] 계좌명` 과 원문 payload 는
  어떤 레벨로도 싣지 않는다.
- 🔴 같은 사건에 `write_log` 를 따로 부르지 않는다 — 루트 `_DbLogHandler` 가 `src.*` 로거의 INFO
  이상을 이미 `system_logs` 로 나른다(cycle72 G-6 이중 INSERT 금지). 그래서 기록 로거는 `src.`
  아래여야 한다(아니면 DB 에 닿지 않는다).
- `_DbLogHandler` 는 `"[<logger>] <msg>"[:500]` 로 자른다 — 한 줄이 그 안에 들어가야 한다.
- 짧은·깨진 프레임은 예외를 던지지 않는다. 이 함수의 예외는 WS 수신 루프까지 올라간다.

## KIS 명세 (docs/kis/domestic-stock-realtime.md H0STCNI0 절 — 2026-09-11 스냅샷, 이 TR 은 09-14 변경 무관)

- `[12] RFUS_YN` 거부여부 = **`0` 승인 · `1` 거부** (호출자 지시는 `"Y"` — 라이브 값이 미실측이라
  둘 다 거부로 본다. `"0"`·`"N"`·빈 값은 거부 아님)
- `[13] CNTG_YN` = `1` 주문·정정·취소·거부 / `2` 체결
- `[14] ACPT_YN` = `1` 주문접수 · `2` 확인 · `3` 취소(FOK/IOC)
- `[5] RCTF_CLS` = `0` 정상 · `1` 정정 · `2` 취소

## 로그 캡처

`caplog` 대신 루트 + 모듈 로거에 직접 붙이는 캡처 핸들러를 쓴다(레벨 DEBUG 고정, `disabled`
해제 후 복원). 개수 단언은 **레벨 + prefix** 로 한정한다(CI 루트 로거 DEBUG 교훈, cycle252 T2).
"""

from __future__ import annotations

import ast
import inspect
import logging
import re
import textwrap

import pytest

from src.realtime import handler as handler_mod

pytestmark = pytest.mark.unit


# ── 개인정보 표식 — 다른 어떤 칸의 부분 문자열도 아니게 고른다 ──────────────────
_HTS_ID = "HTSPIIUSR"
_TARGET_ACCOUNT = "73123456"          # settings.kis_account_no (8자리)
_ACCOUNT_FULL = "7312345601"         # [1] 계좌번호(8) + 상품코드(2)
_ACNT_NAME = "홍길동PII"              # [17] 계좌명
_OTHER_ACCOUNT = "9988776601"

_INFO_PREFIX = "[order_notice] "
_WARN_PREFIX = "[order_rejected_notice] "

_ALLOWED_KEYS = frozenset({
    "order_no", "orig_order_no", "side", "rctf", "kind", "cond", "ticker",
    "qty", "price", "hour", "rfus", "acpt", "ord_qty",
})


def _frame(**overrides) -> list[str]:
    """KIS `ccnl_notice` 26 컬럼 프레임(접수 전문 기본값).

    기본값은 09-14 GTP 실측(073240 금호타이어 1주 5,160원 NXT 매수)을 본뜬다.
    """
    f = [""] * 26
    f[0] = _HTS_ID
    f[1] = _ACCOUNT_FULL
    f[2] = "0000149100"   # ODER_NO
    f[3] = ""             # OODER_NO
    f[4] = "02"           # SELN_BYOV_CLS 02 매수
    f[5] = "0"            # RCTF_CLS 정상
    f[6] = "00"           # ODER_KIND 지정가
    f[7] = "0"            # ODER_COND 없음
    f[8] = "073240"       # 종목코드
    f[9] = "0000000001"   # CNTG_QTY (접수 전문에서의 의미는 미실측 — 원문 기록)
    f[10] = "000005160"   # CNTG_UNPR
    f[11] = "082934"      # 시각
    f[12] = "0"           # RFUS_YN 0 승인
    f[13] = "1"           # CNTG_YN 1 접수
    f[14] = "1"           # ACPT_YN 1 주문접수
    f[15] = "06010"       # BRNC_NO
    f[16] = "000000001"   # ODER_QTY
    f[17] = _ACNT_NAME
    f[19] = "2"           # ORD_EXG_GB NXT
    f[24] = "금호타이어"
    f[25] = "000005160"   # ODER_PRC
    for k, v in overrides.items():
        f[int(k.lstrip("f"))] = v
    return f


def _payload(fields: list[str]) -> str:
    return "^".join(fields)


# ── 로그 캡처 ────────────────────────────────────────────────────────────────


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []
        self._seen: set[int] = set()

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        # 루트와 모듈 로거 양쪽에 붙이므로 같은 레코드가 두 번 온다 — id 로 거른다.
        if id(record) in self._seen:
            return
        self._seen.add(id(record))
        self.records.append(record)

    # 편의
    def with_prefix(self, prefix: str, level: int) -> list[logging.LogRecord]:
        return [
            r for r in self.records
            if r.levelno == level and r.getMessage().startswith(prefix)
        ]

    def at_or_above(self, level: int) -> list[logging.LogRecord]:
        return [r for r in self.records if r.levelno >= level]


@pytest.fixture
def cap():
    h = _Capture()
    root = logging.getLogger()
    mod_logger = logging.getLogger(handler_mod.__name__)
    saved = (root.level, mod_logger.level, mod_logger.disabled)
    root.addHandler(h)
    mod_logger.addHandler(h)
    root.setLevel(logging.DEBUG)
    mod_logger.setLevel(logging.DEBUG)
    # 앞선 테스트의 dictConfig(disable_existing_loggers) 가 모듈 로거를 꺼 두었을 수 있다.
    mod_logger.disabled = False
    try:
        yield h
    finally:
        root.removeHandler(h)
        mod_logger.removeHandler(h)
        root.setLevel(saved[0])
        mod_logger.setLevel(saved[1])
        mod_logger.disabled = saved[2]


@pytest.fixture
def cb(monkeypatch):
    """`_on_execution` 스파이 + 계좌 필터 활성(대상 계좌 = `_TARGET_ACCOUNT`)."""
    calls: list[tuple[tuple, dict]] = []

    async def _spy(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(handler_mod, "_on_execution", _spy)
    from src import config
    monkeypatch.setattr(config.settings, "kis_account_no", _TARGET_ACCOUNT, raising=False)
    return calls


@pytest.fixture
def write_log_spy(monkeypatch):
    """같은 사건의 두 번째 기록(`write_log`) 금지 — cycle72 G-6."""
    calls: list[tuple] = []

    async def _spy(*args, **kwargs):
        calls.append(args)

    import src.db.system_logs as sl
    monkeypatch.setattr(sl, "write_log", _spy)
    # handler 가 모듈 최상단에서 이름을 끌어왔다면 그 이름도 막는다.
    monkeypatch.setattr(handler_mod, "write_log", _spy, raising=False)
    return calls


_KV_RE = re.compile(r"(\w+)=(\S*)")


def _kv(message: str) -> dict[str, str]:
    """`key=value` 토큰 파싱. 값 앞뒤 따옴표는 표기 차이로 보고 벗긴다."""
    body = message.split("] ", 1)[1] if "] " in message else message
    return {k: v.strip("'\"") for k, v in _KV_RE.findall(body)}


def _expected(fields: list[str], *, side: str) -> dict[str, str]:
    d = {
        "order_no": fields[2], "orig_order_no": fields[3], "side": side,
        "rctf": fields[5], "kind": fields[6], "cond": fields[7],
        "ticker": fields[8], "qty": fields[9], "price": fields[10],
        "hour": fields[11], "rfus": fields[12], "acpt": fields[14],
    }
    if len(fields) > 16:
        d["ord_qty"] = fields[16]
    return d


def _normalize(d: dict[str, str]) -> dict[str, str]:
    """[16] 이 없을 때 `ord_qty` 는 생략해도, 빈 값으로 두어도 된다."""
    out = dict(d)
    if out.get("ord_qty", None) == "":
        out.pop("ord_qty")
    return out


def _assert_no_pii(records: list[logging.LogRecord]) -> None:
    for r in records:
        msg = r.getMessage()
        blob = msg + " " + repr(r.args) + " " + (r.exc_text or "")
        for secret, label in (
            (_HTS_ID, "[0] CUST_ID(HTS ID)"),
            (_TARGET_ACCOUNT, "[1] 계좌번호(앞 8자리)"),
            (_ACNT_NAME, "[17] 계좌명"),
        ):
            assert secret not in blob, (
                f"{label} 가 로그에 실렸다 — 개인정보. level={r.levelname} msg={msg!r}"
            )
        assert "^" not in msg, f"원문 payload 가 로그에 실렸다: {msg!r}"


# ── A. 접수 전문(승인) ─────────────────────────────────────────────────────────


class TestAckRecorded:
    @pytest.mark.asyncio
    async def test_ack_when_cntg_yn_1_then_exactly_one_info_order_notice(self, cap, cb, write_log_spy):
        await handler_mod._handle_execution(_payload(_frame()))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1, (
            f"접수 전문 1건 = [order_notice] INFO 정확히 1줄이어야 한다 — 실제 {len(infos)}. "
            f"HEAD 는 DEBUG 로 버린다(DB 미도달)."
        )

    @pytest.mark.asyncio
    async def test_ack_when_recorded_then_named_fields_match_raw_values(self, cap, cb, write_log_spy):
        fields = _frame()
        await handler_mod._handle_execution(_payload(fields))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1
        got = _normalize(_kv(infos[0].getMessage()))
        assert got == _normalize(_expected(fields, side="BUY")), (
            "이름 붙은 칸이 원문 값과 다르다(숫자 변환·누락·칸 밀림)"
        )

    @pytest.mark.asyncio
    async def test_ack_when_every_field_distinct_then_no_index_swap(self, cap, cb, write_log_spy):
        """칸마다 다른 합성 값 — 어느 두 칸이 뒤바뀌거나 한 칸 밀려도 잡힌다."""
        # 숫자 모양으로 둔다 — 깨진 값 내성은 `test_malformed_values_*` 가 따로 본다.
        fields = _frame(
            f2="0000000202", f3="0000000303", f5="5", f6="66", f7="7", f8="088888",
            f9="99", f10="1010", f11="111111", f12="12", f14="14", f15="15151",
            f16="1616", f18="1818", f19="9",
        )
        await handler_mod._handle_execution(_payload(fields))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1
        got = _normalize(_kv(infos[0].getMessage()))
        assert got == {
            "order_no": "0000000202", "orig_order_no": "0000000303", "side": "BUY",
            "rctf": "5", "kind": "66", "cond": "7", "ticker": "088888",
            "qty": "99", "price": "1010", "hour": "111111", "rfus": "12",
            "acpt": "14", "ord_qty": "1616",
        }

    @pytest.mark.asyncio
    async def test_ack_when_recorded_then_key_set_is_exactly_the_named_fields(self, cap, cb, write_log_spy):
        await handler_mod._handle_execution(_payload(_frame()))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1
        keys = set(_kv(infos[0].getMessage()))
        assert keys == _ALLOWED_KEYS, (
            f"키 집합이 계약과 다르다 — 초과 {sorted(keys - _ALLOWED_KEYS)} "
            f"누락 {sorted(_ALLOWED_KEYS - keys)}"
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("raw_side, mapped", [("02", "BUY"), ("01", "SELL")])
    async def test_ack_when_side_code_then_mapped_like_fill_path(self, cap, cb, write_log_spy, raw_side, mapped):
        await handler_mod._handle_execution(_payload(_frame(f4=raw_side)))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1
        assert _kv(infos[0].getMessage()).get("side") == mapped

    @pytest.mark.asyncio
    async def test_ack_when_approved_then_no_warning_and_no_callback(self, cap, cb, write_log_spy):
        await handler_mod._handle_execution(_payload(_frame()))
        assert cap.at_or_above(logging.WARNING) == [], (
            "승인된 접수 전문에 WARNING 이상이 나왔다: "
            f"{[r.getMessage() for r in cap.at_or_above(logging.WARNING)]}"
        )
        assert cb == [], "접수 전문은 콜백을 부르지 않는다(체결 경로 앞에서 return)"

    @pytest.mark.asyncio
    async def test_ack_when_recorded_then_logger_is_under_src_so_db_handler_persists(self, cap, cb, write_log_spy):
        """`_DbLogHandler.emit` 은 `record.name.startswith("src.")` 가 아니면 버린다."""
        await handler_mod._handle_execution(_payload(_frame()))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1
        assert infos[0].name.startswith("src."), (
            f"기록 로거 {infos[0].name!r} 는 `src.` 밖 — system_logs 에 닿지 않는다"
        )

    @pytest.mark.asyncio
    async def test_ack_when_max_length_values_then_fits_db_500_char_cut(self, cap, cb, write_log_spy):
        """`_DbLogHandler` = `f"[{name}] {msg}"[:500]` — 잘리면 뒤 칸(acpt·ord_qty)이 사라진다."""
        fields = _frame(
            f2="9" * 10, f3="8" * 10, f5="1", f6="24", f7="2", f8="Q" * 9,
            f9="7" * 10, f10="6" * 9, f11="5" * 6, f12="1", f14="3", f16="4" * 9,
        )
        await handler_mod._handle_execution(_payload(fields))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        warns = cap.with_prefix(_WARN_PREFIX, logging.WARNING)
        assert len(infos) == 1 and len(warns) == 1
        for r in infos + warns:
            persisted = f"[{r.name}] {r.getMessage()}"
            assert len(persisted) <= 500, f"system_logs 500자 컷에 잘린다: {len(persisted)}자"


# ── B. 거부 ─────────────────────────────────────────────────────────────────


class TestRejectRecorded:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("rfus", ["1", "Y"], ids=["kis_spec_1", "caller_Y"])
    async def test_reject_when_rfus_marks_refusal_then_info_plus_one_warning(self, cap, cb, write_log_spy, rfus):
        fields = _frame(f12=rfus)
        await handler_mod._handle_execution(_payload(fields))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        warns = cap.with_prefix(_WARN_PREFIX, logging.WARNING)
        assert len(infos) == 1, f"거부도 [order_notice] INFO 1줄은 그대로 — 실제 {len(infos)}"
        assert len(warns) == 1, (
            f"RFUS_YN={rfus!r} 거부 = [order_rejected_notice] WARNING 정확히 1줄 — 실제 {len(warns)}"
        )
        assert cb == [], "거부 접수 전문도 콜백을 부르지 않는다"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("rfus", ["1", "Y"])
    async def test_reject_when_warned_then_same_named_fields_as_info(self, cap, cb, write_log_spy, rfus):
        fields = _frame(f12=rfus, f4="01", f3="0000148800", f14="1")
        await handler_mod._handle_execution(_payload(fields))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        warns = cap.with_prefix(_WARN_PREFIX, logging.WARNING)
        assert len(infos) == 1 and len(warns) == 1
        expected = _normalize(_expected(fields, side="SELL"))
        assert _normalize(_kv(warns[0].getMessage())) == expected
        assert _normalize(_kv(infos[0].getMessage())) == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("rfus", ["0", "N", ""], ids=["spec_0", "N", "empty"])
    async def test_reject_when_rfus_not_refusal_then_no_warning(self, cap, cb, write_log_spy, rfus):
        await handler_mod._handle_execution(_payload(_frame(f12=rfus)))
        assert cap.with_prefix(_WARN_PREFIX, logging.WARNING) == []
        assert cap.at_or_above(logging.WARNING) == []
        assert len(cap.with_prefix(_INFO_PREFIX, logging.INFO)) == 1

    @pytest.mark.asyncio
    async def test_reject_when_recorded_then_no_second_write_log(self, cap, cb, write_log_spy):
        await handler_mod._handle_execution(_payload(_frame(f12="1")))
        assert len(cap.with_prefix(_WARN_PREFIX, logging.WARNING)) == 1
        assert write_log_spy == [], (
            "같은 사건에 write_log 를 또 불렀다 — _DbLogHandler 가 이미 적재한다(cycle72 G-6 이중 INSERT)"
        )

    def test_reject_static_when_handle_execution_then_no_write_log_call(self):
        """런타임 스파이가 못 보는 경로(지연 import 별칭 등)까지 — 함수 본문에 write_log 호출 0."""
        src = textwrap.dedent(inspect.getsource(handler_mod._handle_execution))
        tree = ast.parse(src)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    names.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    names.add(fn.attr)
        assert "write_log" not in names


# ── C. 정정·취소·확인 모양 ───────────────────────────────────────────────────


class TestCancelShapedRecorded:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "rctf, acpt",
        [("2", "1"), ("0", "3"), ("1", "2")],
        ids=["rctf_2_cancel", "acpt_3_fok_ioc_cancel", "rctf_1_amend_acpt_2_confirm"],
    )
    async def test_cancel_shaped_when_cntg_yn_1_then_recorded_without_callback(
        self, cap, cb, write_log_spy, rctf, acpt,
    ):
        fields = _frame(f2="0000149200", f3="0000149100", f5=rctf, f14=acpt, f9="0000000000")
        await handler_mod._handle_execution(_payload(fields))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1
        got = _normalize(_kv(infos[0].getMessage()))
        assert got == _normalize(_expected(fields, side="BUY"))
        assert got["orig_order_no"] == "0000149100", "취소·정정은 원주문번호로만 원 주문에 이어진다"
        assert cb == [], "취소·확인 모양도 기록만 — 콜백·상태 변경 없음"
        assert cap.at_or_above(logging.WARNING) == []


# ── D. 개인정보 ─────────────────────────────────────────────────────────────


class TestNoPii:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "overrides",
        [{}, {"f12": "1"}, {"f12": "Y"}, {"f5": "2", "f14": "3"}],
        ids=["ack", "reject_1", "reject_Y", "cancel"],
    )
    async def test_pii_when_any_notice_then_never_in_any_record(self, cap, cb, write_log_spy, overrides):
        await handler_mod._handle_execution(_payload(_frame(**overrides)))
        assert cap.with_prefix(_INFO_PREFIX, logging.INFO), "기록 자체가 없으면 이 검사는 공허하다"
        _assert_no_pii(cap.records)  # DEBUG 포함 전 레벨


# ── E. 계좌 필터 · 짧은/깨진 프레임 ──────────────────────────────────────────


class TestGuards:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("rfus", ["0", "1"])
    async def test_other_account_when_cntg_yn_1_then_nothing_at_info(self, cap, cb, write_log_spy, rfus):
        """동일 HTS ID 에 묶인 다른 계좌의 접수 전문 — 계좌 필터가 기록보다 먼저다."""
        await handler_mod._handle_execution(_payload(_frame(f1=_OTHER_ACCOUNT, f12=rfus)))
        assert cap.at_or_above(logging.INFO) == [], (
            f"다른 계좌 프레임이 INFO 이상으로 기록됐다: {[r.getMessage() for r in cap.at_or_above(logging.INFO)]}"
        )
        assert cb == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("n", [0, 1, 5, 14])
    async def test_short_frame_when_len_lt_15_then_no_exception_nothing_logged(self, cap, cb, write_log_spy, n):
        fields = _frame()[:n]
        await handler_mod._handle_execution("^".join(fields))
        assert cap.at_or_above(logging.INFO) == []
        assert cb == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("n", [15, 16])
    async def test_frame_without_16_when_cntg_yn_1_then_ord_qty_absent_no_exception(self, cap, cb, write_log_spy, n):
        fields = _frame()[:n]
        await handler_mod._handle_execution(_payload(fields))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1
        got = _kv(infos[0].getMessage())
        assert got.get("ord_qty", "") == "", "[16] 이 없는 프레임에서 ord_qty 에 값이 생겼다"
        assert _normalize(got) == _normalize(_expected(fields, side="BUY"))

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "overrides",
        [{"f9": "N/A"}, {"f10": "  "}, {"f16": "abc"}],
        ids=["qty_non_numeric", "price_blank_padded", "ord_qty_non_numeric"],
    )
    async def test_malformed_values_when_cntg_yn_1_then_no_exception_and_raw_recorded(
        self, cap, cb, write_log_spy, overrides,
    ):
        """접수 전문의 [9]/[10] 의미는 미실측이다 — 숫자가 아니어도 WS 수신 루프로 예외가 새면 안 된다.

        HEAD 는 `int(fields[10])`·`int(fields[9])` 를 `CNTG_YN` 판정 **앞**에서 해 접수 전문에서도 던진다.
        """
        fields = _frame(**overrides)
        await handler_mod._handle_execution(_payload(fields))
        infos = cap.with_prefix(_INFO_PREFIX, logging.INFO)
        assert len(infos) == 1
        got = _kv(infos[0].getMessage())
        key, idx = {"f9": ("qty", 9), "f10": ("price", 10), "f16": ("ord_qty", 16)}[next(iter(overrides))]
        assert got.get(key, "") == fields[idx].strip() or got.get(key, "") == fields[idx]
        assert cb == []


# ── F. 체결 경로 불변 ───────────────────────────────────────────────────────


class TestFillPathUnchanged:
    @pytest.mark.asyncio
    async def test_fill_when_cntg_yn_2_then_callback_args_identical_to_head(self, cap, cb, write_log_spy):
        fields = _frame(
            f2="0000411400", f8="257720", f9="1", f10="51100", f11="091551",
            f13="2", f14="2", f16="2",
        )
        await handler_mod._handle_execution(_payload(fields))
        assert cb == [
            (("257720", "0000411400", "BUY", 51_100, 1), {"ordered_qty_payload": 2}),
        ], "체결 콜백 인자가 HEAD 와 다르다 — 체결 경로는 byte 동일해야 한다"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("rfus", ["0", "1"])
    async def test_fill_when_cntg_yn_2_then_no_new_records_at_info(self, cap, cb, write_log_spy, rfus):
        fields = _frame(f8="257720", f9="1", f10="51100", f12=rfus, f13="2", f14="2", f16="2")
        await handler_mod._handle_execution(_payload(fields))
        assert len(cb) == 1
        assert cap.at_or_above(logging.INFO) == [], (
            "체결 프레임에 INFO 이상 기록이 생겼다 — [order_notice] 는 접수 전문 전용: "
            f"{[r.getMessage() for r in cap.at_or_above(logging.INFO)]}"
        )

    @pytest.mark.asyncio
    async def test_fill_when_sell_partial_then_quantity_still_fields_9(self, cap, cb, write_log_spy):
        """cycle235 봉인 재확인 — 체결수량은 [9], [16] 은 주문수량 kwarg 로만."""
        fields = _frame(f4="01", f8="257720", f9="2", f10="51000", f13="2", f14="2", f16="3")
        await handler_mod._handle_execution(_payload(fields))
        assert cb == [(("257720", "0000149100", "SELL", 51_000, 2), {"ordered_qty_payload": 3})]
