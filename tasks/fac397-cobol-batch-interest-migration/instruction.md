Migrate the COBOL batch interest calculation program at /app/src/INTRST01.cbl to Rust.

The existing COBOL program uses a WITH HOLD cursor pattern that remains open across COMMIT boundaries. SQLite does not directly support this behavior – to achieve similar functionality you need to apply keyset pagination with ordered fetches.

Key considerations in researching this conversion to Rust

1. The COBOL program stores the data in a checkpoint file in COMP-3 format. You will need to study the contents of the COPYBOOKS to determine the actual binary structure from the PIC.

2. The way interest is calculated depends on both account type and the account's balance tier. You will need to look through the COBOL program for all instances of the EVALUATE statements and how the logic of the calculation works, and to retain any odd quirks that may have originated intentionally.

3. The SQL statements used are generated dynamically from CONTROL.DAT, which would make them susceptible to SQL Injection attacks. You will need to validate SQL input using field whitelisting to ensure proper sanitization.

4. Your implementation should include logic to handle partially processed transactions (or "waves") related to dependencies between the accounts. Process Wave 1 before Wave 2, Wave 2 before Wave 3, etc. Within each wave, process accounts in ascending order by account_id.

5. Accounts with balance > $100,000 require high-value review and must be excluded from results.dat (but should still appear in audit.log). Only process accounts with status='A'.

Input files:

    /app/src/INTRST01.cbl, /app/src/COPYBOOKS/*.cpy, /app/src/schema.sql, /app/data/batch.db, /app/data/CHECKPOINT.DAT, /app/data/CONTROL.DAT

Output Requirements:

• The Rust implementation must be stored in /app/src/main.rs and compile to /app/target/release/batch_processor.

• Results will be stored in /app/results.dat (pipe delimited ACCOUNT_ID|INTEREST). ACCOUNT_ID is 10 digits, zero-padded. INTEREST is the calculated daily interest amount (integer, floor not round). Expect 150+ records after excluding high-value and inactive accounts.

• Updated checkpoint file in COBOL COMP-3 will be stored in /app/data/CHECKPOINT.DAT. The checkpoint is 37 bytes (derived from CHECKPOINT-REC.cpy).

• An Audit Log of all processing will be stored in /app/audit.log. Expect 180+ audit entries (includes high-value accounts).

Study the COBOL source, copybooks, and comments carefully. The exact formats, business rules, and calculation logic must be derived from the source code itself.
