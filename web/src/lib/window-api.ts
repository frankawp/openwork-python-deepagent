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

async function parseSSE(
  stream: ReadableStream<Uint8Array>,
  onEvent: (data: any) => void,
  signal: AbortSignal
): Promise<{ receivedTerminal: boolean }> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let receivedTerminal = false

  const processChunk = (text: string) => {
    buffer += text
    buffer = buffer.replace(/\r\n/g, "\n")
    const parts = buffer.split("\n\n")
    buffer = parts.pop() || ""

    for (const part of parts) {
      const lines = part.split("\n")
      for (const line of lines) {
        if (line.startsWith("data:")) {
          const payload = line.slice(5).trim()
          if (payload) {
            try {
              const event = JSON.parse(payload)
              if (event?.type === "done" || event?.type === "error") {
                receivedTerminal = true
              }
              onEvent(event)
            } catch {
              // ignore
            }
          }
        }
      }
    }
  }

  const abortReader = () => {
    void reader.cancel().catch(() => {})
  }
  signal.addEventListener("abort", abortReader)
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      processChunk(decoder.decode(value, { stream: true }))
      if (signal.aborted) break
    }
    processChunk(decoder.decode())
  } finally {
    signal.removeEventListener("abort", abortReader)
    reader.releaseLock()
  }
  return { receivedTerminal }
}

