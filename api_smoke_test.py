import argparse
import sys

from smoke_tests import applicant_suite
from smoke_tests import ballot_audits_suite
from smoke_tests import ballot_suite
from smoke_tests import flat_selection_suite
from smoke_tests import flats_suite
from smoke_tests import projects_suite


SERVICE_RUNNERS = {
    "applicant": applicant_suite.run,
    "ballot": ballot_suite.run,
    "ballot-audits": ballot_audits_suite.run,
    "projects": projects_suite.run,
    "flats": flats_suite.run,
    "flat-selection": flat_selection_suite.run,
}


def main():
    parser = argparse.ArgumentParser(
        description="Run smoke tests for one microservice or all microservices."
    )
    parser.add_argument(
        "--service",
        choices=["all", *SERVICE_RUNNERS.keys()],
        default="all",
        help="Select one service to test, or run all smoke tests.",
    )
    parser.add_argument(
        "--applicant-base-url",
        default="http://localhost:6002",
        help="Base URL for the applicant service.",
    )
    parser.add_argument(
        "--ballot-base-url",
        default="http://localhost:6001",
        help="Base URL for the ballot service.",
    )
    parser.add_argument(
        "--ballot-audits-base-url",
        default="http://localhost:6003",
        help="Base URL for the ballot-audits service.",
    )
    parser.add_argument(
        "--projects-base-url",
        default="http://localhost:6004",
        help="Base URL for the projects service.",
    )
    parser.add_argument(
        "--flats-base-url",
        default="http://localhost:6006",
        help="Base URL for the flats service.",
    )
    parser.add_argument(
        "--flat-selection-base-url",
        default="http://localhost:6005",
        help="Base URL for the flat-selection service.",
    )
    args = parser.parse_args()

    selected_services = (
        list(SERVICE_RUNNERS.keys())
        if args.service == "all"
        else [args.service]
    )

    base_urls = {
        "applicant": args.applicant_base_url,
        "ballot": args.ballot_base_url,
        "ballot-audits": args.ballot_audits_base_url,
        "projects": args.projects_base_url,
        "flats": args.flats_base_url,
        "flat-selection": args.flat_selection_base_url,
    }

    failed_services = []

    for service_name in selected_services:
        passed = SERVICE_RUNNERS[service_name](base_urls[service_name])
        if not passed:
            failed_services.append(service_name)

    if failed_services:
        print(f"Failed services: {', '.join(failed_services)}")
        sys.exit(1)

    print("All requested smoke tests passed")


if __name__ == "__main__":
    main()
