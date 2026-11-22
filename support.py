"""Shared request, validation and policy logic. Uses Python's standard library."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import socket
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MAX_MESSAGE_LENGTH = 4000
DEPARTMENTS = ("billing", "technical", "sales", "general")


class SupportError(Exception):
    """An error that can safely be displayed without API response contents."""


def read_json(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def load_questions():
    return read_json("questions.json")


def load_samples():
    return read_json("samples.json")


def build_state(message):
    """Use the identical state shape in Python and in the Playground."""
    if not isinstance(message, str) or not message.strip():
        raise SupportError("Enter a customer message before evaluating.")
    message = message.strip()
    if len(message) > MAX_MESSAGE_LENGTH:
        raise SupportError(f"Keep the message to {MAX_MESSAGE_LENGTH} characters or fewer.")
    return {
        "ticket": {"message": message},
        "context": {
            "application": "Fictional online subscription service",
            "routing_policy": "Identify the primary issue. Request review for unclear or multiple issues. Routing never issues a refund or changes an account.",
        },
    }


def make_request(message, model="jev-latest"):
    return {"model": model, "state": build_state(message), "questions": load_questions()}


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a number")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Probability outside range")
    return float(value)


def distribution(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("Unexpected distribution labels")
    result = {key: probability(value[key]) for key in keys}
    if not math.isclose(sum(result.values()), 1.0, abs_tol=0.02):
        raise ValueError("Probabilities must sum to one")
    return result


def validate_response(raw):
    """Fail closed if required answers are missing or malformed."""
    try:
        answers = raw["answers"]
        dep = answers["department"]
        if dep["type"] != "choice" or dep["choice"] not in DEPARTMENTS:
            raise ValueError("Unexpected choice")
        probs = distribution(dep["probabilities"], DEPARTMENTS)
        if probs[dep["choice"]] + 0.000001 < max(probs.values()):
            raise ValueError("Chosen option must have maximum probability")
        dep_conf = probability(dep["confidence"])
        frustration = answers["frustration"]
        if frustration["type"] != "score":
            raise ValueError("Expected Score")
        score = frustration["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("Invalid score")
        if not math.isfinite(score) or not 0 <= score <= 2:
            raise ValueError("Score outside rubric")
        score_probs = distribution(frustration["probabilities"], ("0", "1", "2"))
        if not math.isclose(score, sum(int(k) * v for k, v in score_probs.items()), abs_tol=0.03):
            raise ValueError("Score does not match distribution")
        score_conf = probability(frustration["confidence"])
        values = {}
        for name in ("is_urgent", "needs_clarification"):
            if answers[name]["type"] != "noul":
                raise ValueError("Expected Noul")
            values[name] = probability(answers[name]["noul"])
        return {
            "department": dep["choice"], "department_probability": probs[dep["choice"]],
            "department_probabilities": probs, "department_confidence": dep_conf,
            "frustration": float(score), "frustration_confidence": score_conf,
            "frustration_probabilities": score_probs, **values,
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        raise SupportError("The service returned an unexpected answer. No routing decision was made. Try again or review the ticket manually.") from None


def fetch_live(payload):
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise SupportError("Set TYPESAFE_API_KEY in the terminal, then restart the app, or select Demo mode.")
    request = Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        messages = {401: "The API key was rejected. Check your TypeSafe key.",
                    403: "This account or key cannot access the requested resource.",
                    402: "Check the account's available API credits.",
                    429: "The service is limiting requests. Wait before trying again.",
                    400: "The service rejected the request. Check questions.json and the model name.",
                    422: "The service rejected the request shape. Check questions.json."}
        raise SupportError(messages.get(error.code, f"The service returned HTTP {error.code}. Try again later.")) from None
    except (URLError, TimeoutError, socket.timeout, ConnectionError):
        raise SupportError("Could not reach TypeSafe within the request timeout. Check your connection and try again.") from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise SupportError("The service did not return readable JSON. No routing decision was made.") from None


def demo_response(message):
    """Replay named, invented examples. This is not an offline AI model."""
    for sample in load_samples():
        if sample["state"]["ticket"]["message"] == message.strip():
            return sample["demo_response"]
    raise SupportError("Demo mode only replays the supplied examples. Select an example, or switch to Live Jev for your own message.")


def decide(result):
    """Illustrative policy thresholds. Validate on your data before real use."""
    reasons = []
    if result["needs_clarification"] >= 0.35:
        reasons.append("The ticket may need clarification.")
    if result["department_probability"] < 0.80:
        reasons.append("The team recommendation is below our example 0.80 threshold.")
    if result["department"] == "general":
        reasons.append("General requests receive human review in this course policy.")
    urgent = result["is_urgent"]
    priority = "Urgent flag" if urgent >= 0.80 else "Standard" if urgent <= 0.20 else "Urgency review"
    if 0.20 < urgent < 0.80:
        reasons.append("The urgency signal is in the example review band.")
    status = "Human review" if reasons else "Team recommendation ready"
    # Reply text is authored by us. Jev does not generate this prose.
    if reasons:
        reply = "Thanks for contacting support. Could you describe the main issue, the feature involved, and any deadline? A support agent will review the details."
    else:
        reply = read_json("reply_templates.json")[result["department"]]
    angry = result["frustration_probabilities"]["2"] >= 0.50
    return {"status": status, "priority": priority, "review_reasons": reasons,
            "tone_guidance": "Use an empathetic tone and request agent attention." if angry else "Use a clear, courteous tone.",
            "suggested_reply": reply}


def evaluate(message, demo=True, model="jev-latest"):
    payload = make_request(message, model)
    start = time.perf_counter()
    raw = demo_response(payload["state"]["ticket"]["message"]) if demo else fetch_live(payload)
    result = validate_response(raw)
    return {"mode": "DEMO: invented fixture" if demo else "LIVE: Jev API",
            "model": raw.get("model", model), "elapsed_seconds": round(time.perf_counter() - start, 3),
            "analysis": result, "decision": decide(result), "raw_response": raw}


def main():
    parser = argparse.ArgumentParser(description="Evaluate a support ticket with Jev or a fixed demonstration.")
    parser.add_argument("--sample", default="billing", help="Example ID from samples.json")
    parser.add_argument("--message", help="Your own customer message; requires --live")
    parser.add_argument("--live", action="store_true", help="Send the ticket to TypeSafe")
    parser.add_argument("--model", default=os.environ.get("TYPESAFE_MODEL", "jev-latest"))
    parser.add_argument("--request-only", action="store_true", help="Print a request without calling the service")
    args = parser.parse_args()
    try:
        samples = {sample["id"]: sample for sample in load_samples()}
        if args.message is None and args.sample not in samples:
            raise SupportError("Unknown example ID. Choose: " + ", ".join(samples))
        message = args.message if args.message is not None else samples[args.sample]["state"]["ticket"]["message"]
        output = make_request(message, args.model) if args.request_only else evaluate(message, not args.live, args.model)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0
    except SupportError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