export function attachWindowApi() {
  const normalizeThread = (thread: any) => ({
    ...thread,
    created_at: thread?.created_at ? new Date(thread.created_at) : new Date(),
    updated_at: thread?.updated_at ? new Date(thread.updated_at) : new Date()
  })

  const normalizeSkill = (skill: any) => ({
    ...skill,
    created_at: skill?.created_at ? new Date(skill.created_at) : new Date(),
    updated_at: skill?.updated_at ? new Date(skill.updated_at) : new Date()
  })

  const normalizeSkillFile = (file: any) => ({
    ...file,
    updated_at: file?.updated_at ? new Date(file.updated_at) : new Date()
  })

  const normalizeMcp = (mcp: any) => ({
    ...mcp,
    created_at: mcp?.created_at ? new Date(mcp.created_at) : new Date(),
    updated_at: mcp?.updated_at ? new Date(mcp.updated_at) : new Date()
  })

  const streamWithSSE = async (
    endpoint: string,
    payload: Record<string, unknown>,
    onEvent: (event: unknown) => void,
    controller: AbortController,
    isAborted: () => boolean
  ) => {
    const emit = (event: unknown): void => {
      onEvent(event)
    }
    const emitError = (error: string): void => {
      emit({ type: "error", error })
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal
    })

    if (!response.ok) {
      const text = await response.text().catch(() => "")
      const statusText = text || response.statusText || "Request failed"
      emitError(`HTTP_${response.status}: ${statusText}`)
      return
    }

    if (!response.body) {
      emitError("EMPTY_STREAM_BODY")
      return
    }

    const { receivedTerminal } = await parseSSE(response.body, emit, controller.signal)
    if (!isAborted() && !receivedTerminal) {
      emitError("STREAM_CLOSED")
    }
  }

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
        modelId?: string,
        skillsEnabled?: boolean
      ) => {
        const controller = new AbortController()
        let abortedByClient = false
        streamWithSSE(
            "/agent/stream",
            {
              thread_id: threadId,
              message,
              command,
              model_id: modelId,
              skills_enabled: skillsEnabled ?? true
            },
            onEvent,
            controller,
            () => abortedByClient
          )
          .catch(() => {
            if (!abortedByClient) {
              onEvent({ type: "error", error: "STREAM_ERROR" })
            }
          })

        return () => {
          abortedByClient = true
          controller.abort()
        }
      },
      interrupt: (
        threadId: string,
        decision: Record<string, unknown>,
        onEvent: (event: unknown) => void,
        modelId?: string,
        skillsEnabled?: boolean
      ) => {
        const controller = new AbortController()
        let abortedByClient = false
        streamWithSSE(
            "/agent/interrupt",
            {
              thread_id: threadId,
              decision,
              model_id: modelId,
              skills_enabled: skillsEnabled ?? true
            },
            onEvent,
            controller,
            () => abortedByClient
          )
          .catch(() => {
            if (!abortedByClient) {
              onEvent({ type: "error", error: "STREAM_ERROR" })
            }
          })

        return () => {
          abortedByClient = true
          controller.abort()
        }
      },
      cancel: async (threadId: string) =>
        apiFetch("/agent/cancel", {
          method: "POST",
          body: JSON.stringify({ thread_id: threadId })
        })
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
    skills: {
      list: () => apiFetch("/skills").then((items: any[]) => items.map(normalizeSkill)),
      get: (skillId: string) => apiFetch(`/skills/${skillId}`).then(normalizeSkill),
      create: (payload: {
        key: string
        name: string
        description: string
        enabled?: boolean
      }) =>
        apiFetch("/skills", {
          method: "POST",
          body: JSON.stringify(payload)
        }).then(normalizeSkill),
      update: (
        skillId: string,
        payload: {
          name?: string
          description?: string
          enabled?: boolean
        }
      ) =>
        apiFetch(`/skills/${skillId}`, {
          method: "PATCH",
          body: JSON.stringify(payload)
        }).then(normalizeSkill),
      delete: (skillId: string) => apiFetch(`/skills/${skillId}`, { method: "DELETE" }),
      listFiles: (skillId: string) =>
        apiFetch(`/skills/${skillId}/files`).then((files: any[]) => files.map(normalizeSkillFile)),
      upsertFile: (skillId: string, payload: { path: string; content: string }) =>
        apiFetch(`/skills/${skillId}/files`, {
          method: "PUT",
          body: JSON.stringify(payload)
        }).then(normalizeSkillFile),
      deleteFile: (skillId: string, path: string) =>
        apiFetch(`/skills/${skillId}/files?path=${encodeURIComponent(path)}`, {
          method: "DELETE"
        })
    },
    mcps: {
      list: () => apiFetch("/mcps").then((items: any[]) => items.map(normalizeMcp)),
      get: (mcpId: string) => apiFetch(`/mcps/${mcpId}`).then(normalizeMcp),
      create: (payload: {
        key: string
        name: string
        description: string
        transport: "streamable_http" | "sse" | "stdio"
        config: Record<string, unknown>
        secret?: Record<string, unknown>
        enabled?: boolean
      }) =>
        apiFetch("/mcps", {
          method: "POST",
          body: JSON.stringify(payload)
        }).then(normalizeMcp),
      update: (
        mcpId: string,
        payload: {
          name?: string
          description?: string
          transport?: "streamable_http" | "sse" | "stdio"
          config?: Record<string, unknown>
          secret?: Record<string, unknown> | null
          enabled?: boolean
        }
      ) =>
        apiFetch(`/mcps/${mcpId}`, {
          method: "PATCH",
          body: JSON.stringify(payload)
        }).then(normalizeMcp),
      delete: (mcpId: string) => apiFetch(`/mcps/${mcpId}`, { method: "DELETE" }),
      test: (mcpId: string, threadId?: string) =>
        apiFetch(`/mcps/${mcpId}/test`, {
          method: "POST",
          body: threadId ? JSON.stringify({ thread_id: threadId }) : undefined
        })
    },
    workspace: {
      get: (threadId?: string) => {
        if (!threadId) return Promise.resolve(null)
        return apiFetch(`/workspace?thread_id=${threadId}`).then((res: any) => res.path ?? null)
      },
      // Backward-compatible alias: workspace selection is disabled for Daytona sandbox.
      select: (threadId?: string) => {
        if (!threadId) return Promise.resolve(null)
        return apiFetch(`/workspace?thread_id=${threadId}`).then((res: any) => res.path ?? null)
      },
      loadTree: (threadId: string, path: string = "/") =>
        apiFetch(
          `/workspace/tree?thread_id=${threadId}&path=${encodeURIComponent(path)}&depth=2`
        ),
      readFile: (threadId: string, filePath: string) =>
        apiFetch(`/workspace/file?thread_id=${threadId}&path=${encodeURIComponent(filePath)}`),
      readBinaryFile: (threadId: string, filePath: string) =>
        apiFetch(`/workspace/file-binary?thread_id=${threadId}&path=${encodeURIComponent(filePath)}`)
    }
  }

  ;(window as any).api = api
}
