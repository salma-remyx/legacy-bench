FROM python:3.13-slim-bookworm

WORKDIR /app
RUN apt-get update && apt-get install -y gfortran g++ strace && rm -rf /var/lib/apt/lists/*
RUN pip install --break-system-packages pytest==8.4.2 numpy==2.0.0

COPY fortran/ /app/fortran/

RUN mkdir -p /app/cpp

COPY generate_data.py /setup/generate_data.py
RUN python3 /setup/generate_data.py
