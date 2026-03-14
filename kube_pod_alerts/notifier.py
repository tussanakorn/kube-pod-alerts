import logging
from typing import Any

import requests


LOGGER = logging.getLogger(__name__)


class TeamsNotifier:
    def __init__(self, webhook_url: str, webhook_format: str = "power_automate") -> None:
        self.webhook_url = webhook_url
        self.webhook_format = webhook_format

    def send(self, *, title: str, text: str, summary: str, color: str, facts: dict[str, Any]) -> None:
        payload = self._build_payload(
            title=title,
            text=text,
            summary=summary,
            color=color,
            facts=facts,
        )

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            LOGGER.info("Teams notification sent: %s", summary)
        except requests.RequestException:
            LOGGER.exception("Failed to send Teams notification: %s", summary)

    def _build_payload(
        self,
        *,
        title: str,
        text: str,
        summary: str,
        color: str,
        facts: dict[str, Any],
    ) -> dict[str, Any]:
        clean_facts = {
            key: str(value)
            for key, value in facts.items()
            if value not in (None, "")
        }

        if self.webhook_format == "teams_message_card":
            return {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "themeColor": color,
                "summary": summary,
                "title": title,
                "text": text,
                "sections": [
                    {
                        "facts": [
                            {"name": key, "value": value}
                            for key, value in clean_facts.items()
                        ]
                    }
                ],
            }

        return {
            "title": title,
            "text": text,
            "summary": summary,
            "reason": summary,
            "color": color,
            "facts": clean_facts,
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": self._build_adaptive_card(
                        title=title,
                        text=text,
                        summary=summary,
                        color=color,
                        facts=clean_facts,
                    ),
                }
            ],
        }

    def _build_adaptive_card(
        self,
        *,
        title: str,
        text: str,
        summary: str,
        color: str,
        facts: dict[str, str],
    ) -> dict[str, Any]:
        fact_set = [
            {"title": f"{key}:", "value": value}
            for key, value in facts.items()
        ]

        severity = "Attention" if color.upper() == "E81123" else "Good"
        status_icon = "🚨" if color.upper() == "E81123" else "✅"
        namespace_value = facts.get("Namespace", "unknown")
        pod_value = facts.get("Pod", "unknown")
        resource_line = f"`{namespace_value}` / `{pod_value}`"

        body: list[dict[str, Any]] = [
            {
                "type": "Container",
                "style": "emphasis",
                "bleed": True,
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"{status_icon} {title}",
                        "weight": "Bolder",
                        "size": "Large",
                        "wrap": True,
                    },
                    {
                        "type": "TextBlock",
                        "text": resource_line,
                        "isSubtle": True,
                        "spacing": "Small",
                        "wrap": True,
                        "fontType": "Monospace",
                    },
                    {
                        "type": "TextBlock",
                        "text": summary,
                        "color": severity,
                        "weight": "Bolder",
                        "spacing": "Small",
                        "wrap": True,
                    }
                ],
            },
            {
                "type": "TextBlock",
                "text": text,
                "wrap": True,
                "spacing": "Medium",
            },
            {
                "type": "TextBlock",
                "text": "Cluster Details",
                "weight": "Bolder",
                "spacing": "Large",
            },
        ]

        if fact_set:
            body.append(
                {
                    "type": "FactSet",
                    "facts": fact_set,
                    "spacing": "Small",
                }
            )

        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": body,
        }
