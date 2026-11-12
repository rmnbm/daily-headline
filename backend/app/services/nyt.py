"""New York Times Top Stories API client."""

import requests

TOP_STORIES_URL = "https://api.nytimes.com/svc/topstories/v2/home.json"


class NytError(RuntimeError):
    pass


class NytClient:
    def __init__(self, api_key: str, *, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def fetch_top_headline(self) -> str:
        """Return the title of the first story on the NYT home page."""
        try:
            response = requests.get(
                TOP_STORIES_URL, params={"api-key": self._api_key}, timeout=self._timeout
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            # `from None` on purpose: the original exception message contains the
            # request URL, which contains the API key, and would end up in logs.
            raise NytError(
                f"NYT API request failed ({type(exc).__name__}, status={status})"
            ) from None

        for article in response.json().get("results", []):
            title = (article.get("title") or "").strip()
            if title:
                return title
        raise NytError("No headline found in the NYT response.")
