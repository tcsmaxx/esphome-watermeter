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
struct ImageLimits {int8_t exposure{2},contrast{2},saturation{2};};
inline bool valid_image_settings(const ImageSettings &v){return v.version==1&&v.exposure>=-5&&v.exposure<=5&&v.contrast>=-3&&v.contrast<=3&&v.saturation>=-4&&v.saturation<=4&&v.white_balance<=4;}
inline bool valid_image_settings(const ImageSettings &v,const ImageLimits &limits){return valid_image_settings(v)&&v.exposure>=-limits.exposure&&v.exposure<=limits.exposure&&v.contrast>=-limits.contrast&&v.contrast<=limits.contrast&&v.saturation>=-limits.saturation&&v.saturation<=limits.saturation;}
inline bool parse_image_adjustment(const std::string &s,int8_t &v,int limit=5){
  int value;if(s=="0")value=0;else if(s.size()==1&&s[0]>='1'&&s[0]<='5')value=s[0]-'0';else if(s.size()==2&&s[0]=='-'&&s[1]>='1'&&s[1]<='5')value=-(s[1]-'0');else return false;
  if(value < -limit||value>limit)return false;v=value;return true;
}
}
