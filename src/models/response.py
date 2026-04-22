"""API 응답 공통 모델."""

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    message: str = ""
