import { useState } from "react"
import {
  Plus,
  MessageSquare,
  Trash2,
  Pencil,
  Loader2,
  LayoutGrid,
  AlertCircle,
  Wrench
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useAppStore } from "@/lib/store"
import { useThreadStream, useThreadContext } from "@/lib/thread-context"
import { cn, formatRelativeTime, truncate } from "@/lib/utils"
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger
} from "@/components/ui/context-menu"
import type { Thread } from "@/types"

// Thread status indicator that shows loading, interrupted, or default state
function ThreadStatusIcon({ threadId }: { threadId: string }): React.JSX.Element {
  const { isLoading } = useThreadStream(threadId)
  const { getThreadState } = useThreadContext()
  const { pendingApproval } = getThreadState(threadId)

  if (isLoading) {
    return <Loader2 className="size-4 shrink-0 text-status-info animate-spin" />
  }
  
  if (pendingApproval) {
    return <AlertCircle className="size-4 shrink-0 text-status-warning" />
  }
  
  return <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
}

// Individual thread list item component
function ThreadListItem({
  thread,
  isSelected,
  isEditing,
  editingTitle,
  disabled = false,
  isDeleting = false,
  onSelect,
  onDelete,
  onStartEditing,
  onSaveTitle,
  onCancelEditing,
  onEditingTitleChange
}: {
  thread: Thread
  isSelected: boolean
  isEditing: boolean
  editingTitle: string
  disabled?: boolean
  isDeleting?: boolean
  onSelect: () => void
  onDelete: () => void
  onStartEditing: () => void
  onSaveTitle: () => void
  onCancelEditing: () => void
  onEditingTitleChange: (value: string) => void
}): React.JSX.Element {
  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div
          className={cn(
            "group flex cursor-pointer items-center gap-2 overflow-hidden rounded-lg border border-transparent px-3 py-2.5 transition-all",
            disabled && "cursor-not-allowed opacity-65",
            isDeleting && "border-status-info/35 bg-status-info/10",
            isSelected
              ? "border-primary/30 bg-sidebar-accent/95 text-sidebar-accent-foreground shadow-[0_4px_10px_rgba(15,23,42,0.08)]"
              : "hover:border-border/70 hover:bg-sidebar-accent/55"
          )}
          onClick={() => {
            if (!isEditing && !disabled) {
              onSelect()
            }
          }}
          onContextMenu={(e) => {
            if (disabled) {
              e.preventDefault()
              e.stopPropagation()
            }
          }}
          aria-disabled={disabled}
        >
          {isDeleting ? (
            <Loader2 className="size-4 shrink-0 text-status-info animate-spin" />
          ) : (
            <ThreadStatusIcon threadId={thread.thread_id} />
          )}
          <div className="flex-1 min-w-0 overflow-hidden">
            {isEditing ? (
              <input
                type="text"
                value={editingTitle}
                onChange={(e) => onEditingTitleChange(e.target.value)}
                onBlur={onSaveTitle}
                onKeyDown={(e) => {
                  if (e.key === "Enter") onSaveTitle()
                  if (e.key === "Escape") onCancelEditing()
                }}
                className="w-full rounded-md border border-border bg-background/80 px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-ring/60"
                autoFocus
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <>
                <div className="text-sm truncate block">
                  {thread.title || truncate(thread.thread_id, 20)}
                </div>
                <div className="text-[10px] text-muted-foreground truncate">
                  {isDeleting ? "Deleting thread..." : formatRelativeTime(thread.updated_at)}
                </div>
              </>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            className="shrink-0 opacity-0 group-hover:opacity-100"
            onClick={(e) => {
              if (disabled) return
              e.stopPropagation()
              onDelete()
            }}
            disabled={disabled}
          >
            <Trash2 className="size-3" />
          </Button>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem onClick={onStartEditing} disabled={disabled}>
          <Pencil className="size-4 mr-2" />
          Rename
        </ContextMenuItem>
        <ContextMenuSeparator />
        <ContextMenuItem variant="destructive" onClick={onDelete} disabled={disabled}>
          <Trash2 className="size-4 mr-2" />
          Delete
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}

export function ThreadSidebar(): React.JSX.Element {
  const {
    threads,
    currentThreadId,
    createThread,
    selectThread,
    deleteThread,
    updateThread,
    setShowKanbanView,
    setShowSkillsView,
    showSkillsView,
    showKanbanView,
    threadCreation
  } = useAppStore()

  const [editingThreadId, setEditingThreadId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState("")
  const [deletingThreadId, setDeletingThreadId] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const startEditing = (threadId: string, currentTitle: string): void => {
    setEditingThreadId(threadId)
    setEditingTitle(currentTitle || "")
  }

  const saveTitle = async (): Promise<void> => {
    if (editingThreadId && editingTitle.trim()) {
      await updateThread(editingThreadId, { title: editingTitle.trim() })
    }
    setEditingThreadId(null)
    setEditingTitle("")
  }

  const cancelEditing = (): void => {
    setEditingThreadId(null)
    setEditingTitle("")
  }

  const handleNewThread = async (): Promise<void> => {
    setDeleteError(null)
    try {
      await createThread({ title: `Thread ${new Date().toLocaleDateString()}` })
    } catch (error) {
      console.error("[ThreadSidebar] Failed to create thread:", error)
    }
  }

  const handleDeleteThread = async (threadId: string): Promise<void> => {
    if (deletingThreadId) return
    setDeleteError(null)
    setDeletingThreadId(threadId)
    if (editingThreadId === threadId) {
      cancelEditing()
    }
    try {
      await deleteThread(threadId)
    } catch (error) {
      const message = (error as { message?: string })?.message || "Failed to delete thread. Please retry."
      console.error("[ThreadSidebar] Failed to delete thread:", error)
      setDeleteError(message)
    } finally {
      setDeletingThreadId(null)
    }
  }

  const isCreating = threadCreation.status === "creating"
  const isDeleting = deletingThreadId !== null
  const isBusy = isCreating || isDeleting
  const hasCreateError = threadCreation.status === "failed"

  return (
    <aside className="flex h-full w-full flex-col overflow-hidden border-r border-border/70 bg-sidebar/96 backdrop-blur-xl">
      {/* New Thread Button - with dynamic safe area padding when zoomed out */}
      <div className="space-y-2 p-3" style={{ paddingTop: "calc(10px + var(--sidebar-safe-padding, 0px))" }}>
        <div className="px-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Threads
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-9 w-full justify-start gap-2 border-border/80 bg-background/45 text-foreground hover:bg-background-interactive/75"
          onClick={handleNewThread}
          disabled={isBusy}
        >
          {isCreating ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
          {isCreating ? "Preparing thread..." : "New Thread"}
        </Button>
      </div>

      {/* Thread List */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="space-y-1 overflow-hidden px-3 pb-3">
          {isCreating && (
            <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-sidebar-accent/50 px-3 py-2.5 text-sidebar-foreground">
              <Loader2 className="size-4 shrink-0 text-status-info animate-spin" />
              <div className="min-w-0">
                <div className="text-sm truncate">Preparing thread...</div>
                <div className="text-[10px] text-muted-foreground truncate">
                  Initializing sandbox workspace
                </div>
              </div>
            </div>
          )}

          {hasCreateError && (
            <div className="rounded-lg border border-status-critical/35 bg-status-critical/10 px-3 py-2.5">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-status-critical" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-status-critical">Thread creation failed</div>
                  <div className="text-[10px] text-muted-foreground truncate">
                    {threadCreation.error || "Please retry"}
                  </div>
                </div>
                <Button size="sm" variant="outline" className="h-6 px-2 text-xs" onClick={handleNewThread}>
                  Retry
                </Button>
              </div>
            </div>
          )}

          {deleteError && !isDeleting && (
            <div className="rounded-lg border border-status-critical/35 bg-status-critical/10 px-3 py-2.5">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-status-critical" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-status-critical">Thread deletion failed</div>
                  <div className="text-[10px] text-muted-foreground truncate">{deleteError}</div>
                </div>
              </div>
            </div>
          )}

          {threads.map((thread) => (
            <ThreadListItem
              key={thread.thread_id}
              thread={thread}
              isSelected={currentThreadId === thread.thread_id}
              isEditing={editingThreadId === thread.thread_id}
              editingTitle={editingTitle}
              disabled={isBusy}
              isDeleting={deletingThreadId === thread.thread_id}
              onSelect={() => selectThread(thread.thread_id)}
              onDelete={() => handleDeleteThread(thread.thread_id)}
              onStartEditing={() => startEditing(thread.thread_id, thread.title || "")}
              onSaveTitle={saveTitle}
              onCancelEditing={cancelEditing}
              onEditingTitleChange={setEditingTitle}
            />
          ))}

          {threads.length === 0 && !isCreating && (
            <div className="rounded-lg border border-dashed border-border/70 px-3 py-8 text-center text-sm text-muted-foreground">
              No threads yet
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Overview Toggle */}
      <div className="border-t border-border/70 p-3">
        <Button
          variant="ghost"
          size="sm"
          className={cn(
            "h-8 w-full justify-start gap-2 rounded-lg",
            showSkillsView && "bg-sidebar-accent/85 text-sidebar-accent-foreground"
          )}
          onClick={() => setShowSkillsView(true)}
        >
          <Wrench className="size-4" />
          Skills & MCP
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className={cn(
            "mt-1 h-8 w-full justify-start gap-2 rounded-lg",
            showKanbanView && "bg-sidebar-accent/85 text-sidebar-accent-foreground"
          )}
          onClick={() => setShowKanbanView(true)}
        >
          <LayoutGrid className="size-4" />
          Overview
        </Button>
      </div>
    </aside>
  )
}
