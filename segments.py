# builtin
import os
import shutil
import argparse
# pillow
from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo
# ezdxf
import ezdxf
# aci_table.py
import aci_table as LUT

# rgb to hex
def rgb_to_hex(color):
    r, g, b = color
    return f"{r:02X}{g:02X}{b:02X}"

# rgb array to hex array
def convert_array_to_hex(rgb_array):
    return [
        [
            rgb_to_hex(pixel[:3]) if pixel[3] > 0 else None  # ignore transparent pixels
            for pixel in row
        ]
        for row in rgb_array
    ]


# find closest matching ACI color (according to aci_table.py)
def find_closest_aci(hex_color):
    r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:], 16)
    closest_color = min(
        LUT.ACI_COLORS.items(),
        key=lambda aci: (r - aci[1][0])**2 + (g - aci[1][1])**2 + (b - aci[1][2])**2
    )
    return closest_color[0]

# create rgb color array from image
def create_color_array(input_path):
    img = Image.open(input_path).convert("RGBA")
    width, height = img.size
    return [[img.getpixel((x, y)) for x in range(width)] for y in range(height)]

# find connected regions of the same color
def find_connected_regions(color_array):
    height, width = len(color_array), len(color_array[0])
    visited = [[False for _ in range(width)] for _ in range(height)]
    regions = {}

    def explore_region(x, y, color):
        stack = [(x, y)]
        region = []

        while stack:
            cx, cy = stack.pop()
            if not (0 <= cx < width and 0 <= cy < height) or visited[cy][cx] or color_array[cy][cx] != color:
                continue
            visited[cy][cx] = True
            region.append((cx, cy))
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        return region

    for y in range(height):
        for x in range(width):
            if not visited[y][x] and color_array[y][x] is not None:  # ignore transparent pixels
                color = color_array[y][x]
                region = explore_region(x, y, color)
                if region:
                    regions.setdefault(color, []).append(region)

    return regions

# draw DXF outlines
def draw_region_outlines(regions, output_path, pixel_size, unit, mode):
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = unit

    # remove "Defpoints" layer
    if "Defpoints" in doc.layers:
        doc.layers.remove("Defpoints")

    for hex_color, color_regions in regions.items():
        aci_color = find_closest_aci(hex_color) if mode == "multi_colored" else 7
        layer_name = "segments" if mode == "mono" else f"#{hex_color}"

        # singles (create new doc)
        if mode == "singles":
            single_doc = ezdxf.new()
            single_doc.header["$INSUNITS"] = unit
            # remove "Defpoints" layer
            if "Defpoints" in single_doc.layers:
                single_doc.layers.remove("Defpoints")
            single_doc.layers.add(name=layer_name, color=aci_color)
            msp = single_doc.modelspace()

        # multi region
        else:
            if layer_name not in doc.layers:
                doc.layers.add(name=layer_name, color=aci_color)
            msp = doc.modelspace()

        # create outlines
        for region in color_regions:
            for x, y in region:
                if (x - 1, y) not in region:
                    msp.add_line((x * pixel_size, -y * pixel_size), (x * pixel_size, -(y + 1) * pixel_size), {"layer": layer_name})
                if (x + 1, y) not in region:
                    msp.add_line(((x + 1) * pixel_size, -y * pixel_size), ((x + 1) * pixel_size, -(y + 1) * pixel_size), {"layer": layer_name})
                if (x, y - 1) not in region:
                    msp.add_line((x * pixel_size, -y * pixel_size), ((x + 1) * pixel_size, -y * pixel_size), {"layer": layer_name})
                if (x, y + 1) not in region:
                    msp.add_line((x * pixel_size, -(y + 1) * pixel_size), ((x + 1) * pixel_size, -(y + 1) * pixel_size), {"layer": layer_name})

            # singles
            if mode == "singles":
                single_doc.saveas(os.path.join(output_path, f"HEX_{layer_name.lstrip('#')}.dxf"))

    # multi region
    if mode != "singles":
        doc.saveas(f"{output_path}.dxf")

# check if a border should be drawn by comparing neighboring pixels
def needs_border(rgb_array, x, y, dx, dy, color):
    neighbor_x = x + dx
    neighbor_y = y + dy
    height = len(rgb_array)
    width = len(rgb_array[0])

    # check if out of bounds
    if neighbor_x < 0 or neighbor_x >= width or neighbor_y < 0 or neighbor_y >= height:
        return True  # needs border at the edge

    neighbor_pixel = rgb_array[neighbor_y][neighbor_x]

    # check if neighbor is transparent or a different color
    return neighbor_pixel[3] == 0 or tuple(neighbor_pixel[:3]) != color

# create single PNG images for every color
def array_to_pngs(rgb_array, png_folder):
    width = len(rgb_array[0])
    height = len(rgb_array)

    unique_colors = set(tuple(pixel[:3]) for row in rgb_array for pixel in row if pixel[3] > 0)
    
    for color in unique_colors:
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        
        for y in range(height):
            for x in range(width):
                current_color = rgb_array[y][x]
                
                if current_color[3] > 0 and current_color[:3] == color:  # ignore transparent pixels
                    img.putpixel((x, y), current_color)
        
        # output path
        hex_color = rgb_to_hex(color).lstrip('#')
        output_image_path = os.path.join(png_folder, f"HEX_{hex_color}.png")
        # save single color PNG
        img.save(output_image_path)

