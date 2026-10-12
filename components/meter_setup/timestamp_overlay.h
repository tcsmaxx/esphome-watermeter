#pragma once
#include <cstdint>
#include <cstddef>
#include <cstring>
namespace esphome::meter_setup {
// Compact 5x7 font; only characters used by the German capture timestamp.
inline const uint8_t *timestamp_glyph(char c) {
  static constexpr uint8_t digits[10][5]={{0x3e,0x51,0x49,0x45,0x3e},{0,0x42,0x7f,0x40,0},{0x42,0x61,0x51,0x49,0x46},{0x21,0x41,0x45,0x4b,0x31},{0x18,0x14,0x12,0x7f,0x10},{0x27,0x45,0x45,0x45,0x39},{0x3c,0x4a,0x49,0x49,0x30},{0x01,0x71,0x09,0x05,0x03},{0x36,0x49,0x49,0x49,0x36},{0x06,0x49,0x49,0x29,0x1e}};
  static constexpr uint8_t dot[5]={0,0x60,0x60,0,0},colon[5]={0,0x36,0x36,0,0},dash[5]={8,8,8,8,8},space[5]={};
  if(c>='0'&&c<='9')return digits[c-'0'];
  return c=='.'?dot:c==':'?colon:c=='-'?dash:space;
}
inline bool draw_capture_timestamp(uint8_t *rgb,size_t size,int width,int height,const char *text) {
  if(!rgb||!text||width<248||height<28||size<size_t(width)*height*3||std::strlen(text)!=19)return false;
  constexpr int scale=2,x=8;const int y=height-20;
  for(int row=y-4;row<height-2;row++)for(int col=x-4;col<x+19*12+4;col++){
    auto *p=rgb+(size_t(row)*width+col)*3;p[0]=p[1]=p[2]=0;
  }
  for(int n=0;n<19;n++)for(int col=0;col<5;col++)for(int row=0;row<7;row++)if(timestamp_glyph(text[n])[col]&(1<<row))
    for(int dy=0;dy<scale;dy++)for(int dx=0;dx<scale;dx++){
      auto *p=rgb+(size_t(y+row*scale+dy)*width+x+n*12+col*scale+dx)*3;p[0]=p[1]=p[2]=255;
    }
  return true;
}
}
