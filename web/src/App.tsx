import { useEffect, useState, useCallback, useRef, useLayoutEffect } from "react"
import { ThreadSidebar } from "@/components/sidebar/ThreadSidebar"
import { TabbedPanel, TabBar } from "@/components/tabs"
import { RightPanel } from "@/components/panels/RightPanel"
import { KanbanView, KanbanHeader } from "@/components/kanban"
import { SkillsPage } from "@/components/skills/SkillsPage"
import { ResizeHandle } from "@/components/ui/resizable"
import { useAppStore } from "@/lib/store"
import { ThreadProvider } from "@/lib/thread-context"
import { Loader2 } from "lucide-react"

// Badge requires ~235 screen pixels to display with comfortable margin
const BADGE_MIN_SCREEN_WIDTH = 235
const TITLEBAR_HEIGHT_CSS = 36
const APP_BADGE_HEIGHT_SCREEN = 26
const APP_BADGE_TOP_SCREEN = Math.max(0, (TITLEBAR_HEIGHT_CSS - APP_BADGE_HEIGHT_SCREEN) / 2)
const LEFT_MAX = 350
const LEFT_DEFAULT = 240

const RIGHT_MIN = 250
const RIGHT_MAX = 450
const RIGHT_DEFAULT = 320

function App(): React.JSX.Element {
  const { currentThreadId, loadThreads, createThread, showKanbanView, showSkillsView, threadCreation } =
    useAppStore()
  const [isLoading, setIsLoading] = useState(true)
  const [authRequired, setAuthRequired] = useState(false)
  const [authEmail, setAuthEmail] = useState("")
  const [authPassword, setAuthPassword] = useState("")
  const [authError, setAuthError] = useState<string | null>(null)
  const [authLoading, setAuthLoading] = useState(false)
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT)
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT)
  const [zoomLevel, setZoomLevel] = useState(1)
  const isCreatingThread = threadCreation.status === "creating"

  // Track drag start widths
  const dragStartWidths = useRef<{ left: number; right: number } | null>(null)

  // Track zoom level changes and update CSS custom properties for safe areas
  useLayoutEffect(() => {
    const updateZoom = (): void => {
      // Detect zoom by comparing outer/inner window dimensions
      const detectedZoom = Math.round((window.outerWidth / window.innerWidth) * 100) / 100
      if (detectedZoom > 0.5 && detectedZoom < 3) {
        setZoomLevel(detectedZoom)

        // Traffic lights are at fixed screen position (y: ~28px bottom including padding)
        // Titlebar is 36px CSS, which becomes 36*zoom screen pixels
        // Extra padding needed when titlebar shrinks below traffic lights
        const TRAFFIC_LIGHT_BOTTOM_SCREEN = 40 // screen pixels to clear traffic lights
        const titlebarScreenHeight = TITLEBAR_HEIGHT_CSS * detectedZoom
        const extraPaddingScreen = Math.max(0, TRAFFIC_LIGHT_BOTTOM_SCREEN - titlebarScreenHeight)
        const extraPaddingCss = Math.round(extraPaddingScreen / detectedZoom)

        document.documentElement.style.setProperty("--sidebar-safe-padding", `${extraPaddingCss}px`)
      }
    }

    updateZoom()
    window.addEventListener("resize", updateZoom)
    return () => window.removeEventListener("resize", updateZoom)
  }, [])

  // Calculate zoom-compensated minimum width to always contain the badge
  const leftMinWidth = Math.ceil(BADGE_MIN_SCREEN_WIDTH / zoomLevel)

  // Enforce minimum width when zoom changes
  useEffect(() => {
    if (leftWidth < leftMinWidth) {
      setLeftWidth(leftMinWidth)
    }
  }, [leftMinWidth, leftWidth])

  const handleLeftResize = useCallback(
    (totalDelta: number) => {
      if (!dragStartWidths.current) {
        dragStartWidths.current = { left: leftWidth, right: rightWidth }
      }
      const newWidth = dragStartWidths.current.left + totalDelta
      setLeftWidth(Math.min(LEFT_MAX, Math.max(leftMinWidth, newWidth)))
    },
    [leftWidth, rightWidth, leftMinWidth]
  )

  const handleRightResize = useCallback(
    (totalDelta: number) => {
      if (!dragStartWidths.current) {
        dragStartWidths.current = { left: leftWidth, right: rightWidth }
      }
      const newWidth = dragStartWidths.current.right - totalDelta
      setRightWidth(Math.min(RIGHT_MAX, Math.max(RIGHT_MIN, newWidth)))
    },
    [leftWidth, rightWidth]
  )

  // Reset drag start on mouse up
  useEffect(() => {
    const handleMouseUp = (): void => {
      dragStartWidths.current = null
    }
    document.addEventListener("mouseup", handleMouseUp)
    return () => document.removeEventListener("mouseup", handleMouseUp)
  }, [])

  useEffect(() => {
    async function init(): Promise<void> {
      try {
        await loadThreads()
        // Create a default thread if none exist
        const threads = useAppStore.getState().threads
        if (threads.length === 0) {
          await createThread()
        }
      } catch (error) {
        console.error("Failed to initialize:", error)
        if ((error as { status?: number }).status === 401) {
          setAuthRequired(true)
        }
      } finally {
        setIsLoading(false)
      }
    }
    init()
  }, [loadThreads, createThread])

  const handleLogin = useCallback(async () => {
    setAuthError(null)
    setAuthLoading(true)
    try {
      await (window as any).api.auth.login(authEmail, authPassword)
      setAuthRequired(false)
      await loadThreads()
    } catch (error) {
      setAuthError("Login failed. Check your credentials.")
    } finally {
      setAuthLoading(false)
    }
  }, [authEmail, authPassword, loadThreads])

  if (isLoading) {
    return (
      <div className="app-shell flex h-screen items-center justify-center bg-background">
        <div className="rounded-xl border border-border/80 bg-card/85 px-5 py-3 text-sm text-muted-foreground shadow-[0_10px_24px_rgba(15,23,42,0.08)] backdrop-blur">
          Initializing...
        </div>
      </div>
    )
  }

  if (authRequired) {
    return (
      <div className="app-shell flex h-screen items-center justify-center bg-background px-4">
        <div className="w-full max-w-sm rounded-2xl border border-border/80 bg-card/90 p-6 shadow-[0_14px_30px_rgba(15,23,42,0.1)] backdrop-blur">
          <div className="mb-4 text-lg font-semibold">Sign in</div>
          <div className="space-y-3">
            <input
              className="w-full rounded-lg border border-border/80 bg-background/70 px-3 py-2 text-sm"
              placeholder="Email"
              type="email"
              value={authEmail}
              onChange={(e) => setAuthEmail(e.target.value)}
            />
            <input
              className="w-full rounded-lg border border-border/80 bg-background/70 px-3 py-2 text-sm"
              placeholder="Password"
              type="password"
              value={authPassword}
              onChange={(e) => setAuthPassword(e.target.value)}
            />
            {authError && <div className="text-sm text-red-500">{authError}</div>}
            <button
              className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/94"
              onClick={handleLogin}
              disabled={authLoading}
            >
              {authLoading ? "Signing in..." : "Sign in"}
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <ThreadProvider>
      <div className="app-shell flex h-screen overflow-hidden bg-background">
        {/* Fixed app badge - zoom independent position and size */}
        <div
          className="app-badge"
          style={{
            // Compensate both position and scale for zoom
            // Keep badge centered in the 36px titlebar while staying past traffic lights.
            top: `${APP_BADGE_TOP_SCREEN / zoomLevel}px`,
            left: `${82 / zoomLevel}px`,
            transform: `scale(${1 / zoomLevel})`,
            transformOrigin: "top left"
          }}
        >
          <span className="app-badge-name">OPENWORK</span>
          <span className="app-badge-version">{__APP_VERSION__}</span>
        </div>

        {/* Left + Center column */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Titlebar row with tabs integrated */}
          <div className="app-drag-region flex h-9 w-full shrink-0 border-b border-border/70 bg-background/65 backdrop-blur-xl">
            {/* Left section - spacer for traffic lights + badge (matches left sidebar width) */}
            <div style={{ width: leftWidth }} className="shrink-0 bg-sidebar/85" />

            {/* Resize handle spacer */}
            <div className="w-[1px] shrink-0" />

            {/* Center section - Tab bar or Kanban header */}
            <div className="min-w-0 flex-1 bg-background/60">
              {showKanbanView ? (
                <KanbanHeader className="h-full" />
              ) : showSkillsView ? (
                <div className="flex h-full items-center px-4 text-sm font-medium">Skills</div>
              ) : isCreatingThread ? (
                <div className="flex h-full items-center gap-2 px-4 text-xs uppercase tracking-[0.08em] text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin text-status-info" />
                  <span>Preparing thread...</span>
                </div>
              ) : (
                currentThreadId && <TabBar className="h-full border-b-0" />
              )}
            </div>
          </div>

          {/* Main content area */}
          <div className="flex flex-1 overflow-hidden">
            {/* Left Sidebar - Thread List */}
            <div style={{ width: leftWidth }} className="shrink-0">
              <ThreadSidebar />
            </div>

            <ResizeHandle onDrag={handleLeftResize} />

            {showKanbanView ? (
              /* Kanban View - replaces center and right panels */
              <main className="flex flex-1 flex-col min-w-0 overflow-hidden">
                <KanbanView />
              </main>
            ) : showSkillsView ? (
              <main className="flex flex-1 flex-col min-w-0 overflow-hidden">
                <SkillsPage />
              </main>
            ) : (
              <>
                {/* Center - Content Panel (Agent Chat + File Viewer) */}
                <main className="flex flex-1 flex-col min-w-0 overflow-hidden">
                  {isCreatingThread ? (
                    <div className="flex flex-1 flex-col items-center justify-center gap-2 text-muted-foreground">
                      <Loader2 className="size-8 animate-spin text-status-info" />
                      <div className="text-sm">Preparing thread workspace...</div>
                      <div className="text-xs">The new session will load automatically when ready.</div>
                    </div>
                  ) : currentThreadId ? (
                    <TabbedPanel threadId={currentThreadId} showTabBar={false} />
                  ) : (
                    <div className="flex flex-1 items-center justify-center text-muted-foreground">
                      Select or create a thread to begin
                    </div>
                  )}
                </main>
              </>
            )}
          </div>
        </div>

        {!showKanbanView && !showSkillsView && (
          <>
            <ResizeHandle onDrag={handleRightResize} />

            {/* Right Panel - Status Panels (full height) */}
            <div style={{ width: rightWidth }} className="shrink-0">
              <RightPanel />
            </div>
          </>
        )}
      </div>
    </ThreadProvider>
  )
}

export default App
