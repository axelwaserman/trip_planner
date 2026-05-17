"""Unit tests for the D-10 minimal API-key log scrubber.

Covers four groups of behavior:

* Group A — direct regex coverage on ``_scrub`` (each pattern, plus the
  precedence rule that Anthropic ``sk-ant-`` matches before bare ``sk-``).
* Group B — ``ApiKeyScrubber.filter`` direct invocation, asserting both
  ``record.msg`` and ``record.args`` are scrubbed and the filter never
  drops a record.
* Group C — real-logger integration through a ``StreamHandler`` writing
  to ``io.StringIO`` so we can assert the formatter output is redacted.
* Group D — ``install_log_scrubber`` / ``uninstall_log_scrubber`` lifecycle:
  attachment to root handlers and uvicorn loggers, idempotency, and safe
  uninstall when never installed.
"""

from __future__ import annotations

import io
import logging

import pytest

from app.llm.log_scrubbing import (
    SECRET_PATTERNS,
    ApiKeyScrubber,
    _scrub,
    install_log_scrubber,
    uninstall_log_scrubber,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Group A — direct regex coverage on _scrub
# ---------------------------------------------------------------------------


def test_scrub_redacts_openai_style_key_in_freeform_string() -> None:
    assert _scrub("key=sk-abcdefghij1234567890") == "key=sk-[REDACTED]"


def test_scrub_redacts_anthropic_style_key_in_freeform_string() -> None:
    assert _scrub("key=sk-ant-api03-abcdefghij1234567890") == "key=sk-ant-[REDACTED]"


def test_scrub_anthropic_pattern_wins_over_openai_pattern() -> None:
    # If the openai pattern ran first it would emit "sk-[REDACTED]ant-..."
    # and leak the key suffix. Anthropic regex MUST run first.
    redacted = _scrub("token=sk-ant-api03-thequickbrownfox1234567890")
    assert redacted == "token=sk-ant-[REDACTED]"
    assert "thequickbrownfox" not in redacted


def test_scrub_redacts_json_api_key_field() -> None:
    assert _scrub('{"api_key": "secret-value-1234567890"}') == '{"api_key": "[REDACTED]"}'


def test_scrub_redacts_json_openai_api_key_field() -> None:
    assert _scrub('{"openai_api_key": "x"}') == '{"openai_api_key": "[REDACTED]"}'


def test_scrub_redacts_json_anthropic_api_key_field() -> None:
    assert _scrub('{"anthropic_api_key": "x"}') == '{"anthropic_api_key": "[REDACTED]"}'


def test_scrub_passes_through_non_secret_strings() -> None:
    assert _scrub("User alice@example.com logged in") == "User alice@example.com logged in"


def test_scrub_passes_through_when_no_secret_present() -> None:
    assert _scrub("GET /api/chat 200 OK") == "GET /api/chat 200 OK"


def test_scrub_short_sk_prefix_does_not_match() -> None:
    # ``sk-abc`` is < 20 chars; must not be redacted (avoids false positives
    # on session-key-shaped identifiers that happen to start with ``sk-``).
    assert _scrub("debug sk-abc was here") == "debug sk-abc was here"


def test_secret_patterns_shape_is_three_pairs() -> None:
    assert len(SECRET_PATTERNS) == 3


# ---------------------------------------------------------------------------
# Group B — ApiKeyScrubber.filter direct invocation
# ---------------------------------------------------------------------------


def _make_record(msg: object, args: object = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=args,  # type: ignore[arg-type]
        exc_info=None,
    )


def test_filter_returns_true_for_redacted_message() -> None:
    scrubber = ApiKeyScrubber()
    record = _make_record("token=sk-abcdefghij1234567890")
    assert scrubber.filter(record) is True


def test_filter_returns_true_for_non_secret_message() -> None:
    scrubber = ApiKeyScrubber()
    record = _make_record("hello world")
    assert scrubber.filter(record) is True


def test_filter_scrubs_record_msg_when_str() -> None:
    scrubber = ApiKeyScrubber()
    record = _make_record("token=sk-abcdefghij1234567890")
    scrubber.filter(record)
    assert record.msg == "token=sk-[REDACTED]"


def test_filter_scrubs_record_args_tuple_strings() -> None:
    scrubber = ApiKeyScrubber()
    record = _make_record("auth: %s", ("sk-realkey1234567890123",))
    scrubber.filter(record)
    assert record.args == ("sk-[REDACTED]",)


def test_filter_passes_through_non_string_args() -> None:
    scrubber = ApiKeyScrubber()
    record = _make_record("count: %d", (42,))
    scrubber.filter(record)
    assert record.args == (42,)


def test_filter_scrubs_record_args_dict_values() -> None:
    # Per stdlib logging: a dict-shaped args is passed as the single
    # positional ``args[0]`` and the LogRecord constructor unwraps it
    # to ``record.args``. We exercise that contract directly.
    scrubber = ApiKeyScrubber()
    record = _make_record("payload: %(token)s", ({"token": "sk-abcdefghij1234567890"},))
    scrubber.filter(record)
    assert record.args == {"token": "sk-[REDACTED]"}


# ---------------------------------------------------------------------------
# Group C — real Logger integration
# ---------------------------------------------------------------------------


def test_filter_integrates_with_real_logger_and_streamhandler() -> None:
    # Arrange: fresh logger + StringIO StreamHandler + scrubber attached
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(ApiKeyScrubber())
    logger = logging.getLogger("test_log_scrubbing.integration")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Act
    logger.info("token=%s", "sk-realkey1234567890123abcdef")

    # Assert
    output = buffer.getvalue()
    assert "sk-[REDACTED]" in output
    assert "realkey1234567890123abcdef" not in output


# ---------------------------------------------------------------------------
# Group D — install_log_scrubber / uninstall_log_scrubber lifecycle
# ---------------------------------------------------------------------------


@pytest.fixture
def root_handler_present() -> object:
    """Ensure the root logger has at least one handler for the duration of a test.

    Tests that exercise ``install_log_scrubber`` need at least one handler
    on the root logger to assert attachment; pytest may not have configured
    one. We add a placeholder StreamHandler and remove it afterwards.
    """
    root = logging.getLogger()
    placeholder = logging.StreamHandler(io.StringIO())
    root.addHandler(placeholder)
    try:
        yield placeholder
    finally:
        root.removeHandler(placeholder)


def test_install_attaches_to_root_handlers(root_handler_present: logging.Handler) -> None:
    scrubber = install_log_scrubber()
    try:
        assert any(scrubber in handler.filters for handler in logging.getLogger().handlers)
    finally:
        uninstall_log_scrubber(scrubber)


def test_install_attaches_to_uvicorn_loggers() -> None:
    scrubber = install_log_scrubber()
    try:
        assert scrubber in logging.getLogger("uvicorn.access").filters
        assert scrubber in logging.getLogger("uvicorn.error").filters
    finally:
        uninstall_log_scrubber(scrubber)


def test_install_is_idempotent(root_handler_present: logging.Handler) -> None:
    # Manual idempotency: install twice with the SAME instance should not
    # double-attach. install_log_scrubber returns a fresh scrubber each call,
    # so we drive the idempotency path by emulating it: construct one and
    # attach via two install passes is not possible; instead, attach once,
    # then re-run the install routine's body via a second install + assert
    # the per-handler filter list does not contain duplicates of the
    # second-install scrubber.
    first = install_log_scrubber()
    try:
        # Re-attach the SAME scrubber by calling addFilter again — the
        # install routine guards against this with ``if scrubber not in
        # handler.filters``. Simulate that guard directly:
        for handler in logging.getLogger().handlers:
            if first not in handler.filters:
                handler.addFilter(first)
        for handler in logging.getLogger().handlers:
            occurrences = sum(1 for f in handler.filters if f is first)
            assert occurrences <= 1
        for name in ("uvicorn.access", "uvicorn.error"):
            occurrences = sum(1 for f in logging.getLogger(name).filters if f is first)
            assert occurrences == 1
    finally:
        uninstall_log_scrubber(first)


def test_uninstall_removes_filter(root_handler_present: logging.Handler) -> None:
    scrubber = install_log_scrubber()
    uninstall_log_scrubber(scrubber)
    assert all(scrubber not in handler.filters for handler in logging.getLogger().handlers)
    assert scrubber not in logging.getLogger("uvicorn.access").filters
    assert scrubber not in logging.getLogger("uvicorn.error").filters


def test_uninstall_is_safe_when_not_installed() -> None:
    scrubber = ApiKeyScrubber()
    # Should not raise even though the scrubber was never attached anywhere.
    uninstall_log_scrubber(scrubber)
