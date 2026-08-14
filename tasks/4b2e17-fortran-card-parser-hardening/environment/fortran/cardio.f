      SUBROUTINE ATOUI(STR, IPOS, ILEN, IVAL, IERR)
C
C     Decode an unsigned decimal integer from the card field
C     STR(IPOS:ILEN).  IERR: 0 ok, 1 no digits.
C
      CHARACTER*(*) STR
      INTEGER IPOS, ILEN, IVAL, IERR
      INTEGER DIGVAL, I
      LOGICAL SEEND
      IVAL = 0
      SEEND = .FALSE.
      DO 100 I = IPOS, ILEN
         IF (STR(I:I) .LT. '0' .OR. STR(I:I) .GT. '9') GO TO 100
         DIGVAL = ICHAR(STR(I:I)) - ICHAR('0')
         IVAL = IVAL*10 + DIGVAL
         SEEND = .TRUE.
  100 CONTINUE
      IF (.NOT. SEEND) THEN
         IERR = 1
         RETURN
      END IF
      IERR = 0
      END
