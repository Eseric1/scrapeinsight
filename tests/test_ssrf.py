import pytest

from app.ssrf import BlockedURL, validate_public_url


BLOCKED = [
    "ftp://example.com/file",                      # scheme
    "file:///etc/passwd",                          # scheme
    "http://127.0.0.1/admin",                      # loopback
    "http://localhost/admin",                      # loopback via DNS
    "http://0.0.0.0/",                             # unspecified
    "http://10.0.0.5/",                            # RFC1918
    "http://172.16.0.1/",                          # RFC1918
    "http://192.168.1.124:80/api",                 # RFC1918 (the rig itself)
    "http://169.254.169.254/latest/meta-data/",    # cloud metadata
    "http://[::1]/",                               # IPv6 loopback
    "http://[fd00::1]/",                           # IPv6 unique-local
    "http://1.1.1.1:8080/",                        # disallowed port
    "http://user:pass@1.1.1.1/",                   # credentials
    "http:///nohost",                              # no host
]


@pytest.mark.parametrize("url", BLOCKED)
def test_blocked_urls(url):
    with pytest.raises(BlockedURL):
        validate_public_url(url)


def test_blocked_for_the_right_reason():
    # The metadata IP must be rejected as private/reserved, not by a parse quirk
    with pytest.raises(BlockedURL, match="private or reserved"):
        validate_public_url("http://169.254.169.254/")
    with pytest.raises(BlockedURL, match="ports 80 and 443"):
        validate_public_url("http://1.1.1.1:8080/")
    with pytest.raises(BlockedURL, match="Credentials"):
        validate_public_url("http://a:b@1.1.1.1/")


def test_public_ips_allowed():
    assert validate_public_url("http://1.1.1.1/page") == "1.1.1.1"
    assert validate_public_url("https://8.8.8.8/") == "8.8.8.8"
