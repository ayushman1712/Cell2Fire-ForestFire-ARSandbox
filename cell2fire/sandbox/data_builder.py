# coding: utf-8
"""
Data builder: generates all Cell2Fire input files (Weather.csv, IgnitionPoints.csv,
fbp_lookup_table.csv, Data.csv) from terrain rasters and parameters.
"""
import os
import shutil
import numpy as np
import pandas as pd

from . import config


def generate_weather_csv(output_dir: str, weather_params: dict = None) -> str:
    """Generate a Weather.csv file for Cell2Fire.

    Args:
        output_dir: Directory to write the file.
        weather_params: Dict with weather fields. Uses config.DEFAULT_WEATHER if None.

    Returns:
        Path to the generated Weather.csv file.
    """
    wp = weather_params or config.DEFAULT_WEATHER.copy()
    filepath = os.path.join(output_dir, "Weather.csv")

    columns = ["Scenario", "datetime", "APCP", "TMP", "RH", "WS", "WD",
               "FFMC", "DMC", "DC", "ISI", "BUI", "FWI"]

    rows = []
    # Generate multiple hours of identical weather to allow multi-period sims
    base_dt = wp.get("datetime", "2024-07-15 13:00")
    for hour_offset in range(8):
        # Parse base hour and offset
        dt_parts = base_dt.split(" ")
        date_part = dt_parts[0]
        time_parts = dt_parts[1].split(":")
        new_hour = int(time_parts[0]) + hour_offset
        dt_str = f"{date_part} {new_hour:02d}:{time_parts[1]}"

        rows.append([
            wp.get("scenario", "SBX"),
            dt_str,
            wp.get("APCP", 0.0),
            wp.get("TMP", 25.0),
            wp.get("RH", 30),
            wp.get("WS", 20),
            wp.get("WD", 270),
            wp.get("FFMC", 90),
            wp.get("DMC", 50),
            wp.get("DC", 300),
            wp.get("ISI", 12.0),
            wp.get("BUI", 65),
            wp.get("FWI", 30),
        ])

    df = pd.DataFrame(rows, columns=columns)
    df.to_csv(filepath, index=False)
    return filepath


def generate_ignition_csv(output_dir: str, ignition_cells: list) -> str:
    """Generate an IgnitionPoints.csv file for Cell2Fire.

    Args:
        output_dir: Directory to write the file.
        ignition_cells: List of 1-indexed cell numbers to ignite.

    Returns:
        Path to the generated IgnitionPoints.csv file.
    """
    filepath = os.path.join(output_dir, "Ignitions.csv")

    with open(filepath, "w") as f:
        f.write("Year,Ncell\n")
        for cell_id in ignition_cells:
            f.write(f"1,{cell_id}\n")

    return filepath


def copy_fbp_lookup(output_dir: str) -> str:
    """Copy the standard fbp_lookup_table.csv to the output directory.

    Args:
        output_dir: Directory to write the file.

    Returns:
        Path to the copied file.
    """
    src = os.path.join(config.REFERENCE_DATA_DIR, "fbp_lookup_table.csv")
    dst = os.path.join(output_dir, "fbp_lookup_table.csv")

    if not os.path.isfile(src):
        raise FileNotFoundError(
            f"fbp_lookup_table.csv not found at {src}. "
            "Ensure the Cell2Fire data directory exists."
        )

    shutil.copy2(src, dst)
    return dst


def generate_data_csv(output_dir: str) -> str:
    """Generate the Data.csv file required by the Cell2Fire C++ engine.

    This wraps the existing DataGeneratorC utility to build Data.csv
    from the .asc raster files in output_dir.

    Args:
        output_dir: Directory containing Forest.asc, elevation.asc, etc.

    Returns:
        Path to the generated Data.csv file.
    """
    # Use the existing Cell2Fire data generator
    import cell2fire.utils.DataGeneratorC as DataGenerator
    DataGenerator.GenDataFile(output_dir)

    filepath = os.path.join(output_dir, "Data.csv")
    if not os.path.isfile(filepath):
        raise RuntimeError(f"Data.csv was not generated at {filepath}")

    return filepath


def build_all_inputs(
    output_dir: str,
    ignition_cells: list,
    weather_params: dict = None,
) -> dict:
    """Generate all Cell2Fire input files in one call.

    Args:
        output_dir: Directory to write all files.
        ignition_cells: List of 1-indexed cell numbers to ignite.
        weather_params: Dict with weather parameters, or None for defaults.

    Returns:
        Dict mapping file type names to their paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    files = {}
    files["weather"] = generate_weather_csv(output_dir, weather_params)
    files["ignition"] = generate_ignition_csv(output_dir, ignition_cells)
    files["fbp_lookup"] = copy_fbp_lookup(output_dir)
    files["data"] = generate_data_csv(output_dir)

    print(f"[DataBuilder] Generated {len(files)} input files in {output_dir}")
    return files
