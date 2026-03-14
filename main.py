import logging

from kube_pod_alerts.config import Settings
from kube_pod_alerts.kube_client import load_api
from kube_pod_alerts.monitor import PodFailureMonitor
from kube_pod_alerts.notifier import TeamsNotifier


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    api = load_api(settings)
    notifier = TeamsNotifier(
        settings.teams_webhook_url,
        webhook_format=settings.webhook_format,
    )
    monitor = PodFailureMonitor(api=api, notifier=notifier, settings=settings)
    monitor.run()


if __name__ == "__main__":
    main()
