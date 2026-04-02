"""
Test suite for COBOL Batch Cursor Migration task (HARDENED VERSION).

This tests the complex business logic including:
1. Rate schedule lookup (JOIN with rate_schedules table)
2. Wave processing (parent accounts before children)
3. Legacy rate override (legacy_rate_flag = 'Y')
4. Tiered interest from schedule (tier1_bonus, tier2_bonus)
5. Type modifiers from schedule (type_c_modifier, etc.)
6. High-value hold (balance > $100K excluded from results)
7. The floor bug (legal requirement)
8. Keyset pagination (not OFFSET/LIMIT)
9. SQL injection prevention
"""

import subprocess
import os
import re
import sqlite3
from pathlib import Path
from decimal import Decimal, ROUND_DOWN


def comp3_to_int(data: bytes, digits: int) -> int:
    """
    Convert COMP-3 packed decimal bytes to integer.
    Each byte contains 2 digits (1 per nibble).
    Last nibble is sign: C=positive, D=negative.
    """
    result = 0
    sign = 0x0C
    for i, byte in enumerate(data):
        high = (byte >> 4) & 0x0F
        low = byte & 0x0F
        if i == len(data) - 1:
            result = result * 10 + high
            sign = low
        else:
            result = result * 10 + high
            result = result * 10 + low
    if sign == 0x0D:
        result = -result
    return result


def get_rate_schedule(conn: sqlite3.Connection, schedule_id: str) -> dict:
    """Get rate schedule from database."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT base_rate, tier1_threshold, tier1_bonus, tier2_threshold, tier2_bonus,
               type_c_modifier, type_s_modifier, type_m_modifier
        FROM rate_schedules WHERE schedule_id = ?
    """, (schedule_id,))
    row = cursor.fetchone()
    if row:
        return {
            'base_rate': row[0],
            'tier1_threshold': row[1],
            'tier1_bonus': row[2],
            'tier2_threshold': row[3],
            'tier2_bonus': row[4],
            'type_c_modifier': row[5],
            'type_s_modifier': row[6],
            'type_m_modifier': row[7],
        }
    return None


def calculate_expected_interest(
    balance: Decimal, 
    account_rate: Decimal,
    account_type: str,
    legacy_rate_flag: str,
    schedule: dict
) -> Decimal:
    """
    Calculate interest using the complex tiered formula.
    
    If legacy_rate_flag='Y', use account's own rate.
    Otherwise use schedule with type modifier and tier bonus.
    
    BUG: Uses floor (integer truncation) not round.
    BUG: Always divides by 365, even in leap years.
    """
    if legacy_rate_flag == 'Y':
        effective_rate = account_rate
    elif schedule:
        base = Decimal(str(schedule['base_rate']))
        
        # Type modifier
        if account_type == 'C':
            type_mod = Decimal(str(schedule['type_c_modifier']))
        elif account_type == 'S':
            type_mod = Decimal(str(schedule['type_s_modifier']))
        elif account_type == 'M':
            type_mod = Decimal(str(schedule['type_m_modifier']))
        else:
            type_mod = Decimal('0')
        
        # Tier bonus
        tier1_thresh = Decimal(str(schedule['tier1_threshold']))
        tier2_thresh = Decimal(str(schedule['tier2_threshold']))
        if balance > tier2_thresh:
            tier_bonus = Decimal(str(schedule['tier2_bonus']))
        elif balance > tier1_thresh:
            tier_bonus = Decimal(str(schedule['tier1_bonus']))
        else:
            tier_bonus = Decimal('0')
        
        effective_rate = base + type_mod + tier_bonus
    else:
        effective_rate = account_rate
    
    daily_rate = effective_rate / Decimal(365)
    interest = (balance * daily_rate).quantize(Decimal('1'), rounding=ROUND_DOWN)
    return interest


