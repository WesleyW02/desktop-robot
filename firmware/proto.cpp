// =====================================================
// 通信协议实现 v2.0（docs/protocol.md）
// 依赖：ArduinoJson v7（串口 JSON 行协议）
// =====================================================

#include "proto.h"
#include "config.h"
#include "servo_ctrl.h"
#include "motor_ctrl.h"
#include "display_ctrl.h"
#include "audio_ctrl.h"

static uint16_t _tx_seq = 0;   // 上行序号（自增）
static bool _ready = false;    // 握手完成标记

// ---------------- 发送工具 ----------------
static void send_line(JsonDocument& doc) {
  serializeJson(doc, Serial);
  Serial.write('\n');
  Serial.flush();
}

// ---------------- 上行：握手 ----------------
void proto_send_hello(void) {
  JsonDocument doc;
  doc["type"] = "hello";
  doc["fw"] = FW_VERSION;
  doc["proto_version"] = PROTO_VERSION;
  JsonArray caps = doc["capabilities"].to<JsonArray>();
  caps.add("audio_in");
  caps.add("audio_out");
  caps.add("display");
  caps.add("head");
  caps.add("chassis");
  caps.add("locate");
  caps.add("sleep");
  send_line(doc);
}

// ---------------- 上行：统一回执 ----------------
void proto_send_ack(const char* for_type, uint16_t seq, bool ok, const char* err) {
  JsonDocument doc;
  doc["type"] = "ack";
  doc["for"] = for_type;
  doc["seq"] = seq;
  doc["ok"] = ok;
  if (err) doc["err"] = err;
  send_line(doc);
}

// ---------------- 上行：错误消息 ----------------
void proto_send_err(uint16_t seq, const char* code, const char* msg) {
  JsonDocument doc;
  doc["type"] = "err";
  doc["code"] = code;
  doc["msg"] = msg;
  if (seq != 0xFFFF) doc["seq"] = seq;
  send_line(doc);
}

// ---------------- 上行：心跳响应 ----------------
void proto_send_pong(uint16_t seq) {
  JsonDocument doc;
  doc["type"] = "pong";
  doc["seq"] = seq;
  doc["uptime"] = millis() / 1000;
  send_line(doc);
}

// ---------------- 上行：状态上报 ----------------
void proto_send_telemetry(float bat, uint32_t free_heap) {
  JsonDocument doc;
  doc["type"] = "telemetry";
  doc["bat"] = bat;
  doc["free"] = free_heap;
  send_line(doc);
}

// ---------------- 上行：VAD / 敲击 ----------------
void proto_send_vad(bool start) {
  JsonDocument doc;
  doc["type"] = "vad";
  doc["state"] = start ? "start" : "end";
  send_line(doc);
}

void proto_send_knock(int angle) {
  JsonDocument doc;
  doc["type"] = "knock";
  doc["angle"] = angle;
  send_line(doc);
}

// ---------------- 下行分发 ----------------
static void handle_ping(JsonDocument& doc) {
  proto_send_pong(doc["seq"] | 0);
}

static void handle_face(JsonDocument& doc) {
  const char* expr = doc["expr"] | "idle";
  display_set_face(expr);
  proto_send_ack("face", doc["seq"] | 0, true, nullptr);
}

static void handle_text(JsonDocument& doc) {
  const char* text = doc["text"] | "";
  display_set_text(text);
  proto_send_ack("text", doc["seq"] | 0, true, nullptr);
}

static void handle_servo(JsonDocument& doc) {
  int ch = doc["ch"] | 0;
  int angle = doc["angle"] | 0;
  bool ok = servo_move(ch, angle);
  proto_send_ack("servo", doc["seq"] | 0, ok, ok ? nullptr : "0x10"); // 0x10 SERVO_LIMIT
}

static void handle_move(JsonDocument& doc) {
  const char* cmd = doc["cmd"] | "stop";
  int speed = doc["speed"] | MOVE_SPEED_DEF;
  motor_cmd(cmd, speed);
  proto_send_ack("move", doc["seq"] | 0, true, nullptr);
}

static void handle_mode(JsonDocument& doc) {
  const char* mode = doc["mode"] | "listen";
  if (strcmp(mode, "sleep") == 0) {
    // 骨架：深睡模式入口（Phase 5 实现）
  }
  proto_send_ack("mode", doc["seq"] | 0, true, nullptr);
}

static void handle_play(JsonDocument& doc) {
  // 骨架：播放 WAV（Phase 2 音频闭环实现解码+播放）
  // const char* b64 = doc["data"] | "";
  // size_t len = doc["len"] | 0;
  // audio_play_wav(b64, len);
  proto_send_ack("play", doc["seq"] | 0, true, nullptr);
}

static void handle_reboot(JsonDocument& doc) {
  (void)doc;
  proto_send_ack("reboot", doc["seq"] | 0, true, nullptr);
  delay(100);
  ESP.restart();
}

static void handle_hello_ack(JsonDocument& doc) {
  // 电脑确认握手：记录电脑协议版本/能力（骨架阶段仅置位）
  _ready = true;
}

// ---------------- 串口读行 + 分发 ----------------
void proto_handle_serial(void) {
  static String line = "";

  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      line.trim();
      if (line.length() > 0) {
        JsonDocument doc;
        DeserializationError err = deserializeJson(doc, line);
        if (err) {
          proto_send_err(0xFFFF, "0x01", "bad_json"); // 0x01 BAD_JSON
        } else {
          const char* type = doc["type"] | "";
          uint16_t seq = doc["seq"] | 0;
          if (strcmp(type, "ping") == 0)            handle_ping(doc);
          else if (strcmp(type, "face") == 0)       handle_face(doc);
          else if (strcmp(type, "text") == 0)       handle_text(doc);
          else if (strcmp(type, "servo") == 0)      handle_servo(doc);
          else if (strcmp(type, "move") == 0)       handle_move(doc);
          else if (strcmp(type, "mode") == 0)       handle_mode(doc);
          else if (strcmp(type, "play") == 0)       handle_play(doc);
          else if (strcmp(type, "reboot") == 0)     handle_reboot(doc);
          else if (strcmp(type, "hello_ack") == 0)  handle_hello_ack(doc);
          else {
            char msg[64];
            snprintf(msg, sizeof(msg), "unknown_type:%s", type);
            proto_send_err(seq, "0x02", msg);       // 0x02 UNKNOWN_TYPE
          }
        }
      }
      line = "";
    } else {
      if (line.length() < 16384) line += c; // 防超长行
    }
  }
}
