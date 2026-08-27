import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-only: preview a `council draft` output locally without ever writing
// into the git-tracked frontend/public/data/ — set VITE_DRAFT_DIR to a
// draft run directory (e.g. `data/draft/cambridge/draft_20260810_065408`,
// relative to this directory) and snapshot fetches are served from there
// instead of the committed placeholder data. No-op for `vite build`
// (configureServer only runs under `vite dev`), so it can't leak into a
// production bundle. See docs/TESTING.md "Draft & publish workflow".
function draftPreview(): Plugin {
  const draftDir = process.env.VITE_DRAFT_DIR
  const root = draftDir ? resolve(process.cwd(), draftDir) : null
  return {
    name: 'draft-preview',
    configureServer(server) {
      if (!root) return
      if (!existsSync(root)) {
        server.config.logger.error(`[draft-preview] VITE_DRAFT_DIR not found: ${root}`)
        return
      }
      server.config.logger.warn(
        `\n[draft-preview] serving UNPUBLISHED draft data from ${root}\n` +
        `[draft-preview] this is not what's live — for local review only\n`
      )
      server.middlewares.use((req, res, next) => {
        const match = req.url?.match(/^\/data\/([\w-]+)\.json(?:\?.*)?$/)
        if (!match) return next()
        const file = resolve(root, `${match[1]}.json`)
        if (!existsSync(file)) return next()
        res.setHeader('Content-Type', 'application/json')
        res.setHeader('Cache-Control', 'no-store')
        res.end(readFileSync(file))
      })
    },
  }
}

// Dev-only: preview a `council meeting-digest --save` output locally, the
// same way draftPreview() previews a `council draft` run — set
// VITE_DIGEST_FILE to one saved digest file (e.g.
// `../data/meeting_digest_preview/cambridge/meeting_412.json`, relative to
// this directory) and it's served as /data/digest.json. Single file, not a
// directory, because a digest is scoped to one meeting. Never wired into
// `council draft`/`council publish` — see docs/frontend/PRODUCT_ROADMAP.md F2
// and `council meeting-digest`'s own docstring for why this stays local-only.
function digestPreview(): Plugin {
  const digestFile = process.env.VITE_DIGEST_FILE
  const file = digestFile ? resolve(process.cwd(), digestFile) : null
  return {
    name: 'digest-preview',
    configureServer(server) {
      if (!file) return
      if (!existsSync(file)) {
        server.config.logger.error(`[digest-preview] VITE_DIGEST_FILE not found: ${file}`)
        return
      }
      server.config.logger.warn(
        `\n[digest-preview] serving UNPUBLISHED meeting digest from ${file}\n` +
        `[digest-preview] this is a review artifact only — never published\n`
      )
      server.middlewares.use((req, res, next) => {
        if (req.url?.split('?')[0] !== '/data/digest.json') return next()
        res.setHeader('Content-Type', 'application/json')
        res.setHeader('Cache-Control', 'no-store')
        res.end(readFileSync(file))
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), draftPreview(), digestPreview()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
