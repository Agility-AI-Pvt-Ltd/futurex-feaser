FROM alpine:3.20

RUN apk add --no-cache \
    aws-cli \
    bash \
    curl \
    gzip \
    jq

COPY backup.sh /backup/backup.sh
COPY entrypoint.sh /backup/entrypoint.sh

RUN chmod +x /backup/backup.sh /backup/entrypoint.sh

ENTRYPOINT ["/backup/entrypoint.sh"]
