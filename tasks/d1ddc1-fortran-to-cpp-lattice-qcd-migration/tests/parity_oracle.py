"""Deterministic parity oracle + witness-search generator.

Capability: generate many input-parameter "witnesses" (input mocks), run both
the legacy Fortran reference and the migrated C++ target on each, and assert
deterministic output parity between the two. This is the core mechanism of the
"Locksmith Loop" from *Agentic Method for Deterministic Validation of Legacy
Code Migration* (arxiv:2607.28271v1): validate agentic coding output against
the original program under a deterministic oracle, pushing coverage beyond what
a single fixed input exercises.

Mode 2 (adapted port). The paper's *agentic* witness search -- an LLM-driven
loop that mutates input mocks to penetrate program branches, plus a "Locked
Paragraph" analyzer that names the condition blocking deeper exploration -- is
substituted here with a deterministic, parameter-free witness generator. The
substitution preserves the paper's framing concretely: for this program the
routing boundary is the thermalization-vs-measurement phase split
(`IF (ICFG-NTHERM) 10, 10, 20` in main.f), so the witness set deliberately
straddles that boundary (NTHERM=0, NMEAS=0, NTHERM==NMEAS) and sweeps the
inputs that drive the Metropolis accept/reject branches (beta scales the
acceptance coefficient `AK = BETA*SR/2`; the RNG seed picks the stochastic path
through accept/reject). The deterministic oracle itself -- run both sides on
the same input, compare outputs -- is reproduced at full fidelity.

This module imports nothing from the verifier; the compile/run/parse helpers
are injected by the caller, which is what ties it to the existing test suite
(see ``test_locksmith_parity`` and ``conftest``).
"""

from typing import Callable, Dict, List, Optional, Tuple

# A witness config mirrors the 7-line /app/data/params.dat layout, in order:
# (beta, kappa, nx, nt, ntherm, nmeas, seed).
# NX and NT are read by the program but the lattice loops are hard-coded to
# ``1, 4`` in gauge.f, so they carry no branch signal; they are held at the
# canonical 4x4 geometry and the witness search varies the signal-bearing dims.
WitnessConfig = Tuple[float, float, int, int, int, int, int]

# Float output keys compared by relative tolerance; integer keys compared exactly.
FLOAT_KEYS = ("PLAQ", "POLY", "ENRG", "ACCR")
INT_KEYS = ("NCFG", "SEED")
PARITY_TOLERANCE = 1e-10

# NX/NT are loop-inert here (see module docstring); fix them at the canonical
# geometry used by generate_data.py and the existing verifier.
_NX = 4
_NT = 4


def witness_configs() -> List[WitnessConfig]:
    """Deterministic witness search over the migration's parameter space.

    Returns an ordered, de-duplicated set of input mocks chosen to penetrate
    the program's routing regions -- the thermalization phase (ICFG <= NTHERM),
    the measurement phase (ICFG > NTHERM), and the Metropolis accept/reject
    branch driven by beta and the RNG seed. The set intentionally includes
    boundary cases that the single fixed ``params.dat`` and the three hard-coded
    configs in ``test_outputs.test_mutation_both_change_consistently`` never
    reach (no-thermalization, no-measurement, and equal-phase crossings).
    """
    configs: List[WitnessConfig] = []

    # (1) Locked-boundary probes: straddle the NTHERM phase split.
    configs.extend([
        (2.5, 0.10, _NX, _NT, 0, 5, 12345),    # skip thermalization entirely
        (2.5, 0.10, _NX, _NT, 10, 0, 12345),   # measurement phase empty
        (2.5, 0.10, _NX, _NT, 1, 1, 12345),    # one config in each phase
        (2.5, 0.10, _NX, _NT, 3, 3, 12345),    # NTHERM == NMEAS crossing
    ])

    # (2) beta sweep: scales the Metropolis acceptance AK = BETA*SR/2, so this
    #     exercises the accept/reject branch across coupling regimes.
    for beta in (1.5, 2.0, 3.0, 4.5, 6.0):
        configs.append((beta, 0.10, _NX, _NT, 5, 3, 24680))

    # (3) kappa sweep at fixed geometry and coupling.
    for kappa in (0.08, 0.12, 0.15):
        configs.append((2.5, kappa, _NX, _NT, 5, 3, 13579))

    # (4) RNG-seed sweep: different stochastic path through accept/reject.
    #     Seeds kept below 2**31-1 so they fit a Fortran INTEGER (int32).
    for seed in (999, 1000003, 2000003):
        configs.append((2.5, 0.10, _NX, _NT, 4, 2, seed))

    # De-duplicate while preserving the discovery order.
    seen = set()
    unique: List[WitnessConfig] = []
    for cfg in configs:
        if cfg not in seen:
            seen.add(cfg)
            unique.append(cfg)
    return unique


def format_params(config: WitnessConfig) -> str:
    """Render a witness config as the 7-line params.dat the programs read."""
    beta, kappa, nx, nt, ntherm, nmeas, seed = config
    return f"{beta}\n{kappa}\n{nx}\n{nt}\n{ntherm}\n{nmeas}\n{seed}\n"


