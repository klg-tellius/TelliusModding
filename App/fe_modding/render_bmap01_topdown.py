#!/usr/bin/env python3
"""Render a top-down view of bmap01 cropped to the gameplay grid.

This script reads a map.bin file (expected to be from bmap01) and generates
a grayscale PNG where each pixel represents a tile's average base elevation.
"""

import sys
from pathlib import Path
from PIL import Image

try:
    from fe_modding.formats.map_file import read_map_file
except ImportError:
    print("Error: Could not import fe_modding.formats.map_file")
    print("Make sure you are running this script from the project root or have the package installed.")
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python render_bmap01_topdown.py <path_to_map.bin>")
        print("Example: python render_bmap01_topdown.py zmap/bmap01/map.bin")
        sys.exit(1)

    map_bin_path = Path(sys.argv[1])
    if not map_bin_path.exists():
        print(f"Error: File not found: {map_bin_path}")
        sys.exit(1)

    try:
        data = read_map_file(map_bin_path)
    except Exception as e:
        print(f"Error reading map.bin: {e}")
        sys.exit(1)

    if data.capacity is None:
        print("Error: Map capacity not found in the map.bin.")
        sys.exit(1)

    width = data.capacity.x_size
    height = data.capacity.y_size

    if data.panel_index_base is None or not data.unique_panel_base:
        print("Error: Base panel index or unique panel base not found.")
        sys.exit(1)

    # Create a grayscale image (mode 'L' for 8-bit pixels, black to white)
    img = Image.new('L', (width, height))
    pixels = img.load()

    # Collect elevations for normalization
    elevations = []
    for x in range(width):
        for y in range(height):
            panel_index = data.panel_index_base[x][y]
            if not 0 <= panel_index < len(data.unique_panel_base):
                # Invalid panel index; treat as minimum elevation
                elevations.append(0)
            else:
                panel = data.unique_panel_base[panel_index]
                # Average of the four corner elevations
                avg_elev = (panel.top_left_elevation +
                            panel.top_right_elevation +
                            panel.bottom_left_elevation +
                            panel.bottom_right_elevation) / 4.0
                elevations.append(avg_elev)

    # Normalize elevations to 0-255
    min_elev = min(elevations)
    max_elev = max(elevations)
    if max_elev == min_elev:
        # Avoid division by zero; set all to mid-gray
        normalized = [128] * len(elevations)
    else:
        normalized = [
            int((e - min_elev) * 255 / (max_elev - min_elev))
            for e in elevations
        ]

    # Apply normalized values to image pixels
    index = 0
    for x in range(width):
        for y in range(height):
            pixels[x, y] = normalized[index]
            index += 1

    # Save the image next to the input file with .png extension
    output_path = map_bin_path.with_suffix('.png')
    try:
        img.save(output_path)
        print(f"Saved top-down view to {output_path}")
    except Exception as e:
        print(f"Error saving image: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()