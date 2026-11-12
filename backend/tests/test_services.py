"""Unit tests for the external service clients.

HTTP calls are intercepted by `responses`: any request without a registered
mock raises an error, so no real request can go out. Web3 is replaced by a
mock, and only the transaction signing really runs, offline, with a public
test key.
"""

import json
from unittest.mock import MagicMock

import pytest
import requests
import responses
from hexbytes import HexBytes

from app.services.chain import ChainClient, TransactionFailedError
from app.services.image import MODEL, CloudflareImageGenerator, ImageGenerationError
from app.services.ipfs import PIN_FILE_URL, PIN_JSON_URL, PinataClient
from app.services.nyt import TOP_STORIES_URL, NytClient, NytError
from tests.conftest import PNG_MAGIC, TEST_CONTRACT, TEST_PRIVATE_KEY, make_jpeg_b64

# --- NYT ---------------------------------------------------------------------


@responses.activate
def test_nyt_returns_first_non_empty_title():
    responses.get(
        TOP_STORIES_URL,
        json={"results": [{"title": ""}, {"title": "  Big News  "}, {"title": "Other"}]},
    )
    assert NytClient("key").fetch_top_headline() == "Big News"
    assert responses.calls[0].request.params == {"api-key": "key"}


@responses.activate
def test_nyt_raises_when_no_headline():
    responses.get(TOP_STORIES_URL, json={"results": []})
    with pytest.raises(NytError, match="No headline"):
        NytClient("key").fetch_top_headline()


@responses.activate
def test_nyt_http_error_does_not_leak_api_key():
    responses.get(TOP_STORIES_URL, status=401)
    with pytest.raises(NytError) as exc:
        NytClient("super-secret").fetch_top_headline()
    assert "status=401" in str(exc.value)
    assert "super-secret" not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


# --- Cloudflare image generation ---------------------------------------------

CF_URL = f"https://api.cloudflare.com/client/v4/accounts/acc/ai/run/{MODEL}"


def make_generator(sleeps: list | None = None) -> CloudflareImageGenerator:
    return CloudflareImageGenerator(
        "acc", "token", sleep=(sleeps.append if sleeps is not None else lambda s: None)
    )


@responses.activate
def test_image_generation_returns_png():
    responses.post(CF_URL, json={"result": {"image": make_jpeg_b64()}})
    image = make_generator().generate("a prompt")
    assert image.startswith(PNG_MAGIC)
    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer token"
    assert json.loads(request.body) == {"prompt": "a prompt", "steps": 4}


@responses.activate
def test_image_generation_retries_transient_errors():
    responses.post(CF_URL, status=503)
    responses.post(CF_URL, body=requests.ConnectionError("boom"))
    responses.post(CF_URL, json={"result": {"image": make_jpeg_b64()}})
    sleeps: list = []
    assert make_generator(sleeps).generate("p").startswith(PNG_MAGIC)
    assert len(responses.calls) == 3
    assert sleeps == [20.0, 20.0]


@responses.activate
def test_image_generation_gives_up_after_three_attempts():
    responses.post(CF_URL, json={"result": {"image": "not base64!"}})
    sleeps: list = []
    with pytest.raises(ImageGenerationError, match="after 3 attempts"):
        make_generator(sleeps).generate("p")
    assert len(responses.calls) == 3
    assert len(sleeps) == 2  # no pointless wait after the last attempt


@responses.activate
def test_image_generation_fails_fast_on_client_error():
    responses.post(CF_URL, status=401, body="bad token")
    with pytest.raises(ImageGenerationError, match="401"):
        make_generator().generate("p")
    assert len(responses.calls) == 1


# --- Pinata ------------------------------------------------------------------


@responses.activate
def test_pinata_upload_file():
    responses.post(PIN_FILE_URL, json={"IpfsHash": "QmImage"})
    uri = PinataClient("jwt").upload_file(b"png-bytes", "headline.png")
    assert uri == "ipfs://QmImage"
    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer jwt"
    assert b'filename="headline.png"' in request.body


@responses.activate
def test_pinata_upload_json():
    responses.post(PIN_JSON_URL, json={"IpfsHash": "bafyMeta"})
    uri = PinataClient("jwt").upload_json({"name": "x"}, "metadata.json")
    assert uri == "ipfs://bafyMeta"
    body = json.loads(responses.calls[0].request.body)
    assert body["pinataContent"] == {"name": "x"}
    assert body["pinataMetadata"] == {"name": "metadata.json"}


@responses.activate
def test_pinata_http_error_propagates():
    responses.post(PIN_JSON_URL, status=500)
    with pytest.raises(requests.HTTPError):
        PinataClient("jwt").upload_json({}, "m.json")


# --- Chain -------------------------------------------------------------------

TX_HASH = HexBytes(b"\x12" * 32)


def make_fake_w3(receipt_status: int = 1) -> MagicMock:
    w3 = MagicMock()
    w3.eth.gas_price = 10
    w3.eth.chain_id = 11155111
    w3.eth.get_transaction_count.return_value = 7
    build = w3.eth.contract.return_value.functions.updateTokenURI.return_value.build_transaction
    build.side_effect = lambda params: {**params, "to": TEST_CONTRACT, "data": "0x", "value": 0}
    w3.eth.send_raw_transaction.return_value = TX_HASH
    w3.eth.wait_for_transaction_receipt.return_value = {"status": receipt_status}
    return w3


def test_chain_client_is_lazy():
    # An invalid key and RPC URL don't fail until a transaction is sent.
    ChainClient("http://nowhere.invalid", "not-a-key", TEST_CONTRACT)


def test_chain_update_token_uri_signs_and_sends():
    w3 = make_fake_w3()
    client = ChainClient("unused", TEST_PRIVATE_KEY, TEST_CONTRACT.lower(), w3=w3)

    assert client.update_token_uri("ipfs://meta") == "0x" + "12" * 32

    contract_call = w3.eth.contract.call_args
    assert contract_call.kwargs["address"] == TEST_CONTRACT  # checksummed
    w3.eth.contract.return_value.functions.updateTokenURI.assert_called_once_with("ipfs://meta")
    build = w3.eth.contract.return_value.functions.updateTokenURI.return_value.build_transaction
    tx_params = build.call_args.args[0]
    assert tx_params["nonce"] == 7
    assert tx_params["chainId"] == 11155111
    assert tx_params["from"] == client.account.address
    raw_tx = w3.eth.send_raw_transaction.call_args.args[0]
    assert isinstance(raw_tx, bytes | HexBytes) and len(raw_tx) > 0


def test_chain_reverted_transaction_raises():
    client = ChainClient("unused", TEST_PRIVATE_KEY, TEST_CONTRACT, w3=make_fake_w3(0))
    with pytest.raises(TransactionFailedError, match="reverted"):
        client.update_token_uri("ipfs://meta")
