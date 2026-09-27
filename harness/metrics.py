"""Read-only metrics exporter for Docker; exposes no run or source endpoints."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .server import Store
from .config import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(Settings.from_env().data))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9108)
    args = parser.parse_args()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/metrics":
                self.send_error(404)
                return
            body = Store(args.data, metrics_only=True).metrics(include_active=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
