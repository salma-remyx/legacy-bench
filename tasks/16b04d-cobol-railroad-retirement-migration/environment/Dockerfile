FROM python:3.13-slim-bookworm

WORKDIR /app

WORKDIR /app

RUN mkdir -p /app/src /app/bin /app/python

COPY src/ /app/src/

COPY copybooks/ /app/copybooks/

COPY data/ /app/data/

RUN pip install pytest==8.4.2

RUN apt-get update && apt-get install -y \
    build-essential \
    libgmp-dev \
    libdb-dev \
    libncurses5-dev \
    libxml2-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://sourceforge.net/projects/gnucobol/files/gnucobol/3.2/gnucobol-3.2.tar.xz/download -O gnucobol-3.2.tar.xz \
    && tar xf gnucobol-3.2.tar.xz \
    && cd gnucobol-3.2 \
    && ./configure --prefix=/usr/local \
    && make \
    && make install \
    && ldconfig \
    && cd .. \
    && rm -rf gnucobol-3.2 gnucobol-3.2.tar.xz
