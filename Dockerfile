FROM python:3.8-alpine3.14

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.aliyun.com/g' /etc/apk/repositories

ENV OJ_ENV production

ADD . /app
WORKDIR /app

HEALTHCHECK --interval=5s --retries=3 CMD python3 /app/deploy/health_check.py

RUN apk add --update --no-cache build-base nginx openssl curl unzip supervisor jpeg-dev zlib-dev postgresql-dev freetype-dev libxml2-dev libxslt-dev && \
    pip install -i http://mirrors.cloud.aliyuncs.com/pypi/simple/ --trusted-host mirrors.cloud.aliyuncs.com --default-timeout=60 --no-cache-dir -r /app/deploy/requirements.txt && \
    apk del build-base --purge

RUN curl -L  $(curl -s  https://api.github.com/repos/xyq0220/OnlineJudgeFE/releases/latest | grep /dist.zip | cut -d '"' -f 4) -o dist.zip && \
    unzip dist.zip && \
    rm dist.zip

ENTRYPOINT /app/deploy/entrypoint.sh
