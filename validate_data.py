"""Run all ASA-3 synthetic-data validation checks."""

from service_repository import load_and_validate_data


def main() -> None:
    assets, events, tickets = load_and_validate_data()
    print("Synthetic data is valid.")
    print(f"- Assets: {len(assets)}")
    print(f"- Maintenance events: {len(events)}")
    print(f"- Service tickets: {len(tickets)}")


if __name__ == "__main__":
    main()
