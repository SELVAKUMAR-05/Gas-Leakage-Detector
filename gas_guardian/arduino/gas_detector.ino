#include <stdlib.h>
#include <string.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

const uint8_t GAS_SENSOR_PIN = A0;
const uint8_t RED_LED_PIN = 2;
const uint8_t GREEN_LED_PIN = 3;
const uint8_t BUZZER_PIN = 4;
const uint8_t OLED_CS_PIN = 10;
const uint8_t OLED_DC_PIN = 8;
const uint8_t OLED_RESET_PIN = 9;

Adafruit_SSD1306 display(128, 64, &SPI, OLED_DC_PIN, OLED_RESET_PIN, OLED_CS_PIN);
bool displayReady = false;

int gasThreshold = 400;
unsigned long lastSampleAt = 0;
char commandBuffer[40];
uint8_t commandLength = 0;

void setup() {
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(GREEN_LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(GREEN_LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);
  Serial.begin(9600);
  SPI.begin();
  displayReady = display.begin(SSD1306_SWITCHCAPVCC);
  if (displayReady) {
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);
    display.setCursor(0, 0);
    display.println("GAS GUARDIAN");
    display.drawFastHLine(0, 11, 128, SSD1306_WHITE);
    display.setCursor(0, 24);
    display.println("OLED READY");
    display.display();
  } else {
    Serial.println("OLED_INIT,FAILED");
  }
}

void updateDisplay(int sensorValue, bool leaking) {
  if (!displayReady) {
    return;
  }

  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("GAS GUARDIAN");
  display.drawFastHLine(0, 11, 128, SSD1306_WHITE);

  display.setCursor(0, 15);
  display.print("GAS LEVEL");
  display.setTextSize(2);
  display.setCursor(0, 25);
  display.print(sensorValue);

  display.setTextSize(1);
  display.setCursor(0, 44);
  display.print(leaking ? "LEAKING" : "NORMAL");
  display.setCursor(0, 57);
  display.print("Threshold: ");
  display.print(gasThreshold);
  display.display();
}

void readCommands() {
  while (Serial.available() > 0) {
    const char incoming = static_cast<char>(Serial.read());
    if (incoming == '\r') {
      continue;
    }
    if (incoming == '\n') {
      commandBuffer[commandLength] = '\0';
      if (strncmp(commandBuffer, "THRESHOLD,", 10) == 0) {
        const int requested = atoi(commandBuffer + 10);
        if (requested >= 0 && requested <= 1023) {
          gasThreshold = requested;
        }
      }
      commandLength = 0;
    } else if (commandLength < sizeof(commandBuffer) - 1) {
      commandBuffer[commandLength++] = incoming;
    } else {
      commandLength = 0;
    }
  }
}

void loop() {
  readCommands();
  const unsigned long now = millis();
  if (now - lastSampleAt >= 500) {
    lastSampleAt = now;
    const int sensorValue = analogRead(GAS_SENSOR_PIN);
    const bool leaking = sensorValue >= gasThreshold;
    digitalWrite(RED_LED_PIN, leaking ? HIGH : LOW);
    digitalWrite(GREEN_LED_PIN, leaking ? LOW : HIGH);
    digitalWrite(BUZZER_PIN, leaking ? HIGH : LOW);
    updateDisplay(sensorValue, leaking);

    Serial.print("GAS,");
    Serial.print(sensorValue);
    Serial.print(',');
    Serial.println(leaking ? "LEAKING" : "NORMAL");
  }
}
