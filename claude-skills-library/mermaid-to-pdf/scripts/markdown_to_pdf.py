#!/usr/bin/env python3
"""
Markdown to PDF Converter with Mermaid Support

Converts Markdown files containing Mermaid diagrams to PDF format.

Dependencies:
    - markdown2: pip install markdown2
    - playwright: pip install playwright && playwright install chromium
    - mermaid_to_image.py (in the same directory)

Usage:
    python markdown_to_pdf.py input.md output.pdf
    python markdown_to_pdf.py input.md output.pdf --theme dark
    python markdown_to_pdf.py input.md output.pdf --css custom.css
"""

import argparse
import re
import sys
import os
import tempfile
import subprocess
from pathlib import Path
import hashlib
import asyncio


def extract_mermaid_blocks(markdown_content):
    """
    Extract Mermaid code blocks from Markdown content.

    Returns:
        List of tuples: (full_block, mermaid_code, block_id)
    """
    pattern = r'```mermaid\s*\n(.*?)\n```'
    matches = re.finditer(pattern, markdown_content, re.DOTALL)

    blocks = []
    for i, match in enumerate(matches):
        full_block = match.group(0)
        mermaid_code = match.group(1).strip()
        block_id = f"mermaid_{i}"
        blocks.append((full_block, mermaid_code, block_id))

    return blocks


