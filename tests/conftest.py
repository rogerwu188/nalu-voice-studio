from __future__ import annotations

import ipaddress
import os
import socket

import pytest


@pytest.fixture(autouse=True)
def block_non_loopback_network_during_offline_e2e(monkeypatch: pytest.MonkeyPatch):
    if os.environ.get("NALU_OFFLINE_E2E_REHEARSAL") != "1":
        yield
        return
    original_connect = socket.socket.connect

    def guarded_connect(instance: socket.socket, address):
        if instance.family == socket.AF_UNIX:
            return original_connect(instance, address)
        host = address[0] if isinstance(address, tuple) and address else ""
        try:
            if ipaddress.ip_address(host).is_loopback:
                return original_connect(instance, address)
        except ValueError:
            pass
        raise RuntimeError("offline E2E rehearsal blocked non-loopback network access")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield
