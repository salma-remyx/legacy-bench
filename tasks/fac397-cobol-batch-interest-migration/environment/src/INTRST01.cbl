
       IDENTIFICATION DIVISION.
       PROGRAM-ID.    INTRST01.
       AUTHOR.        LEGACY-BATCH-SYSTEMS.
       DATE-WRITTEN.  1994-06-15.
       DATE-COMPILED.
      *================================================================*
      * INTEREST CALCULATION BATCH PROCESSOR                           *
      * COBOL Batch System - Production Since 1994                      *
      *================================================================*

       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CHECKPOINT-FILE ASSIGN TO 'CHECKPOINT.DAT'
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE IS SEQUENTIAL
               FILE STATUS IS WS-CP-STATUS.
           SELECT CONTROL-FILE ASSIGN TO 'CONTROL.DAT'
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-CTL-STATUS.
           SELECT AUDIT-FILE ASSIGN TO 'audit.log'
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-AUD-STATUS.
           SELECT RESULTS-FILE ASSIGN TO 'results.dat'
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-RES-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  CHECKPOINT-FILE.
       COPY CHECKPOINT-REC.

       FD  CONTROL-FILE.
       01  CONTROL-RECORD.
           05  CTL-FILTER-FIELD        PIC X(20).
           05  CTL-OPERATOR            PIC X(2).
           05  CTL-VALUE               PIC X(50).

       FD  AUDIT-FILE.
       01  AUDIT-RECORD                PIC X(200).

       FD  RESULTS-FILE.
       01  RESULTS-RECORD              PIC X(100).

       WORKING-STORAGE SECTION.
       01  WS-CP-STATUS                PIC XX.
       01  WS-CTL-STATUS               PIC XX.
       01  WS-AUD-STATUS               PIC XX.
       01  WS-RES-STATUS               PIC XX.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  WS-EOF                  VALUE 'Y'.
       01  WS-COMMIT-CTR               PIC 9(10) VALUE 0.
       01  WS-COMMIT-INTERVAL          PIC 9(5) VALUE 100.

       01  WS-CURRENT-TIMESTAMP        PIC 9(14).
       01  WS-JOB-START-TIME           PIC 9(14).
       01  WS-CURRENT-WAVE             PIC 9(2) VALUE 1.
       01  WS-MAX-WAVE                 PIC 9(2) VALUE 3.

       COPY ACCOUNT-REC REPLACING ==01== BY ==01 WS-==.

      *================================================================*
      * RATE SCHEDULE WORK FIELDS - populated from rate_schedules JOIN *
      *================================================================*
       01  WS-RATE-SCHEDULE.
           05  WS-SCHEDULE-BASE-RATE    PIC 9V9(6).
           05  WS-TIER1-THRESHOLD       PIC 9(9)V99.
           05  WS-TIER1-BONUS           PIC 9V9(6).
           05  WS-TIER2-THRESHOLD       PIC 9(9)V99.
           05  WS-TIER2-BONUS           PIC 9V9(6).
           05  WS-TYPE-C-MOD            PIC 9V9(6).
           05  WS-TYPE-S-MOD            PIC 9V9(6).
           05  WS-TYPE-M-MOD            PIC 9V9(6).

       01  WS-INTEREST-CALC.
           05  WS-BASE-RATE            PIC 9V9(6).
           05  WS-TYPE-BONUS           PIC 9V9(6) VALUE 0.
           05  WS-TIER-BONUS           PIC 9V9(6) VALUE 0.
           05  WS-EFFECTIVE-RATE       PIC 9V9(6).
           05  WS-DAILY-RATE           PIC 9V9(8).
           05  WS-CALCULATED-INT       PIC S9(11)V99.
           05  WS-DAYS-IN-YEAR         PIC 9(3) VALUE 365.

       01  WS-REVIEW-FLAG              PIC X VALUE 'N'.
           88  WS-NEEDS-REVIEW         VALUE 'Y'.
       01  WS-REVIEW-THRESHOLD         PIC 9(9) VALUE 100000.
       01  WS-LEGACY-FLAG              PIC X VALUE 'N'.
           88  WS-USE-LEGACY-RATE      VALUE 'Y'.

       01  WS-DYNAMIC-SQL.
           05  WS-SQL-SELECT           PIC X(500).
           05  WS-SQL-WHERE            PIC X(200).
           05  WS-SQL-FULL             PIC X(800).

       01  WS-FILTER-FIELD             PIC X(20).
       01  WS-FILTER-OP                PIC X(2).
       01  WS-FILTER-VALUE             PIC X(50).

       01  WS-AUDIT-LINE               PIC X(200).
       01  WS-RESULT-LINE              PIC X(100).

       01  WS-LAST-ACCOUNT-ID          PIC 9(10) VALUE 0.
       01  WS-ROWS-THIS-RUN            PIC 9(10) VALUE 0.
       01  WS-TOTAL-INTEREST           PIC S9(13)V99 VALUE 0.

       EXEC SQL BEGIN DECLARE SECTION END-EXEC.
       01  HV-ACCOUNT-ID               PIC 9(10).
       01  HV-ACCOUNT-NAME             PIC X(30).
       01  HV-ACCOUNT-TYPE             PIC X(1).
       01  HV-STATUS                   PIC X(1).
       01  HV-BALANCE                  PIC S9(11)V99.
       01  HV-INTEREST-RATE            PIC 9V9(4).
       01  HV-LAST-UPDATE              PIC 9(14).
       01  HV-OPEN-DATE                PIC 9(8).
       01  HV-PARENT-ID                PIC 9(10).
       01  HV-RATE-SCHEDULE-ID         PIC X(20).
       01  HV-PROCESSING-WAVE          PIC 9(2).
       01  HV-LEGACY-RATE-FLAG         PIC X(1).
       01  HV-NEW-BALANCE              PIC S9(11)V99.
       01  HV-INTEREST-AMT             PIC S9(9)V99.
       01  HV-LAST-PROCESSED           PIC 9(10).
       01  HV-CURRENT-TIME             PIC 9(14).
       01  HV-JOB-START                PIC 9(14).
       01  HV-CURRENT-WAVE             PIC 9(2).
      * Rate schedule host variables
       01  HV-RS-BASE-RATE             PIC 9V9(6).
       01  HV-RS-TIER1-THRESH          PIC 9(9)V99.
       01  HV-RS-TIER1-BONUS           PIC 9V9(6).
       01  HV-RS-TIER2-THRESH          PIC 9(9)V99.
       01  HV-RS-TIER2-BONUS           PIC 9V9(6).
       01  HV-RS-TYPE-C-MOD            PIC 9V9(6).
       01  HV-RS-TYPE-S-MOD            PIC 9V9(6).
       01  HV-RS-TYPE-M-MOD            PIC 9V9(6).
       EXEC SQL END DECLARE SECTION END-EXEC.

       EXEC SQL INCLUDE SQLCA END-EXEC.

       PROCEDURE DIVISION.
       0000-MAIN-PARA.
           PERFORM 1000-INIT-PARA
           PERFORM 2000-READ-CHECKPOINT-PARA
           PERFORM 3000-READ-CONTROL-PARA
      *    WAVE PROCESSING: Process Wave 1 first, then Wave 2, etc.
           PERFORM VARYING WS-CURRENT-WAVE FROM 1 BY 1
               UNTIL WS-CURRENT-WAVE > WS-MAX-WAVE
               MOVE WS-CURRENT-WAVE TO HV-CURRENT-WAVE
               PERFORM 5000-DECLARE-CURSOR-PARA
               PERFORM 6000-PROCESS-ACCOUNTS-PARA
           END-PERFORM
           PERFORM 9000-CLEANUP-PARA
           STOP RUN.

       1000-INIT-PARA.
           MOVE FUNCTION CURRENT-DATE TO WS-JOB-START-TIME
           MOVE WS-JOB-START-TIME TO HV-JOB-START
           OPEN OUTPUT AUDIT-FILE
           OPEN OUTPUT RESULTS-FILE
           IF WS-AUD-STATUS NOT = '00'
               DISPLAY 'ERROR OPENING AUDIT FILE'
               STOP RUN
           END-IF.

       2000-READ-CHECKPOINT-PARA.
           OPEN INPUT CHECKPOINT-FILE
           IF WS-CP-STATUS = '00'
               READ CHECKPOINT-FILE INTO CHECKPOINT-RECORD
               IF WS-CP-STATUS = '00'
                   MOVE CP-LAST-ACCOUNT-ID TO WS-LAST-ACCOUNT-ID
                   MOVE CP-LAST-ACCOUNT-ID TO HV-LAST-PROCESSED
                   MOVE CP-ROWS-PROCESSED TO WS-ROWS-THIS-RUN
                   MOVE CP-TOTAL-INTEREST TO WS-TOTAL-INTEREST
                   IF CP-RUNNING
                       DISPLAY 'RESTART FROM CHECKPOINT: ' 
                               WS-LAST-ACCOUNT-ID
                   END-IF
               ELSE
                   MOVE 0 TO WS-LAST-ACCOUNT-ID
                   MOVE 0 TO HV-LAST-PROCESSED
               END-IF
               CLOSE CHECKPOINT-FILE
           ELSE
               MOVE 0 TO WS-LAST-ACCOUNT-ID
               MOVE 0 TO HV-LAST-PROCESSED
           END-IF.

       3000-READ-CONTROL-PARA.
           OPEN INPUT CONTROL-FILE
           IF WS-CTL-STATUS = '00'
               READ CONTROL-FILE INTO CONTROL-RECORD
               IF WS-CTL-STATUS = '00'
                   MOVE CTL-FILTER-FIELD TO WS-FILTER-FIELD
                   MOVE CTL-OPERATOR TO WS-FILTER-OP
                   MOVE CTL-VALUE TO WS-FILTER-VALUE
               END-IF
               CLOSE CONTROL-FILE
           END-IF.

      *================================================================*
      * CURSOR WITH HOLD - stays open across COMMIT statements         *
      * Note: Also filters by processing_wave for dependency ordering  *
      * ALLOWED FILTER FIELDS: balance, account_type, status ONLY      *
      *================================================================*
       5000-DECLARE-CURSOR-PARA.
           EXEC SQL
               DECLARE C1 CURSOR WITH HOLD FOR
               SELECT A.ACCOUNT_ID, A.ACCOUNT_NAME, A.ACCOUNT_TYPE,
                      A.STATUS, A.BALANCE, A.INTEREST_RATE, 
                      A.LAST_UPDATE, A.OPEN_DATE, A.PARENT_ACCOUNT_ID,
                      A.RATE_SCHEDULE_ID, A.PROCESSING_WAVE,
                      A.LEGACY_RATE_FLAG,
                      R.BASE_RATE, R.TIER1_THRESHOLD, R.TIER1_BONUS,
                      R.TIER2_THRESHOLD, R.TIER2_BONUS,
                      R.TYPE_C_MODIFIER, R.TYPE_S_MODIFIER, 
                      R.TYPE_M_MODIFIER
               FROM ACCOUNTS A
               LEFT JOIN RATE_SCHEDULES R 
                   ON A.RATE_SCHEDULE_ID = R.SCHEDULE_ID
               WHERE A.ACCOUNT_ID > :HV-LAST-PROCESSED
                 AND A.STATUS = 'A'
                 AND A.PROCESSING_WAVE = :HV-CURRENT-WAVE
               ORDER BY A.ACCOUNT_ID
               FOR UPDATE OF BALANCE, LAST_UPDATE
           END-EXEC
           
           EXEC SQL OPEN C1 END-EXEC
           IF SQLCODE NOT = 0
               DISPLAY 'ERROR OPENING CURSOR: ' SQLCODE
               STOP RUN
           END-IF.

       6000-PROCESS-ACCOUNTS-PARA.
           MOVE 'N' TO WS-EOF-FLAG
           PERFORM UNTIL WS-EOF
               EXEC SQL
                   FETCH C1 INTO 
                       :HV-ACCOUNT-ID,
                       :HV-ACCOUNT-NAME,
                       :HV-ACCOUNT-TYPE,
                       :HV-STATUS,
                       :HV-BALANCE,
                       :HV-INTEREST-RATE,
                       :HV-LAST-UPDATE,
                       :HV-OPEN-DATE,
                       :HV-PARENT-ID,
                       :HV-RATE-SCHEDULE-ID,
                       :HV-PROCESSING-WAVE,
                       :HV-LEGACY-RATE-FLAG,
                       :HV-RS-BASE-RATE,
                       :HV-RS-TIER1-THRESH,
                       :HV-RS-TIER1-BONUS,
                       :HV-RS-TIER2-THRESH,
                       :HV-RS-TIER2-BONUS,
                       :HV-RS-TYPE-C-MOD,
                       :HV-RS-TYPE-S-MOD,
                       :HV-RS-TYPE-M-MOD
               END-EXEC
               
               EVALUATE SQLCODE
                   WHEN 0
                       PERFORM 6050-CHECK-REVIEW-PARA
                       PERFORM 6100-CALCULATE-INTEREST-PARA
                       PERFORM 6200-UPDATE-ACCOUNT-PARA
                       PERFORM 6300-WRITE-AUDIT-PARA
                       IF NOT WS-NEEDS-REVIEW
                           PERFORM 6400-WRITE-RESULT-PARA
                       END-IF
                       ADD 1 TO WS-COMMIT-CTR
                       ADD 1 TO WS-ROWS-THIS-RUN
                       MOVE HV-ACCOUNT-ID TO WS-LAST-ACCOUNT-ID
                       
                       IF WS-COMMIT-CTR >= WS-COMMIT-INTERVAL
                           PERFORM 7000-COMMIT-CHECKPOINT-PARA
                           MOVE 0 TO WS-COMMIT-CTR
                       END-IF
                   WHEN 100
                       SET WS-EOF TO TRUE
                   WHEN OTHER
                       DISPLAY 'FETCH ERROR: ' SQLCODE
                       SET WS-EOF TO TRUE
               END-EVALUATE
           END-PERFORM
           EXEC SQL CLOSE C1 END-EXEC.

       6050-CHECK-REVIEW-PARA.
           MOVE 'N' TO WS-REVIEW-FLAG
           IF HV-BALANCE > WS-REVIEW-THRESHOLD
               MOVE 'Y' TO WS-REVIEW-FLAG
           END-IF.

      *================================================================*
      * INTEREST CALCULATION WITH RATE SCHEDULE LOOKUP                  *
      *                                                                 *
      * This is the complex part - rate comes from rate_schedules       *
      * table UNLESS legacy_rate_flag = 'Y'.                           *
      *                                                                 *
      * Formula: effective_rate = base_rate + type_modifier + tier_bonus*
      * Then:    daily_rate = effective_rate / 365                      *
      * Then:    interest = FLOOR(balance * daily_rate)                 *
      *================================================================*
       6100-CALCULATE-INTEREST-PARA.
           MOVE 0 TO WS-TYPE-BONUS
           MOVE 0 TO WS-TIER-BONUS
           
      *    Check if using legacy rate or schedule
           IF HV-LEGACY-RATE-FLAG = 'Y'
               MOVE HV-INTEREST-RATE TO WS-BASE-RATE
               MOVE 0 TO WS-TYPE-BONUS
               MOVE 0 TO WS-TIER-BONUS
           ELSE
               MOVE HV-RS-BASE-RATE TO WS-BASE-RATE
      *        Apply type modifier from schedule
               EVALUATE HV-ACCOUNT-TYPE
                   WHEN 'C'
                       MOVE HV-RS-TYPE-C-MOD TO WS-TYPE-BONUS
                   WHEN 'S'
                       MOVE HV-RS-TYPE-S-MOD TO WS-TYPE-BONUS
                   WHEN 'M'
                       MOVE HV-RS-TYPE-M-MOD TO WS-TYPE-BONUS
                   WHEN OTHER
                       MOVE 0 TO WS-TYPE-BONUS
               END-EVALUATE
      *        Apply tier bonus from schedule based on balance
               EVALUATE TRUE
                   WHEN HV-BALANCE > HV-RS-TIER2-THRESH
                       MOVE HV-RS-TIER2-BONUS TO WS-TIER-BONUS
                   WHEN HV-BALANCE > HV-RS-TIER1-THRESH
                       MOVE HV-RS-TIER1-BONUS TO WS-TIER-BONUS
                   WHEN OTHER
                       MOVE 0 TO WS-TIER-BONUS
               END-EVALUATE
           END-IF
           
           COMPUTE WS-EFFECTIVE-RATE = 
               WS-BASE-RATE + WS-TYPE-BONUS + WS-TIER-BONUS
           
           COMPUTE WS-DAILY-RATE = WS-EFFECTIVE-RATE / WS-DAYS-IN-YEAR
           
           COMPUTE WS-CALCULATED-INT = 
               FUNCTION INTEGER(HV-BALANCE * WS-DAILY-RATE)
           
           MOVE WS-CALCULATED-INT TO HV-INTEREST-AMT
           ADD WS-CALCULATED-INT TO WS-TOTAL-INTEREST.

       6200-UPDATE-ACCOUNT-PARA.
           MOVE FUNCTION CURRENT-DATE TO HV-CURRENT-TIME
           COMPUTE HV-NEW-BALANCE = HV-BALANCE + HV-INTEREST-AMT
           
           EXEC SQL
               UPDATE ACCOUNTS
               SET BALANCE = :HV-NEW-BALANCE,
                   LAST_UPDATE = :HV-CURRENT-TIME
               WHERE CURRENT OF C1
           END-EXEC
           
           IF SQLCODE NOT = 0
               DISPLAY 'UPDATE ERROR: ' SQLCODE
           END-IF.

       6300-WRITE-AUDIT-PARA.
           STRING HV-ACCOUNT-ID DELIMITED BY SIZE
                  '|' DELIMITED BY SIZE
                  HV-BALANCE DELIMITED BY SIZE
                  '|' DELIMITED BY SIZE
                  HV-INTEREST-AMT DELIMITED BY SIZE
                  '|' DELIMITED BY SIZE
                  HV-NEW-BALANCE DELIMITED BY SIZE
                  '|' DELIMITED BY SIZE
                  HV-CURRENT-TIME DELIMITED BY SIZE
                  INTO WS-AUDIT-LINE
           END-STRING
           WRITE AUDIT-RECORD FROM WS-AUDIT-LINE.

       6400-WRITE-RESULT-PARA.
           STRING HV-ACCOUNT-ID DELIMITED BY SIZE
                  '|' DELIMITED BY SIZE
                  HV-INTEREST-AMT DELIMITED BY SIZE
                  INTO WS-RESULT-LINE
           END-STRING
           WRITE RESULTS-RECORD FROM WS-RESULT-LINE.

       7000-COMMIT-CHECKPOINT-PARA.
           EXEC SQL COMMIT END-EXEC
           
           IF SQLCODE = 0
               OPEN OUTPUT CHECKPOINT-FILE
               MOVE WS-LAST-ACCOUNT-ID TO CP-LAST-ACCOUNT-ID
               MOVE WS-ROWS-THIS-RUN TO CP-ROWS-PROCESSED
               MOVE WS-TOTAL-INTEREST TO CP-TOTAL-INTEREST
               MOVE WS-JOB-START-TIME TO CP-JOB-START-TIME
               MOVE FUNCTION CURRENT-DATE TO CP-LAST-COMMIT-TIME
               SET CP-RUNNING TO TRUE
               WRITE CHECKPOINT-RECORD
               CLOSE CHECKPOINT-FILE
               DISPLAY 'CHECKPOINT AT ACCOUNT: ' WS-LAST-ACCOUNT-ID
                       ' ROWS: ' WS-ROWS-THIS-RUN
                       ' WAVE: ' WS-CURRENT-WAVE
           ELSE
               DISPLAY 'COMMIT FAILED: ' SQLCODE
               EXEC SQL ROLLBACK END-EXEC
               STOP RUN
           END-IF.

       9000-CLEANUP-PARA.
           EXEC SQL COMMIT END-EXEC
           
           OPEN OUTPUT CHECKPOINT-FILE
           MOVE WS-LAST-ACCOUNT-ID TO CP-LAST-ACCOUNT-ID
           MOVE WS-ROWS-THIS-RUN TO CP-ROWS-PROCESSED
           MOVE WS-TOTAL-INTEREST TO CP-TOTAL-INTEREST
           MOVE WS-JOB-START-TIME TO CP-JOB-START-TIME
           MOVE FUNCTION CURRENT-DATE TO CP-LAST-COMMIT-TIME
           SET CP-COMPLETED TO TRUE
           WRITE CHECKPOINT-RECORD
           CLOSE CHECKPOINT-FILE
           
           CLOSE AUDIT-FILE
           CLOSE RESULTS-FILE
           
           DISPLAY 'BATCH COMPLETE. TOTAL ROWS: ' WS-ROWS-THIS-RUN
           DISPLAY 'TOTAL INTEREST: ' WS-TOTAL-INTEREST.
