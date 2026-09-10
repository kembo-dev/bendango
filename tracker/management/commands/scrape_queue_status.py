import json

from django.core.management.base import BaseCommand

from tracker.queue_monitoring import queue_metrics


class Command(BaseCommand):
    help = "Show Bendango scrape queue health and per-domain collection metrics."

    def add_arguments(self, parser):
        parser.add_argument("--domains", type=int, default=10, help="Number of problematic domains to display.")
        parser.add_argument("--json", action="store_true", dest="as_json", help="Output metrics as JSON.")

    def handle(self, *args, **options):
        metrics = queue_metrics(limit_domains=max(1, options["domains"]))
        if options["as_json"]:
            self.stdout.write(json.dumps(metrics, ensure_ascii=False, indent=2))
            return

        status = metrics["status"]
        self.stdout.write(self.style.SUCCESS("Bendango Scrape Queue"))
        self.stdout.write(f"Total jobs       : {metrics['total']}")
        self.stdout.write(f"Backlog          : {metrics['backlog']}")
        self.stdout.write(
            "Statuses         : "
            f"pending={status.get('pending', 0)} | running={status.get('running', 0)} | "
            f"retry={status.get('retry', 0)} | failed={status.get('failed', 0)} | success={status.get('success', 0)}"
        )
        self.stdout.write(f"Success rate     : {metrics['success_rate'] * 100:.1f}%")
        self.stdout.write(f"Avg duration     : {metrics['avg_duration_ms']:.1f} ms")
        self.stdout.write(f"Cache hit rate   : {metrics['cache_hit_rate'] * 100:.1f}%")
        self.stdout.write(f"Anti-bot rate    : {metrics['anti_bot_rate'] * 100:.1f}%")

        if metrics["failure_reasons"]:
            self.stdout.write("Failure reasons  : " + ", ".join(f"{name}={count}" for name, count in metrics["failure_reasons"].items()))

        if metrics["domains"]:
            self.stdout.write("")
            self.stdout.write("Problematic domains:")
            for row in metrics["domains"]:
                self.stdout.write(
                    f"- {row['domain']}: total={row['total']} success={row['success']} failed={row['failed']} "
                    f"retry={row['retry']} anti_bot={row['anti_bot']} success_rate={row['success_rate'] * 100:.1f}% "
                    f"avg={row['avg_duration_ms']}ms"
                )
