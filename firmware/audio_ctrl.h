#ifndef AUDIO_CTRL_H
#define AUDIO_CTRL_H

#include <Arduino.h>

// =====================================================
// 音频：INMP441 麦克风（I2S 采集 + VAD + 上行）+ MAX98357A 功放（播放）
//
// 采集：I2S RX 32bit 槽（INMP441 24bit）→ 取高 16bit → int16 PCM
// VAD ：能量检测，超 VAD_ENERGY_THRESHOLD 起录（vad start），
//       静音超 VAD_END_SILENCE_MS 结束（vad end），期间按块上行 audio
// 播放：base64 解码 → I2S TX 16bit → MAX98357A
// =====================================================

void audio_init(void);           // I2S 双通道初始化
void audio_loop(void);           // 采集 + VAD 状态机（loop 调用）
void audio_play_wav(const char* base64_data, size_t wav_len); // 播放 WAV（阻塞）

#endif // AUDIO_CTRL_H
