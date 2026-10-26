FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY culler ./culler

# Run as an ordinary user so files written into the mounted photo folder
# aren't owned by root on the host.
RUN useradd --create-home culler
USER culler

ENTRYPOINT ["python", "-m", "culler"]
CMD ["scan", "/photos"]
