#ifndef PROTO_H
#define PROTO_H

#include <Arduino.h>
#include <ArduinoJson.h>

// =====================================================
// 通信协议层 v2.0（docs/protocol.md）
// 职责：串口读行 → JSON 解析 → 分发各模块 → 统一回执
// =====================================================

#define PROTO_VERSION "2.0"   // 协议版本
#define FW_VERSION    "0.1.0" // 固件版本

// ---- 发送接口（上行）----
void proto_send_hello(void);                       // 上电握手（含 proto_version + capabilities）
void proto_send_ack(const char* for_type, uint16_t seq, bool ok, const char* err); // 统一回执
void proto_send_err(uint16_t seq, const char* code, const char* msg);              // 错误消息
void proto_send_pong(uint16_t seq);                // 心跳响应
void proto_send_telemetry(float bat, uint32_t free_heap); // 状态上报
void proto_send_vad(bool start);                   // VAD 事件
void proto_send_knock(int angle);                  // 敲击定位
void proto_send_audio(const char* b64, size_t raw_len, uint16_t pts); // 音频块上行（base64）

// ---- 串口处理（下行）----
void proto_handle_serial(void);                    // 读串口 + 分发（在 loop 调用）

#endif // PROTO_H
