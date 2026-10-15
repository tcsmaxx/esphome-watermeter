#include "timestamp_camera.h"
#include "timestamp_overlay.h"
#include "esphome/core/log.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_jpeg_dec.h"
#include "esp_jpeg_enc.h"
#include <algorithm>
namespace esphome::meter_setup {
std::time_t camera_capture_epoch(const std::shared_ptr<camera::CameraImage> &image) {
  const auto now=std::time(nullptr);if(now<1609459200)return 0;
  const auto *fb=static_cast<esp32_camera::ESP32CameraImage *>(image.get())->get_raw_buffer();
  const int64_t taken=int64_t(fb->timestamp.tv_sec)*1000000+fb->timestamp.tv_usec;
  const auto age=std::max<int64_t>(0,esp_timer_get_time()-taken);
  return now-age/1000000;
}
TimestampJpeg timestamp_jpeg(const uint8_t *data,size_t size,std::time_t captured) {
  if(!data||size<4)return {};
  jpeg_dec_config_t config=DEFAULT_JPEG_DEC_CONFIG();config.output_type=JPEG_PIXEL_FORMAT_RGB888;
  config.scale.width=config.clipper.width=640;config.scale.height=config.clipper.height=480;config.block_enable=false;
  jpeg_dec_handle_t decoder=nullptr;if(jpeg_dec_open(&config,&decoder)!=JPEG_ERR_OK)return {};
  auto rgb=std::shared_ptr<uint8_t>(static_cast<uint8_t*>(heap_caps_aligned_alloc(16,640*480*3,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),heap_caps_free);
  if(!rgb){jpeg_dec_close(decoder);return {};}
  jpeg_dec_io_t io{};io.inbuf=const_cast<uint8_t*>(data);io.inbuf_len=io.inbuf_remain=size;io.outbuf=rgb.get();io.out_size=640*480*3;
  jpeg_dec_header_info_t header{};
  bool ok=jpeg_dec_parse_header(decoder,&io,&header)==JPEG_ERR_OK&&header.width==640&&header.height==480;
  if(ok)ok=jpeg_dec_process(decoder,&io)==JPEG_ERR_OK;
  jpeg_dec_close(decoder);if(!ok)return {};
  char stamp[32]="--.--.---- --:--:--";
  if(captured>1609459200){struct tm local{};if(localtime_r(&captured,&local))std::strftime(stamp,sizeof(stamp),"%d.%m.%Y %H:%M:%S",&local);}
  if(!draw_capture_timestamp(rgb.get(),640*480*3,640,480,stamp))return {};
  jpeg_enc_config_t encode=DEFAULT_JPEG_ENC_CONFIG();encode.width=640;encode.height=480;encode.src_type=JPEG_PIXEL_FORMAT_RGB888;encode.quality=85;encode.subsampling=JPEG_SUBSAMPLE_420;
  jpeg_enc_handle_t encoder=nullptr;if(jpeg_enc_open(&encode,&encoder)!=JPEG_ERR_OK)return {};
  constexpr size_t capacity=256*1024;
  auto jpeg=std::shared_ptr<uint8_t>(static_cast<uint8_t*>(heap_caps_aligned_alloc(16,capacity,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)),heap_caps_free);
  int length=0;ok=jpeg&&jpeg_enc_process(encoder,rgb.get(),640*480*3,jpeg.get(),capacity,&length)==JPEG_ERR_OK&&length>0&&size_t(length)<=capacity;
  jpeg_enc_close(encoder);if(!ok)return {};
  return {std::move(jpeg),size_t(length)};
}
class TimestampImage : public camera::CameraImage {
 public:
  TimestampImage(TimestampJpeg jpeg,const std::shared_ptr<camera::CameraImage> &source):jpeg_(std::move(jpeg)){for(int i=0;i<3;i++)requested_[i]=source->was_requested_by(static_cast<camera::CameraRequester>(i));}
  uint8_t *get_data_buffer() override {return jpeg_.data.get();}
  size_t get_data_length() override {return jpeg_.size;}
  bool was_requested_by(camera::CameraRequester r) const override {return int(r)<3&&(r==camera::API_REQUESTER||requested_[int(r)]);}
 protected: TimestampJpeg jpeg_;bool requested_[3]{};
};
class TimestampImageReader : public camera::CameraImageReader {
 public:
  void set_image(std::shared_ptr<camera::CameraImage> image) override {image_=std::move(image);offset_=0;}
  size_t available() const override {return image_?image_->get_data_length()-offset_:0;}
  uint8_t *peek_data_buffer() override {return image_?image_->get_data_buffer()+offset_:nullptr;}
  void consume_data(size_t count) override {offset_+=std::min(count,available());}
  void return_image() override {image_.reset();offset_=0;}
 protected: std::shared_ptr<camera::CameraImage> image_;size_t offset_{0};
};
TimestampCamera *TimestampCamera::install(esp32_camera::ESP32Camera *source) {
  // Replace the single public endpoint only after constructing the hardware camera.
  // The hardware instance and its original listeners remain in place.
  global_camera=nullptr;
  return new TimestampCamera(source);
}
void TimestampCamera::setup() {
  // Preserve name, object-id hash, device association and entity flags exactly.
  static_cast<EntityBase&>(*this)=static_cast<const EntityBase&>(*source_);
  source_->add_listener(this);
}
camera::CameraImageReader *TimestampCamera::create_image_reader(){return new TimestampImageReader;}
void TimestampCamera::loop() {
  if(pending_requests_&&cached_&&!streams_){
    // Ordinary HA still-image polling reuses the last real capture without heat.
    for(auto *listener:listeners_)listener->on_camera_image(cached_);
    pending_requests_=0;
  }
  if(!pending_requests_&&!streams_)return;
  if(power_){power_->request();if(!power_->ready())return;}
  for(int i=0;i<3;i++)if((streams_&(1U<<i))&&!(active_streams_&(1U<<i))){source_->start_stream(static_cast<camera::CameraRequester>(i));active_streams_|=1U<<i;}
  for(int i=0;i<3;i++)if(pending_requests_&(1U<<i))source_->request_image(static_cast<camera::CameraRequester>(i));
  pending_requests_=0;
}
void TimestampCamera::on_camera_image(const std::shared_ptr<camera::CameraImage> &image) {
  if(listeners_.empty())return;
  auto jpeg=timestamp_jpeg(image->get_data_buffer(),image->get_data_length(),camera_capture_epoch(image));
  if(!jpeg.data){ESP_LOGW("meter_setup","Zeitstempel im API-Bild fehlgeschlagen; Rohbild übertragen");for(auto *listener:listeners_)listener->on_camera_image(image);return;}
  auto annotated=std::make_shared<TimestampImage>(std::move(jpeg),image);
  cached_=annotated;
  for(auto *listener:listeners_)listener->on_camera_image(annotated);
}
}
