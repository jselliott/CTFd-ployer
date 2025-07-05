# CTFd-Ployer
A collection of docker-compose services for deploying per-player CTF challenge instances on a large GCP instance. This is designed to happen in a private VPC so that CTFd can communicate with the service on the backend as needed. The system was designed for small clubs and organizations that want the flexibility of having per-player instances without the overhead of using Kubernetes. During the 2025 US Cyber Open, this system allowed for over 1,300 players to launch challenges on demand at a cost of around $15 per day using a e2-highmem-8 (8 vCPUs, 64 GB Memory) in GCP as the challenge host.

### General Workflow

* Player clicks the "Start Instance" button on a CTF challenge on a CTFd instance using the deployer plugin.
* CTFd send a request to the deployer app asking it to spin up a specific image with a timeout and player ID from CTFd
* If another challenge is currently deployed for that user, it is shut down
* The challenge is deployed on a random, available high number port
* A new entry is mapped in nginx with a random subdomain
* The domain name is returned to CTFd, which displays it for the user and also shows a countdown
* Additional endpoints for /status, etc can be pinged to return instance status for a player to CTFd
* When a challenge times out or the player clicks the Stop button, the container is stopped and removed and the nginx proxy removes the path

### TCP Connect Challenges

For TCP connection challenges for pwn/crypto/misc/etc, the system will skip the nginx proxy and just return the raw port to the service for players to connect to.

## Installation

* Clone this repo

```git clone https://github.com/jselliott/CTFd-ployer.git```

* Update the base domain in docker-compose.yaml
* Update the SSL certs that are mounted in the nginx container to a valid wildcard certificate that will allow for random subdomains for instances.
* Build and run the services

```
docker-compose build
docker-compose up -d
```

* Consider pre-pulling images for challenges so they are on-hand when needed and don't slow down launch times.
* Install the [CTFd-Ployer Plugin](https://github.com/jselliott/CTFd-ployer-Plugin) on your CTFd instance and configure it.

## !!! SECURITY CONSIDERATIONS !!!

This system allows the launcher service to start and stop Docker containers. This means that it can potentially be used to exploit your system if exposed to the internet and an attacker can launch arbitrary containers. **ONLY** run this inside a controlled VPC and set up firewall rules so that port 443 is exposed to the internet as well as high ephemeral ports for TCP challenges. Port 8000 should **ONLY** allow communication from your CTFd host. Additionally, the service account for your instance should only have very basic read registry permissions to pull images needed for challenges. I'm not responsible if you get hacked!