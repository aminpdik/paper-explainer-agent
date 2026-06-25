import argparse
import logging
from pathlib import Path

from paper_explainer.graph import graph


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a beginner-friendly PDF explanation of a research paper."
    )

    parser.add_argument(
        "--pdf",
        required=True,
        help="Path to the input research paper PDF.",
    )

    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Directory where generated files will be saved.",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help=(
            "Optional maximum number of pages to explain. "
            "Useful for testing with only the first few pages."
        ),
    )

    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()

    input_pdf_path = Path(args.pdf)
    output_dir = Path(args.output_dir)

    initial_state = {
        "pdf_path": str(input_pdf_path),
        "output_dir": str(output_dir),
        "max_pages": args.max_pages,
    }

    result = graph.invoke(initial_state)

    final_pdf_path = result["final_pdf_path"]

    print("\nDone.")
    print(f"Final PDF saved at: {final_pdf_path}")


if __name__ == "__main__":
    main()
