import { getWsUrl } from "./constants";

export type WsStatus = "connecting" | "connected" | "reconnecting" | "disconnected";
type MessageHandler = (data: unknown) => void;

const HEARTBEAT_INTERVAL = 30_000;
const RECONNECT_BASE_DELAY = 1_000;
const RECONNECT_MAX_DELAY = 30_000;

export class WsClient {
  private ws: WebSocket | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private subscriptions = new Map<string, Set<MessageHandler>>();
  private statusListeners = new Set<(status: WsStatus) => void>();
  private _status: WsStatus = "disconnected";

  get status(): WsStatus {
    return this._status;
  }

  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) return;
    this.setStatus("connecting");

    try {
      this.ws = new WebSocket(getWsUrl());
      this.ws.onopen = this.handleOpen;
      this.ws.onmessage = this.handleMessage;
      this.ws.onclose = this.handleClose;
      this.ws.onerror = this.handleError;
    } catch {
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.clearTimers();
    this.reconnectAttempt = 0;
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
    this.setStatus("disconnected");
  }

  subscribe(channel: string, handler: MessageHandler): () => void {
    if (!this.subscriptions.has(channel)) {
      this.subscriptions.set(channel, new Set());
      this.sendSubscribe(channel);
    }
    this.subscriptions.get(channel)!.add(handler);

    return () => {
      const handlers = this.subscriptions.get(channel);
      if (handlers) {
        handlers.delete(handler);
        if (handlers.size === 0) {
          this.subscriptions.delete(channel);
          this.sendUnsubscribe(channel);
        }
      }
    };
  }

  onStatusChange(listener: (status: WsStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  private handleOpen = (): void => {
    this.reconnectAttempt = 0;
    this.setStatus("connected");
    this.startHeartbeat();
    // Re-subscribe to all channels
    for (const channel of this.subscriptions.keys()) {
      this.sendSubscribe(channel);
    }
  };

  private handleMessage = (event: MessageEvent): void => {
    try {
      const msg = JSON.parse(event.data as string) as {
        channel?: string;
        type?: string;
        payload?: unknown;
        ts?: number;
      };
      if (msg.type === "ping") {
        // Respond with pong
        this.ws?.send(JSON.stringify({ type: "pong" }));
        return;
      }
      if (msg.type === "pong") return;

      if (msg.type === "data" && msg.channel && this.subscriptions.has(msg.channel)) {
        for (const handler of this.subscriptions.get(msg.channel)!) {
          handler(msg.payload);
        }
      }
    } catch {
      // Ignore parse errors
    }
  };

  private handleClose = (): void => {
    this.clearTimers();
    this.scheduleReconnect();
  };

  private handleError = (): void => {
    this.ws?.close();
  };

  private scheduleReconnect(): void {
    this.setStatus("reconnecting");
    const delay = Math.min(
      RECONNECT_BASE_DELAY * 2 ** this.reconnectAttempt,
      RECONNECT_MAX_DELAY,
    );
    this.reconnectAttempt++;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  private startHeartbeat(): void {
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_INTERVAL);
  }

  private clearTimers(): void {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.heartbeatTimer = null;
    this.reconnectTimer = null;
  }

  private sendSubscribe(channel: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "subscribe", channels: [channel] }));
    }
  }

  private sendUnsubscribe(channel: string): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "unsubscribe", channels: [channel] }));
    }
  }

  private setStatus(status: WsStatus): void {
    this._status = status;
    for (const listener of this.statusListeners) {
      listener(status);
    }
  }
}

export const wsClient = new WsClient();
