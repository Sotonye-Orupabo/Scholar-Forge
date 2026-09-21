"""Local JSON service the desktop shell launches (127.0.0.1 only, token required).

    python -m scholarforge.server --port 8765 --token SECRET [--db sf.db] [--csl refs.json]

Every request except CORS preflight must send header X-ScholarForge-Token. The token is
generated per launch by the shell, so other web pages cannot call the service.
"""
import argparse
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from .cite import load_csl
from .generate import BlockGenerator, BlockResult, Session
from .llm import AnthropicProvider, LlamaServerProvider, Provider, ProviderError
from .provenance import PRESETS, ProvenanceLog, disclosure
from .router import route
from .store import Store

ALLOWED_ORIGINS = ("http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost",
                   "http://tauri.localhost", "https://tauri.localhost")


class BadRequest(ValueError):
    pass


class Service:
    def __init__(self, store: Store, local: Provider, cloud: Optional[Provider] = None,
                 csl: Optional[Dict[str, dict]] = None):
        self.store, self.log = store, ProvenanceLog(store.db)
        self.online = True
        self.gen = BlockGenerator(store, self.log, local, cloud, online_check=lambda: self.online, csl=csl)
        self.session = Session(self.gen)
        self.pending: Dict[int, BlockResult] = {}

    @staticmethod
    def _need(body: dict, *keys: str) -> None:
        missing = [k for k in keys if k not in body or body[k] in ("", None)]
        if missing:
            raise BadRequest(f"missing field(s): {', '.join(missing)}")

    @staticmethod
    def _result(r: BlockResult) -> dict:
        return {"event_id": r.event_id, "text": r.text, "route_label": r.route_label, "provider": r.provider,
                "findings": r.findings, "clean": r.clean, "fell_back": r.fell_back,
                "withheld_local_only": r.withheld_local_only}

    # --- endpoints ---
    def health(self, body, query):
        return {"ok": True, "sources": self.store.db.execute("SELECT COUNT(*) FROM docs").fetchone()[0],
                "accepted_blocks": len(self.session.accepted)}

    def route(self, body, query):
        self._need(body, "tier")
        try:
            r = route(body["tier"], bool(body.get("online", True)), bool(body.get("prefer_local", False)))
        except ValueError as e:
            raise BadRequest(str(e))
        return {"target": r.target, "label": r.label}

    def ingest(self, body, query):
        self._need(body, "folder")
        if not os.path.isdir(body["folder"]):
            raise BadRequest("folder does not exist")
        return {"results": self.store.ingest_dir(body["folder"])}

    def search(self, body, query):
        self._need(body, "query")
        hits = self.store.search(body["query"], int(body.get("k", 5)))
        return {"hits": [{k: h[k] for k in ("csl_id", "page", "section", "text", "local_only")} for h in hits]}

    def draft(self, body, query):
        self._need(body, "section", "instruction")
        tier = body.get("tier", "draft")
        if tier not in ("draft", "submission"):
            raise BadRequest("tier must be 'draft' or 'submission'")
        self.online = bool(body.get("online", True))
        r = self.session.propose(body["section"], body.get("outline") or body["section"], body["instruction"],
                                 tier=tier, feedback=body.get("feedback", ""))
        self.pending[r.event_id] = r
        return self._result(r)

    def _take(self, body) -> BlockResult:
        self._need(body, "event_id")
        r = self.pending.pop(int(body["event_id"]), None)
        if r is None:
            raise BadRequest("unknown or already handled event_id")
        return r

    def accept(self, body, query):
        r = self._take(body)
        final = self.session.accept(r, body.get("text"))
        return {"final_text": final, "edit_ratio": self.log.human_edit_ratio(r.event_id),
                "manuscript_words": len(self.session.text.split())}

    def reject(self, body, query):
        self.session.reject(self._take(body))
        return {"ok": True}

    def manuscript(self, body, query):
        return {"text": self.session.text, "blocks": len(self.session.accepted)}

    def disclosure(self, body, query):
        preset = (query.get("preset") or ["generic"])[0]
        if preset not in PRESETS:
            raise BadRequest(f"preset must be one of {sorted(PRESETS)}")
        return {"markdown": disclosure(self.log, preset)}


def make_server(service: Service, token: str, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("the service must bind to loopback only")
    routes: Dict[tuple, Callable] = {
        ("GET", "/health"): service.health, ("POST", "/route"): service.route,
        ("POST", "/ingest"): service.ingest, ("POST", "/search"): service.search,
        ("POST", "/draft"): service.draft, ("POST", "/accept"): service.accept,
        ("POST", "/reject"): service.reject, ("GET", "/manuscript"): service.manuscript,
        ("GET", "/disclosure"): service.disclosure,
    }

    lock = threading.Lock()  # one SQLite connection, so requests are handled one at a time

    class Handler(BaseHTTPRequestHandler):
        def _cors(self):
            origin = self.headers.get("Origin", "")
            if origin in ALLOWED_ORIGINS:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-ScholarForge-Token")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _send(self, status: int, payload: dict):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self.send_response(204); self._cors(); self.end_headers()

        def _handle(self, method: str):
            if self.headers.get("X-ScholarForge-Token", "") != token:
                return self._send(401, {"error": "missing or wrong token"})
            url = urlparse(self.path)
            fn = routes.get((method, url.path))
            if fn is None:
                return self._send(404, {"error": f"no route {method} {url.path}"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}") if method == "POST" else {}
                if not isinstance(body, dict):
                    raise BadRequest("JSON body must be an object")
                with lock:
                    result = fn(body, parse_qs(url.query))
                self._send(200, result)
            except BadRequest as e:
                self._send(400, {"error": str(e)})
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid JSON"})
            except ProviderError as e:
                self._send(502, {"error": f"model unavailable: {e}"})

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def log_message(self, *a):
            pass

    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--token", default=os.environ.get("SF_TOKEN", ""))
    p.add_argument("--db", default="scholarforge.db")
    p.add_argument("--csl")
    p.add_argument("--local-url", default="http://127.0.0.1:8080")
    p.add_argument("--no-cloud", action="store_true")
    a = p.parse_args(argv)
    if len(a.token) < 16:
        print("refusing to start: --token (or SF_TOKEN) must be at least 16 characters", file=sys.stderr)
        return 2
    svc = Service(Store(a.db), LlamaServerProvider(a.local_url), None if a.no_cloud else AnthropicProvider(),
                  load_csl(a.csl) if a.csl else None)
    httpd = make_server(svc, a.token, port=a.port)
    print(f"scholarforge service listening on 127.0.0.1:{httpd.server_port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
