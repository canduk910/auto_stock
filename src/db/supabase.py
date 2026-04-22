"""Supabase 클라이언트 초기화."""

from supabase import create_client, Client

from src.config import settings

supabase: Client = create_client(settings.supabase_url, settings.supabase_key)
