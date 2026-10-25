"""
Request cancellation management for LLM inference (SCH-014).
Handles cooperative cancellation tokens, queued request removal, and in-flight interrupt signaling.
"""

import asyncio
from typing import Dict, Optional, Set, Any
from scheduler.models import InferenceRequest, RequestStatus

class CancellationToken:
    def __init__(self, request_id: str):
        self.request_id = request_id
        self._cancelled: bool = False
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._cancelled = True
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._cancelled

    async def wait_cancelled(self) -> None:
        await self._event.wait()


class CancellationManager:
    def __init__(self):
        self._tokens: Dict[str, CancellationToken] = {}
        self._cancelled_ids: Set[str] = set()

    def register(self, request_id: str) -> CancellationToken:
        token = CancellationToken(request_id)
        self._tokens[request_id] = token
        return token

    def cancel_request(self, request_id: str, request: Optional[InferenceRequest] = None) -> Dict[str, Any]:
        """
        Cancels a request. If in queue, marks CANCELLED.
        If in execution, trips cancellation token so worker stops token generation.
        """
        self._cancelled_ids.add(request_id)
        token = self._tokens.get(request_id)
        if token:
            token.cancel()

        if request:
            prev_status = request.status
            request.status = RequestStatus.CANCELLED
            return {
                "success": True,
                "request_id": request_id,
                "previous_status": prev_status.value,
                "current_status": RequestStatus.CANCELLED.value,
                "token_signaled": token is not None
            }

        return {
            "success": True,
            "request_id": request_id,
            "previous_status": "UNKNOWN",
            "current_status": RequestStatus.CANCELLED.value,
            "token_signaled": token is not None
        }

    def is_cancelled(self, request_id: str) -> bool:
        if request_id in self._cancelled_ids:
            return True
        token = self._tokens.get(request_id)
        return token.is_cancelled() if token else False

    def cleanup(self, request_id: str) -> None:
        self._tokens.pop(request_id, None)
        self._cancelled_ids.discard(request_id)
