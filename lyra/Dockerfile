FROM python:3.10.2-slim-buster

WORKDIR /app

COPY config.yml shared/config.yml
COPY bands.yml shared/bands.yml
COPY lyra .

ENV IN_DOCKER Yes
ENV TZ=Asia/Bangkok
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN date

RUN apt update -y && apt upgrade -y
RUN apt install git curl -y
RUN curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
RUN pip3 install -Ur requirements.txt
CMD ["python3", "main.py", "-OO"]