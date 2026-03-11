import { createHighlighterCore, type HighlighterCore } from "shiki/core"
import { createJavaScriptRegexEngine } from "shiki/engine/javascript"

import githubLightDefault from "shiki/themes/github-light-default.mjs"
import langTypescript from "shiki/langs/typescript.mjs"
import langTsx from "shiki/langs/tsx.mjs"
import langJavascript from "shiki/langs/javascript.mjs"
import langJsx from "shiki/langs/jsx.mjs"
import langPython from "shiki/langs/python.mjs"
import langJson from "shiki/langs/json.mjs"
import langCss from "shiki/langs/css.mjs"
import langHtml from "shiki/langs/html.mjs"
import langMarkdown from "shiki/langs/markdown.mjs"
import langYaml from "shiki/langs/yaml.mjs"
import langBash from "shiki/langs/bash.mjs"
import langSql from "shiki/langs/sql.mjs"

let highlighterPromise: Promise<HighlighterCore> | null = null

const SUPPORTED_LANGS = new Set([
  "typescript",
  "tsx",
  "javascript",
  "jsx",
  "python",
  "json",
  "css",
  "html",
  "markdown",
  "yaml",
  "bash",
  "sql"
])

const LANG_ALIASES: Record<string, string> = {
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  json: "json",
  css: "css",
  html: "html",
  htm: "html",
  md: "markdown",
  mdx: "markdown",
  markdown: "markdown",
  yaml: "yaml",
  yml: "yaml",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  shell: "bash",
  console: "bash",
  sql: "sql"
}

async function getHighlighter(): Promise<HighlighterCore> {
  if (!highlighterPromise) {
    highlighterPromise = createHighlighterCore({
      themes: [githubLightDefault],
      langs: [
        langTypescript,
        langTsx,
        langJavascript,
        langJsx,
        langPython,
        langJson,
        langCss,
        langHtml,
        langMarkdown,
        langYaml,
        langBash,
        langSql
      ],
      engine: createJavaScriptRegexEngine()
    })
  }
  return highlighterPromise
}

function normalizeLanguage(raw?: string | null): string | null {
  if (!raw) return null
  const cleaned = raw.trim().toLowerCase().replace(/^language-/, "").replace(/^lang-/, "")
  const firstToken = cleaned.split(/[\s,{]/)[0]
  const mapped = LANG_ALIASES[firstToken] || firstToken
  return SUPPORTED_LANGS.has(mapped) ? mapped : null
}

export function resolveShikiLanguageFromPath(filePath: string): string | null {
  const fileName = filePath.split("/").pop() || filePath
  const ext = fileName.includes(".") ? fileName.split(".").pop()?.toLowerCase() : undefined
  return normalizeLanguage(ext)
}

export function resolveShikiLanguageFromInfoString(infoString?: string | null): string | null {
  return normalizeLanguage(infoString)
}

export async function highlightCodeToHtml(code: string, language: string): Promise<string> {
  const highlighter = await getHighlighter()
  return highlighter.codeToHtml(code, {
    lang: language,
    theme: "github-light-default"
  })
}
