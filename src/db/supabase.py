"""Supabase 클라이언트 초기화."""

from __future__ import annotations

from supabase import create_client, Client

from src.config import settings

supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
