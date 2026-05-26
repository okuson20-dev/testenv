FROM alpine:3.20
RUN apk add --no-cache chrony
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 123/udp
ENTRYPOINT ["/entrypoint.sh"]
