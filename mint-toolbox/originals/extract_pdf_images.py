#!/usr/bin/env python3
"""Extract embedded raster images from one PDF or every PDF in a folder.

The script automatically creates a local virtual environment named
.extract_pdf_images_venv and installs PyMuPDF inside it.

Examples:
    python3 extract_pdf_images.py document.pdf
    python3 extract_pdf_images.py document.pdf -o extracted_images
    python3 extract_pdf_images.py ./pdfs -o ./images
    python3 extract_pdf_images.py document.pdf --include-duplicates
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent
VENV_DIR = SCRIPT_DIR / ".extract_pdf_images_venv"
RESTART_FLAG = "EXTRACT_PDF_IMAGES_VENV_ACTIVE"


def get_venv_python() -> Path:
    """Return the Python executable inside the local virtual environment."""
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"

    return VENV_DIR / "bin" / "python"


def running_inside_target_venv() -> bool:
    """Check whether the script is already running inside its own venv."""
    try:
        return Path(sys.prefix).resolve() == VENV_DIR.resolve()
    except OSError:
        return False


def run_command(command: list[str], description: str) -> None:
    """Run a command and stop with a useful error if it fails."""
    print(f"[SETUP] {description}")

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        print(
            f"[ERROR] Command not found: {command[0]}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except subprocess.CalledProcessError as exc:
        print(
            f"[ERROR] {description} failed with exit code "
            f"{exc.returncode}.",
            file=sys.stderr,
        )
        raise SystemExit(exc.returncode or 1)


def create_or_repair_venv() -> Path:
    """Create the local venv and ensure PyMuPDF is installed."""
    venv_python = get_venv_python()

    if not venv_python.exists():
        print(f"[SETUP] Creating virtual environment: {VENV_DIR}")

        try:
            builder = venv.EnvBuilder(
                system_site_packages=False,
                clear=False,
                symlinks=os.name != "nt",
                with_pip=True,
            )
            builder.create(VENV_DIR)
        except Exception as exc:
            print(
                f"[ERROR] Could not create virtual environment:\n{exc}",
                file=sys.stderr,
            )
            print(
                "\nOn Debian, Ubuntu or Linux Mint, install venv support with:\n"
                f"  sudo apt install python{sys.version_info.major}."
                f"{sys.version_info.minor}-venv",
                file=sys.stderr,
            )
            raise SystemExit(1)

    if not venv_python.exists():
        print(
            f"[ERROR] The venv Python executable was not created: "
            f"{venv_python}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Ensure pip exists and is usable.
    pip_check = subprocess.run(
        [str(venv_python), "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if pip_check.returncode != 0:
        run_command(
            [str(venv_python), "-m", "ensurepip", "--upgrade"],
            "Installing pip inside the virtual environment",
        )

    # Check whether PyMuPDF is already importable.
    pymupdf_check = subprocess.run(
        [
            str(venv_python),
            "-c",
            "import fitz; print(fitz.__doc__ or '')",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if pymupdf_check.returncode != 0:
        run_command(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "pymupdf",
            ],
            "Installing PyMuPDF inside the virtual environment",
        )

    # Verify the final installation.
    verification = subprocess.run(
        [str(venv_python), "-c", "import fitz"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if verification.returncode != 0:
        print(
            "[ERROR] PyMuPDF was installed, but Python still cannot import it.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return venv_python


def bootstrap_venv() -> None:
    """Switch execution to the script-local virtual environment."""
    if running_inside_target_venv():
        return

    if os.environ.get(RESTART_FLAG) == "1":
        print(
            "[ERROR] The script could not start inside its virtual "
            "environment.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    venv_python = create_or_repair_venv()

    environment = os.environ.copy()
    environment[RESTART_FLAG] = "1"

    command = [
        str(venv_python),
        str(SCRIPT_PATH),
        *sys.argv[1:],
    ]

    print(f"[SETUP] Restarting with venv Python: {venv_python}")

    try:
        os.execve(str(venv_python), command, environment)
    except OSError as exc:
        print(
            f"[ERROR] Could not restart inside the virtual environment: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)


# The bootstrap must run before importing PyMuPDF.
bootstrap_venv()

try:
    import fitz  # type: ignore[import-not-found]
except ImportError as exc:
    print(
        f"[ERROR] PyMuPDF is unavailable inside the virtual environment: "
        f"{exc}",
        file=sys.stderr,
    )
    raise SystemExit(1)


def safe_name(name: str) -> str:
    """Return a filesystem-friendly name."""
    cleaned = "".join(
        character
        if character.isalnum() or character in "-_."
        else "_"
        for character in name
    )
    return cleaned.strip("._") or "pdf"


def extract_images(
    pdf_path: Path,
    output_root: Path,
    include_duplicates: bool = False,
) -> int:
    """Extract images from a PDF and return the number of saved files."""
    pdf_output = output_root / safe_name(pdf_path.stem)
    pdf_output.mkdir(parents=True, exist_ok=True)

    saved_count = 0
    seen_xrefs: set[int] = set()

    try:
        document = fitz.open(pdf_path)
    except Exception as exc:
        print(f"[ERROR] Cannot open {pdf_path}: {exc}", file=sys.stderr)
        return 0

    if document.needs_pass:
        print(
            f"[SKIP] Password-protected PDF: {pdf_path}",
            file=sys.stderr,
        )
        document.close()
        return 0

    try:
        for page_number, page in enumerate(document, start=1):
            images = page.get_images(full=True)

            for image_number, image_info in enumerate(images, start=1):
                xref = image_info[0]

                if not include_duplicates and xref in seen_xrefs:
                    continue

                if xref <= 0:
                    print(
                        "[WARN] Skipping an inline or unaddressable image on "
                        f"page {page_number} of {pdf_path.name}",
                        file=sys.stderr,
                    )
                    continue

                try:
                    image = document.extract_image(xref)
                    image_bytes = image["image"]
                    extension = image.get("ext", "bin")

                    filename = (
                        f"page_{page_number:04d}_"
                        f"image_{image_number:03d}_"
                        f"xref_{xref}.{extension}"
                    )

                    output_path = pdf_output / filename
                    output_path.write_bytes(image_bytes)

                    seen_xrefs.add(xref)
                    saved_count += 1
                    print(f"[SAVED] {output_path}")

                except Exception as exc:
                    print(
                        f"[ERROR] Could not extract image xref {xref} "
                        f"from page {page_number} of "
                        f"{pdf_path.name}: {exc}",
                        file=sys.stderr,
                    )
    finally:
        document.close()

    print(
        f"[DONE] {pdf_path.name}: "
        f"{saved_count} image(s) extracted"
    )
    return saved_count


def find_pdfs(input_path: Path) -> list[Path]:
    """Return one PDF or all PDFs directly inside a directory."""
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise ValueError(f"Input file is not a PDF: {input_path}")

        return [input_path]

    if input_path.is_dir():
        return sorted(
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        )

    raise FileNotFoundError(
        f"Input path does not exist: {input_path}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract embedded images from a PDF or a folder of PDFs."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="A PDF file or a directory containing PDF files",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("extracted_images"),
        help="Output directory (default: extracted_images)",
    )

    parser.add_argument(
        "--include-duplicates",
        action="store_true",
        help=(
            "Save reused images again when they appear on multiple pages"
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        input_path = args.input.expanduser().resolve()
        pdf_files = find_pdfs(input_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    if not pdf_files:
        print("[ERROR] No PDF files found.", file=sys.stderr)
        return 1

    output_root = args.output.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    total = 0

    for pdf_file in pdf_files:
        total += extract_images(
            pdf_path=pdf_file,
            output_root=output_root,
            include_duplicates=args.include_duplicates,
        )

    print(
        f"[FINISHED] Extracted {total} image(s) "
        f"from {len(pdf_files)} PDF(s)."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
