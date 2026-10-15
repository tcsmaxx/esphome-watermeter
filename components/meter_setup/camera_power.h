#pragma once
#include <cstdint>
#include <string>
#include "esphome/core/preferences.h"
namespace esphome::meter_setup {
struct CameraPowerSettings {uint32_t version{1};uint8_t standby{1},weak_drive{0};};
class CameraPowerController {
 public:
  void setup();
  void request();
  void loop(bool hold);
  bool ready();
  uint32_t generation() const {return generation_;}
  bool configure(bool standby,bool weak_drive);
  bool supported() const;
  bool sleeping() const {return sleeping_&&!failed_;}
  bool standby_enabled() const {return settings_.standby;}
  bool weak_drive() const {return settings_.weak_drive;}
  const std::string &status() const {return status_;}
 protected:
  bool set_sleep_(bool sleep);
  bool apply_drive_();
  CameraPowerSettings settings_{};
  ESPPreferenceObject preference_;
  bool sleeping_{false},waking_{false},failed_{false},drive_applied_{false};
  uint32_t generation_{0};
  int original_drive_{-1};
  uint32_t last_activity_{0},wake_started_{0},last_attempt_{0},drive_attempt_{0};
  std::string status_{"Noch nicht bereit"};
};
}
