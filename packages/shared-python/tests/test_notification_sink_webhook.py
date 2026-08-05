"""The DEP-1 webhook sink — every arm executed against a REAL local HTTP server.

A webhook sink tested against a mocked transport proves the mock. These tests bind an ephemeral
`http.server` on 127.0.0.1 and drive the adapter through genuine request/response cycles: the
success arm asserts the PAYLOAD the server actually received, and every failure arm asserts the
Protocol's load-bearing contract — ``deliver`` NEVER raises for a delivery failure, because a raise
would be caught upstream and recorded FAILED anyway, but a sink that leans on that is one bug away
from a rowless drop (the NOTIF-1 atomicity invariant).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from irp_shared.notification.service import default_sink
from irp_shared.notification.sink import (
    LoggingNotificationSink,
    NotificationMessage,
    WebhookNotificationSink,
)

_MSG = NotificationMessage(
    tenant_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    recipient_id="reviewer-1",
    breach_id="breach-42",
    source_event_type="BREACH.DETECT",
    severity="ERROR",
)


class _Handler(BaseHTTPRequestHandler):
    status = 200
    received: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        type(self).received.append(
            {"path": self.path, "content_type": self.headers.get("Content-Type"), "body": body}
        )
        self.send_response(type(self).status)
        self.end_headers()

    def log_message(self, *args: Any) -> None:  # silence per-request stderr noise
        return


@pytest.fixture
def server():  # noqa: ANN201
    _Handler.status = 200
    _Handler.received = []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _url(httpd: HTTPServer, path: str = "/hook") -> str:
    return f"http://127.0.0.1:{httpd.server_port}{path}"


def test_a_2xx_delivers_and_the_server_received_the_real_payload(server: HTTPServer) -> None:
    result = WebhookNotificationSink(_url(server)).deliver(_MSG)
    assert result.ok is True
    assert len(_Handler.received) == 1
    got = _Handler.received[0]
    assert got["content_type"] == "application/json"
    body = json.loads(got["body"])
    assert body == {
        "type": "breach-alert",
        "tenant_id": _MSG.tenant_id,
        "recipient_id": _MSG.recipient_id,
        "breach_id": _MSG.breach_id,
        "source_event_type": _MSG.source_event_type,
        "severity": _MSG.severity,
    }


def test_an_http_500_is_a_FAILED_result_not_a_raise(server: HTTPServer) -> None:
    _Handler.status = 500
    result = WebhookNotificationSink(_url(server)).deliver(_MSG)
    assert result.ok is False
    assert result.detail is not None and "500" in result.detail


def test_an_unreachable_host_is_a_FAILED_result_not_a_raise(server: HTTPServer) -> None:
    """A refused connection — the server is shut down FIRST, so the port is genuinely dead."""
    port = server.server_port
    server.shutdown()
    server.server_close()
    result = WebhookNotificationSink(f"http://127.0.0.1:{port}/hook").deliver(_MSG)
    assert result.ok is False
    assert result.detail is not None


def test_the_failure_detail_NEVER_contains_the_url(server: HTTPServer) -> None:
    """BR-10 at the sink boundary: webhook URLs routinely EMBED a secret token (the Slack
    pattern), and ``detail`` lands in the durable ``failure_reason`` column. So the secret-bearing
    URL must not survive into any failure detail, whatever the failure mode."""
    port = server.server_port
    server.shutdown()
    server.server_close()
    secret_url = f"http://127.0.0.1:{port}/services/T000/B000/SECRETTOKENXYZ"
    result = WebhookNotificationSink(secret_url).deliver(_MSG)
    assert result.ok is False
    assert result.detail is not None
    assert "SECRETTOKENXYZ" not in result.detail
    assert secret_url not in result.detail


def test_construction_refuses_an_empty_url_and_a_non_http_scheme() -> None:
    """Misconfiguration is a startup error owed to the operator, NOT a delivery outcome owed a
    FAILED row — so construction raises where ``deliver`` never may. The scheme refusal is
    fail-closed: ``file://`` reaching urlopen would read the filesystem."""
    with pytest.raises(ValueError, match="non-empty"):
        WebhookNotificationSink("")
    with pytest.raises(ValueError, match="http"):
        WebhookNotificationSink("file:///etc/passwd")


def test_default_sink_selects_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """The DEP-1 wiring itself: unset/empty -> the v1 LOG sink (every existing environment
    unchanged); a URL -> the webhook adapter. Channel constants come from the sink, so the
    durable rows record the true channel either way."""
    monkeypatch.delenv("IRP_NOTIFY_WEBHOOK_URL", raising=False)
    assert isinstance(default_sink(), LoggingNotificationSink)
    monkeypatch.setenv("IRP_NOTIFY_WEBHOOK_URL", "  ")
    assert isinstance(default_sink(), LoggingNotificationSink)
    monkeypatch.setenv("IRP_NOTIFY_WEBHOOK_URL", "https://hooks.example.invalid/services/x")
    sink = default_sink()
    assert isinstance(sink, WebhookNotificationSink)
    assert sink.channel == "WEBHOOK"
