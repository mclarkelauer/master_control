# Future Work

Planned enhancements and areas of investigation for Master Control, organized by priority and scope.

## Fleet Management

### Central Dashboard / API
The control host currently only deploys — it has no runtime visibility into clients. A central API and web dashboard would provide:
- Aggregated workload status across all clients.
- Remote start/stop/restart of workloads on specific clients.
- Fleet-wide health overview with alerting.

The FastAPI dependency is already optional in `pyproject.toml` as a starting point.

### Client Heartbeating
Clients should periodically report status back to the control host. This enables:
- Detection of offline/unreachable clients.
- Centralized log and metric collection.
- Automatic alerting when a client goes dark.

Options: lightweight HTTP POST, MQTT (well-suited for constrained devices), or a simple UDP beacon.

### OTA Updates and Rolling Deploys
Currently deployment is all-or-nothing. Future improvements:
- Rolling deploys that update clients in batches with health checks between batches.
- Automatic rollback if a client fails health checks after deployment.
- Delta syncs to minimize bandwidth on slow or metered connections (rsync already handles this partially).
- Version pinning per client to support canary deployments.

## Raspberry Pi / SBC Optimizations

### Resource Constraints
- **Memory limits**: Add configurable memory caps per workload (`cgroup` or `ulimit`). Kill workloads that exceed their allocation.
- **CPU throttling**: Assign CPU affinity or nice values to prevent a runaway workload from starving others.
- **Storage monitoring**: Watch available disk space and pause/alert before SD cards fill up. SQLite WAL mode should be evaluated for write amplification on flash storage.
- **Temperature monitoring**: Read SoC temperature (`/sys/class/thermal/`) and throttle workloads when thermal limits approach.

### Network Resilience
- **Offline operation**: Already supported (daemons are independent), but workloads that need network access should have retry/backoff built in or provided by the framework.
- **Store-and-forward**: Queue workload outputs locally when the network is down and sync when connectivity returns.
- **Bandwidth awareness**: Throttle log shipping and telemetry on metered connections (cellular, satellite).

### Provisioning
- **SD card imaging**: Pre-baked OS images with Master Control pre-installed, reducing first-deploy time.
- **mDNS/Zeroconf discovery**: Auto-discover new clients on the local network instead of manually editing inventory.
- **USB bootstrap**: For air-gapped networks, support provisioning via USB drive.

## Workload Management

### Dependency Ordering
Some workloads depend on others (e.g., a service must be running before a script can use it). Support:
- `depends_on` field in workload YAML.
- Topological sort for startup ordering.
- Health-check gates before starting dependent workloads.

### Resource Isolation
- Run workloads in separate Python virtual environments to avoid dependency conflicts.
- Optional containerization via Podman (Docker is too heavy for most Pis).
- Namespace isolation using Linux namespaces for network and filesystem.

### Workload Versioning
- Track which version of a workload is deployed to which client.
- Support running multiple versions simultaneously (blue/green).
- Rollback to a previous workload version independently of the full deploy.

### Log Management
- Log rotation and size limits — critical on SD cards with limited space.
- Structured log shipping to a central collector (Loki, Elasticsearch, or a simple syslog relay).
- Per-workload log retention policies.

## Observability

### Metrics Collection
- Expose workload metrics (run count, duration, failure rate, resource usage) via a local endpoint.
- Prometheus-compatible `/metrics` endpoint on each client.
- Central Grafana dashboard aggregating metrics from all clients.

### Alerting
- Webhook or email notifications for workload failures, client disconnects, resource exhaustion.
- Configurable alert rules per workload or per client.
- Escalation policies (retry N times before alerting).

### Distributed Tracing
- Correlation IDs across workload runs for debugging multi-step pipelines.
- Trace context propagation when workloads call external services.

## Security

### Secret Management
- Encrypted secrets in workload configs (currently params are plaintext YAML).
- Integration with system keyrings or a lightweight vault.
- Per-client secrets that aren't stored in the inventory file.

### SSH Key Rotation
- Automated key rotation for deploy keys.
- Support for SSH certificates instead of static keys.

### Audit Logging
- Record who deployed what, when, and to which clients.
- Tamper-evident audit trail for compliance.

## Developer Experience

### Plugin System
- Allow third-party workload types beyond agent/script/service.
- Hook points for custom health checks, metrics exporters, and log processors.

### Config Templating
- Jinja2 or similar templating in workload YAML for per-client variable substitution.
- Reduce inventory duplication when many clients run similar configs with different parameters.

### Testing & Simulation
- Local multi-client simulation for testing deployment scripts without hardware.
- Docker Compose or VM-based test harness that mimics a Pi fleet.
- Chaos testing: randomly kill workloads, disconnect networks, fill disks.

### Interactive Debugging
- `master-control shell <name>`: Attach to a running workload's stdin/stdout.
- `master-control exec <name> <command>`: Run a one-off command in a workload's environment.
- Remote REPL for live debugging on constrained devices.
