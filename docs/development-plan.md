# 桌面机器人 · 代码开发计划 v1.1

> 萌系可移动桌宠：ESP32-S3（感官终端）+ 电脑 Python Agent Hub（大脑）+ MiniMax 云
> 串口先行 / WiFi 可升级 · VAD 免按键 · 语音控制电脑 · 敲击定位 · 摇头点头

---

## 1. 技术选型

| 端 | 语言/框架 | 关键依赖 |
|----|-----------|----------|
| ESP32 固件 | **方案 A（已确认）**：Arduino 框架 + **C 风格编写**（函数/结构体/全局变量，不用 C++ 类），Arduino IDE 2.x | TFT_eSPI（屏幕）、ESP32Servo（舵机）、driver/i2s（音频）、ESP32Encoder（编码器）、ArduinoJson（协议） |
| 电脑端 Hub | Python 3.10+（venv 隔离） | pyserial、requests、pyautogui、pygetwindow、openai（MiniMax OpenAI 兼容协议） |
| 云端 | MiniMax Token Plan | M3（对话+工具）、ASR（语音转写）、Speech-2.8（TTS） |

**Python 环境隔离**：`python -m venv hub/.venv`，依赖写入 `hub/requirements.txt`，不污染系统环境。

**固件代码风格约定**（方案 A 落地规则）：
- 全部用 `static` 函数 + 结构体 + 全局变量，**不使用 class / 模板 / 异常**
- `.ino` 只放 setup/loop，业务逻辑放 `xxx.h + xxx.cpp`（C 风格头文件声明）
- 注释用 `//` 风格，中文注释

---

## 2. 目录结构

```
desktop_robot/
├── hub/                          # 电脑端 Agent Hub（Python）
│   ├── main.py                   # 入口：事件循环 + 模块装配
│   ├── config.yaml               # 串口、API Key、应用白名单（tools.yaml 引用）
│   ├── tools.yaml                # 应用白名单：应用名 → exe 路径
│   ├── serial_bridge.py          # 串口收发：读行解析 + 写行
│   ├── minimax_client.py         # ASR / M3 / TTS 三个 API 封装
│   ├── agent.py                  # Agent 核心：M3 对话 + 工具调用循环
│   ├── confirm.py                # 安全确认机制（危险操作 TTS 询问）
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── launch_app.py         # 启动白名单应用
│   │   ├── type_to_app.py        # 激活窗口 + 模拟输入
│   │   ├── shell.py              # 执行命令（白名单命令）
│   │   └── scheduler.py          # 定时任务 / 主动提醒
│   ├── robot_ctrl.py             # 高级动作编排（表情+动作+移动组合）
│   └── requirements.txt
├── firmware/                     # ESP32 固件（Arduino，C 风格）
│   ├── robot.ino                 # 主程序：初始化 + 主循环 + 状态机
│   ├── config.h                  # 引脚映射 + 常量（见下方引脚表）
│   ├── proto.h / proto.cpp       # JSON 行协议编解码（ArduinoJson）
│   ├── audio_in.h/.cpp           # I2S 录音 + VAD 检测 + 敲击脉冲检测
│   ├── audio_out.h/.cpp          # I2S 播放（WAV 流）
│   ├── display.h/.cpp            # ST7789 表情屏（大眼睛 + 文字）
│   ├── head.h/.cpp               # 双舵机：摇头(S1) + 点头(S2) + 软限位
│   ├── chassis.h/.cpp            # TB6612 电机驱动 + 编码器闭环 + 防跌落
│   ├── locate.h/.cpp             # 双麦 TDOA 敲击定位
│   └── sleep.h/.cpp              # Deep Sleep + LM393 GPIO 唤醒
└── docs/
    ├── protocol.md               # 通信协议规范（已交付）
    ├── wiring.md                 # 接线对照表（已交付引脚表）
    └── development-plan.md       # 本文件
```

---

## 3. 通信协议（USB 串口 · JSON 行 · 921600 波特率）

详见 `docs/protocol.md`。摘要：

**上行（机器人 → 电脑）**

