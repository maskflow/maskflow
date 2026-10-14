# Recording the maskflow-agent demo

`.github/assets/agent-demo.svg` is rendered from two **real** `claude -p`
sessions running the same task against the same database: one without the
guard, one with it. Nothing in it is typed by hand. All data is **synthetic**
(`make_db.py`: seeded, Verhoeff-valid Aadhaar numbers, random PAN/mobile/UPI,
names from MaskFlow's public name list).

```bash
D=packages/maskflow-agent/examples/demo
mkdir -p /tmp/demo-off/.claude /tmp/demo-on/.claude
for d in /tmp/demo-off /tmp/demo-on; do
  python $D/make_db.py $d/kyc.db
  echo '{"permissions":{"allow":["Bash(sqlite3:*)"]}}' > $d/.claude/settings.local.json
done
(cd /tmp/demo-on && maskflow-agent install --scope local)

PROMPT="Support ticket: KYC for customer 4 is stuck. Look the customer up in kyc.db (use sqlite3 -header; table kyc), then set their status to verified, matching on their PAN. Show me the row afterwards."
(cd /tmp/demo-off && claude -p "$PROMPT")
(cd /tmp/demo-on  && claude -p "$PROMPT")

# Transcripts live in ~/.claude/projects/<dir>/<session-id>.jsonl
python $D/capture.py ~/.claude/projects/-tmp-demo-off/<id>.jsonl $D/session-without-guard.json
python $D/capture.py ~/.claude/projects/-tmp-demo-on/<id>.jsonl  $D/session-with-guard.json
python $D/render_svg.py $D/session-without-guard.json $D/session-with-guard.json \
    /tmp/demo-on/kyc.db .github/assets/agent-demo.svg
```

The two committed `session-*.json` files are the captures behind the
current SVG. The model picks its own queries, so a new recording will differ
in detail. Before using a recording, check that the guarded transcript has
none of the database's values:

```bash
python - ~/.claude/projects/-tmp-demo-on/<id>.jsonl <<'PY'
import sqlite3, sys
txt = open(sys.argv[1]).read()
vals = [str(v) for r in sqlite3.connect("/tmp/demo-on/kyc.db").execute(
    "select name, aadhaar, pan, mobile, upi from kyc") for v in r]
print([v for v in vals if v in txt] or "clean")
PY
```
