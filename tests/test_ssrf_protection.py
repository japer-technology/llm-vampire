from vampire.cluster import is_allowed_target_url


def test_is_allowed_target_url_allows_private_lm_studio_targets() -> None:
    assert is_allowed_target_url("http://192.168.1.1") is True
    assert is_allowed_target_url("http://10.0.0.1") is True
    assert is_allowed_target_url("http://172.16.0.1") is True
    assert is_allowed_target_url("http://127.0.0.1") is True
    assert is_allowed_target_url("http://localhost") is True


def test_is_allowed_target_url_blocks_offscope_ips() -> None:
    assert is_allowed_target_url("http://169.254.169.254") is False
    assert is_allowed_target_url("http://8.8.8.8") is False


def test_is_allowed_target_url_allows_hostnames_until_dns_validation_exists() -> None:
    assert is_allowed_target_url("http://google.com") is True


def test_is_allowed_target_url_blocks_malformed() -> None:
    assert is_allowed_target_url("invalid-url") is False
