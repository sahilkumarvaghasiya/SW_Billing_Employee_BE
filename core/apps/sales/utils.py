from decimal import Decimal


def format_indian_amount(value):
    amount = Decimal(str(value if value is not None else "0.00")).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    amount = abs(amount)

    integer_part, decimal_part = f"{amount:.2f}".split(".")

    if len(integer_part) <= 3:
        grouped_integer = integer_part
    else:
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]
        groups = []

        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]

        if remaining:
            groups.insert(0, remaining)

        grouped_integer = ",".join(groups + [last_three])

    return f"{sign}{grouped_integer}.{decimal_part}"
