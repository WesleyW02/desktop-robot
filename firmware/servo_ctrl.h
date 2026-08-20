#ifndef SERVO_CTRL_H
#define SERVO_CTRL_H

#include <Arduino.h>
#include <ESP32Servo.h>

// =====================================================
// 头部舵机（MG90S ×2）：摇头(pan) / 点头(tilt)，软限位
// =====================================================

void servo_init(void);
// 移动舵机：ch=1 摇头 / ch=2 点头；越软限位返回 false（上层回 ack 0x10）
bool servo_move(int ch, int angle);
// 复位到中间位置
void servo_center(void);

#endif // SERVO_CTRL_H
