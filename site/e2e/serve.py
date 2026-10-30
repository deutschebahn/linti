"""Serve Nuxt's generated HTML and assets under the GitHub Pages base URL."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PUBLIC = Path(__file__).resolve().parents[1] / ".output" / "public"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def translate_path(self, path):
        route = urlsplit(path).path.removeprefix("/linti") or "/"
        target = Path(super().translate_path(route))
        # Nitro can emit /rules.html alongside /rules/_payload.json.
        # Prefer the HTML page over Python's directory listing or redirect.
        if not target.suffix and target.with_suffix(".html").is_file():
            return str(target.with_suffix(".html"))
        if target.is_dir() and (target / "index.html").is_file():
            return str(target / "index.html")
        return str(target)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 4173), Handler).serve_forever()
