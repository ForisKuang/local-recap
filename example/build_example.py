"""Generic, fictional example: run this to see the recap format without any
real repo's data. `python3 build_example.py` writes ./output/index.html and
./output/recap.json, ready to serve:

    python3 ../scripts/server.py output 8990

This is a template to copy, not a tool to import -- for a real PR, gather the
real diff first (see SKILL.md step 1) and adapt the data below to match.
"""
import hashlib
import html
import json
from pathlib import Path

OUT_DIR = Path("output")
OUT = OUT_DIR / "index.html"

# Fictional -- there is no acme/widget-api repo. Leave REPO as None to
# disable "View source on GitHub" links and the /comment endpoint, exactly
# like server.py does automatically when recap.json is absent. Set REPO to
# a real "owner/name" once you've pointed this at an actual PR.
REPO = None
PR_NUMBER = None
HEAD_SHA = "0000000000000000000000000000000000000000"


def gh_diff_url(path):
    if not REPO:
        return None
    digest = hashlib.sha256(path.encode()).hexdigest()
    return f"https://github.com/{REPO}/pull/{PR_NUMBER}/files#diff-{digest}"


def gh_blob_url(path, start=None, end=None):
    if not REPO:
        return None
    url = f"https://github.com/{REPO}/blob/{HEAD_SHA}/{path}"
    if start:
        url += f"#L{start}" + (f"-L{end}" if end and end != start else "")
    return url


FILES = {
    "middleware": {
        "filename": "middleware/ratelimit.go",
        "kind": "diff",
        "summary": "Wraps every handler with a Redis-backed token bucket check; 429s once a key's bucket is empty.",
        "content": (
            "@@ -1,6 +1,24 @@\n"
            " package middleware\n"
            " \n"
            " import (\n"
            "+\t\"net/http\"\n"
            "+\n"
            "+\t\"acme/widget-api/ratelimit\"\n"
            " )\n"
            "+\n"
            "+func RateLimit(limiter *ratelimit.Limiter) func(http.Handler) http.Handler {\n"
            "+\treturn func(next http.Handler) http.Handler {\n"
            "+\t\treturn http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {\n"
            "+\t\t\tkey := apiKeyFromRequest(r)\n"
            "+\t\t\tallowed, err := limiter.Allow(r.Context(), key)\n"
            "+\t\t\tif err != nil {\n"
            "+\t\t\t\t// fail open: a Redis outage shouldn't take down the API\n"
            "+\t\t\t\tnext.ServeHTTP(w, r)\n"
            "+\t\t\t\treturn\n"
            "+\t\t\t}\n"
            "+\t\t\tif !allowed {\n"
            "+\t\t\t\thttp.Error(w, \"rate limit exceeded\", http.StatusTooManyRequests)\n"
            "+\t\t\t\treturn\n"
            "+\t\t\t}\n"
            "+\t\t\tnext.ServeHTTP(w, r)\n"
            "+\t\t})\n"
            "+\t}\n"
            "+}"
        ),
        "annotations": [
            {"lines": "12-15", "label": "Fails open", "note": "A Redis error lets the request through rather than blocking it -- a deliberate availability-over-strictness tradeoff worth flagging to reviewers, not just a leftover TODO."},
        ],
    },
    "limiter": {
        "filename": "ratelimit/limiter.go",
        "kind": "code",
        "summary": "New file: the actual token-bucket logic against Redis.",
        "content": (
            "package ratelimit\n\n"
            "import (\n"
            "\t\"context\"\n\n"
            "\t\"github.com/redis/go-redis/v9\"\n"
            ")\n\n"
            "type Limiter struct {\n"
            "\tclient     *redis.Client\n"
            "\tbucketSize int\n"
            "\twindow     int // seconds\n"
            "}\n\n"
            "func (l *Limiter) Allow(ctx context.Context, key string) (bool, error) {\n"
            "\tcount, err := l.client.Incr(ctx, \"rl:\"+key).Result()\n"
            "\tif err != nil {\n"
            "\t\treturn false, err\n"
            "\t}\n"
            "\tif count == 1 {\n"
            "\t\tl.client.Expire(ctx, \"rl:\"+key, secondsToDuration(l.window))\n"
            "\t}\n"
            "\treturn count <= int64(l.bucketSize), nil\n"
            "}"
        ),
    },
    "gomod": {
        "filename": "go.mod",
        "kind": "diff",
        "summary": "Adds the Redis client as a new dependency.",
        "content": (
            "@@ -4,6 +4,7 @@ go 1.22\n"
            " \n"
            " require (\n"
            "+\tgithub.com/redis/go-redis/v9 v9.5.1\n"
            "\tgithub.com/go-chi/chi/v5 v5.0.12\n"
            " )"
        ),
    },
}
for f in FILES.values():
    f["src"] = gh_diff_url(f["filename"])

