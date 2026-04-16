from typing import Optional

import typer
from rich.console import Console
from rich.text import Text

from veasy_peasy import __version__

app = typer.Typer(
    help="vzpz — visa document toolkit",
    add_completion=False,
)

LOGO_LINES = [
    "██╗   ██╗ ████████╗ ██████╗  ████████╗",
    "██║   ██║ ╚══███╔══╝ ██╔══██╗ ╚══███╔══╝",
    "██║   ██║    ███╔╝   ██████╔╝    ███╔╝   ",
    "╚██╗ ██╔╝   ███╔╝    ██╔═══╝    ███╔╝    ",
    " ╚████╔╝   ████████╗ ██║       ████████╗ ",
    "  ╚═══╝    ╚═══════╝ ╚═╝       ╚═══════╝ ",
]

GRADIENT = ["cyan", "bright_cyan", "bright_magenta", "magenta", "bright_magenta", "cyan"]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"vzpz {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """vzpz — visa document toolkit."""


@app.command()
def init() -> None:
    """Initialise a new vzpz workspace."""
    console = Console()
    console.print()

    for line, colour in zip(LOGO_LINES, GRADIENT):
        styled = Text(line, style=f"bold {colour}")
        console.print(styled, justify="center")

    console.print()
    console.print(
        Text("workspace initialised", style="bold white"),
        justify="center",
    )
    console.print()
