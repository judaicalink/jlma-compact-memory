# The Compact Memory showcase of mannheim.judaicalink.org: the app (server.py) and its jobs (jobs.py).
# Python standard library only; nothing is installed.
FROM python:3.13.16-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY cm/ cm/
COPY server.py jobs.py ./
USER 501:1000
EXPOSE 8110
CMD ["python3", "server.py"]
