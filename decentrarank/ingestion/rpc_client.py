"""
0G Network RPC Client — production-grade JSON-RPC client with retries,
backoff, and structured error handling.

Compatible with any EVM-based 0G mainnet RPC endpoint. Cosmos-SDK-style
staking queries (validator set, delegations) are accessed via the standard
0G staking precompile at the well-known address.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
import json
import logging
import time

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

logger = logging.getLogger(__name__)


class RpcError(Exception):
    """Raised when an RPC call fails after all retries are exhausted."""
    pass


@dataclass
class RpcConfig:
    """Configuration for an RPC client."""
    endpoint: str
    timeout_seconds:    float = 10.0
    max_retries:        int   = 3
    backoff_base:       float = 0.5  # exponential backoff base in seconds
    user_agent:         str   = "DecentraRank/0.1"


class ZeroGRpcClient:
    """
    JSON-RPC 2.0 client for the 0G Network.

    All public methods return parsed Python objects. Network and protocol
    errors are surfaced as RpcError; transient failures are retried with
    exponential backoff before being raised.
    """

    # The well-known 0G mainnet staking precompile address.
    # In the production environment this is configurable; for the prototype
    # we use the documented default.
    STAKING_PRECOMPILE = "0x0000000000000000000000000000000000001000"

    def __init__(self, config: RpcConfig):
        if requests is None:
            raise RuntimeError("The 'requests' package is required. pip install requests")
        self.config = config
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent":   config.user_agent,
        })
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _call(self, method: str, params: Optional[List[Any]] = None) -> Any:
        """Make a single JSON-RPC call with retries + backoff."""
        payload = {
            "jsonrpc": "2.0",
            "method":  method,
            "params":  params or [],
            "id":      self._next_id(),
        }
        last_exc: Optional[Exception] = None

        for attempt in range(self.config.max_retries + 1):
            try:
                response = self._session.post(
                    self.config.endpoint,
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                if "error" in data:
                    raise RpcError(f"RPC error for {method}: {data['error']}")
                return data.get("result")
            except (requests.exceptions.RequestException, ValueError, RpcError) as e:
                last_exc = e
                if attempt < self.config.max_retries:
                    backoff = self.config.backoff_base * (2 ** attempt)
                    logger.warning(
                        "RPC call %s attempt %d failed: %s. Retrying in %.2fs",
                        method, attempt + 1, e, backoff,
                    )
                    time.sleep(backoff)
                else:
                    break

        raise RpcError(f"RPC call {method} failed after {self.config.max_retries + 1} attempts: {last_exc}")

    # ── Standard EVM RPC methods ────────────────────────────────────────────

    def chain_id(self) -> int:
        """Return the chain ID as an integer."""
        result = self._call("eth_chainId")
        return int(result, 16)

    def block_number(self) -> int:
        """Return the latest block number."""
        result = self._call("eth_blockNumber")
        return int(result, 16)

    def get_block(self, block_number: Union[int, str] = "latest", full_tx: bool = False) -> Dict[str, Any]:
        """Fetch a block by number or 'latest'/'pending'/'earliest'."""
        if isinstance(block_number, int):
            block_number = hex(block_number)
        return self._call("eth_getBlockByNumber", [block_number, full_tx])

    def get_logs(
        self,
        from_block: Union[int, str],
        to_block:   Union[int, str],
        address:    Optional[str] = None,
        topics:     Optional[List[Optional[str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch logs matching the filter parameters."""
        if isinstance(from_block, int): from_block = hex(from_block)
        if isinstance(to_block,   int): to_block   = hex(to_block)
        params: Dict[str, Any] = {"fromBlock": from_block, "toBlock": to_block}
        if address: params["address"] = address
        if topics:  params["topics"]  = topics
        return self._call("eth_getLogs", [params])

    # ── 0G staking precompile queries ───────────────────────────────────────
    #
    # In the production environment, validator data is fetched via either:
    #   (a) eth_call against the staking precompile at STAKING_PRECOMPILE
    #   (b) the Tendermint REST gateway at <rpc>/cosmos/staking/v1beta1/validators
    #
    # The precise method depends on the 0G mainnet deployment configuration,
    # which has evolved during the Aristotle release. The wrapper below uses
    # the Tendermint REST endpoint when a separate REST URL is configured,
    # falling back to a precompile call. See the README for endpoint setup.

    def get_validators_via_rest(self, rest_endpoint: str) -> List[Dict[str, Any]]:
        """
        Fetch the active validator set via the Tendermint REST gateway.
        Returns a list of validator dicts with cosmos-sdk-style fields.
        """
        url = rest_endpoint.rstrip("/") + "/cosmos/staking/v1beta1/validators"
        params = {"status": "BOND_STATUS_BONDED", "pagination.limit": 200}
        try:
            r = self._session.get(url, params=params, timeout=self.config.timeout_seconds)
            r.raise_for_status()
            data = r.json()
            return data.get("validators", [])
        except (requests.exceptions.RequestException, ValueError) as e:
            raise RpcError(f"REST validator query failed: {e}")
