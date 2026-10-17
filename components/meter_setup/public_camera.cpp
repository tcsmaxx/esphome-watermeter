#include "meter_setup.h"
#include "esphome/core/log.h"
namespace esphome::meter_setup {
void MeterSetup::prepare_public_image_(){
  // Publish only after processing has finished; a test image is also useful for setup.
  if(busy_||!inference_jpeg_||timestamped_sequence_==preview_sequence_)return;
  auto image=inference_jpeg_;auto size=inference_jpeg_size_;
  if(preview_){
    if(preview_rgb_){
      if(!preview_jpeg_||preview_jpeg_sequence_!=preview_sequence_)prepare_preview_();
      if(preview_jpeg_&&preview_jpeg_sequence_==preview_sequence_){image=preview_jpeg_;size=preview_jpeg_size_;}
    }else{image=preview_;size=preview_size_;}
  }
  auto annotated=timestamp_jpeg(image.get(),size,inference_capture_epoch_);
  if(annotated.data)public_image_=std::move(annotated);
  else{public_image_={image,size};ESP_LOGW("meter_setup","Zeitstempel im Kamerabild fehlgeschlagen; Aufnahme ohne Zeitstempel übertragen");}
  timestamped_sequence_=preview_sequence_;
  if(public_camera_)public_camera_->set_processed_image(public_image_);
}
}
