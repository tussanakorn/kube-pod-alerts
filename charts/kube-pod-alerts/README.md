# kube-pod-alerts Helm Chart

`kube-pod-alerts` watches Kubernetes pods and sends Microsoft Teams alerts when
pods fail or containers enter unhealthy waiting states.

## What It Detects

- Pod phase `Failed`
- Container waiting reason `CrashLoopBackOff`
- Container waiting reason `ImagePullBackOff`

## Default Image

```yaml
image:
  repository: tussanakorndev/kube-pod-alerts
  tag: "1.0.5"
```

## Install

```bash
helm repo add kube-pod-alerts https://tussanakorn.github.io/kube-pod-alerts
helm repo update
helm upgrade --install kube-pod-alerts kube-pod-alerts/kube-pod-alerts -n monitoring --create-namespace
```

## Required Configuration

Set the Microsoft Teams or Power Automate webhook URL:

```yaml
secretEnv:
  TEAMS_WEBHOOK_URL: "https://example.webhook"
```

## Example Values

```yaml
image:
  repository: tussanakorndev/kube-pod-alerts
  tag: "1.0.5"

env:
  WEBHOOK_FORMAT: power_automate
  KUBE_USE_CLUSTER: "true"
  RECOVERY_ALERT: "true"
  FLOOD_EXPIRE: "60000"
  KUBE_NAMESPACES_ONLY: '["poa"]'

secretEnv:
  TEAMS_WEBHOOK_URL: "https://example.webhook"
```

## Notes

- Recovery alerts can be disabled with `RECOVERY_ALERT=false`
- Pods can be ignored with `kube-teams/ignore-pod` or `kube-slack/ignore-pod`
