      SUBROUTINE ATOUI(STR, IPOS, ILEN, IVAL, IERR)
C
C     Decode an unsigned decimal integer from the card field
C     STR(IPOS:ILEN).  IERR: 0 ok, 1 no digits, 2 overflow.
C
      CHARACTER*(*) STR
      INTEGER IPOS, ILEN, IVAL, IERR
      INTEGER DIGVAL, I
      LOGICAL SEEND
      DOUBLE PRECISION ACC
C
C     Accumulate into DOUBLE PRECISION so a full-card field can be
C     range-checked exactly before the narrowing store.
C
      ACC = 0.0D0
      SEEND = .FALSE.
      DO 100 I = IPOS, ILEN
         IF (STR(I:I) .LT. '0' .OR. STR(I:I) .GT. '9') GO TO 100
         DIGVAL = ICHAR(STR(I:I)) - ICHAR('0')
         ACC = ACC*10.0D0 + DIGVAL
         SEEND = .TRUE.
  100 CONTINUE
      IF (.NOT. SEEND) THEN
         IERR = 1
         RETURN
      END IF
      IF (ACC .GT. 2147483647.0D0) THEN
         IERR = 2
         RETURN
      END IF
      IVAL = ACC
      IERR = 0
      END
