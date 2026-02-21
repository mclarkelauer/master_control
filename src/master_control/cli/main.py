import asyncio
import importlib
import signal
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from master_control import __version__
from master_control.engine.ipc import IPCError, send_command

console = Console()

DEFAULT_SOCKET_PATH = Path("/tmp/master_control.sock")


def _run_async(coro):
    """Run an async function from sync Click commands."""
    return asyncio.run(coro)


def _get_socket_path(ctx: click.Context) -> Path:
    return Path(ctx.obj.get("socket_path", str(DEFAULT_SOCKET_PATH)))


@click.group()
@click.version_option(version=__version__, prog_name="master-control")
@click.option("--config-dir", default="./configs", type=click.Path(), help="Config directory path")
@click.option("--db-path", default="./master_control.db", type=click.Path(), help="SQLite database path")
@click.option("--socket-path", default=str(DEFAULT_SOCKET_PATH), help="IPC socket path")
@click.pass_context
def cli(ctx: click.Context, config_dir: str, db_path: str, socket_path: str) -> None:
    """Master Control — orchestrator for agents, scripts, and services."""
    ctx.ensure_object(dict)
    ctx.obj["config_dir"] = config_dir
    ctx.obj["db_path"] = db_path
    ctx.obj["socket_path"] = socket_path


@cli.command()
@click.pass_context
def up(ctx: click.Context) -> None:
    """Start the orchestrator daemon (foreground)."""
    from master_control.config.loader import ConfigLoader
    from master_control.engine.orchestrator import Orchestrator

    config_dir = Path(ctx.obj["config_dir"])
    db_path = Path(ctx.obj["db_path"])
    socket_path = Path(ctx.obj["socket_path"])
    log_dir = Path("./logs")

    # Load daemon config for fleet/central settings
    loader = ConfigLoader(config_dir)
    daemon_config = loader.load_daemon_config()

    orch = Orchestrator(
        config_dir=config_dir,
        db_path=db_path,
        log_dir=log_dir,
        socket_path=socket_path,
        daemon_config=daemon_config,
    )

    async def run_daemon() -> None:
        await orch.start()
        stop_event = asyncio.Event()

        def handle_signal() -> None:
            console.print("\n[yellow]Shutting down...[/yellow]")
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_signal)

        console.print("[green]Master Control running.[/green] Press Ctrl+C to stop.")
        await stop_event.wait()
        await orch.shutdown()

    _run_async(run_daemon())


@cli.command()
@click.pass_context
def down(ctx: click.Context) -> None:
    """Stop the running orchestrator."""
    socket_path = _get_socket_path(ctx)

    async def run() -> None:
        try:
            response = await send_command({"command": "shutdown"}, socket_path=socket_path)
            console.print(response.get("message", "Shutdown signal sent"))
        except IPCError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1)

    _run_async(run())


@cli.command("list")
@click.pass_context
def list_workloads(ctx: click.Context) -> None:
    """List all registered workloads and their status."""
    socket_path = _get_socket_path(ctx)

    async def run() -> None:
        try:
            response = await send_command({"command": "list"}, socket_path=socket_path)
        except IPCError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1)

        if "error" in response:
            console.print(f"[red]{response['error']}[/red]")
            raise SystemExit(1)

        workloads = response.get("workloads", [])
        if not workloads:
            console.print("No workloads registered.")
            return

        table = Table(title="Workloads")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Run Mode", style="blue")
        table.add_column("Status", style="green")
        table.add_column("PID", justify="right")
        table.add_column("Runs", justify="right")
        table.add_column("Last Started")

        status_colors = {
            "running": "green",
            "stopped": "red",
            "failed": "red bold",
            "completed": "cyan",
            "starting": "yellow",
            "registered": "dim",
        }

        for w in workloads:
            status_val = w["status"]
            color = status_colors.get(status_val, "white")
            table.add_row(
                w["name"],
                w["type"],
                w["run_mode"],
                f"[{color}]{status_val}[/{color}]",
                str(w["pid"] or "-"),
                str(w["run_count"]),
                w.get("last_started", "-") or "-",
            )

        console.print(table)

    _run_async(run())


@cli.command()
@click.argument("name")
@click.pass_context
def start(ctx: click.Context, name: str) -> None:
    """Start a specific workload."""
    socket_path = _get_socket_path(ctx)

    async def run() -> None:
        try:
            response = await send_command(
                {"command": "start", "name": name}, socket_path=socket_path
            )
            msg = response.get("message") or response.get("error", "Unknown response")
            console.print(msg)
        except IPCError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1)

    _run_async(run())


