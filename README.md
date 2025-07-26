# Drawing-Machine

This repository contains the complete software and Arduino firmware for a custom DIY pen plotter. The hardware is based on the 3D-printed design from [Thingiverse: Pen Plotter by KikiTay](https://www.thingiverse.com/thing:4645955), with custom modifications and iterations. The project uses stepper motors controlled via an Arduino, and Python scripts handle everything from manual control to image-to-G-code conversion and sending commands to the plotter.

![](./gif.gif)

The system interprets a subset of G-code commands (with coordinates in motor steps, not mm) to move the X, Y, and Z axes. Images are processed into skeletonized lines, converted to optimized G-code paths, visualized, and sent over serial.

## Features
- **Hardware Control**: Arduino firmware for precise stepper motor movement using half-stepping.
- **Calibration Tool**: GUI to extract calibration points for mapping steps to physical distances.
- **Manual Control**: Simple GUI for jogging motors and testing.
- **Image to G-code**: Convert any image (PNG, JPG, etc.) to G-code paths via skeletonization and path optimization.
- **G-code Visualization**: 2D preview of G-code files.
- **G-code Sender**: GUI to load, send, and monitor G-code execution with progress tracking and homing.
- **Custom G-code Dialect**: Supports G0/G1 (move), G28 (home), G90/G91 (absolute/relative), M84 (disable motors), with coordinates in steps.

## Hardware Requirements
- **3D-Printed Parts**: Based on [Thingiverse design](https://www.thingiverse.com/thing:4645955). Print and assemble the frame, carriages, and mounts. Added some limit switches and mounts for cleanliness.
- **Motors**: 3x 28BYJ-48 stepper motors (for X, Y, Z axes).
- **Electronics**:
  - Arduino Uno (or compatible).
  - ULN2003 driver boards for each stepper motor.
  - Limit switches (pull-up) for homing on X, Y, Z axes (pins 7, 6, 10).
- **Power**: 5V supply for motors and Arduino.
- **Pen Mechanism**: Simple pen lift on Z-axis.
- **Physical Limits**: Configured for ~156mm x 156mm drawing area (adjustable in code).
- **Connections**:
  - X Motor: Pins 5,4,3,2
  - Y Motor: Pins A0-A3 (14-17)
  - Z Motor: Pins 13,12,9,8
  - Serial: USB to PC.

**Note**: Motor directions may need inversion based on wiring (handled in firmware).

## Software Requirements
- **Arduino IDE**: For uploading the firmware.
- **Python 3.8+**: With libraries:
  - `tkinter` (built-in)
  - `serial` (pip install pyserial)
  - `numpy`, `scipy`, `Pillow`, `scikit-image` (pip install numpy scipy pillow scikit-image)
  - For calibration/conversion: Custom utils in `calibration/conversion_utils.py` (included).
- Tested on Windows; should work on macOS/Linux with serial port adjustments.

## Installation
1. **Clone the Repository**:
   ```
   git clone https://github.com/diegobonilla98/Drawing-Machine
   cd diy-pen-plotter
   ```

2. **Upload Arduino Firmware**:
   - Open `sketch_jul24a.ino` in Arduino IDE.
   - Select your board and port.
   - Upload. The Arduino will print "Ready" on serial.

3. **Install Python Dependencies**:
   ```
   pip install pyserial numpy scipy pillow scikit-image
   ```

4. **Configure Serial Port**:
   - In all Python scripts, update `SERIAL_PORT = 'COM11'` to your Arduino's port (e.g., `/dev/ttyUSB0` on Linux).

## Usage

### 1. Calibration (`extract_points.py`)
Calibrate steps to mm for accurate drawing.
- Run: `python extract_points.py`
- GUI: Jog motors to positions, input measured mm (using a ruler), save points.
- Output: CSV file (e.g., `calibration_points_YYYYMMDD_HHMMSS.csv`).
- Use this data to fit models in `calibration/conversion_utils.py` (e.g., linear regression for mm_to_steps_X/Y).
- **Tip**: Collect 20+ points across the drawing area for accuracy.

### 2. Manual Control (`basic_controller.py`)
Test motor movements.
- Run: `python basic_controller.py`
- GUI: Set step size, move X/Y/Z axes forward/backward.
- Useful for initial setup and homing verification.

### 3. Image to G-code Conversion (`image2gcode.py`)
Convert images to plotter-ready G-code.
- Run: `python image2gcode.py`
- GUI:
  - Load image.
  - Adjust blur (denoise), threshold (binarize), invert colors.
  - Preview processed skeleton.
  - Generate and save G-code (coordinates in steps via calibration).
- **Processing**:
  - Grayscale → Blur → Threshold → Skeletonize → Extract strokes → Optimize order → G-code.
- Output: `.gcode` file with headers, paths, and end commands.
- **Save Processed Image**: Export the skeletonized image for verification.

### 4. G-code Visualization (`gcode_visualizer.py`)
Preview G-code paths.
- Run: `python gcode_visualizer.py`
- GUI: Load `.gcode` file.
- Displays 2D drawing paths (pen down only, Z ≤ 0).

### 5. Sending G-code (`gcode_sender.py`)
Send G-code to the plotter.
- Run: `python gcode_sender.py`
- GUI:
  - Load G-code file (displays lines).
  - Test connection, home axes (G28), send manual commands.
  - Start sending: Progress bar, estimated time, stop button.
  - Debug mode for verbose logging.
- **Features**: Dynamic timeouts for long moves, time estimation based on steps.
- **Homing**: Uses limit switches; Z backs off 750 steps to paper position.

## Project Workflow
1. Assemble hardware and upload firmware.
2. Calibrate with `extract_points.py` and update conversion utils.
3. Convert image to G-code with `image2gcode.py`.
4. Preview with `gcode_visualizer.py`.
5. Send to plotter with `gcode_sender.py`.

## Notes and Limitations
- **Speed**: Step delay is 2000μs (adjust in Arduino for faster/slower).
- **Accuracy**: Calibration is crucial; non-linear if belts/gears are uneven.
- **G-code Support**: Limited to G0/G1/G21/G28/G90/G91/M84. Coordinates are steps (calibrated).
- **Z-axis**: Simple pen up/down (Z100 up, Z0 down).
- **Error Handling**: Scripts include status messages and warnings.
- **Improvements**: Add feed rates (F), better optimization, or SVG support.

## Contributing
Pull requests welcome! For major changes, open an issue first.

## License
MIT License.

---

Built with ❤️ by Diego Bonilla. Inspired by open-source plotter designs.
