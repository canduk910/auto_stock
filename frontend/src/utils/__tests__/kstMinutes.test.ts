/**
 * cycle278 Red — KST 분 단위 시각 판정 유틸 (명세 C41 · §7.2 F33~F36).
 *
 * Green 이 `frontend/src/utils/kst.ts` 에 추가할 두 함수:
 * ```ts
 * export function kstMinutesOfDay(now?: Date): number   // KST 기준 0~1439
 * export function isKrxMainSession(now?: Date): boolean  // 09:00 <= t < 15:30
 * ```
 * - `now` 는 **주입 seam** 이다. 시각 창 게이트를 현재시각으로만 판정하면 CI 가 특정 시간대에만
 *   붉어진다(`owns_board(now<09:05)` 선례 — 로컬 23:5x 초록 / CI 00:04 실패).
 * - `Date` 의 로컬타임 getter(`getHours()`/`getMinutes()`)를 쓰지 않는다. 컨테이너·브라우저 TZ 가
 *   무엇이든 같은 값을 내야 한다 — 그래서 이 파일은 **TZ 를 미국으로 고정한 뒤 동적 import** 한다
 *   (모듈 레벨 `Intl` 객체는 정적 import 시점에 생성되므로 정적 import 로는 이 계약을 못 잰다 —
 *   cycle256 F2).
 */
import { describe, it, expect, beforeAll } from 'vitest'

const ORIGINAL_TZ = process.env.TZ

beforeAll(() => {
  // KST 도 UTC 도 아닌 시간대. 여기서 통과하면 배포 환경 TZ 와 무관하다.
  process.env.TZ = 'America/New_York'
  return () => {
    process.env.TZ = ORIGINAL_TZ
  }
})

async function loadKst() {
  return await import('../kst')
}

/** KST 시각 문자열 → Date (오프셋 명시 — 로컬 파싱에 기대지 않는다). */
const kst = (hhmm: string) => new Date(`2026-09-11T${hhmm}:00+09:00`)

describe('cycle278 F33~F36 — kstMinutesOfDay / isKrxMainSession', () => {
  it('F33 kstMinutesOfDay 는 주입한 시각의 KST 분을 준다 (UTC·KST·미국 입력 3케이스)', async () => {
    const { kstMinutesOfDay } = await loadKst()

    // UTC 00:00 = KST 09:00
    expect(kstMinutesOfDay(new Date('2026-09-11T00:00:00Z'))).toBe(9 * 60)
    // KST 오프셋 표기 그대로
    expect(kstMinutesOfDay(kst('15:29'))).toBe(15 * 60 + 29)
    // 미국 동부 표기(EDT, UTC-4) 20:30 = KST 익일 09:30
    expect(kstMinutesOfDay(new Date('2026-09-10T20:30:00-04:00'))).toBe(9 * 60 + 30)
  })

  it('F34 isKrxMainSession 은 08:59 false / 09:00 true', async () => {
    const { isKrxMainSession } = await loadKst()

    expect(isKrxMainSession(kst('08:59'))).toBe(false)
    expect(isKrxMainSession(kst('09:00'))).toBe(true)
  })

  it('F35 isKrxMainSession 은 15:29 true / 15:30 false', async () => {
    const { isKrxMainSession } = await loadKst()

    expect(isKrxMainSession(kst('15:29'))).toBe(true)
    expect(isKrxMainSession(kst('15:30'))).toBe(false)
  })

  it('F36 TZ 환경변수와 무관하게 같은 결과이고 인자 생략도 동작한다', async () => {
    const { kstMinutesOfDay, isKrxMainSession } = await loadKst()

    expect(process.env.TZ, '이 파일은 미국 TZ 로 고정한 채 돈다').toBe('America/New_York')
    // 같은 순간을 세 가지 표기로 넣어도 같은 KST 분
    const instant = '2026-09-11T04:15:00Z'
    expect(kstMinutesOfDay(new Date(instant))).toBe(13 * 60 + 15)
    expect(kstMinutesOfDay(new Date('2026-09-11T13:15:00+09:00'))).toBe(13 * 60 + 15)
    expect(isKrxMainSession(new Date(instant))).toBe(true)

    // 인자 생략(현재 시각) — 값은 시각에 따라 다르므로 범위만 본다.
    const nowMinutes = kstMinutesOfDay()
    expect(Number.isInteger(nowMinutes)).toBe(true)
    expect(nowMinutes).toBeGreaterThanOrEqual(0)
    expect(nowMinutes).toBeLessThanOrEqual(1439)
    expect(typeof isKrxMainSession()).toBe('boolean')
  })
})
