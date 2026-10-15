"""OpenCode and Cline plugin adapters: the Python protocol, and the
generated JS plugin files driven by a real Node.js process the way each
agent calls them. Synthetic identifiers only."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
from conftest import (
    run_agent_hook,
    synthetic_aadhaar,
    synthetic_mobile,
    synthetic_pan,
    token_for,
)
from maskflow_agent import guard
from maskflow_agent.adapters import cline, opencode

AADHAAR, PAN, MOBILE = synthetic_aadhaar(), synthetic_pan(), synthetic_mobile()
CSV = f"id,aadhaar,pan,mobile\n1,{AADHAAR},{PAN},{MOBILE}\n"
CANARIES = (AADHAAR, PAN, MOBILE)
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")


def _clean(text: str) -> bool:
    return not any(c in text for c in CANARIES)


# -- Python protocol ------------------------------------------------------------------
@pytest.mark.leak
@pytest.mark.parametrize("agent", ["opencode", "cline"])
def test_after_masks_any_shape(session_id: str, agent: str) -> None:
    for result in (CSV, {"output": CSV, "metadata_output": CSV}, [{"type": "text", "text": CSV}]):
        out, raw, code = run_agent_hook(
            agent, "after", {"session": session_id, "tool": "x", "input": {}, "result": result}
        )
        assert code == 0 and _clean(raw)
        assert type(out["result"]) is type(result) and "<AADHAAR_" in raw


@pytest.mark.leak
@pytest.mark.parametrize("agent", ["opencode", "cline"])
def test_after_guard_down_withholds(agent_home: Path, agent: str) -> None:
    out, raw, _ = run_agent_hook(
        agent, "after", {"session": f"nobody-{uuid.uuid4().hex[:6]}", "result": {"o": CSV}}
    )
    assert _clean(raw) and out == {"result": {"o": guard.WITHHELD}}


@pytest.mark.parametrize(("agent", "tool"), [("opencode", "write"), ("cline", "editor")])
def test_before_denies_placeholder_writes(session_id: str, agent: str, tool: str) -> None:
    token = token_for(session_id, synthetic_pan())
    out, _, _ = run_agent_hook(
        agent, "before", {"session": session_id, "tool": tool, "input": {"content": token}}
    )
    assert "deny" in out


@pytest.mark.parametrize(("agent", "tool"), [("opencode", "bash"), ("cline", "run_commands")])
def test_before_restores_in_allowlisted_commands(session_id: str, agent: str, tool: str) -> None:
    token = token_for(session_id, synthetic_pan())
    out, _, _ = run_agent_hook(
        agent,
        "before",
        {
            "session": session_id,
            "tool": tool,
            "input": {"command": f"psql -c \"select '{token}'\""},
        },
    )
    assert "--ticket" in out["input"]["command"]


def test_missing_session_falls_back_per_directory() -> None:
    from maskflow_agent.adapters import _jsplugin

    a = _jsplugin.session({"cwd": "/w1"})
    assert (
        a == _jsplugin.session({"session": None, "cwd": "/w1"}) != _jsplugin.session({"cwd": "/w2"})
    )


# -- the generated JS plugins under Node ---------------------------------------------
def _node(script: str, cwd: Path) -> Any:
    proc = subprocess.run(
        [str(NODE), "--input-type=module", "-e", script],
        cwd=cwd, capture_output=True, text=True, timeout=300, check=False,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _plugin_url(module: Any, tmp_path: Path) -> str:
    path = module.config_path("project", tmp_path)
    module.install(path)
    mjs = path.with_suffix(".mjs")
    mjs.write_text(path.read_text())
    return mjs.as_uri()


@needs_node
@pytest.mark.leak
def test_opencode_plugin_masks_and_blocks(session_id: str, tmp_path: Path) -> None:
    url = _plugin_url(opencode, tmp_path)
    token = token_for(session_id, synthetic_pan())
    result = _node(
        f"""
import {{ MaskflowAgent }} from {json.dumps(url)};
const hooks = await MaskflowAgent({{ directory: {json.dumps(str(tmp_path))} }});
const sid = {json.dumps(session_id)};
const csv = {json.dumps(CSV)};
const out = {{ title: "cat", output: csv, metadata: {{ output: csv }} }};
await hooks["tool.execute.after"]({{ tool: "bash", sessionID: sid, callID: "c1",
  args: {{ command: "cat k.csv" }} }}, out);
