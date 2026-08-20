// =====================================================
// 音频实现：INMP441 采集 + VAD + base64 上行；MAX98357A 播放
// 依赖：ESP32 core 3.x（legacy driver/i2s.h API）
// =====================================================

#include "audio_ctrl.h"
#include "config.h"
#include "proto.h"

#include <driver/i2s.h>

// ---- I2S 通道：0=麦克风 RX，1=喇叭 TX ----
#define I2S_MIC  I2S_NUM_0
#define I2S_SPK  I2S_NUM_1

// ---- VAD 状态 ----
enum { VAD_IDLE, VAD_CAPTURE };
static int _vad_state = VAD_IDLE;
static uint32_t _silence_ms = 0;
static uint16_t _pts = 0;

// 上行块缓冲：AUDIO_CHUNK(4096) 字节 PCM → base64(5464 字符)
#define B64_LEN (4 * ((AUDIO_CHUNK + 2) / 3) + 1)
static int16_t _chunk[AUDIO_CHUNK / 2];
static size_t _chunk_n = 0;
static char _b64buf[B64_LEN];

// =====================================================
// base64（标准表）
// =====================================================
static const char B64T[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static void b64_encode(const uint8_t* in, size_t len, char* out) {
  size_t o = 0;
  for (size_t i = 0; i < len; i += 3) {
    uint32_t n = ((uint32_t)in[i]) << 16;
    if (i + 1 < len) n |= ((uint32_t)in[i + 1]) << 8;
    if (i + 2 < len) n |= in[i + 2];
    out[o++] = B64T[(n >> 18) & 63];
    out[o++] = B64T[(n >> 12) & 63];
    out[o++] = (i + 1 < len) ? B64T[(n >> 6) & 63] : '=';
    out[o++] = (i + 2 < len) ? B64T[n & 63] : '=';
  }
  out[o] = '\0';
}

static int b64_val(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

static size_t b64_decode(const char* in, uint8_t* out) {
  size_t o = 0;
  uint32_t buf = 0;
  int bits = 0;
  for (; *in; ++in) {
    if (*in == '=' || *in == '\n' || *in == '\r') break;
    int v = b64_val(*in);
    if (v < 0) continue;
    buf = (buf << 6) | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out[o++] = (uint8_t)(buf >> bits);
    }
  }
  return o;
}

// =====================================================
// I2S 初始化
// =====================================================
void audio_init(void) {
  // ---- 麦克风 RX（INMP441：24bit 放入 32bit 槽）----
  i2s_config_t mic_cfg = {};
  mic_cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  mic_cfg.sample_rate = AUDIO_SAMPLE_RATE;
  mic_cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  mic_cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  mic_cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  mic_cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  mic_cfg.dma_buf_count = 8;
  mic_cfg.dma_buf_len = 1024;

  i2s_pin_config_t mic_pins = {};
  mic_pins.bck_io_num = PIN_I2S_IN_BCLK;
  mic_pins.ws_io_num = PIN_I2S_IN_WS;
  mic_pins.data_out_num = I2S_PIN_NO_CHANGE;
  mic_pins.data_in_num = PIN_I2S_IN_DIN;

  i2s_driver_install(I2S_MIC, &mic_cfg, 0, nullptr);
  i2s_set_pin(I2S_MIC, &mic_pins);
  i2s_zero_dma_buffer(I2S_MIC);

  // ---- 喇叭 TX（MAX98357A：16bit 双声道 I2S）----
  i2s_config_t spk_cfg = {};
  spk_cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  spk_cfg.sample_rate = AUDIO_SAMPLE_RATE;
  spk_cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  spk_cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  spk_cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  spk_cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  spk_cfg.dma_buf_count = 8;
  spk_cfg.dma_buf_len = 1024;

  i2s_pin_config_t spk_pins = {};
  spk_pins.bck_io_num = PIN_I2S_OUT_BCLK;
  spk_pins.ws_io_num = PIN_I2S_OUT_LRC;
  spk_pins.data_out_num = PIN_I2S_OUT_DIN;
  spk_pins.data_in_num = I2S_PIN_NO_CHANGE;

  i2s_driver_install(I2S_SPK, &spk_cfg, 0, nullptr);
  i2s_set_pin(I2S_SPK, &spk_pins);
  i2s_zero_dma_buffer(I2S_SPK);
}

// =====================================================
// 采集 + VAD 状态机
// =====================================================
static void flush_chunk(void) {
  if (_chunk_n == 0) return;
  b64_encode((const uint8_t*)_chunk, _chunk_n * 2, _b64buf);
  proto_send_audio(_b64buf, _chunk_n * 2, _pts++);
  _chunk_n = 0;
}

void audio_loop(void) {
  int32_t buf32[512];
  size_t bytes_read = 0;
  // 非阻塞读麦克风（每块 512 × 4B = 2KB）
  esp_err_t err = i2s_read(I2S_MIC, buf32, sizeof(buf32), &bytes_read, 0);
  if (err != ESP_OK || bytes_read == 0) return;

  size_t samples = bytes_read / 4;
  float energy_sum = 0.0f;
  for (size_t i = 0; i < samples; ++i) {
    int16_t s = (int16_t)(buf32[i] >> 16); // 32bit 槽取高 16bit
    energy_sum += (float)s * s;
    if (_vad_state == VAD_CAPTURE) {
      _chunk[_chunk_n++] = s;
      if (_chunk_n >= AUDIO_CHUNK / 2) flush_chunk();
    }
  }
  float rms = sqrtf(energy_sum / samples);
  uint32_t block_ms = samples * 1000 / AUDIO_SAMPLE_RATE; // 本块实际时长

  if (_vad_state == VAD_IDLE) {
    if (rms > VAD_ENERGY_THRESHOLD) {
      _vad_state = VAD_CAPTURE;
      _silence_ms = 0;
      _pts = 0;
      _chunk_n = 0;
      proto_send_vad(true);
    }
  } else {
    _silence_ms = (rms < VAD_ENERGY_THRESHOLD) ? (_silence_ms + block_ms) : 0;
    if (_silence_ms >= VAD_END_SILENCE_MS) {
      flush_chunk();
      _vad_state = VAD_IDLE;
      proto_send_vad(false);
    }
  }
}

// =====================================================
// 播放 WAV（base64 解码 → I2S 输出，阻塞至播完）
// =====================================================
void audio_play_wav(const char* base64_data, size_t wav_len) {
  static uint8_t dec_buf[16384];
  size_t total = wav_len ? wav_len : strlen(base64_data) * 3 / 4;
  size_t dec = b64_decode(base64_data, dec_buf);
  if (dec > total) dec = total;
  // 跳过 WAV 头（44 字节），只送 PCM
  const uint8_t* pcm = dec_buf + 44;
  size_t pcm_len = (dec > 44) ? (dec - 44) : 0;
  size_t written = 0;
  while (written < pcm_len) {
    size_t w = 0;
    i2s_write(I2S_SPK, pcm + written, pcm_len - written, &w, 100);
    if (w == 0) break; // 超时防死循环
    written += w;
  }
  i2s_zero_dma_buffer(I2S_SPK);
}
