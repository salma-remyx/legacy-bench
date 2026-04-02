      *================================================================*
      * ACCOUNT-REC.CPY - Account Record Layout                        *
      * Contains COMP-3 (packed decimal) fields for balance            *
      *================================================================*
       01  ACCOUNT-RECORD.
           05  AR-ACCOUNT-ID           PIC 9(10).
           05  AR-ACCOUNT-NAME         PIC X(30).
           05  AR-ACCOUNT-TYPE         PIC X(1).
               88  AR-TYPE-CHECKING    VALUE 'C'.
               88  AR-TYPE-SAVINGS     VALUE 'S'.
               88  AR-TYPE-MONEY-MKT   VALUE 'M'.
           05  AR-STATUS               PIC X(1).
               88  AR-ACTIVE           VALUE 'A'.
               88  AR-CLOSED           VALUE 'C'.
               88  AR-FROZEN           VALUE 'F'.
           05  AR-BALANCE              PIC S9(11)V99 COMP-3.
           05  AR-INTEREST-RATE        PIC 9V9(4) COMP-3.
           05  AR-LAST-UPDATE          PIC 9(14).
           05  AR-DAILY-INTEREST       PIC S9(9)V99 COMP-3.
