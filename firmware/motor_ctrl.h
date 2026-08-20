#ifndef MOTOR_CTRL_H
#define MOTOR_CTRL_H

#include <Arduino.h>

// =====================================================
// 底盘电机（TB6612 双路）+ 编码器 + 防跌落
// =====================================================

void motor_init(void);
// 移动指令：cmd = forward / back / left / right / stop
void motor_cmd(const char* cmd, int speed);
// 立即刹停（防跌落等紧急情况）
void motor_brake(void);
// 防跌落检查（任一传感器触发返回 true 并已刹停）
bool motor_fall_check(void);
// 编码器计数（左右）
long motor_enc_left(void);
long motor_enc_right(void);

#endif // MOTOR_CTRL_H
