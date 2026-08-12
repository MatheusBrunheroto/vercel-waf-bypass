H_TOKEN = "X-Vercel-Challenge-Token"
H_ID = "X-Vercel-Id"
H_MITIGATED = "X-Vercel-Mitigated"


def _headers_lower(response):
    try:
        return {k.lower(): v for k, v in response.headers.items()}
    except Exception:
        return {}


def is_challenge(response):
    h = _headers_lower(response)
    return h.get(H_MITIGATED.lower()) == "challenge" and H_TOKEN.lower() in h


def challenge_headers(response):
    out = {}
    for key in (H_TOKEN, H_ID, H_MITIGATED):
        value = response.headers.get(key)
        if value is not None:
            out[key] = value
    return out
