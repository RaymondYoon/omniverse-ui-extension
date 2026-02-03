# client.py
# OmniKit/Omniverse-friendly REST client that mirrors your Unity DigitalTwin logic.

import threading
import time
import logging
import json
import os
from typing import Callable, Optional, Dict, Any, List

import requests


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DigitalTwinClient] %(levelname)s: %(message)s",
)


class DataType:
    CONNECTION_INFO = "ConnectionInfo"
    AMR_INFO = "AMRInfo"
    CONTAINER_INFO = "ContainerInfo"
    WORKING_INFO = "WorkingInfo"
    MISSION_INFO = "MissionInfo"
    RESERVATION_INFO = "ReservationInfo"
    OPC_CONNECTION_CONTROL = "OPCConnectionControl"


class DigitalTwinClient:

    def __init__(
        self,
        base_url: Optional[str] = None,   # ← 인자로 주면 우선, 없으면 Network.json 사용
        timeout: float = 5.0,
        interval: float = 0.5,
    ):
        # ─────────────────────────────────────────────────────────────────
        # Load from Network.json (하드코딩 제거)
        # ─────────────────────────────────────────────────────────────────
        config_path = r"C:\omniverse_exts\platform_ext\config\Network.json"
        cfg_base_url = None
        cfg_map_code = "DEFAULT_MAP"

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)

                ip = cfg.get("opServerIP", "127.0.0.1")
                port = cfg.get("opServerPort", 49000)
                https = cfg.get("https", False)
                scheme = "https" if https else "http"

                cfg_base_url = cfg.get("baseUrl") or f"{scheme}://{ip}:{port}/"
                cfg_map_code = cfg.get("mapCode", "DEFAULT_MAP")

                logging.info(f"[Config] Loaded from {config_path}")
                logging.info(f"[Config] base_url={cfg_base_url}, map_code={cfg_map_code}")
            except Exception as e:
                logging.warning(f"[Config] Failed to read {config_path}: {e}")
        else:
            logging.warning(f"[Config] Network.json not found at {config_path}")

        # base_url 우선순위: 인자 > Network.json > 로컬 기본값
        effective_base_url = base_url or cfg_base_url or "http://127.0.0.1:49000/"

        # ─────────────────────────────────────────────────────────────────
        # Base config
        # ─────────────────────────────────────────────────────────────────
        self._base_url = effective_base_url.rstrip("/") + "/"
        self._timeout = timeout
        self._interval = max(0.05, float(interval))

        # State
        self.is_alive: bool = False
        self._lock = threading.Lock()

        # Threading
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._map_code: str = cfg_map_code

        # Callbacks
        self._on_alive_change: List[Callable[[bool], None]] = []
        self._on_request: List[Callable[[str, Dict[str, Any]], None]] = []
        self._on_response: List[
            Callable[[str, Dict[str, Any], Dict[str, Any]], None]
        ] = []
        self._on_error: List[
            Callable[[Exception, Optional[str], Optional[Dict[str, Any]]], None]
        ] = []

        logging.info(f"[DigitalTwinClient] Initialized (base_url={self._base_url}, map_code={self._map_code})")

    # ─────────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────────

    @property
    def base_url(self) -> str:
        return self._base_url

    def set_base_url(self, url: str) -> None:
        self._base_url = url.rstrip("/") + "/"

    def start(self, map_code: Optional[str] = None) -> None:
        """Start background polling loop (ConnectionInfo → fan-out)."""
        if self._thread and self._thread.is_alive():
            return

        # 호출자가 명시적으로 준 경우에만 덮어쓰기. None이면 Network.json 값 유지
        if map_code is not None:
            self._map_code = map_code

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop, name="DigitalTwinPoller", daemon=True
        )
        self._thread.start()
        logging.info("Polling loop started (map_code=%s, interval=%.2fs)", self._map_code, self._interval)

    def stop(self) -> None:
        """Stop background polling loop."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self._timeout + 1.0)
        logging.info("Polling loop stopped")

    def request_post_api(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generic POST; emits Request/Response/Error and updates is_alive."""
        url = f"{self._base_url}{endpoint.lstrip('/')}"
        self._emit_on_request(endpoint, payload)

        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
            resp.raise_for_status()

            # Consider server alive on any HTTP 2xx
            self._set_alive(True)

            # Try parse JSON; if not JSON, treat as empty dict
            try:
                data = resp.json()
            except Exception:
                data = {}

            self._emit_on_response(endpoint, payload, data)
            return data

        except Exception as exc:
            self._set_alive(False)
            self._emit_on_error(exc, endpoint, payload)
            return None

    def post_digital_twin(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """POST to /DigitalTwin with given payload."""
        return self.request_post_api("DigitalTwin", payload)

    def notify_if_server_down(self) -> bool:
        """Returns True if server is down (and you should notify UI)."""
        return not self.is_alive

    # ─────────────────────────────────────────────────────────────────────────────
    # Callbacks
    # ─────────────────────────────────────────────────────────────────────────────

    def add_on_alive_change(self, cb: Callable[[bool], None]) -> None:
        self._on_alive_change.append(cb)

    def add_on_request(self, cb: Callable[[str, Dict[str, Any]], None]) -> None:
        self._on_request.append(cb)

    def add_on_response(
        self, cb: Callable[[str, Dict[str, Any], Dict[str, Any]], None]
    ) -> None:
        self._on_response.append(cb)

    def add_on_error(
        self, cb: Callable[[Exception, Optional[str], Optional[Dict[str, Any]]], None]
    ) -> None:
        self._on_error.append(cb)

    # ─────────────────────────────────────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            start_ts = time.time()

            # 1) ConnectionInfo
            self._post_connection_info()

            # 2) Sleep for remainder of interval
            elapsed = time.time() - start_ts
            sleep_for = max(0.0, self._interval - elapsed)
            # Use wait so loop can stop promptly
            self._stop_event.wait(timeout=sleep_for)

    def _post_connection_info(self) -> None:
        payload = {
            "dataType": DataType.CONNECTION_INFO,
            "mapCode": self._map_code,
        }

        res = self.post_digital_twin(payload)
        if not res:
            return

        # Expecting CommonResponseBody shape: { success, message, data }
        success = bool(res.get("success", False))
        if not success:
            # Unity code shows an error popup when not success; here we just log.
            msg = res.get("message", "Unknown error")
            logging.warning("ConnectionInfo failed: %s", msg)
            return

        # Normalize data to first dict if list-like
        data = res.get("data")
        info_obj = None
        if isinstance(data, list) and data:
            info_obj = data[0]
        elif isinstance(data, dict):
            info_obj = data
        else:
            info_obj = None

        # If KMReS (operation server) is up, fan-out AMR/Container/Working
        kmres_ok = False
        if isinstance(info_obj, dict):
            # The Unity code checks `kMReSStatus` (exact key). Keep casing as-is.
            kmres_ok = bool(info_obj.get("kMReSStatus", False))

        if kmres_ok:
            self._post_simple(DataType.AMR_INFO)
            self._post_simple(DataType.CONTAINER_INFO)
            self._post_simple(DataType.WORKING_INFO)

        # Always fetch Mission/Reservation
        self._post_simple(DataType.MISSION_INFO)
        self._post_simple(DataType.RESERVATION_INFO)

    def _post_simple(self, data_type: str) -> None:
        payload = {"dataType": data_type, "mapCode": self._map_code}
        self.post_digital_twin(payload)

    def _set_alive(self, alive: bool) -> None:
        with self._lock:
            if self.is_alive != alive:
                self.is_alive = alive
                self._emit_on_alive_change(alive)
                logging.info("Server alive = %s", alive)

    # ─────────────────────────────────────────────────────────────────────────────
    # Emitters (protected against exceptions in user callbacks)
    # ─────────────────────────────────────────────────────────────────────────────

    def _emit_on_alive_change(self, alive: bool) -> None:
        for cb in list(self._on_alive_change):
            try:
                cb(alive)
            except Exception as exc:
                logging.exception("AliveChange callback error: %s", exc)

    def _emit_on_request(self, endpoint: str, payload: Dict[str, Any]) -> None:
        for cb in list(self._on_request):
            try:
                cb(endpoint, payload)
            except Exception as exc:
                logging.exception("Request callback error: %s", exc)

    def _emit_on_response(
        self, endpoint: str, payload: Dict[str, Any], response: Dict[str, Any]
    ) -> None:
        for cb in list(self._on_response):
            try:
                cb(endpoint, payload, response)
            except Exception as exc:
                logging.exception("Response callback error: %s", exc)

    def _emit_on_error(
        self, exc: Exception, endpoint: Optional[str], payload: Optional[Dict[str, Any]]
    ) -> None:
        for cb in list(self._on_error):
            try:
                cb(exc, endpoint, payload)
            except Exception as inner:
                logging.exception("Error callback error: %s", inner)

    # ─────────────────────────────────────────────────────────────────────────────
    # Context manager convenience
    # ─────────────────────────────────────────────────────────────────────────────

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stop()
