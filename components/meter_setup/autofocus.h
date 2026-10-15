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
  State state();
  int error() const {return error_.load();}
 protected:
  static void task_(void *context);
  std::atomic<int> state_{IDLE},error_{0};
  std::atomic<bool> reset_requested_{false};
  uint32_t started_{0};
  bool initialized_{false}; // Owned exclusively by successive AF worker tasks.
};
}
