import logging

from kubernetes import client, config

from kube_pod_alerts.config import Settings


LOGGER = logging.getLogger(__name__)


def load_api(settings: Settings) -> client.CoreV1Api:
    if settings.kube_use_kubeconfig:
        LOGGER.info("Loading Kubernetes config from kubeconfig")
        config.load_kube_config(
            config_file=settings.kubeconfig_path,
            context=settings.kube_context,
        )
    elif settings.kube_use_cluster:
        LOGGER.info("Loading Kubernetes config from in-cluster service account")
        config.load_incluster_config()
    else:
        LOGGER.info("Loading Kubernetes config from default kubeconfig")
        config.load_kube_config(
            config_file=settings.kubeconfig_path,
            context=settings.kube_context,
        )

    return client.CoreV1Api()
