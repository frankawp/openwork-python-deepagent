import { useEffect, useState, useMemo } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { highlightCodeToHtml, resolveShikiLanguageFromPath } from "@/lib/shiki-highlighter"

interface CodeViewerProps {
  filePath: string
  content: string
}

export function CodeViewer({ filePath, content }: CodeViewerProps) {
  const [highlightedHtml, setHighlightedHtml] = useState<string | null>(null)

  const language = useMemo(() => resolveShikiLanguageFromPath(filePath), [filePath])

  // Highlight code with Shiki
  useEffect(() => {
    let cancelled = false

    async function highlight() {
      if (content === undefined || language === null) {
        setHighlightedHtml(null)
        return
      }

      try {
        const html = await highlightCodeToHtml(content, language)

        if (cancelled) return
        setHighlightedHtml(html)
      } catch (e) {
        console.error("[CodeViewer] Shiki highlighting failed:", e)
        setHighlightedHtml(null)
      }
    }

    highlight()

    return () => {
      cancelled = true
    }
  }, [content, language])

  const lineCount = content?.split("\n").length ?? 0

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
      {/* File path header */}
      <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-background/50 text-xs text-muted-foreground shrink-0">
        <span className="truncate">{filePath}</span>
        <span className="text-muted-foreground/50">•</span>
        <span>{lineCount} lines</span>
        <span className="text-muted-foreground/50">•</span>
        <span className="text-muted-foreground/70">{language || "plain text"}</span>
      </div>

      {/* File content with syntax highlighting */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="shiki-wrapper">
          {highlightedHtml ? (
            <div className="shiki-content" dangerouslySetInnerHTML={{ __html: highlightedHtml }} />
          ) : (
            // Fallback plain text rendering
            <pre className="p-4 text-sm font-mono leading-relaxed whitespace-pre-wrap break-all">
              {content}
            </pre>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
