def test_the_audit_canary_env_is_not_treated_as_malformed_config() -> None:
    """`maskflow audit --prove` seeds MASKFLOW_AUDIT_* into the audited
    process. Without this allowlist, every application that calls mask()
    dies in config resolution under --prove -- which is precisely the set
    of applications the audit exists to verify.
    """
    from maskflow_core.config.resolve import _build_env_layer

    layer, errors = _build_env_layer(
        {
            "MASKFLOW_AUDIT_DUMP": "/tmp/captures.json",
            "MASKFLOW_AUDIT_CANARY_AADHAAR": "123456789012",
            "MASKFLOW_AUDIT_SEED": "20261101",
        }
    )
    assert errors == []
    assert layer.data == {}
