import { useRef, useEffect, useMemo, useCallback } from "react"
import { Send, Square, Loader2, AlertCircle, X, Sparkles } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useAppStore } from "@/lib/store"
import { useCurrentThread, useThreadContext, useThreadStream } from "@/lib/thread-context"
import { MessageBubble } from "./MessageBubble"
import { ModelSwitcher } from "./ModelSwitcher"
import { WorkspacePicker } from "./WorkspacePicker"
import { ChatTodos } from "./ChatTodos"
import { ContextUsageIndicator } from "./ContextUsageIndicator"
import type { Message } from "@/types"

interface AgentStreamValues {
  todos?: Array<{ id?: string; content?: string; status?: string }>
}

interface StreamMessage {
  id?: string
  type?: string
  content?: string | unknown[]
  tool_calls?: Message["tool_calls"]
  tool_call_id?: string
  name?: string
  status?: "success" | "error"
}

interface ChatContainerProps {
  threadId: string
}

export function ChatContainer({ threadId }: ChatContainerProps): React.JSX.Element {
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const isAtBottomRef = useRef(true)
  const { reloadThread } = useThreadContext()

  const { threads, loadThreads, generateTitleForFirstMessage } = useAppStore()

  // Get persisted thread state and actions from context
  const {
    messages: threadMessages,
    pendingApproval,
    todos,
    error: threadError,
    notice: threadNotice,
    tokenUsage,
    currentModel,
    skillsEnabled,
    draftInput: input,
    setTodos,
    setPendingApproval,
    appendMessage,
    clearError,
    dismissNotice,
    setDraftInput: setInput
  } = useCurrentThread(threadId)

  // Get the stream data via subscription - reactive updates without re-rendering provider
  const streamData = useThreadStream(threadId)
  const stream = streamData.stream
  const isLoading = streamData.isLoading

  useEffect(() => {
    reloadThread(threadId)
  }, [threadId, reloadThread])

  const handleApprovalDecision = useCallback(
    async (decision: "approve" | "reject" | "edit"): Promise<void> => {
      if (!pendingApproval || !stream) return

      setPendingApproval(null)

      try {
        await stream.submit(null, {
          command: { resume: { decision } },
          config: {
            configurable: {
              thread_id: threadId,
              model_id: currentModel,
              skills_enabled: skillsEnabled
            }
          }
        })
      } catch (err) {
        console.error("[ChatContainer] Resume command failed:", err)
      }
    },
    [pendingApproval, setPendingApproval, stream, threadId, currentModel, skillsEnabled]
  )

  const agentValues = stream?.values as AgentStreamValues | undefined
  const streamTodos = agentValues?.todos
  useEffect(() => {
    if (Array.isArray(streamTodos)) {
      setTodos(
        streamTodos.map((t) => ({
          id: t.id || crypto.randomUUID(),
          content: t.content || "",
          status: (t.status || "pending") as "pending" | "in_progress" | "completed" | "cancelled"
        }))
      )
    }
  }, [streamTodos, setTodos])

  const prevLoadingRef = useRef(false)
  useEffect(() => {
    if (prevLoadingRef.current && !isLoading) {
      for (const rawMsg of streamData.messages) {
        const msg = rawMsg as StreamMessage
        if (msg.id) {
          const streamMsg = msg as StreamMessage & { id: string }

          let role: Message["role"] = "assistant"
          if (streamMsg.type === "human") role = "user"
          else if (streamMsg.type === "tool") role = "tool"
          else if (streamMsg.type === "ai") role = "assistant"

          const storeMsg: Message = {
            id: streamMsg.id,
            role,
            content: typeof streamMsg.content === "string" ? streamMsg.content : "",
            tool_calls: streamMsg.tool_calls,
            ...(role === "tool" &&
              streamMsg.tool_call_id && { tool_call_id: streamMsg.tool_call_id }),
            ...(role === "tool" && streamMsg.name && { name: streamMsg.name }),
            ...(role === "tool" && streamMsg.status && { status: streamMsg.status }),
            created_at: new Date()
          }
          appendMessage(storeMsg)
        }
      }
      loadThreads()
    }
    prevLoadingRef.current = isLoading
  }, [isLoading, streamData.messages, loadThreads, appendMessage])

  const displayMessages = useMemo(() => {
    const threadMessageIds = new Set(threadMessages.map((m) => m.id))

    const streamingMsgs: Message[] = ((streamData.messages || []) as StreamMessage[])
      .filter((m): m is StreamMessage & { id: string } => !!m.id && !threadMessageIds.has(m.id))
      .map((streamMsg) => {
        let role: Message["role"] = "assistant"
        if (streamMsg.type === "human") role = "user"
        else if (streamMsg.type === "tool") role = "tool"
        else if (streamMsg.type === "ai") role = "assistant"

        return {
          id: streamMsg.id,
          role,
          content: typeof streamMsg.content === "string" ? streamMsg.content : "",
          tool_calls: streamMsg.tool_calls,
          ...(role === "tool" &&
            streamMsg.tool_call_id && { tool_call_id: streamMsg.tool_call_id }),
          ...(role === "tool" && streamMsg.name && { name: streamMsg.name }),
          ...(role === "tool" && streamMsg.status && { status: streamMsg.status }),
          created_at: new Date()
        }
      })

    return [...threadMessages, ...streamingMsgs]
  }, [threadMessages, streamData.messages])

  // Build tool results map from tool messages
  const toolResults = useMemo(() => {
    const results = new Map<string, { content: string | unknown; is_error?: boolean }>()
    for (const msg of displayMessages) {
      if (msg.role === "tool" && msg.tool_call_id) {
        results.set(msg.tool_call_id, {
          content: msg.content,
          is_error: msg.status === "error"
        })
      }
    }
    return results
  }, [displayMessages])

  const latestMessageId = displayMessages.length > 0 ? displayMessages[displayMessages.length - 1]?.id : null

  // Get the actual scrollable viewport element from Radix ScrollArea
  const getViewport = useCallback((): HTMLDivElement | null => {
    return scrollRef.current?.querySelector(
      "[data-radix-scroll-area-viewport]"
    ) as HTMLDivElement | null
  }, [])

  // Track scroll position to determine if user is at bottom
  const handleScroll = useCallback((): void => {
    const viewport = getViewport()
    if (!viewport) return

    const { scrollTop, scrollHeight, clientHeight } = viewport
    // Consider "at bottom" if within 50px of the bottom
    const threshold = 50
    isAtBottomRef.current = scrollHeight - scrollTop - clientHeight < threshold
  }, [getViewport])

  // Attach scroll listener to viewport
  useEffect(() => {
    const viewport = getViewport()
    if (!viewport) return

    viewport.addEventListener("scroll", handleScroll)
    return () => viewport.removeEventListener("scroll", handleScroll)
  }, [getViewport, handleScroll])

  // Auto-scroll on new messages only if already at bottom
  useEffect(() => {
    const viewport = getViewport()
    if (viewport && isAtBottomRef.current) {
      viewport.scrollTop = viewport.scrollHeight
    }
  }, [displayMessages, isLoading, getViewport])

  // Always scroll to bottom when switching threads
  useEffect(() => {
    const viewport = getViewport()
    if (viewport) {
      viewport.scrollTop = viewport.scrollHeight
      isAtBottomRef.current = true
    }
  }, [threadId, getViewport])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [threadId])

  const handleDismissError = (): void => {
    clearError()
  }

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault()
    if (!input.trim() || isLoading || !stream) return

    if (threadError) {
      clearError()
    }

    if (pendingApproval) {
      setPendingApproval(null)
    }

    const message = input.trim()
    setInput("")

    const isFirstMessage = threadMessages.length === 0

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
      created_at: new Date()
    }
    appendMessage(userMessage)

    if (isFirstMessage) {
      const currentThread = threads.find((t) => t.thread_id === threadId)
      const hasDefaultTitle = currentThread?.title?.startsWith("Thread ")
      if (hasDefaultTitle) {
        generateTitleForFirstMessage(threadId, message)
      }
    }

    await stream.submit(
      {
        messages: [{ type: "human", content: message }]
      },
      {
        config: {
          configurable: {
            thread_id: threadId,
            model_id: currentModel,
            skills_enabled: skillsEnabled
          }
        }
      }
    )
  }

  const handleKeyDown = (e: React.KeyboardEvent): void => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  // Auto-resize textarea based on content
  const adjustTextareaHeight = (): void => {
    const textarea = inputRef.current
    if (textarea) {
      textarea.style.height = "auto"
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }

  useEffect(() => {
    adjustTextareaHeight()
  }, [input])

  const handleCancel = async (): Promise<void> => {
    await stream?.stop()
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {/* Messages */}
      <ScrollArea className="flex-1 min-h-0" ref={scrollRef}>
        <div className="px-5 py-6 md:px-8">
          <div className="mx-auto max-w-4xl space-y-5">
            {displayMessages.length === 0 && !isLoading && (
              <div className="mx-auto max-w-2xl rounded-2xl border border-border/75 bg-card/75 p-8 text-center text-muted-foreground shadow-[0_12px_28px_rgba(15,23,42,0.08)]">
                <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/12 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-primary">
                  <Sparkles className="size-3.5" />
                  New Conversation
                </div>
                <div className="text-xl font-semibold text-foreground">Ask the agent to build with you</div>
                <div className="mt-2 text-sm">
                  Describe your goal, constraints, and expected output. The agent will plan and execute step by step.
                </div>
                <div className="mt-5 flex flex-wrap items-center justify-center gap-2 text-xs">
                  <span className="rounded-full border border-border/80 bg-background/60 px-3 py-1">
                    UI redesign
                  </span>
                  <span className="rounded-full border border-border/80 bg-background/60 px-3 py-1">
                    Bug investigation
                  </span>
                  <span className="rounded-full border border-border/80 bg-background/60 px-3 py-1">
                    Performance tuning
                  </span>
                </div>
              </div>
            )}

            {displayMessages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                isStreaming={Boolean(
                  isLoading && latestMessageId && message.id === latestMessageId && message.role === "assistant"
                )}
                toolResults={toolResults}
                pendingApproval={pendingApproval}
                onApprovalDecision={handleApprovalDecision}
              />
            ))}

            {/* Streaming indicator and inline TODOs */}
            {isLoading && (
              <div className="space-y-3">
                <div className="flex items-center gap-2 rounded-xl border border-border/75 bg-card/75 px-3 py-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin text-primary" />
                  Agent is drafting a response...
                </div>
                {todos.length > 0 && <ChatTodos todos={todos} />}
              </div>
            )}

            {/* Error state */}
            {threadNotice && !isLoading && (
              <div className="flex items-start gap-3 rounded-xl border border-status-warning/45 bg-status-warning/10 p-4 shadow-[0_8px_18px_rgba(146,64,14,0.08)]">
                <AlertCircle className="mt-0.5 size-5 shrink-0 text-status-warning" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-status-warning">Capability Notice</div>
                  <div className="mt-1 break-words text-sm text-muted-foreground">{threadNotice.message}</div>
                </div>
                <button
                  onClick={dismissNotice}
                  className="shrink-0 rounded-md p-1 transition-colors hover:bg-status-warning/20"
                  aria-label="Dismiss notice"
                >
                  <X className="size-4 text-muted-foreground" />
                </button>
              </div>
            )}

            {threadError && !isLoading && (
              <div className="flex items-start gap-3 rounded-xl border border-destructive/45 bg-destructive/10 p-4 shadow-[0_8px_18px_rgba(127,29,29,0.12)]">
                <AlertCircle className="mt-0.5 size-5 shrink-0 text-destructive" />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-destructive">Agent Error</div>
                  <div className="mt-1 break-words text-sm text-muted-foreground">
                    {threadError}
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    You can try sending a new message to continue the conversation.
                  </div>
                </div>
                <button
                  onClick={handleDismissError}
                  className="shrink-0 rounded-md p-1 transition-colors hover:bg-destructive/20"
                  aria-label="Dismiss error"
                >
                  <X className="size-4 text-muted-foreground" />
                </button>
              </div>
            )}
          </div>
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t border-border/70 bg-background/60 px-5 py-4 backdrop-blur-xl md:px-8">
        <form onSubmit={handleSubmit} className="mx-auto max-w-4xl">
          <div className="rounded-2xl border border-border/80 bg-card/85 p-3 shadow-[0_10px_24px_rgba(15,23,42,0.08)]">
            <div className="flex items-end gap-3">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Message the agent..."
                disabled={isLoading}
                className="min-w-0 flex-1 resize-none rounded-xl border border-border/85 bg-background/72 px-4 py-3 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring/60 disabled:opacity-50"
                rows={1}
                style={{ minHeight: "48px", maxHeight: "200px" }}
              />
              <div className="flex h-12 shrink-0 items-center justify-center">
                {isLoading ? (
                  <Button type="button" variant="outline" size="icon" onClick={handleCancel}>
                    <Square className="size-4" />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    variant="default"
                    size="icon"
                    disabled={!input.trim()}
                    className="rounded-xl"
                  >
                    <Send className="size-4" />
                  </Button>
                )}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <ModelSwitcher threadId={threadId} />
                <div className="h-4 w-px bg-border" />
                <WorkspacePicker threadId={threadId} />
              </div>
              {tokenUsage && (
                <ContextUsageIndicator tokenUsage={tokenUsage} modelId={currentModel} />
              )}
            </div>
          </div>
          <div className="mt-2 px-1 text-[11px] text-muted-foreground">
            Press Enter to send, Shift + Enter for newline.
          </div>
        </form>
      </div>
    </div>
  )
}
