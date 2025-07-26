import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from scipy import ndimage
from PIL import Image, ImageTk
import datetime
import os
import sys
from skimage.morphology import skeletonize

# Add calibration directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'calibration'))
from conversion_utils import mm_to_steps_X, mm_to_steps_Y

# Constants and Calibration Data
PLOTTER_PHYSICAL_LIMIT_X_MM = 156.0
PLOTTER_PHYSICAL_LIMIT_Y_MM = 156.0
PEN_UP_COMMAND = "G0 Z100.0"
PEN_DOWN_COMMAND = "G0 Z0.0"

# Core G-code Conversion Logic
class StrokeProcessor:
    """
    Handles the conversion of a binary skeleton image to a list of strokes,
    and then converts those strokes into an optimized G-code path.
    """
    def __init__(self, skeleton_image, plotter_dims):
        self.skeleton = skeleton_image.astype(np.uint8)
        self.plotter_w, self.plotter_h = plotter_dims
        self.img_h, self.img_w = self.skeleton.shape
        self.scale = 0
        if self.img_w > 0 and self.img_h > 0:
            if self.img_w / self.plotter_w > self.img_h / self.plotter_h:
                self.scale = self.plotter_w / self.img_w
            else:
                self.scale = self.plotter_h / self.img_h

    def _map_to_plotter_coords(self, point):
        """Maps a pixel coordinate (x, y) to plotter step coordinates."""
        px_x, px_y = point
        plotter_x_mm = px_x * self.scale
        plotter_y_mm = self.plotter_h - (px_y * self.scale)
        return mm_to_steps_X(plotter_x_mm), mm_to_steps_Y(plotter_y_mm)

    def _extract_strokes(self):
        """
        Extracts paths (strokes) from the skeleton image.
        This is a more robust method that correctly handles junctions and loops.
        """
        if not self.skeleton.any():
            return []

        # Use convolution to find endpoints (1 neighbor) and junctions (>2 neighbors)
        kernel = np.array([[1, 1, 1], [1, 10, 1], [1, 1, 1]], dtype=np.uint8)
        neighbors = ndimage.convolve(self.skeleton, kernel, mode='constant', cval=0)
        
        # Get all pixel coordinates from the skeleton
        pixels = np.argwhere(self.skeleton > 0)
        # argwhere gives (row, col) -> (y, x), so we flip to (x, y)
        pixels = pixels[:, ::-1]
        pixel_set = {tuple(p) for p in pixels}
        
        strokes = []
        visited = set()

        for p_start in pixels:
            p_start = tuple(p_start)
            if p_start in visited:
                continue

            # A point is a start of a path if it's an endpoint or a junction
            neighbor_count = neighbors[p_start[1], p_start[0]]
            if neighbor_count != 12 and neighbor_count != 11: # Not a middle-of-line point
                
                # Explore all directions from this junction/endpoint
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        if dr == 0 and dc == 0:
                            continue
                        
                        p_curr = (p_start[0] + dc, p_start[1] + dr)
                        if p_curr not in pixel_set or (p_start, p_curr) in visited:
                            continue

                        # Trace a new path
                        path = [p_start, p_curr]
                        visited.add((p_start, p_curr))
                        visited.add((p_curr, p_start))

                        while neighbors[path[-1][1], path[-1][0]] == 12: # 10 + 2 neighbors
                            p_prev = path[-2]
                            p_last = path[-1]
                            found_next = False
                            for dr_n in [-1, 0, 1]:
                                for dc_n in [-1, 0, 1]:
                                    if dr_n == 0 and dc_n == 0: continue
                                    p_next = (p_last[0] + dc_n, p_last[1] + dr_n)
                                    if p_next in pixel_set and p_next != p_prev:
                                        path.append(p_next)
                                        visited.add((p_last, p_next))
                                        visited.add((p_next, p_last))
                                        found_next = True
                                        break
                                if found_next: break
                            if not found_next: break
                        strokes.append(path)
        
        # Handle simple closed loops that have no junctions/endpoints
        remaining_pixels = pixel_set - {p for s in strokes for p in s}
        while remaining_pixels:
            p_start = remaining_pixels.pop()
            path = [p_start]
            p_curr = p_start
            while True:
                found_next = False
                for dr in [-1, 0, 1]:
                    for dc in [-1, 0, 1]:
                        p_next = (p_curr[0] + dc, p_curr[1] + dr)
                        if p_next in remaining_pixels:
                            path.append(p_next)
                            remaining_pixels.remove(p_next)
                            p_curr = p_next
                            found_next = True
                            break
                    if found_next: break
                if not found_next:
                    break
            strokes.append(path)

        return strokes

    def _optimize_and_convert_to_gcode(self, strokes):
        """
        Takes a list of strokes, optimizes their drawing order, and converts
        them to G-code commands.
        """
        if not strokes:
            return []

        gcode_lines = []
        current_pos = (0, 0) # Start at plotter origin (in steps)
        
        remaining_strokes = list(strokes)

        while remaining_strokes:
            # Find the stroke with an endpoint closest to the current pen position
            best_stroke_idx = -1
            min_dist = float('inf')
            
            for i, stroke in enumerate(remaining_strokes):
                # Calculate distance to both ends of the stroke
                start_pos_steps = self._map_to_plotter_coords(stroke[0])
                end_pos_steps = self._map_to_plotter_coords(stroke[-1])
                
                dist_to_start = np.hypot(start_pos_steps[0] - current_pos[0], start_pos_steps[1] - current_pos[1])
                dist_to_end = np.hypot(end_pos_steps[0] - current_pos[0], end_pos_steps[1] - current_pos[1])

                if dist_to_start < min_dist:
                    min_dist = dist_to_start
                    best_stroke_idx = i
                    
                if dist_to_end < min_dist:
                    min_dist = dist_to_end
                    best_stroke_idx = i

            # Get the best stroke and remove it from the list
            best_stroke = remaining_strokes.pop(best_stroke_idx)
            
            # Check if we should draw it in reverse
            start_pos = self._map_to_plotter_coords(best_stroke[0])
            end_pos = self._map_to_plotter_coords(best_stroke[-1])
            if np.hypot(end_pos[0] - current_pos[0], end_pos[1] - current_pos[1]) < np.hypot(start_pos[0] - current_pos[0], start_pos[1] - current_pos[1]):
                best_stroke.reverse()
                start_pos = self._map_to_plotter_coords(best_stroke[0])

            # Generate G-code for this stroke
            gcode_lines.append(PEN_UP_COMMAND)
            gcode_lines.append(f"G0 X{start_pos[0]} Y{start_pos[1]}")
            gcode_lines.append(PEN_DOWN_COMMAND)

            for point in best_stroke:
                x, y = self._map_to_plotter_coords(point)
                gcode_lines.append(f"G1 X{x} Y{y}")
            
            # Update current position to the end of the last drawn line
            current_pos = self._map_to_plotter_coords(best_stroke[-1])
            
        return gcode_lines

    def convert(self):
        """Main method to run the full conversion pipeline."""
        strokes = self._extract_strokes()
        gcode = self._optimize_and_convert_to_gcode(strokes)
        return gcode

