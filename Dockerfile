FROM python:3.7
COPY ./dorcbot /dorcbot
WORKDIR /dorcbot
RUN python -m pip install -r ./requirements.txt
CMD  python dorcbot.py
