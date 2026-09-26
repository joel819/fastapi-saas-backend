"""Send a signed test webhook to a running server (demo mode secret by default).

Usage:
  python -m scripts.send_test_webhook                         # cancels bob's subscription
  python -m scripts.send_test_webhook --type invoice.payment_failed --sub sub_seed_0001
  python -m scripts.send_test_webhook --replay                # sends the same event twice
"""
import argparse
import json

import httpx

from app.config import get_settings
from app.services.payments.mock_provider import build_event, sign_payload


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8000/webhooks/stripe")
    p.add_argument("--type", default="customer.subscription.deleted")
    p.add_argument("--sub", default="sub_seed_0003", help="stripe subscription id")
    p.add_argument("--replay", action="store_true", help="send the same event twice")
    args = p.parse_args()

    if args.type.startswith("invoice."):
        obj = {"object": "invoice", "subscription": args.sub}
    else:
        obj = {"id": args.sub, "object": "subscription", "status": "canceled"}
    payload = json.dumps(build_event(args.type, obj)).encode()
    secret = get_settings().effective_webhook_secret

    for attempt in range(2 if args.replay else 1):
        headers = {"Stripe-Signature": sign_payload(payload, secret), "Content-Type": "application/json"}
        r = httpx.post(args.url, content=payload, headers=headers)
        print(f"attempt {attempt + 1}: {r.status_code} {r.text}")


if __name__ == "__main__":
    main()
