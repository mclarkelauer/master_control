"""mDNS/Zeroconf service discovery for Master Control fleet.

Provides two components:

- ServiceAdvertiser: Registers a service on the local network so other nodes
  can discover it (used by both the central API and client daemons).
- ServiceDiscovery: Watches for services on the local network and invokes a
  callback when services appear or disappear.

Service types:
  _mctl-central._tcp.local. — advertised by the central API server
  _mctl-client._tcp.local.  — advertised by client daemons
"""

from __future__ import annotations

import asyncio
import socket
from typing import TYPE_CHECKING, Callable

import structlog
from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

if TYPE_CHECKING:
    from zeroconf import ServiceBrowser as ZeroconfBrowser

log = structlog.get_logger()

# Service type constants.
CENTRAL_SERVICE_TYPE = "_mctl-central._tcp.local."
CLIENT_SERVICE_TYPE = "_mctl-client._tcp.local."


def _get_local_addresses() -> list[bytes]:
    """Return the local IPv4 addresses as packed bytes for ServiceInfo."""
    addresses: list[bytes] = []
    try:
        hostname = socket.gethostname()
        for addr in socket.getaddrinfo(hostname, None, socket.AF_INET):
            packed = socket.inet_aton(addr[4][0])
            if packed not in addresses and addr[4][0] != "127.0.0.1":
                addresses.append(packed)
    except OSError:
        pass
    # Fallback: use the address of a temporary outbound UDP socket.
    if not addresses:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("224.0.0.251", 5353))  # mDNS multicast, never sent
                addresses.append(socket.inet_aton(s.getsockname()[0]))
        except OSError:
            pass
    return addresses


class ServiceAdvertiser:
    """Registers an mDNS service so other nodes can discover this one.

    Usage::

        advertiser = ServiceAdvertiser(
            service_type=CLIENT_SERVICE_TYPE,
            name="sensor-node-1",
            port=9100,
            properties={"version": "1.0.0"},
        )
        await advertiser.start()
        ...
        await advertiser.stop()
    """

    def __init__(
        self,
        service_type: str,
        name: str,
        port: int,
        properties: dict[str, str] | None = None,
    ) -> None:
        self._service_type = service_type
        self._name = name
        self._port = port
        self._properties = properties or {}
        self._zeroconf: Zeroconf | None = None
        self._info: ServiceInfo | None = None

    async def start(self) -> None:
        """Register the service on the local network."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._register)

    async def stop(self) -> None:
        """Unregister the service and close Zeroconf."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._unregister)

    def _register(self) -> None:
        addresses = _get_local_addresses()
        instance_name = f"{self._name}.{self._service_type}"
        server = f"{self._name}.local."

        self._info = ServiceInfo(
            self._service_type,
            instance_name,
            addresses=addresses,
            port=self._port,
            properties=self._properties,
            server=server,
        )
        self._zeroconf = Zeroconf()
        self._zeroconf.register_service(self._info)
        log.info(
            "mdns service registered",
            service_type=self._service_type,
            name=self._name,
            port=self._port,
        )

    def _unregister(self) -> None:
        if self._zeroconf and self._info:
            self._zeroconf.unregister_service(self._info)
            self._zeroconf.close()
            self._zeroconf = None
            self._info = None
            log.info("mdns service unregistered", name=self._name)


class ServiceDiscovery:
    """Watches for mDNS services and invokes callbacks on add/remove.

    Usage::

        def on_found(name: str, host: str, port: int, properties: dict[str, str]):
            print(f"Discovered {name} at {host}:{port}")

        discovery = ServiceDiscovery(
            service_type=CENTRAL_SERVICE_TYPE,
            on_found=on_found,
        )
        await discovery.start()
        ...
        await discovery.stop()
    """

    def __init__(
        self,
        service_type: str,
        on_found: Callable[[str, str, int, dict[str, str]], None] | None = None,
        on_removed: Callable[[str], None] | None = None,
    ) -> None:
        self._service_type = service_type
        self._on_found = on_found
        self._on_removed = on_removed
        self._zeroconf: Zeroconf | None = None
        self._browser: ZeroconfBrowser | None = None

    async def start(self) -> None:
        """Begin browsing for services."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._start_browser)

    async def stop(self) -> None:
        """Stop browsing and close Zeroconf."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._stop_browser)

    def _start_browser(self) -> None:
        self._zeroconf = Zeroconf()
        self._browser = ServiceBrowser(
            self._zeroconf,
            self._service_type,
            handlers=[self._on_state_change],
        )
        log.info("mdns browser started", service_type=self._service_type)

    def _stop_browser(self) -> None:
        if self._browser:
            self._browser.cancel()
            self._browser = None
        if self._zeroconf:
            self._zeroconf.close()
            self._zeroconf = None
        log.info("mdns browser stopped", service_type=self._service_type)

    def _on_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                host = info.parsed_addresses()[0] if info.parsed_addresses() else None
                port = info.port
                properties = {
                    k.decode() if isinstance(k, bytes) else k: v.decode()
                    if isinstance(v, bytes)
                    else str(v)
                    for k, v in (info.properties or {}).items()
                }
                # Extract a friendly name from the service instance name.
                friendly_name = name.replace(f".{service_type}", "")
                log.info(
                    "mdns service discovered",
                    name=friendly_name,
                    host=host,
                    port=port,
                )
                if self._on_found and host and port:
                    self._on_found(friendly_name, host, port, properties)
        elif state_change == ServiceStateChange.Removed:
            friendly_name = name.replace(f".{service_type}", "")
            log.info("mdns service removed", name=friendly_name)
            if self._on_removed:
                self._on_removed(friendly_name)
