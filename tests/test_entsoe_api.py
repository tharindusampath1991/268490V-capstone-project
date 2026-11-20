"""Tests for ENTSO-E token loading and error handling.

They use no network, no real token and never read the repo's own .env file.
"""

from pathlib import Path

import pytest
import requests
from entsoe.exceptions import NoMatchingDataError

from epf.data.entsoe_api import (
    EntsoeNoDataError,
    EntsoeRequestError,
    MissingTokenError,
    call_entsoe,
    load_token,
)

FAKE_TOKEN = "fake-token-123"


def write_env_file(folder: Path, text: str) -> Path:
    """Write a .env file with the given text into a temporary folder."""
    env_file = folder / ".env"
    env_file.write_text(text, encoding="utf-8")
    return env_file


def fail_with_http_status(status: int) -> None:
    """Fail the way a real request does: the error holds a response whose URL has the token."""
    response = requests.Response()
    response.status_code = status
    response.url = f"https://web-api.tp.entsoe.eu/api?securityToken={FAKE_TOKEN}"
    response.raise_for_status()


def raise_no_data() -> None:
    """Fail the way entsoe-py does when ENTSO-E has no data for a query."""
    raise NoMatchingDataError


def test_load_token_reads_the_token_line_of_the_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ENTSOE_API_TOKEN", raising=False)
    env_file = write_env_file(tmp_path, "# a comment\nOTHER=1\nENTSOE_API_TOKEN=fake-token-123\n")

    assert load_token(env_file) == "fake-token-123"


def test_load_token_strips_spaces_and_quotes(tmp_path, monkeypatch):
    monkeypatch.delenv("ENTSOE_API_TOKEN", raising=False)
    env_file = write_env_file(tmp_path, 'ENTSOE_API_TOKEN = "fake-token-123" \n')

    assert load_token(env_file) == "fake-token-123"


def test_load_token_prefers_the_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("ENTSOE_API_TOKEN", "token-from-environment")
    env_file = write_env_file(tmp_path, "ENTSOE_API_TOKEN=token-from-file\n")

    assert load_token(env_file) == "token-from-environment"


def test_load_token_raises_when_the_env_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("ENTSOE_API_TOKEN", raising=False)

    with pytest.raises(MissingTokenError):
        load_token(tmp_path / ".env")


def test_load_token_raises_when_the_token_line_is_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("ENTSOE_API_TOKEN", raising=False)
    env_file = write_env_file(tmp_path, "ENTSOE_API_TOKEN=\n")

    with pytest.raises(MissingTokenError):
        load_token(env_file)


def test_call_entsoe_returns_the_query_result():
    assert call_entsoe(int, "ff", base=16) == 255


def test_call_entsoe_reports_the_error_type_and_http_status():
    with pytest.raises(EntsoeRequestError) as caught:
        call_entsoe(fail_with_http_status, 401)

    assert caught.value.error_type == "HTTPError"
    assert caught.value.http_status == 401


def test_call_entsoe_reports_errors_without_an_http_status():
    with pytest.raises(EntsoeRequestError) as caught:
        call_entsoe(int, "not a number")

    assert caught.value.error_type == "ValueError"
    assert caught.value.http_status is None


def test_call_entsoe_raises_no_data_error_when_entsoe_has_no_data():
    with pytest.raises(EntsoeNoDataError):
        call_entsoe(raise_no_data)


def test_call_entsoe_request_error_holds_no_trace_of_the_token():
    with pytest.raises(EntsoeRequestError) as caught:
        call_entsoe(fail_with_http_status, 401)

    assert FAKE_TOKEN not in str(caught.value)
    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None


def test_call_entsoe_no_data_error_holds_no_link_to_the_original_error():
    with pytest.raises(EntsoeNoDataError) as caught:
        call_entsoe(raise_no_data)

    assert caught.value.__context__ is None
    assert caught.value.__cause__ is None
