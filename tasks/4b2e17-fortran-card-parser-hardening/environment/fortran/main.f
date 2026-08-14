      PROGRAM PARSDR
C
C     Card-field parser driver.
C
C     Reads one command per record from unit 5:
C
C       INT <start> <width> | <card image>
C       FIX <start> <width> | <card image>
C
C     The field to decode is columns <start> through <start>+<width>-1
C     of the card image that follows the '|' delimiter.  Responses on
C     unit 6 are one line per command:
C
C       OK val=<n>            successful integer decode
C       OK val=<d>            successful fixed-point decode (10 dp)
C       ERROR: no_digits      field held no decodable digits
C       ERROR: overflow       integer field exceeds 32-bit range
C       ERROR: bad_args       malformed command line
C       ERROR: bad_command    unknown keyword
C
      CHARACTER*132 CARD
      CHARACTER*8 CMD
      INTEGER ISTART, IWID, IPIPE, IPOS, ILEN, IVAL, IERR
      DOUBLE PRECISION DVAL
   10 CONTINUE
      READ(5,'(A)',END=200) CARD
      READ(CARD,*,END=190,ERR=190) CMD, ISTART, IWID
      IPIPE = INDEX(CARD,'|')
      IF (IPIPE .LT. 2 .OR. ISTART .LT. 1 .OR. IWID .LT. 1) GO TO 190
      IPOS = IPIPE + ISTART
      ILEN = IPIPE + ISTART + IWID - 1
      IF (ILEN .GT. 132) ILEN = 132
      IF (CMD .EQ. 'INT') THEN
         IF (IPOS .GT. 132) GO TO 120
         CALL ATOUI(CARD, IPOS, ILEN, IVAL, IERR)
         IF (IERR .EQ. 0) THEN
            WRITE(6,'(A,I0)') 'OK val=', IVAL
         ELSE IF (IERR .EQ. 2) THEN
            WRITE(6,'(A)') 'ERROR: overflow'
         ELSE
            GO TO 120
         END IF
      ELSE IF (CMD .EQ. 'FIX') THEN
         IF (IPOS .GT. 132) GO TO 120
         CALL ATOFP(CARD, IPOS, ILEN, DVAL, IERR)
         IF (IERR .EQ. 0) THEN
            WRITE(6,'(A,F20.10)') 'OK val=', DVAL
         ELSE
            GO TO 120
         END IF
      ELSE
         WRITE(6,'(A)') 'ERROR: bad_command'
      END IF
      GO TO 10
  120 CONTINUE
      WRITE(6,'(A)') 'ERROR: no_digits'
      GO TO 10
  190 CONTINUE
      WRITE(6,'(A)') 'ERROR: bad_args'
      GO TO 10
  200 CONTINUE
      END
