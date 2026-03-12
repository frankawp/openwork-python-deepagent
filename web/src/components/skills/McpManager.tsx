import { useCallback, useEffect, useMemo, useState } from "react"
import { Cable, FlaskConical, Plus, RefreshCw, Save, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useAppStore } from "@/lib/store"
import { cn } from "@/lib/utils"
import type { MCPServer, MCPServerTestResult, MCPTransport } from "@/types"

const TRANSPORT_OPTIONS: MCPTransport[] = ["streamable_http", "sse", "stdio"]

function deriveNewMcpKey(mcps: MCPServer[]): string {
  const prefix = "mcp"
  let idx = mcps.length + 1
  while (mcps.some((mcp) => mcp.key === `${prefix}-${idx}`)) {
    idx += 1
  }
  return `${prefix}-${idx}`
}

function defaultConfigForTransport(transport: MCPTransport): string {
  if (transport === "stdio") {
    return JSON.stringify({ command: "npx", args: ["-y", "@modelcontextprotocol/server-filesystem"] }, null, 2)
  }
  return JSON.stringify({ url: "http://127.0.0.1:8001/mcp" }, null, 2)
}

function defaultSecretForTransport(transport: MCPTransport): string {
  if (transport === "stdio") {
    return JSON.stringify({ env: {} }, null, 2)
  }
  return JSON.stringify({ headers: {} }, null, 2)
}

function prettyJson(value: unknown): string {
  if (!value || typeof value !== "object") return "{}"
  return JSON.stringify(value, null, 2)
}

function parseJsonObject(
  input: string,
  field: string,
  allowEmpty: boolean
): Record<string, unknown> | null {
  const text = input.trim()
  if (!text) {
    if (allowEmpty) return null
    throw new Error(`${field} is required`)
  }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error(`${field} must be valid JSON`)
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`${field} must be a JSON object`)
  }
  return parsed as Record<string, unknown>
}

