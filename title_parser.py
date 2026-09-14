import re

AUTOTRADER_MAKES = [
    "Abarth",
    "AC",
    "AION",
    "Aixam",
    "AK",
    "Alfa Romeo",
    "Allard",
    "Alpine",
    "Ariel",
    "Asia",
    "Aston Martin",
    "Audi",
    "Austin",
    "BAC",
    "Beauford",
    "Bentley",
    "BMW",
    "Bristol",
    "Bugatti",
    "Buick",
    "BYD",
    "Cadillac",
    "Carbodies",
    "Caterham",
    "CFMOTO",
    "Changan",
    "Chery",
    "Chesil",
    "Chevrolet",
    "Chrysler",
    "Citroen",
    "Corbin",
    "Corvette",
    "CUPRA",
    "Dacia",
    "Daewoo",
    "Daihatsu",
    "Daimler",
    "Datsun",
    "David Brown",
    "Dax",
    "De Tomaso",
    "Dodge",
    "DS AUTOMOBILES",
    "Ferrari",
    "Fiat",
    "Fisker",
    "Ford",
    "Gardner Douglas",
    "Geely",
    "Genesis",
    "GMC",
    "Great Wall",
    "GWM",
    "Healey",
    "Holden",
    "Honda",
    "Hummer",
    "Hyundai",
    "INEOS",
    "Infiniti",
    "Isuzu",
    "Iveco",
    "JAECOO",
    "Jaguar",
    "JBA",
    "Jeep",
    "Jensen",
    "KGM",
    "Kia",
    "Koenigsegg",
    "Lada",
    "Lamborghini",
    "Lancia",
    "Land Rover",
    "Leapmotor",
    "Lepas",
    "LEVC",
    "Lexus",
    "Leyland",
    "Lincoln",
    "Lister",
    "London Taxis International",
    "Lotus",
    "Marlin",
    "Maserati",
    "MAXUS",
    "Maybach",
    "Mazda",
    "McLaren",
    "Mercedes-Benz",
    "MEV",
    "MG",
    "Micro",
    "Microcar",
    "Mills Extreme Vehicles (MEV)",
    "MINI",
    "Mitsubishi",
    "MK",
    "MOKE",
    "Morgan",
    "Morris",
    "Nardini",
    "NG",
    "Nissan",
    "Noble",
    "OMODA",
    "Opel",
    "Perodua",
    "Peugeot",
    "Pilgrim",
    "Plymouth",
    "Polestar",
    "Pontiac",
    "Porsche",
    "Proton",
    "Quantum",
    "Ram",
    "Reliant",
    "Renault",
    "Rimac",
    "Rivian",
    "Robin Hood",
    "Rolls-Royce",
    "Rover",
    "Saab",
    "SEAT",
    "Shelby",
    "Skoda",
    "Skywell",
    "Smart",
    "SsangYong",
    "Standard",
    "Subaru",
    "Sunbeam",
    "Suzuki",
    "Tesla",
    "Toyota",
    "Triumph",
    "TVR",
    "Ultima",
    "Vauxhall",
    "Viscount",
    "Volkswagen",
    "Volvo",
    "VRS",
    "Westfield",
    "Wiesmann",
    "XPENG",
    "Yugo"
]

def parse_vehicle_title(title):
    """
    Extract the year and make from an underwriter vehicle title.

    Example:
        2016 BMW 5 SERIES 520d [190] SE 4dr Step Auto

    Returns:
        {
            "year": 2016,
            "make": "BMW",
            "remaining": "5 SERIES 520d [190] SE 4dr Step Auto"
        }
    """

    title = title.strip()

    # -----------------------------
    # Extract year
    # -----------------------------

    year_match = re.match(
        r"^(\d{4})\s+",
        title
    )

    if not year_match:
        return None

    year = int(year_match.group(1))

    remaining = title[
        year_match.end():
    ]

    # -----------------------------
    # Find make
    # -----------------------------

    # Longest first prevents things like
    # "Land Rover" being interpreted incorrectly.
    makes = sorted(
        AUTOTRADER_MAKES,
        key=len,
        reverse=True
    )

    make = None

    for candidate in makes:

        if remaining.lower().startswith(
            candidate.lower() + " "
        ):

            make = candidate

            remaining = remaining[
                len(candidate):
            ].strip()

            break

    if make is None:
        return None

    return {
        "year": year,
        "make": make,
        "remaining": remaining
    }

title = "2017 MERCEDES-BENZ A CLASS A180d Sport Premium 5dr"

print(
    parse_vehicle_title(title)
)