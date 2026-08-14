FROM python:3.13-slim-bookworm

WORKDIR /app
RUN apt-get update && apt-get install -y gfortran && rm -rf /var/lib/apt/lists/*
RUN pip install --break-system-packages pytest==8.4.2

COPY fortran/ /app/fortran/
