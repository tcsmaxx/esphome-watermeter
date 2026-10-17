#include "../components/meter_setup/led_selection.h"
#include <cassert>
#include <iostream>
using namespace esphome::meter_setup;
int main(){
 uint64_t mask=7;
 for(const auto *invalid:{"","0","ffffffffffffffff0","-000000000000001","fffffffffffffffg"," fffffffffffffff"}){assert(!parse_led_mask(invalid,mask));assert(mask==7);}
 assert(parse_led_mask("0000000000000000",mask)&&mask==0);
 assert(parse_led_mask("FFFFFFFFFFFFFFFF",mask)&&mask==UINT64_MAX);
 for(int i=0;i<64;i++){const auto bit=uint64_t(1)<<i;assert(parse_led_mask(format_led_mask(bit),mask)&&mask==bit);}
 assert(format_led_mask(UINT64_MAX)=="ffffffffffffffff");assert(format_led_mask(uint64_t(1)<<63)=="8000000000000000");
 std::cout<<"LED selection codec passed: all 64 positions, empty/all selection, strict validation and unchanged output on errors\n";
}
