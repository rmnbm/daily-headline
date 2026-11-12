"""Image generation with FLUX.1-schnell on Cloudflare Workers AI."""

import base64
import binascii
import io
import logging
import time
from collections.abc import Callable

import requests
from PIL import Image

logger = logging.getLogger(__name__)

MODEL = "@cf/black-forest-labs/flux-1-schnell"


class ImageGenerationError(RuntimeError):
    pass


class CloudflareImageGenerator:
    def __init__(
        self,
        account_id: str,
        api_token: str,
        *,
        attempts: int = 3,
        retry_delay: float = 20.0,
        timeout: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,  # injectable so tests don't wait
    ) -> None:
        self._url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._attempts = attempts
        self._retry_delay = retry_delay
        self._timeout = timeout
        self._sleep = sleep

    def generate(self, prompt: str) -> bytes:
        """Generate an image for `prompt` and return it as PNG bytes.

        Transient failures (network, timeout, 429, 5xx, malformed body) are
        retried. Other 4xx errors (bad token, quota, invalid request) fail
        immediately because retrying would not change the result.
        """
        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                response = requests.post(
                    self._url,
                    headers=self._headers,
                    json={"prompt": prompt, "steps": 4},
                    timeout=self._timeout,
                )
            except requests.RequestException as exc:
                last_error = exc
            else:
                status = response.status_code
                if 400 <= status < 500 and status != 429:
                    raise ImageGenerationError(
                        f"Cloudflare AI error {status}: {response.text[:300]}"
                    )
                if status >= 400:
                    last_error = ImageGenerationError(f"Cloudflare AI returned {status}")
                else:
                    try:
                        return _to_png(response.json()["result"]["image"])
                    except (KeyError, TypeError, ValueError, OSError) as exc:
                        last_error = ImageGenerationError(f"Invalid image in response: {exc!r}")

            logger.warning(
                "Image generation failed (attempt %d/%d): %s", attempt, self._attempts, last_error
            )
            if attempt < self._attempts:
                self._sleep(self._retry_delay)

        raise ImageGenerationError(
            f"Image generation failed after {self._attempts} attempts: {last_error}"
        )


def _to_png(image_b64: str) -> bytes:
    """The API returns a base64-encoded JPEG; the NFT image is stored as PNG."""
    try:
        raw = base64.b64decode(image_b64, validate=True)
    except binascii.Error as exc:
        raise ValueError("image is not valid base64") from exc
    buffer = io.BytesIO()
    Image.open(io.BytesIO(raw)).save(buffer, format="PNG")
    return buffer.getvalue()
