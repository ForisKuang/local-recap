#!/usr/bin/env python3
"""Local-recap server: serves a static recap page and brokers a question/answer
queue between the page's chat panel and a live Claude Code session watching
the queue file. Also relays "post to PR" requests to the `gh` CLI so a page
comment can become a real GitHub PR comment under the operator's own account.
No network calls of its own beyond invoking `gh`, no API key -- stdlib only.

Usage: python3 server.py <content_dir> [port]

Content dir layout:
  index.html          the recap page (served at /)
  recap.json          optional {"repo": "owner/name", "pr": 6} -- required
                       for the /comment endpoint; omit to disable it
  <any other assets>  served as static files
  queue/questions.jsonl   append-only log of {id, ts, question, context[]}
  queue/answers/<id>.json written by the watching agent: {id, answer}
"""
import json
import subprocess
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONTENT_DIR = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
QUEUE_DIR = CONTENT_DIR / "queue"
QUESTIONS_FILE = QUEUE_DIR / "questions.jsonl"
ANSWERS_DIR = QUEUE_DIR / "answers"
META_FILE = CONTENT_DIR / "recap.json"

QUEUE_DIR.mkdir(parents=True, exist_ok=True)
ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
QUESTIONS_FILE.touch(exist_ok=True)

META = json.loads(META_FILE.read_text()) if META_FILE.exists() else {}
REPO = META.get("repo")
PR_NUMBER = META.get("pr")

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep stdout quiet; the watcher tails questions.jsonl separately

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/answer/"):
            qid = self.path.split("/answer/", 1)[1]
            answer_file = ANSWERS_DIR / f"{qid}.json"
            if answer_file.exists():
                data = json.loads(answer_file.read_text())
                self._send_json({"status": "done", "answer": data["answer"]})
            else:
                self._send_json({"status": "pending"})
            return

        # static file serving, defaulting to index.html
        rel = self.path.lstrip("/") or "index.html"
        rel = rel.split("?", 1)[0]
        file_path = (CONTENT_DIR / rel).resolve()
        if CONTENT_DIR not in file_path.parents and file_path != CONTENT_DIR:
            self.send_response(403)
            self.end_headers()
            return
        if not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(file_path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self):
        if self.path == "/ask":
            self._handle_ask()
        elif self.path == "/comment":
            self._handle_comment()
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_ask(self):
        payload = self._read_json_body()
        qid = uuid.uuid4().hex[:12]
        record = {
            "id": qid,
            "ts": time.time(),
            "question": payload.get("question", ""),
            "context": payload.get("context", []),
        }
        with QUESTIONS_FILE.open("a") as f:
            f.write(json.dumps(record) + "\n")
        self._send_json({"id": qid})

    def _handle_comment(self):
        if not REPO or not PR_NUMBER:
            self._send_json(
                {"status": "error", "message": "no recap.json with repo/pr in this content dir -- /comment is disabled"},
                status=400,
            )
            return
        payload = self._read_json_body()
        comment_text = payload.get("comment", "").strip()
        context = payload.get("context", [])
        if not comment_text:
            self._send_json({"status": "error", "message": "empty comment"}, status=400)
            return

        body_parts = []
        for c in context:
            title = c.get("title", "")
            snippet = c.get("body", "")
            if len(snippet) > 600:
                snippet = snippet[:600] + "\n... (truncated)"
            body_parts.append(f"**Re `{title}`:**\n```\n{snippet}\n```")
        body_parts.append(comment_text)
        body_parts.append("\n---\n*Posted from a local-recap page.*")
        full_body = "\n\n".join(body_parts)

        try:
            result = subprocess.run(
                ["gh", "pr", "comment", str(PR_NUMBER), "-R", REPO, "-F", "-"],
                input=full_body,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            self._send_json({"status": "error", "message": str(e)}, status=500)
            return

        if result.returncode != 0:
            self._send_json(
                {"status": "error", "message": (result.stderr or result.stdout).strip()},
                status=500,
            )
            return

        url = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else None
        self._send_json({"status": "posted", "url": url})

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        return json.loads(raw)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"local-recap serving {CONTENT_DIR} at http://127.0.0.1:{PORT}")
    print(f"watching {QUESTIONS_FILE}")
    server.serve_forever()