DATA_MODEL = [
    {
        "name": "rate_limit_bucket",
        "change": "added",
        "fields": [
            ("key", "varchar(255)", "PK"),
            ("count", "int", ""),
            ("window_start", "timestamp", ""),
        ],
        "src": None,
    },
    {
        "name": "api_key",
        "change": "modified",
        "fields": [
            ("id", "bigint", "PK"),
            ("key_hash", "varchar(255)", ""),
            ("rate_limit_tier", "varchar(32)", "added this PR"),
        ],
        "src": None,
    },
]

RELATIONS = [
    ("api_key", "1:n", "rate_limit_bucket", "keyed by api_key.key_hash"),
]

FILE_TREE = [
    ("middleware/ratelimit.go", "modified", "Wires the new middleware into the handler chain."),
    ("ratelimit/limiter.go", "added", "Token-bucket logic against Redis."),
    ("ratelimit/limiter_test.go", "added", "Unit tests with a miniredis fake."),
    ("go.mod", "modified", "Adds github.com/redis/go-redis/v9."),
    ("go.sum", "modified", "Checksums for the new dependency."),
]

ARCH = {
    "request": {
        "label": "Request path",
        "nodes": [
            ("HTTP request", "with API key"),
            ("RateLimit middleware", "wraps every handler"),
            ("Limiter.Allow(ctx, key)", "INCR + EXPIRE"),
            ("Redis", "rl:<key> counter"),
            ("200 or 429", ""),
        ],
    },
}


def esc(s):
    return html.escape(s, quote=True)


def ctx_attrs(title, body, src=None):
    attrs = f'data-ctx-title="{esc(title)}" data-ctx-body="{esc(body)}"'
    if src:
        attrs += f' data-src-url="{esc(src)}"'
    return attrs


def render_data_model():
    out = []
    for e in DATA_MODEL:
        field_rows = "\n".join(
            f'<div class="field-row"><span class="fname">{esc(n)}</span><span class="ftype">{esc(t)}</span><span class="fflag">{esc(f)}</span></div>'
            for n, t, f in e["fields"]
        )
        body_text = f"Table `{e['name']}`\n" + "\n".join(f"  {n} {t} {f}".rstrip() for n, t, f in e["fields"])
        out.append(f'''
        <div class="entity-card" tabindex="0" {ctx_attrs(f"table `{e['name']}`", body_text, e.get("src"))}>
          <div class="entity-head"><span class="entity-name">{esc(e['name'])}</span><span class="pill pill-{e['change']}">{e['change']}</span></div>
          <div class="entity-fields">{field_rows}</div>
        </div>''')
    return "\n".join(out)


def render_relations():
    out = []
    for a, kind, b, label in RELATIONS:
        label_html = f'<span class="rel-label">{esc(label)}</span>' if label else ""
        out.append(f'<div class="rel-row"><span class="rel-ent">{esc(a)}</span><span class="rel-kind">{esc(kind)}</span><span class="rel-ent">{esc(b)}</span>{label_html}</div>')
    return "\n".join(out)


