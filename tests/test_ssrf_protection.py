import pytest
from ipaddress import ip_address
from vampire.cluster import is_allowed_target_url

def test_is_allowed_target_url_blocks_private_ips():
    assert is_allowed_target_url("http://192.168.1.1") is False
    assert is_allowed_target_url("http://10.0.0.1") is False
    assert is_allowed_target_url("http://172.16.0.1") is False
    assert is_allowed_target_url("http://127.0.0.1") is False
    assert is_allowed_target_url("http://localhost") is True

def test_is_allowed_target_url_allows_public_ips():
    # 8.8.8.8 is a public IP
    assert is_allowed_target_url("http://8.8.8.8") is True
    assert is_allowed_target_url("http://google.com") is True

def test_is_allowed_target_url_blocks_malformed():
    # This one depends on how urlparse handles it, but let's check
    assert is_allowed_target_url("invalid-url") is False
