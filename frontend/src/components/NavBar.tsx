import {
  useEffect,
  useRef,
  useState,
  type FocusEvent as ReactFocusEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { CONTENT_WIDTH_DEFAULT_LEVEL, contentMaxWidth } from '../utils/contentWidth'

// cycle288 — 메뉴바 2단 카테고리화. 사용자 지정 묶음(원문) =
// "대시보드 // 거래내역 // 로그 // 조건검색 추적, 종목마스터 // 전략현황, 전략수정 AI자문 //
//  설정 // 장운영상태, 실시간상태" — 묶음·순서는 바꾸지 않는다. 라우트 경로도 불변.

interface NavLeaf {
  to: string
  label: string
}

interface NavGroupDef {
  id: string
  label: string
  children: NavLeaf[]
}

type NavEntry = ({ kind: 'leaf' } & NavLeaf) | ({ kind: 'group' } & NavGroupDef)

const NAV_STRUCTURE: NavEntry[] = [
  { kind: 'leaf', to: '/', label: '대시보드' },
  { kind: 'leaf', to: '/history', label: '거래 내역' },
  { kind: 'leaf', to: '/logs', label: '로그' },
  {
    kind: 'group',
    id: 'stock',
    label: '종목',
    children: [
      { to: '/strategy-funnel', label: '조건검색 추적' },
      { to: '/stock-master', label: '종목마스터' },
    ],
  },
  {
    kind: 'group',
    id: 'strategy',
    label: '전략',
    children: [
      { to: '/strategies', label: '전략 현황' },
      { to: '/recommendations', label: '전략수정 AI자문' },
    ],
  },
  { kind: 'leaf', to: '/settings', label: '설정' },
  {
    kind: 'group',
    id: 'ops',
    label: '운영상태',
    children: [
      { to: '/market-state', label: '장운영상태' },
      { to: '/realtime-health', label: '실시간 상태' },
    ],
  },
]

// 모바일 헤더 "현재 메뉴명" 판정용 평탄화 목록 (그룹 순서·구성 그대로 펼침)
const FLAT_LEAVES: NavLeaf[] = NAV_STRUCTURE.flatMap((entry) =>
  entry.kind === 'leaf' ? [{ to: entry.to, label: entry.label }] : entry.children,
)

function isPathActive(to: string, pathname: string): boolean {
  return to === '/' ? pathname === '/' : pathname.startsWith(to)
}

function isGroupActive(group: NavGroupDef, pathname: string): boolean {
  return group.children.some((child) => isPathActive(child.to, pathname))
}

const LEAF_LINK_CLASS = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium px-3 py-2 rounded-md whitespace-nowrap ${
    isActive ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:text-gray-900'
  }`

const MENU_ITEM_CLASS = ({ isActive }: { isActive: boolean }) =>
  `block text-sm font-medium px-3 py-2 whitespace-nowrap ${
    isActive ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
  }`

const DRAWER_LEAF_CLASS = ({ isActive }: { isActive: boolean }) =>
  `block text-sm font-medium px-3 py-2 rounded-md ${
    isActive ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
  }`

const DRAWER_CHILD_CLASS = ({ isActive }: { isActive: boolean }) =>
  `block text-sm font-medium pl-6 pr-3 py-2 rounded-md ${
    isActive ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
  }`

// 나브 내부 컨테이너 폭 — cycle288: 슬라이더 값과 **무관한 고정폭**.
//
// 종전 의도(2026-07-24, frontend/CLAUDE.md 참고)는 <main> 과 이 컨테이너가 같은 동적
// max-width 를 써서 "전체폭일 때 메뉴/슬라이더가 콘텐츠 좌우 끝에 정렬"이었다. 그런데
// 폭 조정 <input type="range"> 이 바로 이 컨테이너 안에 있어서, 드래그 도중 컨테이너
// 자체가 리사이즈되며 슬라이더 박스의 화면 좌표가 함께 움직였다 — 브라우저가 드래그
// 포인터를 요소 박스 기준으로 재해석해 값이 튀고 화면이 깜박였다(사용자 보고, cycle288).
// 그래서 나브는 기본 레벨(CONTENT_WIDTH_DEFAULT_LEVEL) 고정폭으로 얼리고, <main> 만
// 슬라이더 값을 반영한다. **되돌리면 이 깜박임이 재발한다** — 이 주석을 지우지 말 것.
const NAV_INNER_MAX_WIDTH = contentMaxWidth(CONTENT_WIDTH_DEFAULT_LEVEL)

interface NavBarProps {
  contentWidthLevel: number
  onContentWidthChange: (level: number) => void
}

export default function NavBar({ contentWidthLevel, onContentWidthChange }: NavBarProps) {
  const { pathname } = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [openGroup, setOpenGroup] = useState<string | null>(null)
  const containerRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const triggerRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const itemRefs = useRef<Record<string, Array<HTMLAnchorElement | null>>>({})

  // 라우트 이동(뒤로가기 포함) 시 열린 드롭다운·모바일 드로어를 닫는다.
  // 종전엔 드로어 닫힘이 링크 onClick 에만 있어 뒤로가기로 이동하면 열린 채 남았다.
  useEffect(() => {
    setOpenGroup(null)
    setMobileOpen(false)
  }, [pathname])

  // 바깥 클릭 · Escape — 열린 그룹이 있을 때만 리스너를 붙인다 (InfoTooltip.tsx 패턴 답습)
  useEffect(() => {
    if (!openGroup) return
    const onDocClick = (e: MouseEvent) => {
      const container = containerRefs.current[openGroup]
      if (container && !container.contains(e.target as Node)) setOpenGroup(null)
    }
    const onEsc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const trigger = triggerRefs.current[openGroup]
      setOpenGroup(null)
      trigger?.focus()
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onEsc)
    }
  }, [openGroup])

  const currentLeaf = FLAT_LEAVES.find((item) => isPathActive(item.to, pathname))

  const toggleGroup = (id: string) => {
    setOpenGroup((prev) => (prev === id ? null : id))
  }

  const focusMenuItem = (id: string, index: number) => {
    const items = itemRefs.current[id]
    if (!items || items.length === 0) return
    const wrapped = ((index % items.length) + items.length) % items.length
    items[wrapped]?.focus()
  }

  const handleTriggerKeyDown = (id: string) => (e: ReactKeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpenGroup(id)
      requestAnimationFrame(() => focusMenuItem(id, 0))
    } else if (e.key === 'ArrowUp') {
      // 검증 라운드 시정 — WAI-ARIA APG 메뉴버튼 규약: ArrowUp 은 열고 마지막 항목에 포커스.
      // 종전엔 트리거에서 ArrowUp 이 아무 반응이 없었다(ArrowDown 만 처리).
      e.preventDefault()
      setOpenGroup(id)
      requestAnimationFrame(() => focusMenuItem(id, -1))
    }
  }

  const handleMenuItemKeyDown = (id: string, index: number) => (e: ReactKeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      focusMenuItem(id, index + 1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      focusMenuItem(id, index - 1)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpenGroup(null)
      triggerRefs.current[id]?.focus()
    }
  }

  // 검증 라운드 시정 — 포커스가 패널 밖으로 나가면(Tab 등) 닫는다.
  // 종전엔 바깥 mousedown·Escape 만 닫혀서, 키보드로 Tab 을 눌러 패널 밖으로 나가도
  // 열린 채 남아 있었다(포커스는 이미 떠났는데 패널만 화면에 떠 있는 상태).
  const handleGroupBlur = (id: string) => (e: ReactFocusEvent<HTMLDivElement>) => {
    const container = containerRefs.current[id]
    const next = e.relatedTarget as Node | null
    if (container && (!next || !container.contains(next))) {
      setOpenGroup(null)
    }
  }

  return (
    <nav className="bg-white shadow-sm" aria-label="기본 네비게이션">
      {/* 나브 내부 폭 — cycle288: 고정폭(위 NAV_INNER_MAX_WIDTH 주석 참고, 슬라이더와 무관) */}
      <div
        className="mx-auto px-4"
        style={{ maxWidth: NAV_INNER_MAX_WIDTH }}
        data-testid="nav-inner"
      >
        {/* PC (sm 이상): 한 줄 가로 메뉴 */}
        <div className="hidden sm:flex items-center h-14 gap-8">
          <span className="font-brand font-bold tracking-tight text-gray-900 shrink-0">DK Stock</span>
          <div className="flex items-center gap-1 flex-wrap">
            {NAV_STRUCTURE.map((entry) => {
              if (entry.kind === 'leaf') {
                return (
                  <NavLink key={entry.to} to={entry.to} end={entry.to === '/'} className={LEAF_LINK_CLASS}>
                    {entry.label}
                  </NavLink>
                )
              }

              const active = isGroupActive(entry, pathname)
              const isOpen = openGroup === entry.id

              return (
                <div
                  key={entry.id}
                  className="relative"
                  ref={(el) => {
                    containerRefs.current[entry.id] = el
                  }}
                  onBlur={handleGroupBlur(entry.id)}
                >
                  {/* 검증 라운드 시정 — aria-haspopup 제거. 이 트리거는 role="menu" 를 여는 게
                      아니라 하위가 평범한 링크(<a>)인 disclosure(펼침) 위젯이다.
                      aria-haspopup="true" 는 "menu" 와 동치라 스크린리더가 메뉴 규약(role=menu/
                      menuitem·roving tabindex)을 기대하게 만드는데 실제로는 없었다 — 약속하지
                      못하는 규약을 내보내지 않는다. aria-expanded 만으로 펼침 상태는 충분히
                      전달된다. */}
                  <button
                    type="button"
                    ref={(el) => {
                      triggerRefs.current[entry.id] = el
                    }}
                    aria-expanded={isOpen}
                    onClick={() => toggleGroup(entry.id)}
                    onKeyDown={handleTriggerKeyDown(entry.id)}
                    data-testid={`nav-group-trigger-${entry.id}`}
                    className={`inline-flex items-center gap-1 text-sm font-medium px-3 py-2 rounded-md whitespace-nowrap ${
                      active ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    {entry.label}
                    <svg
                      aria-hidden="true"
                      className={`h-3 w-3 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {isOpen && (
                    <div
                      data-testid={`nav-group-panel-${entry.id}`}
                      className="absolute left-0 top-full mt-1 min-w-max bg-white border border-gray-200 rounded-md shadow-lg py-1 z-10"
                    >
                      {entry.children.map((child, index) => (
                        <NavLink
                          key={child.to}
                          to={child.to}
                          ref={(el) => {
                            if (!itemRefs.current[entry.id]) itemRefs.current[entry.id] = []
                            itemRefs.current[entry.id][index] = el
                          }}
                          onClick={() => {
                            // 검증 라운드 시정 — 항목 선택 후 포커스를 트리거로 되돌린다.
                            // 종전엔 클릭한 항목이 언마운트(패널이 닫히며 사라짐)되면서 포커스를
                            // 잃은 요소가 함께 사라져 activeElement 가 <body> 로 떨어졌다(키보드
                            // 사용자가 다음 조작을 위해 문서 맨 앞부터 Tab 을 다시 밟아야 했다).
                            // 트리거를 먼저 focus() 한 뒤 패널을 닫으면 트리거가 여전히 DOM 에
                            // 남아 있어 포커스가 자연스럽게 유지된다.
                            triggerRefs.current[entry.id]?.focus()
                            setOpenGroup(null)
                          }}
                          onKeyDown={handleMenuItemKeyDown(entry.id, index)}
                          className={MENU_ITEM_CLASS}
                        >
                          {child.label}
                        </NavLink>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* 화면 폭 조정 슬라이더 — <main> max-width 사용자 조정, PC 전용(모바일은 소화면이라 조정 불요) */}
          <div className="ml-auto flex items-center gap-2 shrink-0">
            <span className="text-xs text-gray-400 select-none" aria-hidden="true">
              폭
            </span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={contentWidthLevel}
              onChange={(e) => onContentWidthChange(Number(e.target.value))}
              data-testid="content-width-slider"
              aria-label="화면 폭 조정"
              className="w-24 h-2 rounded-lg appearance-none cursor-pointer"
              style={{ accentColor: 'var(--color-navy-600)' }}
            />
          </div>
        </div>

        {/* 모바일 (sm 미만): 로고 + 현재 메뉴명 + 햄버거 버튼 */}
        <div className="flex sm:hidden items-center justify-between h-14">
          <span className="font-brand font-bold tracking-tight text-gray-900">DK Stock</span>
          <span className="text-sm font-medium text-gray-700">{currentLeaf?.label ?? '메뉴'}</span>
          <button
            data-testid="mobile-menu-button"
            aria-label={mobileOpen ? '메뉴 닫기' : '메뉴 열기'}
            aria-haspopup="true"
            aria-controls="mobile-menu-drawer"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((prev) => !prev)}
            className="p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100"
          >
            {/* 햄버거 / X 아이콘 */}
            {mobileOpen ? (
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {/* 모바일 드롭다운 메뉴 — 그룹은 제목(링크 아님) + 들여쓴 하위 링크로 항상 전부 표시 */}
      {mobileOpen && (
        <div
          id="mobile-menu-drawer"
          data-testid="mobile-menu-drawer"
          className="sm:hidden border-t border-gray-100 bg-white shadow-md"
        >
          <div className="px-2 py-2 space-y-1">
            {NAV_STRUCTURE.map((entry) => {
              if (entry.kind === 'leaf') {
                return (
                  <NavLink
                    key={entry.to}
                    to={entry.to}
                    end={entry.to === '/'}
                    onClick={() => setMobileOpen(false)}
                    className={DRAWER_LEAF_CLASS}
                  >
                    {entry.label}
                  </NavLink>
                )
              }
              return (
                <div key={entry.id} data-testid={`nav-mobile-group-${entry.id}`}>
                  <div className="px-3 pt-2 pb-1 text-xs font-semibold text-gray-400">{entry.label}</div>
                  {entry.children.map((child) => (
                    <NavLink
                      key={child.to}
                      to={child.to}
                      onClick={() => setMobileOpen(false)}
                      className={DRAWER_CHILD_CLASS}
                    >
                      {child.label}
                    </NavLink>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </nav>
  )
}
