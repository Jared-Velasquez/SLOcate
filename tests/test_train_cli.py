"""Tests for src/tracerca/train.py — the trainer Click surface and defaults.

End-to-end runs are deferred to the deploy session (they require vendored
TraceRCA-CD scripts + a live Tempo).
"""
from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from tracerca.train import (
    DEFAULT_HYPERPARAMS_PATH,
    load_default_hyperparams,
    parse_window,
    train,
)


def _option_names(cmd) -> set[str]:
    names: set[str] = set()
    for p in cmd.params:
        for opt in getattr(p, "opts", []):
            names.add(opt)
    return names


def test_train_click_options_present():
    opts = _option_names(train)
    for required in ("--baseline-source", "--window", "--out", "--tempo-url", "--hyperparams"):
        assert required in opts, f"missing {required} in trainer CLI"


def test_train_help_runs():
    runner = CliRunner()
    result = runner.invoke(train, ["--help"])
    assert result.exit_code == 0
    assert "--baseline-source" in result.output
    assert "--window" in result.output
    assert "--out" in result.output
    assert "--tempo-url" in result.output
    assert "--hyperparams" in result.output


def test_default_hyperparams_file_exists():
    assert DEFAULT_HYPERPARAMS_PATH.exists(), "default_hyperparams.yaml missing"


def test_default_hyperparams_parses_cleanly():
    hp = load_default_hyperparams()
    assert isinstance(hp, dict)
    assert hp["isolation_forest"]["contamination"] == 0.01
    assert hp["threshold"]["sigma"] == 1
    assert hp["localization"]["min_support_rate"] == 0.1
    assert hp["localization"]["k"] == 100


def test_default_hyperparams_caller_discount_alpha_is_1_5():
    hp = load_default_hyperparams()
    assert hp["localization"]["caller_discount_alpha"] == 1.5


def test_default_hyperparams_yaml_load_direct():
    raw = yaml.safe_load(DEFAULT_HYPERPARAMS_PATH.read_text())
    assert raw["localization"]["caller_discount_alpha"] == 1.5


def test_parse_window():
    assert parse_window("30m") == 30 * 60
    assert parse_window("5m") == 5 * 60
    assert parse_window("1h") == 3600
    assert parse_window("30s") == 30
