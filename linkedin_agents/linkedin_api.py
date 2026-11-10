"""Client LinkedIn (API officielle UGC Posts) — avec mode simulation intégré.

Variables d'environnement pour la publication réelle :
    LINKEDIN_ACCESS_TOKEN   token OAuth avec le scope w_member_social
    LINKEDIN_AUTHOR_URN     ex. urn:li:person:abcdef
    LINKEDIN_API_VERSION    optionnel, défaut 202409
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_ROOT = "https://api.linkedin.com/rest/posts"


class LinkedInError(RuntimeError):
    pass


def author_urn() -> str | None:
    return os.environ.get("LINKEDIN_AUTHOR_URN")


def access_token() -> str | None:
    return os.environ.get("LINKEDIN_ACCESS_TOKEN")


def is_configured() -> bool:
    return bool(author_urn() and access_token())


def build_payload(text: str, author: str, visibility: str = "PUBLIC") -> dict:
    return {
        "author": author,
        "commentary": text,
        "visibility": visibility,
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }


def publish(text: str, author: str | None = None, token: str | None = None,
            timeout: int = 20) -> dict:
    """Publie réellement un post. Lève LinkedInError en cas de problème."""
    author = author or author_urn()
    token = token or access_token()
    if not author or not token:
        raise LinkedInError("LINKEDIN_AUTHOR_URN / LINKEDIN_ACCESS_TOKEN manquants")

    payload = json.dumps(build_payload(text, author)).encode("utf-8")
    request = urllib.request.Request(API_ROOT, data=payload, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": os.environ.get("LINKEDIN_API_VERSION", "202409"),
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "status": response.status,
                "post_urn": response.headers.get("x-restli-id", ""),
            }
    except urllib.error.HTTPError as exc:
        raise LinkedInError(f"HTTP {exc.code}: {exc.read().decode()[:300]}") from exc
    except urllib.error.URLError as exc:
        raise LinkedInError(f"réseau : {exc.reason}") from exc


def simulate(text: str) -> dict:
    """Simulation : renvoie un identifiant factice et la longueur du post."""
    return {"status": 200, "post_urn": f"urn:li:share:simule-{abs(hash(text)) % 10**10}",
            "simulated": True}
