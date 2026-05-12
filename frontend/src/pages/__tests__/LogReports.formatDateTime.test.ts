/**
 * L3 — LogReports `formatDateTime` KST 강제 (2026-05-12).
 *
 * 배경: `LogReports.tsx` 의 `formatDateTime` 은 `toLocaleString('ko-KR', { hour12: false })`
 * 만 사용해 브라우저 로컬 timezone 의존. 도커 빌드(UTC) / 다른 timezone 환경에서
 * 같은 created_at 가 다른 시각으로 표시됨.
 *
 * 요구 행위:
 *  J. `formatDateTime(utc_iso)` 는 `timeZone: 'Asia/Seoul'` 명시 변환을 보장한다.
 *     UTC `2026-05-11T23:05:47Z` → KST 변환 결과에 `2026` + `08`(시각) 포함.
 *
 * 테스트는 `process.env.TZ='UTC'` 환경에서 KST 명시 없이는 `23` 시가 표시되어
 * 단언이 깨지도록 구성 (Red).
 */

import { describe, expect, it, beforeAll, afterAll } from "vitest";

const ORIG_TZ = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "UTC";
});
afterAll(() => {
  process.env.TZ = ORIG_TZ;
});

describe("LogReports.formatDateTime — KST 강제 (L3)", () => {
  it("UTC ISO 입력을 KST(Asia/Seoul) 로 환산한다", async () => {
    // 동적 import — `process.env.TZ` 가 모듈 로드 *전* 에 변경되어
    // jsdom 환경에서 `Intl.DateTimeFormat` 의 default timeZone 에 영향.
    const mod = await import("../LogReports");
    const fn = (mod as unknown as { formatDateTime?: (s: string | null | undefined) => string })
      .formatDateTime;
    expect(typeof fn).toBe("function");

    // 2026-05-11 23:05:47 UTC = 2026-05-12 08:05:47 KST
    const out = fn!("2026-05-11T23:05:47Z");
    // KST 변환 보장 — jsdom 환경의 ko-KR 포맷이 `8시 5분 47초` 형태로 떨어질 수도
    // 있으므로 포맷 무관 KST 시간 값을 검증:
    //   - 시각 부분이 `08:05:47` 또는 `8시 5분 47초` 또는 `8:05:47`
    //   - 일자가 KST 12일
    //   - 연도 2026
    expect(out).toMatch(/2026/);
    expect(out).toMatch(/12/); // KST 일자
    // UTC 23시가 그대로 표시되면 결함. KST 8시(또는 08시)가 보여야 함.
    // 음수 lookahead 로 23시 패턴 차단 + 8시 패턴 확인.
    expect(out).not.toMatch(/23[:시]/);
    expect(out).toMatch(/8[:시 ]/);
    expect(out).toMatch(/47/); // 초 단위 보존
  });

  it("null/undefined/빈 문자열은 `-` 반환", async () => {
    const mod = await import("../LogReports");
    const fn = (mod as unknown as { formatDateTime?: (s: string | null | undefined) => string })
      .formatDateTime;
    expect(fn!(null)).toBe("-");
    expect(fn!(undefined)).toBe("-");
    expect(fn!("")).toBe("-");
  });
});
