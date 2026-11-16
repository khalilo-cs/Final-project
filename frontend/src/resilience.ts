// "Resilience mode": uploads and requests that survive weak connections and power cuts.
import { ApiError, loadTokens, request } from "./api";

const TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

/** CRC-32 in plain JavaScript: Web Crypto is unavailable on http:// LAN addresses. */
export function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) crc = TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

export const isNetworkError = (reason: unknown) => reason instanceof TypeError || (reason instanceof ApiError && reason.status >= 502 && reason.status <= 504);

/** Resolves when the browser is online again (or after `ms`, to probe a flaky link). */
export function waitForConnection(ms: number): Promise<void> {
  return new Promise((resolve) => {
    const done = () => { window.removeEventListener("online", done); window.clearTimeout(timer); resolve(); };
    const timer = window.setTimeout(done, ms);
    window.addEventListener("online", done);
  });
}

interface UploadState { id: string; offset: number; size: number; complete: boolean; chunk_size: number }
export interface Progress { sent: number; total: number; waiting: boolean }
export type UploadKind = "code" | "report" | "database";

const keyFor = (file: File, kind: UploadKind) => `aipe.upload.${kind}.${file.name}.${file.size}.${file.lastModified}`;

/**
 * Upload `file` in small pieces. A dropped connection, a closed laptop or a power cut
 * costs one piece: choosing the same file again continues where it stopped.
 */
export async function resumableUpload(file: File, kind: UploadKind, onProgress: (p: Progress) => void, signal?: AbortSignal): Promise<string> {
  const key = keyFor(file, kind);
  let state: UploadState | null = null;
  const saved = localStorage.getItem(key);
  if (saved) {
    state = await request<UploadState>("projects", `/api/v1/uploads/${saved}`).catch(() => null);
    if (state && state.size !== file.size) state = null;
  }
  if (!state) {
    state = await request<UploadState>("projects", "/api/v1/uploads", { method: "POST", body: JSON.stringify({ kind, filename: file.name, size: file.size }) });
    localStorage.setItem(key, state.id);
  }
  let offset = state.offset;
  let delay = 1000;
  onProgress({ sent: offset, total: file.size, waiting: false });
  while (offset < file.size) {
    if (signal?.aborted) throw new DOMException("cancelled", "AbortError");
    const bytes = new Uint8Array(await file.slice(offset, offset + state.chunk_size).arrayBuffer());
    try {
      const response = await fetch(`/svc/projects/api/v1/uploads/${state.id}`, {
        method: "PATCH",
        body: bytes,
        signal,
        headers: {
          Authorization: `Bearer ${loadTokens()?.access_token ?? ""}`,
          "Content-Type": "application/octet-stream",
          "Upload-Offset": String(offset),
          "X-Chunk-CRC32": String(crc32(bytes)),
        },
      });
      if (response.status === 409) {
        offset = Number(response.headers.get("Upload-Offset") ?? offset); // already received: continue
      } else if (response.status === 401) {
        await request("auth", "/api/v1/auth/me"); // refreshes the access token, then retry
      } else if (response.status === 422 || response.status >= 502) {
        throw new TypeError("retry"); // damaged in transit, or the gateway lost the service
      } else if (!response.ok) {
        throw new ApiError(response.status, (await response.json().catch(() => null))?.detail ?? `خطأ ${response.status}`);
      } else {
        offset = ((await response.json()) as UploadState).offset;
      }
      delay = 1000;
      onProgress({ sent: offset, total: file.size, waiting: false });
    } catch (reason) {
      if (!(reason instanceof TypeError)) throw reason;
      onProgress({ sent: offset, total: file.size, waiting: true });
      await waitForConnection(delay);
      delay = Math.min(delay * 2, 15000);
    }
  }
  localStorage.removeItem(key);
  return state.id;
}

/** Text the student typed, kept on this device until it is safely on the server. */
export const drafts = {
  load: (key: string) => { try { return localStorage.getItem(`aipe.draft.${key}`) ?? ""; } catch { return ""; } },
  save: (key: string, text: string) => { try { if (text) localStorage.setItem(`aipe.draft.${key}`, text); else localStorage.removeItem(`aipe.draft.${key}`); } catch { /* storage full or blocked */ } },
};
