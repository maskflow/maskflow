# Runnable example

`demo.py` runs the MaskFlow proxy in front of `echo_backend.py` (a toy
one-tool MCP server) in-process, and calls a tool through it.

```bash
pip install maskflow-mcp
python packages/maskflow-mcp/examples/demo.py
```

```
[backend] received customer='<PERSON_NAME_1>' contact='<EMAIL_1>'
client receives (restored):
  {'status': 'filed', 'ticket': 'Ticket for Ramesh Kumar: Refund request for PAN ABCPE1234F', 'notify': 'ramesh@example.com'}
```

The backend never sees the real values; the client gets them back.

To run the same backend as a real subprocess behind the CLI:

```bash
maskflow-mcp stdio --backend "python packages/maskflow-mcp/examples/echo_backend.py"
```
