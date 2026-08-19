# 通信协议规范 v2.0

> 桌面机器人 电脑端 Agent Hub ↔ ESP32 固件
> 传输：USB 串口（UART0，GPIO43/44），波特率 921600
> 格式：JSON 行协议（每行一个完整 JSON 对象，`\n` 结尾，UTF-8）

**v2.0 新增能力**（对 v1 向下兼容，旧消息可省略 `seq`）：
- 消息序号 `seq` + 统一回执 `ack`，指令可追溯
- 机器可读错误码 `err.code`（替代纯文本描述）
- 握手版本协商 `proto_version` + 能力上报 `capabilities`
- `ping` / `pong` 心跳保活，断线可感知
- 音频分片与流控规范（半双工排队 + 优先级）

---

## 1. 帧格式（与 v1 一致）

```
{json}\n
```

- 单行 JSON，不包含换行符（字符串内换行转义 `\n`）
- 接收端按行读取，校验 JSON 合法性后分发
- 二进制数据（音频）用 **Base64** 编码放入 `data` 字段

---

## 2. 通用机制（v2.0 新增）

### 2.1 消息序号 seq

所有消息可携带 `seq`（发送方自增，环形 0~65535）：

```json
{"type":"move","cmd":"forward","seq":42}
```

接收方回执时原样带回，用于请求/响应配对、乱序检测。

### 2.2 统一回执 ack

**下行指令**执行后，机器人必须回 `ack`（成功或失败）：

