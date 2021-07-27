FROM python:3.7
RUN apt -y update && apt -y upgrade
RUN mkdir /dorcbot
COPY ./dorcbot/requirements.txt /dorcbot/
WORKDIR /dorcbot
RUN python -m pip install -r ./requirements.txt
COPY ./dorcbot /dorcbot
CMD  python dorcbot.py