# Main Tkinter Application
class Image2GcodeApp(tk.Tk):
    """Main application class for the Image to G-code converter."""
    
    def __init__(self):
        super().__init__()
        self.title("Image to G-code Converter")
        self.geometry("1200x800")
        self.minsize(800, 600)
        
        # Configure main window style
        self.configure(bg='#f0f0f0')
        
        # Application state
        self.original_pil_image = None
        self.processed_skeleton = None
        self.source_filename = "unknown.png"

        # Configure grid weights for responsive layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._create_ui()

    def _create_ui(self):
        """Create the user interface components."""
        self._create_control_panel()
        self._create_image_display()
        self._create_status_bar()

    def _create_control_panel(self):
        """Create the control panel with buttons and sliders."""
        # Main control frame with improved styling
        control_frame = ttk.Frame(self, padding="15")
        control_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        control_frame.grid_columnconfigure(4, weight=1)

        # File operations section
        file_frame = ttk.LabelFrame(control_frame, text="File Operations", padding="10")
        file_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        
        ttk.Button(
            file_frame, 
            text="📁 Load Image", 
            command=self.load_image,
            style="Accent.TButton"
        ).pack(side="left", padx=5)
        
        self.invert_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            file_frame, 
            text="🔄 Invert Colors", 
            variable=self.invert_var, 
            command=self.on_controls_change
        ).pack(side="left", padx=15)

        # --- Add Save Processed Image Button ---
        ttk.Button(
            file_frame,
            text="💾 Save Processed Image",
            command=self.save_processed_image,
            style="Accent.TButton"
        ).pack(side="left", padx=5)
        # --- End addition ---

        # Processing parameters section
        params_frame = ttk.LabelFrame(control_frame, text="Processing Parameters", padding="10")
        params_frame.grid(row=0, column=2, columnspan=3, sticky="ew", padx=5, pady=5)
        params_frame.grid_columnconfigure(1, weight=1)
        params_frame.grid_columnconfigure(3, weight=1)
        
        # Blur control
        ttk.Label(params_frame, text="Blur Intensity:").grid(row=0, column=0, padx=5, sticky="w")
        self.blur_var = tk.DoubleVar(value=1.0)
        self.blur_slider = ttk.Scale(
            params_frame, 
            from_=0, 
            to=5, 
            orient="horizontal", 
            variable=self.blur_var, 
            command=self.on_controls_change
        )
        self.blur_slider.grid(row=0, column=1, sticky="ew", padx=5)
        self.blur_label = ttk.Label(params_frame, text="1.0", width=6, anchor="center")
        self.blur_label.grid(row=0, column=2, padx=5)
        
        # Threshold control
        ttk.Label(params_frame, text="Threshold:").grid(row=1, column=0, padx=5, sticky="w")
        self.threshold_var = tk.IntVar(value=128)
        self.threshold_slider = ttk.Scale(
            params_frame, 
            from_=1, 
            to=254, 
            orient="horizontal", 
            variable=self.threshold_var, 
            command=self.on_controls_change
        )
        self.threshold_slider.grid(row=1, column=1, sticky="ew", padx=5)
        self.threshold_label = ttk.Label(params_frame, text="128", width=6, anchor="center")
        self.threshold_label.grid(row=1, column=2, padx=5)

        # Generate button
        generate_frame = ttk.Frame(control_frame)
        generate_frame.grid(row=0, column=5, padx=10, pady=5)
        
        ttk.Button(
            generate_frame, 
            text="⚙️ Generate G-code", 
            command=self.save_gcode,
            style="Accent.TButton"
        ).pack(pady=10, ipadx=10, ipady=5)

    def _create_image_display(self):
        """Create the image display area."""
        # Main image frame with improved layout
        image_frame = ttk.Frame(self, padding="10")
        image_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        image_frame.grid_rowconfigure(1, weight=1)
        image_frame.grid_columnconfigure(0, weight=1)
        image_frame.grid_columnconfigure(1, weight=1)
        
        # Image labels with better styling
        original_label = ttk.Label(
            image_frame, 
            text="📷 Original Image", 
            font=("Segoe UI", 14, "bold"),
            foreground="#2c3e50"
        )
        original_label.grid(row=0, column=0, pady=10)
        
        processed_label = ttk.Label(
            image_frame, 
            text="🎯 Processed Preview", 
            font=("Segoe UI", 14, "bold"),
            foreground="#2c3e50"
        )
        processed_label.grid(row=0, column=1, pady=10)

        # Image display frames with borders
        self.image_label_orig = ttk.Label(
            image_frame, 
            background="#ffffff", 
            anchor="center",
            relief="solid",
            borderwidth=1,
            text="No image loaded\n\nClick 'Load Image' to get started",
            font=("Segoe UI", 12),
            foreground="#7f8c8d"
        )
        self.image_label_orig.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        self.image_label_proc = ttk.Label(
            image_frame, 
            background="#2c3e50", 
            anchor="center",
            relief="solid",
            borderwidth=1,
            text="Processed image will appear here\n\nAfter loading and processing",
            font=("Segoe UI", 12),
            foreground="#ecf0f1"
        )
        self.image_label_proc.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)

    def _create_status_bar(self):
        """Create the status bar at the bottom."""
        status_frame = ttk.Frame(self)
        status_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        
        self.status_var = tk.StringVar(value="🟢 Ready - Load an image to begin")
        status_label = ttk.Label(
            status_frame, 
            textvariable=self.status_var, 
            relief="sunken", 
            anchor="w", 
            padding=10,
            font=("Segoe UI", 10),
            background="#ecf0f1"
        )
        status_label.pack(fill="x")

    def load_image(self):
        """Load an image file for processing."""
        filepath = filedialog.askopenfilename(
            title="Select an Image", 
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.bmp *.tiff *.gif"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("All files", "*.*")
            ]
        )
        if not filepath:
            return
        try:
            self.source_filename = filepath.split('/')[-1].split('\\')[-1]  # Handle both path separators
            self.original_pil_image = Image.open(filepath)
            self.status_var.set(f"✅ Loaded: {self.source_filename}")
            self._display_image(self.original_pil_image, self.image_label_orig)
            self.process_and_preview()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image:\n{str(e)}")
            self.status_var.set("❌ Failed to load image")

    def on_controls_change(self, *args):
        """Handle changes to control sliders and checkboxes."""
        self.blur_label.config(text=f"{self.blur_var.get():.1f}")
        self.threshold_label.config(text=str(self.threshold_var.get()))
        if self.original_pil_image:
            self.process_and_preview()

    def process_and_preview(self):
        """Process the loaded image and update the preview."""
        if not self.original_pil_image:
            return
            
        self.status_var.set("⚙️ Processing image...")
        self.update_idletasks()

        try:
            # Convert to grayscale numpy array
            image_gray = self.original_pil_image.convert("L")
            if self.invert_var.get():
                image_gray = Image.fromarray(np.invert(np.array(image_gray)))
            image_np = np.array(image_gray, dtype=float)

            # Apply Gaussian blur for denoising
            sigma = self.blur_var.get()
            blurred_image = ndimage.gaussian_filter(image_np, sigma=sigma)

            # Binarize the image using the threshold
            threshold = self.threshold_var.get()
            binary_image = blurred_image < threshold

            # Skeletonize to get 1-pixel wide lines
            self.processed_skeleton = skeletonize(binary_image)
            
            # Create a preview image from the skeleton
            preview_img = Image.fromarray((self.processed_skeleton * 255).astype(np.uint8)).convert("RGB")
            preview_img = Image.fromarray(np.invert(np.array(preview_img)))  # Black on white

            self._display_image(preview_img, self.image_label_proc)
            
            # Count detected lines for status
            line_count = np.sum(self.processed_skeleton)
            self.status_var.set(f"🎯 Processing complete - {line_count} pixels detected")
            
        except Exception as e:
            self.status_var.set(f"❌ Processing error: {str(e)}")
            messagebox.showerror("Processing Error", f"Failed to process image:\n{str(e)}")

    def save_gcode(self):
        """Generate and save G-code from the processed image."""
        if self.processed_skeleton is None or not self.processed_skeleton.any():
            messagebox.showwarning(
                "No Lines Detected", 
                "No lines were detected with the current settings.\n\n"
                "Try adjusting the blur and threshold parameters."
            )
            return

        # Get save location
        default_name = self.source_filename.rsplit('.', 1)[0] + ".gcode"
        save_path = filedialog.asksaveasfilename(
            title="Save G-code File", 
            defaultextension=".gcode", 
            filetypes=[
                ("G-code files", "*.gcode *.nc"),
                ("Text files", "*.txt"),
                ("All files", "*.*")
            ], 
            initialfile=default_name
        )
        if not save_path:
            return
            
        self.status_var.set("⚙️ Generating G-code... Please wait")
        self.update_idletasks()

        try:
            # Convert skeleton to G-code using the new processor
            processor = StrokeProcessor(
                self.processed_skeleton, 
                (PLOTTER_PHYSICAL_LIMIT_X_MM, PLOTTER_PHYSICAL_LIMIT_Y_MM)
            )
            gcode_lines = processor.convert()

            # Write G-code file with proper headers
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write("; G-code generated by Image2Gcode App\n")
                f.write(f"; Source: {self.source_filename}, Date: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
                f.write(f"; Settings: Invert={self.invert_var.get()}, Blur={self.blur_var.get():.1f}, Threshold={self.threshold_var.get()}\n")
                f.write("; NOTE: Coordinates are in STEPS, not millimeters (calibrated for this plotter)\n")
                f.write("G21 ; Use millimeters (ignored by Arduino - coordinates are steps)\n")
                f.write("G90 ; Use absolute positioning\n")
                # f.write("G28 X Y ; Home axes\n")
                f.write(f"{PEN_UP_COMMAND}\n")
                f.write("\n; --- Start Drawing ---\n")
                
                f.write("\n".join(gcode_lines))
                
                f.write("\n\n; --- End Drawing ---\n")
                f.write(f"{PEN_UP_COMMAND}\n")
                f.write("G0 X0 Y0 ; Return to origin\n")
                f.write("M84 ; Disable motors\n")

            # Success feedback
            filename = save_path.split('/')[-1].split('\\')[-1]
            self.status_var.set(f"✅ G-code saved: {filename} ({len(gcode_lines)} commands)")
            messagebox.showinfo("Success", f"G-code file generated successfully!\n\nSaved as: {filename}")
            
        except Exception as e:
            error_msg = f"Failed to generate G-code:\n{str(e)}"
            self.status_var.set("❌ G-code generation failed")
            messagebox.showerror("Error", error_msg)

    def save_processed_image(self):
        """Save the postprocessed (skeletonized) image as PNG."""
        if self.processed_skeleton is None or not self.processed_skeleton.any():
            messagebox.showwarning(
                "No Processed Image",
                "No processed image to save. Please load and process an image first."
            )
            return

        default_name = self.source_filename.rsplit('.', 1)[0] + "_processed.png"
        save_path = filedialog.asksaveasfilename(
            title="Save Processed Image",
            defaultextension=".png",
            filetypes=[
                ("PNG files", "*.png"),
                ("All files", "*.*")
            ],
            initialfile=default_name
        )
        if not save_path:
            return

        try:
            # Convert skeleton to image (black lines on white)
            img = Image.fromarray((self.processed_skeleton * 255).astype(np.uint8)).convert("L")
            img = Image.fromarray(np.invert(np.array(img)))  # Black on white
            img.save(save_path)
            filename = save_path.split('/')[-1].split('\\')[-1]
            self.status_var.set(f"✅ Processed image saved: {filename}")
            messagebox.showinfo("Success", f"Processed image saved as: {filename}")
        except Exception as e:
            self.status_var.set("❌ Failed to save processed image")
            messagebox.showerror("Error", f"Failed to save processed image:\n{str(e)}")

    def _display_image(self, pil_image, label_widget):
        """Display an image in the specified label widget with proper scaling."""
        # Get widget dimensions
        w, h = label_widget.winfo_width(), label_widget.winfo_height()
        if w < 50 or h < 50:
            w, h = 450, 600
            
        # Create a copy and resize to fit
        display_image = pil_image.copy()
        display_image.thumbnail((w - 20, h - 20), Image.Resampling.LANCZOS)
        
        # Convert to PhotoImage and display
        photo_image = ImageTk.PhotoImage(display_image)
        label_widget.image = photo_image  # Keep a reference
        label_widget.config(image=photo_image, text="")


if __name__ == "__main__":
    # Configure ttk styles for better appearance
    app = Image2GcodeApp()
    
    # Set up custom styles
    style = ttk.Style()
    style.theme_use('clam')  # Use a modern theme
    
    # Configure custom button style
    style.configure(
        "Accent.TButton",
        background="#3498db",
        foreground="white",
        font=("Segoe UI", 10, "bold")
    )
    
    app.mainloop()
