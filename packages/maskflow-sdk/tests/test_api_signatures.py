"""Locks the maskflow-sdk 0.1.0 public API shape (CLAUDE.md rule #4: never
break mask()/unmask()/mask_and_call() -- deprecate with warnings one minor
version before removal). A future change to any of these should fail this
test loudly rather than silently drift.
"""

import inspect

from maskflow import mask, mask_and_call, unmask


def test_mask_signature_is_unchanged():
    params = list(inspect.signature(mask).parameters.values())
    assert [p.name for p in params] == ["text", "min_confidence"]
    assert params[1].default == 0.5


def test_unmask_signature_is_unchanged():
    params = list(inspect.signature(unmask).parameters.values())
    assert [p.name for p in params] == ["masked_text", "mapping"]
    assert params[0].default is inspect.Parameter.empty
    assert params[1].default is inspect.Parameter.empty


def test_mask_and_call_signature_is_unchanged():
    params = list(inspect.signature(mask_and_call).parameters.values())
    assert [p.name for p in params] == ["prompt", "call_fn", "min_confidence"]
    assert params[2].default == 0.5
