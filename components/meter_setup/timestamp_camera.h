#pragma once
#include <ctime>
#include <memory>
#include <vector>
#include "camera_power.h"
#include "esphome/components/esp32_camera/esp32_camera.h"
namespace esphome::meter_setup {
struct TimestampJpeg {std::shared_ptr<uint8_t> data;size_t size{0};};
std::time_t camera_capture_epoch(const std::shared_ptr<camera::CameraImage> &image);
TimestampJpeg timestamp_jpeg(const uint8_t *data,size_t size,std::time_t captured);
// Public camera delegates hardware control, but supplies private annotated JPEGs.
// Hardware listeners (OCR, setup and alignment) continue receiving raw images.
class TimestampCamera : public camera::Camera, public camera::CameraListener {
 public:
  static TimestampCamera *install(esp32_camera::ESP32Camera *source);
  void setup() override;
  void loop() override;
  void set_power(CameraPowerController *power){power_=power;}
  void set_processed_image(const TimestampJpeg &jpeg);
  float get_setup_priority() const override {return setup_priority::IO-1;}
  void add_listener(camera::CameraListener *listener) override {listeners_.push_back(listener);}
  camera::CameraImageReader *create_image_reader() override;
  void request_image(camera::CameraRequester requester) override {pending_requests_|=1U<<requester;}
  void start_stream(camera::CameraRequester requester) override {streams_|=1U<<requester;}
  void stop_stream(camera::CameraRequester requester) override {streams_&=~(1U<<requester);if(active_streams_&(1U<<requester)){source_->stop_stream(requester);active_streams_&=~(1U<<requester);}}
  void on_camera_image(const std::shared_ptr<camera::CameraImage> &image) override;
  void on_stream_start() override {for(auto *listener:listeners_)listener->on_stream_start();}
  void on_stream_stop() override {for(auto *listener:listeners_)listener->on_stream_stop();}
 protected:
  explicit TimestampCamera(esp32_camera::ESP32Camera *source):source_(source){}
  esp32_camera::ESP32Camera *source_;
  CameraPowerController *power_{nullptr};
  std::shared_ptr<camera::CameraImage> cached_,processed_;
  uint8_t pending_requests_{0},streams_{0},active_streams_{0};
  std::vector<camera::CameraListener *> listeners_;
};
}
