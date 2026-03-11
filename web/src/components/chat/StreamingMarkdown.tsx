import { memo } from "react"
import { MarkdownRenderer } from "@/components/markdown/MarkdownRenderer"

interface StreamingMarkdownProps {
  children: string
  isStreaming?: boolean
}

export const StreamingMarkdown = memo(function StreamingMarkdown({
  children,
  isStreaming = false
}: StreamingMarkdownProps): React.JSX.Element {
  return <MarkdownRenderer content={children} isStreaming={isStreaming} />
})
