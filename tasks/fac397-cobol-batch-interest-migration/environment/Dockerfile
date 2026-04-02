FROM python:3.13-slim-bookworm

WORKDIR /app

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gnucobol3 \
    sqlite3 \
    curl \
    build-essential \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install pytest==8.3.4

COPY src/ /app/src/
COPY data/ /app/data/

RUN chmod 777 /app /app/data

RUN sqlite3 /app/data/batch.db < /app/src/schema.sql && \
    sqlite3 /app/data/batch.db < /app/src/load_data.sql

# Setup Cargo project and vendor dependencies
RUN mkdir -p /app/oracle_build/src /app/oracle_build/.cargo && \
    cp /app/src/Cargo.toml.template /app/oracle_build/Cargo.toml && \
    cp /app/src/cargo-config.toml /app/oracle_build/.cargo/config.toml && \
    echo 'fn main() {}' > /app/oracle_build/src/main.rs && \
    cd /app/oracle_build && \
    cargo vendor /app/oracle_build/vendor && \
    cargo build --release
