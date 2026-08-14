"""
Tests for Fortran card-field parser hardening task - ATOUI overflow rejection.
"""

import subprocess

import pytest


FORTRAN_DIR = '/app/fortran'
SOURCES = [
    '/app/fortran/main.f',
    '/app/fortran/cardio.f',
    '/app/fortran/fixpt.f',
]
BINARY = '/tmp/parsdr_cardio'

# (command line, expected response line prefix)
CASES = [
    # baseline behavior that must not regress
    ('INT 1 4 |1234ABCDEF', 'OK val=1234'),
    ('INT 1 2 | 7', 'OK val=7'),
    ('INT 1 10 |0000000042', 'OK val=42'),
    ('INT 1 10 |2147483647', 'OK val=2147483647'),
    ('FIX 1 12 |-123456789012', 'OK val='),
    ('FIX 1 10 |1234567890', 'OK val='),
    # the regression under test: out-of-range fields must be rejected
    ('INT 1 10 |4294967296', 'ERROR: overflow'),
    ('INT 1 10 |2147483648', 'ERROR: overflow'),
    ('INT 1 18 |999999999999999999', 'ERROR: overflow'),
    # unchanged error paths
    ('FIX 1 3 |ABC', 'ERROR: no_digits'),
    ('FOO 1 2 |12', 'ERROR: bad_command'),
    ('INT x y |12', 'ERROR: bad_args'),
]


def build():
    """Compile the three fixed-form sources and return (ok, stderr)."""
    result = subprocess.run(
        ['gfortran', '-std=legacy', '-ffixed-form', '-ffixed-line-length-132',
         '-o', BINARY] + SOURCES,
        capture_output=True, text=True
    )
    return result.returncode == 0, result.stderr


def run_cases(input_lines):
    """Run the binary over the given stdin lines; return (stdout, stderr)."""
    result = subprocess.run(
        [BINARY],
        input='\n'.join(input_lines) + '\n',
        capture_output=True, text=True, timeout=60
    )
    return result.stdout, result.stderr


@pytest.fixture(scope='session')
def compiled():
    ok, stderr = build()
    assert ok, f'compilation failed:\n{stderr}'
    return True


def test_in_range_fields_decode_unchanged(compiled):
    stdout, _ = run_cases([c for c, _ in CASES])
    lines = stdout.splitlines()
    assert len(lines) == len(CASES), f'expected {len(CASES)} responses, got {len(lines)}'
    for (cmd, expected), actual in zip(CASES, lines):
        assert actual.startswith(expected), f'{cmd!r}: expected {expected!r}, got {actual!r}'


def test_overflow_reports_error_not_wrapped_value(compiled):
    stdout, _ = run_cases(['INT 1 10 |4294967296'])
    assert 'ERROR: overflow' in stdout
    assert '429496729' not in stdout.replace('ERROR: overflow', '')


def test_max_int32_still_accepted(compiled):
    stdout, _ = run_cases(['INT 1 10 |2147483647'])
    assert stdout.strip() == 'OK val=2147483647'


def test_fixed_point_decoder_untouched(compiled):
    stdout, _ = run_cases(['FIX 1 12 |-123456789012'])
    assert stdout.strip().endswith('-1.2345678901')


def test_runs_clean(compiled):
    result = subprocess.run(
        [BINARY],
        input='INT 1 4 |1234\n',
        capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0
    assert result.stderr == ''
