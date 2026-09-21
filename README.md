# ScholarForge AI

Built from `docs/blueprint_v3.md`.

| Path | What it is | Verified |
|---|---|---|
| `docs/ARCHITECTURE.md` | Specification, status table, risks | n/a |
| `tools/verify_output.py` | Quality gate: style, citations, cross-refs, overlap, optional link audit | 8 tests pass |
| `prototype/` | Python core: ingest, hybrid search, CSL, integrity, provenance, router, LLM providers, block generation, CLI | 17 tests pass |
| `app/` | Tauri 2 + React + TypeScript scaffold with routing UI and Rust commands | Not compiled (no Rust toolchain or network in the build sandbox) |

## Run the prototype
```bash
cd prototype
python -m unittest discover -s tests
python -m scholarforge.cli ingest ./my_sources
python -m scholarforge.cli search "memory consolidation"
python -m scholarforge.cli check draft.md --csl refs.json --sources ./my_sources

# Generate a block. Local model: start `llama-server -m model.gguf --port 8080` first.
# Cloud (submission tier, online): export ANTHROPIC_API_KEY=...
python -m scholarforge.cli draft "Results" "Summarize recall findings" --csl refs.json --tier submission
```
PDF support: `pip install pypdf`.

## Verify a draft
```bash
python tools/verify_output.py draft.md --sources ./sources --prior-work ./old_chapters [--check-links] [--json]
```

## Run the app
```bash
cd app
npm install
npx tauri icon path/to/icon.png   # generates src-tauri/icons
npm run tauri dev
```
`npm run dev` alone runs the UI in a browser with mock data.

## Not built yet
LanceDB, real embeddings, draft version history, cross-reference renumbering, and the Pandoc/Typst export pipeline. The Python LLM layer is not yet connected to the Tauri UI. Each is specified in `docs/ARCHITECTURE.md`.
