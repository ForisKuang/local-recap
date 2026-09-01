---
name: local-recap
description: Build a fully local, interactive PR/diff recap with a live click-to-context chat panel answered by the running Claude Code session, per-line annotation hover markers, right-click "view exact source lines on GitHub" links, and an optional "comment on PR" flow that posts real PR comments via the authenticated `gh` CLI. No hosted Plan viewer, no Claude Artifacts, no API key. Use when the user wants to interrogate a PR (e.g. "what does this table/function/field actually mean") or leave review comments through a page instead of chat, entirely on localhost.
---

# local-recap

A localhost sibling of `/visual-recap`. Same idea -- turn a diff into a
structured, reviewable page -- but rendered as a page **we** own instead of
the hosted Plan viewer, so it can carry a live chat rail. The chat is powered
by the Claude Code session that built the page, not an API key: the browser
talks to a tiny local server, the server queues the question, the agent
(watching the queue) answers it by actually reading the code, and the page
polls for the reply.

Reach for this instead of `/visual-recap` when the user explicitly wants to
*ask questions about* the PR through the page itself -- not just read a
summary. Reach for `/visual-recap` when a standard shareable recap is enough;
it has the polished ERD/diff renderers this skill hand-rolls in plain HTML.

## Why this exists / what it trades away

`/visual-recap` always publishes through the hosted Plan MCP
(`plan.agent-native.com`) or, in local-files mode, still renders through that
hosted viewer over a local data bridge -- the *renderer* is never local, only
the *content*. There is no downloadable copy of that renderer to self-host.
Claude Artifacts' `sample` capability gives a page live Claude chat, but only
when served through claude.ai's Artifact viewer -- not a bare local file --
and it bills per call.

This skill trades the polished block renderers (ERD, diff viewer, comment
system) for full locality and zero external dependency: everything is one
static HTML page plus a stdlib-only Python server, and the "model" answering
questions is literally the agent that built the page. The real cost: answers
only arrive while a Claude Code session is actively watching the queue. This
is a personal/dev tool, not a service you leave running unattended.

## Workflow

1. **Gather the diff exactly like `/visual-recap` does.** Fetch PR metadata
   (`gh pr view <n> --json ...`), clone/checkout the branch, diff against the
   real base/head SHAs, and read the actual changed files -- never paraphrase
   from the PR description. Reuse `recap collect-diff` from
   `@agent-native/recap-cli` if convenient, or just `git diff`/`gh pr diff`.
   Ground every fact the page states in text you actually read.