let denied = null;
try {{
  await hooks["tool.execute.before"]({{ tool: "write", sessionID: sid, callID: "c2" }},
    {{ args: {{ filePath: "a", content: {json.dumps(token)} }} }});
}} catch (e) {{ denied = String(e.message); }}
const args = {{ command: "psql -c \\"select '{token}'\\"" }};
await hooks["tool.execute.before"]({{ tool: "bash", sessionID: sid, callID: "c3" }}, {{ args }});
console.log(JSON.stringify({{ out, denied, args }}));
""",
        tmp_path,
    )
    assert _clean(json.dumps(result["out"]))
    assert (
        "<AADHAAR_" in result["out"]["output"]
        and "<AADHAAR_" in result["out"]["metadata"]["output"]
    )
    assert result["denied"] and "placeholders" in result["denied"]
    assert "--ticket" in result["args"]["command"]


@needs_node
@pytest.mark.leak
def test_cline_plugin_masks_and_fails_closed(session_id: str, tmp_path: Path) -> None:
    url = _plugin_url(cline, tmp_path)
    result = _node(
        f"""
import plugin from {json.dumps(url)};
plugin.setup({{}}, {{ session: {{ sessionId: {json.dumps(session_id)} }}, cwd: "/tmp" }});
const masked = await plugin.hooks.afterTool({{ toolCall: {{ name: "read_files" }},
  input: {{ paths: ["k.csv"] }}, result: {{ content: {json.dumps(CSV)} }} }});
const clean = await plugin.hooks.afterTool({{ toolCall: {{ name: "read_files" }},
  input: {{}}, result: "build ok" }});
console.log(JSON.stringify({{ masked, clean: clean ?? null }}));
""",
        tmp_path,
    )
    assert _clean(json.dumps(result))
    assert "<AADHAAR_" in result["masked"]["result"]["content"]
    assert result["clean"] is None


@needs_node
@pytest.mark.leak
def test_cline_plugin_withholds_when_guard_cannot_answer(tmp_path: Path) -> None:
    path = cline.config_path("project", tmp_path)
    cline.install(path)
    # Point the plugin at a command that never answers in time.
    source = path.read_text()
    start = source.index("const CMD = ")
    end = source.index(";", start)
    path.with_suffix(".mjs").write_text(
        source[:start] + 'const CMD = ["sleep", "10"]' + source[end:]
    )
    result = _node(
        f"""
import plugin from {json.dumps(path.with_suffix(".mjs").as_uri())};
plugin.setup({{}}, {{ session: {{ sessionId: "s" }}, cwd: "/tmp" }});
const t0 = Date.now();
const after = await plugin.hooks.afterTool({{ toolCall: {{ name: "x" }}, input: {{}},
  result: {{ content: {json.dumps(CSV)}, n: 1 }} }});
const before = await plugin.hooks.beforeTool({{ toolCall: {{ name: "x" }}, input: {{}} }});
console.log(JSON.stringify({{ after, before, ms: Date.now() - t0 }}));
""",
        tmp_path,
    )
    assert result["after"] == {"result": {"content": guard.WITHHELD, "n": 1}}
    assert result["before"]["skip"] is True
    assert result["ms"] < 6000  # two calls inside Cline's 3 s per-hook limit


# -- install ----------------------------------------------------------------------------
@pytest.mark.parametrize("module", [opencode, cline])
def test_install_refuses_to_overwrite_a_foreign_file(module: Any, tmp_path: Path) -> None:
    path = module.config_path("project", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("export default {};\n")
    with pytest.raises(FileExistsError):
        module.install(path)
    assert not module.uninstall(path) and path.exists()


@pytest.mark.parametrize("module", [opencode, cline])
def test_install_uninstall_roundtrip(module: Any, tmp_path: Path) -> None:
    path = module.config_path("project", tmp_path)
    module.install(path, portable=True)
    assert '["maskflow-agent", "hook", "--agent"' in path.read_text()
    module.install(path)  # re-install over our own file is fine
    assert module.is_installed(path) and module.uninstall(path) and not path.exists()
