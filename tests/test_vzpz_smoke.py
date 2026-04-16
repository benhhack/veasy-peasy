from typer.testing import CliRunner

from veasy_peasy.vzpz_cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "vzpz" in result.output.lower()
    assert "init" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_init():
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    assert "VZPZ" in result.output or "██" in result.output
    assert "initialised" in result.output
