"""Ensure the packs that register PII types are imported before any test
calls detect() / builds spans -- mirrors maskflow-sdk's conftest."""

import maskflow_pack_india  # noqa: F401
import maskflow_pack_intl  # noqa: F401
