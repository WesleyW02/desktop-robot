# 通信协议规范 v1.0

> 桌面机器人 电脑端 Agent Hub ↔ ESP32 固件
> 传输：USB 串口（UART0，GPIO43/44），波特率 921600
> 格式：JSON 行协议（每行一个完整 JSON 对象，`\n` 结尾，UTF-8）

---

## 1. 帧格式

```
{json}\n
```

- 单行 JSON，不包含换行符（字符串内的换行需转义 `\n`）
- 编码器收到按行读取，校验 JSON 合法性后分发
- 音频等二进制数据用 **Base64** 编码放入 `data` 字段

---

## 2. 上行消息（机器人 → 电脑）

### hello — 上电握手
```json
{"type":"hello","fw":"1.0.0"}
```
电脑收到后应回复 `{"type":"mode","mode":"listen"}` 确认就绪。

### audio — 录音数据块
```json
{"type":"audio","len":4096,"data":"<base64>"}
```
- 格式：PCM 16kHz / 16bit / 单声道
- 每块 4096 字节（约 128ms），连续发送直到 VAD end

### vad — 语音活动检测事件
```json
{"type":"vad","state":"start"}
{"type":"vad","state":"end"}
```
- `start`：检测到人声，开始进入对话流程
- `end`：静音超时（默认 800ms），录音结束

### knock — 敲击定位结果
```json
{"type":"knock","angle":32}
```
- `angle`：声源相对机器人正前方的偏角（度），-90 ~ +90，左负右正

### telemetry — 状态上报
```json
{"type":"telemetry","bat":3.85,"free":260000}
```
- `bat`：电池电压（V），`free`：剩余堆内存（字节）
- 周期性上报（默认 30s）或电量变化时上报

---

## 3. 下行消息（电脑 → 机器人）

### play — 播放音频
```json
{"type":"play","fmt":"wav_16k","len":24680,"data":"<base64>"}
```
- 支持 `wav_16k`（16kHz 16bit 单声道，含 44 字节 WAV 头）
- 播放完成后机器人回 `{"type":"ack","for":"play"}`

### face — 表情
```json
{"type":"face","expr":"happy"}
```
- 枚举：`happy` `sad` `thinking` `idle` `sleep` `surprise`

### text — 屏幕文字
```json
{"type":"text","text":"任务已完成"}
```

### servo — 舵机动作
```json
{"type":"servo","ch":1,"angle":90}
```
- `ch=1` 摇头（软限位 45~135），`ch=2` 点头（软限位 60~120）

### move — 移动指令
```json
{"type":"move","cmd":"forward","speed":60,"dist_cm":15}
```
- `cmd`：`forward` `back` `left` `right` `stop`
- `speed`：PWM 0-100，`dist_cm`：目标距离（可选，0=持续移动）
- 防跌落触发时自动刹车，回 `{"type":"telemetry","fall":1}`

### locate — 敲击定位
```json
{"type":"locate","cmd":"start"}
{"type":"locate","cmd":"stop"}
```
- 启动后机器人进入监听模式，检测到敲击回 `knock`

### mode — 工作模式
```json
{"type":"mode","mode":"listen"}
{"type":"mode","mode":"sleep"}
```
- `listen`：监听模式（VAD 生效）
- `sleep`：进入 Deep Sleep（由 LM393 声音唤醒）

### reboot — 重启
```json
{"type":"reboot"}
```

---

## 4. 交互时序示例

### 一次语音对话
```
机器人: {"type":"hello","fw":"1.0.0"}
电脑:   {"type":"mode","mode":"listen"}
机器人: {"type":"vad","state":"start"}
机器人: {"type":"audio","len":4096,"data":"..."}   (×N)
机器人: {"type":"vad","state":"end"}
电脑:   (ASR→M3→TTS 处理)
电脑:   {"type":"face","expr":"thinking"}
电脑:   {"type":"play","fmt":"wav_16k","len":24680,"data":"..."}
机器人: {"type":"ack","for":"play"}
```

### 敲击定位
```
电脑:   {"type":"locate","cmd":"start"}
机器人: (监听敲击)
机器人: {"type":"knock","angle":32}
电脑:   {"type":"move","cmd":"left","speed":50,"dist_cm":0}   (转向)
电脑:   {"type":"move","cmd":"forward","speed":60,"dist_cm":20}
机器人: (中途再听敲击修正...)
```

---

## 5. 容错约定

- 无法解析的行 → 丢弃并回 `{"type":"err","msg":"bad_json"}`
- 未知 type → 回 `{"type":"err","msg":"unknown_type:<type>"}`
- 音频传输中断（超 5s 无数据）→ 视为播放/录音失败，双端重置缓冲
- 波特率不匹配表现为乱码 → 检查串口参数 921600-8-N-1
