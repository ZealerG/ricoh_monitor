import sys
import unittest
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import ricoh_email_monitor as monitor


class KeywordMatchingTests(unittest.TestCase):
    def test_include_and_exclude_keywords(self):
        config = {
            "include_keywords_normalized": ["gr iii", "gr iiix", "hdf"],
            "exclude_keywords_normalized": ["ring", "金圈", "配件"],
            "match_mode": "any",
        }

        self.assertTrue(monitor.matches_keywords("官翻品 RICOH GR IIIx HDF", config))
        self.assertFalse(monitor.matches_keywords("GR GOLD RING金圈（GRII专用）-未使用", config))


class ChangeDetectionTests(unittest.TestCase):
    def test_only_new_or_changed_goods_trigger_notification(self):
        previous = {
            "114": {"id": "114", "name": "官翻品 RICOH GR IIIx HDF", "price": "5999.00", "stock": 1},
        }
        current_goods = [
            {"id": 114, "store_name": "官翻品 RICOH GR IIIx HDF", "price": "5999.00", "stock": 1},
            {"id": 115, "store_name": "官翻品 RICOH GR III", "price": "5499.00", "stock": 2},
        ]

        changed = monitor.changed_goods(current_goods, previous)

        self.assertEqual(
            changed,
            [{"id": "115", "name": "官翻品 RICOH GR III", "price": "5499.00", "stock": 2}],
        )

    def test_stock_change_counts_as_change(self):
        previous = {
            "114": {"id": "114", "name": "官翻品 RICOH GR IIIx HDF", "price": "5999.00", "stock": 0},
        }
        current_goods = [
            {"id": 114, "store_name": "官翻品 RICOH GR IIIx HDF", "price": "5999.00", "stock": 3},
        ]

        changed = monitor.changed_goods(current_goods, previous)

        self.assertEqual(
            changed,
            [{"id": "114", "name": "官翻品 RICOH GR IIIx HDF", "price": "5999.00", "stock": 3}],
        )


class EmailFormattingTests(unittest.TestCase):
    def test_build_email_content_accepts_raw_current_goods(self):
        config = {
            "include_keywords": ["WG-1000"],
            "exclude_keywords": [],
            "match_mode": "any",
            "notify_zero_stock": True,
        }
        current_goods = [
            {"id": 132, "store_name": "官翻品 WG-1000 Gray", "price": "1519.00", "stock": 0},
        ]
        changed = [
            {"id": "132", "name": "官翻品 WG-1000 Gray", "price": "1519.00", "stock": 0},
        ]

        subject, body = monitor.build_email_content(current_goods, changed, config)

        self.assertIn("WG-1000", subject)
        self.assertIn("官翻品 WG-1000 Gray", body)
        self.assertIn("库存: 0", body)


class FailureNotificationTests(unittest.TestCase):
    def test_same_failure_is_throttled(self):
        now = 1_700_000_000
        original_time = monitor.time.time
        monitor.time.time = lambda: now
        try:
            state = {
                "last_failure_signature": "network_error|temporary failure",
                "last_failure_notify_ts": now - 60,
            }
            result = {"status": "network_error", "error": "Temporary failure"}

            self.assertFalse(monitor.should_send_failure_email(state, result))
        finally:
            monitor.time.time = original_time

    def test_changed_failure_sends_immediately(self):
        now = 1_700_000_000
        original_time = monitor.time.time
        monitor.time.time = lambda: now
        try:
            state = {
                "last_failure_signature": "network_error|temporary failure",
                "last_failure_notify_ts": now - 60,
            }
            result = {"status": "response_error", "error": "Unexpected HTML"}

            self.assertTrue(monitor.should_send_failure_email(state, result))
        finally:
            monitor.time.time = original_time


class ConfigLoggingTests(unittest.TestCase):
    def test_print_effective_config_masks_primary_email(self):
        config = {
            "cid": 9,
            "include_keywords": ["WG-1000"],
            "exclude_keywords": ["配件"],
            "match_mode": "any",
            "notify_zero_stock": True,
            "poll_interval": 30,
            "state_path": "ricoh_monitor_state.json",
            "receiver_emails": ["abcde@example.com"],
            "smtp_server": "smtp.126.com",
            "smtp_port": 465,
            "smtp_user": "sender@example.com",
            "smtp_password": "secret",
        }

        buffer = StringIO()
        with redirect_stdout(buffer):
            monitor.print_effective_config(config)
        output = buffer.getvalue()

        self.assertIn("PRIMARY_RECEIVER=a***e@example.com", output)
        self.assertIn("KEYWORDS=['WG-1000']", output)
        self.assertIn("SMTP_PASSWORD_SET=True", output)
        self.assertNotIn("abcde@example.com", output)


if __name__ == "__main__":
    unittest.main()
