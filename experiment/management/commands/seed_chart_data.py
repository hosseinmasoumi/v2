from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from experiment.models import PaymentCoefficient, QualityCommission
from project.models import Project


class Command(BaseCommand):
    help = "Seed varied fake data for payment coefficient and quality commission charts."

    LAYERS = ["EMBANKMENT", "SUBBASE", "BASE", "ASPHALT"]

    PAYMENT_BASE = {
        "EMBANKMENT": Decimal("0.74"),
        "SUBBASE": Decimal("0.82"),
        "BASE": Decimal("0.91"),
        "ASPHALT": Decimal("0.88"),
    }

    COMMISSION_BASE = {
        "EMBANKMENT": Decimal("58.00"),
        "SUBBASE": Decimal("66.00"),
        "BASE": Decimal("73.00"),
        "ASPHALT": Decimal("81.00"),
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing payment coefficients and quality commissions before seeding.",
        )
        parser.add_argument(
            "--projects",
            type=int,
            default=8,
            help="Maximum number of main projects to seed. Default: 8",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            PaymentCoefficient.objects.all().delete()
            QualityCommission.objects.all().delete()
            self.stdout.write(self.style.WARNING("Existing chart data was cleared."))

        projects = list(
            Project.objects.filter(parent_project__isnull=True)
            .order_by("id")[: options["projects"]]
        )

        if not projects:
            self.stdout.write(
                self.style.ERROR(
                    "No main projects found. Create projects first or run seed_projects, then run this command."
                )
            )
            return

        today = timezone.now().date()
        payment_created = 0
        commission_created = 0

        for project_index, project in enumerate(projects):
            start_km = project.start_kilometer or Decimal("0.000")

            for layer_index, layer in enumerate(self.LAYERS):
                for version in range(3):
                    calculation_date = today - timezone.timedelta(days=(2 - version) * 12)
                    segment_start = start_km + Decimal(str(version + layer_index))
                    segment_end = segment_start + Decimal("0.750")

                    payment_value = self._payment_value(project_index, layer_index, version, layer)
                    commission_value = self._commission_value(project_index, layer_index, version, layer)

                    PaymentCoefficient.objects.create(
                        project=project,
                        layer=layer,
                        coefficient=payment_value,
                        start_kilometer=segment_start,
                        end_kilometer=segment_end,
                        calculation_date=calculation_date,
                    )
                    payment_created += 1

                    QualityCommission.objects.create(
                        project=project,
                        layer=layer,
                        coefficient=commission_value,
                        start_kilometer=segment_start,
                        end_kilometer=segment_end,
                        calculation_date=calculation_date,
                        description="داده تستی برای نمودارهای داشبورد",
                    )
                    commission_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {payment_created} payment coefficients and {commission_created} quality commissions for {len(projects)} projects."
            )
        )

    def _payment_value(self, project_index, layer_index, version, layer):
        wave = Decimal(str(((project_index * 7 + layer_index * 5 + version * 3) % 17) - 8))
        trend = Decimal(str(project_index % 4)) * Decimal("0.035")
        version_shift = Decimal(str(version - 1)) * Decimal("0.025")
        value = self.PAYMENT_BASE[layer] + (wave * Decimal("0.018")) + trend + version_shift
        return self._clamp(value, Decimal("0.45"), Decimal("1.18"))

    def _commission_value(self, project_index, layer_index, version, layer):
        wave = Decimal(str(((project_index * 11 + layer_index * 6 + version * 4) % 23) - 11))
        trend = Decimal(str(project_index % 5)) * Decimal("3.10")
        version_shift = Decimal(str(version - 1)) * Decimal("1.70")
        value = self.COMMISSION_BASE[layer] + (wave * Decimal("1.35")) + trend + version_shift
        return self._clamp(value, Decimal("25.00"), Decimal("98.00"))

    def _clamp(self, value, minimum, maximum):
        value = max(minimum, min(maximum, value))
        return value.quantize(Decimal("0.01"))
