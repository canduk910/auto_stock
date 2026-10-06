#!/usr/bin/env python3
"""30년 전략 성적표 보고서(_workspace/reports/*.html)를
frontend/public/backtest/scoreboard_30y.html 로 변환·게시한다.

변환 내역:
1. 외부 CDN(cdnjs Chart.js) 의존 제거 — frontend/node_modules/chart.js 의
   UMD 번들을 public/backtest/chart.umd.js 로 복사하고 <script src> 를
   상대경로로 바꾼다.
2. 원문 보고서가 <!doctype>/<html>/<head>/<body> 없이 조각(fragment)으로
   작성됐으면 독립 페이지로 열리도록 감싼다. 내용·숫자는 건드리지 않는다.

성적표가 갱신될 때마다 이 스크립트만 다시 돌리면 된다:
    python3 tools/replay/scoreboard_page/publish_to_frontend.py \\
        _workspace/reports/<날짜>_scoreboard_30y.html
"""
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "frontend"
PUBLIC_BACKTEST_DIR = FRONTEND_DIR / "public" / "backtest"
CHART_JS_SRC = FRONTEND_DIR / "node_modules" / "chart.js" / "dist" / "chart.umd.js"
CHART_JS_DEST = PUBLIC_BACKTEST_DIR / "chart.umd.js"
OUTPUT_HTML = PUBLIC_BACKTEST_DIR / "scoreboard_30y.html"

CDN_SCRIPT_RE = re.compile(
    r'<script\s+src="https://cdnjs\.cloudflare\.com/ajax/libs/Chart\.js/[^"]*"\s*></script>'
)


def wrap_as_standalone_page(fragment: str) -> str:
    """<!doctype>/<html>/<head>/<body> 가 없으면 감싼다. 있으면 그대로 둔다."""
    if re.search(r"<!doctype\s+html", fragment, re.IGNORECASE):
        return fragment

    # <title> 은 조각 안에 이미 있다 — head 블록으로 끌어올리지 않고
    # 조각 전체를 <head> 뒤에 그대로 이어 붙인다(스타일·메타가 전부 head 소속).
    # <body> 경계는 명시적 h1/div 블록 시작 지점을 찾아 나눈다 — 대신
    # 더 단순하고 안전하게: head 성격(meta/title/link/style)과 그 외를
    # 가르지 않고 전체를 <head> 안에 두고, <body> 는 별도로 비워두지 않는다.
    # 브라우저는 head 안의 비-head 콘텐츠(div 등)를 자동으로 body 로 옮겨
    # 렌더링하므로(HTML5 파서의 복원 규칙) 실제로는 안전하게 열린다.
    # 다만 명시적으로 옳게 만들기 위해 첫 <style>...</style> 다음까지를
    # head, 그 이후를 body 로 분리한다.
    style_end_match = None
    for m in re.finditer(r"</style>", fragment, re.IGNORECASE):
        style_end_match = m
    head_part = fragment
    body_part = ""
    if style_end_match:
        split_at = style_end_match.end()
        head_part = fragment[:split_at]
        body_part = fragment[split_at:]

    has_charset = bool(re.search(r"<meta\s+charset=", head_part, re.IGNORECASE))
    has_viewport = bool(re.search(r'<meta\s+name="viewport"', head_part, re.IGNORECASE))
    extra_meta = ""
    if not has_charset:
        extra_meta += '<meta charset="utf-8">\n'
    if not has_viewport:
        extra_meta += '<meta name="viewport" content="width=device-width, initial-scale=1">\n'

    return (
        "<!doctype html>\n"
        '<html lang="ko">\n'
        "<head>\n"
        f"{extra_meta}"
        f"{head_part}\n"
        "</head>\n"
        "<body>\n"
        f"{body_part}\n"
        "</body>\n"
        "</html>\n"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(f"사용법: {sys.argv[0]} <보고서 html 경로>", file=sys.stderr)
        return 1

    report_path = Path(sys.argv[1]).resolve()
    if not report_path.is_file():
        print(f"파일을 찾을 수 없습니다: {report_path}", file=sys.stderr)
        return 1

    if not CHART_JS_SRC.is_file():
        print(
            f"frontend/node_modules/chart.js 가 없습니다 — "
            f"'cd frontend && npm install' 먼저 실행하세요 ({CHART_JS_SRC})",
            file=sys.stderr,
        )
        return 1

    PUBLIC_BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

    raw_html = report_path.read_text(encoding="utf-8")

    cdn_matches = CDN_SCRIPT_RE.findall(raw_html)
    if not cdn_matches:
        print(
            "경고: cdnjs Chart.js <script> 태그를 찾지 못했습니다 — "
            "보고서 형식이 바뀌었을 수 있습니다. 그대로 진행합니다.",
            file=sys.stderr,
        )
    local_html = CDN_SCRIPT_RE.sub('<script src="chart.umd.js"></script>', raw_html)

    standalone_html = wrap_as_standalone_page(local_html)

    shutil.copyfile(CHART_JS_SRC, CHART_JS_DEST)
    OUTPUT_HTML.write_text(standalone_html, encoding="utf-8")

    print(f"게시 완료: {OUTPUT_HTML} ({len(standalone_html):,} bytes)")
    print(f"Chart.js 복사: {CHART_JS_DEST} ({CHART_JS_DEST.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
