// =====================================================
// 底盘电机实现：TB6612 双路 PWM + 编码器计数 + 防跌落
// =====================================================

#include "motor_ctrl.h"
#include "config.h"

static volatile long _enc_left = 0;
static volatile long _enc_right = 0;
static bool _falling = false;

// ---- 编码器中断（A 相上升沿计数）----
static void IRAM_ATTR enc_left_isr(void)  { _enc_left++; }
static void IRAM_ATTR enc_right_isr(void) { _enc_right++; }

static void motor_write(int ain1, int ain2, int pwm, bool dir_fwd, int speed) {
  // dir_fwd=true → 前进方向；speed 0-100 → 映射到 0-255
  int p = constrain(speed, 0, MOVE_PWM_MAX);
  digitalWrite(ain1, dir_fwd ? HIGH : LOW);
  digitalWrite(ain2, dir_fwd ? LOW : HIGH);
  analogWrite(pwm, p);
}

void motor_init(void) {
  pinMode(PIN_MOTOR_AIN1, OUTPUT);
  pinMode(PIN_MOTOR_AIN2, OUTPUT);
  pinMode(PIN_MOTOR_PWMA, OUTPUT);
  pinMode(PIN_MOTOR_BIN1, OUTPUT);
  pinMode(PIN_MOTOR_BIN2, OUTPUT);
  pinMode(PIN_MOTOR_PWMB, OUTPUT);
  motor_brake();

  pinMode(PIN_ENC_LA, INPUT_PULLUP);
  pinMode(PIN_ENC_RA, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_LA), enc_left_isr, RISING);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_RA), enc_right_isr, RISING);

  pinMode(PIN_FALL_L, INPUT);
  pinMode(PIN_FALL_R, INPUT);
}

void motor_brake(void) {
  digitalWrite(PIN_MOTOR_AIN1, HIGH);
  digitalWrite(PIN_MOTOR_AIN2, HIGH);
  digitalWrite(PIN_MOTOR_BIN1, HIGH);
  digitalWrite(PIN_MOTOR_BIN2, HIGH);
  analogWrite(PIN_MOTOR_PWMA, 0);
  analogWrite(PIN_MOTOR_PWMB, 0);
}

void motor_cmd(const char* cmd, int speed) {
  if (_falling) return; // 防跌落触发期间禁止移动（需电脑解除）

  if (strcmp(cmd, "forward") == 0) {
    motor_write(PIN_MOTOR_AIN1, PIN_MOTOR_AIN2, PIN_MOTOR_PWMA, true, speed);
    motor_write(PIN_MOTOR_BIN1, PIN_MOTOR_BIN2, PIN_MOTOR_PWMB, true, speed);
  } else if (strcmp(cmd, "back") == 0) {
    motor_write(PIN_MOTOR_AIN1, PIN_MOTOR_AIN2, PIN_MOTOR_PWMA, false, speed);
    motor_write(PIN_MOTOR_BIN1, PIN_MOTOR_BIN2, PIN_MOTOR_PWMB, false, speed);
  } else if (strcmp(cmd, "left") == 0) {
    motor_write(PIN_MOTOR_AIN1, PIN_MOTOR_AIN2, PIN_MOTOR_PWMA, true, speed);
    motor_write(PIN_MOTOR_BIN1, PIN_MOTOR_BIN2, PIN_MOTOR_PWMB, false, speed);
  } else if (strcmp(cmd, "right") == 0) {
    motor_write(PIN_MOTOR_AIN1, PIN_MOTOR_AIN2, PIN_MOTOR_PWMA, false, speed);
    motor_write(PIN_MOTOR_BIN1, PIN_MOTOR_BIN2, PIN_MOTOR_PWMB, true, speed);
  } else {
    motor_brake();
  }
}

bool motor_fall_check(void) {
  bool l = digitalRead(PIN_FALL_L) == HIGH; // TCRT5000 遮挡=0/悬空=1（按模块逻辑调整）
  bool r = digitalRead(PIN_FALL_R) == HIGH;
  if (l || r) {
    if (!_falling) {
      _falling = true;
      motor_brake();
    }
    return true;
  }
  _falling = false;
  return false;
}

long motor_enc_left(void)  { return _enc_left; }
long motor_enc_right(void) { return _enc_right; }
