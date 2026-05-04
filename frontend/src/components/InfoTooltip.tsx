import { useEffect, useRef, useState } from 'react'

type Props = {
  content: string
  widthClass?: string
  ariaLabel?: string
}

export default function InfoTooltip({
  content,
  widthClass = 'w-72',
  ariaLabel = '설명 보기',
}: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onEsc)
    }
  }, [open])

  return (
    <span ref={ref} className="relative inline-flex align-middle">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        aria-label={ariaLabel}
        aria-expanded={open}
        className="inline-flex items-center justify-center w-4 h-4 ml-1 text-[10px] font-bold text-gray-400 hover:text-gray-700 border border-gray-300 hover:border-gray-500 rounded-full transition-colors"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          className={`absolute bottom-full left-1/2 -translate-x-1/2 mb-2 ${widthClass} px-3 py-2 text-xs font-normal text-white bg-gray-900 rounded-md shadow-lg z-50 whitespace-pre-line leading-relaxed`}
        >
          {content}
        </span>
      )}
    </span>
  )
}
