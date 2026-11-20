"""Access to the ENTSO-E API: token loading and error handling.

ENTSO-E request URLs contain the security token. Nothing in this module
prints or logs the token, a request URL or an original request error.
"""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from entsoe.exceptions import NoMatchingDataError

from epf.config import REPO_ROOT

TOKEN_VARIABLE = "ENTSOE_API_TOKEN"
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


class MissingTokenError(Exception):
    """No ENTSO-E token was found in the environment or in the .env file."""


class EntsoeNoDataError(Exception):
    """ENTSO-E answered that it has no data for the query."""


class EntsoeRequestError(Exception):
    """An ENTSO-E call failed. Holds the error type name and the HTTP status only."""

    def __init__(self, error_type: str, http_status: int | None) -> None:
        super().__init__(f"ENTSO-E call failed: {error_type}, HTTP status {http_status}.")
        self.error_type = error_type
        self.http_status = http_status


def load_token(env_file: Path = DEFAULT_ENV_FILE) -> str:
    """Return the ENTSO-E security token.

    Input: path to a .env file. The default is .env in the repo root.
    Output: the token. The ENTSOE_API_TOKEN environment variable is used when
        it is set. Otherwise the ENTSOE_API_TOKEN line of the file is used.
    Raises MissingTokenError when neither holds a token.
    """
    token = os.environ.get(TOKEN_VARIABLE, "")
    if not token and env_file.exists():
        token = _token_from_env_file(env_file)
    if not token:
        raise MissingTokenError(
            f"{TOKEN_VARIABLE} is not set. Set the environment variable or add it to {env_file}."
        )
    return token


def _token_from_env_file(env_file: Path) -> str:
    """Return the value of the ENTSOE_API_TOKEN line of a .env file.

    Input: path to an existing .env file with KEY=VALUE lines.
    Output: the value without surrounding spaces or quotes. An empty string
        when the file has no such line.
    """
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == TOKEN_VARIABLE:
            return value.strip().strip('"').strip("'")
    return ""


def call_entsoe(query: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one entsoe-py query and replace any error with a project error.

    Input: an entsoe-py client method, followed by its arguments.
    Output: whatever the query returns.
    Raises EntsoeNoDataError when ENTSO-E has no data for the query.
    Raises EntsoeRequestError for every other failure.
    """
    try:
        return query(*args, **kwargs)
    except NoMatchingDataError:
        failure: Exception = EntsoeNoDataError("ENTSO-E has no data for this query.")
    except Exception as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        failure = EntsoeRequestError(type(error).__name__, status)
    # An error raised inside an except block keeps the handled error in __context__,
    # and the handled error holds the request URL with the token.
    raise failure
