// =====================================================
// 屏幕实现：Adafruit ST7789 + GFX，极简大眼睛表情
// =====================================================

#include "display_ctrl.h"
#include "config.h"

static Adafruit_ST7789 _tft(PIN_TFT_CS, PIN_TFT_DC, PIN_TFT_RST);

#define SCR_W 240
#define SCR_H 240

// 屏幕中心大眼睛的几何参数
#define EYE_R 34        // 眼球半径
#define EYE_DX 46       // 两眼中点偏移
#define EYE_CY 100      // 眼球垂直中心
#define PUPIL_R 14      // 瞳孔半径

static void draw_eyes(int pupil_dx, int pupil_dy, bool blink) {
  _tft.fillScreen(ST77XX_WHITE);
  for (int side = -1; side <= 1; side += 2) {
    int cx = SCR_W / 2 + side * EYE_DX;
    // 眼皮（眨眼时画肤色横条）
    if (blink) {
      _tft.fillRoundRect(cx - EYE_R, EYE_CY - 8, EYE_R * 2, 16, 6, ST77XX_WHITE);
      _tft.drawLine(cx - EYE_R, EYE_CY, cx + EYE_R, EYE_CY, ST77XX_BLACK);
      continue;
    }
    _tft.fillCircle(cx, EYE_CY, EYE_R, ST77XX_BLACK);        // 眼白外圈
    _tft.fillCircle(cx, EYE_CY, EYE_R - 4, ST77XX_WHITE);    // 眼白
    _tft.fillCircle(cx + pupil_dx, EYE_CY + pupil_dy, PUPIL_R, ST77XX_BLACK); // 瞳孔
    _tft.fillCircle(cx + pupil_dx - 4, EYE_CY + pupil_dy - 4, 4, ST77XX_WHITE); // 高光
  }
}

static void draw_face(const char* expr) {
  if (strcmp(expr, "happy") == 0) {         // 眯眼笑
    _tft.fillScreen(ST77XX_WHITE);
    for (int side = -1; side <= 1; side += 2) {
      int cx = SCR_W / 2 + side * EYE_DX;
      _tft.fillRoundRect(cx - EYE_R, EYE_CY - 8, EYE_R * 2, 16, 6, ST77XX_BLACK);
    }
    _tft.drawLine(SCR_W / 2 - 24, EYE_CY + 60, SCR_W / 2, EYE_CY + 72, ST77XX_BLACK);
    _tft.drawLine(SCR_W / 2 + 24, EYE_CY + 60, SCR_W / 2, EYE_CY + 72, ST77XX_BLACK);
  } else if (strcmp(expr, "sad") == 0) {
    draw_eyes(0, 6, false);
    _tft.drawLine(SCR_W / 2 - 20, EYE_CY + 66, SCR_W / 2, EYE_CY + 52, ST77XX_BLACK);
    _tft.drawLine(SCR_W / 2 + 20, EYE_CY + 66, SCR_W / 2, EYE_CY + 52, ST77XX_BLACK);
  } else if (strcmp(expr, "sleep") == 0) {
    for (int side = -1; side <= 1; side += 2) {
      int cx = SCR_W / 2 + side * EYE_DX;
      _tft.fillScreen(ST77XX_WHITE);
      _tft.drawLine(cx - EYE_R, EYE_CY, cx + EYE_R, EYE_CY, ST77XX_BLACK);
      _tft.drawLine(cx - EYE_R, EYE_CY + 4, cx + EYE_R, EYE_CY + 4, ST77XX_BLACK);
    }
  } else if (strcmp(expr, "surprise") == 0) {
    draw_eyes(0, 0, false);
    _tft.fillCircle(SCR_W / 2, EYE_CY + 62, 5, ST77XX_BLACK);
  } else { // idle / thinking 等默认：正常大眼睛
    draw_eyes(0, 0, false);
  }
}

void display_init(void) {
  _tft.init(SCR_H, SCR_W); // ST7789 240x240（旋转后宽高互换）
  _tft.setRotation(0);
  _tft.fillScreen(ST77XX_WHITE);
}

void display_set_face(const char* expr) {
  draw_face(expr);
}

void display_set_text(const char* text) {
  _tft.fillScreen(ST77XX_WHITE);
  _tft.setTextColor(ST77XX_BLACK);
  _tft.setTextSize(2);
  _tft.setCursor(10, SCR_H / 2 - 10);
  _tft.println(text);
}

void display_clear(void) {
  _tft.fillScreen(ST77XX_WHITE);
}
