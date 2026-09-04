/**
 * KST(Asia/Seoul) 포맷 유틸 단일화 (cycle256, 리팩토링 카드 #9 — 08-09 카드 C2 재발의).
 *
 * `Intl.DateTimeFormat(…, timeZone: 'Asia/Seoul')` 를 파일마다 각자 생성하던 관행이
 * 15 개 사이트로 늘어(08-09 리뷰 13 + cycle251 `PortfolioRiskCard` + cycle249
 * `DailyReportTab`) 컨벤션이 코드가 아니라 문서(`frontend/CLAUDE.md`)에만 있었다.
 * 이 모듈은 **신규 사이트부터** 단일 진실원으로 삼는다 — 기존 13 사이트는 사이트별
 * 출력 동등성 확인이 선행돼야 하므로 이번 사이클 범위 밖(점진 마이그레이션).
 *
 * 모든 함수는 KST 기준 24시제로 값을 산출하며, `Date` 인스턴스의 로컬타임 getter
 * (`getHours()`/`getMinutes()` 등)를 쓰지 않는다 — 브라우저/컨테이너 TZ 에 따라
 * 같은 시각이 다르게 표시되는 것을 원천 차단한다(cycle251 g251_3 관례 계승).
 * 잘못된 입력(빈 값·파싱 실패)은 `formatKstHHMM`/`formatKstDateTime` 모두 `'—'`
 * (em dash)로 통일 — 호출부가 각자 폴백을 두지 않게 한다.
 */

const HHMM_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false, // ko-KR 기본은 12시제("오후 01:05") — HH:mm 계약을 위해 명시
})

const DATETIME_PART_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

const DATE_PART_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

function parseValidDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  return date
}

/** `formatToParts` 결과를 `{year, month, day, hour, minute, second}` 맵으로 — ko-KR
 * 리터럴 서식(`2026. 09. 07. 13:05:09`)은 `yyyy-MM-dd HH:mm:ss` 계약과 맞지 않아
 * 부품을 직접 조립한다. */
function partsToMap(parts: Intl.DateTimeFormatPart[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const part of parts) {
    if (part.type !== 'literal') map[part.type] = part.value
  }
  return map
}

/** KST `HH:mm` (24시제). UTC 입력도 KST 로 환산. 잘못된 입력 → `'—'`. */
export function formatKstHHMM(iso: string | null | undefined): string {
  const date = parseValidDate(iso)
  if (!date) return '—'
  return HHMM_FORMATTER.format(date)
}

/** KST `yyyy-MM-dd HH:mm:ss` (24시제, 초 포함). UTC 입력도 KST 로 환산. 잘못된 입력 → `'—'`. */
export function formatKstDateTime(iso: string | null | undefined): string {
  const date = parseValidDate(iso)
  if (!date) return '—'
  const parts = partsToMap(DATETIME_PART_FORMATTER.formatToParts(date))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}

/** KST 기준 오늘 날짜 `YYYY-MM-DD`. `now` 는 테스트 seam(생략 시 현재 시각). */
export function kstTodayISO(now?: Date): string {
  const base = now ?? new Date()
  const parts = partsToMap(DATE_PART_FORMATTER.formatToParts(base))
  return `${parts.year}-${parts.month}-${parts.day}`
}
