#pragma once
#include <cstdint>
#include <string>
namespace esphome::meter_setup {
// Fixed-width hexadecimal strings preserve all 64 bits in browsers and backups.
inline bool parse_led_mask(const std::string &text,uint64_t &out) {
  if(text.size()!=16)return false;
  uint64_t value=0;
  for(char c:text){int n=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;if(n<0)return false;value=(value<<4)|uint64_t(n);}
  out=value;return true;
}
inline std::string format_led_mask(uint64_t value) {
  static constexpr char hex[]="0123456789abcdef";
  std::string text(16,'0');for(int i=15;i>=0;--i){text[i]=hex[value&15];value>>=4;}return text;
}
}
