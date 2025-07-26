import tkinter as tk
from tkinter import filedialog, Canvas
import re

# --- Configuration ---
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
CANVAS_PADDING = 20
PEN_DOWN_Z_THRESHOLD = 0  # Z values <= this are considered "pen down"
BACKGROUND_COLOR = "#282c34"
LINE_COLOR = "#61afef"
LINE_WIDTH = 2

class GcodeVisualizer:
    def __init__(self, root):
        self.root = root
        self.root.title("2D G-code Visualizer")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        self.canvas = Canvas(
            root,
            bg=BACKGROUND_COLOR,
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.btn_open = tk.Button(
            root,
            text="Open G-code File",
            command=self.load_file
        )
        self.btn_open.pack(pady=10)

        self.info_label = tk.Label(root, text="Load a G-code file to begin.")
        self.info_label.pack(pady=5)

    def load_file(self):
        """Opens a file dialog to select a G-code file and starts visualization."""
        filepath = filedialog.askopenfilename(
            title="Select a G-code file",
            filetypes=(("G-code files", "*.gcode *.gc *.gco *.nc"), ("All files", "*.*"))
        )
        if not filepath:
            return

        self.info_label.config(text=f"Visualizing: {filepath.split('/')[-1]}")
        self.root.update() # Force UI update before processing

        try:
            commands, bounds = self.parse_gcode(filepath)
            if not commands:
                self.info_label.config(text="No valid G0/G1 commands found in file.")
                return
            self.draw_gcode(commands, bounds)
        except Exception as e:
            self.info_label.config(text=f"Error processing file: {e}")

    def parse_gcode(self, filepath):
        """Parses a G-code file to extract movement commands and calculate bounds."""
        commands = []
        bounds = {'min_x': float('inf'), 'max_x': float('-inf'),
                  'min_y': float('inf'), 'max_y': float('-inf')}
        
        # Regex to find G0/G1 commands and extract X, Y, Z values
        move_command_re = re.compile(r"G[01](?:\s+X([-\d.]+))?(?:\s+Y([-\d.]+))?(?:\s+Z([-\d.]+))?")

        with open(filepath, 'r') as f:
            for line in f:
                match = move_command_re.search(line.upper())
                if match:
                    x, y, z = match.groups()
                    cmd = {}
                    if x is not None: cmd['x'] = float(x)
                    if y is not None: cmd['y'] = float(y)
                    if z is not None: cmd['z'] = float(z)
                    
                    if 'x' in cmd and 'y' in cmd:
                        bounds['min_x'] = min(bounds['min_x'], cmd['x'])
                        bounds['max_x'] = max(bounds['max_x'], cmd['x'])
                        bounds['min_y'] = min(bounds['min_y'], cmd['y'])
                        bounds['max_y'] = max(bounds['max_y'], cmd['y'])
                    
                    commands.append(cmd)
        
        return commands, bounds

    def draw_gcode(self, commands, bounds):
        """Scales and draws the parsed G-code commands onto the canvas."""
        self.canvas.delete("all")

        # Get canvas dimensions for scaling
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        drawable_width = canvas_width - 2 * CANVAS_PADDING
        drawable_height = canvas_height - 2 * CANVAS_PADDING

        gcode_width = bounds['max_x'] - bounds['min_x']
        gcode_height = bounds['max_y'] - bounds['min_y']

        if gcode_width == 0 or gcode_height == 0:
            self.info_label.config(text="Cannot visualize: G-code has zero width or height.")
            return

        # Calculate scale factor to fit drawing while maintaining aspect ratio
        scale_x = drawable_width / gcode_width
        scale_y = drawable_height / gcode_height
        scale = min(scale_x, scale_y)

        # Function to transform G-code coordinates to canvas coordinates
        def transform(x, y):
            # Invert Y-axis because canvas (0,0) is top-left
            tx = CANVAS_PADDING + (x - bounds['min_x']) * scale
            ty = CANVAS_PADDING + (bounds['max_y'] - y) * scale
            return tx, ty

        current_pos = {'x': 0, 'y': 0, 'z': 1} # Start with pen up
        
        for cmd in commands:
            last_pos = current_pos.copy()
            current_pos.update(cmd)

            if 'x' in current_pos and 'y' in last_pos:
                x1, y1 = transform(last_pos['x'], last_pos['y'])
                x2, y2 = transform(current_pos['x'], current_pos['y'])

                # Draw line only if Z is at or below the threshold (pen is down)
                if current_pos['z'] <= PEN_DOWN_Z_THRESHOLD:
                    self.canvas.create_line(x1, y1, x2, y2, fill=LINE_COLOR, width=LINE_WIDTH)

if __name__ == "__main__":
    main_window = tk.Tk()
    app = GcodeVisualizer(main_window)
    main_window.mainloop()