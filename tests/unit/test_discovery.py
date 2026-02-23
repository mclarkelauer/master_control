"""Tests for mDNS/Zeroconf service discovery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from master_control.fleet.discovery import (
    CENTRAL_SERVICE_TYPE,
    CLIENT_SERVICE_TYPE,
    ServiceAdvertiser,
    ServiceDiscovery,
)
from master_control.fleet.store import FleetDatabase, FleetStateStore


# --- Helpers ---


def _make_service_info_mock(
    name: str = "test-node",
    host: str = "192.168.1.10",
    port: int = 9100,
    properties: dict | None = None,
) -> MagicMock:
    info = MagicMock()
    info.parsed_addresses.return_value = [host]
    info.port = port
    info.properties = {k.encode(): v.encode() for k, v in (properties or {}).items()}
    return info


# --- ServiceAdvertiser Tests ---


class TestServiceAdvertiser:
    async def test_start_registers_service(self) -> None:
        advertiser = ServiceAdvertiser(
            service_type=CLIENT_SERVICE_TYPE,
            name="sensor-1",
            port=9100,
            properties={"version": "1.0"},
        )

        with (
            patch("master_control.fleet.discovery.Zeroconf") as mock_zc_cls,
            patch("master_control.fleet.discovery.ServiceInfo") as mock_info_cls,
            patch(
                "master_control.fleet.discovery._get_local_addresses",
                return_value=[b"\xc0\xa8\x01\x01"],
            ),
        ):
            mock_zc = mock_zc_cls.return_value
            await advertiser.start()

            mock_info_cls.assert_called_once()
            call_kwargs = mock_info_cls.call_args
            assert call_kwargs[0][0] == CLIENT_SERVICE_TYPE
            assert call_kwargs[1]["port"] == 9100
            assert call_kwargs[1]["properties"] == {"version": "1.0"}

            mock_zc.register_service.assert_called_once()

    async def test_stop_unregisters_service(self) -> None:
        advertiser = ServiceAdvertiser(
            service_type=CLIENT_SERVICE_TYPE,
            name="sensor-1",
            port=9100,
        )

        with (
            patch("master_control.fleet.discovery.Zeroconf") as mock_zc_cls,
            patch("master_control.fleet.discovery.ServiceInfo"),
            patch(
                "master_control.fleet.discovery._get_local_addresses",
                return_value=[b"\xc0\xa8\x01\x01"],
            ),
        ):
            mock_zc = mock_zc_cls.return_value
            await advertiser.start()
            await advertiser.stop()

            mock_zc.unregister_service.assert_called_once()
            mock_zc.close.assert_called_once()

    async def test_stop_without_start_is_safe(self) -> None:
        advertiser = ServiceAdvertiser(
            service_type=CLIENT_SERVICE_TYPE,
            name="sensor-1",
            port=9100,
        )
        # Should not raise.
        await advertiser.stop()

    async def test_central_service_type(self) -> None:
        advertiser = ServiceAdvertiser(
            service_type=CENTRAL_SERVICE_TYPE,
            name="mctl-central",
            port=8080,
        )

        with (
            patch("master_control.fleet.discovery.Zeroconf"),
            patch("master_control.fleet.discovery.ServiceInfo") as mock_info_cls,
            patch(
                "master_control.fleet.discovery._get_local_addresses",
                return_value=[b"\x7f\x00\x00\x01"],
            ),
        ):
            await advertiser.start()
            call_args = mock_info_cls.call_args
            assert call_args[0][0] == CENTRAL_SERVICE_TYPE


# --- ServiceDiscovery Tests ---


class TestServiceDiscovery:
    async def test_start_creates_browser(self) -> None:
        discovery = ServiceDiscovery(
            service_type=CENTRAL_SERVICE_TYPE,
            on_found=MagicMock(),
        )

        with (
            patch("master_control.fleet.discovery.Zeroconf") as mock_zc_cls,
            patch("master_control.fleet.discovery.ServiceBrowser") as mock_browser_cls,
        ):
            await discovery.start()

            mock_zc_cls.assert_called_once()
            mock_browser_cls.assert_called_once()
            call_kwargs = mock_browser_cls.call_args
            assert call_kwargs[0][1] == CENTRAL_SERVICE_TYPE

    async def test_stop_cancels_browser(self) -> None:
        discovery = ServiceDiscovery(
            service_type=CENTRAL_SERVICE_TYPE,
        )

        with (
            patch("master_control.fleet.discovery.Zeroconf") as mock_zc_cls,
            patch("master_control.fleet.discovery.ServiceBrowser") as mock_browser_cls,
        ):
            mock_zc = mock_zc_cls.return_value
            mock_browser = mock_browser_cls.return_value

            await discovery.start()
            await discovery.stop()

            mock_browser.cancel.assert_called_once()
            mock_zc.close.assert_called_once()

    async def test_on_found_callback_invoked(self) -> None:
        on_found = MagicMock()
        discovery = ServiceDiscovery(
            service_type=CLIENT_SERVICE_TYPE,
            on_found=on_found,
        )

        with (
            patch("master_control.fleet.discovery.Zeroconf") as mock_zc_cls,
            patch("master_control.fleet.discovery.ServiceBrowser") as mock_browser_cls,
        ):
            mock_zc = mock_zc_cls.return_value
            mock_info = _make_service_info_mock(
                "sensor-1", "192.168.1.50", 9100, {"version": "1.0"}
            )
            mock_zc.get_service_info.return_value = mock_info

            await discovery.start()

            # Get the handler that was registered with ServiceBrowser.
            handler = mock_browser_cls.call_args[1]["handlers"][0]

            # Simulate a service being added.
            from zeroconf import ServiceStateChange

            handler(
                mock_zc,
                CLIENT_SERVICE_TYPE,
                f"sensor-1.{CLIENT_SERVICE_TYPE}",
                ServiceStateChange.Added,
            )

            on_found.assert_called_once_with("sensor-1", "192.168.1.50", 9100, {"version": "1.0"})

    async def test_on_removed_callback_invoked(self) -> None:
        on_removed = MagicMock()
        discovery = ServiceDiscovery(
            service_type=CLIENT_SERVICE_TYPE,
            on_removed=on_removed,
        )

        with (
            patch("master_control.fleet.discovery.Zeroconf") as mock_zc_cls,
            patch("master_control.fleet.discovery.ServiceBrowser") as mock_browser_cls,
        ):
            mock_zc = mock_zc_cls.return_value
            await discovery.start()

            handler = mock_browser_cls.call_args[1]["handlers"][0]

            from zeroconf import ServiceStateChange

            handler(
                mock_zc,
                CLIENT_SERVICE_TYPE,
                f"sensor-1.{CLIENT_SERVICE_TYPE}",
                ServiceStateChange.Removed,
            )

            on_removed.assert_called_once_with("sensor-1")

    async def test_no_callback_does_not_crash(self) -> None:
        discovery = ServiceDiscovery(service_type=CLIENT_SERVICE_TYPE)

        with (
            patch("master_control.fleet.discovery.Zeroconf") as mock_zc_cls,
            patch("master_control.fleet.discovery.ServiceBrowser") as mock_browser_cls,
        ):
            mock_zc = mock_zc_cls.return_value
            mock_info = _make_service_info_mock()
            mock_zc.get_service_info.return_value = mock_info

            await discovery.start()
            handler = mock_browser_cls.call_args[1]["handlers"][0]

            from zeroconf import ServiceStateChange

            # Should not raise even with no callbacks.
            handler(
                mock_zc, CLIENT_SERVICE_TYPE, "x." + CLIENT_SERVICE_TYPE, ServiceStateChange.Added
            )
            handler(
                mock_zc, CLIENT_SERVICE_TYPE, "x." + CLIENT_SERVICE_TYPE, ServiceStateChange.Removed
            )

    async def test_missing_service_info_ignored(self) -> None:
        on_found = MagicMock()
        discovery = ServiceDiscovery(
            service_type=CLIENT_SERVICE_TYPE,
            on_found=on_found,
        )

        with (
            patch("master_control.fleet.discovery.Zeroconf") as mock_zc_cls,
            patch("master_control.fleet.discovery.ServiceBrowser") as mock_browser_cls,
        ):
            mock_zc = mock_zc_cls.return_value
            mock_zc.get_service_info.return_value = None  # Service info unavailable

            await discovery.start()
            handler = mock_browser_cls.call_args[1]["handlers"][0]

            from zeroconf import ServiceStateChange

            handler(
                mock_zc, CLIENT_SERVICE_TYPE, "x." + CLIENT_SERVICE_TYPE, ServiceStateChange.Added
            )

            on_found.assert_not_called()


# --- Fleet Store register_discovered_client Tests ---


class TestRegisterDiscoveredClient:
    async def test_registers_new_client(self, tmp_path: Path) -> None:
        db = FleetDatabase(tmp_path / "fleet.db")
        await db.connect()
        store = FleetStateStore(db)

        await store.register_discovered_client("node-1", "192.168.1.10", 9100)

        client = await store.get_client("node-1")
        assert client is not None
        assert client.name == "node-1"
        assert client.host == "192.168.1.10"
        assert client.api_port == 9100
        assert client.status == "discovered"

        await db.close()

    async def test_does_not_overwrite_online_client(self, tmp_path: Path) -> None:
        db = FleetDatabase(tmp_path / "fleet.db")
        await db.connect()
        store = FleetStateStore(db)

        # Simulate an existing online client via heartbeat.
        from master_control.api.models import HeartbeatPayload, SystemMetrics

        payload = HeartbeatPayload(
            client_name="node-1",
            timestamp="2026-01-01T00:00:00",
            workloads=[],
            system=SystemMetrics(
                cpu_percent=10,
                memory_used_mb=100,
                memory_total_mb=1024,
                disk_used_gb=5,
                disk_total_gb=32,
            ),
        )
        await store.upsert_heartbeat(payload, host="10.0.0.1")

        # Now try to register via mDNS with a different IP.
        await store.register_discovered_client("node-1", "192.168.1.10", 9100)

        client = await store.get_client("node-1")
        assert client is not None
        assert client.status == "online"
        assert client.host == "10.0.0.1"  # Should NOT be overwritten

        await db.close()

    async def test_updates_offline_client(self, tmp_path: Path) -> None:
        db = FleetDatabase(tmp_path / "fleet.db")
        await db.connect()
        store = FleetStateStore(db)

        # Insert a client then mark it offline.
        conn = db.conn
        await conn.execute(
            """INSERT INTO fleet_clients (name, host, api_port, status, updated_at)
               VALUES ('node-1', '10.0.0.1', 9100, 'offline', datetime('now'))"""
        )
        await conn.commit()

        # mDNS rediscovery should update it.
        await store.register_discovered_client("node-1", "192.168.1.20", 9100)

        client = await store.get_client("node-1")
        assert client is not None
        assert client.host == "192.168.1.20"
        assert client.status == "discovered"

        await db.close()


# --- Config Schema Tests ---


class TestMdnsConfigFields:
    def test_fleet_config_defaults(self) -> None:
        from master_control.config.schema import FleetConfig

        config = FleetConfig()
        assert config.mdns_enabled is False

    def test_fleet_config_enabled(self) -> None:
        from master_control.config.schema import FleetConfig

        config = FleetConfig(mdns_enabled=True)
        assert config.mdns_enabled is True

    def test_central_config_defaults(self) -> None:
        from master_control.config.schema import CentralConfig

        config = CentralConfig()
        assert config.mdns_enabled is False

    def test_central_config_enabled(self) -> None:
        from master_control.config.schema import CentralConfig

        config = CentralConfig(mdns_enabled=True)
        assert config.mdns_enabled is True
