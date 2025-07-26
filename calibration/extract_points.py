import tkinter as tk
from tkinter import ttk, messagebox
import serial
import time
import csv
from datetime import datetime

# Serial port configuration - change this to your Arduino's port
SERIAL_PORT = 'COM11'  # For Windows, e.g., 'COM3'; for Linux/Mac, e.g., '/dev/ttyUSB0'
BAUD_RATE = 9600

class CalibrationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Pen Plotter Calibration Dashboard")
        self.root.geometry("800x600")
        self.root.configure(bg="#2b2b2b")

        # Status Label variable (move this up!)
        self.status_var = tk.StringVar(value="Ready")

        # Serial connection
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)  # Wait for Arduino to initialize
            self.send_command("G91")  # Set to relative mode
            messagebox.showinfo("Connection", "Connected to Arduino successfully!")
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            self.root.quit()

        # Current steps tracking (starting at 0,0,0)
        self.current_steps = {'X': 0, 'Y': 0, 'Z': 0}

        # List to hold calibration points
        self.points = []

        # Style configuration for dark theme
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", font=("Helvetica", 10), background="#2b2b2b", foreground="#ffffff")
        style.configure("TButton", font=("Helvetica", 10), padding=10, background="#007bff", foreground="#ffffff")
        style.map("TButton", background=[('active', '#0056ba')])
        style.configure("TEntry", font=("Helvetica", 10), foreground="#ffffff", fieldbackground="#3a3b3c", insertbackground="#ffffff")
        style.configure("Treeview", font=("Helvetica", 10), background="#2b2b2b", fieldbackground="#2b2b2b", foreground="#ffffff")
        style.configure("Treeview.Heading", font=("Helvetica", 10, "bold"), background="#3a3b3c", foreground="#ffffff")
        style.map("Treeview", background=[('selected', '#007bff')], foreground=[('selected', '#ffffff')])
        style.configure("Vertical.TScrollbar", background="#3a3b3c", troughcolor="#2b2b2b", arrowcolor="#ffffff")

        # Main frame
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Control Panel
        control_frame = ttk.LabelFrame(main_frame, text="Motor Controls", padding=10)
        control_frame.grid(row=0, column=0, sticky="ew", pady=5)

        # Step size slider
        ttk.Label(control_frame, text="Step Size:").grid(row=0, column=0, padx=5, pady=5)
        self.step_size = tk.IntVar(value=100)
        step_slider = ttk.Scale(control_frame, from_=100, to=1000, variable=self.step_size, orient="horizontal", length=150)
        step_slider.grid(row=0, column=1, padx=5, pady=5)
        self.step_size_label = ttk.Label(control_frame, text="100")
        self.step_size_label.grid(row=0, column=2, padx=5, pady=5)
        step_slider.configure(command=lambda val: self.step_size_label.configure(text=f"{int(float(val))}"))

        # Current positions
        self.curX_var = tk.StringVar(value="Current X: 0")
        ttk.Label(control_frame, textvariable=self.curX_var).grid(row=0, column=3, padx=10, pady=5)
        self.curY_var = tk.StringVar(value="Current Y: 0")
        ttk.Label(control_frame, textvariable=self.curY_var).grid(row=0, column=4, padx=10, pady=5)
        self.curZ_var = tk.StringVar(value="Current Z: 0")
        ttk.Label(control_frame, textvariable=self.curZ_var).grid(row=0, column=5, padx=10, pady=5)

        # Axis controls
        axes = [
            ("X Axis (+X right, -X left)", 'X', 1),
            ("Y Axis (+Y towards, -Y away)", 'Y', 3),
            ("Z Axis (Pen Lift)", 'Z', 5)
        ]
        for label, axis, row in axes:
            ttk.Label(control_frame, text=label).grid(row=row, column=0, columnspan=2, pady=5)
            forward_text = "Forward" if axis != 'Z' else "Up"
            backward_text = "Backward" if axis != 'Z' else "Down"
            ttk.Button(control_frame, text=forward_text, command=lambda a=axis: self.move_motor(a, self.step_size.get())).grid(row=row+1, column=0, padx=5)
            ttk.Button(control_frame, text=backward_text, command=lambda a=axis: self.move_motor(a, -self.step_size.get())).grid(row=row+1, column=1, padx=5)

        # Coordinate Input
        coord_frame = ttk.LabelFrame(main_frame, text="Calibration Point (mm)", padding=10)
        coord_frame.grid(row=0, column=1, sticky="ew", pady=5, padx=10)

        ttk.Label(coord_frame, text="X (mm):").grid(row=0, column=0, padx=5, pady=5)
        self.mmX = tk.DoubleVar(value=0.0)
        mmX_slider = ttk.Scale(coord_frame, from_=0, to=156, variable=self.mmX, orient="horizontal", length=200)
        mmX_slider.grid(row=0, column=1, padx=5, pady=5)
        self.mmX_label = ttk.Label(coord_frame, text="0.0")
        self.mmX_label.grid(row=0, column=2, padx=5, pady=5)
        mmX_slider.configure(command=lambda val: self.mmX_label.configure(text=f"{float(val):.1f}"))

        ttk.Label(coord_frame, text="Y (mm):").grid(row=1, column=0, padx=5, pady=5)
        self.mmY = tk.DoubleVar(value=0.0)
        mmY_slider = ttk.Scale(coord_frame, from_=0, to=156, variable=self.mmY, orient="horizontal", length=200)
        mmY_slider.grid(row=1, column=1, padx=5, pady=5)
        self.mmY_label = ttk.Label(coord_frame, text="0.0")
        self.mmY_label.grid(row=1, column=2, padx=5, pady=5)
        mmY_slider.configure(command=lambda val: self.mmY_label.configure(text=f"{float(val):.1f}"))

        ttk.Button(coord_frame, text="Save Point", command=self.save_point).grid(row=2, column=0, columnspan=2, pady=10)

        # Calibration Table
        table_frame = ttk.LabelFrame(main_frame, text="Calibration Points", padding=10)
        table_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=10)
        main_frame.rowconfigure(1, weight=1)

        self.tree = ttk.Treeview(table_frame, columns=('StepX', 'StepY', 'mmX', 'mmY'), show='headings')
        self.tree.heading('StepX', text='Step X')
        self.tree.heading('StepY', text='Step Y')
        self.tree.heading('mmX', text='mm X')
        self.tree.heading('mmY', text='mm Y')
        self.tree.column('StepX', width=100, anchor='center')
        self.tree.column('StepY', width=100, anchor='center')
        self.tree.column('mmX', width=100, anchor='center')
        self.tree.column('mmY', width=100, anchor='center')
        self.tree.grid(row=0, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        # Scrollbar for table
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview, style="Vertical.TScrollbar")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Additional functionality: Delete selected point
        ttk.Button(table_frame, text="Delete Selected", command=self.delete_selected).grid(row=1, column=0, pady=5)

        # Action Buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.grid(row=2, column=0, columnspan=2, pady=10)

        ttk.Button(action_frame, text="Reset Positions (0,0)", command=self.reset_positions).grid(row=0, column=0, padx=5)
        ttk.Button(action_frame, text="Finish and Save CSV", command=self.finish).grid(row=0, column=1, padx=5)
        ttk.Button(action_frame, text="Quit", command=self.quit_app).grid(row=0, column=2, padx=5)

        # Status Label
        ttk.Label(main_frame, textvariable=self.status_var, foreground="#00ff00").grid(row=3, column=0, columnspan=2, pady=5)

    def send_command(self, cmd):
        self.ser.write((cmd + '\n').encode())
        response = self.ser.readline().decode().strip()
        self.status_var.set(f"Command: {cmd}, Response: {response}")
        return response

    def move_motor(self, axis, steps):
        cmd = f"G1 {axis}{steps}"
        response = self.send_command(cmd)
        if response == "OK":
            self.current_steps[axis] += steps
            self.curX_var.set(f"Current X: {self.current_steps['X']}")
            self.curY_var.set(f"Current Y: {self.current_steps['Y']}")
            self.curZ_var.set(f"Current Z: {self.current_steps['Z']}")
            self.status_var.set(f"Moved {axis} by {steps} steps. Current: ({self.current_steps['X']}, {self.current_steps['Y']}, {self.current_steps['Z']})")
        else:
            messagebox.showwarning("Warning", f"Unexpected response: {response}")

    def save_point(self):
        try:
            mmx = self.mmX.get()
            mmy = self.mmY.get()
        except:
            messagebox.showerror("Error", "Invalid mm values")
            return

        sx = self.current_steps['X']
        sy = self.current_steps['Y']
        self.points.append((sx, sy, mmx, mmy))
        self.tree.insert('', 'end', values=(sx, sy, mmx, mmy))
        self.status_var.set(f"Saved point: Steps ({sx}, {sy}), mm ({mmx}, {mmy})")
        self.mmX.set(0.0)
        self.mmY.set(0.0)

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "No point selected")
            return
        for item in selected:
            index = self.tree.index(item)
            del self.points[index]
            self.tree.delete(item)
        self.status_var.set("Selected point(s) deleted")

    def reset_positions(self):
        self.current_steps['X'] = 0
        self.current_steps['Y'] = 0
        self.current_steps['Z'] = 0
        self.curX_var.set(f"Current X: 0")
        self.curY_var.set(f"Current Y: 0")
        self.curZ_var.set(f"Current Z: 0")
        self.status_var.set("Positions reset to (0,0,0) in software. Note: This does not move the motors.")
        messagebox.showinfo("Reset", "Positions reset to (0,0,0) in software.")

    def finish(self):
        if not self.points:
            messagebox.showwarning("Warning", "No points to save")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'calibration_points_{timestamp}.csv'
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['stepX', 'stepY', 'mmX', 'mmY'])
            writer.writerows(self.points)

        messagebox.showinfo("Saved", f"Calibration points saved to {filename}")
        self.status_var.set(f"Saved to {filename}")

    def quit_app(self):
        self.ser.close()
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = CalibrationApp(root)
    root.mainloop()
