FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    e2fsprogs \
    xfsprogs \
    btrfs-progs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /cloud
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN mkdir -p disks_images

CMD ["python3", "main.py"]