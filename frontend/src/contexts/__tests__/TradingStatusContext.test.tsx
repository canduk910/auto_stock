import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import {
  TradingStatusProvider,
  useTradingStatus,
} from "../TradingStatusContext";
import { wrap } from "../../test/factories";
import { server } from "../../test/server";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
    },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <TradingStatusProvider>{children}</TradingStatusProvider>
    </QueryClientProvider>
  );
}

describe("TradingStatusContext", () => {
  it("Provider 안에서 useTradingStatus 가 데이터를 노출한다", async () => {
    server.use(
      http.get("/api/trading/status", () =>
        HttpResponse.json(
          wrap({
            running: true,
            env: "vts",
            board: "main",
            strategies: { momentum: { enabled: true } },
          }),
        ),
      ),
    );

    const { result } = renderHook(() => useTradingStatus(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.running).toBe(true);
    expect(result.current.isLoading).toBe(false);
  });

  it("Provider 밖에서 호출하면 에러를 던진다", () => {
    expect(() => renderHook(() => useTradingStatus())).toThrow(
      /TradingStatusProvider/,
    );
  });

  it("API 가 실패하면 isError 가 true 가 된다", async () => {
    server.use(
      http.get("/api/trading/status", () => HttpResponse.error()),
    );
    const { result } = renderHook(() => useTradingStatus(), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
