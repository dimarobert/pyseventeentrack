"""Define a 17track.net client."""

import logging
from typing import Optional

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientError
from yarl import URL

from .errors import RequestError
from .profile import API_URL_BUYER, API_URL_USER, Profile

_LOGGER: logging.Logger = logging.getLogger(__name__)

# from .track import Track

DEFAULT_TIMEOUT: int = 10


class Client:  # pylint: disable=too-few-public-methods
    """Define the client."""

    def __init__(self, *, session: Optional[ClientSession] = None) -> None:
        """Initialize."""
        self._session: Optional[ClientSession] = session

        self.profile: Profile = Profile(self._request)
        # This is disabled until a workaround can be found:
        # self.track = Track(self._request)

    def _copy_cookies_to_buyer_domain(self, session: ClientSession) -> None:
        """Copy login cookies to the buyer API domain.

        The login endpoint (user.17track.net) may set cookies without a Domain
        attribute, which means they are only sent back to user.17track.net per
        RFC 6265. The buyer API lives on buyer.17track.net and needs the same
        session cookies. This method copies them across.
        """
        login_url = URL(API_URL_USER)
        buyer_url = URL(API_URL_BUYER)
        login_cookies = session.cookie_jar.filter_cookies(login_url)
        if login_cookies:
            session.cookie_jar.update_cookies(login_cookies, buyer_url)
            _LOGGER.debug(
                "Copied %d cookie(s) from %s to %s",
                len(login_cookies),
                login_url.host,
                buyer_url.host,
            )

    async def _request(  # pylint: disable=too-many-arguments
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ) -> dict:
        """Make a request against the RainMachine device."""
        use_running_session = self._session and not self._session.closed

        if use_running_session:
            session = self._session
        else:
            session = ClientSession(timeout=ClientTimeout(total=DEFAULT_TIMEOUT))

        assert session

        try:
            async with session.request(
                method, url, headers=headers, params=params, json=json
            ) as resp:
                _LOGGER.debug(
                    "Response from %s: status=%s, content_type=%s",
                    url,
                    resp.status,
                    resp.content_type,
                )
                resp.raise_for_status()
                raw: str = await resp.text()
                _LOGGER.debug("Raw response body from %s: %r", url, raw)
                data: dict = await resp.json(content_type=None)
                if data is None:
                    _LOGGER.warning(
                        "Response from %s parsed as None; raw body was: %r", url, raw
                    )

                # After a successful login request, copy cookies to the buyer
                # domain so that subsequent API calls are authenticated.
                if url == API_URL_USER and session.cookie_jar:
                    self._copy_cookies_to_buyer_domain(session)

                return data
        except ClientError as err:
            raise RequestError(f"Error requesting data from {url}: {err}") from err
        finally:
            if not use_running_session:
                await session.close()
