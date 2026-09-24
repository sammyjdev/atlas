import sys

from atlas_core.cli import main


def test_dispatches_fake_entry_point():
    seen: dict[str, list[str]] = {}

    def fake() -> int:
        seen["argv"] = sys.argv[:]
        raise SystemExit(0)

    code = main(["sage", "--help"], modules={"sage": fake})

    assert code == 0
    assert seen["argv"] == ["sage", "--help"]


def test_help_lists_module_names(capsys):
    code = main(["--help"], modules={"merit": lambda: 0, "sage": lambda: 0})

    assert code == 0
    out = capsys.readouterr().out
    assert "merit" in out
    assert "sage" in out