export function McpManager(): React.JSX.Element {
  const { currentThreadId } = useAppStore()
  const [mcps, setMcps] = useState<MCPServer[]>([])
  const [selectedMcpId, setSelectedMcpId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<MCPServerTestResult | null>(null)

  const [newMcpKey, setNewMcpKey] = useState("")
  const [newMcpName, setNewMcpName] = useState("")
  const [newMcpDescription, setNewMcpDescription] = useState("")
  const [newTransport, setNewTransport] = useState<MCPTransport>("streamable_http")
  const [newConfigDraft, setNewConfigDraft] = useState(defaultConfigForTransport("streamable_http"))
  const [newSecretDraft, setNewSecretDraft] = useState(defaultSecretForTransport("streamable_http"))

  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [editTransport, setEditTransport] = useState<MCPTransport>("streamable_http")
  const [editConfigDraft, setEditConfigDraft] = useState("{}")
  const [editSecretDraft, setEditSecretDraft] = useState("")

  const selectedMcp = useMemo(
    () => mcps.find((mcp) => mcp.id === selectedMcpId) || null,
    [mcps, selectedMcpId]
  )

  const loadMcps = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await window.api.mcps.list()
      setMcps(result)
      if (!selectedMcpId && result.length > 0) {
        setSelectedMcpId(result[0].id)
      } else if (selectedMcpId && !result.some((mcp: MCPServer) => mcp.id === selectedMcpId)) {
        setSelectedMcpId(result[0]?.id || null)
      }
      if (!newMcpKey) {
        setNewMcpKey(deriveNewMcpKey(result))
      }
    } catch (e) {
      setError((e as Error).message || "Failed to load MCP servers")
    } finally {
      setLoading(false)
    }
  }, [selectedMcpId, newMcpKey])

  useEffect(() => {
    void loadMcps()
  }, [loadMcps])

  useEffect(() => {
    if (!selectedMcp) {
      setEditName("")
      setEditDescription("")
      setEditTransport("streamable_http")
      setEditConfigDraft("{}")
      setEditSecretDraft("")
      setTestResult(null)
      return
    }
    setEditName(selectedMcp.name)
    setEditDescription(selectedMcp.description)
    setEditTransport(selectedMcp.transport)
    setEditConfigDraft(prettyJson(selectedMcp.config))
    setEditSecretDraft("")
    setTestResult(null)
  }, [selectedMcp])

  useEffect(() => {
    setNewConfigDraft(defaultConfigForTransport(newTransport))
    setNewSecretDraft(defaultSecretForTransport(newTransport))
  }, [newTransport])

  const handleCreateMcp = async (): Promise<void> => {
    if (!newMcpKey.trim() || !newMcpName.trim() || !newMcpDescription.trim()) return
    setSaving(true)
    setError(null)
    try {
      const config = parseJsonObject(newConfigDraft, "Config", false)
      const secret = parseJsonObject(newSecretDraft, "Secret", true)
      const created = await window.api.mcps.create({
        key: newMcpKey.trim(),
        name: newMcpName.trim(),
        description: newMcpDescription.trim(),
        transport: newTransport,
        config: config || {},
        secret: secret || undefined,
        enabled: true
      })
      await loadMcps()
      setSelectedMcpId(created.id)
      setNewMcpKey(deriveNewMcpKey([...mcps, created]))
      setNewMcpName("")
      setNewMcpDescription("")
    } catch (e) {
      setError((e as Error).message || "Failed to create MCP server")
    } finally {
      setSaving(false)
    }
  }

  const handleSaveMcp = async (): Promise<void> => {
    if (!selectedMcp) return
    setSaving(true)
    setError(null)
    try {
      const config = parseJsonObject(editConfigDraft, "Config", false)
      const nextSecret = editSecretDraft.trim()
        ? parseJsonObject(editSecretDraft, "Secret", false)
        : undefined
      const updated = await window.api.mcps.update(selectedMcp.id, {
        name: editName.trim(),
        description: editDescription.trim(),
        transport: editTransport,
        config: config || {},
        secret: nextSecret,
        enabled: selectedMcp.enabled
      })
      setMcps((prev) => prev.map((mcp) => (mcp.id === updated.id ? updated : mcp)))
    } catch (e) {
      setError((e as Error).message || "Failed to save MCP server")
    } finally {
      setSaving(false)
    }
  }

  const handleToggleEnabled = async (): Promise<void> => {
    if (!selectedMcp) return
    setSaving(true)
    setError(null)
    try {
      const updated = await window.api.mcps.update(selectedMcp.id, {
        enabled: !selectedMcp.enabled
      })
      setMcps((prev) => prev.map((mcp) => (mcp.id === updated.id ? updated : mcp)))
    } catch (e) {
      setError((e as Error).message || "Failed to update MCP status")
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteMcp = async (): Promise<void> => {
    if (!selectedMcp) return
    if (!window.confirm(`Delete MCP server "${selectedMcp.name}"?`)) return
    setSaving(true)
    setError(null)
    try {
      await window.api.mcps.delete(selectedMcp.id)
      await loadMcps()
    } catch (e) {
      setError((e as Error).message || "Failed to delete MCP server")
    } finally {
      setSaving(false)
    }
  }

  const handleTestMcp = async (): Promise<void> => {
    if (!selectedMcp) return
    setTesting(true)
    setError(null)
    setTestResult(null)
    try {
      const result = await window.api.mcps.test(selectedMcp.id, currentThreadId || undefined)
      setTestResult(result)
    } catch (e) {
      setError((e as Error).message || "Failed to test MCP server")
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <aside className="flex w-80 shrink-0 flex-col border-r border-border bg-sidebar">
        <div className="space-y-2 border-b border-border p-3">
          <div className="text-sm font-medium">MCP Servers</div>
          <Input value={newMcpKey} onChange={(e) => setNewMcpKey(e.target.value)} placeholder="mcp-key" />
          <Input
            value={newMcpName}
            onChange={(e) => setNewMcpName(e.target.value)}
            placeholder="MCP server name"
          />
          <Input
            value={newMcpDescription}
            onChange={(e) => setNewMcpDescription(e.target.value)}
            placeholder="Short description"
          />
          <select
            value={newTransport}
            onChange={(e) => setNewTransport(e.target.value as MCPTransport)}
            className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
          >
            {TRANSPORT_OPTIONS.map((transport) => (
              <option key={transport} value={transport}>
                {transport}
              </option>
            ))}
          </select>
          <textarea
            value={newConfigDraft}
            onChange={(e) => setNewConfigDraft(e.target.value)}
            className="h-24 w-full resize-none rounded-md border border-input bg-transparent p-2 text-xs font-mono"
            placeholder='{"url":"http://127.0.0.1:8001/mcp"}'
          />
          <textarea
            value={newSecretDraft}
            onChange={(e) => setNewSecretDraft(e.target.value)}
            className="h-20 w-full resize-none rounded-md border border-input bg-transparent p-2 text-xs font-mono"
            placeholder='{"headers":{"Authorization":"Bearer ..." }}'
          />
          <Button
            size="sm"
            className="w-full justify-start gap-2"
            onClick={() => void handleCreateMcp()}
            disabled={saving}
          >
            <Plus className="size-4" />
            Install MCP
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="w-full justify-start gap-2"
            onClick={() => void loadMcps()}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
        <ScrollArea className="min-h-0 flex-1">
          <div className="space-y-1 p-2">
            {mcps.map((mcp) => (
              <button
                key={mcp.id}
                className={cn(
                  "w-full rounded-sm border border-transparent px-2 py-2 text-left text-sm hover:border-border",
                  selectedMcpId === mcp.id && "border-border bg-sidebar-accent"
                )}
                onClick={() => setSelectedMcpId(mcp.id)}
              >
                <div className="flex items-center gap-2">
                  <Cable className="size-3.5 shrink-0 text-muted-foreground" />
                  <div className="truncate font-medium">{mcp.name}</div>
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {mcp.key} · {mcp.transport}
                </div>
              </button>
            ))}
            {mcps.length === 0 && <div className="px-2 py-8 text-xs text-muted-foreground">No MCP servers yet.</div>}
          </div>
        </ScrollArea>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col">
        {!selectedMcp ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Select or install an MCP server.
          </div>
        ) : (
          <>
            <div className="space-y-2 border-b border-border p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium">{selectedMcp.key}</div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => void handleToggleEnabled()} disabled={saving}>
                    {selectedMcp.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button size="sm" variant="destructive" onClick={() => void handleDeleteMcp()} disabled={saving}>
                    <Trash2 className="mr-1 size-4" />
                    Uninstall
                  </Button>
                </div>
              </div>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
              <Input value={editDescription} onChange={(e) => setEditDescription(e.target.value)} />
              <select
                value={editTransport}
                onChange={(e) => setEditTransport(e.target.value as MCPTransport)}
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
              >
                {TRANSPORT_OPTIONS.map((transport) => (
                  <option key={transport} value={transport}>
                    {transport}
                  </option>
                ))}
              </select>
              <div className="grid min-h-0 flex-1 grid-cols-2 gap-3">
                <textarea
                  value={editConfigDraft}
                  onChange={(e) => setEditConfigDraft(e.target.value)}
                  className="h-40 w-full resize-none rounded-md border border-input bg-transparent p-2 text-xs font-mono"
                  placeholder='{"url":"http://127.0.0.1:8001/mcp"}'
                />
                <textarea
                  value={editSecretDraft}
                  onChange={(e) => setEditSecretDraft(e.target.value)}
                  className="h-40 w-full resize-none rounded-md border border-input bg-transparent p-2 text-xs font-mono"
                  placeholder='Leave empty to keep current secret; or set {"headers":{"Authorization":"Bearer ..."}}'
                />
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={() => void handleSaveMcp()} className="gap-2" disabled={saving}>
                  <Save className="size-4" />
                  Save MCP
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void handleTestMcp()}
                  className="gap-2"
                  disabled={testing}
                >
                  <FlaskConical className="size-4" />
                  {testing ? "Testing..." : "Test Connection"}
                </Button>
              </div>
              {testResult && (
                <div
                  className={cn(
                    "rounded-md border px-3 py-2 text-xs",
                    testResult.success
                      ? "border-status-nominal/35 bg-status-nominal/10 text-status-nominal"
                      : "border-status-critical/35 bg-status-critical/10 text-status-critical"
                  )}
                >
                  <div>{testResult.message}</div>
                  {testResult.success && (
                    <div className="mt-1 text-muted-foreground">
                      Tools ({testResult.tool_count}):{" "}
                      {testResult.tools.length > 0 ? testResult.tools.join(", ") : "none"}
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
        {error && <div className="border-t border-border px-3 py-2 text-xs text-status-critical">{error}</div>}
      </section>
    </div>
  )
}
