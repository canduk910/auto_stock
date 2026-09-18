interface LoadingSpinnerProps {
  message?: string
}

export default function LoadingSpinner({ message = "데이터를 불러오는 중..." }: LoadingSpinnerProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4 text-gray-500">
      <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      <p className="text-sm">{message}</p>
    </div>
  )
}
