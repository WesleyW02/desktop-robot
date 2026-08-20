// =====================================================
// 音频骨架：VAD 状态机 + 播放接口占位
// （I2S 驱动待硬件实测按 core 3.x API 填充，见头文件说明）
// =====================================================

#include "audio_ctrl.h"
#include "config.h"
#include "proto.h"

static bool _capturing = false;
static uint32_t _silence_ms = 0;

void audio_start_capture(void) {
  _capturing = true;
  _silence_ms = 0;
  // TODO(core3.x): i2s_channel_register_event_callback / i2s_std_new 初始化 INMP441
  proto_send_vad(true);
}

void audio_stop_capture(void) {
  _capturing = false;
  proto_send_vad(false);
  // TODO: 关闭 I2S 通道
}

void audio_loop(void) {
  if (!_capturing) return;
  // TODO: 读 I2S 数据块 → 能量计算 → VAD 状态机（起始门限 VAD_ENERGY_THRESHOLD，
  //       静音 VAD_END_SILENCE_MS 判定）→ 上行 proto 音频块（每块 AUDIO_CHUNK）
  // 骨架阶段仅维持状态机，不实际采集。
  (void)_silence_ms;
}

void audio_play_wav(const char* base64_data, size_t wav_len) {
  (void)base64_data;
  (void)wav_len;
  // TODO(core3.x): base64 解码 → I2S 输出到 MAX98357A（播放完成后 ack 由上层发送）
}