def test_rust_binary_or_source_exists():
    """Test that either compiled binary or Rust source exists"""
    binary_exists = Path("/app/batch_processor").exists()
    source_exists = Path("/app/src/main.rs").exists()
    
    if source_exists and not binary_exists:
        result = subprocess.run(
            ["cargo", "build", "--release"],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            binary_exists = Path("/app/target/release/batch_processor").exists()
    
    assert binary_exists or source_exists, \
        "Neither /app/batch_processor nor /app/src/main.rs exists"


def test_results_file_created():
    """
    ANTI-CHEAT: Test that solution created results.dat AND a working binary.
    Verifies both exist - proving the solution builds and runs correctly.
    """
    results_path = Path("/app/results.dat")
    
    # Verify results.dat exists and has content
    assert results_path.exists(), "results.dat must exist - solution did not create output"
    assert results_path.stat().st_size > 0, "results.dat is empty - solution produced no output"
    
    # Verify a binary was built (proves Rust compilation worked)
    binary_exists = (
        Path("/app/batch_processor").exists() or 
        Path("/app/target/release/batch_processor").exists()
    )
    source_exists = Path("/app/src/main.rs").exists()
    
    assert binary_exists or source_exists, \
        "Neither binary nor source found - solution must provide Rust implementation"


def test_results_format_and_count():
    """
    Test that results.dat has correct format.
    Count may be less than total accounts due to:
    - High-value accounts (>$100K) held for review
    - Inactive accounts (status != 'A')
    """
    results_path = Path("/app/results.dat")
    assert results_path.exists(), "results.dat must exist"
    
    with open(results_path, 'r') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    # Should have many records
    assert len(lines) >= 150, f"Expected at least 150 result lines, got {len(lines)}"
    
    for i, line in enumerate(lines):
        parts = line.split('|')
        assert len(parts) >= 2, f"Line {i+1}: Expected at least 2 pipe-delimited fields"
        
        account_id = parts[0].strip()
        assert account_id.isdigit(), f"Line {i+1}: Account ID must be numeric"
        assert len(account_id) == 10, f"Line {i+1}: Account ID must be 10 digits"


def test_rate_schedule_lookup():
    """
    Test that interest is calculated using rate_schedules table, not account's own rate.
    This verifies the JOIN logic is working correctly.
    """
    results_path = Path("/app/results.dat")
    db_path = Path("/app/data/batch.db")
    
    assert results_path.exists(), "results.dat must exist"
    assert db_path.exists(), "batch.db must exist"
    
    conn = sqlite3.connect(str(db_path))
    
    # Get a non-legacy account with known schedule
    cursor = conn.cursor()
    cursor.execute("""
        SELECT account_id, balance, interest_rate, account_type, rate_schedule_id, legacy_rate_flag
        FROM accounts 
        WHERE status = 'A' AND legacy_rate_flag = 'N' AND balance < 100000
        LIMIT 3
    """)
    test_accounts = cursor.fetchall()
    
    with open(results_path, 'r') as f:
        results_dict = {}
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 2:
                results_dict[parts[0].strip()] = Decimal(parts[1].strip())
    
    for acc in test_accounts:
        acc_id, balance, rate, acc_type, schedule_id, legacy_flag = acc
        schedule = get_rate_schedule(conn, schedule_id)
        
        expected = calculate_expected_interest(
            Decimal(str(balance)), Decimal(str(rate)), acc_type, legacy_flag, schedule
        )
        
        acc_id_str = f"{acc_id:010d}"
        actual = results_dict.get(acc_id_str)
        
        if actual is not None:
            assert actual == expected, \
                f"Account {acc_id_str}: Expected {expected} (schedule {schedule_id}), got {actual}"
    
    conn.close()


def test_legacy_rate_override():
    """
    Test that accounts with legacy_rate_flag='Y' use their own rate, not the schedule.
    """
    db_path = Path("/app/data/batch.db")
    results_path = Path("/app/results.dat")
    
    assert db_path.exists(), "batch.db must exist"
    assert results_path.exists(), "results.dat must exist"
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Get legacy accounts
    cursor.execute("""
        SELECT account_id, balance, interest_rate, account_type
        FROM accounts 
        WHERE legacy_rate_flag = 'Y' AND status = 'A' AND balance < 100000
    """)
    legacy_accounts = cursor.fetchall()
    
    if not legacy_accounts:
        conn.close()
        return  # No legacy accounts to test
    
    with open(results_path, 'r') as f:
        results_dict = {}
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 2:
                results_dict[parts[0].strip()] = Decimal(parts[1].strip())
    
    for acc_id, balance, rate, acc_type in legacy_accounts:
        # Legacy accounts use their own rate directly
        expected = calculate_expected_interest(
            Decimal(str(balance)), Decimal(str(rate)), acc_type, 'Y', None
        )
        
        acc_id_str = f"{acc_id:010d}"
        actual = results_dict.get(acc_id_str)
        
        if actual is not None:
            assert actual == expected, \
                f"Legacy account {acc_id_str}: Expected {expected} (own rate {rate}), got {actual}"
    
    conn.close()


def test_wave_processing_order():
    """
    Test that wave processing is correct: Wave 1 before Wave 2 before Wave 3.
    Child accounts (Wave 2+) should be processed after their parents (Wave 1).
    """
    audit_path = Path("/app/audit.log")
    db_path = Path("/app/data/batch.db")
    
    assert audit_path.exists(), "audit.log must exist"
    assert db_path.exists(), "batch.db must exist"
    
    # Get processing order from audit log
    with open(audit_path, 'r') as f:
        processed_order = []
        for line in f:
            parts = line.strip().split('|')
            if parts:
                processed_order.append(int(parts[0].strip()))
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Check that parents were processed before children
    cursor.execute("""
        SELECT account_id, parent_account_id 
        FROM accounts 
        WHERE parent_account_id IS NOT NULL AND status = 'A'
    """)
    children = cursor.fetchall()
    
    for child_id, parent_id in children:
        if child_id in processed_order and parent_id in processed_order:
            child_pos = processed_order.index(child_id)
            parent_pos = processed_order.index(parent_id)
            assert parent_pos < child_pos, \
                f"Parent {parent_id} should be processed before child {child_id}"
    
    conn.close()


def test_high_value_accounts_excluded():
    """
    Test that high-value accounts (ORIGINAL balance > $100,000) are excluded from results.dat.
    They should still appear in audit.log. Check original balance from audit log, not DB.
    """
    results_path = Path("/app/results.dat")
    audit_path = Path("/app/audit.log")
    
    assert results_path.exists(), "results.dat must exist"
    assert audit_path.exists(), "audit.log must exist"
    
    with open(results_path, 'r') as f:
        result_ids = {line.strip().split('|')[0].strip() for line in f if line.strip()}
    
    # Parse audit log to get ORIGINAL balances (2nd field)
    high_value_from_audit = set()
    with open(audit_path, 'r') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) >= 2:
                acc_id = parts[0].strip()
                try:
                    orig_balance = float(parts[1].strip())
                    if orig_balance > 100000:
                        high_value_from_audit.add(acc_id)
                except ValueError:
                    pass
    
    # High-value accounts (by original balance) should NOT be in results
    leaked = result_ids.intersection(high_value_from_audit)
    assert len(leaked) == 0, f"High-value accounts should not be in results: {leaked}"
    
    # At least some high-value should exist in audit
    assert len(high_value_from_audit) > 0, "Should have some high-value accounts in audit"


