import { useCallback, useEffect, useMemo, useState } from "react"
import { Plus, Save, Trash2, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import type { Skill, SkillFile } from "@/types"

function deriveNewSkillKey(skills: Skill[]): string {
  const prefix = "skill"
  let idx = skills.length + 1
  while (skills.some((s) => s.key === `${prefix}-${idx}`)) {
    idx += 1
  }
  return `${prefix}-${idx}`
}

export function SkillsPage(): React.JSX.Element {
  const [skills, setSkills] = useState<Skill[]>([])
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [files, setFiles] = useState<SkillFile[]>([])
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [newSkillKey, setNewSkillKey] = useState("")
  const [newSkillName, setNewSkillName] = useState("")
  const [newSkillDescription, setNewSkillDescription] = useState("")

  const [editName, setEditName] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const [newFilePath, setNewFilePath] = useState("")
  const [fileContentDraft, setFileContentDraft] = useState("")

  const selectedSkill = useMemo(
    () => skills.find((skill) => skill.id === selectedSkillId) || null,
    [skills, selectedSkillId]
  )

  const selectedFile = useMemo(
    () => files.find((file) => file.path === selectedFilePath) || null,
    [files, selectedFilePath]
  )

  const loadSkills = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await window.api.skills.list()
      setSkills(result)
      if (!selectedSkillId && result.length > 0) {
        setSelectedSkillId(result[0].id)
      } else if (selectedSkillId && !result.some((skill: Skill) => skill.id === selectedSkillId)) {
        setSelectedSkillId(result[0]?.id || null)
      }
      if (!newSkillKey) {
        setNewSkillKey(deriveNewSkillKey(result))
      }
    } catch (e) {
      setError((e as Error).message || "Failed to load skills")
    } finally {
      setLoading(false)
    }
  }, [selectedSkillId, newSkillKey])

  const loadFiles = useCallback(async (skillId: string) => {
    setError(null)
    try {
      const result = await window.api.skills.listFiles(skillId)
      setFiles(result)
      if (!selectedFilePath && result.length > 0) {
        setSelectedFilePath(result[0].path)
      } else if (selectedFilePath && !result.some((file: SkillFile) => file.path === selectedFilePath)) {
        setSelectedFilePath(result[0]?.path || null)
      }
    } catch (e) {
      setError((e as Error).message || "Failed to load skill files")
      setFiles([])
      setSelectedFilePath(null)
    }
  }, [selectedFilePath])

  useEffect(() => {
    void loadSkills()
  }, [loadSkills])

  useEffect(() => {
    if (!selectedSkill) {
      setFiles([])
      setSelectedFilePath(null)
      setEditName("")
      setEditDescription("")
      return
    }
    setEditName(selectedSkill.name)
    setEditDescription(selectedSkill.description)
    void loadFiles(selectedSkill.id)
  }, [selectedSkill, loadFiles])

  useEffect(() => {
    if (selectedFile) {
      setFileContentDraft(selectedFile.content)
    } else {
      setFileContentDraft("")
    }
  }, [selectedFile])

  const handleCreateSkill = async (): Promise<void> => {
    if (!newSkillKey.trim() || !newSkillName.trim() || !newSkillDescription.trim()) return
    try {
      const created = await window.api.skills.create({
        key: newSkillKey.trim(),
        name: newSkillName.trim(),
        description: newSkillDescription.trim(),
        enabled: true
      })
      await loadSkills()
      setSelectedSkillId(created.id)
      setNewSkillKey(deriveNewSkillKey([...skills, created]))
      setNewSkillName("")
      setNewSkillDescription("")
    } catch (e) {
      setError((e as Error).message || "Failed to create skill")
    }
  }

  const handleSaveSkillMeta = async (): Promise<void> => {
    if (!selectedSkill) return
    try {
      const updated = await window.api.skills.update(selectedSkill.id, {
        name: editName,
        description: editDescription,
        enabled: selectedSkill.enabled
      })
      setSkills((prev) => prev.map((skill) => (skill.id === updated.id ? updated : skill)))
    } catch (e) {
      setError((e as Error).message || "Failed to save skill")
    }
  }

  const handleToggleEnabled = async (): Promise<void> => {
    if (!selectedSkill) return
    try {
      const updated = await window.api.skills.update(selectedSkill.id, {
        enabled: !selectedSkill.enabled
      })
      setSkills((prev) => prev.map((skill) => (skill.id === updated.id ? updated : skill)))
    } catch (e) {
      setError((e as Error).message || "Failed to update skill status")
    }
  }

  const handleDeleteSkill = async (): Promise<void> => {
    if (!selectedSkill) return
    if (!window.confirm(`Delete skill "${selectedSkill.name}"?`)) return
    try {
      await window.api.skills.delete(selectedSkill.id)
      await loadSkills()
    } catch (e) {
      setError((e as Error).message || "Failed to delete skill")
    }
  }

  const handleUpsertFile = async (path: string, content: string): Promise<void> => {
    if (!selectedSkill) return
    try {
      await window.api.skills.upsertFile(selectedSkill.id, { path, content })
      await loadFiles(selectedSkill.id)
      setSelectedFilePath(path)
    } catch (e) {
      setError((e as Error).message || "Failed to save file")
    }
  }

  const handleCreateFile = async (): Promise<void> => {
    if (!selectedSkill || !newFilePath.trim()) return
    await handleUpsertFile(newFilePath.trim(), "")
    setNewFilePath("")
  }

  const handleDeleteFile = async (path: string): Promise<void> => {
    if (!selectedSkill) return
    if (!window.confirm(`Delete file "${path}"?`)) return
    try {
      await window.api.skills.deleteFile(selectedSkill.id, path)
      await loadFiles(selectedSkill.id)
    } catch (e) {
      setError((e as Error).message || "Failed to delete file")
    }
  }

  const handleSaveCurrentFile = async (): Promise<void> => {
    if (!selectedFile) return
    await handleUpsertFile(selectedFile.path, fileContentDraft)
  }

  return (
    <main className="flex h-full min-h-0 overflow-hidden">
      <aside className="w-72 shrink-0 border-r border-border bg-sidebar">
        <div className="p-3 border-b border-border space-y-2">
          <div className="text-sm font-medium">Skills</div>
          <Input
            value={newSkillKey}
            onChange={(e) => setNewSkillKey(e.target.value)}
            placeholder="skill-key"
          />
          <Input
            value={newSkillName}
            onChange={(e) => setNewSkillName(e.target.value)}
            placeholder="Skill name"
          />
          <Input
            value={newSkillDescription}
            onChange={(e) => setNewSkillDescription(e.target.value)}
            placeholder="Short description"
          />
          <Button size="sm" className="w-full justify-start gap-2" onClick={handleCreateSkill}>
            <Plus className="size-4" />
            Create Skill
          </Button>
          <Button size="sm" variant="ghost" className="w-full justify-start gap-2" onClick={() => void loadSkills()}>
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            Refresh
          </Button>
        </div>
        <ScrollArea className="h-[calc(100%-220px)]">
          <div className="p-2 space-y-1">
            {skills.map((skill) => (
              <button
                key={skill.id}
                className={cn(
                  "w-full text-left rounded-sm px-2 py-2 text-sm border border-transparent hover:border-border",
                  selectedSkillId === skill.id && "bg-sidebar-accent border-border"
                )}
                onClick={() => setSelectedSkillId(skill.id)}
              >
                <div className="font-medium truncate">{skill.name}</div>
                <div className="text-xs text-muted-foreground truncate">{skill.key}</div>
              </button>
            ))}
            {skills.length === 0 && (
              <div className="px-2 py-8 text-xs text-muted-foreground">No skills yet.</div>
            )}
          </div>
        </ScrollArea>
      </aside>

      <section className="flex-1 min-w-0 min-h-0 flex flex-col">
        {!selectedSkill ? (
          <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
            Select or create a skill.
          </div>
        ) : (
          <>
            <div className="border-b border-border p-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium">{selectedSkill.key}</div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={handleToggleEnabled}>
                    {selectedSkill.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button size="sm" variant="destructive" onClick={handleDeleteSkill}>
                    <Trash2 className="size-4 mr-1" />
                    Delete
                  </Button>
                </div>
              </div>
              <Input value={editName} onChange={(e) => setEditName(e.target.value)} />
              <Input
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
              <Button size="sm" onClick={handleSaveSkillMeta} className="gap-2">
                <Save className="size-4" />
                Save Skill
              </Button>
            </div>

            <div className="flex flex-1 min-h-0">
              <aside className="w-72 shrink-0 border-r border-border">
                <div className="p-3 border-b border-border space-y-2">
                  <div className="text-sm font-medium">Files</div>
                  <div className="flex gap-2">
                    <Input
                      value={newFilePath}
                      onChange={(e) => setNewFilePath(e.target.value)}
                      placeholder="references/notes.md"
                    />
                    <Button size="sm" onClick={handleCreateFile}>
                      <Plus className="size-4" />
                    </Button>
                  </div>
                </div>
                <ScrollArea className="h-[calc(100%-76px)]">
                  <div className="p-2 space-y-1">
                    {files.map((file) => (
                      <div
                        key={file.path}
                        className={cn(
                          "flex items-center gap-2 rounded-sm px-2 py-1 text-sm border border-transparent",
                          selectedFilePath === file.path && "bg-sidebar-accent border-border"
                        )}
                      >
                        <button
                          className="flex-1 truncate text-left"
                          onClick={() => setSelectedFilePath(file.path)}
                        >
                          {file.path}
                        </button>
                        {file.path !== "SKILL.md" && (
                          <button
                            className="text-muted-foreground hover:text-foreground"
                            onClick={() => void handleDeleteFile(file.path)}
                          >
                            <Trash2 className="size-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </aside>
              <div className="flex-1 min-w-0 min-h-0 flex flex-col">
                <div className="p-2 border-b border-border flex items-center justify-between">
                  <div className="text-xs text-muted-foreground">
                    {selectedFile ? selectedFile.path : "Select a file"}
                  </div>
                  {selectedFile && (
                    <Button size="sm" onClick={handleSaveCurrentFile} className="gap-2">
                      <Save className="size-4" />
                      Save File
                    </Button>
                  )}
                </div>
                <div className="flex-1 min-h-0 p-3">
                  {selectedFile ? (
                    <textarea
                      value={fileContentDraft}
                      onChange={(e) => setFileContentDraft(e.target.value)}
                      className="w-full h-full resize-none rounded-sm border border-border bg-background p-3 text-sm font-mono"
                    />
                  ) : (
                    <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                      Select a file to edit.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
        {error && <div className="border-t border-border px-3 py-2 text-xs text-status-critical">{error}</div>}
      </section>
    </main>
  )
}
