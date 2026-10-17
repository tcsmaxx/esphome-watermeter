#pragma once
#include <cstdint>
#include <string>
namespace esphome::meter_setup {
struct ImageSettings {
  uint32_t version{1};
  int8_t exposure{0},contrast{0},saturation{0};
  uint8_t white_balance{0};
  bool operator==(const ImageSettings &v)const{return exposure==v.exposure&&contrast==v.contrast&&saturation==v.saturation&&white_balance==v.white_balance;}
};
inline bool valid_image_settings(const ImageSettings &v){return v.version==1&&v.exposure>=-2&&v.exposure<=2&&v.contrast>=-2&&v.contrast<=2&&v.saturation>=-2&&v.saturation<=2&&v.white_balance<=4;}
inline bool parse_image_adjustment(const std::string &s,int8_t &v){if(s=="-2")v=-2;else if(s=="-1")v=-1;else if(s=="0")v=0;else if(s=="1")v=1;else if(s=="2")v=2;else return false;return true;}
}