def render_file_tree():
    out = []
    for path, change, note in FILE_TREE:
        out.append(f'''<div class="tree-row" tabindex="0" {ctx_attrs(path, f"{path} ({change}): {note}", gh_diff_url(path))}>
          <span class="tree-path">{esc(path)}</span>
          <span class="pill pill-{change}">{change}</span>
          <span class="tree-note">{esc(note)}</span>
        </div>''')
    return "\n".join(out)


def render_arch():
    out = []
    for panel in ARCH.values():
        nodes = "\n".join(
            f'<div class="arch-node" tabindex="0" {ctx_attrs(label, label + (f" -- {sub}" if sub else ""))}>'
            f'<div class="arch-node-label">{esc(label)}</div>'
            + (f'<div class="arch-node-sub">{esc(sub)}</div>' if sub else "")
            + '</div>'
            for label, sub in panel["nodes"]
        )
        out.append(f'''<div class="arch-panel">
          <div class="arch-panel-label">{esc(panel['label'])}</div>
          <div class="arch-panel-nodes">{nodes}</div>
        </div>''')
    return "\n".join(out)


def render_tabs():
    buttons = "\n".join(
        f'<button class="tab-btn{" active" if i == 0 else ""}" data-tab="{key}">{esc(f["filename"])}</button>'
        for i, (key, f) in enumerate(FILES.items())
    )
    panels = []
    for i, (key, f) in enumerate(FILES.items()):
        active = " active" if i == 0 else ""
        anns = json.dumps(f.get("annotations", []))
        panels.append(f'''<div class="tab-panel{active}" data-tab-panel="{key}">
          <div class="tab-summary">{esc(f['summary'])}</div>
          <pre class="code-block {f['kind']}" tabindex="0" {ctx_attrs(f['filename'], f['content'], f['src'])} data-raw='{esc(json.dumps(f['content']))}' data-annotations='{esc(anns)}'></pre>
        </div>''')
    return buttons, "\n".join(panels)


TITLE = "Add Redis-backed rate limiting"
BRIEF = "Fictional example PR: adds a Redis token-bucket rate limiter as HTTP middleware, keyed by API key."
NARRATIVE = (
    "This is placeholder content to show the recap's shape, not a real PR. "
    "<code>middleware/ratelimit.go</code> wraps every handler with a check against "
    "<code>ratelimit.Limiter</code>; the limiter itself lives in the new "
    "<code>ratelimit/limiter.go</code> and counts requests per API key in Redis with a "
    "simple INCR+EXPIRE window. <code>go.mod</code> picks up the Redis client as a new dependency."
)
DM_INTRO = "Two tables: a new rate_limit_bucket keyed by API key, and a rate_limit_tier column added to the existing api_key table."
STATS = (
    '<span class="stat-pill">example</span>\n'
    '      <span class="stat-pill">feat/rate-limit &rarr; main</span>\n'
    '      <span class="stat-pill">5 files &middot; fictional</span>'
)

TABS_BUTTONS, TABS_PANELS = render_tabs()
TEMPLATE = Path("template.html").read_text()
html_out = (
    TEMPLATE
    .replace("__TITLE__", TITLE)
    .replace("__BRIEF__", BRIEF)
    .replace("__NARRATIVE__", NARRATIVE)
    .replace("__DM_INTRO__", DM_INTRO)
    .replace("__STATS__", STATS)
    .replace("__DATA_MODEL__", render_data_model())
    .replace("__RELATIONS__", render_relations())
    .replace("__FILE_TREE__", render_file_tree())
    .replace("__ARCH__", render_arch())
    .replace("__TABS_BUTTONS__", TABS_BUTTONS)
    .replace("__TABS_PANELS__", TABS_PANELS)
)

OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT.write_text(html_out)
(OUT_DIR / "recap.json").write_text(json.dumps({"repo": REPO, "pr": PR_NUMBER}))
print("wrote", OUT.resolve())
print("REPO is None, so 'View source on GitHub' and /comment are both disabled -- edit REPO/PR_NUMBER/HEAD_SHA to point this at a real PR.")
