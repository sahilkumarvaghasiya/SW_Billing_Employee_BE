import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.shops.models import Shop
from apps.products.models import Product, ProductVariant, Size, Color, ItemType
from apps.vendors.models import Vendor, StockEntry


DUMMY_TAG = "DUMMY_FILTER_TEST"


class Command(BaseCommand):
    help = (
        "Seed ProductVariant dummy data for UI/API filter testing "
        "(gender, price range, date, size, search)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--shop-id",
            type=int,
            help="Shop ID where dummy data will be created. Defaults to the first shop.",
        )
        parser.add_argument(
            "--variants-per-gender",
            type=int,
            default=8,
            help="How many variants to create for each gender. Default: 8",
        )
        parser.add_argument(
            "--days-span",
            type=int,
            default=60,
            help="Spread created_at over the last N days. Default: 60",
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
            help="Delete previous dummy records created by this command for the selected shop.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(options["seed"])

        shop = self._resolve_shop(options.get("shop_id"))
        variants_per_gender = options["variants_per_gender"]
        days_span = options["days_span"]

        if variants_per_gender <= 0:
            raise CommandError("--variants-per-gender must be greater than 0")
        if days_span < 0:
            raise CommandError("--days-span cannot be negative")

        if options["clear"]:
            self._clear_previous_dummy_data(shop)

        sizes = self._get_or_create_sizes(shop)
        colors = self._get_or_create_colors(shop)
        item_types = self._get_or_create_item_types(shop)
        stock_entries = self._get_or_create_stock_entries(shop)

        keyword_pool = [
            "alpha",
            "beta",
            "cotton",
            "denim",
            "premium",
            "summer",
            "formal",
            "casual",
        ]

        created_products = 0
        created_variants = 0
        now = timezone.now()

        for gender in Product.GenderChoices.values:
            for idx in range(1, variants_per_gender + 1):
                keyword = random.choice(keyword_pool)
                item_type = random.choice(item_types)
                company_name = f"{DUMMY_TAG} {keyword} textiles {gender}"
                product_name = f"{DUMMY_TAG} {gender} product {idx} {keyword}"

                product = Product.objects.create(
                    shop=shop,
                    name=product_name,
                    company_name=company_name,
                    gender=gender,
                    item_type=item_type,
                    description=f"Seeded product for {gender} filter testing",
                    is_active=True,
                )
                created_products += 1

                base_price = Decimal(str(random.randint(50, 7000)))
                discount_amount = Decimal(str(random.choice([0, 25, 50, 75, 100])))

                variant = ProductVariant.objects.create(
                    product=product,
                    stock_entry=random.choice(stock_entries),
                    qr_code_number=f"{DUMMY_TAG}-{shop.id}-{gender}-{idx}",
                    size=random.choice(sizes),
                    color=random.choice(colors),
                    price=base_price,
                    discount_percent=random.choice([0, 5, 10, 15, 20]),
                    discount_amount=discount_amount,
                    quantity=random.randint(5, 250),
                    low_stock_threshold=random.choice([10, 20, 30]),
                    is_active=True,
                )

                if days_span > 0:
                    age_days = random.randint(0, days_span)
                    created_at = now - timedelta(days=age_days)
                    ProductVariant.objects.filter(id=variant.id).update(created_at=created_at)
                    Product.objects.filter(id=product.id).update(created_at=created_at)

                created_variants += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created_products} products and {created_variants} variants for shop_id={shop.id}."
        ))
        self.stdout.write(
            "Try search terms like: alpha, denim, premium, casual, cotton"
        )

    def _resolve_shop(self, shop_id):
        if shop_id:
            try:
                return Shop.objects.get(id=shop_id)
            except Shop.DoesNotExist as exc:
                raise CommandError(f"Shop with id={shop_id} does not exist") from exc

        shop = Shop.objects.order_by("id").first()
        if not shop:
            raise CommandError("No Shop found. Create a shop first, then re-run this command.")
        return shop

    def _clear_previous_dummy_data(self, shop):
        products = Product.objects.filter(shop=shop, name__icontains=DUMMY_TAG)
        variants_deleted, _ = ProductVariant.objects.filter(product__in=products).delete()
        products_deleted, _ = products.delete()
        self.stdout.write(
            self.style.WARNING(
                f"Cleared previous dummy data for shop_id={shop.id}: "
                f"{products_deleted} products, {variants_deleted} variants"
            )
        )

    def _get_or_create_sizes(self, shop):
        size_names = ["xs", "s", "m", "l", "xl", "xxl"]
        sizes = []
        for name in size_names:
            size, _ = Size.objects.get_or_create(name=name, shop=shop)
            sizes.append(size)
        return sizes

    def _get_or_create_colors(self, shop):
        color_names = ["black", "white", "blue", "red", "green", "beige"]
        colors = []
        for name in color_names:
            color, _ = Color.objects.get_or_create(name=name, shop=shop)
            colors.append(color)
        return colors

    def _get_or_create_item_types(self, shop):
        type_names = ["shirt", "jeans", "kurta", "tshirt", "hoodie"]
        item_types = []
        for name in type_names:
            item_type, _ = ItemType.objects.get_or_create(name=name, shop=shop)
            item_types.append(item_type)
        return item_types

    def _get_or_create_stock_entries(self, shop):
        vendor, _ = Vendor.objects.get_or_create(
            shop=shop,
            name=f"{DUMMY_TAG.lower()} vendor",
            defaults={
                "address": "Seed Address",
                "phone": "9999999999",
                "is_active": True,
            },
        )

        stock_entries = list(
            StockEntry.objects.filter(
                shop=shop,
                vendor=vendor,
                notes__startswith=DUMMY_TAG,
            ).order_by("id")[:4]
        )

        for i in range(len(stock_entries) + 1, 5):
            entry = StockEntry(
                shop=shop,
                vendor=vendor,
                total_amount=Decimal("10000.00") + Decimal(str(i * 750)),
                paid_amount=Decimal("5000.00"),
                notes=f"{DUMMY_TAG} batch {i}",
            )
            entry.save()
            stock_entries.append(entry)

        return stock_entries
