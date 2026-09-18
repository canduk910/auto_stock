import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  const apiTarget = process.env.VITE_API_URL || 'http://localhost:8001'
  console.log(`[vite] proxy target: ${apiTarget} (mode: ${mode})`)
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 3000,
      proxy: {
        // cycle303 — macro_lite 이식 1단계. vite 의 프록시 매칭은 **키 등록 순서대로**
        // prefix 를 검사하므로(첫 매치 채택) `/api/macro` 를 `/api` **앞**에 둔다 — 뒤에
        // 두면 모든 `/api/macro/*` 요청이 먼저 `/api` 에 걸려 backend(8001/8002)로 가버린다.
        // `X-API-Key` 헤더는 **넣지 않는다** — macro 컨테이너는 그 인증 미들웨어가 없다
        // (`macro/main.py` 의 `AUTH_DEPENDENCY=None`, 보호는 nginx Basic Auth 한 겹뿐이고
        // dev 에서는 그것도 없다). `VITE_MACRO_API_URL` 미설정 시 기본값은 dev compose 가
        // 여는 macro 서비스의 루프백 게시 포트(`docker-compose.yml` 참조).
        '/api/macro': {
          target: process.env.VITE_MACRO_API_URL || 'http://localhost:8010',
          changeOrigin: true,
        },
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          // cycle243 — 백엔드 X-API-Key 인증(fail-closed)의 dev 생존 경로.
          // 브라우저가 아니라 **vite dev server(서버 측)** 가 헤더를 넣는다 — 번들에 키가
          // 실리지 않는다. 개발 예외·개발용 기본키를 두지 않는 대신 각자 `.env` 의
          // API_AUTH_KEY 를 쓴다(미설정이면 401 + 백엔드 기동 로그 CRITICAL 로 자가 진단).
          // 값 주입 경로는 `VITE_API_URL` 과 동일한 **프로세스 환경변수**다:
          // docker compose(dev) 는 frontend 서비스 `environment` 가 넣고, 컨테이너 없이
          // `npm run dev` 로 띄울 때는 `API_AUTH_KEY=… npm run dev` 처럼 export 해야 한다
          // (vite 의 `.env` 로딩은 `VITE_` 접두사 + `import.meta.env` 전용이라 여기엔 안 온다).
          //
          // `Origin` 도 함께 정규화한다 — `changeOrigin: true` 는 **Host 만** target 으로
          // 바꾸고 브라우저 `Origin: http://localhost:3000` 은 그대로 전달한다. 백엔드의
          // 상태변경(POST/PUT/PATCH/DELETE) Origin 검사는 `Origin` 의 host:port 와 `Host`
          // 를 대조하므로, 그대로 두면 dev 의 시작·정지·비중 저장·파라미터 적용이 전부
          // `cross_origin` 401 이 된다(GET 폴링만 통과 = "화면은 멀쩡한데 버튼만 죽는" 형태).
          // 프록시는 서버 측 클라이언트이므로 자신이 말하는 상대(upstream)를 출처로 선언하는
          // 것이 정확하고, 이 한 줄로 dev 가 **설정 없이** 동작한다
          // (`API_ALLOWED_ORIGINS` 설정은 이 경로의 폴백이지 전제가 아니다).
          headers: {
            'X-API-Key': process.env.API_AUTH_KEY ?? '',
            Origin: apiTarget,
          },
        },
      },
    },
  }
})