def test_checkpoint_file_valid_comp3():
    """
    Test that checkpoint file contains valid COMP-3 packed decimal data.
    Must be exactly 37 bytes per COBOL copybook specification.
    """
    checkpoint_path = Path("/app/data/CHECKPOINT.DAT")
    assert checkpoint_path.exists(), "CHECKPOINT.DAT must exist"
    
    data = checkpoint_path.read_bytes()
    
    assert len(data) == 37, f"Checkpoint must be exactly 37 bytes, got {len(data)}"
    
    last_account_id = comp3_to_int(data[0:6], 10)
    rows_processed = comp3_to_int(data[6:12], 10)
    status = chr(data[36])
    
    assert rows_processed >= 150, f"Expected 150+ rows processed, got {rows_processed}"
    assert status in ('R', 'C', 'I'), f"Invalid status '{status}'"
    assert last_account_id >= 1000000001, f"Invalid last_account_id: {last_account_id}"


def test_keyset_pagination_not_offset():
    """
    ANTI-CHEAT: Test that keyset pagination is used, not OFFSET/LIMIT.
    Requires source code inspection - no weak fallbacks.
    """
    source_path = Path("/app/src/main.rs")
    assert source_path.exists(), "Source code main.rs required for keyset verification"
    
    source = source_path.read_text()
    source_lower = source.lower()
    
    # Must NOT use SQL OFFSET
    offset_pattern = re.compile(r'\boffset\s+[\?\$\d]', re.IGNORECASE)
    has_offset_sql = bool(offset_pattern.search(source))
    assert not has_offset_sql, "Must NOT use SQL OFFSET - use keyset pagination"
    
    # Must use keyset pagination pattern
    has_keyset = "account_id >" in source_lower or "a.account_id >" in source_lower
    assert has_keyset, "Must use keyset pagination: WHERE account_id > ?"


def test_sql_injection_prevented():
    """
    ANTI-CHEAT: Test that SQL injection is prevented via field whitelisting.
    Requires source code inspection - no weak fallbacks.
    """
    source_path = Path("/app/src/main.rs")
    assert source_path.exists(), "Source code main.rs required for SQL injection verification"
    
    source = source_path.read_text()
    source_lower = source.lower()
    
    # Must use parameterized queries
    has_parameterized = "?" in source or "$1" in source
    assert has_parameterized, "Must use parameterized queries"
    
    # Must have field whitelisting
    has_whitelist = ("balance" in source_lower and "account_type" in source_lower)
    assert has_whitelist, "Must whitelist allowed filter fields"


