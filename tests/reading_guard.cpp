#include "../components/meter_setup/reading_guard.h"
#include <cassert>
#include <iostream>
using namespace esphome::meter_setup;
int main() {
  std::string digits;float conf;uint32_t raw;
  assert(parse_reading("Reading: 00123456 -> 123456.0 (valid: yes, confidence: 97.5%, threshold: 90.0%)",digits,conf,raw));
  assert(digits=="00123456" && raw==123456 && conf==97.5f);
  assert(parse_reading("Reading: 99999999 -> 100000000.0 (valid: yes, confidence: 99.0%, threshold: 90.0%)",digits,conf,raw));
  assert(raw==99999999); // Integer guard never takes the rounded float from the upstream log.
  for(const auto &s:{"Reading: 00123456 -> 123456.0 (valid: no, confidence: 98.0%)", "Reading: 00123456 -> 123456.0 (valid: yes, confidence: 90.0%)", "Reading: 00123456 -> 123456.0 (valid: yes, confidence: nan%)", "Reading: 0123456 -> 123456.0 (valid: yes, confidence: 99.0%)", "Reading: 00-23456 -> 123456.0 (valid: yes, confidence: 99.0%)", "unrelated event"}) assert(!parse_reading(s,digits,conf,raw));
  assert(within_range(123456,123456,1000));assert(within_range(124456,123456,1000));
  assert(!within_range(123455,123456,1000));assert(!within_range(124457,123456,1000));
  assert(!within_range(0,99999999,1000));
  for(int count=1;count<=9;count++){const std::string n(count,'9');assert(parse_reading("Reading: "+n+" -> 1000000000 (valid: yes, confidence: 99.0%)",digits,conf,raw,count));assert(raw==std::strtoul(n.c_str(),nullptr,10));assert(!parse_reading("Reading: "+n+" -> 0 (valid: yes, confidence: 99.0%)",digits,conf,raw,count==9?8:count+1));}
  assert(!parse_reading("Reading: 9999999999 -> 0 (valid: yes, confidence: 99.0%)",digits,conf,raw,10));
  std::cout<<"Reading guard tests passed\n";
}