2. **Author `index.html` as one self-contained page.** Use the shared
   design/content discipline from `visual-recap` (see below for what to keep),
   but hand-render every block in plain HTML/CSS -- there is no MDX block
   library here:
   - Narrative section: what changed and why, grounded in the diff.
   - File tree with change badges.
   - Data model as plain cards (entity name, fields, PK/FK flags) if the diff
     touches schema -- reproduce real column names/types, never invent them.
   - Diffs/new files as syntax-colored `<pre>` blocks (before/after side by
     side for real diffs, single block for new files).
   - **Syntax-highlight code like an IDE, not just diff-colored.** A single
     flat text color per line (only red/green for del/add) is hard to scan --
     readers expect keywords, strings, comments, and numbers to differ in
     color the way an editor renders them. No CDN highlighter is allowed
     (locality is the whole point of this skill), so hand-roll a small
     regex tokenizer inline in the page instead of pulling in highlight.js/
     Prism. Pattern: one `RegExp` per language with named capture groups per
     token class, scanned with `exec`+`lastIndex` so unmatched text passes
     through escaped and matched text gets wrapped in a `<span
     class="tok-...">`:
     ```js
     const LANG_REGEX = {
       python: /(?<com>#.*)|(?<str>"""[^]*?"""|'''[^]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(?<num>\b\d+\.?\d*\b)|(?<deco>@\w+)|(?<kw>\b(?:def|class|import|from|as|return|if|elif|else|for|while|in|not|and|or|is|None|True|False|try|except|finally|raise|with|lambda|yield|pass|break|continue|self|cls)\b)|(?<fn>\b[A-Za-z_]\w*(?=\())/g,
       sql: /(?<com>--.*)|(?<str>'(?:[^'\\]|\\.)*')|(?<num>\b\d+\.?\d*\b)|(?<kw>\b(?:SELECT|FROM|WHERE|CREATE|ROW|POLICY|USING|TO|AS|JOIN|GROUP|BY|LIMIT)\b)|(?<fn>\b[A-Za-z_]\w*(?=\())/gi,
       // add js, json, bash, yaml (or whatever languages the diff actually touches) the same way
     };
     function tokenize(line, lang) {
       const re = LANG_REGEX[lang];
       if (!re) return escHtml(line);
       re.lastIndex = 0;
       let out = "", last = 0, m;
       while ((m = re.exec(line))) {
         if (m.index > last) out += escHtml(line.slice(last, m.index));
         const cls = Object.keys(m.groups).find(k => m.groups[k] !== undefined);
         out += `<span class="tok-${cls}">${escHtml(m[0])}</span>`;
         last = re.lastIndex;
         if (m[0].length === 0) re.lastIndex++;   // guard against zero-width matches
       }
       out += escHtml(line.slice(last));
       return out;
     }
     ```
     Only build regexes for languages the actual diff touches (check file
     extensions first) -- don't pre-write a library of languages nobody
     needs. Derive `lang` from the file extension (`.py` -> `python`, `.sql`
     -> `sql`, etc.) and call `tokenize(text, lang)` in place of `escHtml(text)`
     wherever a code/diff line is rendered; for diff lines, tokenize only the
     text *after* the leading `+`/`-`/space marker so the marker itself stays
     plain. Give each token class its own CSS color (`.tok-kw`, `.tok-str`,
     `.tok-com` italic, `.tok-num`, `.tok-fn`, `.tok-deco`, plus `.tok-key`/
     `.tok-flag` for YAML keys / shell flags if needed) -- since the code
     block background is conventionally dark regardless of page theme, one
     palette works for both light and dark page themes; just make sure it
     contrasts against `--code-bg`. This is intentionally a "good enough"
     line-by-line tokenizer, not a real parser -- multi-line constructs (e.g.
     a Python triple-quoted string spanning several lines) only get colored
     correctly on the line where both delimiters appear together, which is
     an acceptable tradeoff for a recap page.
   - Architecture diagram as simple flex/grid boxes if the diff is
     structural -- see `visual-plan`'s `references/wireframe.md` for the
     `--wf-*` token discipline; reuse that palette approach here even though
     this isn't the Plan renderer.
   - **Every block that could prompt a question is clickable.** Give it
     `data-ctx-title` and `data-ctx-body` attributes with real content (the
     table's real columns, the file's real diff, the node's real label).
     Left-click adds it as a removable chip above the chat input; the chip's
     `title`/`body` gets sent as `context` on the next question or comment.
   - **Right-click gives a custom context menu**, not the browser default:
     "Add to chat context" (same as left-click) and "View source on GitHub"
     (only enabled when the block has a `data-src-url`). Wire `contextmenu`
     with `preventDefault()`, position the menu at the cursor, close on
     outside-click/Escape.
   - **Every block's `data-src-url` must be a real, computed GitHub link**,
     never guessed. Two forms, both grounded in facts you already have from
     step 1:
     - Exact lines you can point to (a CREATE TABLE block, a specific
       function) -> a blob link at the head SHA:
       `https://github.com/<repo>/blob/<head_sha>/<path>#L<start>-L<end>`.
       Compute the line range by grepping the real file for the block's
       start/end, never estimate.
     - A whole changed file (a diff tab, a file-tree row) -> deep-link into
       the PR's Files-changed tab: `https://github.com/<repo>/pull/<pr>/files#diff-<sha256-hex-of-path>`.
       That `sha256(path).hexdigest()` anchor format is a stable, documented
       GitHub convention -- compute it, don't hand-roll a different hash.
   - **Per-line annotations, hover-tooltip style** (carried over from the
     Plan renderer's ERD/diff annotations): give diff/code blocks an
     `annotations` list of `{lines: "20" | "29-35", side?: "before"|"after",
     label, note}`, grounded in something actually true about those lines
     (a real bug, a real design choice visible in the code -- never a
     restatement of what the line obviously does). Render client-side: track
     old/new line numbers while walking the raw text (parse `@@ -a,b +c,d @@`
     hunk headers for diffs; for a whole new file the line number is just the
     1-based index), highlight matching lines, and put a small numbered
     marker with a `title` tooltip on the first line of each range.
   - **A persistent chat rail** with two explicit modes -- "Ask Claude" and
     "Comment on PR" -- never blended into one button, since one is free/local
     and the other is a real public GitHub write:
     - Ask: `fetch('/ask', {method:'POST', body: JSON.stringify({question,
       context})})` returns `{id}`; poll `GET /answer/<id>` every ~1.2s until
       `{status:"done", answer}`.
     - Comment: typing + hitting send NEVER posts directly. It opens an
       in-page confirmation panel showing the exact comment body and which
       blocks are attached, with explicit Cancel/Post buttons -- posting is a
       real, hard-to-reverse, publicly-visible action, and the confirmation
       step is the safety gate, not the send click. Only on explicit confirm:
       `fetch('/comment', {method:'POST', body: JSON.stringify({comment,
       context})})`. Show the returned comment URL on success, the error
       inline on failure.
   - Follow `artifact-design` fundamentals for the visual system (both
     themes via `--wf-*`-style tokens, real typefaces, no lorem) even though
     this never goes through the Artifact tool -- it's still a page someone
     looks at.
   - **HTML-attribute escaping for embedded JSON**: any `data-*` attribute
     that carries JSON (raw diff text, annotations list) must be built with
     `json.dumps(...)` and then **HTML-escaped again** (`html.escape(...,
     quote=True)`) before insertion, regardless of whether the attribute is
     single- or double-quoted. Skipping the second escape breaks the instant
     a value contains an apostrophe (a Go comment, "doesn't", "won't") --
     `JSON.parse` throws, and depending on where, the rest of the page's
     script silently stops running. `element.getAttribute(...)` HTML-decodes
     automatically, so `JSON.parse` on the client side needs no extra work.

3. **Write `<content-dir>/recap.json`** with `{"repo": "<owner>/<name>", "pr":
   <number>}`. This enables the `/comment` endpoint -- omit it (or omit the
   `pr`/`repo` keys) to leave "Comment on PR" disabled with a clear error
   rather than guessing a target repo.

4. **Locate `server.py`, then start it.** This skill can be installed either
   personally (`~/.claude/skills/local-recap/`) or per-project
   (`<repo>/.claude/skills/local-recap/`), so never hardcode the personal
   path -- resolve it fresh each run by checking, in order: each ancestor of
   the current directory from `$PWD` up to `/` for
   `.claude/skills/local-recap/scripts/server.py`, then falling back to
   `~/.claude/skills/local-recap/scripts/server.py`. One-liner:
   ```bash
   SERVER_PY=$(d="$PWD"; while [ "$d" != "/" ]; do
     f="$d/.claude/skills/local-recap/scripts/server.py"
     [ -f "$f" ] && echo "$f" && break
     d=$(dirname "$d")
   done)
   [ -z "$SERVER_PY" ] && SERVER_PY="$HOME/.claude/skills/local-recap/scripts/server.py"
   ```
   Then `python3 "$SERVER_PY" <content-dir> [port]` in the background
   (`run_in_background: true`). Pick an actually-free port first (`lsof -i
   :<port>` before binding) -- sandboxed dev environments often already
   occupy common ports like 8765 with an unrelated proxy, and the failure
   mode (connection refused, or worse, a stray unrelated service answering)
   is confusing to debug after the fact. The server serves `index.html` at
   `/`, `POST /ask` + `GET /answer/<id>` backed by `<content-dir>/queue/`,
   and `POST /comment` (shells out to `gh pr comment <pr> -R <repo> -F -`,
   using whatever `gh` account is already authenticated -- never store or
   ask for a token). Report the `http://127.0.0.1:<port>` URL and open it if
   a browser tool is available.

5. **Watch the queue.** Start a `Monitor` with
   `persistent: true` on:
   ```
   tail -F <content-dir>/queue/questions.jsonl
   ```
   Each new line is one notification carrying that question's JSON. Do not
   use a bounded/default-timeout monitor -- the whole point is this stays
   armed for the rest of the session.

6. **Answer each question as it arrives.** Parse the notification line
   (`{id, ts, question, context}`). Investigate for real -- grep the cloned
   repo, read the actual file, don't guess from the table/column name alone.
   Write the answer to `<content-dir>/queue/answers/<id>.json` as
   `{"id": "...", "answer": "..."}`. The page's poll picks it up on its own;
   no need to notify the user in chat unless the answer is itself
   noteworthy.

7. **Never fire a live "Comment on PR" test yourself.** Verify the flow up to
   the confirmation panel (right context, right body, right repo#pr) and stop
   there -- posting is the user's action to authorize, not something to
   rehearse against a real, possibly-shared PR. If you want to prove the
   round trip works, ask the user first.

8. **Tell the user the tradeoff up front** if not already established this
   session: chat answers land only while a Claude Code session is watching
   the queue -- close the session and chat goes silent until one reattaches
   (same `content-dir`, rerun step 4+5). "Comment on PR" is different: it
   only needs the local *server* process alive (it shells out to `gh`
   synchronously, no agent involved), so it keeps working even with no
   Claude Code session watching, as long as `server.py` itself is still
   running.

## Design notes carried over from `visual-recap`

- **Grounding rule applies identically**: every fact on the page and every
  chat answer must come from text actually read (diff, file, schema) --
  never inferred or invented. Mark genuine inference as inference.
- **Redact secrets** the same way: no real credentials/tokens in the page,
  obviously-fake placeholders only.
- Keep the page lean -- don't pad with boilerplate about what the page is;
  the narrative should say what changed and why, nothing else.

## Layout gotchas

`position: sticky` on the chat rail does not reliably stay pinned once the
main column grows past a few screens of content in a plain two-column
document flow. Use `position: fixed; top: 0; right: 0; height: 100vh` for
the rail instead, with `margin-right: <rail-width>` on the main column (and
drop both to normal flow under the mobile breakpoint). Don't spend time
debugging why `sticky` "isn't sticking" -- just use `fixed`.

**Don't put `margin-right: <rail-width>` on the same element you're also
centering with `margin: 0 auto`.** `margin: 0 auto` sets the left margin to
`auto`; a later `margin-right: <rail-width>` only overrides the right side,
leaving the left `auto`. On a normal-width screen this looks fine by
accident, but on a large/ultra-wide monitor the `auto` left margin balloons
to fill all the leftover space, so the content column drifts to hug the
rail's left edge with a large dead gap on the left instead of staying
centered in the space left of the rail -- the exact "not responsive on a
larger screen" symptom. Put the rail-width offset on the *outer* flex
container instead, and let the main column center inside that already-
narrowed box:

```css
.layout { display: flex; margin-right: <rail-width>; }  /* offset lives here */
.main {
  flex: 1;
  min-width: 0;
  max-width: <content-max-width>;
  margin: 0 auto;                                        /* pure centering */
  padding: 56px 40px 120px;
}
.rail { position: fixed; top: 0; right: 0; width: <rail-width>; height: 100vh; }
```

This keeps `.main` centered in the viewport-minus-rail region at every
viewport width, rather than centered in the full viewport (which is wrong
because the rail eats the right side) or anchored to one edge (which is
what the combined-margin bug produces). Verify by actually resizing the
browser window wide, not just eyeballing the default size -- this bug is
invisible at typical laptop widths and only shows up past roughly 1600px.
