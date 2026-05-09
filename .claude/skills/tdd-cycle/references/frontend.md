# 프론트엔드 TDD 패턴 (vitest + RTL + MSW)

## 의존성 주입 fixture (src/test/setup.ts 핵심)

- `@testing-library/jest-dom` 매처 등록
- MSW 서버 부트 (`server.listen({ onUnhandledRequest: "error" })`)
- 각 테스트 후 `server.resetHandlers()` + `cleanup()`
- afterAll: `server.close()`

## 핸들러 표준 (src/test/handlers.ts)

19개 엔드포인트의 기본 응답을 정의한다. 각 테스트는 필요 시 `server.use(http.get('/api/balance', ...))`로 오버라이드.

```ts
import { http, HttpResponse } from "msw";
import { wrap } from "./factories";

export const handlers = [
  http.get("/api/balance", () => HttpResponse.json(wrap({
    positions: [], total_eval: 0, deposit: 10000000
  }))),
  http.get("/api/trading/status", () => HttpResponse.json(wrap({
    is_running: false, board: "main"
  }))),
  // ... 19개
];
```

## 컴포넌트 테스트 패턴

### 사용자 관점 우선
- `screen.getByRole`, `getByText`, `getByLabelText` 사용
- `getByTestId`는 최후의 수단
- 내부 state, props 직접 검증 ❌

```tsx
test("ControlPanel — 매매 시작 버튼 클릭 시 이중확인 모달이 뜬다", async () => {
  render(<ControlPanel />, { wrapper: TestProviders });
  await userEvent.click(screen.getByRole("button", { name: "매매 시작" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("정말 시작하시겠습니까");
});
```

### TestProviders 헬퍼
```tsx
export function TestProviders({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <TradingStatusProvider>
        {children}
      </TradingStatusProvider>
    </QueryClientProvider>
  );
}
```

## 훅 테스트 패턴

`@testing-library/react`의 `renderHook` + MSW로 API 격리.

```tsx
test("useTradingStatus polls every 5s and exposes is_running", async () => {
  server.use(
    http.get("/api/trading/status", () => HttpResponse.json(wrap({ is_running: true })))
  );
  const { result } = renderHook(() => useTradingStatus(), { wrapper: TestProviders });
  await waitFor(() => expect(result.current.is_running).toBe(true));
});
```

## API 계약 테스트 패턴

`src/api/*.ts`에서 axios 호출이 응답을 올바르게 unwrap하는지 + 에러 처리.

```tsx
test("balance.get unwraps ApiResponse and returns data", async () => {
  server.use(http.get("/api/balance", () => HttpResponse.json(
    wrap({ positions: [{ ticker: "005930", qty: 10 }] })
  )));
  const data = await balance.get();
  expect(data.positions[0].ticker).toBe("005930");
});
```

## E2E (Playwright)

`e2e/`는 진짜 브라우저 + 백엔드 모의(또는 실제 dev server). 4개 시나리오만 유지하고 나머지는 컴포넌트/훅 단위로 흡수.

```ts
test("Trading flow — 시작 → 감시 → 정지", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "매매 시작" }).click();
  await page.getByRole("button", { name: "확인" }).click();
  await expect(page.getByText("매매 진행 중")).toBeVisible();
  // ...
  await page.getByRole("button", { name: "매매 정지" }).click();
  await page.getByRole("button", { name: "확인" }).click();
  await expect(page.getByText("매매 중지됨")).toBeVisible();
});
```

## 흔한 함정

| 함정 | 해결 |
|------|------|
| `act()` 경고 | userEvent는 자동 처리 — fireEvent 대신 userEvent 사용 |
| Query cache가 테스트 간 공유 | TestProviders에서 매번 새 QueryClient 생성 |
| MSW 핸들러 누락 → 실제 네트워크 호출 | `onUnhandledRequest: "error"`로 즉시 실패 |
| `waitFor` 안에 expect 여러 개 | 한 expect당 한 waitFor — 디버깅 쉬움 |
| `screen.debug()` 남발 | CI 로그 오염 — 작성 후 제거 |
