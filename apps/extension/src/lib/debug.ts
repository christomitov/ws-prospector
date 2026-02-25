import type { DebugEntry } from "./types";

const LOCAL_BUFFER_LIMIT = 250;

interface DebugApi {
  clearLogs: () => void;
  getLogs: () => DebugEntry[];
  getSnapshot: () => unknown;
}

interface DebugWindow extends Window {
  __WSP_DEBUG__?: DebugApi;
}

const localLogBuffer: DebugEntry[] = [];

const shouldLogToConsole = (): boolean => {
  if (typeof window === "undefined") {
    return false;
  }
  const flag = (window as Window & { __WSP_VERBOSE__?: boolean }).__WSP_VERBOSE__;
  return import.meta.env.DEV || flag === true;
};

const pushLocalLog = (entry: DebugEntry): void => {
  localLogBuffer.unshift(entry);
  if (localLogBuffer.length > LOCAL_BUFFER_LIMIT) {
    localLogBuffer.length = LOCAL_BUFFER_LIMIT;
  }
};

const sendToBackground = (entry: DebugEntry): void => {
  if (typeof chrome === "undefined" || !chrome.runtime?.sendMessage) {
    return;
  }

  chrome.runtime.sendMessage({ type: "DEBUG_EVENT", entry }, () => {
    void chrome.runtime.lastError;
  });
};

export const debugLog = (scope: string, event: string, details?: unknown): void => {
  const entry: DebugEntry = {
    timestamp: new Date().toISOString(),
    scope,
    event,
    ...(details ? { details } : {}),
  };

  if (shouldLogToConsole()) {
    console.info(`[WSP][${scope}] ${event}`, details ?? "");
  }
  pushLocalLog(entry);
  sendToBackground(entry);
};

export const installDebugApi = (getSnapshot: () => unknown): void => {
  if (typeof window === "undefined") {
    return;
  }

  const debugWindow = window as DebugWindow;
  debugWindow.__WSP_DEBUG__ = {
    getSnapshot,
    getLogs: () => [...localLogBuffer],
    clearLogs: () => {
      localLogBuffer.length = 0;
    },
  };
};
