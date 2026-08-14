      SUBROUTINE ATOFP(STR, IPOS, ILEN, DVAL, IERR)
C
C     Decode a signed fixed-point number with 10 fractional digits
C     from the card field STR(IPOS:ILEN).  Accepts an optional
C     leading '-' or '+'.  IERR: 0 ok, 1 no digits.
C
      CHARACTER*(*) STR
      INTEGER IPOS, ILEN, IERR
      INTEGER DIGVAL, I
      LOGICAL SEEND, NEG
      DOUBLE PRECISION DVAL, ACC
C
C     Accumulate into DOUBLE PRECISION in fixed-point units
C     (value*10**10) to avoid binary floating drift: every
C     representable field is exactly a decimal integer.
C
      ACC = 0.0D0
      SEEND = .FALSE.
      NEG = .FALSE.
      DO 100 I = IPOS, ILEN
         IF (STR(I:I) .GE. '0' .AND. STR(I:I) .LE. '9') THEN
            DIGVAL = ICHAR(STR(I:I)) - ICHAR('0')
            ACC = ACC*10.0D0 + DIGVAL
            SEEND = .TRUE.
         ELSE IF (.NOT. SEEND .AND. .NOT. NEG .AND.
     1            STR(I:I) .EQ. '-') THEN
            NEG = .TRUE.
         ELSE IF (.NOT. SEEND .AND. .NOT. NEG .AND.
     1            STR(I:I) .EQ. '+') THEN
            CONTINUE
         END IF
  100 CONTINUE
      IF (.NOT. SEEND) THEN
         IERR = 1
         RETURN
      END IF
      DVAL = ACC / 1.0D10
      IF (NEG) DVAL = -DVAL
      IERR = 0
      END
