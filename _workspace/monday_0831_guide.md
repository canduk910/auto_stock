# 월요일(2026-08-31) 실행 가이드 — 257720 청산 + D+1 관찰

> 작성 2026-08-29(토). 조회는 read-only(`ssh → docker exec` 패턴). DB/설정 변경·커밋은 사용자 승인 후.
> ⚠️ 2026-09-02 정정: EC2 백엔드 포트는 **8000**(docker `0.0.0.0:8000->8000`), Nginx 80 경유도 가능. 종전 `8002` 는 개발 compose 포트라 EC2 에선 닫혀 있다(09-02 실측 `http=000`).
> ⚠️ 구파일 `monday_activation_guide.md` 는 08-10 대상 구버전 — 이 파일이 8/31 정본.

---

## A. 🔴 257720(실리콘투) — ⚠️ cycle236 배포(08-29 저녁)로 **자동 청산 성공 예상, 수동 개입은 폴백**

> **갱신(08-29 저녁)**: 아래 "자동 재실패 확정" 서술은 cycle236 배포 **전** 기준이다.
> cycle236(`a14bc98`, EC2 반영 완료)의 `execute_sell` #1.5 가 APBK0400 을 잡아
> **held(실보유 2주)로 자기 치유 보정 후 재시도**하므로, 월요일 자동 경로가 성공한다:
> ① 08:00~09:00 **익일 청산**(`_execute_next_day_clear` — VB 포함 안전망, `scheduler.py:1323`.
>   NXT 보류 시 09:00 `_drain` KRX 시장가) → 3주 시도 → APBK0400 → `[sell_qty_reconciled]`
>   held=2 보정 → **2주 매도 성공** ② 실패해도 장중 손절·15:20 강제청산이 같은 자기 치유를 탄다.
> **월요일 실제 할 일 = 09:05 경 확인만**: `[sell_qty_reconciled]` + 257720 SELL COMPLETED 2주
> + positions 정리. **그때도 잔존해 있을 때만** 아래 2번 manual-sell 폴백 실행(HTS 수기 불요 —
> 프로젝트 API 한 줄).

### 사실 (08-29 토 실측 — cycle232 자문 §5 가설 반증됨)

- 08-28 15:20 강제청산은 **정상 발화**했다(`변동성 돌파 15:20 강제 청산 대상: ['035420','257720']`). "무기록 포기"(cycle229 결함 희생자) 가설은 **기각**.
- 실패 원인 = **APBK0400 "주문 가능한 수량을 초과"** ×3회 → CRITICAL 최종 실패. `ORD_QTY=3` 으로 쐈는데 **실보유 2주**.
- 근본 = **부분 체결 수량 오염**: 08-28 09:15 BUY `0000411400` 이 `PARTIAL 2주` 체결인데 `positions.quantity=3`(주문수량)으로 잔존(updated_at 매수 시점 그대로 — sync 도 미정정).
- **월요일 15:20 자동 재청산도 재실패 확정** — `check_force_clear` 가 `pos.quantity=3` 으로 쏘면 또 APBK0400. 자동 대기 금지.
- APBK0400 은 `is_insufficient_quantity`(APBK1234 + "부족" 키워드) 미매칭이라 3회 재시도·positions 정리 경로가 안 탔다 → 신규 결함 N2.

### 절차

> ⚠️ **cycle243 이후 인증 필수 — 포트마다 방식이 다르다.**
> * EC2 내부 `localhost:8000` **직결**(아래 명령들) = `-H "X-API-Key: …"`. nginx 를 거치지
>   않으므로 Basic Auth 는 무의미하고, 헤더가 없으면 **401** 이라 비상 매도가 막힌다.
> * 외부 `http://3.38.228.74/…`(:80, nginx 경유) = `-u <USER>:<PASS>`. X-API-Key 는 nginx 가
>   주입한다.
>
> 키를 argv·셸 히스토리에 남기지 않으려면 EC2 에서 이렇게 읽는다(값 출력 없음):
> ```
> KEY=$(grep '^API_AUTH_KEY=' ~/auto_stock/.env | cut -d= -f2-)
> CFG=$(mktemp); printf 'header = "X-API-Key: %s"\n' "$KEY" > "$CFG"
> # …사용 후: rm -f "$CFG"
> ```

