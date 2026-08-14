You are given a legacy card-field parser in /app/fortran/. The code dates from a 1970s batch reporting system: fields were punched in fixed columns of an 80-column card image, and values were small (account numbers, amounts). It was minimally ported to modern hardware and has not been audited since.

The program implements a command interface reading from stdin and writing to stdout. Each line is one of:

- `INT <start> <width> | <card image>` — decode an unsigned decimal integer from columns `<start>` through `<start>+<width>-1` of the card image (column 1 is the first character after the `|`).
- `FIX <start> <width> | <card image>` — decode a signed fixed-point number with an implied 10 fractional digits from the same field layout.

Responses are one line per command:

- `OK val=<n>` — successful integer decode (`<n>` decimal, no padding).
- `OK val=<d>` — successful fixed-point decode, printed with `F20.10` formatting.
- `ERROR: no_digits` — the field held no decodable digits.
- `ERROR: overflow` — the integer field decodes to a value exceeding the 32-bit signed range.
- `ERROR: bad_args` — malformed command line (missing/non-numeric arguments, no `|` delimiter, non-positive start/width).
- `ERROR: bad_command` — the keyword is neither `INT` nor `FIX`.

The integer decoder in `cardio.f` (`ATOUI`) accumulates the result in a default INTEGER as it scans the field. On the original hardware every field that could physically be punched fit comfortably, so no range check was ever needed. Today the routine silently wraps: a 9+ digit field produces a wrong positive value with no indication of failure, and downstream postings are corrupted. The command driver in `main.f` already knows how to report `ERROR: overflow` (error code 2 from `ATOUI`) — nothing in the current `cardio.f` ever returns it.

Fix `ATOUI` so that any field whose decoded value exceeds 2147483647 is rejected with error code 2 (which the driver already maps to `ERROR: overflow`), while all existing behavior for in-range fields is preserved. The fixed-point decoder `ATOFP` and the driver `main.f` require no changes; do not modify them unless your fix demands it.

All edits must stay in /app/fortran/. The fixed sources must compile with `gfortran -std=legacy -ffixed-form -ffixed-line-length-132 -Wall -Wextra` without errors, and must run with exit code 0 and no stderr output. Do not use features unavailable in fixed-form legacy Fortran; keep the 72-column-era style of the surrounding code unless your fix requires otherwise.
