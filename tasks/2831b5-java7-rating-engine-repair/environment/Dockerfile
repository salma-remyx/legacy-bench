FROM ubuntu:24.04

WORKDIR /app

RUN apt-get update && apt-get install -y wget gnupg python3 python3-pip && \
    wget -qO - https://repos.azul.com/azul-repo.key | gpg --dearmor -o /usr/share/keyrings/azul.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/azul.gpg] https://repos.azul.com/zulu/deb stable main" > /etc/apt/sources.list.d/zulu.list && \
    apt-get update && apt-get install -y zulu7-jdk jq && \
    rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/zulu7
ENV PATH=$JAVA_HOME/bin:$PATH

RUN pip3 install --break-system-packages pytest==8.0.0

WORKDIR /app

COPY docs/cdr_format.txt /app/docs/cdr_format.txt
COPY src/com/telecom/*.java /app/src/com/telecom/
COPY CDRGenerator.java /app/CDRGenerator.java

RUN javac /app/CDRGenerator.java && \
    java -cp /app CDRGenerator && \
    rm /app/CDRGenerator.java /app/CDRGenerator.class

RUN mkdir -p /app/bin
