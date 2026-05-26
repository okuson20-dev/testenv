FROM alpine:3.20
RUN apk add --no-cache iproute2 iptables bash
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
