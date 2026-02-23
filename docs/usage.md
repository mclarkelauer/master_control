# Usage Guide

This guide covers common workflows for configuring, running, and managing workloads with Master Control.

## Getting Started

### Installation

```bash
# Clone and install
git clone <repo-url> master_control
cd master_control
make install
```

### Your First Workload

Create a workload config file in `configs/`:

```yaml
# configs/my_agent.yaml
name: my_agent
type: agent
run_mode: forever
module: agents.examples.hello_agent
entry_point: run
restart_delay: 10.0
```

Start the daemon:

```bash
uv run master-control up
```

The daemon loads all YAML files from the `configs/` directory and starts each workload according to its `run_mode`.

### Validating Configuration

Before starting the daemon, validate your configs:

```bash
uv run master-control validate
```

This checks all config files for schema errors, missing required fields, and invalid values.

## Workload Types

### Agents

Agents perform periodic or continuous data collection and transformation. They are typically small, focused tasks.

```yaml
name: sensor_reader
type: agent
run_mode: schedule
schedule: "*/5 * * * *"
module: agents.sensor_reader
entry_point: run
params:
  device: /dev/ttyUSB0
  baud_rate: 9600
```

### Scripts

Scripts run a fixed number of times, useful for batch processing or one-off tasks.

```yaml
name: report_generator
type: script
run_mode: n_times
max_runs: 3
module: agents.report_generator
entry_point: run
params:
  output_dir: /tmp/reports
```

### Services

Services are long-running daemons that are always restarted on failure.

```yaml
name: web_monitor
type: service
run_mode: forever
module: agents.web_monitor
entry_point: run
restart_delay: 5.0
timeout: 3600
```

## Resource Limits

On resource-constrained devices (Raspberry Pi, SBCs), it's important to prevent any single workload from consuming all available memory or CPU. Master Control supports per-workload resource limits.

### Memory Limits

Set `memory_limit_mb` to cap a workload's address space:

```yaml
name: data_processor
type: agent
run_mode: forever
module: agents.data_processor
memory_limit_mb: 256
```

**How it works:**
- The limit is enforced via `RLIMIT_AS` (address space limit) set on the child process before it starts.
- If the workload tries to allocate memory beyond the limit, Python raises `MemoryError`.
- The health checker monitors RSS usage (requires `psutil`) and logs a warning when a workload reaches 90% of its limit.

**Choosing a limit:**
- Run the workload without limits first and observe peak memory usage.
- Set the limit 20-50% above the observed peak to allow headroom.
- For Python workloads, remember that `RLIMIT_AS` covers virtual address space, which is typically larger than RSS. Start generous and tighten.

**Example: protecting a Pi with 1 GB RAM**

```yaml
# Heavy workload gets 512 MB
name: data_cruncher
type: agent
run_mode: forever
module: agents.data_cruncher
memory_limit_mb: 512

---

# Lightweight monitor gets 128 MB
name: health_reporter
type: agent
run_mode: schedule
schedule: "*/1 * * * *"
module: agents.health_reporter
memory_limit_mb: 128
```

### CPU Nice

Set `cpu_nice` to adjust a workload's CPU scheduling priority:

```yaml
name: background_indexer
type: script
run_mode: n_times
max_runs: 1
module: agents.background_indexer
cpu_nice: 15
```

**How it works:**
- The nice value is applied via `os.nice()` in the child process before it starts.
- Values range from -20 (highest priority) to 19 (lowest priority). The default is 0.
- Higher values make the workload yield CPU time to other processes.

**Guidelines:**
- Use `cpu_nice: 10` to `19` for background/batch tasks that shouldn't interfere with critical workloads.
- Use `cpu_nice: 0` (default) for normal workloads.
- Use negative values only for time-critical workloads (requires root privileges).

### Combining Limits

Both limits can be used together:

```yaml
name: background_etl
type: script
run_mode: n_times
max_runs: 1
module: agents.etl_pipeline
entry_point: run
memory_limit_mb: 384
cpu_nice: 10
params:
  input_path: /data/raw
  output_path: /data/processed
```

