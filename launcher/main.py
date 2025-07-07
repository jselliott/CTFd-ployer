import os
import string
import random
import docker
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import socket
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DOMAIN = os.getenv("BASE_DOMAIN","ctf.example.com")

app = FastAPI()
client = docker.from_env()
NGINX_CONF_DIR = "/mnt/nginx/conf.d"

class LaunchRequest(BaseModel):
    image: str
    port: str
    challenge_id: str
    player_id: str
    expires: str
    flag: str = ""
    type: str = "web"

class StopRequest(BaseModel):
    player_id: str
    challenge_id: str

class StopContainerRequest(BaseModel):
    container_id: str

class StatusRequest(BaseModel):
    player_id: str
    challenge_id: str

def random_subdomain():
    return ''.join(random.choices(string.ascii_lowercase, k=8))


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@app.get("/")
def health():
    return {"healthy":"OK"}

@app.post("/launch")
def launch_challenge(req: LaunchRequest):
    sub = random_subdomain()
    port = get_free_port()

    container_name = f"{req.player_id}_{sub}"
    fqdn = f"{sub}.{BASE_DOMAIN}"

    if req.flag != "":

        path = f"/tmp/flags/{container_name}.flag"

        with open(path, "w") as f:
            f.write(req.flag)

        volumes={path: {'bind': '/flag.txt', 'mode': 'ro'}}

    else:
        volumes = {}

    try:
        container = client.containers.run(
            req.image,
            name=container_name,
            ports={"%s/tcp" % req.port: port},
            detach=True,
            volumes=volumes,
            environment={"FQDN":fqdn},
            labels={"challenge_container":"true","ctf_player": req.player_id, "ctf_subdomain": sub, "started_at":str(int(time.time())),"expires":req.expires, "ctf_challenge": req.challenge_id}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail={"error":str(e)})

    if req.type == "web":
        # Write NGINX route
        nginx_conf = f"""
server {{
    listen 80;
    server_name {fqdn};
    return 301 https://$host$request_uri;
}}

server {{
    listen 443 ssl;
    server_name {fqdn};

    ssl_certificate     /etc/ssl/certs/fullchain.pem;
    ssl_certificate_key /etc/ssl/private/privkey.pem;

    location / {{
        
        if ($is_bad_agent) {{
            return 302 {BASE_DOMAIN}/rules.html;
        }}

        limit_req zone=perip burst=10;
        proxy_pass http://172.17.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }}
}}
    """

        conf_path = Path(NGINX_CONF_DIR) / f"{fqdn}.conf"
        conf_path.write_text(nginx_conf)
        
        nginx = client.containers.get("uscg-nginx")
        output = nginx.exec_run("nginx -s reload")

        return {"url": f"https://{fqdn}", "container": container.id}
    else:
        return {"url":f'nc {BASE_DOMAIN} {port}', "container": container.id}

@app.post("/status")
def player_status(req: StatusRequest):
    containers = client.containers.list(
        filters={"label": [f"ctf_player={req.player_id}",
                           f"ctf_challenge={req.challenge_id}"]}
    )
    if not containers:
        return []

    clist = []
    for c in containers:
        expires = c.labels.get("ctf_player")
        clist.append({"expires":expires})
    return clist

@app.post("/stop")
def stop_challenge(req: StopRequest):

    containers = client.containers.list(
        filters={"label": [f"ctf_player={req.player_id}",
                           f"ctf_challenge={req.challenge_id}"]}
    )
    if not containers:
        raise HTTPException(status_code=404, detail={"error":"Container not found"})

    stopped = []
    for c in containers:
        try:

            sub = c.labels.get("ctf_subdomain",None)

            c.stop()
            c.remove()
            stopped.append(c.name)

            # If a dynamic flag was added, remove it after removing the container
            flag_path = Path("/tmp/flags") / f"{c.name}.flag"

            if flag_path.exists():
                flag_path.unlink()

            # Remove nginx config for subdomain and reload
            if sub is not None:
                fqdn = f"{sub}.{BASE_DOMAIN}"
                conf_path = Path(NGINX_CONF_DIR) / f"{fqdn}.conf"
                conf_path.unlink()
                
                nginx = client.containers.get("uscg-nginx")
                output = nginx.exec_run("nginx -s reload")

        #Continue if nginx file isn't found due to stale references or whatever
        except FileNotFoundError:
            pass
        except Exception as e:
            raise HTTPException(status_code=500, detail={"error":str(e)})

    return {"stopped": stopped}

@app.post("/stop_container")
def stop_challenge(req: StopContainerRequest):

    container = client.containers.get(req.container_id)

    if not container:
        raise HTTPException(status_code=404, detail={"error":"Container not found"})

    stopped = []

    try:

        sub = container.labels.get("ctf_subdomain",None)

        container.stop()
        container.remove()
        stopped.append(container.name)

        # Remove nginx config for subdomain and reload
        if sub is not None:
            fqdn = f"{sub}.{BASE_DOMAIN}"
            conf_path = Path(NGINX_CONF_DIR) / f"{fqdn}.conf"
            conf_path.unlink()
            
            nginx = client.containers.get("uscg-nginx")
            output = nginx.exec_run("nginx -s reload")

    #Continue if nginx file isn't found due to stale references or whatever
    except FileNotFoundError:
        pass
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error":str(e)})

    return {"stopped": stopped}

@app.get("/containers")
def list_containers():

    containers = client.containers.list(filters={"label": f"challenge_container=true"})

    output = []

    for c in containers:
        labels = c.labels
        output.append({"player_id":labels.get("ctf_player","0"),
                       "challenge_id":labels.get("ctf_challenge","0"),
                       "started_at":labels.get("started_at","0"),
                       "expires":labels.get("expires","0")})
    
    return output

@app.get("/count")
def count_containers():
    C = client.containers.list(filters={"label": f"challenge_container=true"})
    return {"count":len(C)}
