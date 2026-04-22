export interface ApiResponse<T> {
  success: boolean
  data: T
  message: string
}

export interface ApiError {
  detail: string
}
