import { Bot, X, FileCode, FileText, FileJson, File } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAppStore } from "@/lib/store"
import { useThreadState, type OpenFile } from "@/lib/thread-context"

interface TabBarProps {
  className?: string
  threadId?: string
}

export function TabBar({
  className,
  threadId: propThreadId
}: TabBarProps): React.JSX.Element | null {
  const { currentThreadId } = useAppStore()
  const threadId = propThreadId ?? currentThreadId
  const threadState = useThreadState(threadId)

  if (!threadState) {
    return null
  }

  const { openFiles, activeTab, setActiveTab, closeFile } = threadState

  return (
    <div
      className={cn(
        "scrollbar-hide flex h-9 items-center overflow-x-auto bg-background/65",
        className
      )}
    >
      {/* Agent Tab - Always first and prominent */}
      <button
        onClick={() => setActiveTab("agent")}
        className={cn(
          "flex h-full shrink-0 items-center gap-2 border-r border-border/70 px-4 text-sm font-medium transition-all",
          activeTab === "agent"
            ? "bg-primary/18 text-foreground"
            : "text-muted-foreground hover:bg-background-interactive/55 hover:text-foreground"
        )}
      >
        <Bot className="size-4" />
        <span>Agent</span>
      </button>

      {/* File Tabs */}
      {openFiles.map((file) => (
        <FileTab
          key={file.path}
          file={file}
          isActive={activeTab === file.path}
          onSelect={() => setActiveTab(file.path)}
          onClose={() => closeFile(file.path)}
        />
      ))}

      {/* Spacer to fill remaining space */}
      <div className="flex-1 min-w-0" />
    </div>
  )
}

interface FileTabProps {
  file: OpenFile
  isActive: boolean
  onSelect: () => void
  onClose: () => void
}

function FileTab({ file, isActive, onSelect, onClose }: FileTabProps): React.JSX.Element {
  const handleClose = (e: React.MouseEvent): void => {
    e.stopPropagation()
    onClose()
  }

  const handleMouseDown = (e: React.MouseEvent): void => {
    // Middle click to close
    if (e.button === 1) {
      e.preventDefault()
      onClose()
    }
  }

  return (
    <button
      onClick={onSelect}
      onMouseDown={handleMouseDown}
      className={cn(
        "group flex h-full max-w-[220px] shrink-0 items-center gap-2 border-r border-border/70 px-3 text-sm transition-all",
        isActive
          ? "bg-card/70 text-foreground"
          : "text-muted-foreground hover:bg-background-interactive/55 hover:text-foreground"
      )}
      title={file.path}
    >
      <FileIcon name={file.name} />
      <span className="truncate">{file.name}</span>
      <button
        onClick={handleClose}
        className={cn(
          "flex size-4 items-center justify-center rounded-md transition-colors hover:bg-background-interactive",
          isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"
        )}
      >
        <X className="size-3" />
      </button>
    </button>
  )
}

function FileIcon({ name }: { name: string }): React.JSX.Element {
  const ext = name.includes(".") ? name.split(".").pop()?.toLowerCase() : ""

  switch (ext) {
    case "ts":
    case "tsx":
    case "js":
    case "jsx":
    case "py":
    case "css":
    case "scss":
    case "html":
      return <FileCode className="size-3.5 text-blue-400 shrink-0" />
    case "json":
      return <FileJson className="size-3.5 text-yellow-500 shrink-0" />
    case "md":
    case "mdx":
    case "txt":
      return <FileText className="size-3.5 text-muted-foreground shrink-0" />
    default:
      return <File className="size-3.5 text-muted-foreground shrink-0" />
  }
}
