import { ScrollArea } from "@/components/ui/scroll-area"
import { MarkdownRenderer } from "@/components/markdown/MarkdownRenderer"

interface MarkdownViewerProps {
  filePath: string
  content: string
}

export function MarkdownViewer({ filePath, content }: MarkdownViewerProps): React.JSX.Element {
  const lineCount = content.split("\n").length

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-background/50 px-4 py-2 text-xs text-muted-foreground">
        <span className="truncate">{filePath}</span>
        <span className="text-muted-foreground/50">•</span>
        <span>{lineCount} lines</span>
        <span className="text-muted-foreground/50">•</span>
        <span>Markdown</span>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="px-4 py-4">
          <MarkdownRenderer content={content} className="openwork-file-markdown" />
        </div>
      </ScrollArea>
    </div>
  )
}
