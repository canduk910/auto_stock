/**
 * 사이클 48 (2026-05-27) — `ScanMonitor.formatRunAt` KST 강제 회귀 가드.
 *
 * 배경: 깔때기 "마지막 {시각}" / "마지막 스캔" 표시가 `toLocaleString('ko-KR', { hour12: false })`
 * 만 사용해 timeZone 누락 → 브라우저/컨테이너 로컬 timezone 의존. 해외(스위스)·도커 UTC 환경에서
 * 07:48 KST boot 시각이 "0시 48분" 등으로 오표시되던 운영 결함 (사용자 5/26 스크린샷).
 * `DailyReportTab.formatDateTime` (L3) 와 동일 컨벤션 — `timeZone: 'Asia/Seoul'` 명시.
 *
 * 요구 행위:
 *  - `formatRunAt(iso)` 는 host TZ 와 무관하게 KST(Asia/Seoul) 로 환산한다.
 *    UTC `2026-05-25T22:48:21Z` → KST `2026. 5. 26. 7시 48분 21초`.
 *  - null/undefined/빈 문자열은 `-` 반환.
 */

import { describe, expect, it, beforeAll, afterAll } from 'vitest'

const ORIG_TZ = process.env.TZ
beforeAll(() => {
  process.env.TZ = 'UTC'
})
afterAll(() => {
  process.env.TZ = ORIG_TZ
})

describe('ScanMonitor.formatRunAt — KST 강제 (사이클 48)', () => {
  it('host TZ(UTC) 와 무관하게 KST 로 환산한다', async () => {
    // 동적 import — `process.env.TZ` 변경이 모듈 로드 전에 반영되어야 jsdom Intl 기본 timeZone 에 영향
    const mod = await import('../ScanMonitor')
    const fn = mod.formatRunAt
    expect(typeof fn).toBe('function')

    // 2026-05-25 22:48:21 UTC = 2026-05-26 07:48:21 KST (07:50 boot 시각 케이스)
    const out = fn('2026-05-25T22:48:21Z')
    expect(out).toMatch(/5\. 26\./) // KST 일자 (UTC 라면 5. 25.)
    expect(out).toMatch(/7시 48분 21초/) // KST 시각 (UTC 라면 22시 48분)
    expect(out).not.toMatch(/22시/) // 로컬(UTC) 시각으로 오표시 금지
    expect(out).not.toMatch(/25\./) // 로컬(UTC) 일자로 오표시 금지
  })

  it('null/undefined/빈 문자열은 `-` 반환', async () => {
    const mod = await import('../ScanMonitor')
    const fn = mod.formatRunAt
    expect(fn(null)).toBe('-')
    expect(fn(undefined)).toBe('-')
    expect(fn('')).toBe('-')
  })
})
