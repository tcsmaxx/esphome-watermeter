#pragma once
#include <atomic>
#include <cstdint>
#include "esphome/core/hal.h"
namespace esphome::meter_setup {
class AutofocusController {
 public:
  enum State {IDLE,RUNNING,FOCUSED,FAILED,HUNG,UNSUPPORTED};
  bool supported() const;
  void invalidate(){reset_requested_=true;}
  bool start();
  bool start_manual(uint16_t position);
  int position() const {return position_.load();}
  State state();
  int error() const {return error_.load();}
 protected:
  bool begin_(bool manual,uint16_t position);
  bool manual_{false};
  uint16_t requested_position_{512};
  std::atomic<int> position_{-1};
  static void task_(void *context);
  std::atomic<int> state_{IDLE},error_{0};
  std::atomic<bool> reset_requested_{false};
  uint32_t started_{0};
  bool initialized_{false}; // Owned exclusively by successive AF worker tasks.
};
}
