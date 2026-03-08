import { useState } from "react"
import { Plus, MessageSquare, Trash2, Pencil, Loader2, LayoutGrid, AlertCircle } from "lucide-react"
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
            "group flex items-center gap-2 rounded-sm px-3 py-2 cursor-pointer transition-colors overflow-hidden",
            isSelected
              ? "bg-sidebar-accent text-sidebar-accent-foreground"
              : "hover:bg-sidebar-accent/50"
          )}
          onClick={() => {
            if (!isEditing) {
              onSelect()
            }
          }}
        >
          <ThreadStatusIcon threadId={thread.thread_id} />
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
                className="w-full bg-background border border-border rounded px-1 py-0.5 text-sm outline-none focus:ring-1 focus:ring-ring"
                autoFocus
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <>
                <div className="text-sm truncate block">
                  {thread.title || truncate(thread.thread_id, 20)}
                </div>
                <div className="text-[10px] text-muted-foreground truncate">
                  {formatRelativeTime(thread.updated_at)}
                </div>
              </>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            className="opacity-0 group-hover:opacity-100 shrink-0"
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
          >
            <Trash2 className="size-3" />
          </Button>
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem onClick={onStartEditing}>
          <Pencil className="size-4 mr-2" />
          Rename
        </ContextMenuItem>
        <ContextMenuSeparator />
        <ContextMenuItem variant="destructive" onClick={onDelete}>
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
    threadCreation
  } = useAppStore()

  const [editingThreadId, setEditingThreadId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState("")

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
    try {
      await createThread({ title: `Thread ${new Date().toLocaleDateString()}` })
    } catch (error) {
      console.error("[ThreadSidebar] Failed to create thread:", error)
    }
  }

  const isCreating = threadCreation.status === "creating"
  const hasCreateError = threadCreation.status === "failed"

  return (
    <aside className="flex h-full w-full flex-col border-r border-border bg-sidebar overflow-hidden">
      {/* New Thread Button - with dynamic safe area padding when zoomed out */}
      <div className="p-2" style={{ paddingTop: "calc(8px + var(--sidebar-safe-padding, 0px))" }}>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2"
          onClick={handleNewThread}
          disabled={isCreating}
        >
          {isCreating ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
          {isCreating ? "Preparing thread..." : "New Thread"}
        </Button>
      </div>

      {/* Thread List */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-2 space-y-1 overflow-hidden">
          {isCreating && (
            <div className="flex items-center gap-2 rounded-sm px-3 py-2 bg-sidebar-accent/40 text-sidebar-foreground">
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
            <div className="rounded-sm px-3 py-2 border border-status-error/40 bg-status-error/10">
              <div className="flex items-start gap-2">
                <AlertCircle className="size-4 mt-0.5 shrink-0 text-status-error" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-status-error font-medium">Thread creation failed</div>
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

          {threads.map((thread) => (
            <ThreadListItem
              key={thread.thread_id}
              thread={thread}
              isSelected={currentThreadId === thread.thread_id}
              isEditing={editingThreadId === thread.thread_id}
              editingTitle={editingTitle}
              onSelect={() => selectThread(thread.thread_id)}
              onDelete={() => deleteThread(thread.thread_id)}
              onStartEditing={() => startEditing(thread.thread_id, thread.title || "")}
              onSaveTitle={saveTitle}
              onCancelEditing={cancelEditing}
              onEditingTitleChange={setEditingTitle}
            />
          ))}

          {threads.length === 0 && !isCreating && (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              No threads yet
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Overview Toggle */}
      <div className="p-2 border-t border-border">
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2"
          onClick={() => setShowKanbanView(true)}
        >
          <LayoutGrid className="size-4" />
          Overview
        </Button>
      </div>
    </aside>
  )
}