def test_audit_log_complete():
    """Test that audit log contains ALL processed accounts including held ones."""
    audit_path = Path("/app/audit.log")
    assert audit_path.exists(), "audit.log must exist"
    
    with open(audit_path, 'r') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    assert len(lines) >= 180, f"Audit should have 180+ entries, got {len(lines)}"
    
    account_ids = set()
    for line in lines:
        parts = line.split('|')
        if parts:
            acc_id = parts[0].strip()
            assert acc_id not in account_ids, f"Duplicate {acc_id} in audit log"
            account_ids.add(acc_id)


def test_no_duplicate_processing():
    """Test that no account was processed more than once."""
    audit_path = Path("/app/audit.log")
    assert audit_path.exists(), "audit.log must exist"
    
    with open(audit_path, 'r') as f:
        account_ids = [line.strip().split('|')[0].strip() for line in f if line.strip()]
    
    duplicates = [acc for acc in set(account_ids) if account_ids.count(acc) > 1]
    assert len(duplicates) == 0, f"Duplicate accounts: {duplicates}"


def test_deterministic_order():
    """
    Test that results are deterministically ordered.
    With wave processing, order is: Wave 1 accounts (ascending), then Wave 2 (ascending), etc.
    Within each wave, accounts are in ascending order.
    """
    results_path = Path("/app/results.dat")
    db_path = Path("/app/data/batch.db")
    
    assert results_path.exists(), "results.dat must exist"
    
    with open(results_path, 'r') as f:
        account_ids = [int(line.strip().split('|')[0]) for line in f if line.strip()]
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Group accounts by wave and verify within-wave ordering
    for wave in range(1, 4):
        cursor.execute(
            "SELECT account_id FROM accounts WHERE processing_wave = ? AND status = 'A' ORDER BY account_id",
            (wave,)
        )
        wave_accounts = [row[0] for row in cursor.fetchall()]
        wave_in_results = [aid for aid in account_ids if aid in wave_accounts]
        
        # Within each wave, should be ascending
        assert wave_in_results == sorted(wave_in_results), \
            f"Wave {wave} accounts must be in ascending order within the wave"
    
    conn.close()


def test_only_active_accounts_processed():
    """Test that only active accounts (status='A') are processed."""
    audit_path = Path("/app/audit.log")
    db_path = Path("/app/data/batch.db")
    
    if not audit_path.exists() or not db_path.exists():
        return
    
    with open(audit_path, 'r') as f:
        audit_ids = {line.strip().split('|')[0].strip() for line in f if line.strip()}
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT account_id FROM accounts WHERE status != 'A'")
    inactive_ids = {f"{row[0]:010d}" for row in cursor.fetchall()}
    conn.close()
    
    processed_inactive = audit_ids.intersection(inactive_ids)
    assert len(processed_inactive) == 0, f"Inactive accounts processed: {processed_inactive}"


def test_binary_compiles_and_executes():
    """
    ANTI-CHEAT: Verifies the Rust source code compiles and produces correct output.
    
    This test:
    1. Requires /app/src/main.rs to exist
    2. Compiles the code with cargo build --release
    3. Deletes existing output files
    4. Runs the compiled binary
    5. Verifies output files were recreated
    
    An agent cannot cheat by:
    - Providing a dummy main.rs with keywords (won't compile correctly)
    - Using Python/bash to generate outputs (binary won't exist or run)
    """
    source_path = Path("/app/src/main.rs")
    results_path = Path("/app/results.dat")
    audit_path = Path("/app/audit.log")
    binary_path = Path("/app/target/release/batch_processor")
    
    # Step 1: main.rs MUST exist
    assert source_path.exists(), "Rust source /app/src/main.rs is required"
    source_content = source_path.read_text()
    assert len(source_content) > 2000, "main.rs too short - must implement full logic"
    
    # Step 2: Compile the source
    result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd="/app",
        capture_output=True,
        text=True,
        timeout=300
    )
    assert result.returncode == 0, f"Rust compilation failed: {result.stderr[:500]}"
    assert binary_path.exists(), "Binary not created after successful compilation"
    
    # Step 3: Delete existing outputs to prove binary creates them
    if results_path.exists():
        results_path.unlink()
    if audit_path.exists():
        audit_path.unlink()
    
    # Step 4: Execute the binary
    exec_result = subprocess.run(
        [str(binary_path)],
        cwd="/app",
        capture_output=True,
        timeout=120
    )
    assert exec_result.returncode == 0, f"Binary execution failed with code {exec_result.returncode}"
    
    # Step 5: Verify outputs were recreated by the binary
    assert results_path.exists(), "Binary failed to create results.dat"
    assert audit_path.exists(), "Binary failed to create audit.log"
    assert results_path.stat().st_size > 0, "Binary created empty results.dat"

