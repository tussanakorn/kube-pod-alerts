import logging
import threading
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from kubernetes import watch
from kubernetes.client import AppsV1Api, CoreV1Api, V1ContainerStatus, V1Pod

from kube_pod_alerts.config import Settings
from kube_pod_alerts.flood_filter import FloodFilter
from kube_pod_alerts.notifier import TeamsNotifier


LOGGER = logging.getLogger(__name__)
IGNORED_WAITING_REASONS = {"ContainerCreating", "PodInitializing"}
FAILURE_WAITING_REASONS = {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"}
CANONICAL_WAITING_REASONS = {
    "CrashLoopBackOff": "CrashLoopBackOff",
    "ImagePullBackOff": "ImagePullBackOff",
    "ErrImagePull": "ImagePullBackOff",
}
IGNORE_ANNOTATIONS = {"kube-teams/ignore-pod", "kube-slack/ignore-pod"}


@dataclass(frozen=True)
class FailureEvent:
    key: str
    state_key: str
    reason: str
    title: str
    text: str
    facts: dict[str, str]


class PodFailureMonitor:
    def __init__(self, api: CoreV1Api, notifier: TeamsNotifier, settings: Settings) -> None:
        self.api = api
        self.apps_api = AppsV1Api(api.api_client)
        self.notifier = notifier
        self.settings = settings
        self.flood_filter = FloodFilter(settings.flood_expire_ms)
        self.active_failures: dict[str, FailureEvent] = {}
        self._lock = threading.Lock()
        self._replicaset_owner_cache: dict[tuple[str, str], str] = {}

    def run(self) -> None:
        namespaces = self.settings.namespaces_only
        if namespaces:
            threads = []
            for namespace in namespaces:
                thread = threading.Thread(
                    target=self._watch_namespace,
                    args=(namespace,),
                    daemon=True,
                    name=f"watch-{namespace}",
                )
                thread.start()
                threads.append(thread)
                LOGGER.info("Watching namespace: %s", namespace)
            for thread in threads:
                thread.join()
            return

        LOGGER.info("Watching pods in all namespaces")
        self._watch_namespace(None)

    def _watch_namespace(self, namespace: Optional[str]) -> None:
        while True:
            watcher = watch.Watch()
            try:
                stream = self._build_stream(watcher, namespace)
                for event in stream:
                    pod = event["object"]
                    if not isinstance(pod, V1Pod):
                        continue
                    self._handle_pod_event(pod)
            except Exception:
                target = namespace or "all namespaces"
                LOGGER.exception("Pod watch failed for %s; reconnecting shortly", target)
                time.sleep(5)
            finally:
                watcher.stop()

    def _build_stream(self, watcher: watch.Watch, namespace: Optional[str]):
        if namespace:
            return watcher.stream(
                self.api.list_namespaced_pod,
                namespace=namespace,
                timeout_seconds=self.settings.watch_timeout_seconds,
            )
        return watcher.stream(
            self.api.list_pod_for_all_namespaces,
            timeout_seconds=self.settings.watch_timeout_seconds,
        )

    def _handle_pod_event(self, pod: V1Pod) -> None:
        pod_prefix = f"{self._pod_identity(pod)}:"

        if self._is_ignored(pod):
            self._clear_active_failures(pod_prefix)
            return

        if pod.status is None:
            self._clear_active_failures(pod_prefix)
            return

        failures = list(self._detect_failures(pod))
        current_keys = {failure.state_key for failure in failures}

        with self._lock:
            existing_keys = [key for key in self.active_failures if key.startswith(pod_prefix)]

            for failure in failures:
                self.active_failures[failure.state_key] = failure
                self._send_failure(failure)

            if self.settings.recovery_alert:
                for state_key in existing_keys:
                    if state_key not in current_keys:
                        recovered = self.active_failures.pop(state_key)
                        self._send_recovery(recovered, pod)
            else:
                for state_key in existing_keys:
                    if state_key not in current_keys:
                        self.active_failures.pop(state_key, None)

    def _clear_active_failures(self, pod_prefix: str) -> None:
        with self._lock:
            keys_to_clear = [key for key in self.active_failures if key.startswith(pod_prefix)]
            for state_key in keys_to_clear:
                self.active_failures.pop(state_key, None)

    def _detect_failures(self, pod: V1Pod) -> Iterable[FailureEvent]:
        namespace = pod.metadata.namespace or "default"
        pod_name = pod.metadata.name or "unknown"
        identity = self._pod_identity(pod)
        phase = (pod.status.phase or "").strip()

        if phase == "Failed":
            yield FailureEvent(
                key=f"{identity}:Failed",
                state_key=f"{identity}:Failed",
                reason="Failed",
                title=f"Pod failed: {namespace}/{pod_name}",
                text=pod.status.message or pod.status.reason or "Pod entered Failed phase.",
                facts={
                    "Namespace": namespace,
                    "Pod": pod_name,
                    "Reason": pod.status.reason or "Failed",
                    "Message": pod.status.message or "",
                },
            )

        for container_status in self._container_statuses(pod):
            waiting_state = getattr(container_status.state, "waiting", None)
            if waiting_state is None:
                continue

            reason = (waiting_state.reason or "").strip()
            if reason in IGNORED_WAITING_REASONS or reason not in FAILURE_WAITING_REASONS:
                continue

            canonical_reason = CANONICAL_WAITING_REASONS[reason]
            message = waiting_state.message or f"Container entered {reason}."
            yield FailureEvent(
                key=f"{identity}:{canonical_reason}",
                state_key=f"{identity}:{canonical_reason}",
                reason=canonical_reason,
                title=f"Pod issue: {namespace}/{pod_name}",
                text=message,
                facts={
                    "Namespace": namespace,
                    "Pod": pod_name,
                    "Container": container_status.name,
                    "Reason": reason,
                    "Restarts": container_status.restart_count,
                },
            )

    def _send_failure(self, failure: FailureEvent) -> None:
        if not self.flood_filter.accept(failure.key):
            return

        self.notifier.send(
            title=failure.title,
            text=failure.text,
            summary=failure.reason,
            color="E81123",
            facts=failure.facts,
        )

    def _send_recovery(self, failure: FailureEvent, pod: V1Pod) -> None:
        recovery_key = f"{failure.key}:recovery"
        if not self.flood_filter.accept(recovery_key):
            return

        namespace = pod.metadata.namespace or "default"
        pod_name = pod.metadata.name or "unknown"
        self.notifier.send(
            title=f"Pod recovered: {namespace}/{pod_name}",
            text=f"Recovered from {failure.reason}.",
            summary=f"{failure.reason} recovered",
            color="107C10",
            facts={
                "Namespace": namespace,
                "Pod": pod_name,
                "Recovered issue": failure.reason,
                "Phase": pod.status.phase or "Unknown",
            },
        )

    @staticmethod
    def _container_statuses(pod: V1Pod) -> Iterable[V1ContainerStatus]:
        statuses = pod.status.container_statuses or []
        init_statuses = pod.status.init_container_statuses or []
        return [*statuses, *init_statuses]

    def _pod_identity(self, pod: V1Pod) -> str:
        namespace = pod.metadata.namespace or "default"
        pod_name = pod.metadata.name or "unknown"
        pod_uid = pod.metadata.uid or "unknown"
        owners = pod.metadata.owner_references or []
        if owners:
            owner = owners[0]
            if owner.kind == "ReplicaSet":
                return self._replicaset_identity(namespace, owner.name)
            return f"{namespace}/{owner.name}"
        return f"{namespace}/{pod_name}:{pod_uid}"

    def _replicaset_identity(self, namespace: str, replicaset_name: str) -> str:
        cache_key = (namespace, replicaset_name)
        cached_identity = self._replicaset_owner_cache.get(cache_key)
        if cached_identity is not None:
            return cached_identity

        identity = f"{namespace}/{replicaset_name}"
        try:
            replicaset = self.apps_api.read_namespaced_replica_set(
                name=replicaset_name,
                namespace=namespace,
            )
            owners = replicaset.metadata.owner_references or []
            if owners:
                identity = f"{namespace}/{owners[0].name}"
        except Exception:
            LOGGER.debug(
                "Falling back to ReplicaSet identity for %s/%s",
                namespace,
                replicaset_name,
                exc_info=True,
            )

        self._replicaset_owner_cache[cache_key] = identity
        return identity

    @staticmethod
    def _is_ignored(pod: V1Pod) -> bool:
        annotations = pod.metadata.annotations or {}
        for name in IGNORE_ANNOTATIONS:
            value = annotations.get(name)
            if value and value.strip().lower() not in {"false", "0", "no"}:
                return True
        return False
