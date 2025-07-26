import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import serial
import time
import threading

# --- Configuration ---
# Match these with your Arduino and system setup
SERIAL_PORT = 'COM11'
BAUD_RATE = 9600

# --- Main Application ---
class GcodeSenderApp(tk.Tk):
    """
    A Tkinter application to send G-code files to a serial-controlled device,
    like a pen plotter.
    """
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("G-code Sender")
        self.geometry("700x600")
        self.minsize(600, 500)
        self.configure(bg="#2c3e50")

        # --- Application State ---
        self.ser = None
        self.gcode_lines = []
        self.is_sending = False
        self.sending_thread = None
        self.source_filename = None
        self.time_status_var = None  # Initialize this early

        # --- UI Creation ---
        self._setup_styles()
        self._create_widgets()
        self._connect_to_plotter()

        # --- Graceful Exit ---
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _setup_styles(self):
        """Configure custom ttk styles for a modern look."""
        style = ttk.Style(self)
        style.theme_use('clam')

        # General widget styles
        style.configure("TFrame", background="#2c3e50")
        style.configure("TLabel", background="#2c3e50", foreground="#ecf0f1", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("TButton", background=[('active', '#3498db')])
        style.configure("TProgressbar", thickness=20, background='#3498db')

        # Custom button styles
        style.configure("Accent.TButton", foreground="white", background="#2980b9")
        style.map("Accent.TButton", background=[('active', '#3498db')])
        style.configure("Stop.TButton", foreground="white", background="#c0392b")
        style.map("Stop.TButton", background=[('active', '#e74c3c')])

    def _create_widgets(self):
        """Create and arrange all the UI elements in the window."""
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # --- Top Control Frame ---
        control_frame = ttk.Frame(self, padding="10")
        control_frame.grid(row=0, column=0, sticky="ew")
        control_frame.grid_columnconfigure(1, weight=1)

        self.load_button = ttk.Button(control_frame, text="📁 Load G-code File", command=self.load_file, width=20)
        self.load_button.grid(row=0, column=0, padx=(0, 10))

        self.file_label = ttk.Label(control_frame, text="No file loaded.", anchor="w", style="TLabel")
        self.file_label.grid(row=0, column=1, sticky="ew")

        self.send_button = ttk.Button(control_frame, text="▶ Send to Plotter", style="Accent.TButton", command=self.start_sending, state="disabled")
        self.send_button.grid(row=0, column=2, padx=10)

        self.stop_button = ttk.Button(control_frame, text="⏹ Stop", style="Stop.TButton", command=self.stop_sending, state="disabled")
        self.stop_button.grid(row=0, column=3)

        self.test_button = ttk.Button(control_frame, text="🔧 Test Connection", command=self.test_connection, width=15)
        self.test_button.grid(row=0, column=4, padx=5)

        self.home_button = ttk.Button(control_frame, text="🏠 Home", command=self.send_home_command, width=10)
        self.home_button.grid(row=0, column=5, padx=5)

        # Debug mode checkbox
        self.debug_var = tk.BooleanVar(value=False)
        self.debug_checkbox = ttk.Checkbutton(control_frame, text="Debug Mode", variable=self.debug_var)
        self.debug_checkbox.grid(row=1, column=0, columnspan=2, sticky="w", pady=5)

        # Manual command entry for testing
        manual_frame = ttk.Frame(control_frame)
        manual_frame.grid(row=1, column=2, columnspan=3, sticky="ew", pady=5)
        
        ttk.Label(manual_frame, text="Manual Command:").pack(side="left", padx=5)
        self.manual_entry = ttk.Entry(manual_frame, width=15)
        self.manual_entry.pack(side="left", padx=5)
        self.manual_entry.bind("<Return>", self.send_manual_command)
        
        ttk.Button(manual_frame, text="Send", command=self.send_manual_command, width=8).pack(side="left", padx=5)

        # --- G-code Log Viewer ---
        log_frame = ttk.Frame(self, padding="10")
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg="#34495e",
            fg="#ecf0f1",
            relief="sunken",
            borderwidth=1,
            state="disabled"
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")

        # --- Bottom Status & Progress Frame ---
        status_frame = ttk.Frame(self, padding="10")
        status_frame.grid(row=2, column=0, sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(status_frame, orient="horizontal", mode="determinate")
        self.progress_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))

        self.status_var = tk.StringVar(value="Initializing...")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor="w")
        status_label.grid(row=1, column=0, sticky="ew")
        
        # Add time information label
        self.time_status_var = tk.StringVar(value="")
        self.time_status_label = ttk.Label(status_frame, textvariable=self.time_status_var, anchor="w", 
                                          font=("Segoe UI", 9), foreground="#95a5a6")
        self.time_status_label.grid(row=2, column=0, sticky="ew")

    def _connect_to_plotter(self):
        """Attempt to connect to the serial port."""
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
            time.sleep(2)  # Wait for Arduino to reset
            
            # Clear any startup messages and wait for "Ready"
            self.ser.flushInput()
            start_time = time.time()
            ready_received = False
            
            while time.time() - start_time < 5:  # Wait up to 5 seconds
                if self.ser.in_waiting > 0:
                    response = self.ser.readline().decode('utf-8').strip()
                    if response == "Ready":
                        ready_received = True
                        break
                time.sleep(0.1)
            
            if ready_received:
                self.status_var.set(f"✅ Connected to plotter on {SERIAL_PORT} (Ready)")
            else:
                self.status_var.set(f"⚠️ Connected to {SERIAL_PORT} but no 'Ready' message received")
                
        except serial.SerialException as e:
            self.status_var.set(f"❌ Connection Error: {e}")
            messagebox.showerror("Connection Error", f"Could not connect to {SERIAL_PORT}.\n\n- Is the plotter plugged in?\n- Is the correct COM port selected?\n- Is another program using the port?")
            self.load_button.config(state="disabled")

    def load_file(self):
        """Open a file dialog to load a G-code file."""
        filepath = filedialog.askopenfilename(
            title="Select a G-code File",
            filetypes=[("G-code files", "*.gcode *.nc"), ("All files", "*.*")]
        )
        if not filepath:
            return

        try:
            with open(filepath, 'r') as f:
                self.gcode_lines = [line.strip() for line in f if line.strip()]
            
            self.source_filename = filepath.split('/')[-1]
            self.file_label.config(text=f"{self.source_filename} ({len(self.gcode_lines)} lines)")
            self.status_var.set(f"Ready to send {self.source_filename}")
            
            # Populate log viewer
            self.log_text.config(state="normal")
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, "\n".join(self.gcode_lines))
            self.log_text.config(state="disabled")

            self.send_button.config(state="normal" if self.ser else "disabled")
            self.progress_bar['value'] = 0

        except Exception as e:
            messagebox.showerror("File Error", f"Failed to read file:\n{e}")
            self.status_var.set("❌ Error loading file.")

    def test_connection(self):
        """Send a simple test command to check communication."""
        if not self.ser or not self.ser.is_open:
            messagebox.showerror("Test Error", "Plotter is not connected.")
            return
        
        try:
            test_command = "G90"  # Simple command to set absolute mode
            self.status_var.set(f"Testing connection with: {test_command}")
            
            # Clear any pending data
            self.ser.flushInput()
            
            # Send test command
            self.ser.write((test_command + '\n').encode('utf-8'))
            self.ser.flush()
            
            # Wait for response with improved handling
            start_time = time.time()
            response = ""
            while time.time() - start_time < 5:
                if self.ser.in_waiting > 0:
                    try:
                        response = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        if response:  # Got a non-empty response
                            break
                    except UnicodeDecodeError:
                        continue
                time.sleep(0.05)
            
            if response:
                if response == "OK":
                    messagebox.showinfo("Test Result", f"✅ Connection test successful!\n\nCommand: {test_command}\nResponse: {response}")
                    self.status_var.set("✅ Connection test passed")
                else:
                    messagebox.showwarning("Test Result", f"⚠️ Unexpected response received:\n\nCommand: {test_command}\nResponse: '{response}'\n\nThis might indicate a communication issue.")
                    self.status_var.set(f"⚠️ Test response: '{response}'")
            else:
                messagebox.showerror("Test Result", f"❌ No response received from plotter\n\nCommand: {test_command}\n\nCheck:\n- Arduino is programmed with correct sketch\n- Correct COM port\n- Baud rate matches (9600)")
                self.status_var.set("❌ No response to test command")
                
        except Exception as e:
            messagebox.showerror("Test Error", f"Error during test: {e}")
            self.status_var.set(f"❌ Test error: {e}")

    def send_manual_command(self, event=None):
        """Send a manual command for testing."""
        if not self.ser or not self.ser.is_open:
            messagebox.showerror("Error", "Plotter is not connected.")
            return
        
        command = self.manual_entry.get().strip()
        if not command:
            return
            
        try:
            self.status_var.set(f"Sending manual command: {command}")
            
            # Clear input buffer
            self.ser.flushInput()
            
            # Send command
            self.ser.write((command + '\n').encode('utf-8'))
            self.ser.flush()
            
            # Wait for response
            start_time = time.time()
            response = ""
            while time.time() - start_time < 5:
                if self.ser.in_waiting > 0:
                    try:
                        response = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        if response:
                            break
                    except UnicodeDecodeError:
                        continue
                time.sleep(0.05)
            
            # Show result
            if response:
                self.status_var.set(f"Manual command response: '{response}'")
                print(f"Manual: '{command}' -> '{response}'")
            else:
                self.status_var.set(f"No response to manual command: {command}")
                print(f"Manual: '{command}' -> NO RESPONSE")
                
            # Clear the entry
            self.manual_entry.delete(0, tk.END)
            
        except Exception as e:
            self.status_var.set(f"Error sending manual command: {e}")

    def send_home_command(self):
        """Send G28 home command to the plotter."""
        if not self.ser or not self.ser.is_open:
            messagebox.showerror("Error", "Plotter is not connected.")
            return
        
        if self.is_sending:
            messagebox.showwarning("Warning", "Cannot home while printing is in progress.")
            return
            
        try:
            self.status_var.set("Homing plotter...")
            
            # Clear input buffer
            self.ser.flushInput()
            
            # Send home command
            command = "G28"
            self.ser.write((command + '\n').encode('utf-8'))
            self.ser.flush()
            
            # Wait for response with longer timeout since homing can take time
            start_time = time.time()
            response = ""
            timeout = 30  # 30 seconds timeout for homing
            
            while time.time() - start_time < timeout:
                if self.ser.in_waiting > 0:
                    try:
                        response = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        if response:
                            break
                    except UnicodeDecodeError:
                        continue
                time.sleep(0.1)
            
            # Show result
            if response == "OK":
                self.status_var.set("✅ Homing completed successfully")
                messagebox.showinfo("Home Complete", "Plotter has been homed successfully!")
            elif response:
                self.status_var.set(f"⚠️ Homing response: '{response}'")
                messagebox.showwarning("Home Warning", f"Received unexpected response from homing:\n'{response}'")
            else:
                self.status_var.set("❌ No response to home command")
                messagebox.showerror("Home Error", "No response received from plotter during homing.\nHoming may have failed or taken longer than expected.")
                
        except Exception as e:
            self.status_var.set(f"❌ Error during homing: {e}")
            messagebox.showerror("Home Error", f"Error during homing: {e}")

    def start_sending(self):
        """Start the G-code sending process in a new thread."""
        if not self.gcode_lines or self.is_sending:
            return
        
        if not self.ser or not self.ser.is_open:
            messagebox.showerror("Serial Error", "Plotter is not connected.")
            return

        self.is_sending = True
        self.load_button.config(state="disabled")
        self.send_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.home_button.config(state="disabled")
        self.test_button.config(state="disabled")
        self.manual_entry.config(state="disabled")
        self.progress_bar['maximum'] = len(self.gcode_lines)
        self.progress_bar['value'] = 0

        # Run the sending logic in a separate thread to keep the UI responsive
        self.sending_thread = threading.Thread(target=self._send_gcode_worker, daemon=True)
        self.sending_thread.start()

    def stop_sending(self):
        """Signal the sending thread to stop."""
        if self.is_sending:
            self.is_sending = False # The thread will check this flag and exit
            self.status_var.set("⏹️ Sending stopped by user.")
            # Buttons will be re-enabled by the thread upon exit

    def _calculate_movement_timeout(self, line):
        """Calculate timeout based on the expected movement time."""
        base_timeout = 3  # Base timeout for non-movement commands
        
        if not (line.startswith('G0') or line.startswith('G1')):
            return base_timeout
        
        try:
            # Extract X and Y coordinates if present
            x_coord = 0
            y_coord = 0
            
            if 'X' in line:
                x_start = line.find('X') + 1
                x_end = line.find(' ', x_start)
                if x_end == -1:
                    x_end = len(line)
                x_coord = float(line[x_start:x_end])
            
            if 'Y' in line:
                y_start = line.find('Y') + 1
                y_end = line.find(' ', y_start)
                if y_end == -1:
                    y_end = len(line)
                y_coord = float(line[y_start:y_end])
            
            # Estimate maximum steps (assuming we might move the full distance)
            max_steps = max(abs(x_coord), abs(y_coord))
            
            # Calculate time: steps × step_delay(2ms) + safety margin
            # stepDelay is 2000 microseconds = 2ms per step
            estimated_time = (max_steps * 2) / 1000  # Convert to seconds
            safety_margin = estimated_time * 1.5  # 150% safety margin
            total_timeout = estimated_time + safety_margin + base_timeout
            
            # Ensure minimum and maximum reasonable timeouts
            return max(5, min(total_timeout, 120))  # Between 5 seconds and 2 minutes
            
        except:
            # If parsing fails, use a large timeout for movement commands
            return 30

    def _estimate_total_time(self):
        """Estimate the total time to complete all G-code commands."""
        total_time = 0
        
        for line in self.gcode_lines:
            # Skip comments and empty lines
            if line.startswith(';') or not line:
                continue
                
            if line.startswith('G0') or line.startswith('G1'):
                try:
                    # Extract coordinates
                    x_coord = 0
                    y_coord = 0
                    z_coord = 0
                    
                    if 'X' in line:
                        x_start = line.find('X') + 1
                        x_end = line.find(' ', x_start)
                        if x_end == -1:
                            x_end = len(line)
                        x_coord = float(line[x_start:x_end])
                    
                    if 'Y' in line:
                        y_start = line.find('Y') + 1
                        y_end = line.find(' ', y_start)
                        if y_end == -1:
                            y_end = len(line)
                        y_coord = float(line[y_start:y_end])
                        
                    if 'Z' in line:
                        z_start = line.find('Z') + 1
                        z_end = line.find(' ', z_start)
                        if z_end == -1:
                            z_end = len(line)
                        z_coord = float(line[z_start:z_end])
                    
                    # Calculate maximum steps for this movement
                    max_steps = max(abs(x_coord), abs(y_coord), abs(z_coord))
                    
                    # Each step takes 2ms (2000 microseconds)
                    line_time = (max_steps * 2) / 1000  # Convert to seconds
                    total_time += line_time
                    
                except:
                    # If parsing fails, add a default time
                    total_time += 1  # 1 second default
            else:
                # Non-movement commands get a small time allocation
                total_time += 0.1
        
        return total_time

    def _send_gcode_worker(self):
        """The actual G-code sending logic that runs in a thread."""
        try:
            # Calculate estimated total time
            estimated_time = self._estimate_total_time()
            job_start_time = time.time()
            
            for i, line in enumerate(self.gcode_lines):
                if not self.is_sending:
                    break # Exit if stop was requested

                # Skip comments and empty lines
                if line.startswith(';') or not line:
                    self.after(0, self._update_progress, i + 1, job_start_time, estimated_time)
                    continue

                elapsed_time = time.time() - job_start_time
                remaining_lines = len(self.gcode_lines) - i
                if remaining_lines > 0:
                    estimated_remaining = estimated_time * (remaining_lines / len(self.gcode_lines))
                    time_info = f" | Elapsed: {elapsed_time:.0f}s, Est. remaining: {estimated_remaining:.0f}s"
                else:
                    time_info = f" | Elapsed: {elapsed_time:.0f}s"
                
                self.status_var.set(f"Sending ({i+1}/{len(self.gcode_lines)}): {line}{time_info}")
                
                # Debug logging
                if self.debug_var.get():
                    print(f"DEBUG: Sending command: '{line}'")
                
                # Clear any pending input before sending
                self.ser.flushInput()
                
                # Send command
                self.ser.write((line + '\n').encode('utf-8'))
                self.ser.flush()  # Ensure data is sent immediately
                
                # Debug logging
                if self.debug_var.get():
                    print(f"DEBUG: Command sent, waiting for response...")
                
                # Calculate dynamic timeout based on movement distance
                timeout = self._calculate_movement_timeout(line)
                
                # Update status with timeout info for long movements
                if timeout > 10:
                    self.status_var.set(f"Sending ({i+1}/{len(self.gcode_lines)}): {line} (timeout: {timeout:.0f}s)")
                
                if self.debug_var.get():
                    print(f"DEBUG: Using timeout of {timeout:.1f} seconds for command: {line}")
                
                command_start_time = time.time()
                response = ""
                last_status_update = command_start_time
                
                while time.time() - command_start_time < timeout:
                    # Update status every 2 seconds for long movements
                    current_time = time.time()
                    if timeout > 10 and current_time - last_status_update > 2:
                        elapsed = current_time - command_start_time
                        self.status_var.set(f"Sending ({i+1}/{len(self.gcode_lines)}): {line} (elapsed: {elapsed:.1f}s/{timeout:.0f}s)")
                        last_status_update = current_time
                    
                    if self.ser.in_waiting > 0:
                        try:
                            response = self.ser.readline().decode('utf-8', errors='ignore').strip()
                            if response:  # Got a non-empty response
                                if self.debug_var.get():
                                    elapsed = time.time() - command_start_time
                                    print(f"DEBUG: Received response: '{response}' after {elapsed:.2f} seconds")
                                break
                        except UnicodeDecodeError:
                            continue
                    time.sleep(0.05)  # Slightly longer sleep to reduce CPU usage
                
                # Debug logging for timeouts
                if not response and self.debug_var.get():
                    print(f"DEBUG: No response received within {timeout} seconds")
                
                if not response:
                    elapsed = time.time() - command_start_time
                    self.status_var.set(f"⚠️ No response from plotter for command: {line}")
                    messagebox.showwarning("Plotter Warning", f"No response from plotter for command:\n{line}\n\nTimeout: {timeout:.1f}s (elapsed: {elapsed:.1f}s)\n\nThe movement might be taking longer than expected.\nTry increasing the timeout or check if the plotter is stuck.\n\nSending has been stopped.")
                    break
                elif response != "OK":
                    # Log the unexpected response for debugging
                    self.status_var.set(f"⚠️ Unexpected response: '{response}' for command: {line}")
                    messagebox.showwarning("Plotter Warning", f"Received unexpected response from plotter:\n\nCommand: {line}\nResponse: '{response}'\n\nSending has been stopped.")
                    break
                
                # Update progress bar from the main thread
                self.after(0, self._update_progress, i + 1, job_start_time, estimated_time)
                
                # Small delay between commands to prevent overwhelming the Arduino
                time.sleep(0.1)

        except serial.SerialException as e:
            self.status_var.set(f"❌ Serial Error: {e}. Sending aborted.")
            messagebox.showerror("Serial Error", f"A serial communication error occurred: {e}\n\nSending has been stopped.")
        except Exception as e:
            self.status_var.set(f"❌ An unexpected error occurred: {e}")
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        finally:
            # This block runs whether the loop finished, was stopped, or an error occurred
            self.after(0, self._finalize_sending)

    def _update_progress(self, value, start_time=None, estimated_time=None):
        """Update the progress bar value (UI thread safe)."""
        self.progress_bar['value'] = value
        
        # Update progress bar text with time information if available
        if start_time and estimated_time:
            elapsed = time.time() - start_time
            progress_percent = (value / len(self.gcode_lines)) * 100
            remaining_time = max(0, estimated_time - elapsed)
            
            # Format time nicely
            def format_time(seconds):
                if seconds < 60:
                    return f"{seconds:.0f}s"
                elif seconds < 3600:
                    return f"{seconds//60:.0f}m {seconds%60:.0f}s"
                else:
                    hours = seconds // 3600
                    minutes = (seconds % 3600) // 60
                    return f"{hours:.0f}h {minutes:.0f}m"
            
            # Update the time status
            time_info = f"Progress: {progress_percent:.1f}% | Elapsed: {format_time(elapsed)} | Est. remaining: {format_time(remaining_time)} | Total est: {format_time(estimated_time)}"
            self.time_status_var.set(time_info)
        else:
            self.time_status_var.set("")

    def _finalize_sending(self):
        """Reset the UI to its idle state after sending is complete or stopped."""
        if self.is_sending: # If it finished without being stopped
            self.status_var.set(f"✅ Successfully sent {self.source_filename}")
        
        self.is_sending = False
        self.load_button.config(state="normal")
        self.send_button.config(state="normal" if self.gcode_lines else "disabled")
        self.stop_button.config(state="disabled")
        self.home_button.config(state="normal")
        self.test_button.config(state="normal")
        self.manual_entry.config(state="normal")

    def _on_closing(self):
        """Handle window closing event."""
        if self.is_sending:
            if messagebox.askyesno("Exit", "Plotter is busy. Are you sure you want to exit?"):
                self.is_sending = False
                if self.ser and self.ser.is_open:
                    self.ser.close()
                self.destroy()
        else:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.destroy()

if __name__ == "__main__":
    app = GcodeSenderApp()
    app.mainloop()
