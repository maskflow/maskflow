"""Locks the maskflow-sdk public API shape (CLAUDE.md rule #4: never break
mask()/unmask()/mask_and_call() -- deprecate with warnings one minor
version before removal). A future change to any of these should fail this
test loudly rather than silently drift.

PR 2 deliberately added a keyword-only `config=` to mask()/mask_and_call()
(session()'s equivalent is covered in test_session.py/test_async_session.py)
-- this is an intentional, additive expansion (an old positional call like
`mask(text)` or `mask(text, 0.7)` behaves exactly as before), not the kind
of drift this test exists to catch. The assertions below were updated
alongside that change to lock in the new shape, not relaxed to let it slip
through.
"""

import inspect

from maskflow import mask, mask_and_call, unmask


def test_mask_signature_is_unchanged() -> None:
    params = list(inspect.signature(mask).parameters.values())
    assert [p.name for p in params] == ["text", "min_confidence", "config"]
    # The original two params are still positional-or-keyword, in the same
    # order, with the same default -- an old `mask(text)`/`mask(text, 0.7)`
    # call is untouched.
    assert params[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[1].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[1].default == 0.5
    # config is new, keyword-only, and defaults to "use ambient discovery".
    assert params[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[2].default is None


def test_unmask_signature_is_unchanged() -> None:
    params = list(inspect.signature(unmask).parameters.values())
    assert [p.name for p in params] == ["masked_text", "mapping"]
    assert params[0].default is inspect.Parameter.empty
    assert params[1].default is inspect.Parameter.empty


def test_mask_and_call_signature_is_unchanged() -> None:
    params = list(inspect.signature(mask_and_call).parameters.values())
    assert [p.name for p in params] == ["prompt", "call_fn", "min_confidence", "config"]
    assert params[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[1].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[2].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert params[2].default == 0.5
    assert params[3].kind is inspect.Parameter.KEYWORD_ONLY
    assert params[3].default is None
