"""
MQTT subscriber with per-car state machine.

Subscribes to TeslaMate's MQTT topics and triggers a callback when a
charging session ends (charging_state transitions from Charging/Starting
to Complete, Stopped, or Disconnected).  Whether it was a Supercharger
session is determined later by matching against the Fleet API response.
"""

from __future__ import annotations

import logging
from typing import Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

_SUBSCRIBE_TOPICS = [
    "teslamate/cars/+/charging_state",
    "teslamate/cars/+/charger_power",
]

_ACTIVE_CHARGING_STATES = {"Charging", "Starting"}
_SESSION_END_STATES = {"Complete", "Stopped", "Disconnected"}


class MQTTClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        on_supercharge_complete: Callable[[int], None],
    ):
        self._host = host
        self._port = port
        self._on_supercharge_complete = on_supercharge_complete

        # {car_id: {"charging_state": str, ...}}
        self._car_state: dict[int, dict[str, str]] = {}

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            self._client.username_pw_set(username, password or None)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=120)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            logger.error("MQTT connection refused: %s", reason_code)
            return
        logger.info("Connected to MQTT broker at %s:%s", self._host, self._port)
        for topic in _SUBSCRIBE_TOPICS:
            client.subscribe(topic)
            logger.debug("Subscribed to %s", topic)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        logger.warning("MQTT disconnected (reason=%s), will auto-reconnect", reason_code)

    def _on_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split("/")
            if len(parts) != 4 or parts[0] != "teslamate" or parts[1] != "cars":
                return
            car_id = int(parts[2])
            field = parts[3]
            value = msg.payload.decode("utf-8", errors="replace")
        except Exception as exc:
            logger.debug("Ignoring unparseable MQTT message: %s", exc)
            return

        state = self._car_state.setdefault(car_id, {})
        prev_charging_state = state.get("charging_state")
        state[field] = value

        if (
            field == "charging_state"
            and value in _SESSION_END_STATES
            and prev_charging_state in _ACTIVE_CHARGING_STATES
        ):
            logger.info(
                "Car %d: charging session ended (%s → %s), checking Fleet API",
                car_id,
                prev_charging_state,
                value,
            )
            try:
                self._on_supercharge_complete(car_id)
            except Exception:
                logger.exception("Error in on_supercharge_complete callback for car %d", car_id)

    def start(self) -> None:
        """Connect and block forever (call from the main thread)."""
        logger.info("Connecting to MQTT broker %s:%s", self._host, self._port)
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_forever()
