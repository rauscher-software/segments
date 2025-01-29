from PIL import Image
import os
import shutil
import ezdxf
import argparse
import aci_table as LUT

def color_to_hex(color):
    r, g, b = color
    return f"{r:02X}{g:02X}{b:02X}"

def find_closest_aci(hex_color):
    r, g, b = int(hex_color[:2], 16), int(hex_color[2:4], 16), int(hex_color[4:], 16)
    closest_color = min(
        LUT.ACI_COLORS.items(),
        key=lambda aci: (r - aci[1][0])**2 + (g - aci[1][1])**2 + (b - aci[1][2])**2
    )
    return closest_color[0]

def create_color_array(input_path):
    img = Image.open(input_path).convert("RGB")
    width, height = img.size
    return [[color_to_hex(img.getpixel((x, y))) for x in range(width)] for y in range(height)]

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
            if not visited[y][x]:
                color = color_array[y][x]
                region = explore_region(x, y, color)
                if region:
                    regions.setdefault(color, []).append(region)

    return regions

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

        # multi
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
                single_doc.saveas(os.path.join(output_path, f"{layer_name}.dxf"))

    # multi
    if mode != "singles":
        doc.saveas(f"{output_path}.dxf")

def main():
    parser = argparse.ArgumentParser(description="Convert an image to a DXF file with pixel-based outlines.")
    parser.add_argument("-i", "--input", required=True, help="Input image file path (mandatory)")
    parser.add_argument("-o", "--output", help="Output name (optional)")
    parser.add_argument("-s", "--size", type=float, default=5, help="Pixel size in DXF units (default: 5)")
    parser.add_argument("-u", "--unit", type=int, default=4, help="Unit type for DXF (default: 4 - millimeters)")

    args = parser.parse_args()

    # dxf output options
    dxf_options = ["mono", "multi", "multi_colored"]

    # input file
    input_image_path = args.input
    input_dir = os.path.dirname(input_image_path)
    input_name = os.path.splitext(os.path.basename(input_image_path))[0]
    
    # general output folder
    output_name = args.output if args.output else input_name
    output_folder = os.path.join(input_dir, f"{output_name}_output")

    # clean up
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)

    # make folder 
    os.makedirs(output_folder, exist_ok=True)

    # dxf folder
    dxf_folder = os.path.join(output_folder, "DXF")
    os.makedirs(dxf_folder, exist_ok=True)

    # single dxf files folder
    singles_folder = os.path.join(dxf_folder, "Singles")
    os.makedirs(singles_folder, exist_ok=True)

    pixel_size = args.size
    unit = args.unit

    print(f"Input file: {input_image_path}")
    print(f"Pixel size: {pixel_size}")
    print(f"Unit type: {unit}")

    color_array = create_color_array(input_image_path)
    regions = find_connected_regions(color_array)

    # multi layer dxf files
    for option in dxf_options:
        draw_region_outlines(
            regions, 
            os.path.join(dxf_folder, f"{output_name}-{option}"), 
            pixel_size, 
            unit, 
            option
            )
        
    # single layer dxf files
    draw_region_outlines(regions, singles_folder, pixel_size, unit, "singles")

    print("Output folder created successfully:", output_folder)

if __name__ == "__main__":
    main()