1. **08:50 사전 확인** — 실보유 수량(2주 예상):
```
ssh -i ~/.ssh/auto-stock-key.pem ubuntu@3.38.228.74 'KEY=$(grep "^API_AUTH_KEY=" ~/auto_stock/.env | cut -d= -f2-); CFG=$(mktemp); printf "header = \"X-API-Key: %s\"\n" "$KEY" > "$CFG"; curl -s --config "$CFG" localhost:8000/api/balance; rm -f "$CFG"' | python3 -c "import sys,json; d=json.load(sys.stdin); [print(h['ticker'],h.get('quantity'),h.get('sellable_quantity','')) for h in d['data']['holdings'] if h['ticker']=='257720']"
```
2. **09:00 직후 수동 매도 (실보유 수량으로!)** — KRX 시장가:
```
ssh -i ~/.ssh/auto-stock-key.pem ubuntu@3.38.228.74 'KEY=$(grep "^API_AUTH_KEY=" ~/auto_stock/.env | cut -d= -f2-); CFG=$(mktemp); printf "header = \"X-API-Key: %s\"\n" "$KEY" > "$CFG"; curl -s --config "$CFG" -X POST localhost:8000/api/trading/manual-sell -H "Content-Type: application/json" -d "{\"ticker\":\"257720\",\"quantity\":2}"; rm -f "$CFG"'
```
   (1의 실보유가 2가 아니면 그 값으로. 갭은 이미 실현된 뒤라 15:20 대기 무의미 — cycle232 D7 결정.)

   ⚠️ **401 이 오면 그것이 곧 비상 경로 차단이다 — 진단에서 멈추지 말고 복구까지 간다.**
   이 문서는 자동 청산이 실패했을 때 손으로 파는 절차이므로 "엔진은 살아 있으니 자동
   경로를 기다린다" 는 답이 될 수 없다(잠긴 것은 대시보드·API 이고 엔진은 계속 돌지만,
   **그 엔진의 자동 청산이 실패해서** 이 문서를 펴든 상황이다).

   1) **진단** — `grep -c '^API_AUTH_KEY=.\{32,\}$' ~/auto_stock/.env`
      - **1** → 키는 정상. 원인은 호출 쪽이다: :8000 직결에 `-u` 를 썼거나(무의미),
        :80 에 `-H "X-API-Key: …"` 만 썼거나(nginx Basic Auth 통과 실패), 헤더 오타.
      - **0** → 백엔드가 fail-closed 라 `/health` 를 뺀 **전 경로 401**. 아래 2)로.
   2) **복구** — 수십 초. `git revert` 후 재배포 왕복(CI+Deploy 5~10분)이 아니다:
```
ssh -i ~/.ssh/auto-stock-key.pem ubuntu@3.38.228.74        # 접속 후 아래 4줄
cd ~/auto_stock
grep -q '^API_AUTH_KEY=' .env || python3 -c "import secrets;print('API_AUTH_KEY='+secrets.token_urlsafe(32))" >> .env
docker compose -f docker-compose.prod.yml up -d
grep -c '^API_AUTH_KEY=.\{32,\}$' .env                     # → 1 (값은 출력하지 않는다)
```
   ⚠️ 이 복구는 `.env` 변경이라 compose 가 **backend·frontend 컨테이너를 재생성**한다
   = 장중이면 **1~5분 tick blind**(cycle232 D6 가 평소 장중 배포를 금지하는 바로 그 비용).
   비상 매도가 막힌 상황에서만 감수하는 교환이다. 재생성 후 `[boot]` 재개·포지션 복구를
   확인한 뒤 위 2번 manual-sell 을 다시 쏘고, 그동안 15:20 자동 청산은 **폴백으로만**
   취급한다(cycle236 자기 치유가 붙었어도 이 종목은 실패 전력이 있다).
3. **사후 확인**:
   - 체결: `trade_history` SELL COMPLETED + 체결통보 로그.
   - **positions 잔량**: 2주 매도 체결 시 `_handle_sell_fill` 이 3−2=1 잔량으로 남길 수 있다 → 15분 `_sync_positions_from_balance` / `[positions_reconciliation]` 이 정리하는지 확인. **미정리 시 DB 정정은 사용자 승인 후**(유령 1주가 다음 15:20 강제청산에서 또 APBK0400 을 만든다).
