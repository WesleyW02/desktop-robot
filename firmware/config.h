#ifndef CONFIG_H
#define CONFIG_H

// =====================================================
// ESP32-S3 桌面机器人 · 引脚映射表 v1.0
// 板型：ESP32-S3-DevKitC-1 N16R8（16MB Flash + 8MB PSRAM）
// 注意：GPIO19/20=USB、GPIO26-32=Flash、GPIO33-37=PSRAM，均不可复用
// =====================================================

// ---- 串口（协议通信，UART0 经板载 USB 转串口）----
#define PIN_UART_TX 43
#define PIN_UART_RX 44

// ---- I2S 麦克风输入（INMP441）----
#define PIN_I2S_IN_BCLK 4
#define PIN_I2S_IN_WS   5
#define PIN_I2S_IN_DIN  6

// ---- I2S 功放输出（MAX98357A）----
#define PIN_I2S_OUT_BCLK 15
#define PIN_I2S_OUT_LRC  16
#define PIN_I2S_OUT_DIN  7

// ---- 屏幕 ST7789（SPI）----
#define PIN_TFT_SCK  12
#define PIN_TFT_MOSI 13
#define PIN_TFT_CS   10
#define PIN_TFT_DC    9
#define PIN_TFT_RST   8

// ---- 舵机（MG90S ×2）----
#define PIN_SERVO_PAN   18   // S1 摇头（水平 ±90°）
#define PIN_SERVO_TILT  21   // S2 点头（垂直 ±30°）

// ---- 电机驱动 TB6612 ----
#define PIN_MOTOR_AIN1  1    // 左马达
#define PIN_MOTOR_AIN2  2
#define PIN_MOTOR_PWMA  3
#define PIN_MOTOR_BIN1 14    // 右马达
#define PIN_MOTOR_BIN2 45
#define PIN_MOTOR_PWMB 48

// ---- 编码器（TT 马达霍尔编码器）----
#define PIN_ENC_LA 11        // 左 A 相
#define PIN_ENC_LB 40        // 左 B 相
#define PIN_ENC_RA 41        // 右 A 相
#define PIN_ENC_RB 42        // 右 B 相

// ---- 防跌落红外（TCRT5000，朝下）----
#define PIN_FALL_L 38
#define PIN_FALL_R 39

// ---- 声音唤醒（LM393 数字输出，Deep Sleep 唤醒）----
#define PIN_WAKE 0           // RTC GPIO，深睡可用

// =====================================================
// 常量
// =====================================================

// 音频参数
#define AUDIO_SAMPLE_RATE 16000
#define AUDIO_BITS       16
#define AUDIO_CHANNELS   1
#define AUDIO_CHUNK      4096        // 单块字节数（约 128ms）

// VAD 参数
#define VAD_ENERGY_THRESHOLD 800.0f  // 起始门限（调参）
#define VAD_END_SILENCE_MS   800     // 静音结束判定

// 舵机软限位（度）
#define SERVO_PAN_MIN   45
#define SERVO_PAN_MAX  135
#define SERVO_TILT_MIN  60
#define SERVO_TILT_MAX 120

// 移动参数
#define MOVE_PWM_MAX    255
#define MOVE_SPEED_DEF   60          // 默认速度 0-100

// 深睡参数
#define SLEEP_TIMEOUT_MS 30000       // 无交互超时进入深睡

#endif
