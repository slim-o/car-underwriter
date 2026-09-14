import json
import re


MODELS_FILE = "autotrader_models.json"


def load_models():

    with open(
        MODELS_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def normalise(text):

    return re.sub(
        r"\s+",
        " ",
        text.strip()
    )


def parse_title(title, models):

    title = normalise(title)

    # --------------------------------------------------
    # Extract year
    # --------------------------------------------------

    year_match = re.match(
        r"^(\d{4})\s+",
        title
    )

    if not year_match:
        return {
            "title": title,
            "year": None,
            "make": None,
            "model": None,
            "variant": None,
            "error": "Could not find year"
        }

    year = int(
        year_match.group(1)
    )

    remaining = title[
        year_match.end():
    ]

    # --------------------------------------------------
    # Identify make
    # --------------------------------------------------

    make = None

    # Longest makes first
    # This prevents something like "MG"
    # being considered before a longer make.
    sorted_makes = sorted(
        models.keys(),
        key=len,
        reverse=True
    )

    for make_name in sorted_makes:

        pattern = (
            r"^"
            + re.escape(make_name)
            + r"(?:\s+|$)"
        )

        if re.match(
            pattern,
            remaining,
            re.IGNORECASE
        ):

            make = make_name

            remaining = re.sub(
                pattern,
                "",
                remaining,
                count=1,
                flags=re.IGNORECASE
            )

            break

    if make is None:
        return {
            "title": title,
            "year": year,
            "make": None,
            "model": None,
            "variant": remaining,
            "error": "Could not find make"
        }

    remaining = normalise(
        remaining
    )

    # --------------------------------------------------
    # Identify model
    # --------------------------------------------------

    model = None

    make_models = models.get(
        make,
        []
    )

    # Longest model names first.
    #
    # This matters for things such as:
    #
    # "4 Series"
    # "4 Series Gran Coupe"
    #
    # We want the longest valid match.
    sorted_models = sorted(
        make_models,
        key=lambda item: len(item["name"]),
        reverse=True
    )

    for model_data in sorted_models:

        model_name = model_data["name"]

        pattern = (
            r"^"
            + re.escape(model_name)
            + r"(?:\s+|$)"
        )

        if re.match(
            pattern,
            remaining,
            re.IGNORECASE
        ):

            model = model_data

            remaining = re.sub(
                pattern,
                "",
                remaining,
                count=1,
                flags=re.IGNORECASE
            )

            break

    # --------------------------------------------------
    # Variant
    # --------------------------------------------------

    variant = normalise(
        remaining
    )

    return {
        "title": title,
        "year": year,
        "make": make,
        "model": model["name"] if model else None,
        "model_value": model["value"] if model else None,
        "variant": variant if variant else None,
        "error": None if model else "Could not find model"
    }


if __name__ == "__main__":

    models = load_models()

    test_titles = [
        "2014 FORD FOCUS 1.0 125 EcoBoost Zetec S 5dr",
        "2023 VAUXHALL CORSA 1.2 GS 5dr",
        "2016 BMW 5 SERIES 520d [190] SE 4dr Step Auto",
        "2017 MERCEDES-BENZ A CLASS A180d Sport Premium 5dr",
        "2015 BMW 4 SERIES 420d [190] xDrive Luxury 5dr [Professional Media]"
    ]

    for title in test_titles:

        result = parse_title(
            title,
            models
        )

        print()
        print("=" * 60)
        print(title)
        print("=" * 60)

        print(
            "Year:",
            result["year"]
        )

        print(
            "Make:",
            result["make"]
        )

        print(
            "Model:",
            result["model"]
        )

        print(
            "Model value:",
            result["model_value"]
        )

        print(
            "Variant:",
            result["variant"]
        )

        if result["error"]:
            print(
                "ERROR:",
                result["error"]
            )