4. **신규 결함 등재 확인** (워크리스트 N1/N2 — cycle235 후보, 8영역 승인 필요):
   - N1: 부분 체결 BUY 의 positions 수량 오염(주문수량 등록·미보정) — `order_engine`(8영역).
   - N2: APBK0400 미분류 → insufficient_quantity 경로 미작동 — `balance.py` 분류기(비8영역) + KIS 정본으로 APBK0400 의미 범위 확인 선행.

---

## B. D+1 관찰 축 (부팅 07:55 ~ 장중 — 전부 read-only)

| 축 | 마커 | 판독 |
|---|---|---|
| cycle228 BFB/VCP 첫 체결 | `[bfb\|vcp_vol_gate_pass\|reject\|no_data]` `[*_latch_armed\|released]` `latch_age_sec` `[setup_structure_conflict]` | 예측 ≈0.5건/일. **진입 임계 재튜닝 금지(N=10)**. 첫 체결 시 청산 경로 첫 실가동 주시 |
| cycle229 15:30대 | `[callback_exception]` **0건이 정상**(의미 반전 — 08-28 전후 합산 금지), `[vb\|momentum_buy_cutoff]` | 08-28 15:30:16 APBK3013(096770 매수)이 시정 전 마지막 표본 |
| cycle230 VI/메인 | `[market_op_subscribe_summary]` main_over, `[market_op_subscribe_no_slot]` | main_over>0 지속 시 메인 헤드룸 항목 착수 근거 |
| cycle231 stage3 | `[kojiro_stage3_stale_skip]` age≥2 WARNING | 발화 = 억제가 실제로 일한 것 |
| cycle233 계좌 리스크 | `[account_risk_watch]` level·eff_pct·coverage·over_cap / `[oversized_fallback]`(000815·192820 예상) / `[account_gate_skip]` **0건이 정상**(다크런치) | eff vs proxy 괴리(effective_ratio)가 척도 병기의 목적. `GET /api/portfolio/risk` 로 즉시 조회 가능 |
| cycle234 tick blind | `[tick_blind_boot]` — 월 부팅은 **first_boot**(마커 최초) | 이후 재시작부터 downtime/market_blind 실측 시작 |

- **cycle235 배포 후 판독 주의 — 부분 체결의 "정상 시그니처"**: 부분→전량 체결이 완결될 때
  `[buy_fill_correction_unique_violation]` WARNING → `[trade_status_update_by_order_no] ... affected=1` →
  (30초 뒤) `부분 체결 잔여 취소 실패` ERROR 순서가 뜰 수 있다 — **이 3연타는 정상 완결 경로다**
  (1차 UPDATE 가 PENDING 한정이라 PARTIAL 에서 0건 → 보정 INSERT UNIQUE 충돌 → N1-b 강제
  UPDATE 수렴 + 이미 전량 체결된 주문의 잔여 취소 시도 무해 실패). 오귀인 금지. 이상 신호는
  `[fill_qty_overrun]`(수량 이상)과 `[fill_qty_zero]`(비양수 통보) 두 마커다.
- **P1-4**(silent_inactive 오판): 월요일 관찰 후 구현·배포(사용자 확정 — "관찰 후에 배포").
- 20:10 리포트에서 `tick_blind`·`portfolio_risk_snapshot.effective`·`over_cap_positions` 신규 키 확인.

## C. 로그 일괄 조회 원라이너

```
ssh -i ~/.ssh/auto-stock-key.pem ubuntu@3.38.228.74 'docker exec -i auto_stock-backend-1 python -c "
import asyncio
from src.db import pg
async def m():
    await pg.init_pool()
    for r in await pg.fetch(\"SELECT to_char(timestamp,'HH24:MI') t, left(message,150) m FROM system_logs WHERE timestamp::date=CURRENT_DATE AND (message LIKE '%account_risk%' OR message LIKE '%tick_blind%' OR message LIKE '%oversized_fallback%' OR message LIKE '%vol_gate%' OR message LIKE '%latch_%' OR message LIKE '%stage3_stale%' OR message LIKE '%market_op_subscribe_summary%' OR message LIKE '%257720%') ORDER BY timestamp LIMIT 120\"):
        print(r['t'], r['m'])
    await pg.close_pool()
asyncio.run(m())"'
```
