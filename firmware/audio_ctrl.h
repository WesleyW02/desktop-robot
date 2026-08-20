#ifndef AUDIO_CTRL_H
#define AUDIO_CTRL_H

#include <Arduino.h>

// =====================================================
// 音频：INMP441 麦克风（I2S 采集 + VAD）+ MAX98357A 功放（播放）
//
// ⚠️ 骨架阶段：接口与状态机完整，I2S 驱动实现待硬件实测时
//    按 ESP32 core 3.x 的 I2S API 填充（audio_init / audio_loop / audio_play_wav）。
// =====================================================

// 启动录音（开始 VAD 检测，触发后上行 audio 块）
void audio_start_capture(void);
// 停止录音（上行 vad end）
void audio_stop_capture(void);
// 录音/VAD 主循环（在 loop 调用）
void audio_loop(void);
// 播放 WAV（base64 解码 + I2S 输出）——骨架 TODO
void audio_play_wav(const char* base64_data, size_t wav_len);

#endif // AUDIO_CTRL_H
