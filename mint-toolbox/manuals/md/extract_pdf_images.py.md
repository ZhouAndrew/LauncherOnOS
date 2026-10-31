# Extract embedded PDF images

Extract bitmap images from a PDF or a directory of PDFs. Duplicate images are removed by default.

## Availability

- Category: Files and archives
- Status: Available; real-system acceptance pending
- Risk: low

## Command line

```bash
mint-toolbox --run extract_pdf_images.py --help
```

The original script arguments are passed through unchanged. Inspect the full command before confirming an operation. External launchers require their existing application or virtual environment; that runtime is not bundled.

## Graphical actions

### Extract images

Extract bitmap images from a PDF or a directory of PDFs. Duplicate images are removed by default.

Confirmation level: low.

- PDF file or folder: file_or_folder; required
- Output folder: folder; optional
- Keep duplicate images: boolean; optional

## Requirements and effects

Requires the original Python image/PDF dependencies (PyMuPDF). Accepts a PDF or folder, --output DIR and --include-duplicates. Duplicate bitmap images are removed by default.

## Tool management

Disable preserves the script, settings and manual. Mark as removed hides the entry without deleting its files. User-tool registration is independent of system extension package installation.

## Execution visibility

The interface shows the complete command. Legacy interactive scripts run in a terminal that keeps the output and exit code visible until Enter is pressed. System extensions use the separate execution log panel and save logs automatically.
