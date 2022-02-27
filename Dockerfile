FROM python:3.10.2-slim-buster

COPY . .
RUN pip3 install -r requirements.txt
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
CMD ["python3", "./main.py", "-OO"]