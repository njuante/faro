# faro in a container. The agents are still reached over SSH, so mount a volume
# for /var/lib/faro (it holds the SSH key) and one for the config.
FROM python:3.13-alpine
RUN apk add --no-cache openssh-client \
 && adduser -D -h /var/lib/faro faro \
 && mkdir -p /etc/faro && chown faro:faro /etc/faro
WORKDIR /opt/faro
COPY faro ./faro
COPY agent ./agent
COPY web ./web
COPY faro.example.toml ./
USER faro
ENV FARO_CONFIG=/etc/faro/faro.toml PYTHONUNBUFFERED=1
EXPOSE 8080
VOLUME ["/var/lib/faro", "/etc/faro"]
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/api/me >/dev/null || exit 1
ENTRYPOINT ["python3", "-m", "faro"]
CMD ["serve"]
