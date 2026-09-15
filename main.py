"""Command-line entry point for lesson 1 of Asset Service Assistant."""

import argparse

from asset_repository import Asset, find_asset, load_assets


def print_asset(asset: Asset) -> None:
    """Print one asset in a readable form."""
    print(f"{asset.asset_id}: {asset.name}")
    print(f"  Type: {asset.asset_type}")
    print(f"  Make/model: {asset.manufacturer} {asset.model} ({asset.year})")
    print(f"  Location: {asset.location}")
    print(f"  Status: {asset.status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Look up synthetic assets")
    parser.add_argument(
        "asset_id",
        nargs="?",
        help="Exact asset ID to look up, for example VEH-1001",
    )
    args = parser.parse_args()

    assets = load_assets()

    if args.asset_id:
        asset = find_asset(args.asset_id, assets)
        if asset is None:
            print(f"No asset found with ID '{args.asset_id}'.")
            return
        print_asset(asset)
        return

    print(f"Loaded {len(assets)} synthetic assets:")
    for asset in assets:
        print(f"- {asset.asset_id}: {asset.name} [{asset.status}]")


if __name__ == "__main__":
    main()
