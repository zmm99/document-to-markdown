from datetime import datetime


DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def normalize_range_boundary(value: str | None, end_of_day: bool = False) -> str | None:
    if value is None or value.strip() == "":
        return None

    text = value.strip()
    if len(text) == 10:
        parsed = datetime.strptime(text, DATE_FORMAT)
        if end_of_day:
            return parsed.strftime(DATE_FORMAT) + " 23:59:59"
        return parsed.strftime(DATE_FORMAT) + " 00:00:00"

    parsed = datetime.strptime(text, DATETIME_FORMAT)
    return parsed.strftime(DATETIME_FORMAT)


def normalize_date_range(
    start_date: str | None,
    end_date: str | None,
) -> tuple[str | None, str | None]:
    start = normalize_range_boundary(start_date)
    end = normalize_range_boundary(end_date, end_of_day=True)
    if start is not None and end is not None and start > end:
        raise ValueError("start_date must be before or equal to end_date")
    return start, end
