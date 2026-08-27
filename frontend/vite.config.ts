import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-only: overlay a `council draft` run's snapshots at /data/draft/<name>.json,
// alongside the committed Publish snapshots at /data/<name>.json (plain static
// files, unaffected by this plugin). frontend/src/api.ts's getSnapshot() picks
// the prefix at fetch time from frontend/src/devMode.ts's persisted mode, so
// the frontend/src/components/DevModeSwitch.tsx corner switch can flip between
// them with a page reload — no env var, no dev-server restart. No-op under
// `vite build` (configureServer only runs under `vite dev`), so it can't leak
// into a production bundle. See docs/TESTING.md "Draft & publish workflow".
//
// Directory resolved PER REQUEST (not once at plugin construction, the way the
// old env-var-only draftPreview()/digestPreview() plugins did — that's exactly
// what made them require a restart to point at a new run) so a fresh
// `council draft` is picked up live.
function findLatestDraftDir(council: string): string | null {
  // Pin to a specific run when set — useful for reviewing the run Editor
  // actually flagged, which stops being "latest" the instant you re-draft.
  const pinned = process.env.VITE_DRAFT_DIR
  if (pinned) return resolve(process.cwd(), pinned)

  const base = resolve(process.cwd(), `../data/draft/${council}`)
  if (!existsSync(base)) return null
  // manifest.json is the on-disk marker that a run cleared the S7 invariant
  // gate (cmd_draft only writes it after gate.passed) — without this filter
  // the overlay would happily serve a gate-blocked draft.
  const runs = readdirSync(base)
    .filter(d => d.startsWith('draft_') && existsSync(resolve(base, d, 'manifest.json')))
    .sort() // draft_YYYYMMDD_HHMMSS sorts newest-last lexicographically
  return runs.length ? resolve(base, runs[runs.length - 1]) : null
}

function draftOverlay(): Plugin {
  return {
    name: 'draft-overlay',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const match = req.url?.match(/^\/data\/draft\/([\w-]+)\.json(?:\?.*)?$/)
        if (!match) return next()
        const dir = findLatestDraftDir('cambridge') // single council today, matches CouncilHeader's hardcoded <select>
        if (!dir) return next()
        const name = match[1]
        // The digest lands in a local/ subdirectory (src/cli.py's cmd_draft),
        // deliberately outside manifest.snapshots and Editor's *.json scope —
        // see docs/review/editor/Editor_prompt.txt's `local/` exclusion.
        const file = name === 'digest' ? resolve(dir, 'local', 'digest.json') : resolve(dir, `${name}.json`)
        if (!existsSync(file)) return next()
        res.setHeader('Content-Type', 'application/json')
        res.setHeader('Cache-Control', 'no-store')
        res.end(readFileSync(file))
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), draftOverlay()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
