FROM alpine:3.20
RUN apk add --no-cache bind bind-tools
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 53/tcp 53/udp
ENTRYPOINT ["/entrypoint.sh"]
