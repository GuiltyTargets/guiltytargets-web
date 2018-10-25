FROM python:3.6.6
MAINTAINER Charles Tapley Hoyt "cthoyt@gmail.com"

RUN pip install pipenv

ADD Pipfile /
ADD Pipfile.lock /
# RUN pipenv check
RUN pipenv install --system --deploy

COPY . /app
WORKDIR /app
