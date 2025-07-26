import tkinter as tk
from tkinter import ttk, messagebox
import serial
import time

SERIAL_PORT = 'COM11'
BAUD_RATE = 9600

class MotorControlApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🖊️ Pen Plotter Motor Control")
        self.root.geometry("350x350")
        self.root.configure(bg="#222831")

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", background="#222831", foreground="#eeeeee", font=("Segoe UI", 11))
        style.configure("TButton", font=("Segoe UI", 10), padding=6)
        style.configure("TEntry", font=("Segoe UI", 10))

        # Serial connection
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            time.sleep(2)
            self.send_command("G91")
            self.status_var = tk.StringVar(value="✅ Connected to Arduino")
        except Exception as e:
            self.status_var = tk.StringVar(value=f"❌ Connection Error: {e}")
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            self.root.quit()

        # Step size frame
        step_frame = ttk.LabelFrame(root, text="Step Size", padding=(10, 5))
        step_frame.grid(row=0, column=0, columnspan=2, padx=15, pady=10, sticky="ew")
        self.step_size = tk.IntVar(value=100)
        ttk.Label(step_frame, text="Steps:").grid(row=0, column=0, padx=5, pady=5)
        ttk.Entry(step_frame, textvariable=self.step_size, width=8).grid(row=0, column=1, padx=5, pady=5)

        # X Axis frame
        x_frame = ttk.LabelFrame(root, text="X Axis", padding=(10, 5))
        x_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        ttk.Button(x_frame, text="⬅️ Backward", command=lambda: self.move_motor('X', -self.step_size.get())).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(x_frame, text="Forward ➡️", command=lambda: self.move_motor('X', self.step_size.get())).grid(row=0, column=1, padx=5, pady=5)

        # Y Axis frame
        y_frame = ttk.LabelFrame(root, text="Y Axis", padding=(10, 5))
        y_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        ttk.Button(y_frame, text="⬆️ Forward", command=lambda: self.move_motor('Y', self.step_size.get())).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(y_frame, text="Backward ⬇️", command=lambda: self.move_motor('Y', -self.step_size.get())).grid(row=0, column=1, padx=5, pady=5)

        # Z Axis frame
        z_frame = ttk.LabelFrame(root, text="Z Axis (Pen Lift)", padding=(10, 5))
        z_frame.grid(row=3, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        ttk.Button(z_frame, text="🔼 Up", command=lambda: self.move_motor('Z', self.step_size.get())).grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(z_frame, text="Down 🔽", command=lambda: self.move_motor('Z', -self.step_size.get())).grid(row=0, column=1, padx=5, pady=5)

        # Quit button
        ttk.Button(root, text="Quit", command=self.quit_app).grid(row=4, column=0, columnspan=2, pady=15, sticky="ew")

        # Status bar
        status_bar = ttk.Label(root, textvariable=self.status_var, anchor="w", relief="sunken", font=("Segoe UI", 9))
        status_bar.grid(row=5, column=0, columnspan=2, sticky="ew", padx=0, pady=0)

    def send_command(self, cmd):
        self.ser.write((cmd + '\n').encode())
        response = self.ser.readline().decode().strip()
        return response

    def move_motor(self, axis, steps):
        cmd = f"G1 {axis}{steps}"
        response = self.send_command(cmd)
        if response != "OK":
            messagebox.showwarning("Warning", f"Unexpected response: {response}")

    def quit_app(self):
        self.ser.close()
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = MotorControlApp(root)
    root.mainloop()