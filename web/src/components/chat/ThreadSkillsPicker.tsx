import { useCallback, useEffect, useMemo, useState } from "react"
import { Check, ChevronDown, ChevronUp, Loader2, Save, Zap, ZapOff } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { cn } from "@/lib/utils"
import type { Skill, SkillMaterializationState, ThreadSkillBinding } from "@/types"

interface ThreadSkillsPickerProps {
  threadId: string
  skillsEnabled: boolean
  setSkillsEnabled: (enabled: boolean) => void
}

function statusLabel(state: SkillMaterializationState | null): string {
  if (!state) return "Ready"
  switch (state.status) {
    case "syncing":
      return "Syncing"
    case "dirty":
      return "Pending sync"
    case "failed":
      return "Sync failed"
    default:
      return "Ready"
  }
}

export function ThreadSkillsPicker({
  threadId,
  skillsEnabled,
  setSkillsEnabled
}: ThreadSkillsPickerProps): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const [allSkills, setAllSkills] = useState<Skill[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [draftIds, setDraftIds] = useState<string[]>([])
  const [materialization, setMaterialization] = useState<SkillMaterializationState | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [skills, bindings, state] = await Promise.all([
        window.api.skills.list(),
        window.api.threadSkills.list(threadId),
        window.api.threadSkills.getMaterializationState(threadId)
      ])
      const ids = (bindings as ThreadSkillBinding[]).map((binding) => binding.skill_id)
      setAllSkills(skills)
      setSelectedIds(ids)
      setDraftIds(ids)
      setMaterialization(state)
    } catch (e) {
      setError((e as Error).message || "Failed to load thread skills")
    } finally {
      setLoading(false)
    }
  }, [threadId])

  useEffect(() => {
    void loadData()
  }, [loadData])

  useEffect(() => {
    if (!materialization || !["syncing", "dirty"].includes(materialization.status)) {
      return
    }
    const timer = window.setInterval(() => {
      window.api.threadSkills
        .getMaterializationState(threadId)
        .then((state: SkillMaterializationState) => setMaterialization(state))
        .catch(() => {
          // Best-effort polling; keep silent to avoid noisy UI.
        })
    }, 2000)
    return () => window.clearInterval(timer)
  }, [threadId, materialization])

  const selectedSkills = useMemo(
    () => draftIds.map((id) => allSkills.find((skill) => skill.id === id)).filter(Boolean) as Skill[],
    [draftIds, allSkills]
  )

  const toggleSkill = (skillId: string): void => {
    setDraftIds((prev) => {
      if (prev.includes(skillId)) return prev.filter((id) => id !== skillId)
      return [...prev, skillId]
    })
  }

  const moveSkill = (index: number, direction: -1 | 1): void => {
    setDraftIds((prev) => {
      const target = index + direction
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  const saveBindings = async (): Promise<void> => {
    setSaving(true)
    setError(null)
    try {
      await window.api.threadSkills.set(threadId, draftIds)
      const state = await window.api.threadSkills.getMaterializationState(threadId)
      setSelectedIds(draftIds)
      setMaterialization(state)
      setOpen(false)
    } catch (e) {
      setError((e as Error).message || "Failed to save thread skills")
    } finally {
      setSaving(false)
    }
  }

  const hasChanges = draftIds.join(",") !== selectedIds.join(",")
  const selectedCount = selectedIds.length
  const displayLabel = selectedCount > 0 ? `Skills ${selectedCount}` : "Skills"

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn(
            "h-7 gap-1.5 rounded-full border border-border/75 bg-background/55 px-2.5 text-xs",
            selectedCount > 0
              ? "text-status-nominal hover:text-status-nominal"
              : "text-muted-foreground hover:text-foreground"
          )}
          title={selectedCount > 0 ? `${selectedCount} skills bound` : "No skills bound"}
        >
          {skillsEnabled ? <Zap className="size-3.5" /> : <ZapOff className="size-3.5" />}
          <span>{displayLabel}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-[380px] overflow-hidden rounded-2xl border-border/80 bg-popover/95 p-0 shadow-[0_12px_28px_rgba(15,23,42,0.12)] backdrop-blur-xl"
      >
        <div className="space-y-2 border-b border-border/70 p-3">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium">Thread Skills</div>
            <Button
              type="button"
              size="sm"
              variant={skillsEnabled ? "secondary" : "outline"}
              onClick={() => setSkillsEnabled(!skillsEnabled)}
              className="h-7 px-2 text-xs"
            >
              {skillsEnabled ? "Enabled" : "Disabled"}
            </Button>
          </div>
          <div className="text-xs text-muted-foreground">Materialization: {statusLabel(materialization)}</div>
        </div>
        <div className="grid min-h-[280px] grid-cols-2">
          <div className="border-r border-border/70">
            <div className="px-3 py-2 text-xs text-muted-foreground">Available</div>
            <div className="max-h-[240px] overflow-auto px-2 pb-2 space-y-1">
              {loading ? (
                <div className="px-2 py-6 text-xs text-muted-foreground flex items-center gap-2">
                  <Loader2 className="size-3 animate-spin" />
                  Loading...
                </div>
              ) : (
                allSkills.map((skill) => {
                  const checked = draftIds.includes(skill.id)
                  return (
                    <button
                      key={skill.id}
                      className={cn(
                        "w-full rounded-lg border px-2 py-1.5 text-left text-xs",
                        checked
                          ? "border-status-nominal/50 bg-status-nominal/10"
                          : "border-border/80 hover:bg-muted/50"
                      )}
                      onClick={() => toggleSkill(skill.id)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="truncate">{skill.name}</div>
                        {checked && <Check className="size-3.5 text-status-nominal" />}
                      </div>
                      <div className="truncate text-muted-foreground">{skill.key}</div>
                    </button>
                  )
                })
              )}
            </div>
          </div>
          <div>
            <div className="px-3 py-2 text-xs text-muted-foreground">Selected Order</div>
            <div className="max-h-[240px] overflow-auto px-2 pb-2 space-y-1">
              {selectedSkills.length === 0 ? (
                <div className="px-2 py-6 text-xs text-muted-foreground">No skill selected.</div>
              ) : (
                selectedSkills.map((skill, idx) => (
                  <div
                    key={skill.id}
                    className="flex items-center gap-1 rounded-lg border border-border/80 px-2 py-1 text-xs"
                  >
                    <div className="flex-1 truncate">{skill.name}</div>
                    <button
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => moveSkill(idx, -1)}
                    >
                      <ChevronUp className="size-3.5" />
                    </button>
                    <button
                      className="text-muted-foreground hover:text-foreground"
                      onClick={() => moveSkill(idx, 1)}
                    >
                      <ChevronDown className="size-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between border-t border-border/70 p-3">
          <div className="text-xs text-status-critical min-h-4">{error || ""}</div>
          <Button
            size="sm"
            onClick={() => void saveBindings()}
            disabled={saving || !hasChanges}
            className="gap-2"
          >
            {saving && <Loader2 className="size-3.5 animate-spin" />}
            {!saving && <Save className="size-3.5" />}
            Save
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