| type | 字段 | 说明 |
|------|------|------|
| hello | fw | 上电握手 |
| audio | len, data(base64) | 录音数据块（16kHz/16bit/mono） |
| vad | state(start/end) | VAD 检测事件 |
| knock | angle | 敲击方向角（度，0=正前） |
| telemetry | bat, free | 电池电压、内存余量 |

**下行（电脑 → 机器人）**

| type | 字段 | 说明 |
|------|------|------|
| play | fmt, len, data(base64) | 播放音频（WAV 16k） |
| face | expr(happy/sad/thinking/idle) | 表情指令 |
| text | text | 屏幕显示文字 |
| servo | ch(1/2), angle | 摇头/点头 |
| move | cmd, speed, dist_cm | 前进/后退/左转/右转/停止 |
| locate | cmd(start/stop) | 启动敲击定位 |
| mode | mode(listen/sleep) | 工作模式切换 |
| reboot | - | 重启 |

---

## 4. ESP32-S3 引脚映射（config.h，已定稿）

```
UART0（USB 串口，协议通信）: TX=43, RX=44
I2S 麦克风输入: BCLK=4, WS=5, DIN=6
I2S 功放输出:   BCLK=15, LRC=16, DIN=7
屏幕 ST7789:    SCK=12, MOSI=13, CS=10, DC=9, RST=8
舵机: 摇头 S1=18, 点头 S2=21
电机 TB6612:    AIN1=1, AIN2=2, PWMA=3（左）
                BIN1=14, BIN2=45, PWMB=48（右）
编码器: 左 A=11/B=40, 右 A=41/B=42
防跌落: TCRT5000 L=38, R=39
唤醒: LM393=GPIO0（RTC 深睡唤醒）
```

注意：GPIO19/20 为 USB 原生接口、GPIO26-32 为 Flash、GPIO33-37 为 PSRAM（N16R8），**均不可复用**。

---

## 4.5 Phase 0：电脑端先行（硬件未到，当前进行中）

> 现状：ESP32 板子未到货 → 优先打通 **电脑端 Agent Hub ↔ MiniMax 云** 全链路
> 此阶段不依赖任何硬件，可完整验证：MiniMax Key 有效性、ASR/M3/TTS 三接口、工具调用框架

**Phase 0 任务分解（本轮）**
- [x] `docs/protocol.md` 通信协议定稿
- [x] `firmware/config.h` 引脚映射定稿（板子到手直接用）
- [ ] `hub/minimax_client.py`：ASR / M3 / TTS 三接口封装
- [ ] `hub/test_minimax.py`：联通测试脚本（验证 Key + 三接口）
- [ ] `hub/main.py`：文本交互入口（输入 → M3 → TTS → 电脑播放）
- [ ] `hub/agent.py` + `hub/tools/*`：M3 工具调用框架（launch_app / shell，白名单）
- [ ] `hub/requirements.txt`、`config.example.yaml`
- **验收标准**：`python test_minimax.py` 全部通过；文本对话可听 M3 回复语音

**Phase 0 之后**（板子到手）→ 进入 Phase 1：串口 + 屏幕点亮

---

## 5. 五阶段开发任务分解

### Phase 1：工程骨架 + 串口打通（约 1 天）
- [ ] 建 `hub/` 与 `firmware/` 工程骨架、requirements.txt
- [ ] ESP32：`config.h` 引脚映射 + `proto` JSON 编解码 + hello 握手
- [ ] Hub：`serial_bridge` 收发 + 命令行测试工具（发 face/text 指令）
- [ ] 屏幕点亮：`display` 显示静态表情（大眼睛）
- **验收**：电脑命令下发 `{"type":"face","expr":"happy"}`，机器人屏幕显示表情

### Phase 2：MiniMax 语音链路（1-2 天）
- [ ] `minimax_client`：ASR / M3 / TTS 三接口封装 + 独立测试脚本（**不依赖硬件，先验证 Key**）
- [ ] ESP32 `audio_in`：I2S 录音 + VAD（能量检测）+ 上传录音流
- [ ] ESP32 `audio_out`：接收音频流播放
- [ ] Hub `main`：VAD 事件 → ASR → M3 → TTS → 下发播放，完成语音闭环
- **验收**：先键盘文本闭环（M3→TTS 出声），再语音闭环（说话→机器人回答）

