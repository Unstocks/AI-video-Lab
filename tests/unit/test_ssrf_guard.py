"""Unit tests for lib.ssrf_guard (connect-time DNS rebinding & SSRF guard)."""

from __future__ import annotations

import socket
import threading
import pytest

from lib import ssrf_guard
from lib.ssrf_guard import (
    SSRFBlockedError,
    assert_public_host,
    assert_public_url,
    assert_public_urls,
    guarded,
    is_public_ip,
)


class TestIsPublicIp:
    @pytest.mark.parametrize(
        "addr",
        [
            "8.8.8.8",
            "1.1.1.1",
            "93.184.216.34",
            "2606:4700:4700::1111",
        ],
    )
    def test_public_ips_allowed(self, addr):
        assert is_public_ip(addr) is True

    @pytest.mark.parametrize(
        "addr",
        [
            "127.0.0.1",
            "127.0.0.53",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.10",
            "169.254.169.254",
            "100.64.0.1",  # RFC 6598 CGNAT
            "0.0.0.0",
            "224.0.0.1",
            "255.255.255.255",
            "::1",
            "::",
            "fe80::1",
            "fc00::1",
            "fd12:3456:789a::1",
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
            "::ffff:10.0.0.5",
            "not-an-ip",
            "",
        ],
    )
    def test_non_public_ips_blocked(self, addr):
        assert is_public_ip(addr) is False


class TestAssertPublicUrlAndHost:
    def test_assert_public_url_rejects_bad_scheme(self):
        with pytest.raises(SSRFBlockedError, match="unsupported URL scheme"):
            assert_public_url("file:///etc/passwd", resolve_dns=False)
        with pytest.raises(SSRFBlockedError, match="unsupported URL scheme"):
            assert_public_url("gopher://127.0.0.1:70/", resolve_dns=False)

    def test_assert_public_url_rejects_private_literal_without_dns(self):
        with pytest.raises(SSRFBlockedError):
            assert_public_url("http://169.254.169.254/latest/meta-data/", resolve_dns=False)
        with pytest.raises(SSRFBlockedError):
            assert_public_url("https://[::ffff:127.0.0.1]/admin", resolve_dns=False)
        with pytest.raises(SSRFBlockedError):
            assert_public_url("http://localhost:8080/internal", resolve_dns=False)

    def test_assert_public_url_allows_public_literal_and_hostname(self):
        assert_public_url("https://8.8.8.8/media.mp4", resolve_dns=False)
        assert_public_url("https://rr1.googlevideo.com/videoplayback", resolve_dns=False)

    def test_assert_public_urls_walks_nested_yt_dlp_payload(self):
        good_payload = {
            "url": "https://rr1.googlevideo.com/video",
            "formats": [
                {"url": "https://rr2.googlevideo.com/a", "manifest_url": "https://manifest.googlevideo.com/m"},
                {"url": "https://1.1.1.1/stream.m3u8"},
            ],
            "subtitles": {"en": [{"url": "https://www.youtube.com/api/timedtext"}]},
        }
        assert_public_urls(good_payload, resolve_dns=False)

        poisoned_payload = {
            "url": "https://rr1.googlevideo.com/video",
            "formats": [
                {"url": "https://rr2.googlevideo.com/a"},
                {"manifest_url": "http://169.254.169.254/latest/meta-data/"},
            ],
        }
        with pytest.raises(SSRFBlockedError):
            assert_public_urls(poisoned_payload, resolve_dns=False)

    def test_assert_public_host_blocks_private_dns_answer(self, monkeypatch):
        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.30.40", 443))]

        monkeypatch.setattr(ssrf_guard, "_real_getaddrinfo", fake_getaddrinfo)
        with pytest.raises(SSRFBlockedError, match="10.20.30.40"):
            assert_public_host("evil.rebind.example")

    def test_assert_public_host_accepts_public_dns_answer(self, monkeypatch):
        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

        monkeypatch.setattr(ssrf_guard, "_real_getaddrinfo", fake_getaddrinfo)
        assert_public_host("example.com")


class TestGuardedContextManager:
    def test_guarded_blocks_connect_time_dns_rebinding_and_restores_socket(self, monkeypatch):
        calls = {"n": 0}

        def rebinding_getaddrinfo(host, port, *args, **kwargs):
            calls["n"] += 1
            if host == "rebind.test":
                ip = "93.184.216.34" if calls["n"] == 1 else "127.0.0.1"
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 443))]
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]

        monkeypatch.setattr(socket, "getaddrinfo", rebinding_getaddrinfo)

        with guarded():
            # First lookup returns public IP -> allowed
            res = socket.getaddrinfo("rebind.test", 443)
            assert res[0][4][0] == "93.184.216.34"
            # Second lookup rebinds to 127.0.0.1 -> blocked at connect time!
            with pytest.raises(SSRFBlockedError, match="127.0.0.1"):
                socket.getaddrinfo("rebind.test", 443)

        # Outside guarded(), socket.getaddrinfo is restored
        assert socket.getaddrinfo is rebinding_getaddrinfo
        res_after = socket.getaddrinfo("rebind.test", 443)
        assert res_after[0][4][0] == "127.0.0.1"

    def test_guarded_is_reentrant(self, monkeypatch):
        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.5", port or 80))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        with guarded():
            with guarded():
                with pytest.raises(SSRFBlockedError):
                    socket.getaddrinfo("lan.internal", 80)
            # Still guarded after exiting inner block
            with pytest.raises(SSRFBlockedError):
                socket.getaddrinfo("lan.internal", 80)

        # Restored after exiting outer block
        assert socket.getaddrinfo is fake_getaddrinfo

    def test_guarded_does_not_block_other_threads(self, monkeypatch):
        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port or 4760))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

        other_thread_result = {}

        def worker():
            other_thread_result["addr"] = socket.getaddrinfo("localhost", 4760)[0][4][0]

        with guarded():
            t = threading.Thread(target=worker)
            t.start()
            t.join(timeout=5)
            assert other_thread_result["addr"] == "127.0.0.1"
            with pytest.raises(SSRFBlockedError):
                socket.getaddrinfo("localhost", 4760)
