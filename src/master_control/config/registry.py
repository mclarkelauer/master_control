import threading

from master_control.models.workload import WorkloadSpec


class WorkloadRegistry:
    """Thread-safe, name-indexed collection of WorkloadSpecs."""

    def __init__(self) -> None:
        self._specs: dict[str, WorkloadSpec] = {}
        self._lock = threading.Lock()

    def register(self, spec: WorkloadSpec) -> None:
        with self._lock:
            if spec.name in self._specs:
                raise ValueError(f"Workload '{spec.name}' is already registered")
            self._specs[spec.name] = spec

    def unregister(self, name: str) -> None:
        with self._lock:
            if name not in self._specs:
                raise KeyError(f"Workload '{name}' is not registered")
            del self._specs[name]

    def get(self, name: str) -> WorkloadSpec:
        with self._lock:
            if name not in self._specs:
                raise KeyError(f"Workload '{name}' is not registered")
            return self._specs[name]

    def list_all(self) -> list[WorkloadSpec]:
        with self._lock:
            return list(self._specs.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._specs)

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._specs
