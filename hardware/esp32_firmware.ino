/**
 * ====================================================================================
 * APEX SMART PLANT CARE & WATERING PLATFORM - ESP32 FIRMWARE
 * ====================================================================================
 * Hardware Target: ESP32 DevKit v1 (NodeMCU-32S)
 * Sensors: Capacitive Soil Moisture Sensor v1.2 (ADC GPIO 34)
 *          DHT22 Temperature & Humidity Sensor (GPIO 4)
 * Actuators: 5V Active-Low Relay Module (GPIO 26) - Submersible DC Water Pump
 * Security: mbedTLS HMAC-SHA256 Payload Signing & Pre-Shared API Token
 * Fail-Safe: Local Hardware Emergency Hysteresis watchdog if Cloud disconnects > 5m
 * ====================================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include "DHTesp.h"
#include "mbedtls/md.h"

// -------------------------------------------------------------
// Pin Assignments & Safe Low-Voltage DC Configuration
// -------------------------------------------------------------
#define PIN_SOIL_MOISTURE  34   // Analog ADC1 input (ADC2 unavailable during WiFi)
#define PIN_DHT22           4   // Digital input for DHT22
#define PIN_RELAY_PUMP     26   // Active-Low Relay trigger for 5V DC pump
#define PIN_STATUS_LED      2   // Onboard indicator LED

// Calibration Constants for Capacitive Soil Moisture Sensor v1.2
// Measured at 12-bit ADC resolution (0 - 4095)
const int DRY_ADC_VALUE = 3200;   // Sensor in dry open air
const int WET_ADC_VALUE = 1450;   // Sensor fully submerged in water cup

// -------------------------------------------------------------
// Network & Cloud Gateway Parameters
// -------------------------------------------------------------
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Cloud Backend Ingestion URL (Use HTTPS in production; HTTP for local testing)
const char* BACKEND_INGEST_URL = "http://192.168.1.100:8000/api/v1/telemetry/ingest";

// Cryptographic Edge Identity
const char* DEVICE_ID       = "esp32-greenhouse-01";
const char* DEVICE_API_KEY  = "plant-care-edge-token-2026-secure";
const char* HMAC_SECRET_KEY = "hmac-secret-key-plant-guard-99228811";

// Timing Parameters (Non-blocking FreeRTOS/millis loop)
const unsigned long TELEMETRY_INTERVAL_MS = 10000;  // 10s sample cadence
const unsigned long FAILSAFE_TIMEOUT_MS   = 300000; // 5 minutes network disconnect
const float EMERGENCY_LOCAL_MIN_MOISTURE  = 25.0;   // Local fallback threshold
const float MAX_HARDWARE_PUMP_RUNTIME_SEC = 6.0;    // Hard hardware watchdog cutoff

// -------------------------------------------------------------
// Global Instances & State Tracking
// -------------------------------------------------------------
DHTesp dht;
unsigned long lastTelemetryMillis = 0;
unsigned long lastSuccessfulCloudContact = 0;
bool isPumpActive = false;
unsigned long pumpStartTime = 0;
float currentPumpDurationSeconds = 0.0;

// Relay Polarity: Active-Low Relay (LOW = ON, HIGH = OFF)
void setRelay(bool state) {
  if (state) {
    digitalWrite(PIN_RELAY_PUMP, LOW);  // Energize coil
    digitalWrite(PIN_STATUS_LED, HIGH); // Visual feedback
    isPumpActive = true;
  } else {
    digitalWrite(PIN_RELAY_PUMP, HIGH); // De-energize coil
    digitalWrite(PIN_STATUS_LED, LOW);
    isPumpActive = false;
  }
}

// -------------------------------------------------------------
// Cryptographic Helper: Generate HMAC-SHA256 Signature
// -------------------------------------------------------------
String computeHmacSha256(const String &payload, const char *secretKey) {
  byte hmacResult[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;

  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)secretKey, strlen(secretKey));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)payload.c_str(), payload.length());
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);

  String signature = "";
  for (int i = 0; i < 32; i++) {
    char hex[3];
    sprintf(hex, "%02x", hmacResult[i]);
    signature += hex;
  }
  return signature;
}

// -------------------------------------------------------------
// Sensor Acquisition & Calibration
// -------------------------------------------------------------
float readCalibratedMoisture() {
  // Multisampling filter to suppress analog electrical noise
  long sum = 0;
  for (int i = 0; i < 16; i++) {
    sum += analogRead(PIN_SOIL_MOISTURE);
    delay(5);
  }
  int rawAdc = sum / 16;

  // Linear interpolation: Dry ADC -> 0%, Wet ADC -> 100%
  float moisture = map(rawAdc, DRY_ADC_VALUE, WET_ADC_VALUE, 0, 100);
  moisture = constrain(moisture, 0.0, 100.0);
  return moisture;
}

// -------------------------------------------------------------
// Setup & Initialization
// -------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n[BOOT] Initializing ESP32 Smart Plant Care Node...");

  pinMode(PIN_RELAY_PUMP, OUTPUT);
  pinMode(PIN_STATUS_LED, OUTPUT);
  pinMode(PIN_SOIL_MOISTURE, INPUT);

  // Default relay state: strictly OFF
  setRelay(false);

  dht.setup(PIN_DHT22, DHTesp::DHT22);
  analogReadResolution(12);

  // WiFi Connection
  Serial.print("[WIFI] Connecting to ");
  Serial.println(WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WIFI] Connected! Assigned IP: " + WiFi.localIP().toString());
    lastSuccessfulCloudContact = millis();
  } else {
    Serial.println("\n[WIFI] Initial connection failed. Operating in standalone fallback mode.");
  }
}

// -------------------------------------------------------------
// Main Loop (Non-blocking FreeRTOS model)
// -------------------------------------------------------------
void loop() {
  unsigned long currentMillis = millis();

  // 1. Hardware Watchdog Clamp: Ensure relay is shut off after duration
  if (isPumpActive) {
    if ((currentMillis - pumpStartTime) >= (currentPumpDurationSeconds * 1000)) {
      Serial.println("[ACTUATION] Pump cycle completed. Shutting off relay.");
      setRelay(false);
    }
  }

  // 2. Periodic Telemetry Collection & Cloud Transmission
  if (currentMillis - lastTelemetryMillis >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMillis = currentMillis;

    // Read Sensors
    float moisture = readCalibratedMoisture();
    TempAndHumidity dhtData = dht.getTempAndHumidity();
    float temperature = isnan(dhtData.temperature) ? 24.0 : dhtData.temperature;
    float humidity    = isnan(dhtData.humidity) ? 55.0 : dhtData.humidity;
    float lightLevel  = 1200.0;  // Analog lux or fixed indoor ambient estimation
    float tankLevel   = 90.0;    // Level switch / float sensor reading

    Serial.printf("[SENSORS] Moisture: %.1f%% | Temp: %.1f°C | Hum: %.1f%%\n", moisture, temperature, humidity);

    // Check Cloud Connectivity
    if (WiFi.status() == WL_CONNECTED) {
      // Build JSON Payload
      StaticJsonDocument<256> doc;
      doc["device_id"]        = DEVICE_ID;
      doc["soil_moisture"]    = moisture;
      doc["temperature"]      = temperature;
      doc["humidity"]         = humidity;
      doc["light_level"]      = lightLevel;
      doc["water_tank_level"] = tankLevel;

      String jsonPayload;
      serializeJson(doc, jsonPayload);

      // Compute HMAC-SHA256 signature
      String signature = computeHmacSha256(jsonPayload, HMAC_SECRET_KEY);

      // Issue HTTP POST Request
      HTTPClient http;
      http.begin(BACKEND_INGEST_URL);
      http.addHeader("Content-Type", "application/json");
      http.addHeader("x-api-key", DEVICE_API_KEY);
      http.addHeader("x-device-signature", signature);

      int httpResponseCode = http.POST(jsonPayload);

      if (httpResponseCode == 200) {
        String responseStr = http.getString();
        lastSuccessfulCloudContact = currentMillis;

        StaticJsonDocument<384> respDoc;
        DeserializationError err = deserializeJson(respDoc, responseStr);
        if (!err) {
          bool pumpActive = respDoc["pump_active"];
          float duration  = respDoc["pump_duration_seconds"];

          if (pumpActive && duration > 0.0) {
            // Guardrail against excessive duration
            float safeDuration = min(duration, MAX_HARDWARE_PUMP_RUNTIME_SEC);
            Serial.printf("[CLOUD COMMAND] Actuating pump for %.1f seconds...\n", safeDuration);
            pumpStartTime = millis();
            currentPumpDurationSeconds = safeDuration;
            setRelay(true);
          }
        }
      } else {
        Serial.printf("[HTTP ERROR] Ingestion failed. Status code: %d\n", httpResponseCode);
      }
      http.end();
    } else {
      Serial.println("[WIFI] Connection lost. Attempting reconnection...");
      WiFi.reconnect();
    }

    // 3. Fail-Safe Local Emergency Hysteresis (If disconnected > 5 mins)
    if (currentMillis - lastSuccessfulCloudContact > FAILSAFE_TIMEOUT_MS) {
      Serial.println("[FAILSAFE WARNING] Cloud unreachable > 5m. Evaluating local emergency hysteresis.");
      if (moisture < EMERGENCY_LOCAL_MIN_MOISTURE && !isPumpActive) {
        Serial.println("[FAILSAFE ACTION] Emergency local irrigation pulse triggered (3.0s).");
        pumpStartTime = millis();
        currentPumpDurationSeconds = 3.0; // Short emergency pulse
        setRelay(true);
      }
    }
  }

  delay(20); // FreeRTOS yield
}
