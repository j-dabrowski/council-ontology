import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-only: overlay a `council draft` run's snapshots at
// /data/draft/<council>/<name>.json, alongside the committed Publish
// snapshots at /data/<council>/<name>.json (plain static files, unaffected
// by this plugin). frontend/src/api.ts's getSnapshot() picks the prefix at
// fetch time from frontend/src/devMode.ts's persisted mode, so the
// frontend/src/components/DevModeSwitch.tsx corner switch can flip between
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
  // A pin is global (not per-council): whichever council that run's own
  // manifest.json names is the only one Draft mode will resolve while pinned.
  const pinned = process.env.VITE_DRAFT_DIR
  if (pinned) {
    const dir = resolve(process.cwd(), pinned)
    if (!existsSync(resolve(dir, 'manifest.json'))) return null
    const manifest = JSON.parse(readFileSync(resolve(dir, 'manifest.json'), 'utf-8'))
    return manifest.council === council ? dir : null
  }

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

// The mode-dependent council list's Draft-mode source (SECOND_COUNCIL_PLAN.md
// Phase 2.5) — every council under data/draft/ with at least one
// gate-passing run, Testville included (this is the one place Testville is
// meant to be selectable: a dev-only middleware `vite build` never runs).
// Served at the fixed path /data/draft/councils.json, which the per-council
// `([\w.-]+)/([\w./-]+)\.json` pattern below can't ever match (no "/" in
// "councils" itself), so the two routes can't collide.
interface DraftCouncilEntry {
  key: string
  run_id: string
  generated_at: string
  // From manifest.json's own short_name/display_name/name_prefix/
  // name_suffix/source_url (src/cli.py's cmd_draft, sourced from the
  // COUNCILS registry) — this plugin is plain Node/TS, it can't import that
  // Python dict directly, so the manifest carries them instead of the
  // frontend selector falling back to the raw key ("cambridge" instead of
  // "Town of Cambridge"). Optional: a manifest written before these fields
  // existed just falls back to the key on the frontend side.
  short_name?: string
  display_name?: string
  name_prefix?: string
  name_suffix?: string
  source_url?: string | null
}

function listDraftCouncils(): DraftCouncilEntry[] {
  const pinned = process.env.VITE_DRAFT_DIR
  if (pinned) {
    const dir = resolve(process.cwd(), pinned)
    const manifestPath = resolve(dir, 'manifest.json')
    if (!existsSync(manifestPath)) return []
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'))
    return [{
      key: manifest.council, run_id: manifest.run_id, generated_at: manifest.generated_at,
      short_name: manifest.short_name, display_name: manifest.display_name,
      name_prefix: manifest.name_prefix, name_suffix: manifest.name_suffix,
      source_url: manifest.source_url,
    }]
  }

  const draftRoot = resolve(process.cwd(), '../data/draft')
  if (!existsSync(draftRoot)) return []
  return readdirSync(draftRoot)
    .map(council => ({ council, dir: findLatestDraftDir(council) }))
    .filter((x): x is { council: string; dir: string } => x.dir !== null)
    .map(({ council, dir }) => {
      const manifest = JSON.parse(readFileSync(resolve(dir, 'manifest.json'), 'utf-8'))
      return {
        key: council, run_id: manifest.run_id, generated_at: manifest.generated_at,
        short_name: manifest.short_name, display_name: manifest.display_name,
        name_prefix: manifest.name_prefix, name_suffix: manifest.name_suffix,
        source_url: manifest.source_url,
      }
    })
}

