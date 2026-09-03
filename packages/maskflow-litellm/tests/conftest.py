"""Importing maskflow registers every pack's recognizers and PIITypes, so
Session masking resolves the India identifiers in tests."""

import maskflow  # noqa: F401  -- import side effect: register recognizers / PIITypes
