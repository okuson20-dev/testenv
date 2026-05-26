FROM alpine:3.20
RUN apk add --no-cache rsyslog
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 514/tcp 514/udp
ENTRYPOINT ["/entrypoint.sh"]
