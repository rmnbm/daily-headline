"""Pinata (IPFS pinning) client."""

import requests

PIN_FILE_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PIN_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"


class PinataClient:
    def __init__(self, jwt: str, *, timeout: float = 60.0) -> None:
        self._headers = {"Authorization": f"Bearer {jwt}"}
        self._timeout = timeout

    def upload_file(self, content: bytes, filename: str, content_type: str = "image/png") -> str:
        response = requests.post(
            PIN_FILE_URL,
            headers=self._headers,
            files={"file": (filename, content, content_type)},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return f"ipfs://{response.json()['IpfsHash']}"

    def upload_json(self, data: dict, name: str) -> str:
        payload = {
            "pinataOptions": {"cidVersion": 1},
            "pinataMetadata": {"name": name},
            "pinataContent": data,
        }
        response = requests.post(
            PIN_JSON_URL, headers=self._headers, json=payload, timeout=self._timeout
        )
        response.raise_for_status()
        return f"ipfs://{response.json()['IpfsHash']}"
