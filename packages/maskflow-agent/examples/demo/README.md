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

## Video (MP4 / GIF)

`record_video.mjs` renders the SVG frame by frame in your installed Chrome
(it pauses every CSS animation and seeks it) and writes PNG frames.
`ffmpeg` then encodes them. Neither tool is a project dependency; install
them into a throwaway folder:

```bash
mkdir -p /tmp/video-deps /tmp/frames && (cd /tmp/video-deps && npm init -y >/dev/null \
  && npm install puppeteer-core@23.11.1 ffmpeg-static@5.2.0)
node $D/record_video.mjs /tmp/video-deps .github/assets/agent-demo.svg /tmp/frames 26 30 14.5 0.65
FF=$(node -e "process.stdout.write(require('/tmp/video-deps/node_modules/ffmpeg-static'))")
$FF -framerate 30 -i /tmp/frames/f%05d.png -c:v libx264 -crf 18 -pix_fmt yuv420p \
    -movflags +faststart maskflow-agent-demo.mp4
```

The arguments are: 26 s of video at 30 fps, with the animation played at
0.65× speed until 14.5 s of animation time, then held. `replay.py` prints
the same capture in a terminal, if you'd rather screen-record a terminal.

## Multi-agent videos (`agents/`)

`agents/` renders the nine-agent montage and one clip per agent used on
maskflow.in/agents. Each clip pairs the **synthetic** `agents/customers.csv`
(left) with what that agent sent to its model in a live session (right).
`agents.json` holds, per agent, the masked row and the agent's answer, both
copied from that agent's own session record. `source` says where to find
it. Logos are from [Simple Icons](https://simpleicons.org) (CC0; the marks
belong to their owners and are shown only to indicate compatibility).

```bash
D=packages/maskflow-agent/examples/demo
python $D/agents/render_agents.py /tmp/clips          # 9 clips + intro.svg + outro.svg
for a in claude codex cursor copilot antigravity gemini opencode cline devin; do
  node $D/record_video.mjs /tmp/video-deps /tmp/clips/$a.svg /tmp/frames-$a 11 30 8.5 1.0
done   # then ffmpeg each frame folder to MP4, as above
```

The montage is `intro`, then each clip's first 8.8 s at 1.6x speed, then
`outro`, joined with ffmpeg's concat demuxer.

**Evidence rule.** A clip may only show an agent whose own session record
contains the masked row `1,Test User,<AADHAAR_1>,<PAN_1>,<INDIAN_MOBILE_1>`
and none of the CSV's raw values. A bare `<AADHAAR_1>` isn't enough, because
the guard's session-start message uses it as an example.
