#pragma once
#include <ctime>
#include <memory>
#include <vector>
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
  float get_setup_priority() const override {return setup_priority::IO-1;}
  void add_listener(camera::CameraListener *listener) override {listeners_.push_back(listener);}
  camera::CameraImageReader *create_image_reader() override;
  void request_image(camera::CameraRequester requester) override {source_->request_image(requester);}
  void start_stream(camera::CameraRequester requester) override {source_->start_stream(requester);}
  void stop_stream(camera::CameraRequester requester) override {source_->stop_stream(requester);}
  void on_camera_image(const std::shared_ptr<camera::CameraImage> &image) override;
  void on_stream_start() override {for(auto *listener:listeners_)listener->on_stream_start();}
  void on_stream_stop() override {for(auto *listener:listeners_)listener->on_stream_stop();}
 protected:
  explicit TimestampCamera(esp32_camera::ESP32Camera *source):source_(source){}
  esp32_camera::ESP32Camera *source_;
  std::vector<camera::CameraListener *> listeners_;
};
}
