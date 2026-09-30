"""Local server for the OrbitTech UI demo.

The browser receives only the generated answer and retrieved chunks. The server
keeps OPENAI_API_KEY in .env and reuses the same DomainAssistant RAG path used
by the benchmark.
"""

from __future__ import annotations

import json
import argparse
import sys
from functools import lru_cache
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openai import OpenAIError

from domain_assistant import DomainAssistant

CORPUS_DIR = ROOT / "data" / "technology_store"
MAX_REQUEST_BYTES = 8_000


@lru_cache(maxsize=1)
def get_assistant() -> DomainAssistant:
    """Load corpus and model client once for the lifetime of the local server."""

    return DomainAssistant.from_corpus(CORPUS_DIR, top_k=5)


class OrbitTechHandler(SimpleHTTPRequestHandler):
    """Serve static UI files plus a small local RAG chat endpoint."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        request_path = urlparse(self.path).path
        if request_path == "/api/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if any(part.startswith(".") for part in Path(request_path).parts):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/chat":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint."})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid request size."})
            return
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Question must be between 1 and 8000 bytes."},
            )
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
            question = payload.get("question", "")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.BAD_REQUEST, {"error": "Request must be valid JSON."}
            )
            return
        if not isinstance(question, str) or not question.strip():
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Question is required."})
            return
        try:
            response = get_assistant().answer_with_trace(question)
        except (OSError, OpenAIError, TypeError, ValueError, RuntimeError) as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "question": response.question,
                "actual_answer": response.actual_answer,
                "retrieved_contexts": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "source_doc": chunk.source_doc,
                        "text": chunk.text,
                        "score": round(chunk.score, 6),
                    }
                    for chunk in response.retrieved_chunks
                ],
            },
        )

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print("OrbitTech UI | " + format % args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local OrbitTech RAG UI.")
    parser.add_argument("--port", type=int, default=8000, help="Local port")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), OrbitTechHandler)
    print(f"OrbitTech UI ready at http://127.0.0.1:{args.port}/demo_ui/")
    print("Press Ctrl+C to stop the local server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nOrbitTech UI server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
