#!/usr/bin/env python3

import docker
import time

client = docker.from_env()
now = int(time.time())

print(f"[INFO] Checking for expired containers at {now}")

for container in client.containers.list(all=True):
    try:
        labels = container.labels
        expires_at = int(labels.get("expires", 0))

        if expires_at and expires_at < now:
            print(f"[INFO] Removing expired container {container.name} (expires at {expires_at})")
            container.remove(force=True)
        else:
            print(f"[DEBUG] Container {container.name} is still valid or untracked.")

    except Exception as e:
        print(f"[ERROR] Failed to check/remove container {container.name}: {e}")