"""Voice assistant REPL — text-only Phase 1 entry point.

Run with: python -m voice_assistant.main [--debug]

Features:
  - Rich colored output (green=user, blue=assistant, cyan=tools)
  - Spinner while the model is thinking
  - Auto-pulls Qwen 3 if not installed
  - Commands: quit/exit/q, clear
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from rich.console import Console
from rich.text import Text

from .config import settings
from .orchestrator import Orchestrator

console = Console()


def _setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)-14s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy HTTP-level debug logs — we only want orchestrator/tool logs
    if debug:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def _tool_call_callback(name: str, args: dict) -> None:
    """Display tool calls in real time."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items()) if args else ""
    console.print(f"  [cyan dim]tool:[/] [cyan]{name}[/]({args_str})")


async def _pull_model_interactive(orchestrator: Orchestrator, model: str) -> bool:
    """Prompt user and pull a model with progress display."""
    console.print(f"\n[yellow]Model '{model}' is not installed.[/]")
    try:
        answer = console.input("[yellow]Pull it now? (y/n): [/]").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False

    if answer not in ("y", "yes"):
        return False

    console.print(f"[dim]Pulling {model}... this may take a few minutes.[/]")
    try:
        last_status = ""
        async for progress in orchestrator.pull_model(model):
            status = progress.get("status", "")
            if status != last_status:
                console.print(f"  [dim]{status}[/]")
                last_status = status
        console.print(f"[green]Model '{model}' ready.[/]\n")
        return True
    except Exception as e:
        console.print(f"[red]Pull failed: {e}[/]")
        return False


async def _run_repl() -> None:
    orchestrator = Orchestrator()

    try:
        # Ensure model is available
        active = await orchestrator.ensure_model()
        if not active:
            # Offer to pull preferred model
            pulled = await _pull_model_interactive(orchestrator, settings.ollama_model)
            if pulled:
                active = await orchestrator.ensure_model()
            if not active:
                # Try fallback
                pulled = await _pull_model_interactive(orchestrator, settings.ollama_fallback_model)
                if pulled:
                    active = await orchestrator.ensure_model()
            if not active:
                console.print("[red]No model available. Install one with: ollama pull qwen3:8b[/]")
                return

        console.print(f"[bold]Voice Assistant[/] [dim]({active})[/]")
        console.print("[dim]Type 'quit' to exit, 'clear' to reset conversation.[/]\n")

        while True:
            try:
                user_input = console.input("[bold green]You:[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/]")
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                console.print("[dim]Goodbye![/]")
                break
            if user_input.lower() == "clear":
                orchestrator.clear_history()
                console.print("[dim]Conversation cleared.[/]\n")
                continue

            with console.status("[dim]Thinking...[/]", spinner="dots"):
                try:
                    response = await orchestrator.chat(
                        user_input,
                        on_tool_call=_tool_call_callback,
                    )
                except Exception as e:
                    console.print(f"[red]Error: {e}[/]\n")
                    continue

            console.print(f"[bold blue]Assistant:[/] {response}\n")

    finally:
        await orchestrator.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Voice Assistant REPL")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    _setup_logging(args.debug)
    asyncio.run(_run_repl())


if __name__ == "__main__":
    main()