## Run Modes

### Schedule Mode

Runs the workload on a cron schedule. The workload starts at each scheduled time and exits when done.

```yaml
name: hourly_report
type: agent
run_mode: schedule
schedule: "0 * * * *"
module: agents.report
```

Common cron patterns:
- `"*/5 * * * *"` — every 5 minutes
- `"0 * * * *"` — every hour
- `"0 0 * * *"` — daily at midnight
- `"0 9 * * 1-5"` — weekdays at 9 AM

### Forever Mode

Runs continuously. If the workload exits, it is restarted after `restart_delay` seconds.

```yaml
name: stream_processor
type: service
run_mode: forever
module: agents.stream_processor
restart_delay: 10.0
```

### N-Times Mode

Runs exactly `max_runs` times, then completes.

```yaml
name: migration
type: script
run_mode: n_times
max_runs: 1
module: agents.migration
```

## Managing Workloads

### CLI Commands

```bash
# List all workloads and their status
uv run master-control list

# Check a specific workload
uv run master-control status data_collector

# Start/stop/restart a workload
uv run master-control start data_collector
uv run master-control stop data_collector
uv run master-control restart data_collector

# View recent logs
uv run master-control logs data_collector

# Run a workload in the foreground (one-shot, for testing)
uv run master-control run data_collector
```

### Daemon Control

```bash
# Start the daemon (foreground)
uv run master-control up

# Start as a background daemon
make start

# Graceful shutdown
uv run master-control down

# Check daemon status
make status
```

### Hot-Reloading Configuration

After editing workload config files, reload without restarting the daemon:

```bash
# Via CLI
uv run master-control reload

# Via client HTTP API (if fleet features are enabled)
curl -X POST http://localhost:9100/api/reload
```

The daemon will add new workloads, remove deleted ones, and update changed ones.

## Multi-Workload Configuration

Multiple workloads can be defined in a single YAML file:

```yaml
workloads:
  - name: collector_a
    type: agent
    run_mode: schedule
    schedule: "*/5 * * * *"
    module: agents.collector_a
    memory_limit_mb: 128

  - name: collector_b
    type: agent
    run_mode: schedule
    schedule: "*/10 * * * *"
    module: agents.collector_b
    memory_limit_mb: 128
    cpu_nice: 5
```

## Monitoring and Health

### Process Health

The daemon's health checker periodically verifies that workload processes are alive. If a process disappears, the workload is marked as `FAILED` and restarted according to its run mode strategy.

### Memory Warnings

When `psutil` is installed and `memory_limit_mb` is configured, the health checker logs warnings when a workload's RSS usage exceeds 90% of its limit:

```
workload approaching memory limit  workload=data_processor rss_mb=230.4 limit_mb=256
```

Install `psutil` for memory monitoring:

```bash
uv pip install psutil
```

### Viewing Status

```bash
# All workloads
uv run master-control list

# Detailed status for one workload
uv run master-control status data_collector
```

The status output includes resource limit settings (`memory_limit_mb`, `cpu_nice`) when configured.

## Troubleshooting

### Workload Keeps Getting MemoryError

- The `memory_limit_mb` may be too low. Increase it and monitor actual usage.
- Remember that `RLIMIT_AS` limits virtual address space, not RSS. Python's memory allocator may request more virtual memory than it actually uses.

### Workload Is Slow / Starved for CPU

- Check if `cpu_nice` is set too high. Lower the value to give the workload higher priority.
- Check if other workloads on the same device are consuming too much CPU.

### Config Validation Errors

- `memory_limit_mb` must be a positive integer (> 0).
- `cpu_nice` must be between -20 and 19.
- Run `uv run master-control validate` to check all configs.

### Daemon Won't Start

- Check for YAML syntax errors: `uv run master-control validate`
- Ensure no other daemon is already running (check the socket file at `/tmp/master_control.sock`)
- Check `logs/daemon.log` for error details

For fleet-specific troubleshooting, see [Operations Guide](operations.md#troubleshooting).
