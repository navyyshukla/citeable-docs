# S1: `stable` docs vs the published site; command reference

Run 2026-10-18 with `spikes/s1_sources.py` against `saulpw/visidata`. Tarballs are cached in `spikes/.cache/` (gitignored; never committed).

## Results

### (a) Does `stable` match the published headings? Yes for 2 of 3 pages

| Page | `stable` vs published site | Notes |
|---|---|---|
| `join` | match | Published adds only site chrome: "combining datasets" (page title) and "corporate sponsors" (sidebar) |
| `rows` | match | Same site-chrome extras |
| `columns` | **one section behind** | Published and `develop` both have the heading "increment by key"; `stable` does not. Also a cosmetic Markdown artifact in `stable` (`**month/day/year**` inside a heading) |

Decision rule from the plan: `stable` matches the published site on 2 or more of 3 pages, so **ingest `stable`**.

### (b) File counts: `stable` 32, `develop` 32
Same file list, but **13 of 32 files differ in content** (`README`, `columns`, `customize`, `formats`, `graph`, `group`, `internal_formats`, `join`, `loading`, `navigate`, `plugins`, `save-restore`, `usage`). The 3-page heading test only sees headings, so differences in body text are not measured here. The `columns` result shows the published site is built from something newer than `stable` for at least one section.

### (c) Where the command reference lives
- There is **no ready-made command-reference file** in the docs folder.
- Docs and guides contain runtime placeholders like `{help.commands.exec_longname}` (for example `visidata/guides/CommandsSheet.md`). These are filled in by VisiData itself, not stored as text.
- Candidates found in the repo (content not yet read or judged):
  - `visidata/man/vd.inc` (man page source) and `visidata/man/parse_options.py`
  - `docs/api/commands.rst`
  - `visidata/guides/*.md` (25 in-app guides, e.g. `ColumnsGuide.md`, `SortGuide.md`)
- Published man page: https://www.visidata.org/man/ (HTTP 200). `https://www.visidata.org/guide/` returned 404, so the guides are not published under that path.
- Fetchable the same way as the docs (same tarball). Whether it is good retrieval material is a Plan 2 question.

### (d) The correct `ref`
`stable` (the tarball download worked; no 404). Release tags exist (latest seen in `git ls-remote`: `v3.4`). A tag would be reproducible, while `stable` moves when upstream moves.

### Published URL pattern
`https://www.visidata.org/docs/<stem>/`, from the file name without `.md` (confirmed for `join`, `columns`, `rows`). `docs/index` maps to the docs root (assumed, matches Task 9's test; check when Task 9 runs).

## Things to carry into later tasks
- **Task 7 (cleaner):** `{help.*}` placeholders also appear **inline in list items** (`- {help.commands.exec_longname}`), not only on their own line. The plan's regex only removes whole-line placeholders, so inline ones would stay in the text. Add a test with a real inline example before Task 7.
- **Task 8 (chunker):** the `columns.md` heading with `**...**` inside it shows headings can carry Markdown emphasis; strip it when building anchors and titles.
- **Task 9 (fetch):** the `develop`/`stable` content gap above means anchors in our citation links may occasionally not exist on the published page. Citation links to a heading that is only in `develop` would break.

## Not measured
- Body-text differences between `stable`, the published site and the latest tag.
- Whether a release tag would match the published site better than `stable`.
- The quality of the command-reference candidates.
