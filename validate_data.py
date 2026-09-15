"""Run all synthetic-data validation checks."""

from manual_repository import load_manuals, validate_manual_applicability
from service_repository import load_and_validate_data


def main() -> None:
    assets, events, tickets = load_and_validate_data()
    manuals = load_manuals()
    validate_manual_applicability(manuals, assets)
    print("Synthetic data is valid.")
    print(f"- Assets: {len(assets)}")
    print(f"- Maintenance events: {len(events)}")
    print(f"- Service tickets: {len(tickets)}")
    print(f"- Maintenance manuals: {len(manuals)}")


if __name__ == "__main__":
    main()