@cli.command()
@click.argument("name")
@click.pass_context
def stop(ctx: click.Context, name: str) -> None:
    """Stop a specific workload."""
    socket_path = _get_socket_path(ctx)

    async def run() -> None:
        try:
            response = await send_command(
                {"command": "stop", "name": name}, socket_path=socket_path
            )
            msg = response.get("message") or response.get("error", "Unknown response")
            console.print(msg)
        except IPCError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1)

    _run_async(run())


@cli.command()
@click.argument("name")
@click.pass_context
def restart(ctx: click.Context, name: str) -> None:
    """Stop then start a workload."""
    socket_path = _get_socket_path(ctx)

    async def run() -> None:
        try:
            response = await send_command(
                {"command": "restart", "name": name}, socket_path=socket_path
            )
            msg = response.get("message") or response.get("error", "Unknown response")
            console.print(msg)
        except IPCError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1)

    _run_async(run())


@cli.command()
@click.argument("name")
@click.pass_context
def status(ctx: click.Context, name: str) -> None:
    """Show detailed status of a workload."""
    socket_path = _get_socket_path(ctx)

    async def run() -> None:
        try:
            response = await send_command(
                {"command": "status", "name": name}, socket_path=socket_path
            )
        except IPCError as e:
            console.print(f"[red]{e}[/red]")
            raise SystemExit(1)

        if "error" in response:
            console.print(f"[red]{response['error']}[/red]")
            raise SystemExit(1)

        table = Table(title=f"Workload: {response['name']}", show_header=False)
        table.add_column("Field", style="cyan")
        table.add_column("Value")

        fields = [
            ("Name", response["name"]),
            ("Type", response["type"]),
            ("Run Mode", response["run_mode"]),
            ("Status", response["status"]),
            ("PID", str(response.get("pid") or "-")),
            ("Run Count", str(response.get("run_count", 0))),
            ("Module", response.get("module", "-")),
            ("Entry Point", response.get("entry_point", "-")),
            ("Schedule", response.get("schedule") or "-"),
            ("Max Runs", str(response.get("max_runs") or "-")),
            ("Last Started", response.get("last_started") or "-"),
            ("Last Stopped", response.get("last_stopped") or "-"),
            ("Last Error", response.get("last_error") or "-"),
            ("Tags", ", ".join(response.get("tags", [])) or "-"),
        ]

        for field_name, value in fields:
            table.add_row(field_name, str(value))

        console.print(table)

    _run_async(run())


@cli.command()
@click.argument("name")
@click.option("--lines", "-n", default=50, help="Number of lines to show")
def logs(name: str, lines: int) -> None:
    """Show recent log lines for a workload."""
    log_file = Path("./logs") / f"{name}.log"
    if not log_file.exists():
        console.print(f"[red]No log file found for '{name}' at {log_file}[/red]")
        raise SystemExit(1)

    with open(log_file) as f:
        all_lines = f.readlines()
        tail = all_lines[-lines:]
        for line in tail:
            console.print(line.rstrip())


@cli.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate all config files."""
    from master_control.config.loader import ConfigError, ConfigLoader

    config_dir = Path(ctx.obj["config_dir"])

    try:
        loader = ConfigLoader(config_dir)
        specs = loader.load_all()
        console.print(f"[green]All configs valid. {len(specs)} workload(s) found.[/green]")
        for spec in specs:
            console.print(f"  - {spec.name} ({spec.workload_type}, {spec.run_mode})")
    except ConfigError as e:
        console.print(f"[red]Config error: {e}[/red]")
        raise SystemExit(1)


@cli.command("run")
@click.argument("name")
@click.pass_context
def run_workload(ctx: click.Context, name: str) -> None:
    """Run a workload in the foreground (one-shot, bypasses orchestrator)."""
    from master_control.config.loader import ConfigError, ConfigLoader
    from master_control.logging_config import configure_logging

    cfg_dir = Path(ctx.obj["config_dir"])
    configure_logging()

    try:
        loader = ConfigLoader(cfg_dir)
        specs = loader.load_all()
    except ConfigError as e:
        console.print(f"[red]Config error: {e}[/red]")
        raise SystemExit(1)

    spec = next((s for s in specs if s.name == name), None)
    if not spec:
        console.print(f"[red]Workload '{name}' not found in configs.[/red]")
        raise SystemExit(1)

    console.print(f"Running [cyan]{name}[/cyan] ({spec.module_path}:{spec.entry_point})...")

    # Ensure cwd is on sys.path so agent modules can be imported
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        mod = importlib.import_module(spec.module_path)
        func = getattr(mod, spec.entry_point)
        result = func(**spec.params)
        if asyncio.iscoroutine(result):
            asyncio.run(result)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)
