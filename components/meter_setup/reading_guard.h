#pragma once
#include <cstdint>
#include <cstdlib>
#include <cmath>
#include <string>
namespace esphome::meter_setup {
inline bool parse_reading(const std::string &log, std::string &digits, float &confidence, uint32_t &raw) {
  if(log.rfind("Reading: ",0)!=0) return false;
  const auto end=log.find(" -> ");
  digits=end==std::string::npos?"":log.substr(9,end-9);
  const auto pos=log.find("confidence: ");
  confidence=pos==std::string::npos?0:std::strtof(log.c_str()+pos+12,nullptr);
  // Log rounds to 0.1 %. 90.1 rather than 90.0 avoids accepting 89.95 % rounded up.
  if(digits.size()!=8 || digits.find_first_not_of("0123456789")!=std::string::npos || !std::isfinite(confidence) || confidence<90.1f || log.find("valid: yes")==std::string::npos) return false;
  raw=std::strtoul(digits.c_str(),nullptr,10); return true;
}
inline bool within_range(uint32_t raw,uint32_t baseline,uint32_t max_step) {
  return raw>=baseline && raw-baseline<=max_step;
}
}
