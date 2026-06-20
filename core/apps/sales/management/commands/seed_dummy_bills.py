import random
import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import tenant_context

from apps.accounts.models import User
from apps.products.models import ProductVariant
from apps.sales.models import Bill, BillItem, Customer
from apps.shops.models import Shop


DUMMY_NOTE_TAG = "DUMMY_OVERVIEW_TEST"


class Command(BaseCommand):
    help = (
        "Seed dummy paid Bills (and BillItems) spread across multiple years "
        "so the manager overview revenue trend / filters can be tested."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--shop-id",
            type=int,
            help="Shop ID where dummy bills will be created. Defaults to the first shop.",
        )
        parser.add_argument(
            "--years",
            type=int,
            nargs="+",
            default=[2024, 2025, 2026],
            help="Years to spread bills across. Default: 2024 2025 2026",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Total number of bills to create across all years. Default: 20",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="Random seed for repeatable data. Default: 42",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete previously seeded dummy bills for the selected shop before creating new ones.",
        )

    def handle(self, *args, **options):
        random.seed(options["seed"])

        shop = self._resolve_shop(options.get("shop_id"))

        with tenant_context(shop):
            self._seed_tenant_data(options, shop)

    @transaction.atomic
    def _seed_tenant_data(self, options, shop):
        years = options["years"]
        count = options["count"]

        if count <= 0:
            raise CommandError("--count must be greater than 0")
        if not years:
            raise CommandError("--years must contain at least one year")

        if options["clear"]:
            self._clear_previous_dummy_data(shop)

        creator = self._resolve_creator()
        variants = list(ProductVariant.objects.all()[:200])
        customer = self._get_or_create_customer()

        created_bills = 0
        revenue_by_year = {year: Decimal("0.00") for year in years}

        for i in range(count):
            year = years[i % len(years)]
            created_dt = self._random_datetime_in_year(year)

            bill = self._create_bill(creator, customer, variants, created_dt)
            revenue_by_year[year] += bill.total_amount
            created_bills += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created_bills} dummy bills for shop_id={shop.id}."
        ))
        for year in sorted(revenue_by_year):
            self.stdout.write(
                f"  {year}: revenue {revenue_by_year[year]}"
            )

    def _create_bill(self, creator, customer, variants, created_dt):
        chosen_variants = []
        if variants:
            chosen_variants = random.sample(
                variants, k=min(len(variants), random.randint(1, 4))
            )

        subtotal = Decimal("0.00")
        item_specs = []
        if chosen_variants:
            for variant in chosen_variants:
                quantity = random.randint(1, 5)
                price = variant.price or Decimal(str(random.randint(100, 3000)))
                line_total = (price * quantity).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                subtotal += line_total
                item_specs.append((variant, quantity, price, line_total))
        else:
            subtotal = Decimal(str(random.randint(200, 8000)))

        discount_percent = Decimal(str(random.choice([0, 0, 0, 5, 10])))
        discount_value = (subtotal * discount_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_amount = (subtotal - discount_value).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        bill = Bill.objects.create(
            created_by=creator,
            customer=customer,
            bill_number=f"BILL-{created_dt.strftime('%Y%m%d')}-DUMMY-{uuid.uuid4().hex[:6].upper()}",
            subtotal=subtotal,
            discount_percent=discount_percent,
            custom_amount=Decimal("0.00"),
            total_amount=total_amount,
            paid_amount=total_amount,
            payment_method=random.choice(Bill.PaymentMethod.values),
            payment_status=Bill.PaymentStatus.PAID,
            notes=DUMMY_NOTE_TAG,
            is_active=True,
        )

        for variant, quantity, price, line_total in item_specs:
            BillItem.objects.create(
                bill=bill,
                product_variant=variant,
                quantity=quantity,
                price=price,
                discount_percent=Decimal("0.00"),
                custom_amount=Decimal("0.00"),
                total_price=line_total,
            )

        Bill.objects.filter(id=bill.id).update(created_at=created_dt)
        bill.refresh_from_db()
        return bill

    def _random_datetime_in_year(self, year):
        start = date(year, 1, 1)
        if year == timezone.localdate().year:
            end = timezone.localdate()
        else:
            end = date(year, 12, 31)

        span_days = (end - start).days
        random_day = start + timedelta(days=random.randint(0, max(span_days, 0)))
        naive = datetime.combine(
            random_day,
            time(hour=random.randint(8, 21), minute=random.randint(0, 59)),
        )
        return timezone.make_aware(naive, timezone.get_current_timezone())

    def _resolve_shop(self, shop_id):
        if shop_id:
            try:
                return Shop.objects.get(id=shop_id)
            except Shop.DoesNotExist as exc:
                raise CommandError(f"Shop with id={shop_id} does not exist") from exc

        shop = Shop.objects.exclude(schema_name="public").order_by("id").first()
        if not shop:
            raise CommandError("No Shop found. Create a shop first, then re-run this command.")
        return shop

    def _resolve_creator(self):
        creator = (
            User.objects.filter(role=User.Role.EMPLOYEE).order_by("id").first()
            or User.objects.order_by("id").first()
        )
        if not creator:
            raise CommandError(
                "No User found in this shop. Create a manager/employee first."
            )
        return creator

    def _get_or_create_customer(self):
        customer, _ = Customer.objects.get_or_create(
            phone="9000000000",
            defaults={"name": "Dummy Overview Customer", "is_active": True},
        )
        return customer

    def _clear_previous_dummy_data(self, shop):
        bills = Bill.objects.filter(notes=DUMMY_NOTE_TAG)
        BillItem.objects.filter(bill__in=bills).delete()
        deleted, _ = bills.delete()
        self.stdout.write(
            self.style.WARNING(
                f"Cleared previously seeded dummy bills for shop_id={shop.id}: {deleted} rows"
            )
        )