def _describe(config: WitnessConfig) -> str:
    beta, kappa, nx, nt, ntherm, nmeas, seed = config
    return (
        f"beta={beta}, kappa={kappa}, nx={nx}, nt={nt}, "
        f"ntherm={ntherm}, nmeas={nmeas}, seed={seed}"
    )


def assert_output_parity(
    fortran_out: Dict[str, str],
    cpp_out: Dict[str, str],
    config: WitnessConfig,
    parse_float: Callable[[str], float],
    tolerance: float = PARITY_TOLERANCE,
) -> None:
    """Assert two parsed output dicts agree under the deterministic oracle.

    Integer keys (NCFG, SEED) must match exactly. Float keys (PLAQ, POLY, ENRG,
    ACCR) must match within ``tolerance`` by relative error when the reference
    magnitude is meaningful, else by absolute error -- the same rule the
    existing verifier uses. Raises ``AssertionError`` with the offending config
    and values on any mismatch.
    """
    which = _describe(config)

    for key in INT_KEYS:
        if key not in fortran_out or key not in cpp_out:
            raise AssertionError(
                f"{key} missing from output (config: {which}): "
                f"fortran={fortran_out.get(key)!r}, cpp={cpp_out.get(key)!r}"
            )
        if fortran_out[key].strip() != cpp_out[key].strip():
            raise AssertionError(
                f"{key} mismatch (config: {which}): "
                f"fortran={fortran_out[key]!r}, cpp={cpp_out[key]!r}"
            )

    for key in FLOAT_KEYS:
        if key not in fortran_out or key not in cpp_out:
            raise AssertionError(
                f"{key} missing from output (config: {which}): "
                f"fortran={fortran_out.get(key)!r}, cpp={cpp_out.get(key)!r}"
            )
        f_val = parse_float(fortran_out[key])
        c_val = parse_float(cpp_out[key])
        if abs(f_val) > 1e-12:
            rel_error = abs(f_val - c_val) / abs(f_val)
            if rel_error >= tolerance:
                raise AssertionError(
                    f"{key} mismatch (config: {which}): "
                    f"fortran={f_val}, cpp={c_val}, rel_error={rel_error}"
                )
        else:
            if abs(f_val - c_val) >= tolerance:
                raise AssertionError(
                    f"{key} mismatch (config: {which}): "
                    f"fortran={f_val}, cpp={c_val}"
                )


def run_parity_check(
    *,
    compile_fortran: Callable[[str], Tuple[bool, str]],
    compile_cpp: Callable[[str, str], Tuple[bool, str]],
    run_program: Callable[..., Tuple[bool, str, str]],
    parse_output_file: Callable[[str], Dict[str, str]],
    parse_float: Callable[[str], float],
    cpp_source: str,
    params_file: str,
    output_file: str,
    configs: Optional[List[WitnessConfig]] = None,
    workdir: Optional[str] = None,
) -> Dict[str, int]:
    """Run the deterministic parity oracle over the witness set.

    Compiles the Fortran reference and the migrated C++ target once, then for
    each witness config: writes ``params_file``, runs both programs, parses
    ``output_file`` after each run, and asserts parity. The original
    ``params_file`` is always restored and ``output_file`` cleaned up on exit.

    The compile/run/parse helpers are injected by the caller so this oracle
    reuses the verifier's existing forward path (the same
    ``compile_fortran`` / ``compile_cpp`` / ``run_program`` / parsing used by
    ``test_outputs``) rather than re-implementing it.

    Returns a small summary ``{"configs": N, "passed": N}``. Raises
    ``AssertionError`` on the first parity failure so pytest reports the
    offending config.
    """
    import os
    import tempfile

    configs = configs if configs is not None else witness_configs()
    workdir = workdir if workdir is not None else tempfile.mkdtemp(prefix="locksmith_")

    fortran_binary = os.path.join(workdir, "fortran_prog")
    cpp_binary = os.path.join(workdir, "cpp_prog")

    ok, stderr = compile_fortran(fortran_binary)
    if not ok:
        raise AssertionError(f"Fortran reference failed to compile: {stderr}")
    ok, stderr = compile_cpp(cpp_source, cpp_binary)
    if not ok:
        raise AssertionError(f"C++ migration failed to compile: {stderr}")

    with open(params_file, "r") as fh:
        original_params = fh.read()

    passed = 0
    try:
        for config in configs:
            with open(params_file, "w") as fh:
                fh.write(format_params(config))

            if os.path.exists(output_file):
                os.remove(output_file)
            ok, _, stderr = run_program(fortran_binary)
            if not ok:
                raise AssertionError(
                    f"Fortran execution failed (config: {_describe(config)}): {stderr}"
                )
            fortran_out = parse_output_file(output_file)

            if os.path.exists(output_file):
                os.remove(output_file)
            ok, _, stderr = run_program(cpp_binary)
            if not ok:
                raise AssertionError(
                    f"C++ execution failed (config: {_describe(config)}): {stderr}"
                )
            cpp_out = parse_output_file(output_file)

            assert_output_parity(fortran_out, cpp_out, config, parse_float)
            passed += 1
    finally:
        with open(params_file, "w") as fh:
            fh.write(original_params)
        if os.path.exists(output_file):
            os.remove(output_file)

    return {"configs": len(configs), "passed": passed}
