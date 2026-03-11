import { Folder } from "lucide-react"
import { useEffect } from "react"
import { useCurrentThread } from "@/lib/thread-context"

interface WorkspacePickerProps {
  threadId: string
}

export function WorkspacePicker({ threadId }: WorkspacePickerProps): React.JSX.Element {
  const { workspacePath, setWorkspacePath, setWorkspaceFiles } = useCurrentThread(threadId)

  useEffect(() => {
    async function loadWorkspace(): Promise<void> {
      if (!threadId) return
      const path = await window.api.workspace.get(threadId)
      setWorkspacePath(path)

      if (path) {
        const result = await window.api.workspace.loadTree(threadId, "/", 2)
        if (result.success && result.files) {
          setWorkspaceFiles(result.files)
        }
      }
    }
    loadWorkspace()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId])

  return (
    <div className="inline-flex h-7 max-w-[280px] items-center gap-1.5 rounded-full border border-border/75 bg-background/55 px-2.5 text-xs text-foreground">
      <Folder className="size-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate" title={workspacePath || undefined}>
        {workspacePath || "Sandbox workspace"}
      </span>
    </div>
  )
}
