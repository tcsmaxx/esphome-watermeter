#include "meter_setup.h"
#include "esp_camera.h"
#include "esphome/core/log.h"
namespace esphome::meter_setup {
bool MeterSetup::image_controls_available_() const {
  auto *s=esp_camera_sensor_get();return s&&s->set_exposure_ctrl&&s->set_ae_level&&s->set_contrast&&s->set_saturation&&s->set_wb_mode;
}
void MeterSetup::image_setup_(){
  image_preference_=global_preferences->make_preference<ImageSettings>(0x7a32b90d);
  ImageSettings saved;if(image_preference_.load(&saved)&&valid_image_settings(saved))image_settings_=saved;
  pending_image_=image_settings_;image_status_=image_controls_available_()?"Bildeinstellungen bereit":"Bildeinstellungen für diese Kamera nicht verfügbar";
}
bool MeterSetup::prepare_image_settings_(){
  if(focus_only_)return true;
  if(!image_controls_available_())return true;
  if(image_applied_&&active_image_==applied_image_&&image_power_generation_==camera_power_.generation()){
    if(int32_t(millis()-image_settle_until_)<0)return false;
    image_status_="Bildeinstellungen angewendet";return true;
  }
  auto *s=esp_camera_sensor_get();
  // Change only image controls; preserve focus, geometry, gain and standby registers.
  const bool ok=s->set_exposure_ctrl(s,1)==0&&s->set_ae_level(s,active_image_.exposure)==0&&s->set_contrast(s,active_image_.contrast)==0&&s->set_saturation(s,active_image_.saturation)==0&&s->set_wb_mode(s,active_image_.white_balance)==0;
  if(!ok){
    image_applied_=false;image_status_="Bildeinstellungen konnten nicht angewendet werden";message_=image_status_;ESP_LOGW("meter_image","%s",message_.c_str());
    capture_pending_=false;busy_=false;inference_started_=false;preview_active_=false;reader_->set_pause_processing(true);set_illumination_(light_test_,pending_illumination_);
    if(capture_inference_&&!test_){reading_problem_=true;reading_error_=message_;}
    next_=millis()+settings_.interval*1000;return false;
  }
  applied_image_=active_image_;image_applied_=true;image_power_generation_=camera_power_.generation();image_settle_until_=millis()+300;
  image_status_="Belichtung und Weißabgleich passen sich an";message_=image_status_+" …";return false;
}
}
