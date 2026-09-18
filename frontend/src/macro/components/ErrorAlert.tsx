interface ErrorAlertProps {
  message?: string | null
}

export default function ErrorAlert({ message }: ErrorAlertProps) {
  if (!message) return null
  return (
    <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700">
      <span className="font-semibold">오류: </span>
      {message}
    </div>
  )
}