### Phase 3：Agent 工具调用（1-2 天）——核心能力
- [x] `agent.py`：**ReAct 框架 v2**——对话/行动分流；行动先规划（submit_plan 协议工具）
  后执行（每步 思考→行动→观察）；三场景实测通过（纯对话 / 行动计划 / MCP 工具）
- [x] `tools/` 工具包：launch_app / type_to_app / shell / scheduler（白名单在 config.yaml）
- [x] `tools/type_to_app`：pygetwindow 激活 + 剪贴板粘贴（支持中文，中英文窗口标题兼容）
- [x] `tools/shell`：白名单命令执行（前缀匹配，只读为主）
- [x] `confirm.py`：危险操作分级确认（low/medium/high，high 弹确认）
- [x] `test_tools.py`：5 项测试全通过（含真实 M3 工具调用循环）
- [x] **MCP 扩展**：`mcp_tools.py` 动态加载层 + `test_mcp_server.py` 演示服务器，
  M3 实测自主调用 `mcp_test_server_get_time` 成功（config.yaml → mcp.servers 即插即用）
- **验收**：文本输入"列出当前目录文件" → M3 自动调 shell(dir) → 回填汇报 ✅；
  语音版（Phase 2 语音闭环后）：说"打开 WorkBuddy 发消息"全流程自动完成

### Phase 4：移动 + 敲击定位（2-3 天）
- [ ] `chassis`：TB6612 双电机 PWM 控制 + 编码器计数 + 直线走（PID 可选）
- [ ] `chassis`：防跌落状态机（TCRT5000 触发立即刹停+后退）
- [ ] `locate`：双麦同步采样 + 互相关时延估计 + 角度解算 + 迭代逼近
- [ ] move/locate 协议指令贯通 Hub
- **验收**：桌面敲击 → 转向声源 → 前进（防跌落保护）→ 到达停止

### Phase 5：深睡待机 + 拟人化（2-3 天）
- [ ] `sleep`：Deep Sleep + LM393 GPIO 唤醒 + 唤醒后外设重初始化
- [ ] `display` 表情动画库（眨眼、笑、思考）
- [ ] `scheduler`：定时任务 + 主动播报（开会提醒、构建完成汇报）
- [ ] 外壳适配：安装孔位、电池仓、充电口/麦克风开孔核对
- **验收**：待机功耗实测（目标 <5mA）、全功能联调、拆壳装壳无障碍

---

## 6. 环境准备清单

1. **电脑**：Python 3.10+；安装 `hub/requirements.txt`（pyserial/requests/openai/pyautogui/pygetwindow）
2. **MiniMax Key**：Token Plan 订阅 Key（写环境变量 `MINIMAX_API_KEY`，**不硬编码进代码**）
3. **Arduino IDE 2.x** + ESP32-S3 板卡包（espressif 官方源）；装库：TFT_eSPI、ESP32Servo、ArduinoJson、ESP32Encoder
4. **TFT_eSPI 配置**：User_Setup.h 按 ST7789 + 引脚表修改（Phase 1 给具体配置）
5. **串口**：Windows 设备管理器确认 COM 口

---

## 7. 待确认事项（开工前）

| # | 事项 | 说明 |
|---|------|------|
| 1 | MiniMax Key 类型 | Token Plan 订阅 Key / 按量 API Key（影响请求方式） |
| 2 | WorkBuddy 可执行文件路径 | 填入 tools.yaml 白名单（Phase 3 前提供即可） |
| 3 | Arduino IDE 已装？ | 未装则 Phase 1 给安装步骤 |
| 4 | 电脑端 Python 版本 | 确认 3.10+（建议 3.11/3.12） |

---

## 8. 质量与安全原则

- API Key 一律走环境变量 / config.yaml（gitignore），不落代码
- 工具执行全部白名单化（应用白名单 + 命令白名单），危险操作（启动/输入/删除）前 TTS 询问用户确认
- 电机/舵机动作全部软限位，防跌落为最高优先级中断（任何移动指令不得越过防跌落保护）
- 代码分阶段交付：每阶段先出骨架→跑通→再扩展，增量迭代，可随时在任意阶段暂停/验收
