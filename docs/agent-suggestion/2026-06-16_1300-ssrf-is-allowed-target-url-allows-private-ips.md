# SSRF: is_allowed_target_url allows private IP addresses

- **Severity:** High
- **Category:** security
- **Summary:** The `is_allowed_target_url` function in `src/vampire/cluster.py` incorrectly returns `True` when a host is a private IP address (e.g., `192.168.1.1`). This allows an attacker to perform Server-Side Request Forgery (SSRF) attacks against the local network and loopback interface.
- **Location:** `src/vampire/cluster.py:85`
- **Evidence:**
```python
# src/vampire/cluster.py:75-85
def is_allowed_target_url(base_url: str) -> bool:
    """Return whether a caller-supplied probe/proxy target is in the safe scope."""
    parsed = urlparse(base_url)
    if parsed.scheme not in _ALLOWED_SCHEMES or parsed.hostname is None:
        return False
    host_ip = _host_ip_address(parsed.hostname)
    if host_ip is None:
        return True
    if host_ip.is_link_local or host_ip.is_reserved or host_ip.is_multicast:
        return False
    return bool(host_ip.is_loopback or host_ip.is_private)
```
When `base_url` is `"http://192.68.1.1"`, `host_ip` is `IPv4Address('192.168.1.1')`.
`host_ip.is_private` is `True`.
`host_ip.is_loopback` is `False`.
`bool(False or True)` returns `True`.
The function returns `True`, effectively allowing access to a private IP.

- **Impact:** An attacker can use this to probe the internal network of the environment where the gateway is running, potentially accessing sensitive internal services.
- **Fix:**
```python
# before
    return bool(host_ip.is_loopback or host_ip.is_private)

# after
    return not (host_ip.is_loopback or host_ip.is_private)
```

- **Test:**
```python
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
    assert is_allowed_target_url("invalid-url") is False
```
- **Effort & risk:** 1 line change. Extremely low risk.
