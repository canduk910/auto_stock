/**
 * DailyReportTab — W2 (2026-09-05): daily_log_reports.ext_* 6컬럼(cycle249) 표시.
 *
 * 배경: cycle249 가 daily_log_reports 에 ext_provider/ext_model/ext_summary/
 * ext_findings/ext_report_md/ext_created_at 을 추가했고, 매일 20:20 KST Claude 루틴이
 * `POST /api/log-reports/{date}/external` 로 채운다. GET 은 SELECT * 라 이미 응답에
 * 포함되지만 대시보드는 아직 OpenAI 필드만 그린다.
 *
 * 요구 행위:
 * - ext-A: ext 없는 레거시 행 — "Claude 분석" 텍스트 0건, 기존 총평·개선 항목 렌더 불변
 * - ext-B: ext 있는 행 — "Claude 분석" 헤더 + provider/model + ext_summary + ext_findings
 *   건수 + FindingCard 제목 렌더, OpenAI 총평도 그대로 공존
 * - ext-C: ext_report_md 접이식 토글 동작 (기본 접힘 → 클릭 시 펼침)
 * - ext-D: 좌측 날짜 목록 "Claude" 배지 유무 (ext_summary 있는 행만)
 * - ext-E: 타입 가드 — types/log_reports.ts 소스에 6개 키 전부 존재 (문자열 검사)
 *
 * 시정 (2026-09-05, 확증 결함 2건):
 * - ext-F: severity 정렬 회귀 가드 — [low, high, medium] 입력 → [high, medium, low] 렌더
 *   (sortedExtFindings 의 .sort 제거/반전 뮤테이션을 잡는다. 종전 픽스처는 이미 정렬된
 *   상태라 순서 단언이 없었다 — 정렬 제거·반전 뮤테이션 모두 5/5 PASS 로 통과하던 결함)
 * - ext-G/H/I: ext_findings 항목 내부 정규화 — 비문자열 detail(object)/잘못된
 *   severity('critical')/title·detail 결손 항목이 하나 섞여도 렌더가 크래시하지 않는다
 *   (레거시 log_analysis_engine._validate_report 와 동일 규약을 프론트에서 재현)
 * - ext-J: ReportCard error boundary — 정규화가 못 잡는 예외(레거시 findings 쪽 비문자열
 *   detail)로 렌더가 던져도 탭 전체가 아니라 카드만 대체된다
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import DailyReportTab from '../DailyReportTab'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'
import type { LogReportItem, Severity } from '../../types/log_reports'

const legacyReport: LogReportItem = {
  id: 'r1',
  target_date: '2026-09-01',
  summary: '오늘은 정상 운영되었습니다.',
  findings: [
    {
      category: 'trading',
      severity: 'medium',
      title: '레거시 발견',
      detail: '레거시 상세',
      suggestion: '레거시 권고',
    },
  ],
  metrics: null,
  model: 'gpt-4o',
  created_at: '2026-09-01T20:15:00+09:00',
}

const extReport: LogReportItem = {
  id: 'r2',
  target_date: '2026-09-02',
  summary: 'OpenAI 총평입니다.',
  findings: [
    {
      category: 'order',
      severity: 'high',
      title: 'OpenAI 발견1',
      detail: 'openai 상세',
      suggestion: 'openai 권고',
    },
  ],
  metrics: null,
  model: 'gpt-4o',
  created_at: '2026-09-02T20:15:00+09:00',
  ext_provider: 'anthropic',
  ext_model: 'claude-sonnet-5',
  ext_summary: 'Claude 총평입니다.\n두번째 줄입니다.',
  ext_findings: [
    {
      category: 'websocket',
      severity: 'high',
      title: 'Claude 발견1',
      detail: 'claude 상세1',
      suggestion: 'claude 권고1',
    },
    {
      category: 'balance',
      severity: 'low',
      title: 'Claude 발견2',
      detail: 'claude 상세2',
      suggestion: 'claude 권고2',
    },
  ],
  ext_report_md: '# 상세 리포트\n\n마크다운 본문입니다.',
  ext_created_at: '2026-09-02T20:20:00+09:00',
}

function mockList(items: LogReportItem[]) {
  server.use(http.get('/api/log-reports', () => HttpResponse.json(wrap(items))))
}

describe('DailyReportTab — ext_* (W2, cycle249 연동)', () => {
  it('ext-A: ext 없는 레거시 행 — Claude 분석 텍스트 0건, 기존 렌더 불변', async () => {
    mockList([legacyReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByText('2026-09-01 총평')
    expect(screen.getByText('오늘은 정상 운영되었습니다.')).toBeInTheDocument()
    expect(screen.getByText('레거시 발견')).toBeInTheDocument()
    expect(screen.getByText('개선 항목 (1건)')).toBeInTheDocument()

    expect(screen.queryByText(/Claude 분석/)).toBeNull()
    expect(screen.queryByTestId('ext-analysis-card')).toBeNull()
  })

  it('ext-B: ext 있는 행 — Claude 분석 헤더/본문/findings + OpenAI 총평 공존', async () => {
    mockList([extReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    const card = await screen.findByTestId('ext-analysis-card')
    expect(card.textContent).toContain('2026-09-02 Claude 분석')
    expect(card.textContent).toContain('anthropic')
    expect(card.textContent).toContain('claude-sonnet-5')

    const summary = screen.getByTestId('ext-summary')
    expect(summary.textContent).toContain('Claude 총평입니다.')
    expect(summary.textContent).toContain('두번째 줄입니다.')

    expect(card.textContent).toContain('개선 항목 (2건)')
    expect(screen.getByText('Claude 발견1')).toBeInTheDocument()
    expect(screen.getByText('Claude 발견2')).toBeInTheDocument()

    // OpenAI 총평 블록도 그대로 공존
    expect(screen.getByText('2026-09-02 총평')).toBeInTheDocument()
    expect(screen.getByText('OpenAI 총평입니다.')).toBeInTheDocument()
    expect(screen.getByText('OpenAI 발견1')).toBeInTheDocument()
  })

  it('ext-C: ext_report_md 접이식 토글 — 기본 접힘, 클릭 시 펼침', async () => {
    mockList([extReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByTestId('ext-analysis-card')
    expect(screen.queryByText(/마크다운 본문입니다/)).toBeNull()

    const toggle = screen.getByTestId('ext-report-md-toggle')
    fireEvent.click(toggle)

    await waitFor(() => {
      expect(screen.getByText(/마크다운 본문입니다/)).toBeInTheDocument()
    })

    fireEvent.click(toggle)
    await waitFor(() => {
      expect(screen.queryByText(/마크다운 본문입니다/)).toBeNull()
    })
  })

  it('ext-D: 좌측 날짜 목록 Claude 배지 — ext_summary 있는 행만', async () => {
    mockList([extReport, legacyReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByText('2026-09-02')
    expect(screen.getByTestId(`ext-badge-${extReport.id}`)).toBeInTheDocument()
    expect(screen.queryByTestId(`ext-badge-${legacyReport.id}`)).toBeNull()
  })

  it('ext-E: 타입 가드 — log_reports.ts 소스에 ext_* 6키 전부 존재', () => {
    const typesPath = path.join(__dirname, '..', '..', 'types', 'log_reports.ts')
    const source = readFileSync(typesPath, 'utf-8')
    for (const key of [
      'ext_provider',
      'ext_model',
      'ext_summary',
      'ext_findings',
      'ext_report_md',
      'ext_created_at',
    ]) {
      expect(source.includes(key), `types/log_reports.ts 에 ${key} 결손`).toBe(true)
    }
  })

  it('ext-F: severity 정렬 — [low, high, medium] 입력 → [high, medium, low] 렌더 순서', async () => {
    const sortReport: LogReportItem = {
      ...legacyReport,
      id: 'r3',
      target_date: '2026-09-03',
      ext_summary: '정렬 검증용 총평',
      ext_findings: [
        { category: 'trading', severity: 'low', title: '낮음 발견', detail: '낮음 상세', suggestion: '' },
        { category: 'order', severity: 'high', title: '높음 발견', detail: '높음 상세', suggestion: '' },
        { category: 'scan', severity: 'medium', title: '보통 발견', detail: '보통 상세', suggestion: '' },
      ],
    }
    mockList([sortReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    const card = await screen.findByTestId('ext-analysis-card')
    const titles = Array.from(card.querySelectorAll('h4')).map((h) => h.textContent)
    expect(titles).toEqual(['높음 발견', '보통 발견', '낮음 발견'])
  })

  it('ext-G: 정규화 — 비문자열 detail(object) 도 크래시 없이 문자열로 렌더', async () => {
    const objDetailReport: LogReportItem = {
      ...legacyReport,
      id: 'r4',
      target_date: '2026-09-04',
      ext_summary: '객체 detail 검증용 총평',
      ext_findings: [
        {
          category: 'order',
          severity: 'high',
          // 백엔드 ExternalReportIn.findings 는 항목 내부를 검증하지 않아
          // 임의 형태가 그대로 온다 — 타입은 Finding 이지만 런타임은 아닐 수 있다.
          title: 'ObjDetail' as unknown as string,
          detail: { a: 1 } as unknown as string,
          suggestion: '',
        },
      ],
    }
    mockList([objDetailReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    const card = await screen.findByTestId('ext-analysis-card')
    expect(card.textContent).toContain('ObjDetail')
    expect(card.textContent).toContain('{"a":1}')
    expect(screen.queryByTestId('report-card-error')).toBeNull()
  })

  it('ext-H: 정규화 — 잘못된 severity("critical") → "보통" 취급', async () => {
    const badSeverityReport: LogReportItem = {
      ...legacyReport,
      id: 'r5',
      target_date: '2026-09-05',
      ext_summary: '잘못된 severity 검증용 총평',
      ext_findings: [
        {
          category: 'order',
          severity: 'critical' as unknown as Severity,
          title: '잘못된 심각도 발견',
          detail: '상세',
          suggestion: '',
        },
      ],
    }
    mockList([badSeverityReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    const card = await screen.findByTestId('ext-analysis-card')
    expect(card.textContent).toContain('잘못된 심각도 발견')
    // 배지가 undefined 라벨 없이 SEVERITY_LABEL.medium("보통")으로 폴백해야 한다.
    const badge = Array.from(card.querySelectorAll('span')).find((s) => s.textContent === '보통')
    expect(badge).toBeDefined()
    expect(card.textContent).not.toContain('undefined')
  })

  it('ext-I: 정규화 — title/detail 결손 항목 드롭', async () => {
    const droppedItemReport: LogReportItem = {
      ...legacyReport,
      id: 'r6',
      target_date: '2026-09-06',
      ext_summary: '결손 항목 드롭 검증용 총평',
      ext_findings: [
        { category: 'order', severity: 'high', title: '', detail: '상세만 있음', suggestion: '' },
        { category: 'order', severity: 'high', title: '정상 항목', detail: '정상 상세', suggestion: '' },
      ],
    }
    mockList([droppedItemReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    const card = await screen.findByTestId('ext-analysis-card')
    expect(card.textContent).toContain('개선 항목 (1건)')
    expect(screen.getByText('정상 항목')).toBeInTheDocument()
    expect(screen.queryByText('상세만 있음')).toBeNull()
  })

  it('ext-J: ReportCard error boundary — 정규화 밖(레거시 findings) 예외는 카드만 대체', async () => {
    const crashingLegacyReport: LogReportItem = {
      ...legacyReport,
      id: 'r7',
      target_date: '2026-09-07',
      findings: [
        {
          category: 'trading',
          severity: 'high',
          title: '레거시 크래시 유발',
          // 레거시 findings 경로는 정규화 대상이 아니다(ext_findings 한정 시정) —
          // React 는 객체 자식을 렌더할 수 없어 이 값이 그대로 오면 던진다.
          detail: { nested: true } as unknown as string,
          suggestion: '',
        },
      ],
    }
    mockList([crashingLegacyReport, legacyReport])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByTestId('report-card-error')
    // 카드만 대체되고 좌측 날짜 목록(탭 전체)은 살아있어야 한다.
    expect(screen.getByText('2026-09-07')).toBeInTheDocument()
    expect(screen.getByText('2026-09-01')).toBeInTheDocument()
  })
})
