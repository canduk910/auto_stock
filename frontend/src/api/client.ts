import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 10000,
  // cycle246 — nginx Basic Auth(cycle243) 도입 후 **로그인 다이얼로그가 두 번** 뜨던 것을
  // 닫는다. 원인은 realm 불일치가 아니었다(전 location 이 동일 `"auto_stock"` 실측).
  // 문서 `/` 는 인증되는데 SPA 의 XHR 이 자격 없이 나가 401 을 받고 브라우저가 **두 번째로**
  // 묻는 것이었다 — nginx 접근 로그가 같은 초에 `/api/*` 여러 건을 user 필드 `-`(무자격)로
  // 기록했고, 재입력 후에는 같은 경로가 `ubuntu` 로 찍혔다.
  // `withCredentials: true` 는 XHR 에 자격(HTTP Basic 포함)을 실어 보내게 한다. 이 앱은
  // `baseURL: '/api'` 상대경로 = **동일 출처**라 CORS 파급이 없고, 백엔드는 cycle243 에서
  // 와일드카드 CORS 를 폐지하고 상태변경 Origin 검사를 넣어 둔 상태다.
  // 회귀 가드 = `tests/unit/ast/test_cycle246_nginx_template_no_key_leak.py::G-246-5`.
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

export default apiClient
