from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from tracker.models import ScrapeJob
from tracker.queue_monitoring import queue_metrics


class QueueMonitoringTests(TestCase):
    def _job(self, url, status, **kwargs):
        defaults = {
            "query": "telephone",
            "model_name": "model",
            "status": status,
            "attempts": 1,
            "available_at": timezone.now(),
        }
        defaults.update(kwargs)
        return ScrapeJob.objects.create(url=url, **defaults)

    def test_metrics_report_backlog_rates_and_domains(self):
        self._job("https://good.example/p/1", ScrapeJob.STATUS_SUCCESS, duration_ms=100, fetch_status="success")
        self._job("https://good.example/p/2", ScrapeJob.STATUS_SUCCESS, duration_ms=300, fetch_status="success", from_cache=True)
        self._job("https://bad.example/p/1", ScrapeJob.STATUS_FAILED, duration_ms=200, fetch_status="anti_bot")
        self._job("https://bad.example/p/2", ScrapeJob.STATUS_RETRY, fetch_status="network_failure")
        self._job("https://pending.example/p/1", ScrapeJob.STATUS_PENDING)

        metrics = queue_metrics()

        self.assertEqual(metrics["total"], 5)
        self.assertEqual(metrics["backlog"], 2)
        self.assertEqual(metrics["status"][ScrapeJob.STATUS_SUCCESS], 2)
        self.assertEqual(metrics["status"][ScrapeJob.STATUS_FAILED], 1)
        self.assertEqual(metrics["success_rate"], 0.6667)
        self.assertEqual(metrics["avg_duration_ms"], 200.0)
        self.assertEqual(metrics["cache_hit_rate"], 0.2)
        self.assertEqual(metrics["anti_bot_rate"], 0.2)
        self.assertEqual(metrics["domains"][0]["domain"], "bad.example")

    def test_empty_queue_is_safe(self):
        metrics = queue_metrics()
        self.assertEqual(metrics["total"], 0)
        self.assertEqual(metrics["backlog"], 0)
        self.assertEqual(metrics["success_rate"], 0.0)
        self.assertEqual(metrics["domains"], [])

    def test_management_command_outputs_summary(self):
        self._job("https://merchant.example/p/1", ScrapeJob.STATUS_PENDING)
        out = StringIO()
        call_command("scrape_queue_status", stdout=out)
        text = out.getvalue()
        self.assertIn("Bendango Scrape Queue", text)
        self.assertIn("Backlog", text)
        self.assertIn("pending=1", text)
