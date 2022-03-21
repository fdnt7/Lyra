FROM python:3.10.2-slim-buster

WORKDIR /app

COPY . .
RUN find . \! -iname "*-db-firebase-adminsdk-*.json"  -mindepth 2 -maxdepth 2 -print | xargs rm -rf

FROM python:3.10.2-slim-buster

WORKDIR /app

COPY --from=0 ["/app", "shared"]
COPY config.yml shared/config.yml
COPY bands.yml shared/bands.yml
COPY lyra .

ENV IN_DOCKER Yes
ENV TZ=Asia/Bangkok
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
RUN date

RUN curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh
RUN pip3 install -Ur requirements.txt
CMD ["python3", "main.py", "-OO"]