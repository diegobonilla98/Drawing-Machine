#include <math.h>    // for isnan

// Pin definitions for each motor
int xPins[4] = {5, 4, 3, 2};    // IN1=5, IN2=4, IN3=3, IN4=2
int yPins[4] = {14, 15, 16, 17}; // IN1=A0=14, IN2=A1=15, IN3=A2=16, IN4=A3=17
int zPins[4] = {13, 12, 9, 8};   // IN1=13, IN2=12, IN3=9, IN4=8

// Limit switch pins (pull-up switches)
const int xLimitPin = 7;
const int yLimitPin = 6;
const int zLimitPin = 10;

// Half-step sequence (8 steps)
// const int stepSequence[8][4] = {
//   {1, 0, 0, 0},
//   {1, 1, 0, 0},
//   {0, 1, 0, 0},
//   {0, 1, 1, 0},
//   {0, 0, 1, 0},
//   {0, 0, 1, 1},
//   {0, 0, 0, 1},
//   {0, 0, 0, 1}
// };

const int stepSequence[8][4] = {
  {1, 0, 0, 0},
  {1, 1, 0, 0},
  {0, 1, 0, 0},
  {0, 1, 1, 0},
  {0, 0, 1, 0},
  {0, 0, 1, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1}  // This should be {1, 0, 0, 1}, not a duplicate
};

// Current phase for each motor
int xPhase = 0;
int yPhase = 0;
int zPhase = 0;

// Current positions (in steps)
long curX = 0;
long curY = 0;
long curZ = 0;

// Positioning mode (true for absolute, false for relative)
bool absMode = true;

// Step delay in microseconds (adjust for speed; lower = faster, but may skip steps)
const int stepDelay = 2000;  // ~1000-3000 us recommended for 28BYJ-48

void setup() {
  Serial.begin(9600);

  // Set pin modes for all motor pins
  for (int i = 0; i < 4; i++) {
    pinMode(xPins[i], OUTPUT);
    pinMode(yPins[i], OUTPUT);
    pinMode(zPins[i], OUTPUT);
  }

  // Set limit switch pins as inputs with pull-up resistors
  pinMode(xLimitPin, INPUT_PULLUP);
  pinMode(yLimitPin, INPUT_PULLUP);
  pinMode(zLimitPin, INPUT_PULLUP);

  // Initialize motors to off
  turnOffMotors();

  Serial.println("Ready");
}

void loop() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    
    // Skip empty commands
    if (cmd.length() == 0) {
      return; // Don't send OK for empty commands
    }

    processCommand(cmd);
    Serial.println("OK");
    Serial.flush(); // Ensure data is sent immediately
    delay(10); // Small delay for serial communication stability
  }
}

// Function to process incoming G-code-like commands
void processCommand(String cmd) {
  int gNum = -1;
  int mNum = -1;
  float Xval = NAN, Yval = NAN, Zval = NAN;

  // Parse G number
  if (cmd.startsWith("G")) {
    gNum = cmd.substring(1, 3).toInt();
  }
  // Parse M number
  else if (cmd.startsWith("M")) {
    mNum = cmd.substring(1, 3).toInt();
  }

  // Handle specific G-codes
  if (gNum == 90) {
    absMode = true;
    return;
  } else if (gNum == 91) {
    absMode = false;
    return;
  } else if (gNum == 21) {
    // G21: Use millimeters (ignored, we work in steps)
    return;
  } else if (gNum == 28) {
    // G28: Home axes using limit switches
    homeAxes();
    return;
  } else if (mNum == 84) {
    // M84: Disable motors
    turnOffMotors();
    return;
  } else if (gNum != 0 && gNum != 1 && gNum != -1) {
    // Unsupported G-code, but still acknowledge
    return;
  }

  // Only G0 and G1 commands continue past here

  // Parse X, Y, Z values
  int xIndex = cmd.indexOf('X');
  int yIndex = cmd.indexOf('Y');
  int zIndex = cmd.indexOf('Z');

  if (xIndex != -1) {
    int end = cmd.indexOf(' ', xIndex);
    if (end == -1) end = cmd.length();
    Xval = cmd.substring(xIndex + 1, end).toFloat();
  }
  if (yIndex != -1) {
    int end = cmd.indexOf(' ', yIndex);
    if (end == -1) end = cmd.length();
    Yval = cmd.substring(yIndex + 1, end).toFloat();
  }
  if (zIndex != -1) {
    int end = cmd.indexOf(' ', zIndex);
    if (end == -1) end = cmd.length();
    Zval = cmd.substring(zIndex + 1, end).toFloat();
  }

  // Calculate target positions and deltas
  long targetX = curX;
  long targetY = curY;
  long targetZ = curZ;
  long dX = 0, dY = 0, dZ = 0;

  if (!isnan(Xval)) {
    targetX = absMode ? (long)Xval : curX + (long)Xval;
    dX = targetX - curX;
  }
  if (!isnan(Yval)) {
    targetY = absMode ? (long)Yval : curY + (long)Yval;
    dY = targetY - curY;
  }
  if (!isnan(Zval)) {
    targetZ = absMode ? (long)Zval : curZ + (long)Zval;
    dZ = targetZ - curZ;
  }

  // If no movement, return
  if (dX == 0 && dY == 0 && dZ == 0) return;

  // Perform interpolated movement using DDA algorithm
  long absDX = abs(dX);
  long absDY = abs(dY);
  long absDZ = abs(dZ);
  long maxDelta = max(absDX, max(absDY, absDZ));

  float incX = (float)dX / maxDelta;
  float incY = (float)dY / maxDelta;
  float incZ = (float)dZ / maxDelta;

  float accX = 0, accY = 0, accZ = 0;

  for (long i = 0; i < maxDelta; i++) {
    accX += incX;
    accY += incY;
    accZ += incZ;

    if (fabs(accX) >= 1) {
      int dir = (accX > 0) ? 1 : -1;
      stepMotor('X', dir);
      accX -= dir;
    }
    if (fabs(accY) >= 1) {
      int dir = (accY > 0) ? 1 : -1;
      stepMotor('Y', dir);
      accY -= dir;
    }
    if (fabs(accZ) >= 1) {
      int dir = (accZ > 0) ? 1 : -1;
      stepMotor('Z', dir);
      accZ -= dir;
    }
  }

  // Update current positions
  curX = targetX;
  curY = targetY;
  curZ = targetZ;

  // Optional: turn off motors after move to save power
  // turnOffMotors();
}

