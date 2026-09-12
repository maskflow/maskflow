# maskflow-mcp is a proxy: it wraps a backend MCP server and needs one to
# run at all. For an automated introspection check (e.g. Glama's sandboxed
# `tools/list` probe) there's no real backend to point it at, so this image
# wraps the toy `echo_backend.py` shipped in examples/ -- it takes no
# credentials, makes no network calls, and exposes one tool (`file_ticket`)
# so the proxy has something to introspect.
#
# This is NOT how you'd run maskflow-mcp in production -- see README.md for
# wrapping a real backend (`--backend "npx -y @modelcontextprotocol/server-github"`,
# a URL, or --config/--backend-name against a Claude-Desktop-style file).
FROM python:3.12-slim

WORKDIR /app

# maskflow-mcp pulls in fastmcp, which echo_backend.py also needs -- no
# separate install required for the toy backend.
RUN pip install --no-cache-dir maskflow-mcp

COPY examples/echo_backend.py /app/echo_backend.py

# --patterns-only skips the spaCy NER pass (and its model download) so the
# container starts with no network access and no first-run delay.
ENTRYPOINT ["maskflow-mcp", "stdio", "--backend", "python /app/echo_backend.py", "--patterns-only"]
