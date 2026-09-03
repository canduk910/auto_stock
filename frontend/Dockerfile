FROM node:22-alpine AS base

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install

# --- Development (소스는 볼륨 마운트) ---
FROM base AS dev
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--host"]

# --- Build ---
FROM base AS build
COPY . .
RUN npm run build

# --- Production (Nginx 정적 서빙 + API 리버스 프록시) ---
FROM nginx:alpine AS prod
COPY --from=build /app/dist /usr/share/nginx/html
# cycle243 — envsubst 템플릿. `nginx:alpine` 엔트리포인트가 시작 시
# `/etc/nginx/templates/*.template` → `/etc/nginx/conf.d/` 로 렌더한다.
# 파일명이 `default.conf.template` 이어야 스톡 `default.conf` 를 덮어쓴다.
# 구 `COPY nginx.conf /etc/nginx/conf.d/default.conf` 를 되살리지 말 것 —
# 템플릿 렌더가 건너뛰어질 때 **인증 없는 구버전이 조용히 서빙되는 fail-open** 이 된다.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 80