```json
{"type":"ack","for":"move","seq":42,"ok":true}
{"type":"ack","for":"play","seq":43,"ok":false,"err":"0x04"}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| for | string | 回执对应的消息 type |
| seq | int | 对应请求的序号（原样返回） |
| ok | bool | 是否执行成功 |
| err | string | 失败时的错误码（十六进制，见 2.3） |

> 例外：流式/事件类（audio 数据块）与上行消息不回 ack，避免风暴。

### 2.3 错误码表 err.code

| 码 | 名称 | 含义 |
|----|------|------|
| 0x00 | OK | 成功 |
| 0x01 | BAD_JSON | 无法解析的 JSON 行 |
| 0x02 | UNKNOWN_TYPE | 未知消息 type |
| 0x03 | BAD_PARAM | 参数缺失/非法 |
| 0x04 | TIMEOUT | 操作超时（音频传输中断 >5s 等） |
| 0x05 | BUSY | 忙（正在播放/移动，拒绝新指令） |
| 0x06 | UNSUPPORTED | 能力不支持（见 capabilities） |
| 0x10 | SERVO_LIMIT | 舵机越软限位 |
| 0x11 | FALL_EDGE | 防跌落触发（移动被强制刹停） |
| 0xFF | INTERNAL | 内部错误 |

错误消息统一格式：

```json
{"type":"err","code":"0x02","msg":"unknown_type:foo","seq":5}
```

### 2.4 心跳 ping / pong

电脑 → 机器人 `ping`，机器人立即回 `pong`：

```json
{"type":"ping","seq":100}
{"type":"pong","seq":100,"uptime":86400}
```

- 电脑侧默认每 10s 发一次；连续 3 次无 `pong` 判定离线 → 走重连流程
- `pong.uptime`：机器人运行秒数（调试用）

---

## 3. 握手（v2.0 升级）

### 上电握手（电脑 → 机器人 hello_ack）

```json
机器人: {"type":"hello","fw":"1.0.0","proto_version":"2.0","capabilities":["audio_in","audio_out","display","head","chassis","locate","sleep"]}
电脑:   {"type":"hello_ack","proto_version":"2.0","mode":"listen","capabilities":["asr","tts","mcp"]}
```

| 字段 | 说明 |
|------|------|
| proto_version | 协议版本（主.次），双方取 min 主版本兼容 |
| capabilities | 能力列表：机器人上报硬件能力，电脑上报服务能力 |
| mode | 电脑确认的工作模式（listen / sleep） |

约定：若机器人 `proto_version` 主版本高于电脑支持值，电脑仍按自己最大兼容版本工作并回 `hello_ack` 注明。

---

## 4. 上行消息（机器人 → 电脑）

### hello — 上电握手（见 §3）

### audio — 录音数据块

```json
{"type":"audio","seq":1,"len":4096,"data":"<base64>","pts":0}
```

- 格式：PCM 16kHz / 16bit / 单声道
- `pts`：块序号（从 0 递增），电脑用于检测丢块
- 每块 4096 字节（约 128ms），连续发送直到 VAD end

### vad — 语音活动检测事件

```json
{"type":"vad","state":"start"}
{"type":"vad","state":"end"}
```

### knock — 敲击定位结果

```json
{"type":"knock","angle":32}
```

### telemetry — 状态上报

```json
{"type":"telemetry","bat":3.85,"free":260000}
```

- 周期 30s 或电量变化时上报
- 防跌落触发时：`{"type":"telemetry","fall":1}`（与 v1 一致）

---

## 5. 下行消息（电脑 → 机器人）

### play — 播放音频

```json
{"type":"play","seq":43,"fmt":"wav_16k","len":24680,"data":"<base64>"}
```

- 支持 `wav_16k`（16kHz 16bit 单声道，含 44 字节 WAV 头）
- 播放完成回 `{"type":"ack","for":"play","seq":43,"ok":true}`

### face — 表情

```json
{"type":"face","expr":"happy"}
```

枚举：`happy` `sad` `thinking` `idle` `sleep` `surprise`

### text — 屏幕文字

```json
{"type":"text","text":"任务已完成"}
```

### servo — 舵机动作

```json
{"type":"servo","ch":1,"angle":90}
```

- `ch=1` 摇头（软限位 45~135），`ch=2` 点头（软限位 60~120）
- 越限回 `ack ok:false err:0x10`

### move — 移动指令

```json
{"type":"move","cmd":"forward","speed":60,"dist_cm":15}
```

- `cmd`：`forward` `back` `left` `right` `stop`
- 防跌落触发自动刹车，回 `{"type":"telemetry","fall":1}` 且本指令 `ack ok:false err:0x11`

### locate — 敲击定位

```json
{"type":"locate","cmd":"start"}
{"type":"locate","cmd":"stop"}
```

### mode — 工作模式

```json
{"type":"mode","mode":"listen"}
{"type":"mode","mode":"sleep"}
```

### reboot — 重启

```json
{"type":"reboot"}
```

---

## 6. 音频传输与流控（v2.0 规范）

串口为**半双工**（同一时刻只能一方发送），遵循：

1. **分片上限**：单条消息 ≤ 8KB（Base64 编码前）。WAV 数据超限必须分片（play 可分多条，末片 `last:true`）
2. **发送排队**：任一方一次只发一条；收到回复前不抢占。播放期间新指令回 `ack ok:false err:0x05 BUSY`
3. **优先级**：控制指令（move/servo/reboot）> 语音（play/audio）> 状态（telemetry）
4. **互斥**：上行 audio 流进行中，电脑不下发 play（语音双向互斥）；需打断时先发 `mode` 或等 VAD end
5. **缓冲重置**：任一方向超 5s 无数据 → 视为传输中断，双端重置缓冲，中断方发 `err 0x04`

---

## 7. 交互时序示例

### 语音对话（含回执）

```
机器人: {"type":"hello","fw":"1.0.0","proto_version":"2.0","capabilities":[...]}
电脑:   {"type":"hello_ack","proto_version":"2.0","mode":"listen","capabilities":[...]}
电脑:   {"type":"ping","seq":1}
机器人: {"type":"pong","seq":1,"uptime":3}
机器人: {"type":"vad","state":"start"}
机器人: {"type":"audio","seq":0,"len":4096,"data":"..."}   (×N)
机器人: {"type":"vad","state":"end"}
电脑:   (ASR→M3→TTS 处理)
电脑:   {"type":"face","expr":"thinking"}
电脑:   {"type":"play","seq":10,"fmt":"wav_16k","len":24680,"data":"..."}
机器人: {"type":"ack","for":"play","seq":10,"ok":true}
```

### 敲击定位

```
电脑:   {"type":"locate","cmd":"start"}
机器人: (监听敲击)
机器人: {"type":"knock","angle":32}
电脑:   {"type":"move","cmd":"left","speed":50,"seq":20}
机器人: {"type":"ack","for":"move","seq":20,"ok":true}
电脑:   {"type":"move","cmd":"forward","speed":60,"dist_cm":20,"seq":21}
机器人: (中途再听敲击修正...)
```

---

## 8. 容错约定（v2.0 更新）

- 无法解析的行 → 回 `{"type":"err","code":"0x01","msg":"bad_json"}`
- 未知 type → 回 `{"type":"err","code":"0x02","msg":"unknown_type:<type>"}`
- 参数非法 → 回 `{"type":"err","code":"0x03","msg":"bad_param:<field>"}`
- 忙状态 → 回 `ack ok:false err:0x05`
- 音频传输中断（超 5s 无数据）→ 双端重置缓冲，回 `err 0x04`
- 心跳超时（电脑侧 30s 无 pong）→ 视为离线，走重连（重新 hello 握手）
- 波特率不匹配表现为乱码 → 检查串口参数 921600-8-N-1
