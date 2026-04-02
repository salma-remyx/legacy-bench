      *================================================================*
      * CHECKPOINT-REC.CPY - Checkpoint Record Layout                  *
      * All numeric fields in COMP-3 (packed decimal) format           *
      *================================================================*
       01  CHECKPOINT-RECORD.
           05  CP-LAST-ACCOUNT-ID      PIC 9(10) COMP-3.
           05  CP-ROWS-PROCESSED       PIC 9(10) COMP-3.
           05  CP-TOTAL-INTEREST       PIC S9(13)V99 COMP-3.
           05  CP-JOB-START-TIME       PIC 9(14) COMP-3.
           05  CP-LAST-COMMIT-TIME     PIC 9(14) COMP-3.
           05  CP-STATUS               PIC X(1).
               88  CP-RUNNING          VALUE 'R'.
               88  CP-COMPLETED        VALUE 'C'.
               88  CP-FAILED           VALUE 'F'.
