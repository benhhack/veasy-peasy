"""Generate an SVG screenshot of `vzpz init` for the README."""

from pathlib import Path

from rich.console import Console
from rich.text import Text

LOGO_LINES = [
    "██╗   ██╗███████╗██████╗ ███████╗",
    "██║   ██║╚══███╔╝██╔══██╗╚══███╔╝",
    "██║   ██║  ███╔╝ ██████╔╝  ███╔╝ ",
    "╚██╗ ██╔╝ ███╔╝  ██╔═══╝  ███╔╝  ",
    " ╚████╔╝ ███████╗██║     ███████╗",
    "  ╚═══╝  ╚══════╝╚═╝     ╚══════╝",
]

GRADIENT = ["cyan", "bright_cyan", "bright_magenta", "magenta", "bright_magenta", "cyan"]


def main() -> None:
    console = Console(record=True, width=72)
    console.print()

    for line, colour in zip(LOGO_LINES, GRADIENT):
        styled = Text(line, style=f"bold {colour}")
        console.print(styled, justify="center")

    console.print()
    console.print(Text("workspace initialised", style="bold white"), justify="center")
    console.print()

    out = Path(__file__).resolve().parent.parent / "docs" / "vzpz-init.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(console.export_svg(title="vzpz init"))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
