#ifndef DISPLAY_CTRL_H
#define DISPLAY_CTRL_H

#include <Arduino.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>

// =====================================================
// 1.3 寸 ST7789 屏幕：大眼睛表情 + 文字
// 表情枚举：happy / sad / thinking / idle / sleep / surprise
// =====================================================

void display_init(void);
void display_set_face(const char* expr);
void display_set_text(const char* text);
void display_clear(void);

#endif // DISPLAY_CTRL_H
