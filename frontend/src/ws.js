import { useEffect, useRef, useState } from "react";
import { WS_URL, getToken } from "./api";

// Close codes the server uses for auth/ownership rejections -- reconnecting
// would just be rejected again, so don't retry these.
const NO_RETRY_CODES = new Set([1008]);
const MAX_ATTEMPTS = 8;

export function useDocumentSocket(documentId, onMessage) {
  const handlerRef = useRef(onMessage);
  handlerRef.current = onMessage;
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!documentId) return;
    let socket;
    let retryTimer;
    let attempt = 0;
    let disposed = false;

    const connect = () => {
      // token as query param: browsers can't set headers on a WS handshake
      const token = getToken();
      socket = new WebSocket(`${WS_URL}/ws/documents/${documentId}?token=${encodeURIComponent(token || "")}`);
      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
      };
      socket.onmessage = (event) => {
        try {
          handlerRef.current(JSON.parse(event.data));
        } catch (e) {
          console.error("Bad WS payload", e);
        }
      };
      socket.onclose = (event) => {
        setConnected(false);
        // A handshake rejected before accept() surfaces as 1006, not 1008,
        // so also give up after repeated failures in a row.
        if (disposed || NO_RETRY_CODES.has(event.code) || attempt >= MAX_ATTEMPTS) return;
        // The server replays completed stages on connect, so a reconnect
        // after a dropped connection (Railway proxy idle timeout, laptop
        // sleep) catches the page up without losing any stage output.
        const delay = Math.min(1000 * 2 ** attempt, 15000);
        attempt += 1;
        retryTimer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, [documentId]);

  return connected;
}
