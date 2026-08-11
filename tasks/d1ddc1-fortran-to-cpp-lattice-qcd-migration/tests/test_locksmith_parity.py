"""Locksmith Loop deterministic-parity tests.

Exercises the witness-based parity oracle in ``parity_oracle`` using the
existing compile/run/parse helpers from the task verifier (``test_outputs``).
This is the integration surface: the oracle re-uses ``test_outputs``'s forward
path (compile-fortran / compile-cpp / run / parse) instead of re-implementing
it, then drives that path across many generated inputs rather than the single
fixed ``params.dat``.

These tests are pulled into the verifier session that ``test.sh`` launches
(``pytest /tests/test_outputs.py``) by ``conftest.py``'s collection hook.
"""

import os

import pytest

# Existing verifier module (non-new) -- the call site whose forward path the
# oracle reuses. Importing these names from test_outputs is the integration
# surface: the oracle drives the verifier's own compile/run/parse forward path.
from test_outputs import (
    CPP_SOURCE,
    FORTRAN_MAIN,
    OUTPUT_FILE,
    PARAMS_FILE,
    compile_cpp,
    compile_fortran,
    parse_float,
    parse_output_file,
    run_program,
)

from parity_oracle import format_params, witness_configs


def _oracle_available() -> bool:
    """True only inside the task container, where /app is populated."""
    return os.path.exists(FORTRAN_MAIN) and os.path.exists(CPP_SOURCE)


def test_witness_set_covers_routing_boundaries():
    """The witness search must straddle the program's routing boundary.

    The Locked-Paragraph analog for this migration is the thermalization-vs-
    measurement phase split, so the generated set must include no-thermalization
    (NTHERM=0) and no-measurement (NMEAS=0) boundary configs, and must sweep
    the inputs that drive the Metropolis accept/reject branch (beta and the RNG
    seed). This runs without the container -- it is a pure check on the
    generator -- so the witness set is validated on every collection.
    """
    configs = witness_configs()
    assert len(configs) >= 8, f"witness set too small: {len(configs)} configs"

    # NTHERM=0 (all measurement) and NMEAS=0 (all thermalization) boundaries.
    ntherm_zero = any(c[4] == 0 for c in configs)
    nmeas_zero = any(c[5] == 0 for c in configs)
    assert ntherm_zero, "witness set missing NTHERM=0 boundary"
    assert nmeas_zero, "witness set missing NMEAS=0 boundary"

    # beta drives Metropolis acceptance; the set must sweep multiple regimes.
    betas = {c[0] for c in configs}
    assert len(betas) >= 3, f"witness set does not sweep beta: {betas}"

    # seed drives the stochastic accept/reject path; must vary it.
    seeds = {c[6] for c in configs}
    assert len(seeds) >= 3, f"witness set does not sweep seed: {seeds}"

    # All seeds must fit a Fortran INTEGER (signed int32).
    for seed in seeds:
        assert 0 <= seed < 2 ** 31, f"seed {seed} overflows int32"


def test_format_params_matches_seven_line_layout():
    """Witness configs must serialize to exactly the 7 values the programs read."""
    text = format_params((2.5, 0.10, 4, 4, 5, 3, 12345))
    lines = [ln for ln in text.split("\n") if ln != ""]
    assert len(lines) == 7
    assert lines[:2] == ["2.5", "0.1"]
    assert lines[2:] == ["4", "4", "5", "3", "12345"]


def test_locksmith_deterministic_parity():
    """Deterministic oracle: migrated C++ must match Fortran across the witness set.

    Compiles the legacy Fortran reference and the agent-produced C++ target once,
    then runs both on every generated witness config and asserts output parity
    (exact for NCFG/SEED, within 1e-10 for the float observables). This is the
    Locksmith Loop's core result -- validating agentic output against the
    original under a deterministic oracle, across inputs the fixed ``params.dat``
    never exercises. Skipped outside the task container where /app is absent.
    """
    if not _oracle_available():
        pytest.skip("Locksmith parity oracle needs the task container (/app)")

    from parity_oracle import run_parity_check

    result = run_parity_check(
        compile_fortran=compile_fortran,
        compile_cpp=compile_cpp,
        run_program=run_program,
        parse_output_file=parse_output_file,
        parse_float=parse_float,
        cpp_source=CPP_SOURCE,
        params_file=PARAMS_FILE,
        output_file=OUTPUT_FILE,
    )
    assert result["passed"] == result["configs"], (
        f"parity held on only {result['passed']}/{result['configs']} witness configs"
    )
