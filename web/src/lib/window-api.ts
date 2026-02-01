/* eslint-disable @typescript-eslint/no-explicit-any */

const API_BASE = (() => {
  if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL
  if (!import.meta.env.DEV) return ""
  const host = window.location.hostname
  if (host === "localhost") return "http://localhost:8000"
  return "http://127.0.0.1:8000"
})()

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  })

  if (!res.ok) {
    const text = await res.text()
    const error = new Error(text || `Request failed: ${res.status}`)
    ;(error as any).status = res.status
    throw error
  }
  if (res.status === 204) {
    return {} as T
  }
  return (await res.json()) as T
}

function parseSSE(stream: ReadableStream<Uint8Array>, onEvent: (data: any) => void) {
  const reader = stream.getReader()
  let buffer = ""

  function processChunk(text: string) {
    buffer += text
    const parts = buffer.split("\n\n")
    buffer = parts.pop() || ""

    for (const part of parts) {
      const lines = part.split("\n")
      for (const line of lines) {
        if (line.startsWith("data:")) {
          const payload = line.slice(5).trim()
          if (payload) {
            try {
              onEvent(JSON.parse(payload))
            } catch {
              // ignore
            }
          }
        }
      }
    }
  }

  function read() {
    reader.read().then(({ done, value }) => {
      if (done) return
      const text = new TextDecoder().decode(value)
      processChunk(text)
      read()
    })
  }

  read()
  return () => reader.cancel()
}

export function attachWindowApi() {
  const normalizeThread = (thread: any) => ({
    ...thread,
    created_at: thread?.created_at ? new Date(thread.created_at) : new Date(),
    updated_at: thread?.updated_at ? new Date(thread.updated_at) : new Date()
  })

  const api = {
    auth: {
      login: (email: string, password: string) =>
        apiFetch("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
      logout: () => apiFetch("/auth/logout", { method: "POST" }),
      refresh: () => apiFetch("/auth/refresh", { method: "POST" })
    },
    agent: {
      streamAgent: (
        threadId: string,
        message: string,
        command: unknown,
        onEvent: (event: unknown) => void,
        modelId?: string
      ) => {
        const controller = new AbortController()
        fetch(`${API_BASE}/agent/stream`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            thread_id: threadId,
            message,
            command,
            model_id: modelId
          }),
          signal: controller.signal
        })
          .then((res) => {
            if (!res.body) return
            const cleanup = parseSSE(res.body, (data) => onEvent(data))
            // tie cleanup to abort
            controller.signal.addEventListener("abort", () => cleanup())
          })
          .catch(() => {
            onEvent({ type: "error", error: "STREAM_ERROR" })
          })

        return () => controller.abort()
      },
      cancel: async (_threadId: string) => {
        return
      }
    },
    threads: {
      list: () => apiFetch("/threads").then((items: any[]) => items.map(normalizeThread)),
      get: (threadId: string) => apiFetch(`/threads/${threadId}`).then(normalizeThread),
      create: (metadata?: Record<string, unknown>) =>
        apiFetch("/threads", {
          method: "POST",
          body: JSON.stringify({
            title: typeof metadata?.title === "string" ? metadata.title : undefined,
            metadata: metadata || {}
          })
        }).then(normalizeThread),
      update: (threadId: string, updates: Record<string, unknown>) =>
        apiFetch(`/threads/${threadId}`, { method: "PATCH", body: JSON.stringify(updates) }).then(
          normalizeThread
        ),
      delete: (threadId: string) => apiFetch(`/threads/${threadId}`, { method: "DELETE" }),
      getHistory: (threadId: string) => apiFetch(`/threads/${threadId}/history`),
      generateTitle: (message: string) =>
        apiFetch("/threads/generate-title", {
          method: "POST",
          body: JSON.stringify({ message })
        }).then((res: any) => (typeof res === "string" ? res : res.title))
    },
    models: {
      list: () => apiFetch("/models"),
      listProviders: () => apiFetch("/models/providers"),
      getDefault: () => apiFetch("/models/default").then((res: any) => res.model_id),
      setDefault: (modelId: string) =>
        apiFetch("/models/default", { method: "POST", body: JSON.stringify({ model_id: modelId }) }),
      setApiKey: (provider: string, apiKey: string) =>
        apiFetch("/models/api-key", { method: "POST", body: JSON.stringify({ provider, apiKey }) }),
      getApiKey: (provider: string) => apiFetch(`/models/api-key/${provider}`),
      deleteApiKey: (provider: string) => apiFetch(`/models/api-key/${provider}`, { method: "DELETE" })
    },
    workspace: {
      get: (_threadId?: string) => apiFetch("/workspace").then((res: any) => res.path ?? null),
      select: (_threadId?: string) => apiFetch("/workspace").then((res: any) => res.path ?? null),
      loadFromDisk: (threadId: string) => apiFetch(`/workspace/files?thread_id=${threadId}`),
      readFile: (threadId: string, filePath: string) =>
        apiFetch(`/workspace/file?thread_id=${threadId}&path=${encodeURIComponent(filePath)}`),
      readBinaryFile: (threadId: string, filePath: string) =>
        apiFetch(`/workspace/file-binary?thread_id=${threadId}&path=${encodeURIComponent(filePath)}`),
      onFilesChanged: (callback: (data: { threadId: string; workspacePath: string }) => void) => {
        const threadId = "default"
        const source = new EventSource(`${API_BASE}/workspace/changes?thread_id=${threadId}`, {
          withCredentials: true
        })
        source.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data) as { threadId?: string; workspacePath?: string }
            if (payload.workspacePath) {
              callback({
                threadId: payload.threadId || threadId,
                workspacePath: payload.workspacePath
              })
              return
            }
          } catch {
            // fallback
          }
          apiFetch("/workspace").then((data: { path: string }) => {
            callback({ threadId, workspacePath: data.path })
          })
        }
        return () => source.close()
      }
    }
  }

  ;(window as any).api = api
}
