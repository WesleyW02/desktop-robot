// =====================================================
// 头部舵机实现：ESP32Servo + 软限位
// =====================================================

#include "servo_ctrl.h"
#include "config.h"

static Servo _pan;
static Servo _tilt;
static int _pan_angle = (SERVO_PAN_MIN + SERVO_PAN_MAX) / 2;
static int _tilt_angle = (SERVO_TILT_MIN + SERVO_TILT_MAX) / 2;

static int clamp_angle(int v, int lo, int hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

void servo_init(void) {
  _pan.attach(PIN_SERVO_PAN);
  _tilt.attach(PIN_SERVO_TILT);
  _pan.write(_pan_angle);
  _tilt.write(_tilt_angle);
}

bool servo_move(int ch, int angle) {
  if (ch == 1) {
    if (angle < SERVO_PAN_MIN || angle > SERVO_PAN_MAX) return false;
    _pan_angle = angle;
    _pan.write(_pan_angle);
    return true;
  }
  if (ch == 2) {
    if (angle < SERVO_TILT_MIN || angle > SERVO_TILT_MAX) return false;
    _tilt_angle = angle;
    _tilt.write(_tilt_angle);
    return true;
  }
  return false; // 未知通道
}

void servo_center(void) {
  _pan_angle = (SERVO_PAN_MIN + SERVO_PAN_MAX) / 2;
  _tilt_angle = (SERVO_TILT_MIN + SERVO_TILT_MAX) / 2;
  _pan.write(_pan_angle);
  _tilt.write(_tilt_angle);
}
