# coding: utf-8
"""
Simulation bridge: orchestrates Cell2Fire C++ engine runs and parses grid outputs.
"""
import os
import glob
import shutil
import subprocess
import numpy as np
import pandas as pd

from . import config
from . import data_builder
from .terrain_generator import TerrainGenerator

import cell2fire
_p = str(cell2fire.__path__)
_l = _p.find("'")
_r = _p.find("'", _l + 1)
CELL2FIRE_PKG_PATH = _p[_l + 1:_r]


class SimulationBridge:
    """Bridges the sandbox application with the Cell2Fire C++ engine.

    Manages the full cycle of:
        1. Generating input files from terrain data
        2. Running the Cell2Fire C++ simulator as a subprocess
        3. Parsing the output grid CSVs into arrays for rendering
    """

    def __init__(
        self,
        sim_data_dir: str = None,
        output_dir: str = None,
    ):
        self.sim_data_dir = sim_data_dir or config.SANDBOX_DATA_DIR
        self.output_dir = output_dir or config.SANDBOX_OUTPUT_DIR
        self.cell2fire_exe = os.path.join(
            CELL2FIRE_PKG_PATH, "Cell2FireC", "Cell2Fire"
        )
        self.terrain_gen = TerrainGenerator()
        self._last_grids = []

    def prepare_terrain(self, depth_frame: np.ndarray, firelines: list = None) -> dict:
        """Generate terrain raster files from a depth frame.

        Args:
            depth_frame: 2D uint16 array from the Kinect.
            firelines: Optional list of (r1, c1, r2, c2) firebreaks.

        Returns:
            Dict with terrain data and file paths.
        """
        return self.terrain_gen.generate_all(depth_frame, self.sim_data_dir, firelines=firelines)

    def run_simulation(
        self,
        ignition_cells: list,
        weather_params: dict = None,
    ) -> list:
        """Run a complete Cell2Fire simulation and return grid outputs.

        Args:
            ignition_cells: List of 1-indexed cell numbers to ignite.
            weather_params: Dict of weather parameters, or None for defaults.

        Returns:
            List of 2D numpy arrays, one per time step, where:
                0 = unburned/available
                1 = burning
                2 = burned out
            Returns empty list if simulation fails.
        """
        # Clean previous output
        self.cleanup_output()

        # Generate all input files
        try:
            data_builder.build_all_inputs(
                self.sim_data_dir, ignition_cells, weather_params
            )
        except Exception as e:
            print(f"[SimulationBridge] Failed to build input files: {e}")
            return []

        # Build the C++ command
        exec_array = self._build_command()
        if exec_array is None:
            return []

        # Run the simulation
        success = self._execute(exec_array)
        if not success:
            return []

        # Parse grid outputs
        grids = self.parse_grid_outputs()
        self._last_grids = grids
        return grids

    def _build_command(self) -> list:
        """Build the subprocess command array for Cell2Fire C++."""
        exe_path = self.cell2fire_exe

        # On Windows, look for .exe
        if os.name == "nt" and not exe_path.endswith(".exe"):
            exe_with_ext = exe_path + ".exe"
            if os.path.isfile(exe_with_ext):
                exe_path = exe_with_ext

        if not os.path.isfile(exe_path):
            print(f"[SimulationBridge] Cell2Fire executable not found: {exe_path}")
            print("[SimulationBridge] Please compile the C++ engine first.")
            return None

        cmd = [
            exe_path,
            "--input-instance-folder", self.sim_data_dir + os.sep,
            "--output-folder", self.output_dir + os.sep,
            "--ignitions",
            "--sim-years", str(config.SIM_YEARS),
            "--nsims", str(config.N_SIMS),
            "--grids",
            "--finalGrid",
            "--Fire-Period-Length", str(config.FIRE_PERIOD_LENGTH),
            "--weather", config.WEATHER_OPT,
            "--nweathers", "1",
            "--ROS-CV", str(config.ROS_CV),
            "--seed", str(config.SEED),
            "--ROS-Threshold", str(config.ROS_THRESHOLD),
            "--HFI-Threshold", str(config.HFI_THRESHOLD),
        ]

        return cmd

    def _execute(self, exec_array: list) -> bool:
        """Execute the Cell2Fire subprocess.

        Returns:
            True if the simulation completed successfully, False otherwise.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        log_path = os.path.join(self.output_dir, "LogFile.txt")

        print("[SimulationBridge] Running Cell2Fire C++ simulation...")
        try:
            with open(log_path, "w") as log_file:
                proc = subprocess.Popen(
                    exec_array,
                    stdout=log_file,
                    stderr=log_file,  # also capture stderr
                )
                proc.communicate(timeout=60)  # 60 second timeout

            return_code = proc.returncode
            if return_code != 0:
                print(f"[SimulationBridge] C++ returned {return_code}. Check {log_path}")
                return False

            print("[SimulationBridge] Simulation completed successfully.")
            return True

        except subprocess.TimeoutExpired:
            print("[SimulationBridge] Simulation timed out (>60s).")
            proc.kill()
            return False
        except Exception as e:
            print(f"[SimulationBridge] Execution error: {e}")
            return False

    def parse_grid_outputs(self) -> list:
        """Parse ForestGrid*.csv output files into numpy arrays.

        Cell2Fire writes grid state at each time step as CSV files:
            Grids/Grids1/ForestGrid01.csv, ForestGrid02.csv, ...

        Each CSV contains one value per row (flattened row-major), where:
            0 = available/unburned
            1 = burning/burned

        Returns:
            List of 2D numpy arrays (rows × cols), one per time step.
            Cell values: 0 = unburned, 1 = burning (at that step).
        """
        grids_dir = os.path.join(self.output_dir, "Grids", "Grids1")
        if not os.path.isdir(grids_dir):
            print(f"[SimulationBridge] Grid output dir not found: {grids_dir}")
            return []

        # Find all grid files, sorted by number
        pattern = os.path.join(grids_dir, "ForestGrid*.csv")
        grid_files = sorted(glob.glob(pattern))

        if not grid_files:
            print("[SimulationBridge] No grid output files found.")
            return []

        grids = []
        rows = config.SIM_ROWS
        cols = config.SIM_COLS

        for gf in grid_files:
            try:
                df = pd.read_csv(gf, header=None)
                data = df.values.flatten()

                if len(data) != rows * cols:
                    print(f"[SimulationBridge] Grid size mismatch in {gf}: "
                          f"expected {rows * cols}, got {len(data)}")
                    continue

                grid = data.reshape((rows, cols)).astype(int)
                grids.append(grid)
            except Exception as e:
                print(f"[SimulationBridge] Error reading {gf}: {e}")
                continue

        print(f"[SimulationBridge] Parsed {len(grids)} grid time steps.")

        # Post-process: derive burning vs burned-out states
        # Cell2Fire grids show cumulative burn.
        # We compute: burned_this_step = grid[t] - grid[t-1]
        if len(grids) > 1:
            state_grids = []
            for t in range(len(grids)):
                state = np.zeros((rows, cols), dtype=int)

                if t == 0:
                    # First grid: any cell marked = burning
                    state[grids[t] == 1] = 1
                else:
                    # Newly burned this step = burning
                    newly_burned = (grids[t] == 1) & (grids[t - 1] == 0)
                    state[newly_burned] = 1

                    # Previously burned = burned out
                    prev_burned = grids[t - 1] == 1
                    state[prev_burned] = 2

                    # Currently burning overrides burned-out
                    state[newly_burned] = 1

                state_grids.append(state)
            return state_grids

        return grids

    def get_last_grids(self) -> list:
        """Return the grid outputs from the most recent simulation."""
        return self._last_grids

    def cleanup_output(self):
        """Remove previous simulation output files."""
        if os.path.isdir(self.output_dir):
            try:
                shutil.rmtree(self.output_dir)
            except Exception as e:
                print(f"[SimulationBridge] Cleanup warning: {e}")

    def cleanup_all(self):
        """Remove all temporary directories."""
        self.cleanup_output()
        if os.path.isdir(self.sim_data_dir):
            try:
                shutil.rmtree(self.sim_data_dir)
            except Exception as e:
                print(f"[SimulationBridge] Cleanup warning: {e}")

    def precompute_and_save(
        self,
        depth_frame: np.ndarray,
        ignition_row: int = None,
        ignition_col: int = None,
        weather_params: dict = None,
        cache_path: str = None,
        firelines: list = None,
    ) -> list:
        """Run full pipeline: terrain → simulation → save fire grids to disk.

        Args:
            depth_frame: Raw depth frame from Kinect.
            ignition_row: Row of the ignition point (default: config center).
            ignition_col: Col of the ignition point (default: config center).
            weather_params: Weather parameters (default: config defaults).
            cache_path: Path to save the .npz cache (default: config path).
            firelines: Optional list of (r1, c1, r2, c2) firebreaks.

        Returns:
            List of fire grid arrays (same as run_simulation).
        """
        ig_row = ignition_row if ignition_row is not None else config.DEFAULT_IGNITION_ROW
        ig_col = ignition_col if ignition_col is not None else config.DEFAULT_IGNITION_COL
        cache = cache_path or config.PRECOMPUTED_CACHE_FILE

        print(f"[SimulationBridge] Precomputing simulation from ignition ({ig_row}, {ig_col})...")

        # Generate terrain files from the depth frame
        result = self.prepare_terrain(depth_frame, firelines=firelines)

        # Calculate 1-indexed cell ID (row-major order)
        ignition_cell_id = ig_row * config.SIM_COLS + ig_col + 1

        # Run the simulation
        grids = self.run_simulation(
            ignition_cells=[ignition_cell_id],
            weather_params=weather_params,
        )

        if grids:
            # Save to disk
            os.makedirs(os.path.dirname(cache), exist_ok=True)

            # Stack grids into a 3D array: (time_steps, rows, cols)
            grids_array = np.stack(grids, axis=0)
            np.savez_compressed(
                cache,
                grids=grids_array,
                ignition_row=ig_row,
                ignition_col=ig_col,
                elevation=result["elevation"],
                fuel=result["fuel"],
            )
            print(f"[SimulationBridge] Saved {len(grids)} fire grids to {cache}")
        else:
            print("[SimulationBridge] Precomputation produced no output.")

        return grids

    @staticmethod
    def load_precomputed(cache_path: str = None) -> dict:
        """Load precomputed fire grids from disk.

        Args:
            cache_path: Path to the .npz cache file.

        Returns:
            Dict with keys:
                'grids': list of 2D numpy arrays (fire state per time step)
                'ignition_row': int
                'ignition_col': int
                'elevation': 2D float array
                'fuel': 2D int array
            Returns None if cache not found.
        """
        cache = cache_path or config.PRECOMPUTED_CACHE_FILE

        if not os.path.isfile(cache):
            print(f"[SimulationBridge] No precomputed cache found at {cache}")
            return None

        data = np.load(cache, allow_pickle=False)
        grids_3d = data["grids"]  # shape: (T, rows, cols)
        grids = [grids_3d[t] for t in range(grids_3d.shape[0])]

        print(f"[SimulationBridge] Loaded {len(grids)} precomputed fire grids from {cache}")

        return {
            "grids": grids,
            "ignition_row": int(data["ignition_row"]),
            "ignition_col": int(data["ignition_col"]),
            "elevation": data["elevation"],
            "fuel": data["fuel"],
        }
