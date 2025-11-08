#!/usr/bin/env python3
"""
Mermaid to Image Converter

Converts Mermaid diagram code to high-quality images (PNG or SVG).

Dependencies:
    - Node.js and npm (for mermaid-cli)
    - mermaid-cli: npm install -g @mermaid-js/mermaid-cli
    - OR Playwright: pip install playwright && playwright install chromium

Usage:
    python mermaid_to_image.py input.mmd output.png --format png
    python mermaid_to_image.py input.mmd output.svg --format svg
    python mermaid_to_image.py --code "graph TD; A-->B" output.png
"""

import argparse
import subprocess
import sys
import os
import tempfile
from pathlib import Path


def check_mermaid_cli():
    """Check if mermaid-cli (mmdc) is installed."""
    try:
        result = subprocess.run(['mmdc', '--version'],
                              capture_output=True,
                              text=True,
                              timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def convert_with_mermaid_cli(input_path, output_path, format='png', theme='default',
                             background='white', width=3200, height=2400):
    """
    Convert Mermaid diagram using mermaid-cli (mmdc).

    Args:
        input_path: Path to input .mmd file
        output_path: Path to output image file
        format: Output format ('png' or 'svg')
        theme: Mermaid theme ('default', 'forest', 'dark', 'neutral')
        background: Background color
        width: Image width (for PNG)
        height: Image height (for PNG)

    Returns:
        True if successful, False otherwise
    """
    cmd = ['mmdc', '-i', str(input_path), '-o', str(output_path)]

    # Add format-specific options
    if format == 'svg':
        # SVG output doesn't need width/height parameters
        pass
    else:
        cmd.extend(['-w', str(width), '-H', str(height)])

    # Add theme
    cmd.extend(['-t', theme])

    # Add background
    cmd.extend(['-b', background])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            return True
        else:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return False

    except subprocess.TimeoutExpired:
        print("Error: Mermaid conversion timed out", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return False


def convert_with_playwright(mermaid_code, output_path, format='png', theme='default',
                           background='white', width=3200, height=2400):
    """
    Convert Mermaid diagram using Playwright (fallback method).

    Requires: pip install playwright && playwright install chromium
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Error: Playwright not installed. Install with: pip install playwright",
              file=sys.stderr)
        print("Then run: playwright install chromium", file=sys.stderr)
        return False

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{
                startOnLoad: true,
                theme: '{theme}',
                themeVariables: {{
                    background: '{background}'
                }}
            }});
        </script>
        <style>
            body {{
                margin: 0;
                padding: 20px;
                background: {background};
            }}
        </style>
    </head>
    <body>
        <div class="mermaid">
{mermaid_code}
        </div>
    </body>
    </html>
    """

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            # Use device_scale_factor for Retina-quality rendering (2x pixel density)
            page = browser.new_page(
                viewport={'width': width, 'height': height},
                device_scale_factor=2.0  # Double pixel density for crisp images
            )
            page.set_content(html_content)

            # Wait for mermaid to render
            page.wait_for_timeout(2000)

            # Get the rendered SVG element
            svg_element = page.query_selector('.mermaid svg')
            if not svg_element:
                print("Error: Mermaid diagram failed to render", file=sys.stderr)
                browser.close()
                return False

            if format == 'svg':
                # Save as SVG - use outerHTML to get complete SVG element
                svg_content = svg_element.evaluate("el => el.outerHTML")
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(svg_content)
            else:
                # Save as PNG
                svg_element.screenshot(path=str(output_path))

            browser.close()
            return True

    except Exception as e:
        print(f"Error with Playwright: {str(e)}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Convert Mermaid diagrams to high-quality images'
    )
    parser.add_argument('input', nargs='?', help='Input Mermaid file (.mmd)')
    parser.add_argument('output', help='Output image file')
    parser.add_argument('--code', help='Mermaid code string (alternative to input file)')
    parser.add_argument('--format', choices=['png', 'svg'], default='png',
                       help='Output format (default: png)')
    parser.add_argument('--theme', choices=['default', 'forest', 'dark', 'neutral'],
                       default='default', help='Mermaid theme')
    parser.add_argument('--background', default='white',
                       help='Background color (default: white)')
    parser.add_argument('--width', type=int, default=3200,
                       help='Image width for PNG (default: 3200)')
    parser.add_argument('--height', type=int, default=2400,
                       help='Image height for PNG (default: 2400)')
    parser.add_argument('--use-playwright', action='store_true',
                       help='Force use of Playwright instead of mermaid-cli')

    args = parser.parse_args()

    # Validate input
    if not args.input and not args.code:
        print("Error: Either input file or --code must be provided", file=sys.stderr)
        sys.exit(1)

    # Prepare input file
    if args.code:
        # Create temporary file with code
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.mmd',
                                                delete=False, encoding='utf-8')
        temp_file.write(args.code)
        temp_file.close()
        input_path = temp_file.name
        cleanup_temp = True
    else:
        input_path = args.input
        if not os.path.exists(input_path):
            print(f"Error: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        cleanup_temp = False

    output_path = Path(args.output)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Choose conversion method
    success = False

    if args.use_playwright:
        # Force Playwright
        with open(input_path, 'r', encoding='utf-8') as f:
            mermaid_code = f.read()
        success = convert_with_playwright(
            mermaid_code, output_path, args.format, args.theme,
            args.background, args.width, args.height
        )
    else:
        # Try mermaid-cli first
        if check_mermaid_cli():
            print("Using mermaid-cli (mmdc)...")
            success = convert_with_mermaid_cli(
                input_path, output_path, args.format, args.theme,
                args.background, args.width, args.height
            )
        else:
            print("mermaid-cli not found, falling back to Playwright...")
            with open(input_path, 'r', encoding='utf-8') as f:
                mermaid_code = f.read()
            success = convert_with_playwright(
                mermaid_code, output_path, args.format, args.theme,
                args.background, args.width, args.height
            )

    # Cleanup
    if cleanup_temp:
        os.unlink(input_path)

    if success:
        print(f"✅ Successfully converted Mermaid diagram to {output_path}")
        sys.exit(0)
    else:
        print(f"❌ Failed to convert Mermaid diagram", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
