"""Offline behavior checks. Run: python -m unittest -v"""
import copy
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import support


class SupportTests(unittest.TestCase):
    def sample(self, key="billing"):
        return next(x for x in support.load_samples() if x["id"] == key)

    def test_all_fixture_paths_and_matching_playground_requests(self):
        for sample in support.load_samples():
            with self.subTest(sample=sample["id"]):
                message = sample["state"]["ticket"]["message"]
                result = support.evaluate(message)
                self.assertIn("DEMO", result["mode"])
                request = support.read_json(f"playground/requests/{sample['id']}.json")
                self.assertEqual(request, support.make_request(message))

    def test_demo_does_not_call_network(self):
        with patch("support.urlopen", side_effect=AssertionError("network call")):
            self.assertEqual(support.evaluate(self.sample()["state"]["ticket"]["message"])["analysis"]["department"], "billing")

    def test_reject_empty_and_overlong_inputs(self):
        for message in ("", "   ", "x" * 4001):
            with self.subTest(message_length=len(message)), self.assertRaises(support.SupportError):
                support.build_state(message)

    def test_no_unlabeled_mock_for_custom_text(self):
        with self.assertRaises(support.SupportError):
            support.evaluate("A custom message that has no fixture")

    def test_ambiguous_and_mixed_go_to_review(self):
        for key in ("ambiguous", "mixed"):
            result = support.evaluate(self.sample(key)["state"]["ticket"]["message"])
            self.assertEqual(result["decision"]["status"], "Human review")

    def test_outage_is_urgent_and_calm(self):
        result = support.evaluate(self.sample("outage")["state"]["ticket"]["message"])
        self.assertEqual(result["decision"]["priority"], "Urgent flag")
        self.assertLess(result["analysis"]["frustration"], 0.5)

    def test_missing_answers_fail_closed(self):
        with self.assertRaises(support.SupportError):
            support.validate_response({"answers": {}})

    def test_invalid_numbers_fail_closed(self):
        for number in (float("nan"), float("inf"), -0.1, 1.1, True, "0.8"):
            raw = copy.deepcopy(self.sample()["demo_response"])
            raw["answers"]["is_urgent"]["noul"] = number
            with self.subTest(number=number), self.assertRaises(support.SupportError):
                support.validate_response(raw)

    def test_wrong_option_and_distribution_fail_closed(self):
        raw = copy.deepcopy(self.sample()["demo_response"])
        raw["answers"]["department"]["choice"] = "unknown"
        with self.assertRaises(support.SupportError):
            support.validate_response(raw)
        raw = copy.deepcopy(self.sample()["demo_response"])
        raw["answers"]["department"]["probabilities"]["billing"] = 0.1
        with self.assertRaises(support.SupportError):
            support.validate_response(raw)

    def test_missing_key_does_not_call_network(self):
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": ""}), patch("support.urlopen") as call:
            with self.assertRaises(support.SupportError):
                support.fetch_live(support.make_request("A test message"))
            call.assert_not_called()

    def test_http_and_network_errors_do_not_echo_secrets(self):
        errors = [HTTPError(support.ENDPOINT, 401, "private-key", None, None), URLError("private-key"), TimeoutError("private-key")]
        for error in errors:
            with patch.dict(os.environ, {"TYPESAFE_API_KEY": "private-key"}), patch("support.urlopen", side_effect=error):
                with self.assertRaises(support.SupportError) as caught:
                    support.fetch_live({})
                self.assertNotIn("private-key", str(caught.exception))

    def test_live_request_header_and_response_handling(self):
        raw = self.sample()["demo_response"]
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-key"}), patch("support.urlopen") as call:
            call.return_value.__enter__.return_value.read.return_value = json.dumps(raw).encode()
            result = support.evaluate(self.sample()["state"]["ticket"]["message"], demo=False)
            request = call.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
            self.assertEqual(request.get_method(), "POST")
            self.assertEqual(call.call_args.kwargs["timeout"], 30)
            self.assertIn("LIVE", result["mode"])

    def test_threshold_boundaries(self):
        result = support.validate_response(self.sample()["demo_response"])
        result.update(department_probability=0.80, needs_clarification=0.34, is_urgent=0.20)
        self.assertEqual(support.decide(result)["status"], "Team recommendation ready")
        result["needs_clarification"] = 0.35
        self.assertEqual(support.decide(result)["status"], "Human review")
        result["needs_clarification"] = 0.0
        result["is_urgent"] = 0.80
        self.assertEqual(support.decide(result)["priority"], "Urgent flag")
        result["is_urgent"] = 0.5
        self.assertEqual(support.decide(result)["priority"], "Urgency review")


if __name__ == "__main__":
    unittest.main()
