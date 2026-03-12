import { describe, expect, it, vi, beforeEach } from "vitest";
import { WsClient } from "../ws-client";

// Mock WebSocket
class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  send = vi.fn();
  close = vi.fn();
}

describe("WsClient", () => {
  let client: WsClient;

  beforeEach(() => {
    client = new WsClient();
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  it("starts with disconnected status", () => {
    expect(client.status).toBe("disconnected");
  });

  it("transitions to connecting on connect()", () => {
    client.connect();
    expect(client.status).toBe("connecting");
  });

  it("subscribe returns unsubscribe function", () => {
    const handler = vi.fn();
    const unsub = client.subscribe("ticker", handler);
    expect(typeof unsub).toBe("function");
    unsub();
  });

  it("notifies status listeners", () => {
    const listener = vi.fn();
    client.onStatusChange(listener);
    client.connect();
    expect(listener).toHaveBeenCalledWith("connecting");
  });

  it("unsubscribe removes listener", () => {
    const listener = vi.fn();
    const unsub = client.onStatusChange(listener);
    unsub();
    client.connect();
    expect(listener).not.toHaveBeenCalled();
  });

  it("disconnect sets status to disconnected", () => {
    client.connect();
    client.disconnect();
    expect(client.status).toBe("disconnected");
  });
});
