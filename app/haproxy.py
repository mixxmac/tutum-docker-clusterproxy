import subprocess
import sys

from cfg import cfg_calc, cfg_save, cfg_to_text
from constants import *
from utils import *


# Global Var
HAPROXY_CURRENT_SUBPROCESS = None
LINKED_SERVICES_ENDPOINTS = None
PREVIOUS_CFG_TEXT = None

logger = logging.getLogger("tutum_haproxy")


def reload_haproxy(haproxy_process):
    if haproxy_process:
        # Reload haproxy
        logger.info("Reloading HAProxy")
        process = subprocess.Popen(HAPROXY_CMD + ["-sf", str(haproxy_process.pid)])
        haproxy_process.wait()
        logger.info("HAProxy has been reloaded\n******************************")
        return process
    else:
        # Launch haproxy
        logger.info("Launching HAProxy\n******************************")
        return subprocess.Popen(HAPROXY_CMD)


def run_haproxy(container_uri=None):
    container = fetch_tutum_obj(container_uri)
    envvars = load_haproxy_envvars(container)
    links = load_links_info(container)
    vhost = parse_vhost(envvars)

    if container_uri:
        global PREVIOUS_CFG_TEXT, HAPROXY_CURRENT_SUBPROCESS
        logger.info("Fetching HAProxy container details through REST Api")
        cfg = cfg_calc(links, vhost)
        cfg_text = cfg_to_text(cfg)
        if PREVIOUS_CFG_TEXT != cfg_text:
            logger.info("HAProxy configuration is updated:\n%s" % cfg_text)
            cfg_save(cfg_text, CONFIG_FILE)
            PREVIOUS_CFG_TEXT = cfg_text
            HAPROXY_CURRENT_SUBPROCESS = reload_haproxy(HAPROXY_CURRENT_SUBPROCESS)
        else:
            logger.info("HAProxy configuration remains unchanged")
    else:
        cfg = cfg_calc(links, vhost)
        cfg_text = cfg_to_text(cfg)
        logger.info("HAProxy configuration:\n%s" % cfg_text)
        cfg_save(cfg_text, CONFIG_FILE)

        logger.info("Launching HAProxy")
        p = subprocess.Popen(HAPROXY_CMD)
        p.wait()


def tutum_event_handler(event):
    global LINKED_SERVICES_ENDPOINTS
    # When service scale up/down or container start/stop/terminate/redeploy, reload the service
    if event.get("state", "") not in ["In progress", "Pending", "Terminating", "Starting", "Scaling", "Stopping"] and \
                    event.get("type", "").lower() in ["container", "service"] and \
                    len(set(LINKED_SERVICES_ENDPOINTS).intersection(set(event.get("parents", [])))) > 0:
        logger.info("Tutum even detected: %s %s is %s" %
                    (event["type"], parse_uuid_from_resource_uri(event.get("resource_uri", "")), event["state"]))
        run_haproxy(TUTUM_CONTAINER_API_URI)

    # Add/remove services linked to haproxy
    if event.get("state", "") == "Success" and TUTUM_SERVICE_API_URI in event.get("parents", []):
        service = fetch_tutum_obj(TUTUM_SERVICE_API_URI)
        service_endpoints = [srv.get("to_service") for srv in service.linked_to_service]
        if LINKED_SERVICES_ENDPOINTS != service_endpoints:
            LINKED_SERVICES_ENDPOINTS = service_endpoints
            logger.info("Service linked to HAProxy container is changed")
            run_haproxy(TUTUM_CONTAINER_API_URI)


def init_tutum_settings():
    global LINKED_SERVICES_ENDPOINTS
    service = fetch_tutum_obj(TUTUM_SERVICE_API_URI)
    LINKED_SERVICES_ENDPOINTS = [srv.get("to_service") for srv in service.linked_to_service]


def main():
    logging.basicConfig(stream=sys.stdout)
    logging.getLogger("tutum_haproxy").setLevel(logging.DEBUG if DEBUG else logging.INFO)

    if TUTUM_SERVICE_API_URI and TUTUM_CONTAINER_API_URI:
        running_mode = "IN_TUTUM_API_ROLE" if TUTUM_AUTH else "IN_TUTUM_NO_API_ROLE"
    else:
        running_mode = "NOT_IN_TUTUM"

    # Tell the user the mode of autoupdate we are using, if any
    if running_mode == "IN_TUTUM_API_ROLE":
        logger.info("HAProxy has access to Tutum API - will reload list of backends in real-time")
    elif running_mode == "IN_TUTUM_NO_API_ROLE":
        logger.warning(
            "HAProxy doesn't have access to Tutum API and it's running in Tutum - you might want to give "
            "an API role to this service for automatic backend reconfiguration")
    else:
        logger.info("HAProxy is not running in Tutum")

    if running_mode == "IN_TUTUM_API_ROLE":
        init_tutum_settings()
        run_haproxy(TUTUM_CONTAINER_API_URI)
        events = tutum.TutumEvents()
        events.on_message(tutum_event_handler)
        events.run_forever()
    else:
        while True:
            run_haproxy()
            time.sleep(1)

if __name__ == "__main__":
    main()
