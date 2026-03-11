import { memo, useEffect, useMemo, useState } from "react"
import { XMarkdown, type ComponentProps } from "@ant-design/x-markdown"
import Latex from "@ant-design/x-markdown/plugins/Latex"
import { cn } from "@/lib/utils"
import {
  highlightCodeToHtml,
  resolveShikiLanguageFromInfoString
} from "@/lib/shiki-highlighter"

interface MarkdownRendererProps {
  content: string
  isStreaming?: boolean
  className?: string
}

const MARKDOWN_EXTENSIONS = Latex()

function extractTextFromNode(node: unknown): string {
  if (typeof node === "string") return node
  if (Array.isArray(node)) return node.map(extractTextFromNode).join("")
  if (node && typeof node === "object" && "children" in (node as Record<string, unknown>)) {
    return extractTextFromNode((node as { children?: unknown }).children)
  }
  if (node && typeof node === "object" && "data" in (node as Record<string, unknown>)) {
    return String((node as { data?: unknown }).data ?? "")
  }
  return ""
}

function extractPreCodeBlock(domNode: unknown): { code: string; lang?: string } {
  const node = domNode as { children?: Array<{ name?: string; attribs?: Record<string, string>; children?: unknown }> }
  const codeNode = node.children?.find((child) => child?.name === "code")
  if (!codeNode) return { code: "" }

  const rawCode = extractTextFromNode(codeNode.children ?? "")
  const dataLang = codeNode.attribs?.["data-lang"] || codeNode.attribs?.class
  return { code: rawCode, lang: dataLang }
}

function MarkdownPre({
  domNode,
  className
}: ComponentProps): React.JSX.Element {
  const { code, lang } = useMemo(() => extractPreCodeBlock(domNode), [domNode])
  const language = useMemo(() => resolveShikiLanguageFromInfoString(lang), [lang])
  const [highlightedHtml, setHighlightedHtml] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function renderHighlighted() {
      if (!language || !code.trim()) {
        setHighlightedHtml(null)
        return
      }
      try {
        const html = await highlightCodeToHtml(code, language)
        if (!cancelled) {
          setHighlightedHtml(html)
        }
      } catch {
        if (!cancelled) {
          setHighlightedHtml(null)
        }
      }
    }

    renderHighlighted()
    return () => {
      cancelled = true
    }
  }, [code, language])

  const displayLang = language || (lang ? lang.split(/[\s,{]/)[0] : "text")

  return (
    <div className={cn("openwork-xmarkdown-preblock", className)}>
      <div className="openwork-xmarkdown-prehead">{displayLang}</div>
      {highlightedHtml ? (
        <div
          className="openwork-xmarkdown-precontent shiki-content"
          dangerouslySetInnerHTML={{ __html: highlightedHtml }}
        />
      ) : (
        <pre className="openwork-xmarkdown-precontent openwork-xmarkdown-fallback-pre">
          <code>{code}</code>
        </pre>
      )}
    </div>
  )
}

export const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
  isStreaming = false,
  className
}: MarkdownRendererProps): React.JSX.Element {
  return (
    <div className={cn("openwork-xmarkdown-wrapper", className)}>
      <XMarkdown
        content={content}
        className="x-markdown-light openwork-xmarkdown"
        openLinksInNewTab
        escapeRawHtml
        config={{
          gfm: true,
          breaks: true,
          extensions: MARKDOWN_EXTENSIONS
        }}
        components={{
          pre: MarkdownPre
        }}
        streaming={{
          hasNextChunk: isStreaming,
          enableAnimation: isStreaming,
          animationConfig: {
            fadeDuration: 180,
            easing: "ease-out"
          }
        }}
      />
      {isStreaming && <span className="openwork-xmarkdown-cursor" aria-hidden />}
    </div>
  )
})
