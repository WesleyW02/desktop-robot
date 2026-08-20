// =====================================================
// 桌面机器人 · 主程序（Phase 1 骨架）
//
// 启动流程：
//   setup   → 串口 921600 → 各模块 init → 上行 hello 握手
//   loop    → 串口下行分发（proto_handle_serial）
//           → 防跌落检查（紧急刹停 + 上报）
//           → 音频 VAD 状态机（骨架）
//           → 周期 telemetry
//
// 协议 v2.0 见 docs/protocol.md
// =====================================================

#include "config.h"
#include "proto.h"
#include "servo_ctrl.h"
#include "motor_ctrl.h"
#include "display_ctrl.h"
#include "audio_ctrl.h"

static uint32_t _last_telemetry = 0;

void setup() {
  // ---- 串口（协议通道）----
  Serial.begin(921600);
  Serial.setTimeout(50);

  // ---- 硬件初始化 ----
  servo_init();
  motor_init();
  display_init();
  // audio_init() 待 I2S 实现后启用（骨架阶段不初始化）

  // ---- 表情：开机开心脸 ----
  display_set_face("happy");

  // ---- 上行握手（协议 v2.0）----
  delay(200); // 等电脑端串口就绪
  proto_send_hello();
}

void loop() {
  // 1) 下行指令分发（face/text/servo/move/play/mode/ping...）
  proto_handle_serial();

  // 2) 防跌落：触发 → 刹停（0x11 由上层移动指令回执体现）
  if (motor_fall_check()) {
    // 骨架：触发后置位，telemetry 上报 fall 状态（Phase 4 完善）
  }

  // 3) 音频 VAD 状态机（骨架）
  audio_loop();

  // 4) 周期状态上报（30s）
  uint32_t now = millis();
  if (now - _last_telemetry >= 30000) {
    _last_telemetry = now;
    proto_send_telemetry(3.85f, ESP.getFreeHeap());
  }
}
