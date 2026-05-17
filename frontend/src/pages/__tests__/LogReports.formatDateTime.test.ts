/**
 * L3 — `formatDateTime` KST 강제 (2026-05-12).
 *
 * 사이클 6 (2026-05-17) — `LogReports.tsx` 는 `/logs?tab=daily-report` 로 통합되며
 * 본문은 `components/DailyReportTab.tsx` 로 추출되었다. `formatDateTime` 도 그 모듈에서 export.
 * 본 테스트는 회귀 가드 보존을 위해 import 경로만 갱신.
 *
 * 배경: `formatDateTime` 은 `toLocaleString('ko-KR', { hour12: false })`
 * 만 사용하면 브라우저 로컬 timezone 의존. 도커 빌드(UTC) / 다른 timezone 환경에서
 * 같은 created_at 가 다른 시각으로 표시됨.
 *
 * 요구 행위:
 *  J. `formatDateTime(utc_iso)` 는 `timeZone: 'Asia/Seoul'` 명시 변환을 보장한다.
 *     UTC `2026-05-11T23:05:47Z` → KST 변환 결과에 `2026` + `08`(시각) 포함.
 */

import { describe, expect, it, beforeAll, afterAll } from "vitest";

const ORIG_TZ = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "UTC";
});
afterAll(() => {
  process.env.TZ = ORIG_TZ;
});

describe("DailyReportTab.formatDateTime — KST 강제 (L3)", () => {
  it("UTC ISO 입력을 KST(Asia/Seoul) 로 환산한다", async () => {
    // 동적 import — `process.env.TZ` 가 모듈 로드 *전* 에 변경되어
    // jsdom 환경에서 `Intl.DateTimeFormat` 의 default timeZone 에 영향.
    const mod = await import("../../components/DailyReportTab");
    const fn = (mod as unknown as { formatDateTime?: (s: string | null | undefined) => string })
      .formatDateTime;
    expect(typeof fn).toBe("function");

    // 2026-05-11 23:05:47 UTC = 2026-05-12 08:05:47 KST
    const out = fn!("2026-05-11T23:05:47Z");
    expect(out).toMatch(/2026/);
    expect(out).toMatch(/12/); // KST 일자
    expect(out).not.toMatch(/23[:시]/);
    expect(out).toMatch(/8[:시 ]/);
    expect(out).toMatch(/47/); // 초 단위 보존
  });

  it("null/undefined/빈 문자열은 `-` 반환", async () => {
    const mod = await import("../../components/DailyReportTab");
    const fn = (mod as unknown as { formatDateTime?: (s: string | null | undefined) => string })
      .formatDateTime;
    expect(fn!(null)).toBe("-");
    expect(fn!(undefined)).toBe("-");
    expect(fn!("")).toBe("-");
  });
});