// The two cross-council boundary layers council publish writes at the top
// of frontend/public/data/ (MAP_PAGE_PLAN.md Phase 3.3) — config-sourced,
// not draft output, so they carry no review risk and don't belong behind
// the Draft/Publish toggle the way a council's own snapshots do. Without
// this, MapPage's fixed /data/wa_lga_backdrop.geojson and
// /data/councils.geojson fetches would 404 in local dev until someone ran
// a real `council publish` — which shouldn't be a prerequisite for
// reviewing the map locally, any more than reviewing any other snapshot
// is. Served straight from config/ whenever the real published copy isn't
// there yet; once a real publish exists, that committed file wins (this
// only ever fills the gap before the first one, never shadows it).
const CONFIG_ROOT = resolve(__dirname, '../config')
const PUBLIC_DATA_ROOT = resolve(__dirname, 'public/data')

function serveBackdropFromConfig(res: import('node:http').ServerResponse): boolean {
  const configPath = resolve(CONFIG_ROOT, 'wa_lga_backdrop.geojson')
  if (!existsSync(configPath)) return false
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Cache-Control', 'no-store')
  res.end(readFileSync(configPath))
  return true
}

function serveCouncilsGeojsonFromConfig(res: import('node:http').ServerResponse): boolean {
  const boundaryDir = resolve(CONFIG_ROOT, 'council_boundaries')
  if (!existsSync(boundaryDir)) return false
  const features = readdirSync(boundaryDir)
    .filter(f => f.endsWith('.geojson'))
    .map(f => JSON.parse(readFileSync(resolve(boundaryDir, f), 'utf-8')))
  res.setHeader('Content-Type', 'application/json')
  res.setHeader('Cache-Control', 'no-store')
  res.end(JSON.stringify({ type: 'FeatureCollection', features }))
  return true
}

function draftOverlay(): Plugin {
  return {
    name: 'draft-overlay',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url === '/data/wa_lga_backdrop.geojson'
          && !existsSync(resolve(PUBLIC_DATA_ROOT, 'wa_lga_backdrop.geojson'))) {
          if (serveBackdropFromConfig(res)) return
        }
        if (req.url === '/data/councils.geojson'
          && !existsSync(resolve(PUBLIC_DATA_ROOT, 'councils.geojson'))) {
          if (serveCouncilsGeojsonFromConfig(res)) return
        }

        if (req.url === '/data/draft/councils.json') {
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-store')
          res.end(JSON.stringify(listDraftCouncils()))
          return
        }

        // [\w./-]+ (not [\w-]+) — an evidence/*.json snapshot name has both
        // a "/" and a "." in it before the extension (e.g.
        // "evidence/governance.incumbency"); the narrower class silently
        // missed every one of those, falling through to Vite's SPA
        // index.html fallback instead of the real file — a "." alone
        // wasn't enough to fix (still no "/"), nor was "/" alone (still no
        // "."; test_id-shaped names like "governance.incumbency" have one
        // even without the "evidence/" prefix). Found while verifying
        // RECORD_PAGE_PLAN.md Step 8 in Draft mode — every evidence-chain
        // drill-down built so far (DivergencePanel included) was hitting
        // this same gap in local dev, just unnoticed until now.
        const match = req.url?.match(/^\/data\/draft\/([\w.-]+)\/([\w./-]+)\.json(?:\?.*)?$/)
        if (!match) return next()
        const [, council, name] = match
        const dir = findLatestDraftDir(council)
        if (!dir) return next()
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
  resolve: {
    alias: {
      // config/test_registry.json is council-agnostic and read by both the
      // Python battery (src/test_registry.py) and the frontend — this alias
      // is how the frontend reaches the one copy instead of a duplicated one
      // inside frontend/. See docs/frontend/TEST_REGISTRY_PLAN.md Step 1.
      '@registry': resolve(__dirname, '../config/test_registry.json'),
      // Pattern data for the private-name redactor (RECORD_PAGE_PLAN.md
      // B.1) — read by src/privacy.py too, so both implementations build
      // their regexes from one definition instead of a hand-copied one
      // that can drift. See frontend/src/guardrail.tsx.
      '@patterns': resolve(__dirname, '../config/private_name_patterns.json'),
    },
  },
  server: {
    fs: {
      allow: ['..'],
    },
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