# create printable black/white PNG containing all regions as outlines
def array_to_scaled_png(rgb_array, png_folder, pixel_size, unit, line_width, output_name):
    # convert pixel size to pixels based on unit in 300 DPI
    pixel_size_in_pixels = int(pixel_size * 300 / (25.4 if unit == "mm" else 1))

    width, height = len(rgb_array[0]), len(rgb_array)

    img = Image.new("RGBA", (width * pixel_size_in_pixels, height * pixel_size_in_pixels), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # identify unique colors (excluding transparent pixels)
    unique_colors = set(tuple(pixel[:3]) for row in rgb_array for pixel in row if pixel[3] > 0)

    for color in unique_colors:
        region_pixels = set()

        # find pixels belonging to current color
        for y in range(height):
            for x in range(width):
                if tuple(rgb_array[y][x][:3]) == color and rgb_array[y][x][3] > 0:  
                    # ignore transparent pixels
                    region_pixels.add((x, y))

        for x, y in region_pixels:
            top_left = (x * pixel_size_in_pixels, y * pixel_size_in_pixels)
            bottom_right = ((x + 1) * pixel_size_in_pixels, (y + 1) * pixel_size_in_pixels)

            # preserve transparent pixels
            if rgb_array[y][x][3] == 0:
                continue

            # check borders and draw line if a neighbor is different or transparent
            # top
            if needs_border(rgb_array, x, y, 0, -1, color):
                draw.line(
                    [(top_left[0], top_left[1]), (bottom_right[0], top_left[1])], 
                    fill="black", width=line_width
                )

            # bottom
            if needs_border(rgb_array, x, y, 0, 1, color):
                draw.line(
                    [(top_left[0], bottom_right[1]), (bottom_right[0], bottom_right[1])], 
                    fill="black", width=line_width
                )

            # left
            if needs_border(rgb_array, x, y, -1, 0, color):
                draw.line(
                    [(top_left[0], top_left[1]), (top_left[0], bottom_right[1])], 
                    fill="black", width=line_width
                )

            # right
            if needs_border(rgb_array, x, y, 1, 0, color):
                draw.line(
                    [(bottom_right[0], top_left[1]), (bottom_right[0], bottom_right[1])], 
                    fill="black", width=line_width
                )

    # output path
    output_image_path = os.path.join(png_folder, f"{output_name}_print.png")
    # ensure resolution
    metadata = PngInfo()
    metadata.add_text("dpi", "300")
    metadata.add_itxt("Resolution", "300 dpi")
    # save PNG
    img.save(output_image_path, pnginfo=metadata, dpi=(300, 300))

def main():
    # arguments
    parser = argparse.ArgumentParser(description="Convert an image to a DXF file with pixel-based outlines.")
    parser.add_argument("-i", "--input", required=True, help="Input image file path (mandatory)")
    parser.add_argument("-o", "--output", help="Output name (optional)")
    parser.add_argument("-s", "--size", type=float, default=5, help="Pixel size in DXF units (default: 5)")
    parser.add_argument("-u", "--unit", type=str, default="mm", choices=["mm", "inch"], help="Unit type for DXF (default: mm, options: mm | inch)")
    parser.add_argument("-l", "--linewidth", type=int, default=2, help="Line width for printable PNG file in pixels (default: 2)")

    args = parser.parse_args()

    # pixel size and unit
    pixel_size = args.size
    unit = args.unit

    # line width for printable PNG outlines
    line_width = args.linewidth

    # input file
    input_image_path = args.input
    input_dir = os.path.dirname(input_image_path)
    input_name = os.path.splitext(os.path.basename(input_image_path))[0]

    # check if input file exists
    if not os.path.exists(input_image_path):
        raise SystemExit(f"Error: The file {input_image_path} does not exist")
    
    # general output folder
    output_name = args.output if args.output else input_name
    output_folder = os.path.join(input_dir, f"{output_name}_output")

    # clean up
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)

    # make folder 
    os.makedirs(output_folder, exist_ok=True)

    # DXF folder
    dxf_folder = os.path.join(output_folder, "DXF")
    os.makedirs(dxf_folder, exist_ok=True)

    # single DXF files folder
    singles_folder = os.path.join(dxf_folder, "Singles")
    os.makedirs(singles_folder, exist_ok=True)

    # PNG folder
    png_folder = os.path.join(output_folder, "PNG")
    os.makedirs(png_folder, exist_ok=True)

    # single color PNG image folder
    png_singles_folder = os.path.join(png_folder, "Single-Color")
    os.makedirs(png_singles_folder, exist_ok=True)

    # print info
    print(f"Input file: {input_image_path}")
    print(f"Pixel size: {pixel_size}")
    print(f"Unit: {unit}")
    print(f"Line width: {line_width}px")

    # create arrays and regions
    color_array = create_color_array(input_image_path)
    hex_array = convert_array_to_hex(color_array)
    regions = find_connected_regions(hex_array)

    # DXF output options
    dxf_options = ["mono", "multi", "multi_colored"]

    # multi layer DXF files
    for option in dxf_options:
        draw_region_outlines(
            regions, 
            os.path.join(dxf_folder, f"{output_name}-{option}"), 
            pixel_size, 
            4 if unit == "mm" else 1, 
            option
            )
        
    # single layer DXF files
    draw_region_outlines(regions, singles_folder, pixel_size, 4 if unit == "mm" else 1, "singles")

    # printable black/white PNG file
    array_to_scaled_png(color_array, png_folder, pixel_size, unit, line_width, output_name)

    # single color PNG files
    array_to_pngs(color_array, png_singles_folder)

    print("Output folder created successfully:", output_folder)

if __name__ == "__main__":
    main()