def convert_mermaid_to_image(mermaid_code, output_path, theme='default',
                            background='white', format='png', width=3200, height=2400):
    """
    Convert Mermaid code to image using mermaid_to_image.py.

    Args:
        mermaid_code: Mermaid diagram code
        output_path: Output image path
        theme: Mermaid theme
        background: Background color
        format: Image format (png or svg)
        width: Image width for PNG (default: 3200 for ultra-high quality)
        height: Image height for PNG (default: 2400 for ultra-high quality)

    Returns:
        True if successful, False otherwise
    """
    script_dir = Path(__file__).parent
    converter_script = script_dir / 'mermaid_to_image.py'

    if not converter_script.exists():
        print(f"Error: mermaid_to_image.py not found at {converter_script}",
              file=sys.stderr)
        return False

    cmd = [
        sys.executable,
        str(converter_script),
        '--code', mermaid_code,
        str(output_path),
        '--format', format,
        '--theme', theme,
        '--background', background,
        '--width', str(width),
        '--height', str(height)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0
    except Exception as e:
        print(f"Error converting Mermaid: {str(e)}", file=sys.stderr)
        return False


def process_markdown_with_mermaid(markdown_content, temp_dir, theme='default',
                                 background='white', image_format='png'):
    """
    Process Markdown content and convert Mermaid blocks to images.

    Args:
        markdown_content: Original Markdown content
        temp_dir: Temporary directory for image files
        theme: Mermaid theme
        background: Background color
        image_format: Image format (png or svg)

    Returns:
        Modified Markdown content with image references
    """
    mermaid_blocks = extract_mermaid_blocks(markdown_content)

    if not mermaid_blocks:
        print("No Mermaid blocks found in Markdown")
        return markdown_content

    print(f"Found {len(mermaid_blocks)} Mermaid diagram(s)")

    modified_content = markdown_content

    for full_block, mermaid_code, block_id in mermaid_blocks:
        # Generate image filename
        image_filename = f"{block_id}.{image_format}"
        image_path = Path(temp_dir) / image_filename

        # Convert Mermaid to image
        print(f"Converting {block_id}...")
        success = convert_mermaid_to_image(
            mermaid_code, image_path, theme, background, image_format
        )

        if success:
            # Replace Mermaid block with image reference
            img_tag = f'![{block_id}]({image_filename})'
            modified_content = modified_content.replace(full_block, img_tag, 1)
        else:
            print(f"Warning: Failed to convert {block_id}", file=sys.stderr)
            # Keep the original code block as fallback
            fallback = f'```\n{mermaid_code}\n```'
            modified_content = modified_content.replace(full_block, fallback, 1)

    return modified_content


def markdown_to_html(markdown_content, css_content=None):
    """
    Convert Markdown to HTML.

    Args:
        markdown_content: Markdown content
        css_content: Optional CSS content

    Returns:
        HTML string
    """
    try:
        import markdown2
    except ImportError:
        print("Error: markdown2 not installed. Install with: pip install markdown2",
              file=sys.stderr)
        sys.exit(1)

    # Convert Markdown to HTML
    html_body = markdown2.markdown(
        markdown_content,
        extras=['tables', 'fenced-code-blocks', 'break-on-newline']
    )

    # Default CSS if none provided
    if css_content is None:
        css_content = """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            font-size: 9pt;
        }
        h1, h2, h3, h4, h5, h6 {
            margin-top: 24px;
            margin-bottom: 16px;
            font-weight: 600;
            line-height: 1.25;
        }
        h1 {
            font-size: 1.75em;
            border-bottom: 1px solid #eaecef;
            padding-bottom: 0.3em;
        }
        h2 {
            font-size: 1.4em;
            border-bottom: 1px solid #eaecef;
            padding-bottom: 0.3em;
        }
        h3 {
            font-size: 1.15em;
        }
        h4 {
            font-size: 1em;
        }
        code {
            background-color: #f6f8fa;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
            font-size: 85%;
        }
        pre {
            background-color: #f6f8fa;
            padding: 16px;
            overflow: auto;
            border-radius: 6px;
            font-size: 85%;
        }
        pre code {
            background-color: transparent;
            padding: 0;
        }
        table {
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 0.95em;
        }
        table th, table td {
            border: 1px solid #dfe2e5;
            padding: 6px 13px;
        }
        table th {
            background-color: #f6f8fa;
            font-weight: 600;
        }
        img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px 0;
            image-rendering: -webkit-optimize-contrast;
            image-rendering: crisp-edges;
            -ms-interpolation-mode: nearest-neighbor;
        }
        blockquote {
            padding: 0 1em;
            color: #6a737d;
            border-left: 0.25em solid #dfe2e5;
            margin: 0;
        }
        a {
            color: #0366d6;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        ul, ol {
            padding-left: 2em;
        }
        li {
            margin: 0.25em 0;
        }
        p {
            margin: 0.8em 0;
        }
        """

    # Construct full HTML
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
{css_content}
        </style>
    </head>
    <body>
{html_body}
    </body>
    </html>
    """

    return html


async def html_to_pdf_async(html_content, output_path, base_dir=None):
    """
    Convert HTML to PDF using Playwright.

    Args:
        html_content: HTML content string
        output_path: Output PDF path
        base_dir: Base directory for resolving relative paths

    Returns:
        True if successful, False otherwise
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Error: playwright not installed. Install with:", file=sys.stderr)
        print("  pip install playwright", file=sys.stderr)
        print("  playwright install chromium", file=sys.stderr)
        sys.exit(1)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            # Set HTML content
            if base_dir:
                # Write HTML to temp file to resolve relative paths correctly
                temp_html = Path(base_dir) / 'temp_output.html'
                with open(temp_html, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                await page.goto(f'file://{temp_html.absolute()}')
            else:
                await page.set_content(html_content, wait_until='networkidle')

            # Generate PDF with options for high quality
            await page.pdf(
                path=str(output_path),
                format='A4',
                print_background=True,
                margin={
                    'top': '12mm',
                    'right': '10mm',
                    'bottom': '12mm',
                    'left': '10mm'
                },
                scale=1.0,  # Use 1:1 scale for best quality
                prefer_css_page_size=False
            )

            await browser.close()
        return True

    except Exception as e:
        print(f"Error converting HTML to PDF: {str(e)}", file=sys.stderr)
        return False


def html_to_pdf(html_content, output_path, base_dir=None):
    """
    Convert HTML to PDF using Playwright (sync wrapper).

    Args:
        html_content: HTML content string
        output_path: Output PDF path
        base_dir: Base directory for resolving relative paths

    Returns:
        True if successful, False otherwise
    """
    return asyncio.run(html_to_pdf_async(html_content, output_path, base_dir))


def main():
    parser = argparse.ArgumentParser(
        description='Convert Markdown with Mermaid diagrams to PDF'
    )
    parser.add_argument('input', help='Input Markdown file')
    parser.add_argument('output', help='Output PDF file')
    parser.add_argument('--theme', choices=['default', 'forest', 'dark', 'neutral'],
                       default='default', help='Mermaid theme (default: default)')
    parser.add_argument('--background', default='white',
                       help='Mermaid background color (default: white)')
    parser.add_argument('--image-format', choices=['png', 'svg'], default='png',
                       help='Image format for Mermaid diagrams (default: png)')
    parser.add_argument('--css', help='Custom CSS file for styling')
    parser.add_argument('--keep-temp', action='store_true',
                       help='Keep temporary files for debugging')

    args = parser.parse_args()

    # Validate input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Read Markdown content
    print(f"Reading {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        markdown_content = f.read()

    # Create temporary directory
    temp_dir = tempfile.mkdtemp(prefix='mermaid_pdf_')
    print(f"Temporary directory: {temp_dir}")

    try:
        # Process Mermaid blocks
        print("Processing Mermaid diagrams...")
        processed_markdown = process_markdown_with_mermaid(
            markdown_content,
            temp_dir,
            args.theme,
            args.background,
            args.image_format
        )

        # Read custom CSS if provided
        css_content = None
        if args.css:
            css_path = Path(args.css)
            if css_path.exists():
                with open(css_path, 'r', encoding='utf-8') as f:
                    css_content = f.read()
            else:
                print(f"Warning: CSS file not found: {css_path}", file=sys.stderr)

        # Convert Markdown to HTML
        print("Converting Markdown to HTML...")
        html_content = markdown_to_html(processed_markdown, css_content)

        # Save HTML for debugging
        html_path = Path(temp_dir) / 'output.html'
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # Convert HTML to PDF
        print("Converting HTML to PDF...")
        success = html_to_pdf(html_content, output_path, temp_dir)

        if success:
            print(f"✅ Successfully created PDF: {output_path}")
            print(f"   File size: {output_path.stat().st_size / 1024:.1f} KB")
        else:
            print(f"❌ Failed to create PDF", file=sys.stderr)
            sys.exit(1)

    finally:
        # Cleanup
        if not args.keep_temp:
            import shutil
            shutil.rmtree(temp_dir)
            print(f"Cleaned up temporary files")
        else:
            print(f"Temporary files kept at: {temp_dir}")


if __name__ == '__main__':
    main()
