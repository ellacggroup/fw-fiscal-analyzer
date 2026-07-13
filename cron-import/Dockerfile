FROM curlimages/curl:latest

USER root
COPY run.sh /run.sh
RUN chmod +x /run.sh
USER curl_user

ENTRYPOINT ["/bin/sh", "/run.sh"]
