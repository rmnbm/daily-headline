"""Sepolia client that updates the DailyHeadline NFT's token URI."""

import threading
from functools import cached_property

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3

# Minimal ABI: the only function the backend calls.
UPDATE_TOKEN_URI_ABI = [
    {
        "inputs": [{"internalType": "string", "name": "newURI", "type": "string"}],
        "name": "updateTokenURI",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# One wallet sends all transactions. Sending them one at a time prevents two
# runs from reading the same nonce, which would make one of them fail.
_tx_lock = threading.Lock()


class TransactionFailedError(RuntimeError):
    pass


class ChainClient:
    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        contract_address: str,
        *,
        w3: Web3 | None = None,
        receipt_timeout: float = 180.0,
    ) -> None:
        self._rpc_url = rpc_url
        self._private_key = private_key
        self._contract_address = contract_address
        self._receipt_timeout = receipt_timeout
        if w3 is not None:
            self.w3 = w3  # pre-fills the cached_property (used by tests)

    # Lazy: nothing connects or parses the key until a transaction is sent.
    @cached_property
    def w3(self) -> Web3:
        return Web3(Web3.HTTPProvider(self._rpc_url, request_kwargs={"timeout": 30}))

    @cached_property
    def account(self) -> LocalAccount:
        return Account.from_key(self._private_key)

    def update_token_uri(self, token_uri: str) -> str:
        """Send `updateTokenURI(token_uri)`, wait for it to be mined, and return the tx hash."""
        w3 = self.w3
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(self._contract_address), abi=UPDATE_TOKEN_URI_ABI
        )
        with _tx_lock:
            gas_price = w3.eth.gas_price
            tx = contract.functions.updateTokenURI(token_uri).build_transaction(
                {
                    "from": self.account.address,
                    "chainId": w3.eth.chain_id,
                    "gas": 200_000,
                    "maxFeePerGas": gas_price * 2,
                    "maxPriorityFeePerGas": gas_price,
                    "nonce": w3.eth.get_transaction_count(self.account.address),
                }
            )
            signed = self.account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=self._receipt_timeout)

        tx_hex = Web3.to_hex(tx_hash)
        if receipt["status"] != 1:
            raise TransactionFailedError(f"Transaction {tx_hex} reverted")
        return tx_hex