// Function to step a motor in a given direction (1 forward, -1 backward)
void stepMotor(char motor, int dir) {
  int *pins;
  int *phase;

  // Invert direction for X and Y motors due to reversed wiring
  if (motor == 'X') {
    pins = xPins;
    phase = &xPhase;
    dir = -dir;
  } else if (motor == 'Y') {
    pins = yPins;
    phase = &yPhase;
    dir = -dir;
  } else if (motor == 'Z') {
    pins = zPins;
    phase = &zPhase;
  } else {
    return;
  }

  // Update phase
  if (dir > 0) {
    *phase = (*phase + 1) % 8;
  } else {
    *phase = (*phase - 1 + 8) % 8;
  }

  // Apply sequence to pins
  for (int i = 0; i < 4; i++) {
    digitalWrite(pins[i], stepSequence[*phase][i]);
  }

  // Delay for speed control
  delayMicroseconds(stepDelay);
}

// Function to step a motor with custom delay (for homing)
void stepMotorWithDelay(char motor, int dir, int customDelay) {
  int *pins;
  int *phase;

  // Invert direction for X and Y motors due to reversed wiring
  if (motor == 'X') {
    pins = xPins;
    phase = &xPhase;
    dir = -dir;
  } else if (motor == 'Y') {
    pins = yPins;
    phase = &yPhase;
    dir = -dir;
  } else if (motor == 'Z') {
    pins = zPins;
    phase = &zPhase;
  } else {
    return;
  }

  // Update phase
  if (dir > 0) {
    *phase = (*phase + 1) % 8;
  } else {
    *phase = (*phase - 1 + 8) % 8;
  }

  // Apply sequence to pins
  for (int i = 0; i < 4; i++) {
    digitalWrite(pins[i], stepSequence[*phase][i]);
  }

  // Delay for speed control
  delayMicroseconds(customDelay);
}

// Function to turn off all motors (no holding torque)
void turnOffMotors() {
  for (int i = 0; i < 4; i++) {
    digitalWrite(xPins[i], 0);
    digitalWrite(yPins[i], 0);
    digitalWrite(zPins[i], 0);
  }
}

// Function to home all axes using limit switches
void homeAxes() {
  // Use slower speed for homing accuracy
  const int homingDelay = 3000; // Slower homing speed for accuracy
  
  // Store original step delay for homing
  int originalDelay = stepDelay;
  
  // Temporarily change stepDelay for homing
  // Note: We need to modify the stepMotor function or create a separate one
  // For now, we'll use a simple approach with direct motor control
  
  // Home each axis until it hits its limit switch
  // Note: Limit switches are pull-up, so they read LOW when pressed
  
  // Home X axis
  while (digitalRead(xLimitPin) == HIGH) {
    stepMotorWithDelay('X', -1, homingDelay); // Move towards limit switch
  }
  
  // Home Y axis (reversed direction)
  while (digitalRead(yLimitPin) == HIGH) {
    stepMotorWithDelay('Y', 1, homingDelay); // Move towards limit switch (positive direction for reversed Y)
  }
  
  // Home Z axis (reversed direction)
  while (digitalRead(zLimitPin) == HIGH) {
    stepMotorWithDelay('Z', 1, homingDelay); // Move towards limit switch (positive direction for reversed Z)
  }
  
  // Move Z motor back 750 steps to position exactly on the paper
  for (int i = 0; i < 750; i++) {
    stepMotorWithDelay('Z', -1, homingDelay); // Move away from limit switch to paper position
  }
  
  // Reset positions to zero after homing
  curX = 0;
  curY = 0;
  curZ = 0;
  
  // Turn off motors after homing
  turnOffMotors();
}