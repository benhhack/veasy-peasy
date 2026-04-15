from typer.testing import CliRunner

from veasy_peasy.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "veasy" in result.output.lower() or "scan" in result.output.lower()


def test_scan_help():
    result = runner.invoke(app, ["scan", "--help"])
    assert result.exit_code == 0
    assert "--requirements" in result.output
